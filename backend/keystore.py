"""Encrypted at-rest storage for Ed25519 signing keys.

Every economically valuable CraftProof signing key is encrypted inside an
AEAD envelope (AES-256-GCM) whose key is derived from the owner's password:
Argon2id when argon2-cffi is installed, PBKDF2-HMAC-SHA-256 (1.2M iterations)
otherwise. Losing the password makes the signature key unrecoverable --
deliberately: with a centralized keystore, the always-available operator
override path is the one CraftProof treats as the insider threat (threat Cs1).

Stored value format ('ckd:' prefix, self-describing):
    ckd:v1:argon2id:{b64 salt}={b64 nonce}={b64 ciphertext}
    ckd:v1:pbkdf2:{b64 salt}={b64 nonce}={b64 ciphertext}

Keystore: with a password held only in memory and never written to disk, the
keystore cache maps user id -> 32-byte seed, with an expiry. A restart
rehooks the cache lazily on the next signing action; startup failure of the
args module fails closed. The admin re-seal reflects the "encrypt to value"
philosophy: no way to produce plaintext from the database alone.
"""

from __future__ import annotations

import base64
import binascii
import os
import time

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.exceptions import InvalidTag

try:
    from argon2.low_level import hash_secret_raw, Type  # RFC 9106
    _HAS_ARGON2 = True
except Exception:  # ImportError
    _HAS_ARGON2 = False

_KDF_KEY_LEN = 32   # AES-256
_SALT_LEN = 16
_NONCE_LEN = 12     # AES-GCM standard
_ARGON2_TIME = 4
_ARGON2_MEM = 262144   # 256 MiB
_ARGON2_PAR = 2
_PBKDF2_ITERS = 1_200_000
_HASHER = 'argon2id' if _HAS_ARGON2 else 'pbkdf2'


# ---------------------------------------------------------------- primitives

def _derive(password: str, salt: bytes) -> bytes:
    if _HAS_ARGON2:
        return hash_secret_raw(
            secret=password.encode('utf-8'),
            salt=salt,
            time_cost=_ARGON2_TIME,
            memory_cost=_ARGON2_MEM,
            parallelism=_ARGON2_PAR,
            hash_len=_KDF_KEY_LEN,
            type=Type.ID,
        )
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=_KDF_KEY_LEN,
                     salt=salt, iterations=_PBKDF2_ITERS)
    return kdf.derive(password.encode('utf-8'))


def _b64e(b: bytes) -> str:
    """Base64 WITHOUT '=' padding: '=' is the envelope's field separator, so
    padded standard base64 inside a field makes the split ambiguous (the
    padding of one field looks like a separator). Unpadded base64 round-trips
    once padding is restored, which _b64d does."""
    return base64.b64encode(b).decode('ascii').rstrip('=')


def _b64u(b: bytes) -> str:
    """urlsafe base64 without '=' padding — parse-safe against the '=' separator."""
    return base64.urlsafe_b64encode(b).decode('ascii').rstrip('=')


def _b64u_decode(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + '=' * (-len(s) % 4))


def _b64d(s: str) -> bytes:
    """Decode standard base64 that may have had its '=' padding stripped."""
    return base64.b64decode(s + '=' * (-len(s) % 4), validate=True)


# ------------------------------------------------------------ envelope API

def encrypt_private_key(seed: bytes, password: str) -> str:
    """Encrypt a 32-byte Ed25519 seed under password; return the envelope string.

    Format v2:   ckd:v2:{hasher}:{salt_b64u}={nonce_b64u}={ct_b64u}
    (urlsafe base64, padding stripped — '-'/'_' cannot collide with the '='
    field separators, so the payload is split-safe without stripping math.)

    v1 (padded standard base64 with '=' separators) is accepted by the
    reader for historical rows; see decrypt_private_key.
    """
    if len(seed) != 32:
        raise ValueError('seed must be 32 bytes')
    if not password:
        raise ValueError('password must not be empty')
    salt = os.urandom(_SALT_LEN)
    nonce = os.urandom(_NONCE_LEN)
    ct = AESGCM(_derive(password, salt)).encrypt(nonce, seed, None)
    return f"ckd:v2:{_HASHER}:{_b64u(salt)}={_b64u(nonce)}={_b64u(ct)}"


