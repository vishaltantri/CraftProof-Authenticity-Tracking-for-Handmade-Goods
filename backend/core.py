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

def verify_full_chain(piece_id):
    conn = get_db()
    records = conn.execute("SELECT * FROM custody_records WHERE piece_id = ? ORDER BY seq_index ASC", (piece_id,)).fetchall()
    conn.close()
    
    for i, r in enumerate(records):
        rec = CustodyRecord(r["piece_id"], r["seq_index"], r["from_user_id"], r["to_user_id"], r["to_name"], r["note"], r["prev_hash"], timestamp=r["timestamp"])
        
        # 1. Content integrity
        if rec.compute_hash() != r["record_hash"]:
            return False, f"Record {i} content hash mismatch"
        
        # 2. Chain linkage
        expected_prev = records[i-1]["record_hash"] if i > 0 else GENESIS_HASH
        if r["prev_hash"] != expected_prev:
            return False, f"Record {i} prev_hash linkage broken"
            
        # 3. Signature
        pk = get_user_pubkey(r["from_user_id"])
        if not verify(pk, bytes.fromhex(r["record_hash"]), bytes.fromhex(r["signature"])):
            return False, f"Record {i} signature invalid"
            
    return True, None

def rebuild_merkle():
    conn = get_db()
    # In a real app we'd batch, here we just tree all records
    records = conn.execute("SELECT record_hash FROM custody_records ORDER BY id ASC").fetchall()
    leaves = [r["record_hash"] for r in records]
    tree = MerkleTree(leaves)
    
    conn.execute("INSERT INTO merkle_batches (batch_index, root_hash, record_ids) VALUES (?, ?, ?)", 
                 (1, tree.root, json.dumps([r["record_hash"] for r in records])))
    conn.commit()
    conn.close()
    return tree
