"""ReMarket marketplace integration — import completed sales as custody events.

ReMarket (https://github.com/arpan-basak/ReMarket) is a used-item marketplace
that lets a seller attach a CraftProof certificate code to a listing. When the
item sells, ReMarket knows two things CraftProof does not: *who bought it* and
*which order recorded the sale*. This module pulls that feed and appends the
new holder to the certificate's custody chain.

Direction of travel
-------------------
CraftProof is the API *client* here. ReMarket never writes to CraftProof; it
exposes a key-protected, read-only feed and CraftProof polls it:

    GET {REMARKET_API_URL}/api/v1/sales?after_id=<n>&limit=100
    Authorization: Bearer {REMARKET_SALE_API_KEY}

The contract is pinned in the partner repo's CRAFTPROOF_INTEGRATION.md.

What this module guarantees
---------------------------
* **Idempotence** — each ReMarket ``order_id`` imports at most once, enforced
  by a primary key on ``remarket_imports``, inside the same transaction that
  writes the custody record. Re-polling the same sale is a no-op.
* **Title agreement** — a sale only touches a certificate when the ReMarket
  listing title matches the certificate's piece title (case- and
  whitespace-insensitive). A mismatch is skipped and retried later, so a
  wrong or guessed code can never rewrite an unrelated certificate.
* **Honest attribution** — the record is signed by a dedicated integration
  service account, never by the previous owner. The chain therefore says
  "ReMarket reported this sale", not "the owner confirmed this handover".

What this module does NOT establish
-----------------------------------
A matching code and title is a *safety check*, not proof of seller authority.
ReMarket's checkout is a simulation with no payment and no physical handoff,
and its buyer names are self-reported. Imported steps are consequently marked
as marketplace-reported everywhere they surface (API and certificate page) so
a reader is never told a marketplace claim was confirmed by a custodian.

Signing key
-----------
The service account's private key lives in a file *outside* the custody
database (same reasoning as anchoring.py): exfiltrating the DB must not yield
the ability to mint new custody records. The ``users`` row holds only the
public half, so chain verification works normally.
"""

from __future__ import annotations

import hmac
import os
import re
import secrets
from typing import Any, Optional

import httpx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import HTTPException

from core import create_checkpoint
from crypto_utils import pubkey_to_hex, sign
from database import get_db
from record import CustodyRecord

# ------------------------------------------------------------------ configuration

#: Identity of the service account that signs imported sales.
SERVICE_EMAIL = "remarket-import@craftproof.local"
SERVICE_NAME = "ReMarket"
SERVICE_ROLE = "integration"

#: Marker stored in users.encrypted_privkey for accounts whose signing key is
#: held in a file rather than a password envelope. Never a valid hex seed, so
#: an accidental sign-as-this-user path fails loudly instead of silently.
EXTERNAL_KEY_MARKER = "external-key-file:remarket"

#: Where the integration signing key is kept. Deliberately not in the DB.
_KEY_FILE = os.environ.get(
    "CRAFTPROOF_REMARKET_KEY",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "integration", "remarket_signer.key"),
)

#: ReMarket's documented page ceiling.
_MAX_LIMIT = 100

#: Cursor key in the integration_state table.
_CURSOR_KEY = "remarket_after_id"
_LAST_SYNC_KEY = "remarket_last_sync"

_ORDER_ID_RE = re.compile(r"RM-\d+")


def api_url() -> str:
    return os.environ.get("REMARKET_API_URL", "").strip().rstrip("/")


def api_key() -> str:
    return os.environ.get("REMARKET_SALE_API_KEY", "").strip()


def is_configured() -> bool:
    """True when both halves of the ReMarket credential are present."""
    return bool(api_url() and api_key())


def sync_interval() -> int:
    """Seconds between background polls; 0 disables the poller."""
    try:
        return max(0, int(os.environ.get("REMARKET_SYNC_INTERVAL_SECONDS", "300")))
    except ValueError:
        return 300


