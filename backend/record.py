from datetime import datetime, timezone
from crypto_utils import sha256, canonical_json

GENESIS_HASH = sha256(b"GENESIS").hex()

class CustodyRecord:
    def __init__(self, piece_id, seq_index, from_user_id, to_user_id, to_name, note, prev_hash, timestamp=None):
        self.piece_id = piece_id
        self.seq_index = seq_index
        self.from_user_id = from_user_id
        self.to_user_id = to_user_id
        self.to_name = to_name
        self.note = note
        # Always use ISO-format string timestamps for deterministic hashing
        if timestamp is None:
            self.timestamp = datetime.now(timezone.utc).isoformat()
        else:
            self.timestamp = str(timestamp)
        self.prev_hash = prev_hash

    def _fields(self):
        return {
            "piece_id": self.piece_id,
            "seq_index": self.seq_index,
            "from_user_id": self.from_user_id,
            "to_user_id": self.to_user_id,
            "to_name": self.to_name,
            "note": self.note,
            "timestamp": self.timestamp,
            "prev_hash": self.prev_hash,
        }

    def compute_hash(self):
        return sha256(canonical_json(self._fields())).hex()
