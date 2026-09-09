import hashlib
import json
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey, Ed25519PublicKey
)
from cryptography.hazmat.primitives import serialization
from cryptography.exceptions import InvalidSignature


def sha256(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_json(obj: dict) -> bytes:
    """Deterministic serialization so the same record always hashes the same way."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")


def generate_keypair():
    sk = Ed25519PrivateKey.generate()
    pk = sk.public_key()
    return sk, pk


def sign(sk: Ed25519PrivateKey, message: bytes) -> bytes:
    return sk.sign(message)


def verify(pk: Ed25519PublicKey, message: bytes, signature: bytes) -> bool:
    try:
        pk.verify(signature, message)
        return True
    except InvalidSignature:
        return False


def pubkey_to_hex(pk: Ed25519PublicKey) -> str:
    raw = pk.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return raw.hex()