def require_sync_key(supplied: Optional[str]) -> None:
    """Gate the manual sync endpoint on a shared secret.

    Separate from the ReMarket key on purpose: whoever may *trigger* a sync is
    not automatically trusted with the credential that reads the partner's
    sales data.
    """
    expected = os.environ.get("CRAFTPROOF_REMARKET_SYNC_KEY", "").strip()
    if not expected:
        raise HTTPException(503, "ReMarket sync key is not configured on this server")
    if not supplied or not hmac.compare_digest(supplied, expected):
        raise HTTPException(401, "Valid integration key required")


# ------------------------------------------------------------------ small state store


def _get_state(conn, key: str) -> Optional[str]:
    row = conn.execute("SELECT value FROM integration_state WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


def _set_state(conn, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO integration_state (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP",
        (key, value),
    )


def read_cursor() -> int:
    conn = get_db()
    try:
        raw = _get_state(conn, _CURSOR_KEY)
    finally:
        conn.close()
    try:
        return max(0, int(raw)) if raw is not None else 0
    except ValueError:
        return 0


def write_cursor(after_id: int) -> None:
    conn = get_db()
    try:
        _set_state(conn, _CURSOR_KEY, str(max(0, int(after_id))))
        conn.commit()
    finally:
        conn.close()


# ------------------------------------------------------------------ HTTP client


def remarket_client() -> httpx.Client:
    """An httpx client pre-authenticated against the partner's sales API.

    The key is read from the environment at call time and never logged, never
    stored in the database, and never sent to the browser — every call to
    ReMarket happens server-side.
    """
    base_url, key = api_url(), api_key()
    if not base_url or not key:
        raise HTTPException(
            503,
            "ReMarket is not configured — set REMARKET_API_URL and REMARKET_SALE_API_KEY",
        )
    return httpx.Client(
        base_url=base_url,
        headers={
            "Authorization": f"Bearer {key}",
            "Accept": "application/json",
            "User-Agent": "CraftProof-ReMarket-Importer/1.0",
        },
        # Render free services sleep; a cold start can take a while to answer.
        timeout=httpx.Timeout(30.0, connect=15.0),
        # Never chase a redirect: following one off-host would leak the bearer
        # token to whatever the partner host happens to point at.
        follow_redirects=False,
    )


def _as_json(response: httpx.Response) -> Any:
    if response.status_code == 401:
        raise HTTPException(502, "ReMarket rejected the sale API key (401)")
    if response.status_code == 503:
        raise HTTPException(502, "ReMarket has no sale API key configured (503)")
    response.raise_for_status()
    return response.json()


def fetch_sales(client: httpx.Client, after_id: int, limit: int = _MAX_LIMIT) -> dict:
    """One page of completed, certificate-bearing sales, oldest first."""
    try:
        payload = _as_json(
            client.get("/api/v1/sales", params={"after_id": after_id, "limit": limit})
        )
        if not isinstance(payload, dict):
            raise ValueError("sales response is not an object")
        if not isinstance(payload.get("sales"), list):
            raise ValueError("sales response has no 'sales' list")
        if not isinstance(payload.get("next_after_id"), int):
            raise ValueError("sales response has no integer 'next_after_id'")
        return payload
    except HTTPException:
        raise
    except (httpx.HTTPError, ValueError, TypeError) as exc:
        raise HTTPException(502, f"Could not read the ReMarket sales feed: {exc}") from exc


def fetch_sale(client: httpx.Client, order_id: str) -> Optional[dict]:
    """A single sale by ReMarket order id, or None when ReMarket has no such order."""
    if not _ORDER_ID_RE.fullmatch(order_id or ""):
        raise HTTPException(400, "order_id must look like RM-000001")
    try:
        response = client.get(f"/api/v1/sales/{order_id}")
        if response.status_code == 404:
            return None
        payload = _as_json(response)
        return payload if isinstance(payload, dict) else None
    except HTTPException:
        raise
    except (httpx.HTTPError, ValueError, TypeError) as exc:
        raise HTTPException(502, f"Could not read ReMarket order {order_id}: {exc}") from exc


# ------------------------------------------------------------------ service signer


def _load_or_create_signing_key() -> Ed25519PrivateKey:
    """Load the integration signing key, creating it on first use.

    Mirrors anchoring._ensure_journal_key: the private half lives in its own
    file so a database compromise alone cannot forge imported custody records.
    """
    directory = os.path.dirname(_KEY_FILE)
    if directory:
        os.makedirs(directory, exist_ok=True)
    if os.path.exists(_KEY_FILE):
        with open(_KEY_FILE, "rb") as fh:
            return Ed25519PrivateKey.from_private_bytes(fh.read())
    key = Ed25519PrivateKey.generate()
    raw = key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    # Write 0600 before any bytes land on disk.
    fd = os.open(_KEY_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as fh:
        fh.write(raw)
    return key


def service_account(conn) -> tuple[int, Ed25519PrivateKey]:
    """The (user_id, signing key) pair used to sign imported sales.

    The account is looked up *by public key*, not by a fixed email, and an
    unrecognised key gets a new row rather than overwriting the old one.

    That detail matters on an ephemeral host. If the key file is lost while
    the database survives — a redeploy without a persistent disk — the next
    import generates a fresh key. Updating the existing row's public key to
    match would leave every previously imported record signed by a key the
    database no longer names, so each of those certificates would start
    reporting "ALTERED RECORD" to the public. Keeping the old signer intact
    and registering the new key as a new signer keeps history verifiable: a
    different key really is a different signer, and the chain says so.
    """
    key = _load_or_create_signing_key()
    public_hex = pubkey_to_hex(key.public_key())

    row = conn.execute(
        "SELECT id FROM users WHERE public_key = ? AND role = ?",
        (public_hex, SERVICE_ROLE),
    ).fetchone()
    if row:
        return row["id"], key

    # Email is UNIQUE, so a second signing identity needs its own address.
    taken = {
        r["email"] for r in conn.execute(
            "SELECT email FROM users WHERE email LIKE ?", ("remarket-import%",)
        ).fetchall()
    }
    email = SERVICE_EMAIL
    if email in taken:
        email = f"remarket-import+{public_hex[:12]}@craftproof.local"

    cursor = conn.execute(
        "INSERT INTO users (name, email, password_hash, role, shop_name, public_key, encrypted_privkey) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            SERVICE_NAME,
            email,
            # Not a bcrypt hash, so verify_password can never succeed: this
            # account exists to sign, not to be logged into.
            f"no-login:{secrets.token_urlsafe(32)}",
            SERVICE_ROLE,
            "ReMarket marketplace",
            public_hex,
            EXTERNAL_KEY_MARKER,
        ),
    )
    return cursor.lastrowid, key


# ------------------------------------------------------------------ import


def _normalise_title(value: str) -> str:
    """Collapse whitespace and case so 'Tea  Bowl' == 'tea bowl'."""
    return " ".join(value.split()).casefold()


def validate_sale(sale: Any) -> dict:
    """Coerce one feed entry into the fields we are willing to act on."""
    if not isinstance(sale, dict):
        raise ValueError("sale is not an object")

    order_id = sale.get("order_id")
    code = sale.get("certificate_code")
    title = sale.get("item_title")
    buyer = sale.get("buyer_name")

    if not isinstance(order_id, str) or not _ORDER_ID_RE.fullmatch(order_id):
        raise ValueError("order_id must look like RM-000001")
    if sale.get("status") != "completed":
        raise ValueError("only completed sales are imported")
    if not isinstance(code, str) or not code.strip():
        raise ValueError("certificate_code is required")
    if not isinstance(title, str) or not title.strip():
        raise ValueError("item_title is required")
    if not isinstance(buyer, str) or not buyer.strip():
        raise ValueError("buyer_name is required")
    if len(buyer.strip()) > 128:
        raise ValueError("buyer_name is too long")

    return {
        "order_id": order_id,
        "certificate_code": code.strip().upper(),
        "item_title": title.strip(),
        "buyer_name": buyer.strip(),
        "completed_at": sale.get("completed_at"),
    }


def import_sale(sale: Any) -> str:
    """Append one ReMarket sale to its certificate. Returns an outcome string.

    Outcomes: ``imported``, ``already_imported``, ``certificate_not_found``,
    ``item_title_mismatch``, ``no_custody_history``. Everything except
    ``imported``/``already_imported`` leaves the database untouched and is
    safe to retry on the next sync.
    """
    clean = validate_sale(sale)

    conn = get_db()
    try:
        # BEGIN IMMEDIATE takes the write lock up front, so two concurrent
        # syncs cannot both pass the duplicate check for the same order.
        conn.execute("BEGIN IMMEDIATE")

        if conn.execute(
            "SELECT 1 FROM remarket_imports WHERE order_id = ?", (clean["order_id"],)
        ).fetchone():
            conn.rollback()
            return "already_imported"

        piece = conn.execute(
            "SELECT id, title, current_owner_id FROM pieces WHERE certificate_code = ?",
            (clean["certificate_code"],),
        ).fetchone()
        if not piece:
            conn.rollback()
            return "certificate_not_found"

        if _normalise_title(piece["title"]) != _normalise_title(clean["item_title"]):
            conn.rollback()
            return "item_title_mismatch"

        last = conn.execute(
            "SELECT seq_index, record_hash FROM custody_records "
            "WHERE piece_id = ? ORDER BY seq_index DESC LIMIT 1",
            (piece["id"],),
        ).fetchone()
        if not last:
            conn.rollback()
            return "no_custody_history"

        # Name the holder the piece is leaving, so the note preserves what the
        # signed record itself cannot say (from_user_id is the service account).
        previous = None
        if piece["current_owner_id"]:
            holder = conn.execute(
                "SELECT name, shop_name FROM users WHERE id = ?", (piece["current_owner_id"],)
            ).fetchone()
            if holder:
                previous = holder["shop_name"] or holder["name"]
        note = (
            f"Sold on ReMarket (order {clean['order_id']})"
            + (f", handed on from {previous}" if previous else "")
        )

        signer_id, signing_key = service_account(conn)
        record = CustodyRecord(
            piece["id"],
            last["seq_index"] + 1,
            signer_id,
            None,                      # external buyer: no CraftProof account
            clean["buyer_name"],
            note,
            last["record_hash"],
        )
        record_hash = record.compute_hash()
        signature = sign(signing_key, bytes.fromhex(record_hash)).hex()

        cursor = conn.execute(
            "INSERT INTO custody_records (piece_id, seq_index, from_user_id, to_user_id, "
            "to_name, note, timestamp, prev_hash, record_hash, signature) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                record.piece_id, record.seq_index, record.from_user_id, None,
                record.to_name, record.note, record.timestamp, record.prev_hash,
                record_hash, signature,
            ),
        )
        # The buyer has no CraftProof account, so the piece has no account
        # holder any more — the certificate falls back to the recorded name.
        conn.execute("UPDATE pieces SET current_owner_id = NULL WHERE id = ?", (piece["id"],))
        conn.execute(
            "INSERT INTO remarket_imports (order_id, piece_id, record_id, certificate_code, "
            "buyer_name, item_title, completed_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                clean["order_id"], piece["id"], cursor.lastrowid, clean["certificate_code"],
                clean["buyer_name"], clean["item_title"], clean["completed_at"],
            ),
        )
        conn.commit()
        return "imported"
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ------------------------------------------------------------------ sync


