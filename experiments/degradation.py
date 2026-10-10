#!/usr/bin/env python3
"""E3 — synthetic degradation robustness (plan §9.3).

For each cell in the degradation grid, recompute the fused similarity
between the ENROLMENT template and a probe of the same object degraded by
that transformation, and (crucially) the same degradation applied to a
DIFFERENT object as the impostor baseline. Per cell it reports:

    mean_genuine, mean_impostor, auc, fpr_at_frr10, n

`fpr_at_frr10` is the metric the plan specifies (FPR at the operating
point where the false-rejection rate is fixed at 10% — what a buyer
actually feels). The pass condition from §9.3 is AUC >= 0.95 in the
central cells; the script prints which cells fall below it and writes a
CSV for the paper's heat map.

Deterministic: object identities and all noise draw from fixed seeds.

    cd craftproof/backend && source venv/bin/activate
    python3 ../experiments/degradation.py --objects 10 \
        --out ../experiments/results/e3_degradation.csv

NOTE (plan §14 limitation L1): synthetic degradation does NOT replace
controlled re-capture of real objects — it isolates which transformation
axes dominate the loss, using the same deterministic photo generator as
test_fingerprint.py, so the run needs no dataset.
"""
from __future__ import annotations

import argparse
import csv
import random
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND))

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter, ImageOps

import fingerprint as fp


# ------------------------------------------------------------------ photos

def photo(seed: int, size: int = 128, tilt: float = 0.0, noise_scale: float = 1.0) -> Image.Image:
    """Deterministic synthetic object photo — same generator semantics as
    test_fingerprint.py (seed = object identity)."""
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
    tex = np.asarray(Image.fromarray(tex, "L").resize((size, size), Image.BILINEAR),
                     dtype=np.float64)
    noise = rng.normal(0, 4 * noise_scale, (size, size))
    gray = np.clip(base * 0.6 + tex * 0.4 + noise, 0, 255).astype(np.uint8)
    return Image.fromarray(gray, "L").convert("RGB")


# -------------------------------------------------------------- degradations

