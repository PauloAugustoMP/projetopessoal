# Business rules — Investment tracking app

This document formalizes the rules decided throughout planning. It is the source of truth that the implementation (and unit tests) must follow.

> **Tax scope**: the app does not calculate DARF (Brazilian tax return form), does not track the monthly R$20k tax-exempt threshold on stock sales, nor loss carryforward. It **shows gross vs. net value** whenever tax is withheld at the source (e.g. JCP). Calculating the actual tax liability is the user's/accountant's responsibility.

## 1. Average price and position

Weighted average price method (the standard approach in the Brazilian market).

**Buy:**
```
newAveragePrice = (currentQty × currentAveragePrice + boughtQty × buyPrice + fees) / (currentQty + boughtQty)
newQuantity     = currentQty + boughtQty
```

**Sell:**
```
newQuantity      = currentQty - soldQty
realizedProfit   = soldQty × (sellPrice - currentAveragePrice) - fees
# the average price does NOT change on a sell
```

If `newQuantity == 0`, the average price resets to zero — a future buy of the same asset starts the calculation from scratch (it does not inherit the average price from a previous position cycle).

Transactions for the same asset are always processed **in chronological order**, never in the order they were entered into the system — essential for backdated entries.

## 2. Retroactive recalculation engine

Triggered whenever a transaction is created, edited, or removed with a past date.

1. Recalculates the affected asset's position (rule 1) by walking the entire transaction history in chronological order.
2. Recalculates the daily `PortfolioSnapshot` records between the transaction date and today.
3. Re-evaluates dividend (`Dividend`) eligibility whose ex-date falls between the transaction date and today — flags as "pending review" if the new position now qualifies for a dividend that wasn't previously linked.
4. Runs in the background (queue), does not block the API response. Idempotent: re-running produces the same result.

## 3. Allocation targets and rebalancing (contribution simulator)

Two-level structure:
- `AllocationTarget`: percentage per **category** (Stocks, REITs, Fixed income, Crypto), must add up to 100%.
- `TargetAsset`: asset → category + optional weight within the category. With no weight defined, **splits equally among the assets in the category**.

```
finalAssetPercentage = categoryPercentage × weightWithinCategory
```

Given a contribution of amount `C`:

```
for each target asset:
  targetValue_i = finalAssetPercentage_i × (currentTotalPortfolioValue + C)
  gap_i = max(0, targetValue_i - currentInvestedValue_i)   # never suggests selling

totalGap = Σ gap_i

if totalGap > 0:
  suggestedValue_i = C × (gap_i / totalGap)
else (every asset already met or exceeded its target):
  suggestedValue_i = C × finalAssetPercentage_i   # splits by target weight

suggestedQuantity_i = floor(suggestedValue_i / currentPrice_i)
unallocated = C - Σ (suggestedQuantity_i × currentPrice_i)   # shown as "not allocated in this contribution"
```

