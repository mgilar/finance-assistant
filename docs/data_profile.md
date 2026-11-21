# Data & policy profile

Done before any design work, to find what could make answers wrong.
Source: `data/invoices_2025_clean.csv` (140 rows), `data/vendor_master.csv` (10 vendors),
`data/procurement_policy.md` (FIN-POL-014 v3.2).

## A. Data issues that affect answers

| # | Finding | Impact | How the app handles it |
|---|---|---|---|
| 1 | Every vendor invoices in EUR, GBP **and** USD (89 / 27 / 24 rows; native sums EUR 4.49M, GBP 1.18M, USD 1.15M) | Rankings and totals are wrong without FX | Per-currency totals are the source of truth; EUR equivalent at fixed, labelled rates, with a caveat |
| 2 | Approval thresholds (§3) are in EUR; 12 GBP/USD invoices sit between 40k and 60k | The approval band can flip after conversion | Bands are computed on the EUR-converted amount, with a caveat |
| 3 | 2 credit notes (INV-20029 −52,749.39 EUR, INV-20096 −29,534.55 USD, both Helix Consulting), with no link to an original invoice | Gross ≠ net; §6.1 matching can't be verified | Totals are **net**; answers state how many credit notes are included |
| 4 | Vendor status is a current snapshot, not the status on the invoice date (29 rows from INACTIVE/ON_HOLD vendors, 22 of them with a PO and an approver) | §4.1 breaches can be overstated | Phrased as "vendor is *currently* INACTIVE", with a caveat |
| 5 | Country and category exist only in the vendor master | Country/category questions need a join | Joined once at load time |
| 6 | Free-text descriptions don't match vendor categories | "Spend on X" is ambiguous | Category = vendor-master category |
| 7 | `approved_by` is a username, not a role | Can't verify the approver had the right authority | Assistant states the gap |
| 8 | 21 invoices without a PO (all ≥ EUR 1,000), 25 without an approver, 3 without either | Real §2.2 / §3.1 flags | Listed as flags, not as confirmed violations (see §9.1) |
| 9 | Max invoice is 94,655; none above EUR 250k | The CFO band never applies | Correct answer is "none" |

Clean checks: no duplicate invoice numbers, no orphan vendor IDs, vendor names match the master, all dates in 2025.

## B. Policy rules the current data cannot verify

| Policy | Missing data |
|---|---|
| §1 Scope excludes clinical-trial site payments | No flag identifying them |
| §2.1 PO issued *before* work starts | No PO date or service date |
| §2.3 Blanket POs for recurring services | No PO type |
| §2.1 vs §2.2 | Policy inconsistency: "EUR 1,000 **or above**" vs "**above** the EUR 1,000 threshold" |
| §3 "Invoice / PO value" | Doesn't say which value, or which FX rate (§5.1 covers reporting only) |
| §3, §7 Approver level, segregation of duties, self-approval | No role directory, no requester field |
| §4.2 Due diligence, §4.3 master-data changes | No due-diligence status, no change log |
| §5.1 ECB rate on the invoice date | No FX rates in the pack |
| §5.2 Payment terms, early-payment discounts | No receipt or payment dates |
| §6.1 Credit-note matching, 90-day aging | No reference to the original invoice |
| §9.1 Emergency exceptions | No Exception Register (a missing PO may be legitimate) |
| §8.2 Traceable lineage | Requirement on **this system**: every answer must trace to its source rows / sections |

For questions touching these rules, the assistant answers what the data supports and
states explicitly what it cannot verify.
