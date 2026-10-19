"""Import completed ReMarket sales using its server-to-server sales API."""

import hmac
import os
import re
import secrets

import httpx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import HTTPException

from crypto_utils import generate_keypair, pubkey_to_hex, sign
from core import create_checkpoint
from database import get_db
from record import CustodyRecord


def require_sync_key(supplied):
    expected = os.environ.get("CRAFTPROOF_REMARKET_SYNC_KEY", "")
    if not expected:
        raise HTTPException(503, "ReMarket sync key is not configured")
    if not supplied or not hmac.compare_digest(supplied, expected):
        raise HTTPException(401, "Valid integration key required")


def remarket_client():
    base_url = os.environ.get("REMARKET_API_URL", "").rstrip("/")
    api_key = os.environ.get("REMARKET_SALE_API_KEY", "")
    if not base_url or not api_key:
        raise HTTPException(503, "ReMarket API URL and sale API key must be configured")
    return httpx.Client(
        base_url=base_url,
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=10,
        follow_redirects=False,
    )


def fetch_sales(client, after_id):
    try:
        response = client.get("/api/v1/sales", params={"after_id": after_id, "limit": 100})
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload.get("sales"), list) or not isinstance(payload.get("next_after_id"), int):
            raise ValueError("Invalid sales response")
        return payload
    except (httpx.HTTPError, ValueError, TypeError, AttributeError) as exc:
        raise HTTPException(502, "Could not read ReMarket sales API") from exc


def _integration_signer(conn):
    """Use a distinct service signature; never impersonate the previous owner."""
    user = conn.execute(
        "SELECT id, encrypted_privkey FROM users WHERE email = ?",
        ("remarket-import@craftproof.local",),
    ).fetchone()
    if user:
        return user["id"], Ed25519PrivateKey.from_private_bytes(bytes.fromhex(user["encrypted_privkey"]))

    private_key, public_key = generate_keypair()
    private_hex = private_key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    ).hex()
    cursor = conn.execute(
        """INSERT INTO users (name, email, password_hash, role, public_key, encrypted_privkey)
           VALUES (?, ?, ?, ?, ?, ?)""",
        ("ReMarket import", "remarket-import@craftproof.local", secrets.token_urlsafe(32),
         "integration", pubkey_to_hex(public_key), private_hex),
    )
    return cursor.lastrowid, private_key


def import_sale(sale):
    """Append one signed, idempotent custody event identified by ReMarket order ID."""
    if not isinstance(sale, dict):
        raise ValueError("Invalid sale")
    order_id = sale.get("order_id")
    code = sale.get("certificate_code")
    item_title = sale.get("item_title")
    name = sale.get("buyer_name")
    if (not isinstance(order_id, str) or not re.fullmatch(r"RM-\d+", order_id)
            or sale.get("status") != "completed"
            or not isinstance(code, str) or not code.strip()
            or not isinstance(item_title, str) or not item_title.strip()
            or not isinstance(name, str) or not name.strip() or len(name.strip()) > 128):
        raise ValueError("Sale requires a completed order, certificate code, item title, and buyer name")

    conn = get_db()
    try:
        conn.execute("BEGIN IMMEDIATE")
        if conn.execute("SELECT 1 FROM remarket_imports WHERE order_id = ?", (order_id,)).fetchone():
            return "already_imported"

        piece = conn.execute(
            "SELECT id, title FROM pieces WHERE certificate_code = ?", (code.strip().upper(),)
        ).fetchone()
        if not piece:
            return "certificate_not_found"
        if " ".join(piece["title"].split()).casefold() != " ".join(item_title.split()).casefold():
            return "item_title_mismatch"

        last = conn.execute(
            "SELECT seq_index, record_hash FROM custody_records WHERE piece_id = ? ORDER BY seq_index DESC LIMIT 1",
            (piece["id"],),
        ).fetchone()
        if not last:
            raise ValueError("Certificate has no custody history")

        signer_id, private_key = _integration_signer(conn)
        note = f"Imported ReMarket sale {order_id}"
        record = CustodyRecord(piece["id"], last["seq_index"] + 1,
                               signer_id, None, name.strip(), note, last["record_hash"])
        record_hash = record.compute_hash()
        signature = sign(private_key, bytes.fromhex(record_hash)).hex()
        cursor = conn.execute(
            """INSERT INTO custody_records
               (piece_id, seq_index, from_user_id, to_user_id, to_name, note,
                timestamp, prev_hash, record_hash, signature)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (record.piece_id, record.seq_index, record.from_user_id, None,
             record.to_name, note, record.timestamp, record.prev_hash, record_hash, signature),
        )
        conn.execute("UPDATE pieces SET current_owner_id = NULL WHERE id = ?", (piece["id"],))
        conn.execute(
            "INSERT INTO remarket_imports (order_id, piece_id, record_id) VALUES (?, ?, ?)",
            (order_id, piece["id"], cursor.lastrowid),
        )
        conn.commit()
        return "imported"
    finally:
        conn.close()


def sync_sales():
    result = {"imported": 0, "already_imported": 0, "skipped": []}
    after_id = 0
    with remarket_client() as client:
        while True:
            page = fetch_sales(client, after_id)
            for sale in page["sales"]:
                try:
                    status = import_sale(sale)
                except ValueError:
                    status = "invalid_sale"
                if status in ("imported", "already_imported"):
                    result[status] += 1
                else:
                    result["skipped"].append({"order_id": sale.get("order_id") if isinstance(sale, dict) else None, "reason": status})
            next_id = page["next_after_id"]
            if not page["sales"] or next_id <= after_id or len(page["sales"]) < 100:
                break
            after_id = next_id
    # Re-check existing imports too: a previous run might have committed the
    # custody record but stopped before publishing its Merkle checkpoint.
    if result["imported"] or result["already_imported"]:
        create_checkpoint()
    return result
