# CraftProof 2.0 — Research Paper Plan
## Physical–Digital Binding and Cryptographic Provenance for Handmade Goods

| | |
|---|---|
| **Version** | 1.0 |
| **Date** | 7 October 2026 |
| **Status** | Approved execution plan — documentation only; all code work appears as follow-up tasks (Section 10) |
| **Target output** | One research paper (venue decided after the work is solid — Section 17) |
| **Grounding** | Prior-art claims verified via web search on this date; repo state verified by running `backend/test_crypto.py` (12/12 passed) |

---

## 0. How to read this document

This is the complete research protocol for turning CraftProof from a well-engineered student
system into a publishable research contribution. It is written to be **self-contained**: a
reader who has never seen the repository or the earlier discussions can execute it.

**Sequencing rule (agreed with the author):** implement first, publish second. The paper is
written **on the implemented system and its measured results** — no speculative or projected
numbers. Sections 10 and 17 encode that order: engineering work items W1–W8 and experiment
phases P0–P4 come before any write-up (P5).

- Sections 1–3: what exists today, the research gap, and the verified prior art the paper must position against.
- Sections 4–6: research questions, contributions, and the formal threat/attack model.
- Sections 7–9: the proposed system design and the experiment designs (E1–E7) with metrics.
- Sections 10–13: follow-up engineering tasks, dataset logistics, related-work map, paper skeleton.
- Sections 14–17: risks, honest limitations, the patent checkpoint, and the phased timeline.

**One-line thesis.** CraftProof today proves that a *digital* custody history is intact; the
research contribution is binding that history to the *physical object itself* — camera-verified
surface fingerprints committed into the custody chain — so that tag cloning and object
substitution become detectable across the whole ownership lifecycle, under a formal attack
model with externally anchored checkpoints.

---

## 1. Background: what CraftProof is today (verified)

CraftProof is a full-stack web application (FastAPI + SQLite backend, React + Vite frontend)
that lets artisans create digital certificates for handmade pieces and record every custody
transfer. Anyone can scan a QR code on the piece and see the maker, the ownership timeline,
and a "Verified Authentic" badge — no account required.

The cryptographic core (all verified working on this date, `test_crypto.py` 12/12):

| Component | Implementation |
|---|---|
| Custody records | `CustodyRecord` — piece id, seq index, from/to, note, ISO timestamp, `prev_hash`; hashed as SHA-256 over canonical JSON (sorted keys, no whitespace) |
| Hash chain | Each record stores the previous record's `record_hash`; genesis link is `SHA256(b"GENESIS")` |
| Signatures | Ed25519; the **outgoing** custodian signs each record hash (this is what lets buyers participate without accounts) |
| Merkle checkpoints | SHA-256 binary tree over all record hashes, 0x00 leaf / 0x01 node prefixes, odd-node duplication; roots published as numbered checkpoints |
| Verification | Server-side check on `/c/{code}` (content hash, chain linkage, signature per record) + independent offline verifier `verify_cli.py` that trusts no server verdict |
| Attack tests | Edited notes, rewritten buyer names, deleted middle records, forged records with recomputed hashes, Merkle proof rejection, domain-separation checks |

This is a sound integrity layer — well above the typical "blockchain + CRUD + QR" student
project. It is **not**, however, a research contribution yet: hash chains, Ed25519, and Merkle
inclusion proofs are textbook primitives, and the architecture has two structural weaknesses
that are themselves the research opportunity:

1. **The physical–digital gap.** The QR sticker is the *only* link between the object and its
   history. A counterfeiter copies a genuine QR onto a fake object; every cryptographic check
   passes, because the checks verify the *record*, never the *object*.
2. **Self-anchored checkpoints.** The Merkle roots live in the same SQLite database as the
   records they certify. An attacker who controls the database can rewrite history *and*
   rebuild every checkpoint. The system provides tamper **evidence**, not tamper resistance.

---

## 2. The research problem and the gap

**The central research question:**

> How can we determine that the physical handmade object being scanned is actually the same
> physical object whose digital provenance is stored in the system?

Blockchain-based provenance answers "is this certificate genuine and unaltered?" — it cannot
answer "is the object in front of me the one the certificate describes?". For handmade goods
there is a structural advantage no industrial system has: **every handmade object is inherently
unique by construction**. Glaze crazing, tool marks, wood grain, weave irregularities — the
manufacturing process produces unclonable surface structure *for free*, with no added taggant,
chip, or special ink. The gap:

> No published system binds the physical handmade object itself (camera-verified surface
> fingerprint) to a cryptographic custody chain, detects tag cloning and object substitution
> across the ownership lifecycle, supports independent third-party verification, and is
> evaluated under a formal adversary model with an architecture-comparison study.

CraftProof 2.0 claims exactly that gap. The paper's positioning is therefore **not**
"blockchain for handicrafts" (dead — see Section 3) but:

> *A cryptographically verifiable physical–digital binding and chain-of-custody framework for
> counterfeit-resistant handmade goods.*

---

## 3. Verified prior-art foundation

Every claim below was verified by direct search on 7 October 2026. This table is the spine of
the paper's related-work section.

### 3.1 Closest prior art

