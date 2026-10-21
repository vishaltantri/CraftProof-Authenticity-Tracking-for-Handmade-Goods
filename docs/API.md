# CraftProof Public API

Every certificate is readable over a simple JSON API so other websites, marketplaces
and gallery tools can verify authenticity without scraping. Verification endpoints are
open — no API key or account needed. Write endpoints use bearer-token auth.

Interactive docs: `https://craftproof-backend.onrender.com/docs` · raw schema: `/openapi.json`

CORS is open to all origins on the public endpoints. The backend is a free Render instance that
sleeps, so allow up to a minute for the first request after a quiet period.

## Base URL

```
https://craftproof-backend.onrender.com
```

## Verify a certificate

```
GET /api/verify/{code}
```

Plain-language verdict plus the full ownership history. `authentic: false` comes with a
human-readable `reason` when any record fails its integrity checks.

```bash
curl https://craftproof-backend.onrender.com/api/verify/KOODE0LL
```

```json
{
  "certificate_code": "KOODE0LL",
  "authentic": true,
  "reason": null,
  "piece": { "title": "Speckled tea bowl set", "maker": "Meera Krishnan", "..." : "..." },
  "current_holder": "Kalakriti Gallery",
  "history": [
    { "date": "2026-08-14T10:32:11.428706+00:00", "event": "Created by Meera Krishnan", "note": "Piece created" },
    { "date": "2026-09-02T09:10:03.117420+00:00", "event": "Meera Krishnan → Kalakriti Gallery", "note": "Delivered to the gallery in person" }
  ],
  "ledger": { "records": 2, "anchored": 2 },
  "marketplace": null,
  "verify_url": "/c/KOODE0LL"
}
```

`current_holder` is the gallery or person recorded as holding the piece. A buyer with no CraftProof
account still appears here by name.

### The `marketplace` block

Present when the current holder arrived through a marketplace sale rather than a hand-to-hand
transfer. `null` otherwise.

```json
"marketplace": {
  "source": "ReMarket",
  "order_id": "RM-000001",
  "buyer_name": "Asha Rao",
  "sold_at": "2026-10-14T12:00:00+00:00",
  "recorded_at": "2026-10-14 12:04:08",
  "reported_by_marketplace": true
}
```

**Please keep that distinction visible rather than flattening it into "verified owner."** A
marketplace sale is a report, not a confirmation from the person who handed the piece over.
CraftProof labels these steps as marketplace-reported on its own certificate page for the same
reason.

## Verify many certificates at once

```
GET /api/verify?codes=A,B,C
```

Up to 50 codes per request. Built for a listing page that would otherwise make one call per item.
Unknown codes come back with `found: false` instead of failing the whole batch.

```bash
curl 'https://craftproof-backend.onrender.com/api/verify?codes=KOODE0LL,0275UKUB,NOPE0000'
```

```json
{
  "results": [
    { "certificate_code": "KOODE0LL", "found": true, "authentic": true, "current_holder": "Kalakriti Gallery" },
    { "certificate_code": "NOPE0000", "found": false, "authentic": null }
  ]
}
```

## Is the seller the recorded holder?

```
GET /api/verify/{code}/holder?name=<seller name>
```

A certificate proves the piece is genuine. It does **not** prove the person offering it to you is
entitled to sell it — a resale listing can quote any code, including one copied from a public
certificate page. This compares a named seller against the holder on record.

```bash
curl 'https://craftproof-backend.onrender.com/api/verify/KOODE0LL/holder?name=Kalakriti%20Gallery'
```

```json
{
  "certificate_code": "KOODE0LL",
  "authentic": true,
  "current_holder": "Kalakriti Gallery",
  "checked_name": "Kalakriti Gallery",
  "matches": true,
  "verdict": "The name given matches the holder CraftProof has on record...",
  "caveat": "Name comparison only. It does not prove identity..."
}
```

`matches` is **three-valued**, and the difference matters:

| Value | Meaning | What to show a user |
|---|---|---|
| `true` | The name matches the recorded holder | A positive note, not a guarantee |
| `false` | It does not match | A warning |
| `null` | CraftProof cannot answer — the chain does not verify, or no holder is recorded | Neither; say it is unknown |

