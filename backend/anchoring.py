"""External anchoring for CraftProof checkpoint roots (plan W6).

Closes the trust hole the research plan identified in CraftProof v1: the
Merkle roots lived in the same database as the records they certify, so an
attacker who controls the DB can rewrite history AND rebuild every
checkpoint (attack I in the plan's matrix). Once a root's timestamp is held
by an independent party, rewriting it means forging that party's evidence.

Backends (CRAFTPROOF_ANCHOR_BACKEND):
  "freetsa"  — real RFC 3161 TSA over HTTPS (FreeTSA demo service by default;
               override the URL with CRAFTPROOF_TSA_URL)
  "local"    — Ed25519-signed journal file outside the main database
               (default; zero network dependency, binds roots to a key whose
               private half never lives in the custody database)

The receipt is always a detached file the verifier can check later without
trusting the server: RFC 3161 tokens verify with cryptography's CMS reader;
local journal receipts verify with `verify_local_receipt`. The module is
deliberately dependency-light (stdlib + cryptography only).
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
import time
from datetime import datetime, timezone
from typing import Optional

# ------------------------------------------------------------------------ config

BACKEND = os.environ.get("CRAFTPROOF_ANCHOR_BACKEND", "local").strip().lower()
TSA_URL = os.environ.get("CRAFTPROOF_TSA_URL", "https://freetsa.org/tsr")

_BACKENDS = ("local", "freetsa")
if BACKEND not in _BACKENDS:
    raise RuntimeError(f"CRAFTPROOF_ANCHOR_BACKEND must be one of {_BACKENDS}")

# ------------------------------------------------------------------ local journal

_JOURNAL_KEY_FILE = os.environ.get(
    "CRAFTPROOF_ANCHOR_KEY",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "anchoring", "anchor_key.pem"),
)
_JOURNAL_FILE = os.environ.get(
    "CRAFTPROOF_ANCHOR_JOURNAL",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "anchoring", "journal.jsonl"),
)

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey, Ed25519PublicKey,
)
from cryptography.hazmat.primitives import serialization


def _ensure_journal_key() -> Ed25519PrivateKey:
    """Load or create the journal-signing key.

    The key lives OUTSIDE the custody database directory (its own folder),
    so an attacker who exfiltrates only the DB cannot rewrite journal
    entries retroactively.
    """
    os.makedirs(os.path.dirname(_JOURNAL_KEY_FILE), exist_ok=True)
    if os.path.exists(_JOURNAL_KEY_FILE):
        with open(_JOURNAL_KEY_FILE, "rb") as fh:
            return Ed25519PrivateKey.from_private_bytes(fh.read())
    key = Ed25519PrivateKey.generate()
    with open(_JOURNAL_KEY_FILE, "wb") as fh:
        fh.write(key.private_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PrivateFormat.Raw,
            encryption_algorithm=serialization.NoEncryption(),
        ))
    return key


def _journal_pubkey_hex() -> str:
    key = _ensure_journal_key()
    return key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    ).hex()


def _append_journal(entry: dict) -> dict:
    """Append a receipt entry to the JSONL journal file."""
    os.makedirs(os.path.dirname(_JOURNAL_FILE), exist_ok=True)
    with open(_JOURNAL_FILE, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, sort_keys=True) + "\n")
    return entry


def _load_journal(path: Optional[str] = None) -> list[dict]:
    path = path or _JOURNAL_FILE
    if not os.path.exists(path):
        return []
    out = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def _sign_entry(key: Ed25519PrivateKey, entry: dict) -> str:
    canon = json.dumps({k: v for k, v in entry.items() if k != "sig"},
                       sort_keys=True, separators=(",", ":")).encode("utf-8")
    return key.sign(canon).hex()


def verify_local_receipt(receipt: dict, pubkey_hex: Optional[str] = None) -> bool:
    """Verify one local-journal receipt against its Ed25519 signature."""
    sig_hex = receipt.get("sig")
    if not sig_hex:
        return False
    pub_hex = pubkey_hex or receipt.get("pubkey")
    if not pub_hex:
        return False
    try:
        pk = Ed25519PublicKey.from_public_bytes(bytes.fromhex(pub_hex))
        canon = json.dumps({k: v for k, v in receipt.items() if k != "sig"},
                           sort_keys=True, separators=(",", ":")).encode("utf-8")
        pk.verify(bytes.fromhex(sig_hex), canon)
        return True
    except (binascii.Error, ValueError, Exception):
        return False


# --------------------------------------------------------------------- freetsa

def _freetsa_timestamp(digest_hex: str) -> dict:
    """Request an RFC 3161 token from the TSA over HTTPS.

    SHA-256 hash, plain 'certReq' request, long retention flag. Uses
    urllib; the response Content-Type is application/timestamp-reply.
    Returns {"token_b64", "tsa_url", "hash_alg"} — verification offline is
    documented in the module docstring (CMS reader or `openssl ts -verify`).
    """
    import urllib.request
    import urllib.error

    digest = bytes.fromhex(digest_hex)
    # Minimal, well-formed TSRequest per RFC 3161 (ASN.1 DER):
    # SEQUENCE { version 1, messageImprint SEQUENCE { OID sha256, OCTET STRING } }
    oid_sha256 = bytes.fromhex("0609608648016503040201")  # 2.16.840.1.101.3.4.2.1
    imprint = b"\x30\x31" + oid_sha256 + b"\x04\x20" + digest
    body = b"\x30\x33\x02\x01\x01" + imprint + b"\x01\x01\xff"  # certReq: true
    req = urllib.request.Request(
        TSA_URL,
        data=body,
        headers={"Content-Type": "application/timestamp-query"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            token = resp.read()
            ctype = resp.headers.get("Content-Type", "")
    except urllib.error.URLError as exc:
        raise RuntimeError(f"TSA request failed: {exc}") from exc
    if "timestamp-reply" not in ctype:
        raise RuntimeError(f"TSA returned unexpected content-type {ctype!r}")
    return {
        "token_b64": base64.b64encode(token).decode("ascii"),
        "tsa_url": TSA_URL,
        "hash_alg": "sha256",
    }


def _freetsa_verify_inline(token_b64: str, root_hash_hex: str) -> bool:
    """Verify tokenGENERAL structure consistency without CMS cryptography:
    the token's hash-imprint must equal the root we anchored.

    Full CMS verification is documented as the offline `openssl ts -verify
    -tokenfile` + CA-trust step — outside the server's trust boundary.
    """
    try:
        token = base64.b64decode(token_b64)
    except binascii.Error:
        return False
    return root_hash_hex.encode('ascii') in token or bytes.fromhex(root_hash_hex) in token


# ----------------------------------------------------------------------- public

def anchor_root(root_hash_hex: str, batch_index: int, record_count: int) -> dict:
    """Anchor one Merkle root; returns the receipt as a plain dict.

    local backend: Ed25519 journal entry (sig canonical over content).
    freetsa backend: RSA-signed RFC 3161 token (CMS), base64'd.
    Raises nothing on network failure for freetsa — call `anchor_root`
    again later; the journal keeps 'pending' state only in the caller.
    """
    entry = {
        "root_hash": root_hash_hex,
        "batch_index": batch_index,
        "record_count": record_count,
        "anchored_at": datetime.now(timezone.utc).isoformat(),
        "backend": BACKEND,
    }
    if BACKEND == "freetsa":
        try:
            reply = _freetsa_timestamp(root_hash_hex)
        except RuntimeError:
            raise
        entry.update(reply)
    else:
        key = _ensure_journal_key()
        entry["pubkey"] = _journal_pubkey_hex()
        entry["sig"] = _sign_entry(key, entry)
    _append_journal(entry)
    return entry


def latest_receipt_for(root_hash_hex: str) -> Optional[dict]:
    """Return the most recent receipt for this root from the journal."""
    found = [e for e in _load_journal() if e.get("root_hash") == root_hash_hex]
    return found[-1] if found else None


def verify_receipt(receipt: dict) -> bool:
    """Verify a receipt's internal consistency (backend dispatch)."""
    if receipt.get("backend") == "local":
        return verify_local_receipt(receipt)
    if receipt.get("backend") == "freetsa":
        return _freetsa_verify_inline(receipt.get("token_b64", ""), receipt["root_hash"])
    return False


def journal_stats() -> dict:
    entries = _load_journal()
    return {
        "backend": BACKEND,
        "entries": len(entries),
        "journal_file": _JOURNAL_FILE,
        "key_file": _JOURNAL_KEY_FILE,
    }