| # | Prior art | What it covers | Why it does not kill the paper |
|---|---|---|---|
| P1 | **Sensors 2024** — Aounzou, Kalloubi, Boulaalam, *"A Blockchain of Things System for Managing Handcrafted Products in a Cultural Industry"*, Sensors 24(22):7384, DOI 10.3390/s24227384 | Blockchain-of-Things + IoT + handicrafts: authentication, traceability, smart contracts | No physical-object binding; the artifact's identity is still just a tag/QR. No fingerprint verification, no clone detection |
| P2 | **Applied Sciences 2024** — Yi & Moon, *"Secure and Transparent Craftwork Authentication and Transaction System: Integrating Digital Fingerprinting and Blockchain Technologies"*, Applied Sciences 14(19):9054 | "Digital fingerprinting" of craftwork **attributes** + consortium blockchain + smart contracts + QR + buyer verification | Their "fingerprint" is hashed *metadata/attributes* — a string of properties, not camera-verified surface structure. No physical re-verification, no lifecycle clone detection. This is the closest work and must be engaged in detail |
| P3 | **NIT Srinagar Indian patent application (Oct 2021)** — Sofi & Ali, *"Blockchain based Internet of Things (BIoT) Track and Trace system for Saffron and Handicrafts"* | Handicrafts + blockchain + IoT + QR codes + digital certificates + artisan→consumer traceability, permissioned chain | IoT/QR traceability only — it confirms that "blockchain + QR + handicrafts" is **already claimed prior art in India**. Contains no object-identity verification mechanism. (Patent status/claims must be re-checked by an agent before any filing — Section 16) |
| P4 | **Paper-fingerprint / PUF literature** — Toreini et al. 2017 *"Practical Paper Fingerprinting based on Texture Patterns"* (Warwick); *"Counterfeit detection using paper PUF and mobile cameras"*; *"SoK: Fighting Counterfeits with Cyber-Physical Synergy Based on Physically-Unclonable Identifiers of Paper Surface"* (2024); *"A guide for assessing optically imaged physically unclonable functions for authentication"* (Appl. Phys. Rev. 2025) | Camera-readable surface micro-texture as a physically unclonable identifier; paper/label/taggant anti-counterfeiting; evaluation methodology (FAR/FRR, degradation studies) | Targets *paper, labels, and engineered taggants*. Handmade artifacts need **no added material** — uniqueness is inherent to the craft process. P4 supplies the evaluation methodology we will follow, not the application |

### 3.2 Additional related anchors (context for Section 12)

Certificate Transparency (RFC 6962) for transparency-log patterns; W3C PROV for provenance data
models; USENIX Security '25 *"Scanned and Scammed: Insecurity by ObsQRity?"* (Kowalewski et al.)
for QR trust user studies; Cordeiro et al. 2025 blockchain wine-traceability with QR verification
(user study); IEEE 2025 NFT + NFC handicraft work (Sri Lanka); Hyperledger + IPFS batik/weaving
authentication (2025); blockchain + IoT + QR for Indian apparel MSMEs (2026).

### 3.3 Claims that are already dead (do not use these as contributions)

Confirmed saturated by the sources above — adding any of these would *weaken* the paper:

- ❌ "Blockchain for handmade/handicraft authentication" (P1, P3)
- ❌ "QR code links physical product to digital record" (P1, P2, P3)
- ❌ NFT as certificate of authenticity (IEEE 2025 NFT+NFC handicrafts)
- ❌ Hyperledger / IPFS / IoT-sensor traceability (P1; batik 2025; apparel 2026)
- ❌ "Hash the attributes of the craft as a fingerprint" (P2 does this)

---

## 4. Research questions and hypotheses

| # | Research question | Hypothesis (measurable) | Answered by |
|---|---|---|---|
| **RQ1** | Does adding physical-fingerprint binding significantly reduce successful counterfeit acceptance compared with QR-only and QR+crypto systems? | **H1:** Under attacks F–H (QR cloning, tag substitution, object substitution), the full system's attack-detection rate is strictly higher than architectures A/B/C's — the fingerprint layer is what catches what pure provenance cannot | E1, E4 |
| **RQ2** | How robust is camera-based object-fingerprint matching under realistic image degradation? | **H2:** Same-object matching keeps AUC ≥ 0.95 under the full synthetic degradation grid, while reject-level drops for impostor pairs stay ≤ 5% | E2, E3 |
| **RQ3** | What does external checkpoint anchoring (RFC 3161 TSA / OpenTimestamps) add in trust, and at what cost? | **H3:** Architecture D defeats attack I (checkpoint rewriting) where architecture C does not, for a bounded per-checkpoint cost and latency overhead | E1, E5, E6 |
| **RQ4** | How does the system scale (registration, verification, checkpointing)? | **H4:** Verification latency stays O(log n) in record count via Merkle proofs; registration stays O(1); checkpoint cost grows sub-linearly | E5, E6 |

Hypothesis-testing note: H1/H3 are comparative claims against explicitly built baselines
(architectures A–D, Section 8) — not vibes. H2's threshold is a design target; if it fails,
the paper reports the failure and the operating-point analysis honestly (Section 14).

---

## 5. Contributions (each mapped to evidence)

