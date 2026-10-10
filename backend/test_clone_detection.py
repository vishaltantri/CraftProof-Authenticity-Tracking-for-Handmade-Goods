"""Unit tests for clone / tag-substitution detection (W5).

Builds real custody chains in a throwaway database, then replays the
physical attack families from the research plan (attacks F/G/H):
  * one genuine tag mounted on K different counterfeit objects
  * genuine re-scan of the SAME object (must never flag)
  * lone mis-photograph (must not confirm a flag on its own)
"""

import os
import sys
import tempfile
import unittest.mock

_TMP_DB = os.path.join(tempfile.mkdtemp(prefix="craftproof-clone-test-"), "test.db")
os.environ["CRAFTPROOF_DB"] = _TMP_DB
os.environ["CRAFTPROOF_TEMPLATES_DIR"] = os.path.join(
    tempfile.mkdtemp(prefix="craftproof-clone-test-templates-"), "templates")

import numpy as np
from PIL import Image

from database import get_db, init_db
from crypto_utils import generate_keypair
from cryptography.hazmat.primitives import serialization
import fingerprint as fp
from clone_detection import record_event, detect_clone

init_db()


def _ensure_user1(conn):
    """Create user 1 so pieces can reference it (FK-respecting fixture)."""
    if conn.execute("SELECT 1 FROM users WHERE id = 1").fetchone():
        return
    sk, pk = generate_keypair()
    conn.execute(
        "INSERT INTO users (name, email, password_hash, role, public_key, encrypted_privkey) VALUES (?, ?, ?, ?, ?, ?)",
        ("fixture", f"fixture-{os.urandom(4).hex()}@test", "x", "maker",
         pk.public_bytes(encoding=serialization.Encoding.Raw,
                         format=serialization.PublicFormat.Raw).hex(),
         sk.private_bytes(encoding=serialization.Encoding.Raw,
                          format=serialization.PrivateFormat.Raw,
                          encryption_algorithm=serialization.NoEncryption()).hex()),
    )
    conn.commit()