def sync_sales(max_pages: int = 50) -> dict:
    """Poll ReMarket from the saved cursor and import every matching sale.

    Cursor discipline: the cursor only advances past orders that reached a
    terminal state (imported or already imported). A sale that was skipped —
    unknown certificate, mismatched title — holds the cursor at the position
    before it, so it is retried on every later sync until the certificate
    appears or a human intervenes. Nothing is ever silently dropped.
    """
    result: dict[str, Any] = {
        "imported": 0,
        "already_imported": 0,
        "skipped": [],
        "pages": 0,
        "cursor_before": read_cursor(),
    }

    after_id = result["cursor_before"]
    committed = after_id       # highest id we may safely skip past next time
    blocked = False            # a skipped sale pins the cursor behind it

    with remarket_client() as client:
        for _ in range(max_pages):
            page = fetch_sales(client, after_id)
            result["pages"] += 1
            sales = page["sales"]
            if not sales:
                break

            for sale in sales:
                order_id = sale.get("order_id") if isinstance(sale, dict) else None
                try:
                    outcome = import_sale(sale)
                except ValueError as exc:
                    outcome, reason = "invalid_sale", str(exc)
                else:
                    reason = outcome

                if outcome in ("imported", "already_imported"):
                    result[outcome] += 1
                    if not blocked:
                        committed = _order_number(order_id, committed)
                else:
                    blocked = True
                    result["skipped"].append({"order_id": order_id, "reason": reason})

            next_id = page["next_after_id"]
            if next_id <= after_id or len(sales) < _MAX_LIMIT:
                break
            after_id = next_id

    # Seal before advancing the cursor, and seal unconditionally.
    #
    # Both details matter. Checkpointing *unconditionally* repairs a previous
    # run that committed custody records but died before publishing their
    # root — by then the cursor may already sit past those sales, so a
    # condition on "did this run import anything" would leave them unsealed
    # forever. Advancing the cursor *after* the checkpoint means a failure
    # here leaves the feed position untouched, so the next sync re-reads
    # those sales (the duplicate guard makes that a no-op) and retries.
    #
    # create_checkpoint() is idempotent: unchanged records return the existing
    # checkpoint with new=False rather than publishing a redundant root.
    checkpoint = create_checkpoint()
    result["checkpoint"] = (
        {"batch_index": checkpoint["batch_index"], "new": checkpoint["new"]}
        if checkpoint else None
    )

    write_cursor(committed)
    result["cursor_after"] = committed

    conn = get_db()
    try:
        _set_state(conn, _LAST_SYNC_KEY, _now_iso())
        conn.commit()
    finally:
        conn.close()

    return result


