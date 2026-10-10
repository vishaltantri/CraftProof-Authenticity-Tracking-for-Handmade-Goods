"""Physical-fingerprint templates for CraftProof (plan W3).

Extracts a compact, comparably-matchable descriptor set from ordinary
photographs of a handmade object, so a verifier can later decide whether the
object in front of the camera is plausibly the enrolled one (plan §7 layer 3,
experiments E2/E3). Classical CV only: deterministic, no training data, no
GPU, every threshold inspectable (design constraint carried from CraftProof
v1: verification paths must stay independently re-implementable).

Descriptor set per image (all built with Pillow + NumPy):
  * d_hash           — 8x8 horizontal-gradient hash of the object crop
  * color            — 4x4x4 HSV histogram of the object crop
  * lbp              — patch histogram (radius 1, 8 samples)
  * l2_patterns      — rotation-minimized 16-bin histogram of Radon-warp
                       of the object crop
  * color_coherence  — hard/soft transition share (0..1)

An object template accumulates one descriptor vector per enrolled image.
`template_similarity` scores a probe template against an enrolled template
by per-field best-of match (max over the enrolled images), so a probe that
agrees with ANY reasonable view of the object passes — the right semantics
for "same object, photographed from a new angle on a stranger's phone";

THE THREAT MODEL (why fakes fail): a counterfeiting photograph of a
DIFFERENT object will disagree on short-distance pixel structure (dHash,
LBP) even when its color balance matches. The score is intentionally a
weighted mean of per-field similarity with STRUCTURAL fields carrying the
most weight, so one forgeable surface match (color) cannot carry the score.

Serialization: template_to_json -> canonical_json -> deflate -> url-safe
b64 in `serialize_template`; the matching digest to bind into custody
records is SHA-256 over the canonical JSON (never over the compressed
form), so commitments stay verifiable from the JSON alone.
"""

from __future__ import annotations

import hashlib
import json
import zlib
import base64
import os
from typing import Dict, List, Sequence, TypedDict

import numpy as np
from PIL import Image, ImageOps

# ---------------------------------------------------------------- config

HASH_SIZE = 8            # dHash grid: 8x8 comparisons -> 64 bits
HSV_BINS = (4, 4, 4)     # H x S x V -> 64 bins
LBP_POINTS = 8
LBP_RADIUS = 1

# Whole-template similarity weights (sum=1). Spatial structure dominates.
_W = {
    "spatial_texture": 0.25,
    "d_hash": 0.25,
    "form_hash": 0.25,
    "lbp": 0.10,
    "l2_patterns": 0.05,
    "color": 0.05,
    "structure": 0.05,
}
DEFAULT_MATCH_THRESHOLD = 0.70


# ------------------------------------------------------------ low-level CV

def _to_grayscale(img: Image.Image) -> Image.Image:
    return ImageOps.grayscale(img)


def _d_hash(gray: Image.Image) -> np.ndarray:
    """8x8 horizontal-gradient hash, normalised to 0..1 (bit-space)."""
    resized = gray.resize((HASH_SIZE + 1, HASH_SIZE), Image.BILINEAR)
    arr = np.asarray(resized, dtype=np.int16)
    diff = (arr[:, 1:] > arr[:, :-1]).astype(np.float64)  # (8, 8)
    return diff


def _d_hash_diag(gray: Image.Image) -> np.ndarray:
    """8x8 diagonal-gradient hash (same bit layout, 45° axis)."""
    resized = gray.resize((HASH_SIZE + 1, HASH_SIZE + 1), Image.BILINEAR)
    arr = np.asarray(resized, dtype=np.int16)
    diff = (arr[1:, 1:] > arr[:-1, :-1]).astype(np.float64)
    return diff


def _form_hash(gray: Image.Image, grid: int = 12) -> np.ndarray:
    """Where is the object bright and dark? A tiny luminance layout map.

    Spatial form is the one thing a different object cannot share: glaze
    pooling, carved facets and shadows sit in different places on different
    pieces. The crop is resized to grid x grid and each cell's mean luma is
    converted into a signed offset from the crop's overall mean. Resizing
    makes it scale-tolerant; the signed-offset form makes it exposure-
    tolerant (uniform brightening/darkening cancels).
    """
    small = np.asarray(gray.resize((grid, grid), Image.BILINEAR), dtype=np.float64)
    return small - small.mean()


