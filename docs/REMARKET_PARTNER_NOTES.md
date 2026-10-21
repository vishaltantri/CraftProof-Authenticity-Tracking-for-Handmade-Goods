# Notes for the ReMarket team

Counterpart to ReMarket's `CRAFTPROOF_INTEGRATION.md`. That document specified the sale feed and
asked what CraftProof would do with it. This one answers: the importer is built, and here is what
ReMarket can change to take advantage of it.

**Nothing here is required.** The sale import already works against ReMarket exactly as it stands
today — no ReMarket code change is needed for ownership transfers to be recorded. Everything below
is an improvement ReMarket can adopt at its own pace.

CraftProof backend: `https://craftproof-backend.onrender.com`
All endpoints below are public and need no API key.

---

## 1. Check the seller is the recorded holder — recommended

ReMarket's own README is candid about this gap:

> ReMarket does not check that a code belongs to the photographed item or that the seller is its
> current recorded owner.

The title check added in `product_detail` closes the first half. This closes the second.

Today a listing can quote **any** certificate code — including one lifted from someone else's
public certificate page — and inherit its credibility. The buyer sees a real ownership history
for a real handmade piece and has no way to tell it has nothing to do with the seller.

### Endpoint

```http
GET /api/verify/{code}/holder?name=<seller name>
```

```json
{
  "certificate_code": "KOODE0LL",
  "authentic": true,
  "current_holder": "Asha Rao",
  "checked_name": "Asha Rao",
  "matches": true,
  "verdict": "The name given matches the holder CraftProof has on record...",
  "caveat": "Name comparison only. It does not prove identity..."
}
```

`matches` is **three-valued** and that distinction matters:

| Value | Meaning | What to show |
|---|---|---|
| `true` | The seller's name matches the recorded holder | A positive note, not a guarantee |
| `false` | It does not match | A warning |
| `null` | CraftProof cannot answer — the chain does not verify, or no holder is recorded | Neither; say it is unknown |

Please do not collapse `null` to `false`. That would accuse a seller because of a database problem
rather than because of anything they did.

### Where it goes

In `app.py`, `product_detail` already fetches the certificate and computes `certificate_mismatch`.
Add a sibling check next to it:

```python
seller_check = None
if product["craftproof_code"] and certificate and not certificate_error:
    for base in craftproof_bases(request):
        try:
            response = httpx.get(
                f"{base}/api/verify/{quote(product['craftproof_code'])}/holder",
                params={"name": product["seller_name"]},
                timeout=3 if base == CRAFTPROOF_LOCAL_BASE else 20,
            )
            response.raise_for_status()
            seller_check = response.json()
            break
        except (httpx.HTTPError, ValueError):
            continue
```

Then pass `seller_check=seller_check` to `render(...)`, and in `templates/product.html` extend the
existing `alert-soft` chain in the certificate section:

```jinja
{% elif seller_check and seller_check.matches is false %}
  <p class="alert-soft">
    CraftProof records this piece as held by {{ seller_check.current_holder }},
    not {{ product.seller_name }}. Ask the seller how they came by it before buying.
  </p>
{% endif %}
```

### Also worth doing at listing time

The same call in `create_listing`, after the existing `craftproof_code` format check, lets ReMarket
warn the seller while they are still filling the form — far better than surprising a buyer later.
A warning is the right response, not a hard rejection: a legitimate seller may simply have signed
up under a different spelling of their name, and a marketplace should not refuse the listing over
a string comparison.

---

## 2. Verify a whole page of listings in one request

`GET /api/verify/{code}` is one request per certificate. A home page showing twelve listings would
make twelve calls to a free-tier service that sleeps.

```http
GET /api/verify?codes=KOODE0LL,AB12CD34,32DUQVJ2
```

Up to 50 codes. Unknown codes return `found: false` rather than failing the batch:

```json
{
  "results": [
    { "certificate_code": "KOODE0LL", "found": true, "authentic": true, "current_holder": "Asha Rao" },
    { "certificate_code": "NOPE0000", "found": false, "authentic": null }
  ]
}
```

This makes it practical to show a verified marker on the listing grid in `home.html`, which
currently shows no certificate signal at all — the buyer only discovers a piece is documented
after opening it.

