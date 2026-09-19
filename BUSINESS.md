# Lelong Intelligence — Business Plan

**One line:** Sell auction bidders the two things the listing never tells them — *what this property is actually worth to own* and *what it will cost if I bid*.

Everything below is grounded in the dataset already in this repo. Figures marked
**[assumption]** are guesses that need validating before anyone spends money on them.

---

## 1. What we already own (audited 19 Sep 2026)

| Asset | Measured value |
|---|---|
| Deduplicated properties tracked | **12,810** |
| Geocoded (lat/lng) | **12,810 — 100%** |
| With a usable floor area | **12,542 — 97.9%** |
| Named building/scheme resolved | **3,651 schemes** |
| Schemes with ≥3 tracked listings | **1,474**, covering 9,874 listings |
| Listings with a future auction date | **320** live right now |
| Properties re-listed at least once | **4,200 — 33% of the database** |
| Observed reserve-price change events | **6,190** |
| Median cut per re-listing | **−10.0%** (mean −11.7%) |
| Median gap between re-listings | **22 days** |
| Longitudinal snapshots | ~6 months, every 2–3 days, 778 MB |
| Coverage | Selangor 9,442 · KL 3,252 |

**The one thing here nobody else sells.** lelongtips.com.my, AuctionGuru and every
auctioneer site show you *today's* reserve price. They do not show you that this
unit already failed three auctions and the bank has cut the reserve 10% each time,
roughly every 22 days of listing cycle. We have 6,190 recorded instances of that
happening. That history is the product.

**Data-quality debt (fix before selling anything).** Spot checks found real
defects: one listing flip-flops RM2.5m ↔ RM2.1m across scans (two units collapsed
into one key), another records an RM3,245,000 blip against an RM360,000 unit
(scrape/parse error). Selling a "price history" that is partly scraper noise is how
you lose a paying customer on day one. Budget ~1 week for outlier detection,
re-list vs. duplicate-unit disambiguation, and a confidence flag per history point.

---

## 2. Who pays, and for what pain

The buyer at a Malaysian foreclosure auction is making a six-figure, **irreversible**
decision on ~2 weeks' notice, with no interior viewing, no vendor to ask, and a
10% bank draft that is forfeited if they get the financing wrong. Their real
questions are:

1. **Is RM405,000 actually cheap?** The listing claims a discount off "market
   value" — a number from a valuation report they have never seen.
2. **What will it rent for?** Most bidders here are yield investors, not owner-occupiers.
3. **What will I actually pay to own it?** Not the bid — the bid *plus* outstanding
   maintenance arrears, quit rent and assessment arrears, water/electricity arrears,
   legal fees for the Memorandum of Transfer and loan documents, stamp duty, and
   possibly the cost of evicting an occupant who is not leaving.
4. **Can I even buy it?** Bumi lot restriction, leasehold state-consent, developer
   consent on a master title, financing eligibility on a property with no strata title yet.
5. **Should I bid now or wait?** If it fails again, the reserve drops ~10% in ~3 weeks.

Questions 3 and 4 are where people lose real money, and no product in Malaysia
answers them per listing. Question 5 only we can answer.

**Target segments, in order of willingness to pay:**

- **Active retail investors** (own 1–5 auction properties, bid a few times a year) — pay-per-report.
- **Auction-focused agents and bidding proxies** — subscription, they need it weekly and will white-label reports to their own clients.
- **Serious repeat investors / small funds** — subscription + area reports + export.
- **Renovate-and-flip operators** — need yield *and* resale comparables.

---

## 3. The product

### 3.1 Free tier — the funnel (already built)
The existing GitHub Pages site: search, map, filters, current price. Keep it free
and good. It exists to get people to a listing page where the paywall sits.
Gate exactly three things: full price history, the analysis report, and alerts.

### 3.2 The Bid Report — RM39 one-off, per property
A PDF/web report generated per listing, ~2 pages, delivered in under a minute.
This is the core object. Everything else is packaging.

### 3.3 Subscriptions

| Tier | Price **[assumption]** | For | Contents |
|---|---|---|---|
| **Free** | RM0 | Browsers | Search, map, current price |
| **Investor** | **RM89/mo** or RM790/yr | Retail bidders | Unlimited Bid Reports, full price history on every listing, watchlist alerts (new listing / reserve cut / auction date moved), bid-cap calculator |
| **Pro** | **RM349/mo** | Agents, proxies, flippers | Everything, plus client-branded PDF reports, area/building reports, CSV export, 5 seats |
| **Data** | **from RM1,500/mo** | Valuers, bank panels, proptech | API access + historical reserve-price dataset |

Annual billing on the Investor tier matters: the auction cycle is lumpy, and a
monthly subscriber churns the month after they win a property. Sell the year.

---

## 4. What goes in a Bid Report