def _l2_patterns(gray: Image.Image) -> np.ndarray:
    """Rotation-tolerant pattern histogram.

    Wavelet-style 16-bin histogram over a 4x4 grid of the object crop, keyed
    by the cosine of the direction of the local gradient (8 direction bins x
    {+, -}). Roughly orientation-invariant up to the 8-fold symmetries, and
    strictly local so genuine wear degrades gently.
    """
    arr = np.asarray(gray.resize((64, 64), Image.BILINEAR), dtype=np.float64)
    gy = np.gradient(arr, axis=0)
    gx = np.gradient(arr, axis=1)
    mag = np.hypot(gx, gy)
    angles = np.arctan2(gy, gx)
    # 8 direction bins over [0, pi); sign of gx+gy (not angle) as polarity
    dirs = np.clip(
        ((angles + np.pi) % np.pi) / np.pi * 8, 0, 7.999
    ).astype(np.int16)
    polar = np.clip((gx + gy).mean(), 0, None) * np.ones_like(mag)
    polar = np.where(gx + gy >= 0, 1.0, 0.0)
    H = np.zeros(16, dtype=np.float64)
    for b in range(8):
        sel = (dirs == b)
        if not sel.any():
            continue
        w = mag[sel] * polar[sel].mean()
        H[b] += w.sum()
        w2 = mag[sel] * (1.0 - polar[sel].mean())
        H[b + 8] += w2.sum()
    total = H.sum()
    return H / max(total, 1e-9)


def _to_hsv(img: Image.Image) -> np.ndarray:
    return np.asarray(img.convert("RGB").convert("HSV"), dtype=np.float64)


def _color_hist(hsv: np.ndarray) -> np.ndarray:
    h = np.clip((hsv[..., 0] / 256.0) * HSV_BINS[0], 0, HSV_BINS[0] - 1).astype(np.int16)
    s = np.clip((hsv[..., 1] / 256.0) * HSV_BINS[1], 0, HSV_BINS[1] - 1).astype(np.int16)
    v = np.clip((hsv[..., 2] / 256.0) * HSV_BINS[2], 0, HSV_BINS[2] - 1).astype(np.int16)
    flat = (h * HSV_BINS[1] * HSV_BINS[2] + s * HSV_BINS[2] + v).ravel()
    hist = np.bincount(flat, minlength=HSV_BINS[0] * HSV_BINS[1] * HSV_BINS[2])
    return hist.astype(np.float64) / max(hist.sum(), 1)


def _lbp(grid_mono: np.ndarray) -> np.ndarray:
    """Histogram of LBP codes over a grayscale patch (radius 1, 8 samples).

    Each 3x3 neighborhood produces one integer code (0..255); all 256 codes
    get their own bin (code = value), so structurally different textures must
    land in different bins. Folded "uniform vs non-uniform" binning provably
    destroys texture discrimination on smooth/gradient images (different
    synthetic textures collapsed to near-identical histograms) — full-width
    binning is what keeps LBP a structural feature worth its weight.

    The canonical LBP decision is strict-sign against the CENTER PIXEL
    (Ojala et al. 2002): ''code bit = neighbor >= center''. Weights follow
    the standard CCW sampling order P=8, R=1.
    """
    if grid_mono.ndim == 2 and grid_mono.dtype != np.float64:
        grid_mono = grid_mono.astype(np.float64)
    if grid_mono.size < 9 or min(grid_mono.shape) < 3:
        raise ValueError("image too small for texture analysis")
    center = grid_mono[1:-1, 1:-1]
    # Canonical CCW sample order starting mid-right (standard textbook layout).
    offsets = [(1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1)]
    acc = np.zeros_like(center, dtype=np.uint16)
    for bit, (dy, dx) in enumerate(offsets):
        shift = grid_mono[1 + dy: grid_mono.shape[0] - 1 + dy,
                          1 + dx: grid_mono.shape[1] - 1 + dx]
        acc |= ((shift >= center).astype(np.uint16) << bit)
    bins = np.bincount(acc.ravel(), minlength=256).astype(np.float64)
    total = bins.sum()
    return bins / max(total, 1)