def decrypt_private_key(envelope: str, password: str) -> bytes:
    """Decrypt an envelope back to the 32-byte seed.

    Reads both v2 (current, urlsafe unpadded) and v1 envelopes (the original
    padded-standard-base64 format — parseable when the '=' split yields
    exactly three unambiguous fields; we suffix-strip defensively). Raises
    ValueError on any malformed input or wrong password.
    """
    parts = envelope.split(':')
    version = parts[1] if len(parts) >= 3 and parts[0] == 'ckd' else None
    if version not in ('v1', 'v2') or parts[2] not in ('argon2id', 'pbkdf2'):
        raise ValueError('not a valid envelope')
    try:
        field = parts[3]
        if version == 'v2':
            sep = field.split('=')
            if len(sep) != 3:
                raise ValueError('invalid envelope or wrong password')
            salt_s, nonce_s, ct_s = sep
            salt, nonce, ct = _b64u_decode(salt_s), _b64u_decode(nonce_s), _b64u_decode(ct_s)
        else:
            # v1: standard base64 WITH '=' padding inside each field, '=' also
            # being the separator — ambiguous by construction. Field lengths
            # are canonical, so parse positionally.
            salt, nonce, ct = _v1_parse(field)
        seed = AESGCM(_derive(password, salt)).decrypt(nonce, ct, None)
    except (binascii.Error, ValueError, KeyError, InvalidTag) as exc:
        raise ValueError('invalid envelope or wrong password') from exc
    if len(seed) != 32:
        raise ValueError('invalid envelope or wrong password')
    return seed


# Canonical v1 field lengths (standard base64 WITH padding):
_V1_LENS = (24, 16, 64)   # salt(16B→24ch), nonce(12B→16ch), ct(48B = 32B seed
                          # + 16B GCM tag → 64ch, unpadded)

def _v1_parse(field: str) -> tuple[bytes, bytes, bytes]:
    """Positional parser for the historical (v1) field layout.

    The v1 writer emitted 16B salt / 12B nonce / 44B ciphertext,
    standard-base64 encoded WITH '=' padding, joined by '=' separators.
    Padding is deterministic (24 / 16 / 60 chars), so the separators sit at
    fixed offsets 24 and 41 — parse by position instead of by splitting.
    """
    if len(field) != 24 + 1 + 16 + 1 + 64:
        raise ValueError('not a valid envelope')
    if field[24] != '=' or field[41] != '=':
        raise ValueError('not a valid envelope')
    salt = _b64d(field[0:24])
    nonce = _b64d(field[25:41])
    ct = _b64d(field[42:])
    return salt, nonce, ct


def is_envelope(value: str | None) -> bool:
    """True iff value parses as an encrypted-key envelope (v1 or v2)."""
    if not value:
        return False
    p = value.split(':')
    return (len(p) >= 3 and p[0] == 'ckd' and p[1] in ('v1', 'v2')
            and p[2] in ('argon2id', 'pbkdf2'))


# -------------------------------------------------------------- keystore cache

class KeyStore:
    """In-memory cache of unlocked seeds, keyed by user id.

    A seed in memory lets the server sign without repeated KDF passes. The
    cache is volatile: restart kills it and callers re-unlock on demand, so
    the database file (or a stolen dump) never yields keys on its own.
    """

    def __init__(self, ttl: int = 900) -> None:
        self._seeds: dict[int, bytes] = {}
        self._expires: dict[int, float] = {}
        self._ttl = ttl

    def remember(self, user_id: int, seed: bytes) -> None:
        self._seeds[user_id] = seed
        self._expires[user_id] = time.time() + self._ttl

    def get(self, user_id: int) -> bytes | None:
        exp = self._expires.get(user_id)
        if exp is None or exp < time.time():
            self._seeds.pop(user_id, None)
            self._expires.pop(user_id, None)
            return None
        return self._seeds.get(user_id)

    def forget(self, user_id: int) -> None:
        self._seeds.pop(user_id, None)
        self._expires.pop(user_id, None)
