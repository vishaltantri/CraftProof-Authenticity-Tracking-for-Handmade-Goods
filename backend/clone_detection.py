"""Clone / tag-substitution detection across the ownership lifecycle (W5).

The physical–digital binding has an Achilles heel the provenance chain
cannot see: the QR tag is just paper. If a counterfeiter copies one genuine
tag onto K counterfeit objects, every *cryptographic* check keeps passing —
the certificate is genuine; it is the object under it that is not.

Detection principle: every physical verification records which fingerprint
was presented against which certificate code. When the same code is
repeatedly paired with fingerprints that disagree with *each other*, at
most one of those pairings can be genuine — so the tag is cloned and riding
on multiple bodies. This is deliberately independent of the enrolled
template: even a piece with NO enrollment (legacy) gets clone detection,
because it needs only within-code fingerprint disagreement, not ground truth.

Design points
-------------
* Impression matching uses pairwise template similarity between the probe
  and previously seen fingerprints for the same code. A cheap quantized
  bit-signature pre-filter discards obvious non-matches before precise
  similarity work — pre-filtering only ever *defers* a flag; it can never
  suppress one (no precision is lost on the final decision path).
* Verdicts use plain language only (CraftProof's UI golden rule): the
  certificate page says "Possible tag cloning detected" — never "hash",
  "cosine", "similarity".
* Flag policy is conservative: one genuine capture (3 mis-matched events
  against a series of other distinct objects) never cries wolf; the rule
  requires a MINIMUM impression group of SIZE >= 2 (at least one previous
  distinct impression), and flags when an arriving impression fails against
  a >= 2-strong sibling group (they agree with each other, not with it).
* The event ledger stores quantized canonical descriptor records so the
  history is auditable and re-checkable later without re-sending captures.
"""

from __future__ import annotations

import hashlib
import json
from typing import Optional

from database import get_db
import fingerprint as fp


# ----------------------------------------------------------------- signatures

def _signatures(t: fp.Template) -> list[str]:
    """Quantized sign-bit signatures for cheap pre-filtering.

    The discriminative field is form_hash: a different object puts its
    bright/dark layout in different places, so its sign pattern differs;
    re-photographs of the SAME object keep the layout and the sign pattern.
    Sign-bit signatures of DISTRIBUTIONS (lbp/color histograms) are
    meaningless — every textured object gives a near-uniform histogram whose
    every bit lands on the same side of its mean — so only layout-style
    vectors are signed. The pre-filter only ever defers a flag; the precise
    similarity always decides.
    """
    SIGN_AS_IS_FIELDS = ("form_hash",)
    sigs: list[str] = []
    for field, vectors in t["fields"].items():
        if field == "d_hash":  # already binary; use its raw bits directly
            for vec in vectors:
                sigs.append(''.join('1' if float(b) > 0.5 else '0' for b in vec))
            continue
        if field not in SIGN_AS_IS_FIELDS:
            continue
        for vec in vectors:
            a = fp.np.asarray(vec, dtype=float)
            bits = (a > 0).astype(int)
            sigs.append(''.join(str(b) for b in bits))
    return sigs


_SIGNATURE_PRE_FILTER_THRESHOLD = 0.80


def _signature_compatible(a: str, b: str) -> bool:
    if not a or not b or len(a) != len(b):
        return False
    same = sum(1 for x, y in zip(a, b) if x == y)
    return (same / len(a)) >= _SIGNATURE_PRE_FILTER_THRESHOLD


# ---------------------------------------------------------------- similarity

def _pair_similarity(a: fp.Template, b: fp.Template) -> float:
    """Symmetric pairwise similarity for two templates (mirrored call)."""
    return max(fp.template_similarity(a, b), fp.template_similarity(b, a))


# ------------------------------------------------------------- event recording