def degrade(img: Image.Image, axis: str, level, seed: int) -> Image.Image:
    """Apply one grid cell. level is axis-specific (see GRID below)."""
    if axis == "jpeg":
        import io
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=int(level))
        return Image.open(buf).convert("RGB")
    if axis == "rotation":
        return img.rotate(float(level), resample=Image.BILINEAR, expand=False)
    if axis == "scale":
        w, h = img.size
        nw, nh = int(w * level), int(h * level)
        scaled = img.resize((nw, nh), Image.BILINEAR)
        canvas = Image.new("RGB", (w, h), (0, 0, 0))
        canvas.paste(scaled, ((w - nw) // 2, (h - nh) // 2))
        return canvas
    if axis == "brightness":
        return ImageEnhance.Brightness(img).enhance(level)
    if axis == "contrast":
        return ImageEnhance.Contrast(img).enhance(level)
    if axis == "noise":
        arr = np.asarray(img, dtype=np.float64)
        rng = np.random.default_rng(seed)
        arr = np.clip(arr + rng.normal(0, level, arr.shape), 0, 255)
        return Image.fromarray(arr.astype(np.uint8), "RGB")
    if axis == "crop":
        w, h = img.size
        cw, ch = int(w * level), int(h * level)
        x0, y0 = (w - cw) // 2, (h - ch) // 2
        return img.crop((x0, y0, x0 + cw, y0 + ch)).resize((w, h), Image.BILINEAR)
    if axis == "blur":
        return img.filter(ImageFilter.GaussianBlur(radius=float(level)))
    raise ValueError(f"unknown degradation axis {axis!r}")


GRID: dict[str, list] = {
    "jpeg":       [90, 75, 60, 40],
    "rotation":   [-45, -15, -5, 5, 15, 45],
    "scale":      [0.8, 1.2],
    "brightness": [0.6, 1.4],
    "contrast":   [0.6, 1.4],
    "noise":      [8, 20],
    "crop":       [0.9, 0.8],
    "blur":       [1.5, 3.0],
}
# Central (mild) cells — the §9.3 pass condition applies to these:
CENTRAL = {"jpeg": {90, 75}, "rotation": {-5, 5}, "scale": {0.8, 1.2},
           "brightness": {0.6, 1.4}, "contrast": {0.6, 1.4}, "noise": {8},
           "crop": {0.9}, "blur": {1.5}}


# ------------------------------------------------------------------ metrics

def auc(genuine: list[float], impostor: list[float]) -> float:
    """Mann-Whitney AUC: P(genuine > impostor), ties = 0.5."""
    g, i = sorted(genuine), sorted(impostor)
    import bisect
    wins = 0.0
    for gv in g:
        lo = bisect.bisect_left(i, gv)
        hi = bisect.bisect_right(i, gv)
        wins += lo + 0.5 * (hi - lo)
    return wins / (len(g) * len(i))


def fpr_at_frr(genuine: list[float], impostor: list[float], frr: float = 0.10) -> float:
    """FPR when the match threshold sits at the FRR-quantile of genuine."""
    g = sorted(genuine)
    idx = max(0, min(len(g) - 1, int(len(g) * frr)))   # reject the worst frr share
    threshold = g[idx]
    return sum(1 for s in impostor if s >= threshold) / len(impostor)


# -------------------------------------------------------------------- main

def main() -> None:
    ap = argparse.ArgumentParser(description="E3 degradation robustness")
    ap.add_argument("--objects", type=int, default=10, help="distinct object identities")
    ap.add_argument("--out", default=None, help="CSV path for the heat-map data")
    args = ap.parse_args()

    rng = random.Random(31337)
    base_seeds = [10_000 + i * 977 for i in range(args.objects)]
    # impostor universe: disjoint seeds
    imp_seeds = [900_000 + i * 7919 for i in range(args.objects)]

    # Enrol: 3 clean captures per object (viewpoint variation only).
    enrolled = {}
    for s in base_seeds:
        enrolled[s] = fp.build_template([photo(s, tilt=t) for t in (0.0, 0.08, -0.08)])

    rows = []
    print(f"{'axis':<12} {'level':>7} {'genuine':>8} {'impostor':>9} "
          f"{'AUC':>7} {'FPR@FRR10':>10}  verdict")
    print("-" * 76)
    central_failures = []

    for axis, levels in GRID.items():
        for level in levels:
            genuine_scores, impostor_scores = [], []
            for s in base_seeds:
                probe = fp.build_template([degrade(photo(s, tilt=0.05), axis, level, s)])
                genuine_scores.append(fp.template_similarity(enrolled[s], probe))
                # impostor: a different object through the SAME degradation
                other = imp_seeds[rng.randrange(len(imp_seeds))]
                iprobe = fp.build_template([degrade(photo(other, tilt=0.05), axis, level, other)])
                impostor_scores.append(fp.template_similarity(enrolled[s], iprobe))

            a = auc(genuine_scores, impostor_scores)
            f = fpr_at_frr(genuine_scores, impostor_scores)
            ok = a >= 0.95
            is_central = level in CENTRAL.get(axis, set())
            if is_central and not ok:
                central_failures.append((axis, level, a))
            rows.append({
                "axis": axis, "level": level,
                "mean_genuine": round(float(np.mean(genuine_scores)), 4),
                "mean_impostor": round(float(np.mean(impostor_scores)), 4),
                "auc": round(a, 4),
                "fpr_at_frr10": round(f, 4),
                "n_objects": len(base_seeds),
                "central_cell": int(is_central),
                "pass": int(ok),
            })
            print(f"{axis:<12} {level:>7} {np.mean(genuine_scores):>8.3f} "
                  f"{np.mean(impostor_scores):>9.3f} {a:>7.3f} {f:>10.3f}  "
                  f"{'PASS' if ok else 'FAIL'}{' *' if (is_central and not ok) else ''}")

    print("\n* = central cell below the §9.3 pass condition (AUC >= 0.95)")
    if central_failures:
        print(f"central-cell failures: {len(central_failures)} "
              f"(plan §14 branch C would be considered for the paper)")
    else:
        print("central-cell pass condition met: AUC >= 0.95 in every central cell")

    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        with open(args.out, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
        print(f"\nCSV -> {args.out}")


if __name__ == "__main__":
    main()
