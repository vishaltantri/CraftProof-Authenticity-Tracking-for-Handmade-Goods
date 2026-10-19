# CraftProof – Authenticity Tracking for Handmade Goods

CraftProof is a full‑stack web application that allows artisans to issue digital certificates for their handmade products and record every custody transfer securely.  The project is written in **Python/FastAPI** on the back‑end and **React + Vite** on the front‑end, with **SQLite** as the persistence layer.

## Key Features

- **QR Code Registry** – Every product gets a QR code that contains a verifiable hash of its provenance.
- **Cryptographically‑Linked Custody Records** – Each transfer is stored as an ISO‑8601 timestamped record signed with Ed25519 and chained via SHA‑256.
- **Merkle Checkpoints** – Periodic tree roots provide efficient, tamper‑evident proofs of the entire history.
- **Independent Verification** – Clients can verify authenticity locally without contacting the server.
- **Open‑Source** – All source is freely available on GitHub.

## Repository Structure

```
backend/          # FastAPI + SQLite + cryptographic core
frontend/          # React + Vite front‑end
docs/              # Markdown documentation (this file, plan, presentation)
```

## Building & Running Locally

The repository uses **pip** and relies on the `requirements.txt` files in each sub‑directory.

```bash
# Install backend dependencies
cd backend && pip install -r requirements.txt
# Run the FastAPI server
uvicorn main:app --reload

# Install frontend dependencies
cd ../frontend && npm install
# Start the Vite development server
npm run dev
```

The API is available at `http://localhost:8000` and the front‑end at `http://localhost:5173`.

## Documentation 

Additional documentation and the research plan are kept in the `docs/` directory:

- [CraftProof 2.0 – Research Paper Plan](docs/craftproof_research_paper_plan.md)
- [CraftProof – Artisan Auth. Plan](docs/craftproof_artisan_authenticity_plan.md)
- [Project Review Slides](docs/final_project_review_ppt.md)

## License

MIT.
