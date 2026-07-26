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
7. **Held-out split isolation** — placement outside the repo tree, deny-guards, and a **canary probe**
   proving the guarded area is unreachable from an agent context. **Read the tier table below before
   implementing this; getting the guard scope wrong breaks evaluation rather than protecting it.**
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
- [ ] Scorecard embeds SHA-256 fingerprints of the findings artifact and the answer key.
- [ ] Zero-defect control with an empty findings artifact reports false-positive count 0 and rate 0.0, and
  reports no precision figure.
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
- [ ] Canary probe confirms the guarded area is unreachable from an agent context; a reachable canary fails
  loudly and exits non-zero.
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
