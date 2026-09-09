from crypto_utils import sha256

LEAF_PREFIX = b"\x00"
NODE_PREFIX = b"\x01"

def leaf_hash(data: bytes) -> bytes:
    return sha256(LEAF_PREFIX + data)

def node_hash(left: bytes, right: bytes) -> bytes:
    return sha256(NODE_PREFIX + left + right)

class MerkleTree:
    def __init__(self, leaves_hex: list[str]):
        """leaves_hex: list of record_hash hex strings, in order."""
        if not leaves_hex:
            self.leaves = []
            self.levels = []
            return
        self.leaves = [leaf_hash(bytes.fromhex(h)) for h in leaves_hex]
        self.levels = self._build()

    def _build(self):
        levels = [self.leaves]
        current = self.leaves
        while len(current) > 1:
            nxt = []
            for i in range(0, len(current), 2):
                left = current[i]
                right = current[i+1] if i+1 < len(current) else current[i]  # duplicate last if odd
                nxt.append(node_hash(left, right))
            levels.append(nxt)
            current = nxt
        return levels

    @property
    def root(self) -> str:
        if not self.levels:
            return ""
        return self.levels[-1][0].hex()

    def get_proof(self, index: int):
        """Returns list of (sibling_hash_hex, 'L'|'R') from leaf to root."""
        proof = []
        if not self.levels:
            return proof
        idx = index
        for level in self.levels[:-1]:
            is_right = idx % 2 == 1
            sibling_idx = idx - 1 if is_right else idx + 1
            if sibling_idx >= len(level):
                sibling_idx = idx  # odd node duplicated with itself
            proof.append((level[sibling_idx].hex(), "L" if is_right else "R"))
            idx //= 2
        return proof

    @staticmethod
    def verify_proof(leaf_hex: str, proof, root_hex: str) -> bool:
        current = leaf_hash(bytes.fromhex(leaf_hex))
        for sibling_hex, side in proof:
            sibling = bytes.fromhex(sibling_hex)
            if side == "L":
                current = node_hash(sibling, current)
            else:
                current = node_hash(current, sibling)
        return current.hex() == root_hex