def _spatial_texture(gray: np.ndarray, blocks: int = 6) -> np.ndarray:
    """Where is the texture? A blocks x blocks map of local structure.

    Real handmade objects are not texture-statistics: the glaze crazing
    cluster is HERE, the tool marks are THERE. This descriptor tiles the
    crop into 6x6 blocks and measures, per block, the local LBP-code
    diversity (Shannon entropy of the 3x3 LBP code distribution inside that
    block) plus mean gradient energy. Two different handmade objects will
    put their crazing in different places, so the block maps differ even
    when the global histograms agree — and both measures are robust to
    moderate re-photography of the SAME object.
    """
    if gray.ndim != 2:
        gray = np.asarray(ImageOps.grayscale(Image.fromarray(gray.astype(np.uint8))), dtype=np.float64)
    h, w = gray.shape
    if h < blocks * 3 or w < blocks * 3:
        raise ValueError("image too small for spatial texture analysis")
    # LBP codes once for the whole image (same rule as _lbp)
    center = gray[1:-1, 1:-1]
    offsets = [(1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1)]
    acc = np.zeros_like(center, dtype=np.uint16)
    for bit, (dy, dx) in enumerate(offsets):
        shift = gray[1 + dy: gray.shape[0] - 1 + dy, 1 + dx: gray.shape[1] - 1 + dx]
        acc |= ((shift >= center).astype(np.uint16) << bit)
    gy, gx = np.gradient(gray)
    grad = np.hypot(gx, gy)
    # per-block LBP entropy + gradient energy (blocks align to the inner map)
    out = np.zeros(blocks * blocks, dtype=np.float64)
    bh = (h - 2) // blocks
    bw = (w - 2) // blocks
    for by in range(blocks):
        for bx in range(blocks):
            cell = acc[by*bh:(by+1)*bh, bx*bw:(bx+1)*bw]
            hist = np.bincount(cell.ravel(), minlength=256).astype(np.float64)
            p = hist / max(hist.sum(), 1.0)
            p = p[p > 0]
            entropy = float(-(p * np.log2(p)).sum())
            gcell = grad[1 + by*bh: 1 + (by+1)*bh, 1 + bx*bw: 1 + (bx+1)*bw]
            energy = float(np.log1p(gcell.mean()))
            out[by*blocks + bx] = entropy * energy
    m = out.max()
    return out / m if m > 0 else out


def _color_coherence(hsv: np.ndarray) -> np.ndarray:
    """Three scalar structure features of the object crop.

    Returns [smooth_share, edge_share, dark_share], each clamped to [0,1]:
      smooth_share = fraction of adjacent-pixel luma gaps <= 4
        (piece-sensitive; distinguishes unplastered clay from glazed surface)
      edge_share   = fraction of Sobel-gradient magnitude above the 90th
        percentile normalized threshold (texture 'busyness')
      dark_share   = fraction of pixels below luma 60 (deep shadows from
        faceted sculpture, carved depth, etc.)
    """
    luma = hsv.mean(axis=2)
    smooth = float(np.clip((np.abs(np.diff(luma, axis=0)) <= 4).mean(), 0, 1))
    gy, gx = np.gradient(luma)
    grad = np.hypot(gx, gy)
    edge = float(np.clip((grad > float(np.percentile(grad, 95)) / 2).mean(), 0, 1))
    dark = float(np.clip((luma < 60).mean(), 0, 1))
    return np.array([smooth, edge, dark], dtype=np.float64)


# ------------------------------------------------------------ descriptor field

def extract_token_descriptor(img: Image.Image) -> Dict[str, np.ndarray]:
    """One descriptor vector for one image (used singly and in aggregate)."""
    gray = _to_grayscale(img)
    hsv = _to_hsv(img)
    return {
        "d_hash": _d_hash(gray).ravel(),
        "color": _color_hist(hsv),
        "lbp": _lbp(np.asarray(gray, dtype=np.int16).astype(np.float64)),
        "l2_patterns": _l2_patterns(gray),
        "structure": _color_coherence(hsv),
        "spatial_texture": _spatial_texture(np.asarray(gray, dtype=np.float64)),
        "form_hash": _form_hash(gray).ravel(),
    }


# ------------------------------------------------------------ template class

class Template(TypedDict):
    feature_flags: List[str]          # descriptor names (defines vector length)
    fields: Dict[str, List[List[float]]]  # field -> per-image vectors


def build_template(images: Sequence[Image.Image]) -> Template:
    """Build a physical-image template from one or more enrollment photos."""
    if not images:
        raise ValueError("need at least one image")
    fields: Dict[str, List[List[float]]] = {}
    feature_flags: List[str] = []
    for img in images:
        desc = extract_token_descriptor(img)
        if not feature_flags:
            feature_flags = sorted(desc)
        for name in feature_flags:
            fields.setdefault(name, []).append(desc[name].tolist())
    return {"feature_flags": feature_flags, "fields": fields}


# ------------------------------------------------------------ similarity

