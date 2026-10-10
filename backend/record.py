from datetime import datetime, timezone
from typing import Any, Dict, Optional
from crypto_utils import sha256, canonical_json

GENESIS_HASH = sha256(b"GENESIS").hex()

# Fields allowed as protocol extensions (e.g. 'cm' fingerprint commitment).
# Each must be explicitly listed here or add_field raises, so the signed
# record schema stays auditable.
ALLOWED_EXTRA_FIELDS = ('cm',)


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
        self.extra: Dict[str, Any] = {}

    def add_field(self, name: str, value: Any) -> "CustodyRecord":
        """Attach a protocol-extension field (included in the signed hash).

        Currently: 'cm' = SHA-256 hex of the enrolled physical-fingerprint
        template (see fingerprint.py). The value becomes part of the hashed
        canonical JSON, so altering the commitment breaks the record hash —
        exactly like any other signed field.
        """
        if name not in ALLOWED_EXTRA_FIELDS:
            raise ValueError(f"unknown extra field {name!r} (allowed: {ALLOWED_EXTRA_FIELDS})")
        self.extra[name] = value
        return self

    def _fields(self):
        fields = {
            "piece_id": self.piece_id,
            "seq_index": self.seq_index,
            "from_user_id": self.from_user_id,
            "to_user_id": self.to_user_id,
            "to_name": self.to_name,
            "note": self.note,
            "timestamp": self.timestamp,
            "prev_hash": self.prev_hash,
        }
        fields.update(self.extra)
        return fields

    def compute_hash(self):
        return sha256(canonical_json(self._fields())).hex()
