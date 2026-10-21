import React, { useState } from 'react'
import { Link } from 'react-router-dom'

import { API } from '../api'
const SITE = window.location.origin

function CodeBlock({ children }) {
  const [copied, setCopied] = useState(false)
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(children)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch { /* clipboard unavailable (non-secure context) — text stays selectable */ }
  }
  return (
    <div style={{ position: 'relative', marginBottom: '1rem' }}>
      <pre className="hash" style={{ padding: '1rem', paddingTop: '2.4rem', margin: 0, overflowX: 'auto', whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>{children}</pre>
      <button type="button" className="btn btn-sm" style={{ position: 'absolute', top: '0.5rem', right: '0.5rem' }} onClick={copy}>
        {copied ? 'Copied ✓' : 'Copy'}
      </button>
    </div>
  )
}

function Endpoint({ method, path, children }) {
  return (
    <div className="card" style={{ padding: '1.2rem 1.5rem', marginBottom: '1rem' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', marginBottom: '0.5rem', flexWrap: 'wrap' }}>
        <code className="badge badge-success" style={{ fontFamily: 'var(--font-sans)', fontWeight: 700 }}>{method}</code>
        <code className="hash" style={{ fontSize: '0.9rem' }}>{path}</code>
      </div>
      <div style={{ color: 'var(--color-muted)', fontSize: '0.95rem', lineHeight: 1.7 }}>{children}</div>
    </div>
  )
}

export default function Developers() {
  return (
    <div style={{ maxWidth: '860px', margin: '0 auto' }}>
      <h2>Build on CraftProof</h2>
      <p style={{ color: 'var(--color-muted)', lineHeight: 1.7 }}>
        Every certificate in CraftProof is readable over a simple JSON API, so other websites,
        marketplaces and gallery tools can verify a handmade piece without scraping or manual checks.
        The public verification endpoints are open — <strong>no API key or account needed</strong>.
        Write endpoints (registering pieces, recording transfers) use the same bearer-token auth as the web app.
      </p>

      <div className="card" style={{ padding: '1.2rem 1.5rem', marginBottom: '1.5rem' }}>
        <h3 style={{ margin: '0 0 0.4rem' }}>Base URL</h3>
        <CodeBlock>{API}</CodeBlock>
        <p style={{ color: 'var(--color-muted)', fontSize: '0.9rem', margin: 0 }}>
          Interactive docs: <a href={`${API}/docs`} target="_blank" rel="noreferrer">/docs (Swagger)</a> ·
          Raw schema: <a href={`${API}/openapi.json`} target="_blank" rel="noreferrer">/openapi.json</a>
        </p>
      </div>

      <h3 style={{ marginBottom: '0.75rem' }}>Verify a certificate (the one you probably want)</h3>
      <Endpoint method="GET" path="/api/verify/{code}">
        One call, plain-language verdict: is the piece authentic, who made it, where it is now,
        and its full ownership history. Returns <code>authentic: false</code> with a human-readable
        <code> reason</code> if any record fails its checks.
        <div style={{ marginTop: '0.75rem' }}>
          <CodeBlock>{`curl ${API}/api/verify/KOODE0LL`}</CodeBlock>
          <CodeBlock>{`const res = await fetch('${API}/api/verify/KOODE0LL')
const { authentic, piece, current_holder, history } = await res.json()
if (authentic) {
  console.log(\`\${piece.title} by \${piece.maker} — now at \${current_holder}\`)
}`}</CodeBlock>
          <p style={{ fontSize: '0.85rem', margin: '0 0 0.4rem', color: 'var(--color-faint)' }}>Example response (trimmed):</p>
          <CodeBlock>{`{
  "certificate_code": "KOODE0LL",
  "authentic": true,
  "reason": null,
  "piece": {
    "title": "Speckled tea bowl set",
    "materials": "Stoneware clay, tenmoku glaze",
    "maker": "Meera Krishnan",
    "created_at": "2026-08-14T10:32:11.428706+00:00"
  },
  "current_holder": "Kalakriti Gallery",
  "history": [
    { "date": "2026-08-14T10:32:11.428706+00:00", "event": "Created by Meera Krishnan",
      "note": "Piece created" },
    { "date": "2026-09-02T09:10:03.117420+00:00", "event": "Meera Krishnan → Kalakriti Gallery",
      "note": "Delivered to the gallery in person" }
  ],
  "ledger": { "records": 2, "anchored": 2 },
  "verify_url": "/c/KOODE0LL"
}`}</CodeBlock>
        </div>
      </Endpoint>

      <h3 style={{ margin: '1.5rem 0 0.75rem' }}>Verify a page of listings at once</h3>
      <Endpoint method="GET" path="/api/verify?codes=A,B,C">
        A marketplace rendering a grid of listings would otherwise make one request per
        certificate. This takes up to 50 codes and answers them together. Codes that do not
        exist come back with <code>found: false</code> instead of failing the whole batch.
        <div style={{ marginTop: '0.75rem' }}>
          <CodeBlock>{`curl '${API}/api/verify?codes=KOODE0LL,AB12CD34,NOPE0000'`}</CodeBlock>
          <CodeBlock>{`{
  "results": [
    { "certificate_code": "KOODE0LL", "found": true, "authentic": true,
      "current_holder": "Asha Rao", "marketplace": { "source": "ReMarket", ... } },
    { "certificate_code": "NOPE0000", "found": false, "authentic": null }
  ]
}`}</CodeBlock>
        </div>
      </Endpoint>

      <h3 style={{ margin: '1.5rem 0 0.75rem' }}>Marketplace sales</h3>
      <p style={{ color: 'var(--color-muted)', lineHeight: 1.7, marginTop: 0 }}>
        CraftProof reads completed sales from <Link to="/marketplace">ReMarket</Link> and records
        the buyer as the new holder. Responses carry a <code>marketplace</code> block whenever a
        step came from a marketplace rather than from the previous owner — show that distinction
        to your users rather than hiding it, because a marketplace sale is a report, not a
        custodian's confirmation.
      </p>
      <Endpoint method="GET" path="/integrations/remarket/status">
        Whether the ReMarket link is configured, how many sales it has recorded and when it last
        checked. Reports only whether a key is present, never its value. No auth.
      </Endpoint>
      <Endpoint method="GET" path="/integrations/remarket/imports">
        The sales already written onto certificates — order id, certificate code, buyer and the
        time CraftProof recorded it. No auth.
      </Endpoint>
      <Endpoint method="POST" path="/integrations/remarket/sync">
        Run a sync immediately instead of waiting for the next poll. Send the shared
        <code> X-Integration-Key</code> header. Intended for an external scheduler, since a free-tier
        backend sleeps and its own poller only runs while it is awake.
        <div style={{ marginTop: '0.75rem' }}>
          <CodeBlock>{`curl -X POST ${API}/integrations/remarket/sync \\
  -H "X-Integration-Key: $CRAFTPROOF_REMARKET_SYNC_KEY"`}</CodeBlock>
        </div>
      </Endpoint>

      <h3 style={{ margin: '1.5rem 0 0.75rem' }}>Full detail</h3>
      <Endpoint method="GET" path="/c/{code}">
        The complete certificate exactly as the <Link to={`/c/KOODE0LL`}>public certificate page</Link> renders it:
        per-record integrity checks and ledger anchoring included.
      </Endpoint>
      <Endpoint method="GET" path="/c/{code}/proof">
        Everything needed to verify CraftProof's claims independently — signed fields, record hashes,
        Ed25519 signatures, signer public keys and Merkle inclusion proofs. Pair it with the reference
        verifier, <code>backend/verify_cli.py</code>, in the repo.
      </Endpoint>
      <Endpoint method="GET" path="/ledger/checkpoints">
        The published ledger checkpoints CraftProof has sealed so far — the tamper-evidence backbone.
      </Endpoint>

      <h3 style={{ margin: '1.5rem 0 0.75rem' }}>Creating certificates from your own site</h3>
      <Endpoint method="POST" path="/auth/login → /pieces">
        Log in with any account to get a bearer token, then register pieces exactly like the dashboard does.
        <div style={{ marginTop: '0.75rem' }}>
          <CodeBlock>{`TOKEN=$(curl -s -X POST ${API}/auth/login \\
  -H 'Content-Type: application/json' \\
  -d '{"email":"meera@example.com","password":"craftproof123"}' \\
  | jq -r .access_token)

curl -X POST ${API}/pieces \\
  -H "Authorization: Bearer $TOKEN" \\
  -H 'Content-Type: application/json' \\
  -d '{"title":"Handwoven wool scarf","materials":"Merino wool, natural dye"}'`}</CodeBlock>
        </div>
      </Endpoint>

      <h3 style={{ margin: '1.5rem 0 0.75rem' }}>Embedding in your own site</h3>
      <div className="card" style={{ padding: '1.2rem 1.5rem', marginBottom: '1.5rem' }}>
        <p style={{ color: 'var(--color-muted)', lineHeight: 1.7, marginTop: 0 }}>
          The certificate URL is a stable public page — link a QR code or a “verify authenticity” badge
          straight at it, or fetch <code>/api/verify/&#123;code&#125;</code> and render your own badge:
        </p>
        <CodeBlock>{`https://${SITE.replace(/^https?:\/\//, '')}/c/KOODE0LL`}</CodeBlock>
      </div>

      <p style={{ color: 'var(--color-faint)', fontSize: '0.9rem' }}>
        The demo accounts above exist on this deployment; register your own account for production use.
      </p>
    </div>
  )
}