def _field_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity when vectors are non-trivial, else exact-match share."""
    if a.size != b.size:
        raise ValueError(f"descriptor size mismatch: {a.size} vs {b.size}")
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    if denom <= 0:
        return 1.0 if np.array_equal(a, b) else 0.0
    return float(np.dot(a, b) / denom)


def _scalar_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """1 - |mean_a - mean_b| clamped to [0, 1] (for 0..1 scalar features)."""
    return float(np.clip(1.0 - abs(a.mean() - b.mean()), 0.0, 1.0))


def _match_vectors(a: np.ndarray, b: np.ndarray, field: str) -> float:
    """Field-appropriate similarity.

    - 1-element vectors are 0..1 scalars: similarity = 1 - |a - b|
    - 'structure' is a 3-vector of 0..1 scalars: component-wise 1-|delta|
      averaged.
    - everything else (histograms, bit planes, spatial maps) is cosine.
    """
    if a.size == 1 or b.size == 1:
        return _scalar_similarity(a, b)
    if field == "structure":
        return float(np.mean(np.clip(1.0 - np.abs(a - b), 0.0, 1.0)))
    return _field_similarity(a, b)


def _best_match(enrolled: Sequence[np.ndarray], probe: np.ndarray, field: str) -> float:
    """Best per-image similarity for one field ("any enrolled view wins")."""
    return max(_match_vectors(np.asarray(v, float), probe, field) for v in enrolled)


def template_similarity(enrolled: Template, probe: Template) -> float:
    """Weakest-link template similarity in [0, 1].

    For each field: best over enrolled-image vectors. Score = mean of the
    weighted per-field similarities (min over fields would be too brittle
    once a single view has sun-flare; the weights in _W keep structural
    features dominant, so counterfeits still fail hard).
    """
    fields = [f for f in enrolled["feature_flags"] if f in probe["fields"]]
    if not fields:
        raise ValueError("no comparable descriptor fields between templates")
    total = 0.0
    for field in fields:
        enrolled_field = np.asarray(enrolled["fields"][field], float)
        best = _best_match(enrolled_field, np.asarray(probe["fields"][field][0], float), field)
        total += _W.get(field, 0.0) * best
    used = sum(_W.get(f, 0.0) for f in fields)
    return max(0.0, min(1.0, total / max(used, 1e-9)))


def match_threshold() -> float:
    return float(os.environ.get("CRAFTPROOF_MATCH_THRESHOLD", DEFAULT_MATCH_THRESHOLD))


# ------------------------------------------------------------ (de)serialization

def descriptorset_to_json(t: Template) -> bytes:
    return json.dumps(
        {"feature_flags": t["feature_flags"], "fields": t["fields"]},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def template_from_json(raw: bytes) -> Template:
    doc = json.loads(raw.decode("utf-8"))
    return {"feature_flags": doc["feature_flags"],
            "fields": {k: [np.asarray(v, dtype=float).tolist() for v in vecs]
                       for k, vecs in doc["fields"].items()}}


def serialize_template(t: Template) -> bytes:
    return base64.urlsafe_b64encode(zlib.compress(descriptorset_to_json(t), 6))


def deserialize_template(blob: bytes) -> Template:
    return template_from_json(zlib.decompress(base64.urlsafe_b64decode(blob)))


def template_digest(t: Template) -> str:
    """SHA-256 hex over the canonical JSON — this is the custody commitment."""
    return hashlib.sha256(descriptorset_to_json(t)).hexdigest()


# ------------------------------------------------------- server-side storage

_CRAFTPROOF_TEMPLATES_DIR = os.environ.get(
    "CRAFTPROOF_TEMPLATES_DIR",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates"),
)


def _template_path(piece_id: int) -> str:
    return os.path.join(_CRAFTPROOF_TEMPLATES_DIR, f"{piece_id}.json")


def store_template(piece_id: int, t: Template) -> str:
    """Persist the enrolled template for a piece (server-side, JSON file).

    The piece's custody commitment (in the signed genesis record) binds this
    file: any tampering with the stored template is detected by re-hashing it
    and comparing against the chain. Returns the commitment hex digest.
    """
    os.makedirs(_CRAFTPROOF_TEMPLATES_DIR, exist_ok=True)
    path = _template_path(piece_id)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(descriptorset_to_json(t).decode("utf-8"))
    return template_digest(t)


def load_template_by_piece(piece_id: int) -> Template | None:
    """Load the enrolled template for a piece, or None when not enrolled."""
    path = _template_path(piece_id)
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as fh:
        return template_from_json(fh.read().encode("utf-8"))


def _event_template_path(digest: str) -> str:
    return os.path.join(_CRAFTPROOF_TEMPLATES_DIR, f"event-{digest}.json")


def store_event_template(digest: str, t: Template) -> None:
    """Persist a probe template so later clone checks can recall it.

    Keyed by the template's SHA-256 digest; identical probes (same object,
    same capture) overwrite the same file, so repeated genuine scans cost
    no extra storage.
    """
    os.makedirs(_CRAFTPROOF_TEMPLATES_DIR, exist_ok=True)
    with open(_event_template_path(digest), "w", encoding="utf-8") as fh:
        fh.write(descriptorset_to_json(t).decode("utf-8"))


def load_event_template(digest: str) -> Template | None:
    path = _event_template_path(digest)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return template_from_json(fh.read().encode("utf-8"))
    except Exception:
        return None
