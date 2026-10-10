from database import get_db
from record import CustodyRecord, GENESIS_HASH
from crypto_utils import sign, verify, pubkey_to_hex
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives import serialization
from merkle import MerkleTree
import json

def get_user_keys(user_id):
    conn = get_db()
    user = conn.execute("SELECT encrypted_privkey, public_key FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    if not user:
        return None, None
    sk = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(user["encrypted_privkey"]))
    pk = Ed25519PublicKey.from_public_bytes(bytes.fromhex(user["public_key"]))
    return sk, pk

def get_user_pubkey(user_id):
    conn = get_db()
    user = conn.execute("SELECT public_key FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    if not user:
        return None
    return Ed25519PublicKey.from_public_bytes(bytes.fromhex(user["public_key"]))


def verify_chain_detailed(piece_id):
    """Run every integrity check over a piece's custody chain.

    Returns (valid, reason, checks) where checks is a per-record list of the
    three independent tests, so the certificate page can show exactly which
    step of the history failed rather than a single global verdict.

    The genesis record of a fingerprint-committed piece was signed over an
    extra 'cm' field (see record.ALLOWED_EXTRA_FIELDS / fingerprint.py), so
    the re-hash of that record includes the commitment too.
    """
    conn = get_db()
    records = conn.execute("SELECT * FROM custody_records WHERE piece_id = ? ORDER BY seq_index ASC", (piece_id,)).fetchall()
    prow = conn.execute("SELECT fingerprint_commitment FROM pieces WHERE id = ?", (piece_id,)).fetchone()
    commitment = prow["fingerprint_commitment"] if prow else None
    conn.close()

    checks = []
    valid = True
    reason = None

    for i, r in enumerate(records):
        rec = CustodyRecord(r["piece_id"], r["seq_index"], r["from_user_id"], r["to_user_id"], r["to_name"], r["note"], r["prev_hash"], timestamp=r["timestamp"])

        # 1. Content integrity — the stored hash must match a re-hash of the row
        content_ok = rec.compute_hash() == r["record_hash"]
        if not content_ok and r["seq_index"] == 0 and commitment:
            rec.add_field("cm", commitment)
            content_ok = rec.compute_hash() == r["record_hash"]

        # 2. Chain linkage — each record must point at its predecessor
        expected_prev = records[i-1]["record_hash"] if i > 0 else GENESIS_HASH
        linkage_ok = r["prev_hash"] == expected_prev

        # 3. Signature — the outgoing custodian must have signed the record hash
        pk = get_user_pubkey(r["from_user_id"])
        signature_ok = False
        if pk is not None:
            try:
                signature_ok = verify(pk, bytes.fromhex(r["record_hash"]), bytes.fromhex(r["signature"]))
            except ValueError:
                signature_ok = False

        checks.append({
            "seq_index": r["seq_index"],
            "content_ok": content_ok,
            "linkage_ok": linkage_ok,
            "signature_ok": signature_ok,
            "ok": content_ok and linkage_ok and signature_ok,
        })

        if valid:
            if not content_ok:
                valid, reason = False, f"Record {i} content hash mismatch"
            elif not linkage_ok:
                valid, reason = False, f"Record {i} prev_hash linkage broken"
            elif not signature_ok:
                valid, reason = False, f"Record {i} signature invalid"

    return valid, reason, checks


def verify_full_chain(piece_id):
    valid, reason, _ = verify_chain_detailed(piece_id)
    return valid, reason


# ---------- Merkle checkpoints (the "public ledger") ----------

def _all_record_hashes(conn):
    rows = conn.execute("SELECT record_hash FROM custody_records ORDER BY id ASC").fetchall()
    return [r["record_hash"] for r in rows]


def create_checkpoint():
    """Publish a new checkpoint: a Merkle root over every custody record so far.

    Each checkpoint is an independent snapshot, so a record included in
    checkpoint N stays provable against that root even as new records arrive.
    """
    conn = get_db()
    try:
        leaves = _all_record_hashes(conn)
        if not leaves:
            return None

        latest = conn.execute("SELECT root_hash FROM merkle_batches ORDER BY batch_index DESC LIMIT 1").fetchone()
        tree = MerkleTree(leaves)
        if latest and latest["root_hash"] == tree.root:
            # Nothing new has been recorded since the last checkpoint.
            existing = conn.execute(
                "SELECT * FROM merkle_batches ORDER BY batch_index DESC LIMIT 1"
            ).fetchone()
            return {"batch_index": existing["batch_index"], "root_hash": existing["root_hash"],
                    "record_count": len(leaves), "created_at": existing["created_at"], "new": False}

        next_index = conn.execute("SELECT COALESCE(MAX(batch_index), 0) + 1 AS n FROM merkle_batches").fetchone()["n"]
        c = conn.cursor()
        c.execute(
            "INSERT INTO merkle_batches (batch_index, root_hash, record_ids) VALUES (?, ?, ?)",
            (next_index, tree.root, json.dumps(leaves))
        )
        conn.commit()
        row = conn.execute("SELECT created_at FROM merkle_batches WHERE batch_index = ?", (next_index,)).fetchone()
        return {"batch_index": next_index, "root_hash": tree.root,
                "record_count": len(leaves), "created_at": row["created_at"], "new": True}
    finally:
        conn.close()


def list_checkpoints():
    conn = get_db()
    try:
        rows = conn.execute("SELECT * FROM merkle_batches ORDER BY batch_index DESC").fetchall()
        out = []
        for r in rows:
            try:
                count = len(json.loads(r["record_ids"]))
            except (ValueError, TypeError):
                count = 0
            out.append({
                "batch_index": r["batch_index"],
                "root_hash": r["root_hash"],
                "record_count": count,
                "created_at": r["created_at"],
            })
        return out
    finally:
        conn.close()


def get_inclusion_proof(record_hash):
    """Find the earliest checkpoint containing this record and prove inclusion.

    Returns None when the record has not been checkpointed yet — that is a
    normal state (a piece registered after the last checkpoint), not tampering.
    """
    conn = get_db()
    try:
        rows = conn.execute("SELECT * FROM merkle_batches ORDER BY batch_index ASC").fetchall()
    finally:
        conn.close()

    for r in rows:
        try:
            leaves = json.loads(r["record_ids"])
        except (ValueError, TypeError):
            continue
        if record_hash not in leaves:
            continue
        index = leaves.index(record_hash)
        tree = MerkleTree(leaves)
        proof = tree.get_proof(index)
        return {
            "batch_index": r["batch_index"],
            "root_hash": r["root_hash"],
            "leaf_index": index,
            "proof": [{"hash": h, "side": side} for h, side in proof],
            "included": MerkleTree.verify_proof(record_hash, proof, r["root_hash"]),
            "created_at": r["created_at"],
        }
    return None


def rebuild_merkle():
    """Backwards-compatible alias kept for the earlier CLI scripts."""
    return create_checkpoint()