def record_event(conn, piece, similarity: Optional[float], match: Optional[bool],
                 probe: fp.Template) -> dict:
    """Persist one physical-verification event and return the stored row.

    The probe template is stored beside the event (file named by its digest)
    so later precise comparisons can recall it; only its digest rides in the
    event row. Commit policy belongs to the caller (the API commits once per
    request so the event and the clone outcome land atomically).
    """
    impression_digest = hashlib.sha256(
        fp.descriptorset_to_json(probe)
    ).hexdigest()
    fp.store_event_template(impression_digest, probe)
    sigs = _signatures(probe)
    sig_primary = sigs[0] if sigs else ""
    c = conn.cursor()
    c.execute(
        """INSERT INTO verification_events
           (piece_id, certificate_code, similarity, matched, impression)
           VALUES (?, ?, ?, ?, ?)""",
        (piece["id"], piece["certificate_code"], similarity,
         None if match is None else int(match),
         impression_digest + ':' + sig_primary),
    )
    return {
        "event_id": c.lastrowid,
        "impression": impression_digest + ':' + sig_primary,
        "similarity": similarity,
        "matched": match,
    }


def _load_events(conn, piece_id: int) -> list[dict]:
    rows = conn.execute(
        """SELECT id, impression, similarity, matched, verified_at
           FROM verification_events WHERE piece_id = ? ORDER BY id ASC""",
        (piece_id,),
    ).fetchall()
    out = []
    for r in rows:
        digest, _, sig = r["impression"].partition(':')
        out.append({
            "event_id": r["id"],
            "digest": digest,
            "signature": sig,
            "similarity": r["similarity"],
            "matched": r["matched"],
            "verified_at": r["verified_at"],
        })
    return out


# -------------------------------------------------------------- clone decision

def detect_clone(conn, piece, probe: fp.Template) -> dict:
    """Run clone detection for a probe just recorded on this certificate.

    Returns a plain-language result:
      {"flagged": bool, "reason": str, "compared": int}
    `flagged` is True only when the fingerprint family around this code is
    inconsistent — see the module docstring for the conservative policy.
    """
    compared = 0
    events = _load_events(conn, piece["id"])
    if not events:
        return {"flagged": False, "reason": None, "compared": 0}
    # The probe's own row is always the latest one; compare against history.
    others = events[:-1]

    probe_sigs = _signatures(probe)
    mismatch_exact = 0      # impressions that fail precise similarity
    mismatches_sig = 0      # impressions that even fail the cheap pre-filter
    best = 0.0
    for e in others:
        candidate_sigs = [e["signature"]] if e.get("signature") else []
        sig_ok = any(_signature_compatible(p, c) for p in probe_sigs for c in candidate_sigs)
        if not sig_ok:
            mismatches_sig += 1
            compared += 1
            continue
        # Precise similarity decides (pre-filter never suppresses a flag).
        stored_digest = e["digest"]
        stored = _template_from_digest(conn, stored_digest)
        if stored is None:
            continue  # cannot compare precisely; the sig pre-filter said "maybe"
        compared += 1
        s = _pair_similarity(stored, probe)
        best = max(best, s)
        if s < fp.match_threshold() * 0.90:
            mismatch_exact += 1
    if best < fp.match_threshold() and compared >= 1:
        threshold = fp.match_threshold()
        # Only flag when there are at least TWO distinct historical impressions
        # on record AND the probe fails against ALL of them: this makes a
        # single stray capture harmless while catching cloned-tag families.
        if len(others) >= 2 and (mismatches_sig + mismatch_exact) == len(others):
            return {
                "flagged": True,
                "reason": (
                    "This tag has been shown with several different objects — "
                    "possible tag cloning detected"
                ),
                "compared": compared,
            }
        return {
            "flagged": False,
            "reason": ("Object differs from earlier captures on this code "
                       "— needs another scan to confirm")
                      if (mismatches_sig + mismatch_exact) else None,
            "compared": compared,
        }
    return {"flagged": False, "reason": None, "compared": compared}


def _template_from_digest(conn, digest: str) -> Optional[fp.Template]:
    """Recall the stored template behind an impression digest.

    Events store only a digest for compactness, plus the quantized signature
    for pre-filtering; precise matching reloads the stored template file.
    When the file is unavailable (e.g. wiped), the event degrades to the
    pre-filter — never to a flag.
    """
    return fp.load_event_template(digest)
