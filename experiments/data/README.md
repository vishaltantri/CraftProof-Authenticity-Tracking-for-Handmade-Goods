# CraftProof Dataset Kit (plan W8, feeds experiments E2 / E3 / E4)

A non-expert should be able to produce the photo dataset the experiments
need, ethically, with no scraping anywhere in the pipeline. Three files do
the work: this checklist, the consent form template, and `manifest.csv`.

## 1. What the dataset is for (and the hard rules)

The experiments need two groups of photos:

- **Same-object pairs** — two or more photos of the SAME handmade object.
  These teach the matcher what "same thing, different photo" looks like.
- **Impostor pairs** — photos of DIFFERENT objects. These teach it what
  "different" looks like.

**Hard rules — no exceptions (plan §11):**

1. Never scrape any website. Never bulk-download. If a marketplace listing
   contains several photos of the one same item, you may *manually* save
   those images for your own research use only, and you record the source
   and license in the manifest. Do not republish them.
2. No faces, no people, no personally identifiable surroundings (house
   numbers, license plates, documents). Reframe or crop before adding.
3. Images stay on your machine for the study. They are not reposted,
   published, or shared. Paper figures use only author-owned or synthetic
   images (the synthetic generator lives in
   `backend/test_fingerprint.py` / the attack harness).
4. Every image you did not take yourself gets a `capture_source` +
   `license` entry. No blanks.

## 2. The 5-shot photography checklist

Per object, take FIVE photos in this order. Ordinary daylight, near a
window, no flash; a plain matte background (a pillowcase works). The whole
object in frame, in focus.

| # | Shot | Aim |
|---|------|-----|
| 1 | **Front**, object facing camera | overall form |
| 2 | **Back** (or underside) | the "other side" |
| 3 | **Oblique left**, ~30–45° to the left | edges, handles, joins |
| 4 | **Oblique right**, ~30–45° to the right | the other profile |
| 5 | **Macro of a distinctive area**: a chip, glaze pooling, carve marks, weave knot | local texture |

If you re-photograph the same object later (weeks, different room, phone
vs camera), that is a **same-object pair** and is even more valuable —
keep both sessions in the manifest under the same `object_id`.

## 3. Naming scheme

    photos/<object_id>/<NN>_<shot>.jpg
      <object_id>  = your own label, e.g. obj001, obj002, ...
      <NN>         = 01..05 for the five checklist shots; 06+ extra photos
      <shot>       = front | back | obl_l | obl_r | macro | extra

Example:

    photos/obj003/01_front.jpg
    photos/obj003/02_back.jpg
    photos/obj003/06_extra.jpg

Re-photograph sessions: create a sibling folder
`photos/<object_id>/session2/` and keep the same shot names inside.

## 4. Consent form template

Print or copy this for every object whose photos you (or a colleague) took.
Keep the signed page; record just `consent=y` (or `n` / `na`) in the manifest.

```
CONSENT FOR CRAFTPROOF RESEARCH PHOTOS
---------------------------------------
I own (or photographed with permission) the handmade object described
below and I agree that photos of it — with no people or personal details
in them — may be used by the CraftProof research project to test its
verification software. I understand the photos stay with the researcher,
are not published, and I can ask for them to be deleted at any time.

Object description: ____________________________
Object owner: __________________________________
Photographer (if not owner): ___________________
Email/contact: _________________________________
Date: ____________   Signature: ________________
```

## 5. `manifest.csv` — required columns

One row per photo (not per object). Columns per plan §11:

    object_id,image_path,capture_source,license,consent,
    capture_device,capture_context,set,notes

- `capture_source`: `self` (you took it), `colleague`, `marketplace_listing`,
  `cc_public_domain` — plus a free-form reference (URL or name) in `notes`.
- `license`: `owned`, `permission-on-file`, `cc0`, `cc-by`, `together-with-source-link`,
  or `unknown-do-not-use` (rows with this license get EXCLUDED by the loader).
- `consent`: `y` / `n` / `na` (na = CC-licensed commercial-use images).
- `capture_device`: e.g. `pixel6`, `eos_m50`, `scan`.
- `capture_context`: `window daylight`, `overcast outdoors`, `indoor lamp`, ...
- `set`: `same-object-pair-eligible`, `impostor-only` — which experiment pool
  the row belongs to. An object is same-object-pair-eligible once it has two
  or more photos (same or different sessions).

Minimum bar for a full result (plan §11): **≥ 60 distinct objects,
≥ 150 same-object pairs, ≥ 400 impostor pairs.** Below that, the paper
reports the run as a *pilot*, not a definitive benchmark.

## 6. Building the experiment files from the manifest

`build_pairs.py` turns the manifest into the pair files E2 expects:

    cd backend && source venv/bin/activate
    python3 ../experiments/build_pairs.py --manifest ../experiments/data/manifest.csv \
        --photos-root ../experiments/data/photos \
        --out ../experiments/data

It emits:

    same_pairs.csv    object_id,img_a,img_b          (the E2 same-object pairs)
    impostor_pairs.csv object_id_a,img_a,object_id_b,img_b
    excluded.csv      image_path,reason               (a pair/image audit trail)

Exclusion reasons: `unknown-do-not-use` license, missing consent where it is
required, unreadable file, or identical image path on both sides.

It refuses to run without at least 10 usable objects — accidental
"everything excluded" surprises stay loud.

## 7. Quick start for a non-expert

1. Photograph five shots of each object per §2.
2. Save into `photos/<object_id>/01_front.jpg` etc.
3. Fill one manifest row per photo. When unsure about a column, leave
   `unknown-do-not-use` (the loader excludes it, which is safe).
4. Get the one-page consent signed for self/colleague photos.
5. Run `build_pairs.py`.
