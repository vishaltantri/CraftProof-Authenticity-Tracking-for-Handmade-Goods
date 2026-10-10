#!/usr/bin/env python3
"""Smoke test for experiments/build_pairs.py using synthetic fixture photos."""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

EXPERIMENTS = Path(__file__).resolve().parent
sys.path.insert(0, str(EXPERIMENTS.parent / "backend"))  # for PIL/numpy availability

import numpy as np
from PIL import Image

home = Path(tempfile.mkdtemp(prefix="craftproof-dataset-test-"))
photos = home / "photos"

rows = []
# 12 same-object-pair-eligible objects × 2 photos each (consecutive ids)
for obj_i in range(1, 15):
    obj = f"obj{obj_i:03d}"
    d = photos / obj
    d.mkdir(parents=True, exist_ok=True)
    for shot in ("01_front", "06_extra"):
        arr = np.random.default_rng(f"{obj}{shot}".__hash__() % (2**32)).integers(
            0, 255, (48, 48, 3)).astype("uint8")
        Image.fromarray(arr, "RGB").save(d / f"{shot}.jpg")
        rows.append([obj, f"photos/{obj}/{shot}.jpg", "self", "owned", "y",
                     "pixel6", "window daylight", "same-object-pair-eligible", ""])

# Impostor-only object with missing file (should be excluded)
rows.append(["obj900", "photos/obj900/01_front.jpg", "cc_public_domain", "cc0", "na",
             "unknown", "unknown", "impostor-only", ""])

manifest = home / "manifest.csv"
import csv
with open(manifest, "w", newline="", encoding="utf-8") as fh:
    w = csv.writer(fh)
    w.writerow(["object_id", "image_path", "capture_source", "license", "consent",
                "capture_device", "capture_context", "set", "notes"])
    w.writerows(rows)

out = home / "out"
r = subprocess.run(
    [sys.executable, str(EXPERIMENTS / "build_pairs.py"),
     "--manifest", str(manifest), "--photos-root", str(home), "--out", str(out)],
    capture_output=True, text=True)

print(r.stdout)
if r.returncode != 0:
    print(r.stderr)
    sys.exit(f"build_pairs failed (exit {r.returncode})")

summary = json.loads((out / "pairs_summary.json").read_text())
assert summary["objects"] == 14, summary
assert summary["photos_excluded"] == 1, summary
assert summary["same_object_pairs"] == 14, summary
assert (out / "excluded.csv").read_text().strip().endswith("file missing")
assert summary["impostor_pairs"] >= 400, summary
print("test_build_pairs: OK")
