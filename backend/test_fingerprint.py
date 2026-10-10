"""Unit tests for the physical-fingerprint templates (W3)."""

import os
import sys
import tempfile

# Keep every test isolated from the developer's real database.
_TMP_DB = os.path.join(tempfile.mkdtemp(prefix="craftproof-fp-test-"), "test.db")
os.environ["CRAFTPROOF_DB"] = _TMP_DB

import numpy as np
from PIL import Image

from fingerprint import (
    build_template, template_similarity, serialize_template,
    deserialize_template, template_digest, descriptorset_to_json,
    match_threshold,
)


def _photo(seed: int, size: int = 96, tilt: float = 0.0) -> Image.Image:
    """Deterministic synthetic 'object' photo.

    Modeled on real craft surfaces: a per-object low-frequency form (random
    shading blobs — the glaze pooling, carved facets), a per-object texture
    layer, and fine noise. Two different objects differ in local structure
    AND its spatial layout; the same object re-photographed differs only in
    global phase (tilt) and sensor noise — exactly the separation the
    descriptors must achieve.
    """
    rng = np.random.default_rng(seed)
    x = np.linspace(0, np.pi * 2, size)
    xx, yy = np.meshgrid(x, x)
    base = np.sin(xx * (1 + tilt) + yy * (2 + tilt) + seed) * 20 + 128
    # per-object form: random shading blobs at fixed pixel positions
    px, py = np.meshgrid(np.arange(size), np.arange(size))
    for _ in range(6):
        cx, cy = rng.uniform(0.15, 0.85, 2) * size
        amp = rng.uniform(20, 55)
        rad = rng.uniform(size / 10, size / 4)
        base += amp * np.exp(-(((px - cx) ** 2 + (py - cy) ** 2) / (2 * rad ** 2)))
    # per-object texture: 12x12 grid of random-intensity patches, smoothed
    tex = rng.integers(0, 255, (size // 8, size // 8)).astype(np.float64)
    tex_img = Image.fromarray(tex.astype(np.uint8), "L").resize((size, size), Image.BILINEAR)
    tex = np.asarray(tex_img, dtype=np.float64)
    noise = rng.normal(0, 4, (size, size))
    gray = np.clip(base * 0.6 + tex * 0.4 + noise, 0, 255).astype(np.uint8)
    return Image.fromarray(gray, "L")


def test_deterministic_extraction():
    a = build_template([_photo(7)])
    b = build_template([_photo(7)])
    assert descriptorset_to_json(a) == descriptorset_to_json(b)


def test_same_object_high_similarity():
    enrolled = build_template([_photo(1), _photo(1, tilt=0.05)])
    probe = build_template([_photo(1, tilt=0.02)])
    score = template_similarity(enrolled, probe)
    assert score >= 0.85, f"same object scored {score}"


def test_different_objects_low_similarity():
    a = build_template([_photo(10), _photo(11)])
    b = build_template([_photo(20), _photo(21)])
    score = template_similarity(a, b)
    assert score < 0.75, f"different objects scored {score}"


def test_separation_margin():
    enrolled = build_template([_photo(3)])
    same = build_template([_photo(3, tilt=0.03)])
    other = build_template([_photo(90)])
    s_same = template_similarity(enrolled, same)
    s_other = template_similarity(enrolled, other)
    assert s_same - s_other > 0.1, f"margin too thin: same={s_same} other={s_other}"


def test_serialization_round_trip():
    t = build_template([_photo(5), _photo(6)])
    blob = serialize_template(t)
    assert isinstance(blob, bytes)
    t2 = deserialize_template(blob)
    assert abs(template_similarity(t, t2) - 1.0) < 1e-9


def test_commitment_is_stable_and_binds_content():
    t1 = build_template([_photo(9)])
    t2 = build_template([_photo(9)])
    t_other = build_template([_photo(99)])
    assert template_digest(t1) == template_digest(t2)
    assert template_digest(t1) != template_digest(t_other)
    assert len(template_digest(t1)) == 64


def test_threshold_is_configurable():
    os.environ["CRAFTPROOF_MATCH_THRESHOLD"] = "0.5"
    try:
        assert match_threshold() == 0.5
    finally:
        del os.environ["CRAFTPROOF_MATCH_THRESHOLD"]
    assert match_threshold() == 0.70


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