**Do not collapse `null` to `false`.** That reports a database problem as an accusation against a
seller. Names are compared case- and whitespace-insensitively, the same rule the sale importer
uses. A mismatch is a reason to ask questions, never proof of theft.

## Embeddable badge

```
GET /badge/{code}.svg
GET /badge/{code}.svg?style=compact
```

A live SVG for any page, no JavaScript:

```html
<a href="https://craftproof-frontend.onrender.com/c/KOODE0LL" target="_blank" rel="noopener">
  <img src="https://craftproof-backend.onrender.com/badge/KOODE0LL.svg"
       alt="Verified by CraftProof" width="232" height="48">
</a>
```

Generated per request and cached for one minute, so a certificate that stops verifying turns the
badge red everywhere it is embedded. It reports four states: verified, object unconfirmed (a
possible cloned tag), not verified, and not found. An unknown code returns a badge saying so rather
than a 404, so a broken code never shows a broken image.

The piece title is XML-escaped before it enters the SVG. The badge renders inside other people's
pages, so a title containing markup must not become markup there.

## Full detail

| Endpoint | What it returns |
|---|---|
| `GET /c/{code}` | Complete certificate with per-record integrity checks, as the public page renders it. Steps imported from a marketplace carry a `marketplace` object |
| `GET /c/{code}/proof` | Signed fields, record hashes, Ed25519 signatures, signer public keys, Merkle inclusion proofs |
| `GET /ledger/checkpoints` | Published Merkle checkpoints sealing the record history |
| `POST /pieces/{code}/verify-object` | Compare a captured physical fingerprint against the enrolled one; runs clone detection |

`/c/{code}/proof` is what you want if you intend to re-verify the cryptography yourself rather than
trust this server's verdict. `backend/verify_cli.py` is a reference implementation.

## Marketplace integration

CraftProof reads completed sales from [ReMarket](https://github.com/arpan-basak/ReMarket) and
records the buyer as the new holder. CraftProof is the API client; ReMarket never writes here.

| Method | Endpoint | Auth | Purpose |
|---|---|---|---|
| `GET` | `/integrations/remarket/status` | No | Connection health and import counts. Reports whether a key is present, never any part of its value |
| `GET` | `/integrations/remarket/imports` | No | Sales already written onto certificates |
| `POST` | `/integrations/remarket/sync` | `X-Integration-Key` | Run a sync now. For an external scheduler |
| `POST` | `/integrations/remarket/sync-as-user` | Bearer | Same work, authorised by a normal session. Backs the dashboard button |
| `GET` | `/integrations/remarket/feed` | Bearer | Read the partner's live feed without importing |

```bash
curl -X POST https://craftproof-backend.onrender.com/integrations/remarket/sync \
  -H "X-Integration-Key: $CRAFTPROOF_REMARKET_SYNC_KEY"
```

```json
{ "imported": 1, "already_imported": 0, "skipped": [], "pages": 1,
  "cursor_before": 0, "checkpoint": { "batch_index": 7, "new": true }, "cursor_after": 1 }
```

A sale is imported only when its status is `completed`, a certificate with that code exists, and
the listing title matches the piece title. Mismatches appear in `skipped` and are retried on later
syncs; they never alter a certificate. Each order id imports exactly once, so replaying the feed
is a no-op.

What a partner should change on their side to use all of this is written up in
[REMARKET_PARTNER_NOTES.md](REMARKET_PARTNER_NOTES.md).

## Writing data

Authenticate like the web app does, then call the same endpoints the dashboard uses:

```bash
TOKEN=$(curl -s -X POST https://craftproof-backend.onrender.com/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"meera@example.com","password":"craftproof123"}' \
  | jq -r .access_token)

curl -X POST https://craftproof-backend.onrender.com/pieces \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"title":"Handwoven wool scarf","materials":"Merino wool, natural dye"}'
```

The demo accounts above exist on the deployed instance. Register your own for anything real.

## Embedding

Certificate URLs are stable public pages — point a QR code or an authenticity badge at
`https://craftproof-frontend.onrender.com/c/{code}`, use the SVG badge above, or fetch
`/api/verify/{code}` and render your own verdict.