def _photo(seed: int, size: int = 96, tilt: float = 0.0, noise_scale: float = 1.0) -> Image.Image:
    """Deterministic synthetic 'object' photo.

    seed controls the object identity: its blob layout (form), texture grid
    and colorings all derive from it. tilt shifts the viewpoint; noise_scale
    scales the sensor noise. Re-photographing object N = same seed, new
    tilt/noise. Different objects = different seeds.
    """
    rng = np.random.default_rng(seed)
    x = np.linspace(0, np.pi * 2, size)
    xx, yy = np.meshgrid(x, x)
    base = np.sin(xx * (1 + tilt) + yy * (2 + tilt) + seed) * 20 + 128
    px, py = np.meshgrid(np.arange(size), np.arange(size))
    for _ in range(6):
        cx, cy = rng.uniform(0.15, 0.85, 2) * size
        amp = rng.uniform(20, 55)
        rad = rng.uniform(size / 10, size / 4)
        base += amp * np.exp(-(((px - cx) ** 2 + (py - cy) ** 2) / (2 * rad ** 2)))
    tex = rng.integers(0, 255, (size // 8, size // 8)).astype(np.uint8)
    tex = np.asarray(Image.fromarray(tex, "L").resize((size, size), Image.BILINEAR), dtype=np.float64)
    noise = rng.normal(0, 4 * noise_scale, (size, size))
    gray = np.clip(base * 0.6 + tex * 0.4 + noise, 0, 255).astype(np.uint8)
    return Image.fromarray(gray, "L")


def _template(seed: int) -> fp.Template:
    return fp.build_template([_photo(seed)])


def _recapture(template_seed: int, tilt: float, noise_scale: float = 1.0) -> fp.Template:
    """A re-photograph of the SAME object: same layout, new noise/tilt.

    The blob layout that makes an object identifiable must come from the
    SAME seed; only tilt (viewpoint) and noise (sensor) vary per capture.
    """
    return fp.build_template([_photo(template_seed, tilt=tilt, noise_scale=noise_scale)])


def _make_piece(conn, code="CLONETEST"):
    _ensure_user1(conn)
    c = conn.cursor()
    c.execute(
        "INSERT INTO pieces (certificate_code, title, made_by, current_owner_id) VALUES (?, ?, ?, ?)",
        (code, "Clone test piece", 1, 1),
    )
    conn.commit()
    return dict(conn.execute(
        "SELECT * FROM pieces WHERE certificate_code = ?", (code,)
    ).fetchone())


def _events_count(conn, piece_id):
    return conn.execute(
        "SELECT COUNT(*) AS n FROM verification_events WHERE piece_id = ?", (piece_id,)
    ).fetchone()["n"]


def _fresh_conn():
    """Every test owns its connection; SQLite locks die with the handle."""
    return get_db()


def test_single_genuine_scan_never_flags():
    conn = _fresh_conn()
    try:
        piece = _make_piece(conn, code="SINGLESCAN")
        t = _template(100)
        record_event(conn, piece, 0.95, True, t)
        conn.commit()
        result = detect_clone(conn, piece, t)
        assert not result["flagged"], f"first scan flagged: {result}"
    finally:
        conn.close()


def test_same_object_rescans_never_flags():
    conn = _fresh_conn()
    try:
        piece = _make_piece(conn, code="RESCANS")
        t1 = _template(200)
        t2 = _recapture(200, tilt=0.04)   # same object, new viewpoint/noise
        t3 = _recapture(200, tilt=-0.03)
        assert fp.template_similarity(t1, t2) > fp.match_threshold()
        for t, m in ((t1, 0.95), (t2, 0.93), (t3, 0.93)):
            record_event(conn, piece, m, True, t)
        conn.commit()
        probe = _recapture(200, tilt=0.02)
        result = detect_clone(conn, piece, probe)
        assert not result["flagged"], f"genuine rescans flagged: {result}"
    finally:
        conn.close()


def test_cloned_tag_across_three_distinct_objects_flags():
    conn = _fresh_conn()
    try:
        piece = _make_piece(conn, code="KCLONES")
        # Three genuinely different objects photographed under one tag.
        a, b, c_t = _template(300), _template(400), _template(500)
        record_event(conn, piece, 0.95, True, a)
        record_event(conn, piece, None, None, b)
        record_event(conn, piece, None, None, c_t)
        conn.commit()
        probe = _template(600)   # yet another different object
        result = detect_clone(conn, piece, probe)
        assert result["flagged"], f"cloned tag not flagged: {result}"
    finally:
        conn.close()


def test_lone_mismatch_does_not_confirm():
    conn = _fresh_conn()
    try:
        piece = _make_piece(conn, code="LONEMISS")
        a, b = _template(700), _template(800)
        record_event(conn, piece, 0.95, True, a)
        record_event(conn, piece, None, None, b)  # second distinct object
        conn.commit()
        probe = _template(810)
        result = detect_clone(conn, piece, probe)
        # One previous distinct impression: suspicious, but not confirmed-clone.
        assert not result["flagged"], f"lone mismatch flagged: {result}"
    finally:
        conn.close()


def test_events_are_recorded():
    conn = _fresh_conn()
    try:
        piece = _make_piece(conn, code="EVENTS")
        t = _template(900)
        before = _events_count(conn, piece["id"])
        record_event(conn, piece, 0.9, True, t)
        conn.commit()
        assert _events_count(conn, piece["id"]) == before + 1
    finally:
        conn.close()


def test_plain_language_reasons():
    conn = _fresh_conn()
    try:
        piece = _make_piece(conn, code="WORDS")
        a, b, c = _template(1000), _template(1100), _template(1200)
        record_event(conn, piece, 0.95, True, a)
        record_event(conn, piece, None, None, b)
        record_event(conn, piece, None, None, c)
        conn.commit()
        result = detect_clone(conn, piece, _template(1300))
        assert result["flagged"]
        text = (result.get("reason") or "")
        assert ("cloning" in text or "clone" in text), f"reason not plain-language: {text}"
        bad_words = ["hash", "cosine", "similarity", "merkle", "signature"]
        assert not any(w in text.lower() for w in bad_words), f"jargon leaked: {text}"
    finally:
        conn.close()


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