Six sections. The first and the fifth are the ones nobody else can produce.

### A. Reserve price trajectory — *our moat*
Every observed reserve price, the cut at each step, days between, and a projection.

> **Worked example — Desa Villa Condominium, KL · 1,152 sq.ft · auction 23 Sep 2026**
> (real data, from `docs/data/active.json`)
>
> | Seen | Reserve | Change |
> |---|---|---|
> | 14 Mar 2026 | RM500,000 | — |
> | 16 Apr 2026 | RM450,000 | −10.0% |
> | 10 Jul 2026 | RM405,000 | −10.0% |
>
> **Read:** two failed auctions, a disciplined 10% cut each cycle — this bank is
> following a fixed reserve-reduction schedule, and no one has bid yet at any level.
> Current reserve is **19% below** the March reserve.
> **If it fails again, expect ~RM364,500 around Nov–Dec 2026.**
> Two failed cycles is also a warning: ask why nobody wants it at RM351/sq.ft.

That paragraph is worth RM39 on its own. It converts a blind bid into a decision
with a stated downside and a stated waiting cost.

### B. What it's worth — comparables
- **Auction comparables**: same scheme, same size band, from our own history.
  *(Reality check: Desa Villa has only 2 tracked listings. 1,474 schemes have ≥3 —
  thin comps are the norm, so external data is mandatory, see §5.)*
- **Open-market asking** prices for the same building/size band.
- **Transacted** prices (JPPH/NAPIC-derived) for the same building.
- Output: **RM/sq.ft: auction reserve vs. asking vs. last transacted**, with sample
  sizes shown. Never print a single "market value" number we cannot defend.

### C. What it rents for — yield
Median asking rent for the building/size band → **gross yield on your bid**, then
**net yield** after maintenance fee, sinking fund, quit rent, assessment, fire
insurance, and a vacancy allowance. Plus: how many units in this building are
currently listed for rent (a building with 40 units chasing tenants is a yield trap),
and how many are in foreclosure — we can already count that: Flora Damansara has
**57** tracked auction listings, The Scott Garden **70**. That concentration is a
distress signal that belongs in the report in red.

### D. All-in cost to own
A line-item worksheet on top of the bid price — this is the section that saves
people from disaster:
- 10% deposit on the fall of the hammer, balance typically within 90/120 days
- Outstanding **maintenance and sinking fund arrears** (commonly borne by the purchaser)
- **Quit rent and assessment** arrears; water/electricity arrears
- Legal fees + stamp duty on the Memorandum of Transfer, loan documentation, valuation
- Eviction/possession cost allowance where vacant possession is not guaranteed
- Renovation allowance by property type

Output: **all-in cost, all-in RM/sq.ft, and break-even rent.** Every figure is
sourced from the Proclamation of Sale and Conditions of Sale for *that* listing,
with the clause quoted, because these terms vary per auction and the whole value of
the report is that we read the document the bidder didn't.

### E. Can you actually buy it — risk flags
Parsed from the PoS/CoS: Bumi lot restriction, leasehold requiring state consent,
master title / no individual or strata title issued, developer consent required,
tenancy or occupation status, LACA vs non-LACA, financing eligibility notes.
Presented as a red/amber/green checklist. **A single "Bumi lot — you are not
eligible to bid" flag justifies the year's subscription for a non-Bumi buyer.**

### F. The area
From lat/lng (we have 100% coverage): distance to MRT/LRT/KTM, schools, hospitals,
malls; flood-risk history; auction density within 1 km; and the rental/resale
liquidity of the neighbourhood.

**Every report ends with:** a suggested **maximum bid** for a stated target net
yield, and a clear "bid now / wait for the next cut / avoid" verdict with reasons.

---

## 5. What has to be built (the honest gap list)

We have the auction side. We have **zero** market-price and rental data, and that is
half the pitch. Priority order:

| # | Build | Why | Effort **[assumption]** |
|---|---|---|---|
| 1 | Data-quality pass on price histories | Can't sell noisy history | 1 wk |
| 2 | **Rental comparables** by building/size | Section C; the #1 buyer question | 2–3 wks |
| 3 | **Transacted / asking price comparables** | Section B; validates "discount" | 2–3 wks |
| 4 | **PoS/CoS document ingestion + LLM extraction** | Sections D & E — the real differentiator, and defensible: it's document work, not a data copy | 3–4 wks |
| 5 | Report generator (web + PDF) | The deliverable | 2 wks |
| 6 | Auth, payments (Stripe/Billplz), paywall | Revenue | 1–2 wks |
| 7 | Alerts (Telegram already works) on watchlist | Retention | 1 wk |
| 8 | Next-cut prediction model | Upgrade §A from arithmetic to a model | later |

Steps 1, 4, 5 and 6 alone are a sellable v1 — reserve trajectory + all-in cost +
risk flags, with comparables marked "coming". Don't wait for everything.