def _order_number(order_id: Optional[str], fallback: int) -> int:
    """ReMarket order ids are RM-<zero-padded row id>; the cursor is that id."""
    if isinstance(order_id, str) and _ORDER_ID_RE.fullmatch(order_id):
        return max(fallback, int(order_id.split("-", 1)[1]))
    return fallback


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


# ------------------------------------------------------------------ reporting


def integration_status() -> dict:
    """Connection and import summary — safe to serve publicly.

    Reports whether a key is present, never any part of its value.
    """
    conn = get_db()
    try:
        imports = conn.execute("SELECT COUNT(*) AS n FROM remarket_imports").fetchone()["n"]
        latest = conn.execute(
            "SELECT order_id, certificate_code, buyer_name, item_title, imported_at "
            "FROM remarket_imports ORDER BY imported_at DESC, rowid DESC LIMIT 1"
        ).fetchone()
        last_sync = _get_state(conn, _LAST_SYNC_KEY)
        cursor = _get_state(conn, _CURSOR_KEY)
    finally:
        conn.close()

    return {
        "partner": "ReMarket",
        "configured": is_configured(),
        "api_url": api_url() or None,
        "api_key_present": bool(api_key()),
        "sync_key_present": bool(os.environ.get("CRAFTPROOF_REMARKET_SYNC_KEY", "").strip()),
        "poll_interval_seconds": sync_interval(),
        "imported_sales": imports,
        "last_sale": dict(latest) if latest else None,
        "last_sync_at": last_sync,
        "cursor": int(cursor) if cursor and cursor.isdigit() else 0,
    }


