# CraftProof — Authenticity Tracking for Handmade Goods

CraftProof lets artisans issue tamper-evident digital certificates for their handmade pieces and
records every change of custody. Python/FastAPI on the back end, React + Vite on the front end,
SQLite for storage.

This repository holds the **research and planning material**. The application itself lives in its
own repository, checked out here as `craftproof/`:

**https://github.com/vishaltantri/CraftProof-Authenticity-Tracking-for-Handmade-Goods**

Read [`craftproof/README.md`](craftproof/README.md) for the application: architecture, setup,
API, tests and deployment.

## What the system does

- **QR certificates** — every piece gets a code and a printable QR tag pointing at a public
  certificate page that needs no login or app.
- **Signed custody chain** — each transfer is an Ed25519-signed record, hash-linked to the one
  before it.
- **Merkle checkpoints** — periodic roots seal the history so far, anchored outside the database
  by an RFC 3161 timestamp or an Ed25519-signed journal.
- **Independent verification** — `verify_cli.py` re-checks every hash, signature and Merkle proof
  locally, so the green badge does not depend on trusting the server.
- **Physical binding** — a photographic fingerprint of the object is committed into the signed
  genesis record, and repeat scans are cross-checked to catch a cloned tag.
- **Marketplace integration** — completed sales on the partner marketplace
  [ReMarket](https://github.com/arpan-basak/ReMarket) are imported as custody events, so a piece's
  history does not stop at the last person who happened to hold a CraftProof account.

### What it does not claim

Nothing here makes history impossible to change. Anyone with database access can alter the copy of
the data they hold. What the system provides is tamper-*evidence*: an alteration shows up as an
explicit, verifiable failure on the certificate, in the independent verifier, and against the
external anchor for any checkpointed record.

## Repository contents

| Path | What it is |
|---|---|
| `craftproof/` | The application (its own Git repository — see the link above) |
| `craftproof_research_paper_plan.md` | CraftProof 2.0 research paper plan: threat model, experiments E1–E6, attack matrix |
| `craftproof_artisan_authenticity_plan.md` | Original product and system design plan |
| `final_project_review_ppt.md` | Project review slide outline |
| `add_screenshots_to_pptx.py` | Builds the review deck from the workflow guide's screenshots |
| `*.pptx` | Generated review decks |

## Running the application

Full instructions, including demo data and the test suites, are in
[`craftproof/README.md`](craftproof/README.md). In short:

```bash
cd craftproof/backend
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
CRAFTPROOF_ALLOW_INSECURE_DEMO=true uvicorn main:app --port 8002

cd ../frontend
npm install
npm run dev -- --port 5174          # http://localhost:5174
```

The demo flag installs a fixed throwaway JWT secret so the app starts without configuration. Never
set it on a deployed instance — it also re-enables the tamper-demo endpoint. For anything real, set
`JWT_SECRET_KEY` to a secret of at least 32 characters.

## Documentation

In the application repository:

- [Complete workflow guide](craftproof/docs/WORKFLOW_GUIDE.md) — the whole product journey in
  screenshots, from registering a piece through a marketplace resale and a caught tamper attempt
- [Public API reference](craftproof/docs/API.md)
- [Deploying on Render](craftproof/docs/DEPLOYMENT.md)
- [Notes for the ReMarket team](craftproof/docs/REMARKET_PARTNER_NOTES.md)
- [Landing page design brief](craftproof/docs/LANDING_DESIGN_BRIEF.md)
- [Research dataset kit](craftproof/experiments/data/README.md) — photography checklist, consent
  template, manifest spec

In this repository: the research paper plan and the original design plan listed above.

## License

MIT.
