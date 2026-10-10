#!/usr/bin/env python3
"""Tests for the key envelope (W1 security work).

Covers the AES-256-GCM envelope round-trip, wrong-password rejection, the
fixed positional v1 (legacy) parser, and the parse-safe v2 writer format.
"""

import base64
import os
import sys

from keystore import (AESGCM, _derive, decrypt_private_key, encrypt_private_key,
                      is_envelope, InvalidTag)

SEED = os.urandom(32)


def test_v2_roundtrip():
    env = encrypt_private_key(SEED, "correct horse battery staple")
    assert env.startswith("ckd:v2:"), env
    # urlsafe alphabet inside fields: no '+' or '/' — so '=' is unambiguous
    field = env.split(":")[3]
    assert "+" not in field and "/" not in field, field
    assert decrypt_private_key(env, "correct horse battery staple") == SEED


def test_wrong_password_rejected():
    env = encrypt_private_key(SEED, "right password")
    try:
        decrypt_private_key(env, "wrong password")
        raise AssertionError("wrong password must not decrypt")
    except ValueError:
        pass


def test_garbage_and_empty_rejected():
    for bad in ("", "garbage", "ckd:v2:pbkdf2:short", "ckd:v2:md5:aaa=bbb=ccc"):
        try:
            decrypt_private_key(bad, "x")
            raise AssertionError(f"accepted malformed envelope {bad!r}")
        except ValueError:
            pass


def test_v1_legacy_envelope_still_decrypts():
    """Rebuild an envelope exactly the way the pre-v2 writer did (padded
    standard base64, '=' separators) and check the positional parser."""
    salt, nonce = os.urandom(16), os.urandom(12)
    ct = AESGCM(_derive("legacy pw", salt)).encrypt(nonce, SEED, None)
    leg = ("ckd:v1:pbkdf2:"
           f"{base64.b64encode(salt).decode()}={base64.b64encode(nonce).decode()}={base64.b64encode(ct).decode()}")
    assert is_envelope(leg)
    assert decrypt_private_key(leg, "legacy pw") == SEED
    try:
        decrypt_private_key(leg, "wrong")
        raise AssertionError("v1 wrong password must not decrypt")
    except ValueError:
        pass


def test_seed_size_enforced():
    try:
        encrypt_private_key(b"short", "pw")
        raise AssertionError("non-32-byte seed must be rejected")
    except ValueError:
        pass


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    failed = []
    for name, fn in tests:
        try:
            fn()
            print(f"  PASS  {name}")
        except Exception as e:  # noqa: BLE001
            failed.append(name)
            print(f"  FAIL  {name}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - len(failed)}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