| # | Contribution | Novel vs prior art | Evidence |
|---|---|---|---|
| 1 | Formal adversary model and a 10-attack matrix (A database edit … J replay) spanning digital, physical, and cross-layer attacks | Cross-layer attack taxonomy not present in P1/P2/P3 | E1 |
| 2 | Four-architecture comparative evaluation: plain DB → hash chain → + Ed25519/Merkle (today's CraftProof) → + external anchor | Architectures C/D evaluated against the physical attacks they *cannot* catch — showing provenance systems' blind spot | E1 |
| 3 | Multimodal physical-fingerprint binding protocol: classical-CV descriptors (pHash, ORB, color/texture) with a cryptographic commitment bound into the **genesis custody record** | P2 hashes attributes; P4 fingerprints paper/tags. Nobody commits *object-surface* features into a custody chain for handmade goods | E2, E3, E4 |
| 4 | Clone / tag-substitution detection across the ownership lifecycle (one genuine QR mounted on K counterfeits; substitution mid-lifecycle) | New — no prior system detects that one certificate matches K objects | E4 |
| 5 | External anchoring of Merkle checkpoints (RFC 3161 TSA / OpenTimestamps) + scalability study | Anchoring pattern is known (transparency logs); the *evaluation in this domain* (four architectures, A–J, 1k→1M records) is new | E5, E6 |
| 6 | Independent third-party verification retained and formalized as a design property (verify_cli path) | Design contribution — reuse of a transparency-log property in this domain | E1 |

**Bar to clear:** whichever single contribution turns out weakest after experiments (likely #4
if fingerprint accuracy disappoints, or #3 if the commitment binding becomes trivial), the
paper's claims are cut to what the data supports. See Section 14 for the failure branches.

---

## 6. Formal adversary model and the 10-attack matrix

### 6.1 Assets and trust boundaries

**Assets:** custody records (window into provenance); signer private keys; the Merkle
checkpoint roots; the physical↔digital link (the QR tag); the physical object's surface.

**Boundaries:** (i) the application server + database — inside boundary **B1**;
(ii) trusted timestamping / external anchor — boundary **B2**; (iii) every mobile device and
every person — **B3**, untrusted; (iv) the physical world — **B4**, untrusted.

### 6.2 Adversary archetypes

| ID | Archetype | Capabilities | Can be inside? |
|---|---|---|---|
| A1 | Dishonest insider (DBA, employee) | Read/write DB, restart services | B1 |
| A2 | Full server compromise | As A1 + keys, code | B1 |
| A3 | Counterfeiter (physical) | No DB access. Copies tags, manufactures fakes, resells | B4 |
| A4 | Malicious custodian (rogue maker/seller) | Valid account + keys. Records false transfers, re-registers own pieces | B3 |
| A5 | Colluding distributor | A3 + one genuine article: clones its tag onto K fakes | B4 |
| A6 | Replay adversary | Captures a valid proof/verification transcript, re-presents it later | B3 |

Time bound on verification: an adversary can only poison the *latched* state — records sealed
into an anchored checkpoint cannot be rewritten without breaking B2's evidence.

### 6.3 The 10-attack matrix

| ID | Attack | Adversary | Description (what the system must catch or tolerate) |
|---|---|---|---|
| A | Database edit | A1 | MODIFY a record field (note, buyer, description) without touching hashes |
| B | Ownership rewriting | A1/A2 | Replace the recorded owner / insert a plausible-but-false transfer path |
| C | Record deletion | A1/A2 | DELETE a middle custody record, breaking the chain deliberately or not |
| D | Record insertion | A1/A2 | INSERT a fabricated custody event with correct linkage into the chain |
| E | Signature forgery | A2 | Re-sign a modified record with a key the attacker DOES hold (e.g. compromised server keys, or as rogue custodian A4) |
| F | QR cloning | A5 | Copy the genuine QR/certificate onto K counterfeit objects |
| G | Tag substitution | A3 | Swap the original tag to a different object (or replace tag entirely) |
| H | Object substitution | A3/A5 | The right tag + the WRONG physical object — QR passes, provenance passes, object is fake |
| I | Checkpoint rewriting | A2 | Compromise DB, rebuild records AND recompute all Merkle roots / batches |
| J | Replay | A6 | Re-verify with a captured old (valid) proof / re-serve stale but valid data |

### 6.4 Expected defense matrix (pre-registered predictions — the paper reports hits and misses)

Attacks A–D are the ones today's CraftProof already catches (content hash, linkage, signature
as independent checks, verified live in test_crypto.py). E fails only against keys the
attacker does hold. F, G, H are **not caught today by any of architectures A/B/C** — that is
the paper's core empirical claim. I is caught only after architecture D (external anchor).
J requires freshness defense (anchoring timestamps + fingerprint liveness). The defense
matrix table is filled from E1's actual results, not from this pre-registration.

---

## 7. Proposed system: CraftProof 2.0 architecture

Two layers exist today and are kept as-is (contribution #6 depends on their stability):

1. **Cryptographic provenance layer** — existing custody chain, Ed25519 signatures, Merkle
 checkpoints, independent verifier.
2. **Verification UX** — QR → public certificate page; plain-language; no account for buyers.

Three layers are new:

3. **Physical-fingerprint layer (contribution #3).** At registration, capture N images of the
 object under a short checklist (Section 11). Extract descriptors:
 - Global perceptual: pHash + dHash on a masked, perspective-normalized crop.
 - Local/structural: ORB keypoints + descriptors with handcrafted ratio-test matching.
 - Appearance: HSV color histogram (3D); optionally LBP texture histogram (linear or ROR).
 - All classical CV (OpenCV + Python), chosen deliberately: no training data needed beyond
 the enrolled images, no GPU, fully reproducible, and FAR/FRR trade-offs are explicit.
 The enrolled fingerprint = per-descriptor stats (e.g. medians across the N images).
 The **commitment** `C = SHA256(canonical_json(descriptor_summary))` is stored in the piece
 record and bound into the genesis custody record — so the commitment itself is signed as
 part of the chain.
4. **Ownership-aware verification (contribution #4).** Where current accounts exist
 (maker/seller), the new app records a **verification event**: timestamp, verifier-side
 geo-time hints (coarse), code, fingerprint match score. Every subsequent pairing of
 (code, fingerprint) searches all previous events for the same certificate code with a
 mismatching fingerprint. If found: **POSSIBLE TAG CLONING / OBJECT SUBSTITUTION** — surface
 to the buyer as a red banner on the certificate page.
5. **External-anchor layer (contribution #5).** Checkpoint roots are batched daily and
 anchored to (a) an RFC 3161 TSA and (b) OpenTimestamps (aggregates through Bitcoin's block
 headers — storage cost ≈ 0). Architecture D = C + this layer.

### 7.1 The user-facing decision flow

QR scan first (zero friction, as today). Then, **optionally after three challenges**
(intent only — jargon-free prompts): "Is the object in front of you the one on the tag? Yes →
snap N photos following the guide." No camera / no consent / low light → fall back to the
current certificate-only verdict, explicitly labelled as "history verified; object
auto-verified". Final score is always presented with the four-layer scorecard shown to the
user (provenance / fingerprint / deference-to-fallback / optional liveness).

### 7.2 Design constraints carried over from CraftProof v1

- No account for buyers. No jargon on the buyer side (use shorthand, not "Merkle proof").
- Verification and registration paths stay separate — registration is the only fingerprint
 enrollment point (no re-enrollment: custody history is signed over the snapshot).
- Independent verification (verify_cli path) must keep working — it now also needs a
 fingerprint-comparison operation available offline, so the fingerprint format is
 exported in the /c/{code}/proof payload.
- Falsifiability: every layer has an explicit failure mode and a user-visible fallback.

---

## 8. Four-architecture comparison (evaluation frame)

All four run on the same dataset and the same attack harness (W2, Section 10). Only the
integrity/anchor stack differs. The physical-fingerprint and clone-detection layers are
**architectural variants**, not baselines — they are measured as system variants (D vs D+
fingerbinding) so the marginal value of each layer is isolated.

| ID | Stack | What it defends | What it cannot do |
|---|---|---|---|
| A | Plain DB (FastAPI + SQLite, same schema, no crypto beyond auth) | Nothing — attacker rewrites any column | Everything |
| B | A + hash chain (prev_hash linkage, no signatures, no Merkle, no anchor) | Detects content edits (A) unless attacker recomputes; detects some order operations | Catches E (any valid signature forgery with attacker keys) doesn't apply here; no Merkle → no exclusion / portfolio proofs; no anchor → fatal to I (checkpoint rewrite = recompute chain, and no anchor to contradict it) |
| C | B + Ed25519 signatures per record (outgoing custodian) + Merkle checkpointing — **this is today's CraftProof** | Defends A–D (via hash + signature + linkage); partial E (only if attacker lacks keys); catches checkpoint rebuild only if roots are published externally — which they are NOT in v1 | F/G/H not caught (no object verification); I caught only partially (attacker controls root storage); J not addressed |
| D | C + RFC 3161 TSA / OpenTimestamps anchoring of checkpoint roots | Everything C does plus: I is caught for latched state (an attacker cannot rewrite anchored roots without breaking the TSA/OTS evidence); J partially addressed via anchor freshness | Still cannot catch F/G/H — the object's physical identity never enters the loop. **This is the paper's key insight: anchoring solves the digital trust problem but not the physical–digital binding one** |

The fingerprint layer (Section 7, layer 3) is then evaluated as an architectural variant of D
(D+fingerprint). Expected results R1 (filled from E1/E4, NOT pre-written):

| ID | A | B | C | D | D+fingerprint |
|---|---|---|---|---|---|
| Attack A (DB edit) | ✗ | ✓ | ✓ | ✓ | ✓ |
| Attack B (ownership rewrite) | ✗ | ✗/partial* | ✓ | ✓ | ✓ |
| Attack C (record deletion) | ✗ | ✓ | ✓ | ✓ | ✓ |
| Attack D (record insertion) | ✗ | ✗/partial | ✓ | ✓ | ✓ |
| Attack E (signature forgery w/ attacker keys) | ✗ | ✗ | ✗ | ✗ | ✗ (physical layer does not help here) |
| Attack F (QR cloning on K counterfeits) | ✗ | ✗ | ✗ | ✗ | ✓ (clone detection — Section E4) |
| Attack G (tag substitution) | ✗ | ✗ | ✗ | ✗ | ✓ (fingerprint mismatch) |
| Attack H (object substitution) | ✗ | ✗ | ✗ | ✗ | ✓ (fingerprint mismatch) |
| Attack I (checkpoint rewriting) | ✗ | ✗ | partial (needs out-of-band root copy) | ✓ (external anchor disagrees) | ✓ |
| Attack J (replay / stale proof) | ✗ | ✗ | ✗ | partial (freshness via TSA/OTS timestamps) | partial → tightest with fingerprint liveness |

*B's partial catches are those the attacker's recompute-step doesn't perfectly replicate
(specified in W2); the point of the row is to show B is a weak but non-zero defence.

---

## 9. Experiment designs (E1–E7)

All experiments run on the same physical machine (laptop-class), same Python version, same
OpenCV version, fixed random seeds — reproducibility instructions are part of the deliverable
(Sec 13). Metrics definitions follow the PUF literature (P4) for comparability.

### 9.1 E1 — Attack-matrix execution across the four architectures

**Purpose:** fill the defense matrix in Section 8 from real execution, not prediction.
**Procedure:** the W2 harness (Section 10) replays attacks A–J against each architecture's
dockerized instance, with N=30 randomized repetitions per (architecture, attack) cell. Each
repetition logs: detected y/n, detection layer (hash / linkage / signature / inclusion /
anchor / fingerprint), detection latency, and the user-visible verdict text.
**Metrics:** detection rate per cell; attack-detection-distribution; veracity table for
architectures A, B, C, D, D+fp (as the fifth column);
cross-layer detection attribution (which of A–D each architecture catches).
**Scale:** all four architectures run the full 10-attack suite per repetition.
**Expected runtime:** minutes per (arch, attack) pair — bounded, batches overnight.

### 9.2 E2 — Fingerprint matching on the photo-only dataset

**Purpose:** establish same-object vs different-object separability for the descriptors in
Section 7, using only ordinary photos (constraint: no controlled re-capture — Section 14).
**Data:** same-object pairs photograph pairs of the SAME object from various sources —
marketplace multi-photo listings of the same item, photos the author/colleagues consented to,
CC-licensed ecommerce photo pairs; impostor pairs: photos of DIFFERENT objects. No scraping —
**ethics in Section 11**. Target ≥ 150 same-object pairs, ≥ 400 impostor pairs, ≥ 60 distinct objects.
**Procedure:** for each pair, compute log-polar similarity per descriptor; record scores.
**Metrics:** ROC curve + AUC per descriptor and for the fused score; FAR/FRR curves; EER; and FPR@FRR = 10% (the FPR at the operating point where FRR is fixed at 10% — what a buyer actually feels); distribution histograms.
**Pass condition:** AUC ≥ 0.95 fused; else Section 14 branch B.

### 9.3 E3 — Synthetic degradation robustness

**Purpose:** simulate realistic capture variation and quantify which degradations dominate
loss. This EXPLICITLY does not replace controlled re-capture — that's Section 14's limitation L1.
**Procedure:** each enrolled image is degraded per grid: JPEG quality (90, 75, 60, 40),
rotation (±5°, ±15°, ±45°), scale (0.8×, 1.2×), brightness/contrast jitter, Gaussian noise,
crop (90%, 80%), blur. Each cell: recompute similarity to enrolment; track AUC/FPR@FRR=10 per cell.
**Metrics:** heat map of AUC across grid cells, identifying the fragile axes; a robustness
ranking per descriptor. Reporting: the fused descriptor's sensitivity profile.
**Pass condition:** AUC ≥ 0.95 in the central cells' tolerance; else Section 14 branch C.

### 9.4 E4 — Clone and substitution detection (the flagship experiment)

**Purpose:** measure the system's ability to catch three physical attack families in Section
6.3: F (one cert, K fakes), G (tag swap), H (wrong object, right tag).
**Procedure:**
- Simulate: M certificates over M registered objects. For each certificate, generate K
 counterfeit-scan events: either (a) impostor fingerprints paired with the same code, or
 (b) genuine fingerprints paired off-code (substitution). The verification pipeline runs the
 full scorecard logic each time.
- Metrics: clone-detection rate as a function of K (does the 2nd, 5th, 10th clone get caught?);
 false-flag rate on the genuine object's own re-scans (which must NOT flag); attribution latency
 (events elapsed before each flag); per-descriptor and fused.
- **Pass condition:** clone detection ≥ 90% by the 3rd counterfeit event; false-flag rate on
 genuine re-scan ≤ 5%. else Section 14 branch A (report the operating-point curve honestly).

### 9.5 E5 — Latency and proof-size benchmarks (per operation, per architecture)

**Ops:** piece registration, custody transfer, certificate page render, fingerprint enrol,
fingerprint verify, checkpoint build, anchor publish, independent-verify.
**Metrics:** p50/p95/p99 latency per operation (wall time, server-side; mobile-side where
relevant), CPU time, payload size (esp. /c/{code}/proof size for offline verification).
Compare D vs D+fp specifically to isolate the perceptual verification cost.

### 9.6 E6 — Scalability and checkpoint cost

**Purpose:** RQ4's answer. Fill the database with 1k, 10k, 100k, 1M records (synthetic
custody generators, seeded). For each size: certificate page render (worst-case piece at
tail of chain), Merkle proof size/path length, checkpoint build time and root size,
anchor publish cost (TSA round-trip, OTS batching), fingerprint lookup (index-dependent —
SQLite FTS vs linear scan as ablation).
**Metrics:** as above, per size tier; growth curves per metric fitted and reported.
### 9.7 E7 — Offline verification (STRETCH — cut if the core is at risk)

**Purpose:** in artisan environments, connectivity is intermittent. Some verification
(signal: key + checkpoint proof + fingerprint template) could run entirely offline.
**Design variant:** QR payload rotates to embed a compressed proof. Cost: less room for scan
robustness, longer URLs break native camera behaviour — measure扫码 success additionally.
**Metrics:** offline verification success rate vs data availability; QR payload size vs
camera-scan success on 3 real phone models.
**WARNING:** this experiment is scope-creep risk #1 and is cut FIRST (Section 15) if
E2/E4 results are weak — a paper about fingerprint binding must not have a half-done
offline add-on crowding its evaluation section.

---

## 10. Follow-up engineering work items (code comes in later threads — not now)

This document creates **zero code changes**. The following list is what later threads will
implement, in dependency order. Each item names the experiments it unblocks.

| ID | Work item | Unblocks | Notes / acceptance |
|---|---|---|---|
| **W1** | **Security fixes (do first, required before any public paper)** | all | (a) Private keys stored raw under `encrypted_privkey`: replace with password-derived AES-GCM envelope (PBKDF2/Argon2id → AES-GCM, in `crypto_utils.py` / `main.py` / `seed.py`). (b) Hardcoded JWT `SECRET_KEY` in `auth.py`: move to env var with fail-fast startup check. (c) Replace "tamper-proof" wording with "tamper-evident" across README/UI/how-it-works — reviewers will check this. (d) `/admin/tamper` endpoint: bind to admin auth or remove from deployed builds. Acceptance: `pytest`-style suite extended; no regressions; `verify_cli.py` still passes on migrated DB. |
| W2 | Attack harness (`experiments/harness.py`) | E1 | Parameterized A–J attacks against any of architectures A–D; docker/composeProfiles per architecture; machine-readable JSON results (cell = arch × attack × repetition); deterministic seeds. Acceptance: reproduce test_crypto.py's existing 12 test behaviors as a strict subset. |
| W3 | Fingerprint module (`backend/fingerprint.py`) | E2, E3, E4 | pHash + dHash + ORB + 3D color histogram + optional LBP; canonical descriptor serialization; deterministic augmentation pipeline (Pillow/OpenCV transforms with seeds). Acceptance: unit tests — descriptor determinism, correct reject on impostor pairs, score range invariants. |
| W4 | Fingerprint commitment binding | E1, E4 | Add `fingerprint_commitment` column + include in genesis `CustodyRecord` signed fields; migration for existing DBs; verify_cli extended. Acceptance: commitment change detected as record tampering by the existing tests' approach. |
| W5 | Clone-detection service + certificate-page scorecard | E4 | verification-event log table; same-code cross-check on each verification; UI: red banner + plain-language wording; no jargon. Acceptance: simulated F/G/H events surface correctly on `/c/{code}`; false-flag behavior defined. |
| W6 | Anchoring worker | E5, E6 | Periodic MERKLE-root batching; RFC 3161 client (stdlib `urllib` or `pycryptodome`); OpenTimestamps client; store receipts in a new `anchored_checkpoints` table. Acceptance: a fresh receipt validates against its root offline. |
| W7 | Benchmark + scaling generator | E5, E6 | Synthetic custody generator (seeded); perf logging to CSV; plotting scripts. Acceptance: one command runs the full E5/E6 matrix and produces machine-readable + human-readable output. |
| W8 | Dataset collection kit | E2 | Photography checklist (5 shots: front, back, two obliques, macro of a distinctive area), naming scheme, consent form template, labeling CSV. Acceptance: a non-expert can run it; no ToS-violating scraping anywhere in the pipeline. |

Dependency order: **W1 → W2 → W3 → W4 → W5 → W6 → W7 → W8** (W8 parallelizes anytime after W3; W7 after W6).

---

## 11. Dataset and ethics (E2's physical-photo constraint)

The author cannot do controlled re-capture photography (same object, multiple controlled
sessions). The design accepts this:

**Accepted data sources**
1. Objects the author or consenting colleagues own; photographed from existing images or
 re-shot casually (no lighting booth).
2. Marketplace listing photos where the SAME object appears in multiple images (the
 same-object pair is the listing's own presentation of one item).
3. CC-licensed / public-domain photo sets of distinct handmade objects (impostor universe).

**Hard rules (no exceptions)**
- Never scrape in violation of a site's ToS; not in an automated or bulk way.
- No faces; no personally identifiable properties; images stored author-locally for the
 duration of the study; not redistributed.
- Every image the author did not take gets a labeled source + license in the dataset CSV.
- Marketplace images: use only for research deformation robustness study, not republished in
 the paper; figures use author-owned and synthetic images only.

**Structure** / `experiments/data/manifest.csv`: `object_id, image_path, capture_source,
license, consent, capture_context{device, environment}` and augmentation lineage columns.

**Quality bar:** ≥ 60 distinct objects; ≥ 150 same-object pairs; ≥ 400 impostor pairs.
Below this, report the dataset as a pilot (limitation L2) rather than a definitive bench.

---

## 12. Related-work map (paper §2 skeleton)

Organized as five narrative threads, each ending at the gap this paper fills:

1. **Blockchain provenance for physical goods** — P1 (Sensors 2024 handicrafts); wine
 traceability (Cordeiro 2025); Indian apparel MSMEs (2026); batik (2025). *End:* none verify
 the object itself.
2. **Cryptographic + fingerprinting authentication for craftwork** — P2 (Applied Sciences
 2024). *End:* fingerprints are hashed attributes, not camera-verified surfaces; no lifecycle
 detection.
3. **Physically unclonable identifiers** — P4: paper-fingerprint (Toreini 2017), paper PUF +
 mobile cameras, SoK 2024, Ricker et al. (APR 2025) methodology. *End:* engineered tags/
 paper, never the artifact itself, never integrated with provenance.
4. **Transparency and independently verifiable logs** — RFC 6962 / Certificate Transparency,
 RFC 3161 TSA, OpenTimestamps. *End:* anchoring patterns exist; not bound to physical objects.
5. **Usable authentication & QR-trust** — Kowalewski et al. (USENIX Sec '25 QR-phishing),
 wine QR user study (Cordeiro 2025 user study), W3C PROV. *End:* QR trust gap is documented;
 no work ties it to artifact-level verification.

Each paragraph ends: "CraftProof 2.0 differs by …", so the related-work section actively
funnels into the gap statement from Section 2.

---

## 13. Paper skeleton (draft when results exist, not before)

**Working titles (choose close to submission):**
- Primary: *CraftProof: A Cryptographically Verifiable Physical–Digital Binding Framework for Authenticating Handmade Goods*
- Alt: *Binding Provenance to the Object: Camera-Verified Surface Fingerprints over a Signed
Chain-of-Custody for Handmade Goods*
- Alt (if H1 is weakened but H2 stands): *Fingerprint-Bound Custody Chains: Detecting
Counterfeit Tag Cloning in Handmade Goods*

**Format:** IEEE conference (6–8 pages) unless the author later chooses a journal (extended,
then add E7 and a more complete robustness study).

Sections (with page budget):
1. Introduction (0.75p) — counterfeiting in the craft sector; the certificate that can be
 detached from its object; contributions C1–C6.
2. Related work (1.0p) — the five threads of Section 12.
3. System design (1.5p) — Fig. 1: eight-layer architecture (Section 7); protocol figures for
 fingerprint enrolment-bound custody records; Fig. for clone detection flow.
4. Threat model (0.75p) — archetypes + the 10-attack matrix (Section 6).
5. Implementation (0.5p) — FastAPI/SQLite/OpenCV; stack table; independent verifier.
6. Evaluation (2.5–3p) — E1 defense matrix table (headline); E2 ROC figures; E3 degradation
 heat map; E4 clone curves; E5/E6 benchmark and scaling tables. Every table/figure captioned
 from *real* results.
7. Discussion & limitations (0.5p) — Section 14 verbatim distilled; honest fallback behavior.
8. Conclusion & future work (0.25p).

**Figures/tables plan (10–12 total):** architecture; enrollment protocol; verification
decision flow; defense-matrix table; ROC curves (E2); degradation heat map (E3); clone
rate vs K curve (E4); latency CDFs (E5); scaling table (E6); anchoring comparison (E5/E6);
scorecard mock; dataset sample grid.

<b>Reproducibility artifact</b>: code (MIT, consistent with the repo), harness configs,
seeds, and (where licenses allow) the dataset manifest — bundled in a repository + DOI/ Zenodo.

---

## 14. Risks, honest limitations, and failure branches

### 14.1 Known limitations stated IN the paper (not hidden)

- **L1 (permanent):** no controlled re-capture. E3 is synthetic degradation over ordinary
 photos; lighting/angle/perspective variation from real re-photography is only partially
 covered. The paper says this in the abstract-adjacent limitations block, not in a footnote.
- **L2:** dataset size is bounded by consent/licensed sources; reported as a pilot if under
 the Section 11 quality bar.
- **L3:** enrollment photos are taken once at craft-guild time; the protocol does not support
 re-enrollment mid-lifecycle (custody history already signed). Wear-and-tear robustness is
 measurable only via E3's synthetic wear proxies.
- **L4:** clone detection relies on the counterfeit objects being photo-enrollable. If the
 counterfeiter never sets up the certificate, the flag emerges from subsequent mismatching
 scans (Section 9.4) — the paper defines which of those paths work.
- **L5:** scale claims are laptop-class, not production-distributed.
- **L6:** anchoring adds external trust dependencies (TSA, Bitcoin aggregation); the paper
 states these dependence chains plainly.
- **L7:** fingerprint enroll/verify is a computer-vision similarity system with imperfect
 FPR@FRR=10 ≠ 0. The certificate page ALWAYS offers the cryptographic verdict separately
 from the physical verdict; they are presented as distinct signals, never merged into one
 opaque number for the buyer.
- **L8:** no user study in this paper (deferred); the UX claims are design-level, not measured.

### 14.2 Failure branches (pre-committed, so results can't be soft-pedaled)

| Branch | Trigger | Paper response |
|---|---|---|
| **BR-A** | E4 clone-detection ≥ 90% NOT reached by 3rd clone, or false-flags > 5% | Report the operating-point curve; re-frame paper on the detection-vs-false-flag trade-off; title shifts to the fingerprint operating-point analysis; do NOT oversell |
| **BR-B** | E2 fused AUC < 0.95 | Drop the fingerprint as authentication; reframe as *fingerprint-assisted advisory*; contributions re-scoped to architecture evaluation + clone-detection framework; very likely venue-downgrade or journal re-target |
| **BR-C** | E3 shows catastrophic fragility (e.g. AUC < 0.90 at ≥ half of grid cells) | Same as BR-B, with the degradation study as the headline contribution (negative-results framing is publishable; honesty > stretch) |
| **BR-D** | E6 scaling worse than O(log n) proof growth (e.g. checkpoint build blows up) | Anchor the numbers; contribution #5 becomes "practical only under batching strategy X"; batch strategy becomes a contribution |
| **BR-E** | Patent search (Section 16) finds the fingerprint-commitment mechanism already claimed | Drop contribution #3 IP claims; keep the paper if experiments stand (a published implementation is still a contribution); refund the patent route |

### 14.3 Project risks (management, not paper content)

- **Scope creep:** E7 is the designated cut; W7 before W6 is prohibited; W8 parallelizes.
- **Single-person throughput:** each phase has a "thin publishable core" defined below
 (Section 17) so a minimum paper exists even if stretch items die.
- **Dataset availability:** if consenting/licensed sources fall short of the bar, cut to the
 pilot framing (L2) rather than scraping.
- **Reproducibility risk:** every experiment commits seeds and configs (Section 9);
 no "it worked on my machine" reporting.

---

## 15. Phased timeline (quality-driven, no fixed dates)

| Phase | Work | Exit criterion (hard gate) |
|---|---|---|
| **P0** | W1 security fixes; wording audit ("tamper-evident") | All W1 acceptance items pass; repo tests green |
| **P1** | W2 harness + architecture containers | E1 harness reproduces the 12-test subset; runs end-to-end on arch A and C |
| **P2** | W3 fingerprint module + W8 dataset kit; dataset collection | E2 dataset assembled to ≥ quality bar or honest pilot; unit tests pass |
| **P3** | W4 commitment binding + W5 clone service + W6 anchoring | E4's wiring present; receipt validation passing; E2/E3/E4 runnable end-to-end |
| **P4** | W7 benchmarks; run E1–E6; RESULT FREEZE | All result tables/figures generated from committed configs+seeds; no more touching experiments after freeze |
| **P5** | Paper write-up (Section 13) from frozen results only | Full draft with every cited number traceable to a committed result file |
| **P6** | Patent checkpoint (Section 16) BEFORE submission | Written go/no-go decision; if go: provisional filed prior to any public upload |
| **P7** | Venue selection + submission + (if accepted) camera-ready with DOI/artifact link | Per venue rules; artifact bundle published simultaneously |

Minimum publishable core (if time/energy runs out): P0 + W2 + E1 on architectures A–C +
a pilot-quality E2 → a short paper on the defense-matrix evaluation with honest
limitations. This core alone is a legitimate contribution (Section 13's alternative title).

---

## 16. Patent-reassessment checkpoint (pre-disclosure gate)

**Standing agreement with the author:** the paper is the primary goal; patent protection is a
secondary option. Before ANY public disclosure of the genuinely new mechanism
(fingerprint-commitment binding + lifecycle clone detection), reassess patentability and, if
warranted, file an **Indian provisional** (complete specification due within 12 months; the
application is ordinarily published after 18 months).

### 16.1 Disclosure-sensitive components (do NOT expose before the checkpoint)

1. The exact fingerprint-commitment construction and its binding into the genesis custody
 record (W4's schema change).
2. The lifecycle clone-detection rule (W5's cross-verification logic + flagging policy).
3. Any novel composing of the fingerprint layer with the anchoring layer for freshness
defense (the J-attack tightening, if E7 or D+fp results show a defensible mechanism).

Everything else — the existing repo, architecture descriptions, threat model, and evaluation
methodology — is already public/intended-public and is fine to publish.

### 16.2 Procedure at P6 (before submitting the camera-ready anywhere)

1. Commission a **claim-level prior-art search** from an Indian patent agent (Google Patents,
 WIPO, Indian IPO, IEEE/Springer/ACM literature). Carried-over known art to re-check: the
 NIT Srinagar application (P3) and P2.
2. Written go/no-go against Indian patentability: novelty, inventive step (technical effect
 under the 2025 CRI Guidelines), industrial applicability, §3(k) exclusions — the
 physical-binding mechanism is deliberately framed as a *technical* contribution precisely
 because 3(k) is the recurring hurdle for software claims.
3. If GO: file the provisional BEFORE the paper's public upload (preprint, camera-ready, or
 public repo push of W4/W5 code).
4. If NO-GO: publish openly; discontinue the patent route permanently (BR-E).

### 16.3 Standing caution

The current CraftProof implementation is already public on GitHub — treat it as prior art
against itself, exactly as the earlier analysis concluded. The patent conversation is about
the NEW mechanism only, and the decision happens at P6, not now. Nothing in this document
constitutes a legal opinion.

---

## 17. Venue selection (decided after results, not before)

Per the author's direction: make the work genuinely strong first, then choose. The decision
points below are ranked by what the frozen results will support.

| Results profile | Realistic venue class |
|---|---|
| H1 strong + feasible H2 + anchored E1 matrix + decent E4 curves | IEEE conference (security/applied computing tracks; Scopus-indexed IEEE conf.), or applied-crypto journal |
| BR-A/BR-B path (trade-off paper) | Workshop / national conference; possibly a demonstrated-systems track |
| Exceptional results across E1/E4/E6 | Higher-tier venue (e.g., ACISP, ESORICS SAMM/workshops, Computers & Security) — the author is on no deadline, so aiming there costs nothing except patience |

Submission mechanics at P7: dual-use check of repo (public already, fine), artifact bundle
(Zenodo DOI), author-profile hygiene, conflict-of-interest statement (none), and the P6
patent decision MUST precede any of these.

---

## 18. Section-checklist against the approved plan (completeness audit)

| Approved-plan item | Delivered in |
|---|---|
| One execution-ready document at repo root, no code changes | This file, root of the outer workspace; zero code touched |
| Verified prior-art table with why-doesn't-kill column | §3.1 (P1–P4, all live-search-verified 2026-10-07) |
| RQ1–RQ4 | §4 (with H1–H4 and answered-by mapping) |
| Six contributions each mapped to an experiment | §5 |
| Formal adversary model + 10-attack matrix | §6 (A1–A6 archetypes; attacks A–J) |
| Experiment designs under photos-only constraint | §9 (E1–E7; E2 dataset+ethics §11; E3 synthetic; E4 K-counterfeits; E5 architecture comparison incl. RFC 3161/OTS; §9.6 1k→1M) |
| Metrics: ROC/AUC, FAR/FRR, EER, detection rates | §9.2–§9.4, §10 (per experiment) |
| Honest limitations (no controlled re-capture) | §14.1 (L1–L8) + failure branches §14.2 |
| Timeline | §15 (P0–P7, quality-driven) |
| Patent checkpoint before public disclosure | §16 (16.1–16.3) |
| Security fixes flagged as follow-up work | §10 W1 (keys, JWT secret, wording, admin endpoint) |
| Code work items listed inside the document | §10 (W1–W8 with dependency order) |
| Self-contained for a context-free reader | §0 + §1 background + inline cross-refs |

---

## Appendix A — Reference list (as cited in this document)

1. Aounzou Y., Kalloubi F., Boulaalam A. *A Blockchain of Things System for Managing
 Handcrafted Products in a Cultural Industry.* Sensors 24(22):7384, 2024. DOI 10.3390/s24227384.
2. Yi J.H., Moon J. *Secure and Transparent Craftwork Authentication and Transaction System:
 Integrating Digital Fingerprinting and Blockchain Technologies.* Applied Sciences
 14(19):9054, 2024.
3. Sofi S.A., Ali J. *Blockchain based Internet of Things (BIoT) Track and Trace system for
 Saffron and Handicrafts.* Indian patent application, filed 6 Oct 2021 (NIT Srinagar).
4. Toreini E., et al. *Practical Paper Fingerprinting based on Texture Patterns.* 2017.
5. Wong et al. *Counterfeit detection using paper PUF and mobile cameras.*
6. *SoK: Fighting Counterfeits with Cyber-Physical Synergy Based on Physically-Unclonable
 Identifiers of Paper Surface.* 2024.
7. Ricker et al. *A guide for assessing optically imaged physically unclonable functions for
 authentication.* Applied Physics Reviews 12(2), 2025.
8. Kowalewski M., et al. *Scanned and Scammed: Insecurity by ObsQRity?* USENIX Security 2025.
9. Cordeiro M., et al. *Blockchain-Powered Traceability in the Wine Industry.* 2025.
10. RFC 6962 (Certificate Transparency); RFC 3161 (TSP timestamp protocol); OpenTimestamps.
11. W3C PROV-DM / PROV-O provenance data model.
12. Government of India, CGPDTM. *Guidelines for Examination of Computer Related Inventions
 (CRIs), 2025* — for the §16 patent framing; not a research citation.

*Sequencing reminder (author's own words): implement first, then write the paper on the
work — Sections 10 and 15 encode that order, and every number in the final paper must trace
to a committed experiment artifact from P4.*
