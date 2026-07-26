# Build prompt — goldset-triad-harness, PHASE 1 (credibility core)

Hand this file to a building agent (a fresh Claude Code session, Cursor, Aider, or equivalent) together
with the spec. It targets **phase 1 only**.

## Read first

1. `specs/goldset-triad-harness.md` — the complete specification. Read it fully before writing any code.
2. `DECISIONS.md` (repo root) — the decision record D0–D12: every fork, the options, the choice, and why.
   Do not relitigate these; if one looks unsafe or wrong, say so before building.

## Recommended build-time settings

**Model: Claude Opus 5. Reasoning effort: Extra (xhigh).** Phase 1 carries a heavy subtle-correctness load
— 1:1 matching with a deterministic tie-break, byte-identical reproducibility, and answer-key authoring
where an error invalidates every score built on it. These settings were reviewed and accepted by the author.
Do not silently downgrade.

## Work in this order

1. **Restate the outcome in one sentence.**
2. **Review the spec's assumptions block.** All eight were confirmed on 2026-07-25. Flag anything that now
   looks wrong or risky and confirm with the author BEFORE building.
3. **List any remaining ambiguities or missing information.**
4. **PLAN GATE — enter plan mode (or your tool's equivalent), present an implementation plan for phase 1,
   and get human approval BEFORE writing code.** Do not skip this.
5. Build **only** phase 1.
6. Verify every phase-1 acceptance criterion **by running it**.

## Build ONLY phase 1

Phase 1 is the nine floor items, all retained:

1. **Findings payload schema v1** — the stable port. Closed category enumeration of **five** categories
   (`PRICE_VARIANCE`, `QTY_UNDER_SHIPMENT`, `QTY_OVER_SHIPMENT`, `QTY_INVOICE_INFLATED`, `TAX_VARIANCE`);
   **`scope`** of `LINE` or `DOCUMENT`; composite `TargetLine` (document id + line id) where the document is
   **the invoice under evaluation**; `Status` (`MATCH` | `DISCREPANCY`), `Confidence`, free-text reasoning.
   Confidence and reasoning are carried but **never scored**. `target_line` is required for `LINE` scope and a
   **reserved sentinel — never empty, never absent** — for `DOCUMENT` scope; a document-scoped finding with a
   missing line id is **malformed**, not inferred. Line identifiers are assigned explicitly by the dataset,
   never positional (D20, D22).
2. **Scoring engine** — strict match key (`Status` + `Category` + `TargetLine`), 1:1 matching, deterministic
   tie-break, per-category precision and recall, false-positive count and rate.
3. **Scorecard emission** — JSON plus human-readable summary; embedded SHA-256 fingerprints of the findings
   artifact and the answer key; a `run_metadata` envelope holding exactly the non-deterministic fields.
4. **A small, newly-authored 3-way dataset** including goods-receipt discrepancies (under-shipment and
   over-shipment) and a **zero-defect control case**. Existing `reconciliation-fixtures` inform the *schema
   only* — do not copy their content.
5. **The initial category set** as enumerated above, including arithmetic `TAX_VARIANCE`.
6. **Dataset selection by identifier or path** — a dev split shipped in the repo, and a fully private
   held-out split resident outside the repository tree.
7. **Held-out split isolation** — placement outside the repo tree, deny-guards, plus a **guard-configuration
   check** and a **placement check** (see D30 below — do **not** write a reachability probe). **Read the tier
   table below before implementing this; getting the guard scope wrong breaks evaluation rather than protecting
   it.**
10. **Separate `goods_receipts/` documents** with their own GRN, date, receiver, line items and identifiers
    (D31), and a **realistic dev split** plus a small labelled **synthetic fixture** set (D32).
8. **Type discipline** — pyright with zero errors, `Decimal` for money, frozen dataclasses, `typing.Final`
   constants.
9. **Test suite** covering every `[P1]` acceptance criterion.

**Higher phases are documented-but-not-yet. Do NOT build them, and do NOT make architectural choices that
block them.** Specifically out of this push: `--verify` mode, the JSONL ledger, README/methodology, CI,
cross-platform verification (all `[P2]`); dataset expansion, performance budget, lenient match mode
(`[P3]`); compliance categories (`[P4]`); packaging, runner adapter, confidence calibration (`[P5]`).

Note the forward-compatibility obligations even though those items are not built now: fingerprints must be
embedded in phase 1 so `[P2]` verify mode works later; duration must be recorded in `run_metadata` in phase
1 so the `[P2]` ledger has something to aggregate; and the match key must be structured so `[P3]` lenient
mode can drop `TargetLine` without redesign.

## Non-negotiable constraints

**Determinism boundary — the spine of this project.**
- The harness makes **no LLM call and no network call, ever, at runtime.** Every operation is plain
  deterministic code: loading, schema validation, matching, tie-breaking, precision/recall arithmetic,
  fingerprinting, timestamp handling, serialization.
- There are **no runtime judgment tasks** and therefore no model tier to select. This is deliberate: a
  non-deterministic scorer cannot produce the byte-reproducible verdict that makes the tool credible.
- AI assistance is permitted only at **design time** for the discrepancy plan, whose output is audited and
  frozen into seeded generator code. No design model is invoked by any pipeline.

**Type & value discipline.**
- Type hints throughout; **pyright must report zero errors** — this is an acceptance criterion, not advice.
- `Decimal` for every monetary value; **never `float`** on a monetary path.
- Frozen dataclasses for records; `typing.Final` for constants.

**Stack.**
- Python 3.11+. The **scoring engine imports standard library only** (`json`, `decimal`, `dataclasses`,
  `typing`, `hashlib`, `pathlib`). No third-party dependency in the scoring core.
- **No new packages without flagging for approval first.**
- Windows and Linux both first-class: use `pathlib`, assume no shell-specific behaviour, and document every
  command for **both** PowerShell and bash.

**Scoring semantics — these decide which lines the answer key marks (D15, D16).**

```
payable_qty      = min(qty_ordered, qty_received)
overbilled       = qty_invoiced > payable_qty
price_variance   = (invoice_unit_price - po_unit_price) * payable_qty

basis            = payable_qty * po_unit_price          # LINE scope   (D19)
basis            = invoice_taxable_subtotal             # DOCUMENT/tax (D21)
threshold        = max($0.05, min(0.02 * basis, $25.00))
flag             = |variance| >= threshold              # >= , not >

match_key        = (status, category, scope, target)    # D20
```

- **The basis is the PAYABLE extended amount, never the invoiced one.** An inflated invoice would enlarge its
  own denominator and understate its variance ratio — PO 10 × $10 billed as 10 × $20 reads 100% against the
  PO basis and only 50% against the invoice basis. Never divide by the disputed value.
- **Phantom billing falls out of the formula**: `payable_qty = 0` → basis $0 → threshold drops to the $0.05
  floor → anything billed for goods never received always flags. No special case needed.
- **`TAX_VARIANCE` is DOCUMENT-scoped** and measured against the invoice's taxable subtotal, not a line
  amount. Do **not** distribute one tax error across taxable lines — that multiplies a single error into N
  findings and corrupts per-category precision/recall.
- **Scope participates in the match key**, so a line-scoped and a document-scoped finding sharing status,
  category and document id must not match each other.

- **Quantity category = which constraint bound the payable quantity.** `received < ordered` →
  `QTY_UNDER_SHIPMENT`. `ordered < received` → `QTY_OVER_SHIPMENT`. `ordered == received` →
  `QTY_INVOICE_INFLATED` (no shipment anomaly; the invoice is simply wrong).
- **A short shipment billed correctly for what arrived is NOT a discrepancy.** Shipment anomaly without
  billing impact produces no finding. Marking it would reward flagging non-issues.
- **Price variance is measured at the payable quantity**, so a quantity error cannot present as a price error
  and get counted twice across two categories.
- **One materiality threshold for all monetary categories**, quantity included — a quantity overbill is
  valued at `(qty_invoiced - payable_qty) * po_unit_price` and passed through the same formula.
- **The $25 cap governs large lines; the 2% only ever governs below the $1,250 crossover.** On a $100,000
  line the threshold is $25, not $2,000 — that asymmetry is deliberate, because a tolerated $1,999 variance
  would be a disqualifying blind spot for a harness built to catch money leaving.
- **`>=`, not `>`** — a variance exactly on the threshold flags rather than passes, so a boundary case is
  never a silent miss.
- **Publish the rule** in the dataset's matching policy. The agent cannot compete against a threshold it
  cannot read.

**Do NOT write a reachability probe (D30).** A criterion previously asked code to confirm the guarded area is
"unreachable from an agent context". That is impossible: deny rules bind **tool calls**, and a subprocess runs
**beneath** that boundary — your script will always `open()` the canary. Such a probe reports failure
unconditionally and fails *identically* whether the guards are perfect or absent, which is worse than no check.

Ship instead:
1. **Guard-configuration check** — deny rules exist, parse, and cover **every** secret path (directory,
   answer-key filename, generator filenames, design artifact). Fail loudly naming any uncovered path. This
   catches the real regression: a guard file lost, hand-edited, or stale after a new secret file was added.
2. **Placement check** — no secret artifact at any path inside the repo tree, **including under ignored
   directories**.

Harness enforcement is **attested, not tested**: record a dated note of a tool-level read being refused, using
the canary as the decoy. Keep the canary covered by the directory rule alone. And **claim only what is
verified** — placement and configuration are checked; enforcement is attested; a determined subprocess is
outside deny coverage by design, which is exactly why placement is the primary control.

**The harness NEVER parses a document (D34).** Structured invoice data — line ids, quantities, prices, tax
field, timestamps, invoice count — comes from a **structured invoice index** in the **agent-denied tier**,
beside the answer key. Not from parsing PDFs (extraction is out of scope, and a parser in the scoring engine
breaks stdlib-only), and **not** from an agent-readable sidecar (structured invoice data would bypass the
extraction the PDF exists to require).

It is a **complete line inventory including clean lines** — target validation must tell a line that exists from
one that does not, which expected findings alone cannot support. It is **separate from the key**, so the key
stays expected-findings rather than input restatement. And it is **fingerprinted**: it moves the score, so by
D27's logic the scorecard carries **four** fingerprints — findings, key, **invoice index**, inputs aggregate.

**PDF authoring: ReportLab, from P1, clean text-layer only (D33).** Hard format tiers (dot-matrix, multi-page,
consolidated, scanned) stay `[P3]`. ⚠️ **Generated PDFs must be byte-identical on regeneration** — PDF writers
embed a creation timestamp and document ID by default, so without pinning them, every regeneration changes the
inputs digest and looks like tampering. Pin document dates to the **seeded** timestamp (D6) and pin or suppress
the ID; ReportLab's invariant output mode is the reason it was chosen over PyMuPDF, so **verify that early**.
This dependency is **generation-side only** — the scoring engine remains standard-library-only.

**Goods receipts are separate documents (D31).** Their own `goods_receipts/` directory, each with GRN, date,
receiver, line items and **its own identifiers and descriptions** — not a `receipts[]` array inside the PO
record, which would let an agent find quantity discrepancies by diffing two fields in one file without opening
an invoice. Invoices are supplier **PDFs** (external, need extraction); PO database and receipts are internal
**structured JSON**. ⚠️ **Received quantity is the SUM across all receipts for a line** — partial deliveries
produce several, and a key built from one receipt where two exist is wrong.

**Data families (D32).** A **realistic dev split** (`datasets/dev/`, portfolio-facing, ships with its key) plus
a small **clearly labelled synthetic fixture** set — and only for values implausible in the domain. Most
boundary cases are realistic and belong in the dev split: a fully exempt PO is the *common* case, and $500 and
$333.33 extended lines are ordinary. **Only the $100,000 line is synthetic.** Synthetic fixtures load through
the **same manifest and loader**, so tests exercise the real path. A $100,000 head of lettuce in the showcase
dataset would destroy the domain credibility the dev split exists to establish.

**Line correspondence (D22) — the key declares it, the inputs do not.**

The invoice→PO→receipt correspondence is **ground truth in the answer key**, on the secret side, so the key is
unambiguous and an independent auditor can reproduce it. It is **absent from the agent-readable inputs**:
resolving correspondence across differing descriptions, part numbers and UOM is the capability under test, and
publishing the mapping would delete a class of difficulty the taxonomy exists to create. `TargetLine` names
the invoice line only, so the agent never has to *express* the correspondence in a finding — it only needs it
to decide what to flag.

**Out-of-tree layout (D17) — sibling directories, deliberately not a shared parent:**

```
D:\Claude_Stuff\goldset-triad-holdout\      tier 2: out-of-repo, agent-READABLE
├─ invoices\
└─ po_database\

D:\Claude_Stuff\goldset-triad-secret\       tier 3: out-of-repo, agent-DENIED
├─ ANSWER_KEY.json
├─ design\discrepancy-plan.md
├─ _generators\gen_*.py
├─ _guard-template.settings.json            source of truth for deny rules
├─ dataset-holdout.manifest.json            names inputs_dir + key_path
└─ canary\throwaway.json                    unique marker
```

Siblings, not `holdout/{inputs,secret}`, so that a careless `holdout\**` deny rule cannot silently cover the
inputs. A **dataset is a pair of locations** — resolve it through a manifest naming `inputs_dir` and
`key_path`. The dev manifest ships in-repo under `datasets/dev/`; the held-out manifest lives on the secret
side, readable by the scoring process and unreachable by the agent, which only needs the inputs directory.
Keep the canary covered by the **directory** rule only, never a filename rule, so it exercises the weakest
layer.

**Isolation tiers — read this before touching the guards (D14).** Two axes are easy to conflate, and
conflating them produces a harness that cannot evaluate anything:

| | in-repo | out-of-repo |
|---|---|---|
| **agent-readable** | dev split — inputs **and** answer key | **held-out inputs** |
| **agent-denied** | — | held-out answer key, generators, discrepancy-design artifact |

- The **held-out inputs are out-of-repo but MUST stay agent-readable.** The agent-under-test cannot produce
  findings without reading them. A deny-guard scoped to "the held-out directory" instead of to "the
  held-out key, generators and design artifact" silently breaks evaluation.
- The **dev split is public by design** and is NOT deny-guarded. It ships complete, key included, and is
  the split every automated check and the CI workflow runs against.
- The **held-out split must be unreachable from CI** by construction. The full acceptance suite therefore
  has to pass using only the dev split, with no out-of-tree path configured.
- Dataset selection by path is what makes an out-of-tree split work — no special-casing, just a path.

**Rounding (D23) — compare exact, round only to display.**
- Compute and compare at **full `Decimal` precision. Never round before a comparison.** Rounding an
  intermediate is path-dependent (round-then-multiply ≠ multiply-then-round) and would make an auditor's
  recomputation diverge. On a $333.33 basis the threshold stays $6.6666: a $6.67 variance flags, $6.66 does not.
- Round to 2dp **only at emission**, and set **`ROUND_HALF_UP` explicitly** — Python's `Decimal` defaults to
  `ROUND_HALF_EVEN` (banker's), which is not what an accountant expects. A rounded value must never re-enter a
  comparison.
- Amounts are **not** part of the match key, so rounding can only affect whether a finding *exists* and how it
  *displays* — never what matches what.

**No division inside a decision (D28).** The derived tax rate `po_tax ÷ po_taxable` is generally
non-terminating, and `Decimal` division rounds to the ambient context precision — so a divide-then-compare
formulation is **not** exact and an auditor at a different precision could diverge. Cross-multiply instead:

```
LHS = | inv_tax * po_taxable - po_tax * inv_taxable |
RHS = threshold * po_taxable
flag iff LHS >= RHS
```

Multiplication and subtraction only. Algebraically identical, genuinely exact.

⚠️ **This form is valid ONLY where `po_taxable > 0`. At zero it breaks (D29).** Multiplying through by zero
destroys the inequality: both sides become `0`, so `0 >= 0` flags **every** invoice — and flags identically
whether the invoice charged `$0` or `$50`, because `inv_tax` is annihilated. Since unprepared food is
sales-tax-exempt in most US states, a food distributor's POs are commonly fully exempt, so this branch is
ordinary traffic, not an exotic corner:

```
if po_taxable == 0:                     # no rate derivable; nothing to divide
    expected_tax = 0
    flag iff |inv_tax| >= $0.05         # threshold degenerates via basis = 0
```

A correct `Tax: 0.00` on an exempt order produces **no finding**; any charge of 5¢ or more flags as
`TAX_VARIANCE`. Note "no taxable lines" is **not** "no tax line" — real single-template printing always emits
`Tax: 0.00`, so the field is present and zero. Two supporting validations: a PO with zero taxable subtotal but
**non-zero** tax is **malformed** — reject at load, naming it — and a PO or invoice with an **absent or null**
tax field is likewise malformed, since absent must never be confusable with zero.

Also: **pin the `Decimal` context precision** to a declared constant, and give **reported ratios** (precision,
recall, FP-per-invoice) an explicit output precision with `ROUND_HALF_UP`. Those are divisions whose bytes fall
under the byte-identical comparison — left at ambient precision, U4 is unenforceable.

**Inputs fingerprint (D27).** The scorecard embeds an **aggregate digest of the dataset inputs**, alongside the
findings-artifact and answer-key digests. Without it, an edited input under an unchanged key and version scores
differently while provenance looks identical — which defeats verify-by-recompute entirely. Algorithm, exactly:
every file under `inputs_dir` recursively → path normalized **relative, forward slashes** → sorted byte-wise →
each file's **raw bytes** digested (no text transformation; these are PDFs) → hash the concatenated
`path + digest` pairs. On a verify mismatch, recompute per-file and report which files diverged.

⚠️ **Mark dataset files binary / `-text` in `.gitattributes`.** If `autocrlf` touches the JSON inputs, Windows
and Linux checkouts hold different bytes, the digest diverges, and the cross-platform requirement fails looking
like a harness bug.

**Expected tax (D24).** `expected_tax = po_derived_rate × invoice_taxable_subtotal` — the invoice's **own**
subtotal, not the payable one. Using the payable subtotal would cascade: any price or quantity error changes
the correct tax base, so one root cause would produce both its own finding *and* a `TAX_VARIANCE`, polluting
per-category recall. A seeded price error must therefore produce **no** tax finding.

**Zero-expectation cases (D25).** `precision = TP/(TP+FP)`, and on the control `TP = 0`:
- No flags at all → `0/0`, undefined → emit **`null`**.
- Flags raised → `0/N = 0.0`, **defined** → emit `0.0`. Do not suppress it; that is the result carrying the signal.
- **Recall is `null` unconditionally** on a zero-expectation case.
- Undefined is always `null` — never `0` (reads as failure when the run was perfect), never an omitted key
  (unstable field breaks byte-identical comparison).

**Duplicate contention (D26).** Two findings contending for one expectation are identical on the match key, so
the tie-break **cannot change any metric** — one TP and one FP either way. It exists purely for output
determinism. Order contending findings by a **canonical serialization** of each whole finding and take the
first; **never by position in the findings artifact**, which would break order-reversal invariance. Report the
duplicate-contention count as its own diagnostic — duplicates still count as FPs, but an agent emitting them
has a bug worth surfacing.

**Timestamps.** UTC ISO-8601 with a `Z` suffix at second precision, everywhere. Dataset timestamps are
seeded and fixed, never wall-clock. Only the scorecard run stamp reads the real clock.

**Clean-room terminology.** The strings "reconciliation agent" and "iTradeNetwork" must not appear anywhere
in this repository. Reuse *patterns* from `practice--reconciliation-agent-manual-from-scratch-app`
(Decimal discipline, deterministic finding identifiers, append-never-insert for positionally-indexed
records) but do not import from it or copy its terminology.

## NEVER do unattended — human checkpoint required

- **Never modify, move, or delete any dataset, answer-key, or fixture file.** All inputs are strictly
  read-only; a run that mutates them invalidates every prior comparison.
- **Never delete or overwrite a prior scorecard.** They are the durable record.
- **Never commit or push** without the author's explicit approval of the commit message.
- **Never route around a denied answer-key read.** If a deny-guard refuses access, the refusal is correct and
  is the mechanism working — not an obstacle to solve. Do not attempt it via Bash, a helper script, or a
  subagent.
- **Never place any part of the held-out split inside the repository tree** — not the answer key, not the
  generators, not the discrepancy-design artifact, not the dataset inputs. `.gitignore` is not sufficient:
  it hides a file from git, not from the filesystem or from a reading agent.

## Phase-1 acceptance gate

Do not mark this phase complete until every criterion below **passes by execution**, not by inspection.

**Happy path**
- [ ] Findings artifact containing exactly the expected findings scores recall 1.0 and precision 1.0 in every
  category.
- [ ] Scorecard emitted both as parseable JSON and as a human-readable summary.
- [ ] Scorecard records dataset identifier and version.
- [ ] Scorecard embeds four fingerprints: findings artifact, answer key, structured invoice index, and the
  aggregate inputs digest.
- [ ] Editing the invoice index alone changes its recorded fingerprint.
- [ ] Regenerating the dev split's PDFs from the same seed yields byte-identical files and an unchanged inputs
  digest.
- [ ] No PDF or document-parsing library is importable from the scoring engine.
- [ ] A scan of the agent-readable inputs confirms the invoice index is absent from them.
- [ ] Editing one byte of one input, with key and version untouched, changes the aggregate inputs digest.
- [ ] A verify mismatch names which input files diverged, not just that the aggregate differed.
- [ ] The aggregate inputs digest is identical computed on Windows and on Linux from the same data.
- [ ] A non-terminating tax rate yields the same verdict under two different `Decimal` context precisions.
- [ ] Tax charged against a zero taxable subtotal flags at `>= $0.05`.
- [ ] An invoice against a fully exempt PO, correctly showing `Tax: 0.00`, produces **no** finding — the case
  the cross-multiplied form alone would have flagged.
- [ ] The same invoice charging `$0.05` flags, and charging `$50.00` flags, proving `inv_tax` is not annihilated.
- [ ] A PO with zero taxable subtotal and non-zero tax is rejected as malformed, naming that PO.
- [ ] A PO or invoice with an absent or null tax field is rejected as malformed, not treated as zero.
- [ ] No division is reachable from any flagging decision — asserted by scanning the scoring path.
- [ ] Reported ratios emit at the declared precision, and a run under a different ambient decimal precision
  produces a byte-identical scorecard.
- [ ] Zero-defect control with an empty findings artifact reports false-positive count 0, rate 0.0, precision
  `null` and recall `null`.
- [ ] The same control scored against three spurious findings reports precision `0.0` — not `null` — and recall
  still `null`.
- [ ] Every undefined metric is emitted as `null`; none is emitted as `0` or omitted.
- [ ] On a $500 basis (2% = $10.00 exactly) a $10.00 variance flags and $9.99 does not; on a $333.33 basis
  (2% = $6.6666) a $6.67 variance flags and $6.66 does not.
- [ ] A seeded price error on a taxable line yields exactly one finding, in `PRICE_VARIANCE`, with no
  `TAX_VARIANCE`.
- [ ] Two duplicate findings for one expectation report a duplicate-contention count of 1, distinct from the
  plain FP total, and the scorecard is byte-identical when the two are swapped in the input.
- [ ] A value ending in exactly half a cent rounds away from zero, confirming `ROUND_HALF_UP` rather than the
  `Decimal` default.
- [ ] Seeded tax overcharge on the correct line scores as a true positive under `TAX_VARIANCE`.
- [ ] Seeded goods-receipt under-shipment on the correct line scores as a true positive.
- [ ] Seeded goods-receipt over-shipment on the correct line scores as a true positive.
- [ ] `run_metadata` carries the run timestamp and load/score/total durations, and **nothing else**.
- [ ] Invoice count and finding count live in the **scored body**, and altering either changes the byte
  comparison — proving they are protected by it rather than excluded (D18).
- [ ] Every field in `run_metadata` is non-deterministic — excluding it alone suffices to make two runs
  byte-identical.
- [ ] The three quantity categories each score correctly on a purpose-built line, and a short shipment
  billed correctly for what arrived produces no finding at all.
- [ ] A variance exactly equal to the threshold flags; one cent below it does not.
- [ ] A $26 variance on a $100,000 extended line flags, confirming the $25 cap governs large lines.
- [ ] A line with both a wrong price and a wrong quantity yields one price finding measured at the payable
  quantity plus one quantity finding, neither absorbing the other's dollars.
- [ ] A `TAX_VARIANCE` scores as one document-scoped finding — not duplicated across taxable lines, not
  rejected for lacking a line id — and is assessed against the taxable subtotal.
- [ ] A document-scoped finding with an absent or empty line id is rejected as malformed, not inferred.
- [ ] A line-scoped and a document-scoped finding sharing status, category and document id do not match each
  other, proving `scope` is part of the key.
- [ ] The 2% term uses the payable extended amount: a line short-shipped to a tenth of its ordered quantity
  flags a variance the ordered-quantity basis would have passed.
- [ ] The answer key carries invoice→PO→receipt correspondence for every line, and a scan of the
  agent-readable inputs confirms it is absent there.
- [ ] Reordering lines within an invoice input file changes no line identifier and no finding.
- [ ] The human-readable summary names each missed finding and each false flag individually.

**Edge cases**
- [ ] Omitting one expected finding records a miss and reduces that category's recall by exactly one over its
  expectation count.
- [ ] Adding one spurious finding records a false positive and reduces precision accordingly.
- [ ] Two findings contending for one expected finding yield exactly one true positive and one false
  positive, **and the scorecard is identical when the findings artifact order is reversed.**
- [ ] Correct category with wrong `TargetLine` is not a true positive under strict matching; it counts as
  both a false negative and a false positive.
- [ ] A finding referencing a non-existent line is a false positive labelled as referencing a non-existent
  target.
- [ ] A finding with status `MATCH` is not counted as a false positive.
- [ ] A malformed findings artifact halts, exits non-zero, names the offending finding and field, and writes
  no scorecard.
- [ ] A category outside the closed enumeration halts as a schema violation.
- [ ] A missing or unreadable dataset halts, exits non-zero, names the dataset, and writes no partial score.
- [ ] An unreadable answer key halts and exits non-zero rather than passing by default.
- [ ] A dataset timestamp lacking the `Z` suffix or second precision is rejected as malformed.

**Constraint validation**
- [ ] Same dataset version and findings artifact scored twice produce byte-identical scorecards apart from
  `run_metadata`.
- [ ] pyright reports zero errors.
- [ ] Import scan confirms the scoring engine imports only standard-library modules.
- [ ] Scan confirms no `float` on any monetary path.
- [ ] Scan confirms no networking or model-client import anywhere in the scoring path.
- [ ] Guard-configuration check passes on the shipped deny rules, and fails naming the path when a secret path
  is deliberately removed from coverage.
- [ ] Placement check passes on a clean tree and fails when a decoy secret is planted inside the repo, including
  beneath an ignored directory.
- [ ] No shipped check claims to test harness enforcement by executing code; the dated attestation record exists.
- [ ] A PO line delivered across two receipts sums both; a key built from one is demonstrably different.
- [ ] The dev split carries a fully exempt PO, a $500 line and a $333.33 line at plausible values; the $100,000
  line appears only in a synthetic fixture, and every synthetic fixture is labelled as such.
- [ ] A repository scan finds no held-out answer key, generator, discrepancy-design artifact, or held-out
  dataset input at any path, including under ignored directories.
- [ ] The agent context **can** read held-out dataset inputs while **cannot** read the held-out answer key —
  assert both halves.
- [ ] The full acceptance suite passes using only the repo's dev split, with no out-of-tree path configured.
- [ ] Scan confirms zero occurrences of "reconciliation agent" and "iTradeNetwork" in the repository.
- [ ] No input dataset or answer-key file is modified by any run, verified by comparing file hashes before
  and after.

## Record-keeping obligations

- Append any architectural call the spec did not cover to the spec's **`## decisions made`** block.
- If a decision represents a genuine fork (options existed and you chose one), **also append it to
  `DECISIONS.md`** in the same format as D0–D12: fork, options considered, decision, why. That file is the
  project's reasoning record and must not go stale.
- If the spec itself changes, add a **changelog** line and **bump the spec version** in metadata.
- Do not add features outside the spec's in-scope list. Do not use packages outside the constraints block
  without flagging first.

## Quality bar — the regeneration test

Could another agent rebuild this phase from the spec alone and produce behaviourally identical output? If
not, you have found what is missing — say so rather than papering over it.