def list_imports(limit: int = 50) -> list[dict]:
    """Most recent imported sales, newest first."""
    limit = max(1, min(int(limit), 200))
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT i.order_id, i.certificate_code, i.buyer_name, i.item_title, "
            "       i.completed_at, i.imported_at, p.title AS piece_title "
            "FROM remarket_imports i JOIN pieces p ON p.id = i.piece_id "
            "ORDER BY i.imported_at DESC, i.rowid DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def import_for_piece(conn, piece_id: int) -> Optional[dict]:
    """The ReMarket sale that produced a record on this piece, if any.

    Used to annotate the public certificate so a marketplace-reported step is
    never displayed as an owner-confirmed handover.
    """
    row = conn.execute(
        "SELECT order_id, certificate_code, buyer_name, completed_at, imported_at, record_id "
        "FROM remarket_imports WHERE piece_id = ? ORDER BY rowid DESC LIMIT 1",
        (piece_id,),
    ).fetchone()
    return dict(row) if row else None


def imported_record_ids(conn, piece_id: int) -> dict[int, str]:
    """Map custody_records.id → ReMarket order id for one piece."""
    rows = conn.execute(
        "SELECT record_id, order_id FROM remarket_imports WHERE piece_id = ?", (piece_id,)
    ).fetchall()
    return {r["record_id"]: r["order_id"] for r in rows}