Quantity is always an integer (B3's fractional market allows any quantity ≥ 1, no round-lot requirement).

## 4. Indicators, markers, and target prices

Each indicator has: a formula, a marker color (threshold), and tooltip text — kept in a single registry (not duplicated across the UI).

| Indicator | Formula | Green | Yellow | Red |
|---|---|---|---|---|
| P/E | Price ÷ Earnings per share | < 15 | 15–25 | > 25 |
| P/B | Price ÷ Book value per share | < 1 | 1–2 | > 2 |
| DY | Trailing 12-month dividends ÷ Price | > 6% | 3–6% | < 3% |
| ROE | Net income ÷ Shareholders' equity | > 15% | 10–15% | < 10% |

Thresholds are configurable heuristics, not investment advice — the app makes this explicit in the UI.

**Ceiling price (Bazin Method):**
```
ceilingPrice = trailingDividends12m ÷ desiredMinimumYield
# default: 6% for stocks, 8% for REITs — configurable per asset
```

**Fair price (Graham's Formula):**
```
fairPrice = √(22.5 × EPS × bookValuePerShare)
# only applies to stocks; undefined if EPS or book value per share ≤ 0
```

## 5. Corporate actions

Captured automatically from the B3 statement import (rule 7), never requiring manual entry in the normal flow.

| Event | Effect on quantity | Effect on average price |
|---|---|---|
| Split N:M (e.g. 1:2) | `qty × (M/N)` | `averagePrice × (N/M)` |
| Reverse split M:N (e.g. 10:1) | `qty ÷ factor` | `averagePrice × factor` |
| Bonus shares X% | `qty × (1 + X/100)` | recalculated to preserve total cost: `(oldQty × oldAveragePrice) / newQty` |
| Subscription rights exercised | treated as a new buy transaction, at the subscription date and price | follows rule 1 (buy) |
| Subscription rights not exercised | no effect | no effect |

Total position cost is preserved across these events (except exercised subscription rights, which injects new capital).

## 6. Dividends — gross, net, and withholding

| Type | Tax withheld at source | Net |
|---|---|---|
| Dividend (stocks) | Tax-exempt | = gross |
| JCP (Interest on Equity) | 15% | `gross × 0.85` |
| REIT income | Tax-exempt for individuals (fund with ≥ 50 unit holders, exchange-traded, investor holding < 10% of the fund's units) | = gross |
| Fixed income redemption | Regressive schedule by holding period | see below |

Regressive schedule (fixed income, applied to the yield at redemption):

| Holding period | Rate |
|---|---|
| up to 180 days | 22.5% |
| 181–360 days | 20% |
| 361–720 days | 17.5% |
| over 720 days | 15% |

`Dividend` stores `grossValuePerShare`, `withholdingTaxRate`, and a computed `netValuePerShare`.

## 7. B3 statement import

1. Upload of the CSV/Excel file exported from the B3 investor portal.
2. The parser classifies each line as: a transaction (buy/sell), a dividend, or a corporate action (section 5).
3. **Deduplication**: a line is only saved if no equivalent transaction already exists (same ticker + date + quantity + price, within a cent's tolerance). On an ambiguous match (more than one candidate), the line is flagged for manual review instead of being decided automatically.
4. Every newly saved line triggers the recalculation engine (section 2).

## 8. Daily snapshots and growth breakdown

A daily job (`daily-snapshot`, run after market close) records, per day:
- Total and per-category portfolio value
- Cumulative contributions to date
- Cumulative reinvested dividends to date

The growth breakdown over a period is computed **by residual**, guaranteeing consistency (the three parts always add up to the total observed change):

```
periodAppreciation = periodTotalChange - periodContributions - periodReinvestedDividends
```

### 8.1 Catch-up on startup

Since the backend doesn't run 24/7 (it's a desktop app, not an always-on server), the daily snapshot job can miss days when the computer was off or the app was closed. State is persisted as `lastSnapshotDate` (date) and `lastRunAt` (full date and time, useful for diagnosing how long the app was offline).

On backend startup:
1. Reads the persisted `lastSnapshotDate`.
2. Computes the missing days between that date and today (`computeMissingSnapshotDates`, in `packages/domain`).
3. Runs the same recalculation engine from section 2 for each missing day, in order.
4. Updates `lastSnapshotDate` and `lastRunAt` after each successful run — if the process is interrupted midway, the next startup resumes exactly from the last confirmed day, without skipping or duplicating.

On the very first run (no prior state), there's no catch-up: today's snapshot is created by the job's normal execution.

## 9. Dividend reinvestment

```
availableReinvestmentBalance = Σ(netDividendsReceived) - Σ(dividendsAlreadyReinvested)
```

The "Reinvest now" flow uses `availableReinvestmentBalance` as the `C` input to the contribution simulator (section 3). On confirming the suggested purchases, the corresponding dividends are marked as reinvested, feeding into the growth breakdown (section 8).

## 10. Sanity checks

- **Sell larger than the position on that date**: manual entry is blocked with an immediate error. On statement import (where several lines come in together and order matters), the check runs **after** the full batch has been recalculated, and flags the inconsistency for review instead of rejecting the line in isolation.
- **Unknown ticker**: blocks the entry until the asset is confirmed (prevents a silent typo).
- Every retroactive change is recorded in an audit log with the option to undo the last change.