Collect the codes in the `home` handler, make one call, and pass a `{code: result}` dict to the
template. Treat a failed lookup as "no badge" rather than an error; the grid should still render
if CraftProof is asleep.

---

## 3. Show that a piece has sold through ReMarket before

`/api/verify/{code}` now returns a `marketplace` block when the current holder arrived via a
marketplace sale rather than a hand-to-hand transfer:

```json
"marketplace": {
  "source": "ReMarket",
  "order_id": "RM-000001",
  "buyer_name": "Asha Rao",
  "sold_at": "2026-10-14T12:00:00+00:00",
  "reported_by_marketplace": true
}
```

`null` when the last transfer was a normal one. Showing it on the product page gives a secondhand
listing something genuinely useful: this piece has been resold through here before, and the chain
recorded it.

Please keep the `reported_by_marketplace` distinction visible rather than flattening it into
"verified owner". CraftProof labels these steps as marketplace-reported on its own certificate
page for the same reason — see section 5.

---

## 4. The embeddable badge — the cheapest option here

One tag, no JSON parsing, no error handling:

```html
<a href="https://craftproof-backend.onrender.com/c/KOODE0LL" target="_blank" rel="noopener">
  <img src="https://craftproof-backend.onrender.com/badge/KOODE0LL.svg"
       alt="Verified by CraftProof" width="232" height="48">
</a>
```

`?style=compact` gives a smaller variant suited to a listing card. The image is live and cached
for a minute, so a certificate that stops verifying turns the badge red on ReMarket without
ReMarket doing anything.

---

## 5. What CraftProof does with a ReMarket sale, so your UI can match

So the two sites tell buyers the same story:

- A sale is imported only when `status` is `completed`, a certificate with that code exists, and
  the listing title matches the certificate title (case- and whitespace-insensitive). A mismatch
  is skipped and retried on later syncs — it never alters a certificate.
- Each `order_id` imports exactly once. Replaying the feed is a no-op.
- The custody record is signed by a CraftProof integration service account, **not** by the previous
  owner, and is labelled *"Reported by ReMarket — not confirmed by the previous owner"* on the
  public certificate.

That last point is deliberate and worth mirroring. A matching code and title is a safety check, not
proof of seller authority, and ReMarket's checkout is currently a simulation with no payment or
physical handoff. Neither site should present a marketplace sale as if a custodian confirmed it.

---

## 6. Open questions for us to agree on

These are decisions for both teams, not things either side can settle alone.

1. **When is a sale final?** CraftProof currently records a transfer as soon as ReMarket reports
   `status: completed`. With no payment and no handoff in the flow, that is early. If ReMarket
   later adds a settled or delivered state, CraftProof should wait for it — tell us the field name
   and we will gate on it.
2. **Seller authority.** Neither side verifies that the ReMarket seller was entitled to sell the
   piece. Section 1 narrows it; it does not close it. A real fix needs the holder to confirm,
   which means a CraftProof account action.
3. **Storage durability.** Both services use SQLite on free Render instances, so orders and
   accounts are lost on redeploy. Worth sorting before either side relies on the other's history.
4. **A push webhook instead of polling.** Your integration document offered this. We have not
   built a receiver, because polling is sufficient at this scale and a receiver is one more
   authenticated write path to get right. If ReMarket would prefer to push, say so and we will
   specify a receiver URL, an authentication scheme and a payload.

---

## 7. Checklist

- [ ] Confirm `REMARKET_SALE_API_KEY` on the ReMarket Render service matches the value given to the
      CraftProof team. The live endpoint currently answers `401` to an unauthenticated request, so
      a key is set — we have not been able to confirm it is the same one.
- [ ] Consider rotating that key once both sides are configured. It has travelled through chat.
- [ ] Seller/holder check on the product page (section 1)
- [ ] Seller/holder warning on the sell form (section 1)
- [ ] Batch verify on the listing grid (section 2)
- [ ] Show the `marketplace` block (section 3)
- [ ] Embed the badge (section 4)
- [ ] Reply on the open questions (section 6)

Questions or a different preferred shape for any of this — open an issue on the CraftProof repo and
we will adjust. The endpoints in sections 1 to 4 are additive and nothing existing has changed, so
ReMarket keeps working untouched if none of this is adopted.
