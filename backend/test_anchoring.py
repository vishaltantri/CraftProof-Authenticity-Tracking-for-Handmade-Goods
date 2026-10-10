"""Tests for the external anchoring module (W6).

Covers: journal receipt verification (valid, tampered, missing-sig),
latest-receipt lookup, and journal persistence across restarts. The freetsa
network backend is stubbed — the unit suite must run air-gapped.
"""

import json
import os
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix="craftproof-anchor-test-")
os.environ["CRAFTPROOF_DB"] = os.path.join(_TMP, "t.db")
os.environ["CRAFTPROOF_ANCHOR_KEY"] = os.path.join(_TMP, "anchor", "key.pem")
os.environ["CRAFTPROOF_ANCHOR_JOURNAL"] = os.path.join(_TMP, "anchor", "journal.jsonl")
os.environ["CRAFTPROOF_ANCHOR_BACKEND"] = "local"

import anchoring


ROOT1 = "a" * 64
ROOT2 = "b" * 64


def test_anchor_creates_valid_receipt():
    receipt = anchoring.anchor_root(ROOT1, batch_index=1, record_count=12)
    assert receipt["root_hash"] == ROOT1
    assert receipt["backend"] == "local"
    assert anchoring.verify_receipt(receipt), "fresh receipt must verify"


def test_tampered_root_fails_verification():
    receipt = anchoring.anchor_root(ROOT2, batch_index=2, record_count=5)
    tampered = dict(receipt)
    tampered["root_hash"] = "c" * 64   # attacker rewrites the anchored root
    assert not anchoring.verify_receipt(tampered), "tampered root must fail"


def test_tampered_batch_index_fails_verification():
    receipt = anchoring.anchor_root(ROOT2, batch_index=3, record_count=5)
    tampered = dict(receipt)
    tampered["batch_index"] = 99
    assert not anchoring.verify_receipt(tampered)


def test_missing_signature_fails():
    receipt = anchoring.anchor_root(ROOT2, batch_index=4, record_count=5)
    stripped = {k: v for k, v in receipt.items() if k != "sig"}
    assert not anchoring.verify_receipt(stripped)


def test_journal_persistence_and_lookup():
    anchoring.anchor_root(ROOT1, batch_index=10, record_count=3)
    receipt = anchoring.latest_receipt_for(ROOT1)
    assert receipt and receipt["root_hash"] == ROOT1
    # journal survives "restart" (fresh module-level read from disk)
    again = anchoring.latest_receipt_for(ROOT1)
    assert again["batch_index"] == receipt["batch_index"]


def test_no_receipt_for_unknown_root():
    assert anchoring.latest_receipt_for("f" * 64) is None


def test_freetsa_inline_verification():
    receipt = {
        "backend": "freetsa",
        "root_hash": ROOT1,
        "token_b64": anchoring.base64.b64encode(b"x" * 10 + bytes.fromhex(ROOT1) + b"y" * 3).decode(),
    }
    assert anchoring.verify_receipt(receipt), "token containing the root must pass inline check"


def test_freetsa_inline_verification_rejects_wrong_root():
    receipt = {
        "backend": "freetsa",
        "root_hash": ROOT1,
        "token_b64": anchoring.base64.b64encode(b"x" * 10 + bytes.fromhex("d" * 64)).decode(),
    }
    assert not anchoring.verify_receipt(receipt)


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
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