**Source strategy matters.** Pulling the Proclamation of Sale directly from
auctioneer and bank panel sites makes us the primary processor of that document
rather than a mirror of someone else's listing page — better product *and* better
legal footing. See §8.

---

## 6. Unit economics **[all assumptions — validate]**

Cost to serve one report: LLM extraction + geo/comps lookups + PDF ≈ **RM1–3**.
At RM39, gross margin ~93%. The cost base is the pipeline, not the marginal report.

Illustrative month 12:
- 250 Investor subs × RM89 = RM22,250
- 25 Pro × RM349 = RM8,725
- 400 one-off reports × RM39 = RM15,600
- **≈ RM46,500/mo**, against infra + data + LLM costs well under RM5,000.

The sensitive number is **conversion from free traffic to paid**, not price. Track
it from week one. 320 live auctions at any time is a small pond — revenue comes
from *repeat* use across cycles and from Pro seats, not from one-time bidders.

---

## 7. Go to market

1. **Give away the moat, once.** Publish a monthly public post: *"Reserve prices in
   KL/Selangor fell a median 10% per re-listing; 33% of auctioned properties fail at
   least once."* Nobody else can publish that. It's link-bait for property media,
   Facebook auction groups and agents — and it proves the dataset exists.
2. **Free listing pages, paywalled history.** Every listing page shows the current
   price and the *shape* of the history blurred, with the count visible: "3 reserve
   cuts recorded — unlock". That is the whole funnel.
3. **Telegram alerts as the retention loop** — already built. Free alerts for new
   listings; paid alerts for reserve cuts on your watchlist.
4. **Agents first for B2B.** Auction agents and bidding proxies already charge
   clients for hand-made analysis. Sell them the Pro tier to white-label. They bring
   their clients to our free site.
5. **Referral revenue, later.** Auction financing pre-approval leads to bank panels
   and legal firm referrals for MOT work — meaningful per-lead value in Malaysia,
   but only once the product has trust. Don't start here; it compromises the
   "we're on the bidder's side" position.

---

## 8. Risks, in order of how much they matter

1. **Data provenance.** The current pipeline scrapes a third-party listing site.
   Reselling that content is a real legal and platform risk. Mitigations, in
   preference order: (a) build the paid layer on *our own observations* — the
   reserve-change time series is our measurement record, not their content; (b) go
   direct to auctioneer/bank-panel PoS documents, which are published notices;
   (c) approach the source for a data licence. Do not republish their listing text
   or images behind a paywall — link out. **Get a lawyer's read before charging.**
2. **Accuracy liability.** People will bid on our numbers. Every report needs a
   prominent scope statement: derived from public sources, verify the PoS and
   conduct a land search before bidding; no valuation or financial advice is given.
   Carry professional indemnity insurance before the Pro tier goes live.
3. **The source site changes or blocks us.** Single point of failure today.
   Diversify to auctioneer sites early — see risk 1, same fix.
4. **Small market.** 320 live listings across KL/Selangor. Growth requires national
   coverage (Penang, Johor, Sabah/Sarawak) — the pipeline generalises, so plan for it.
5. **Incumbent moves.** EdgeProp/Brickz/PropertyGuru have market-price data and could
   add an auction layer. Our defence is the longitudinal reserve history — they
   cannot backfill 6 months of observations they didn't record, and by the time they
   start we'll have 18.

---

## 9. Ninety days

- **Weeks 1–2 — validate before building.** Interview 15 people who bid in the last
  year (Facebook auction groups, agents). Ask what they got wrong and what they'd
  have paid to know. Hand-make 5 reports in a spreadsheet and try to sell them at
  RM39. If nobody pays for a hand-made report, no amount of engineering fixes that.
- **Weeks 3–6.** Data-quality pass; PoS ingestion + extraction for the ~320 live
  listings; report generator.
- **Weeks 7–9.** Paywall + payments; launch pay-per-report at RM39; publish the
  public data post.
- **Weeks 10–13.** Rental and transacted comparables; open the Investor tier; sign
  the first 3 Pro (agent) accounts.

**The one metric for the quarter:** paid reports per 100 listing-page views. Below
1%, the report isn't good enough or the price is wrong — fix it before scaling traffic.

---

## 10. Do this week

1. Fix the price-history defects (§1) — the moat is worthless if it's noisy.
2. Hand-make the Desa Villa report from §4 as a single PDF. That's the pitch.
3. Post the "10% per re-listing, 33% fail rate" finding publicly and watch what it
   pulls in.
4. Ask 10 bidders one question: *"Would you pay RM39 to know the reserve has been
   cut twice and will likely drop to RM364k in December?"*

*(All figures recomputed from `data/properties.json` and `docs/data/active.json` on
19 Sep 2026.)*
