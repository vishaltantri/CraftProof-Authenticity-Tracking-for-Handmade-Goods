#!/usr/bin/env python3
"""Build the E2 pair files from the dataset manifest (plan W8 / experiment E2).

Reads manifest.csv (columns in data/README.md §5), validates the ethics
columns, and emits:

    same_pairs.csv      object_id,img_a,img_b
    impostor_pairs.csv  object_id_a,img_a,object_id_b,img_b
    excluded.csv        image_path,reason
    pairs_summary.json  counts + the §11 minimum-bar check

Safety rules encoded here (plan §11 hard rules):
  * rows whose license is unknown-do-not-use are excluded and recorded
  * self / colleague photos without consent=y are excluded
  * image files that cannot be opened are excluded
  * no scraping, no network access anywhere in this script

Run:

    cd craftproof/backend && source venv/bin/activate
    python3 ../experiments/build_pairs.py \
        --manifest ../experiments/data/manifest.csv \
        --photos-root ../experiments/data/photos \
        --out ../experiments/data
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from pathlib import Path

REQUIRED_COLUMNS = ["object_id", "image_path", "capture_source", "license",
                    "consent", "capture_device", "capture_context", "set", "notes"]
DO_NOT_USE = "unknown-do-not-use"
NEEDS_CONSENT = {"self", "colleague"}
MIN_OBJECTS = 10          # loud failure if the usable dataset is tiny
PAIR_SAMPLING_SEED = 42


def _openable(path: Path) -> bool:
    try:
        from PIL import Image
        with Image.open(path) as im:
            im.load()
        return True
    except Exception:
        return False


def load_manifest(path: Path) -> tuple[list[dict], list[tuple[str, str]]]:
    if not path.exists():
        sys.exit(f"manifest not found: {path}\nStart from the template: "
                 f"manifest_template.csv next to this script's data/README.md")
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        missing = [c for c in REQUIRED_COLUMNS if c not in (reader.fieldnames or [])]
        if missing:
            sys.exit(f"manifest is missing required columns: {missing}")
        rows = list(reader)
    excluded: list[tuple[str, str]] = []
    for r in rows:
        r["image_path"] = (r["image_path"] or "").strip()
        r["_reason"] = None
    return rows, excluded


def validate(rows: list[dict], excluded: list[tuple[str, str]], photos_root: Path) -> list[dict]:
    keep: list[dict] = []
    for r in rows:
        ip = r["image_path"]
        reason = None
        if not ip:
            reason = "empty image_path"
        elif r["license"].strip().lower() == DO_NOT_USE:
            reason = "license unknown-do-not-use"
        elif r["capture_source"].strip().lower() in NEEDS_CONSENT and r["consent"].strip().lower() != "y":
            reason = "consent required for self/colleague photos"
        elif not (photos_root / ip).exists():
            reason = "file missing"
        elif not _openable(photos_root / ip):
            reason = "unreadable image"
        if reason:
            excluded.append((ip, reason))
        else:
            keep.append(r)
    return keep


def build_pairs(rows: list[dict]) -> tuple[list[list[str]], list[list[str]]]:
    rng = random.Random(PAIR_SAMPLING_SEED)
    by_object: dict[str, list[str]] = {}
    for r in rows:
        by_object.setdefault(r["object_id"], []).append(r["image_path"])

    same: list[list[str]] = []
    for obj, imgs in sorted(by_object.items()):
        for i in range(len(imgs)):
            for j in range(i + 1, len(imgs)):
                same.append([obj, imgs[i], imgs[j]])

    objects = sorted(by_object)
    impostor: list[list[str]] = []
    target = max(len(same) * 2, 400)          # ≥ 2× impostors vs same pairs
    tries = 0
    while len(impostor) < target and tries < target * 20:
        a, b = rng.sample(objects, 2) if len(objects) >= 2 else (None, None)
        tries += 1
        if a is None:
            break
        ia = rng.choice(by_object[a])
        ib = rng.choice(by_object[b])
        impostor.append([a, ia, b, ib])
    return same, impostor


def main() -> None:
    ap = argparse.ArgumentParser(description="Build E2 pair files from the manifest")
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--photos-root", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    photos_root = Path(args.photos_root)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    rows, excluded = load_manifest(Path(args.manifest))
    keep = validate(rows, excluded, photos_root)
    if not keep:
        sys.exit("no usable rows after exclusion — check excluded.csv "
                 "(none written because there is nothing to audit)")

    same, impostor = build_pairs(keep)

    with open(out / "same_pairs.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["object_id", "img_a", "img_b"])
        w.writerows(same)
    with open(out / "impostor_pairs.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["object_id_a", "img_a", "object_id_b", "img_b"])
        w.writerows(impostor)
    with open(out / "excluded.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["image_path", "reason"])
        w.writerows(excluded)

    n_objects = len({r["object_id"] for r in keep})
    summary = {
        "objects": n_objects,
        "photos_kept": len(keep),
        "photos_excluded": len(excluded),
        "same_object_pairs": len(same),
        "impostor_pairs": len(impostor),
        "meets_plan_minimum_bar": (n_objects >= 60 and len(same) >= 150
                                    and len(impostor) >= 400),
        "minimum_bar_definition": ">= 60 objects, >= 150 same pairs, >= 400 impostor pairs (plan §11)",
    }
    (out / "pairs_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(json.dumps(summary, indent=2))
    if n_objects < MIN_OBJECTS:
        sys.exit(f"only {n_objects} usable object(s) — refusing to emit analysis-ready "
                 f"pairs from a dataset this small (see data/README.md §6)")


if __name__ == "__main__":
    main()
