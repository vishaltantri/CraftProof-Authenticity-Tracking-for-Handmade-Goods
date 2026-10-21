# CraftProof frontend

React + Vite single-page app. It is a thin client: every verification verdict is computed by the
backend and re-checkable independently, so nothing here is trusted to decide whether a certificate
is authentic.

## Running it

```bash
npm install
npm run dev -- --port 5174     # http://localhost:5174
npm run build                  # production bundle into dist/
npm run lint                   # oxlint
```

The backend must be running too — see the root [README](../README.md).

## Configuration

One variable, read at build time:

```
VITE_API_URL=http://localhost:8002
```

Set in `.env` locally. On Render it is injected from the backend service's own URL via the
`fromService` block in [`render.yaml`](../render.yaml), so it never has to be kept in sync by hand.

`src/api.js` is the single source of truth for the base URL and strips trailing slashes
deliberately: a stray one turns every call into `…onrender.com//auth/login`, which 404s. That bug
broke login, signup and certificate lookups on a previous deployment.

## Pages

| Route | File | Purpose |
|---|---|---|
| `/` | `pages/Landing.jsx` | Public landing page with certificate lookup |
| `/login`, `/signup` | `pages/Auth.jsx` | Sign in and registration |
| `/dashboard` | `pages/Dashboard.jsx` | Maker and seller inventory, QR tags, transfers |
| `/c/:code` | `pages/Certificate.jsx` | Public certificate, ownership history, seller check |
| `/ledger` | `pages/Ledger.jsx` | Published Merkle checkpoints |
| `/marketplace` | `pages/Marketplace.jsx` | ReMarket connection, imported sales, live partner feed |
| `/developers` | `pages/Developers.jsx` | Public API guide with copyable examples |
| `/how-it-works` | `pages/HowItWorks.jsx` | Plain-language explainer |

Routing note: the landing page sits outside the shared chrome because it is a full-bleed design
with its own header and footer. Everything else renders inside `Nav` in `App.jsx`.

Deep links need an SPA rewrite on the host, or reloading `/c/ABC123` returns a 404. The rewrite
rule is in `render.yaml`.

## Two rules this UI follows

**Never show jargon.** Users see "Verified", "Certificate", "Ownership History". They never see
"hash", "signature" or "Merkle". The cryptography is in the backend and in
[`docs/API.md`](../docs/API.md) for anyone who wants it.

**Never overstate what is known.** Three places in the UI exist because of this:

- A step imported from a marketplace reads *"Reported by ReMarket — not confirmed by the previous
  owner"*, never *"Confirmed by"*. A marketplace sale is a report, not a custodian's word.
- A certificate whose tag may have been cloned never headlines as verified authentic, even when
  its recorded history is intact. The history being clean says nothing about the object the tag is
  stuck to.
- The seller check reports three outcomes, not two. "We cannot answer" is shown as its own state
  rather than being folded into a mismatch, because a database problem is not an accusation.

## Styling

Plain CSS with custom properties in `src/index.css`. No framework. Icons from `lucide-react`, QR
codes from `qrcode.react`. Colour, type and spacing tokens are defined on `:root`; use those rather
than literal values so the artisan theme stays consistent.
