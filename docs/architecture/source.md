---
title: goldset-triad-harness — Architecture and Workflow Report
short_title: goldset-triad-harness
subtitle: A deterministic, held-out golden-dataset harness that scores an accounts-payable matching agent against an answer key kept outside the agent's repository and behind access rules
repo: https://github.com/hmbseaotter/goldset-triad-harness
commit: 303ee4f
date: 2026-10-29
---

# Executive summary

`goldset-triad-harness` is a Python command-line tool that grades an AI agent doing **three-way matching** in accounts payable (AP). Three-way matching compares three documents for each purchase: the **purchase order** (what was ordered, at what price), the **goods receipt** (what actually arrived), and the supplier's **invoice** (what is being billed). An agent reads these documents and reports discrepancies, such as an inflated unit price or a bill for goods that never arrived. The harness compares the agent's reported findings against an **answer key** of known-correct findings and emits a **scorecard**: precision and recall per discrepancy category, a false-positive rate, and a named list of every miss and every false flag.

The project name explains itself. A **golden dataset** ("goldset") is a set of inputs whose correct answers have been fixed and audited in advance. **Triad** refers to the three documents. **Held-out** data is kept out of development and publication; the agent reads its inputs only when evaluated and never sees its key, so its score measures real ability, not memorization.

Two ideas carry the whole design:

1. **Every number can be re-derived.** Scoring involves no model call, no network call, no randomness and no floating-point arithmetic. The same inputs always produce a byte-identical scorecard apart from its timing block, and CI observes this on Windows and Linux for the dev split. Each scorecard embeds SHA-256 fingerprints of what it scored, so a separate `verify` command can recompute it and say exactly what, if anything, differs.
2. **The answer key is kept out of the repository.** The held-out answer key, the generators and the notes on where errors were planted live in a separate folder outside the repository tree. A second folder holds the held-out inputs, so the harness sits in a **three-tier layout**. Claude Code permission rules add a second layer of protection.

::: M
Placement keeps the key out of the repository, its history and anything published from it. It does not put the key out of reach on the same machine. The permission rules refuse certain reads by a correctly rooted session. The project argues a script cannot test whether those rules bind, so their effect is attested by hand.
:::

::: M
The repository is small in code and large in reasoning. About 3,950 lines of Python implement the harness, with no third-party runtime dependencies. Around them sit 329 tests, a 2,069-line specification, and a decision record of 124 numbered entries (D0 to D123). The decision record explains every design fork, including decisions later overturned. The specification calls phase 1, which built the scoring core, "the credibility core": its purpose is a score that a skeptical reader can check.
:::

# Context and problem

The README states the problem directly: evaluating an AP agent usually degrades into eyeballing its output. A prompt change improves one invoice and quietly breaks another, and nobody notices until totals stop adding up. What is missing is a verdict that can be re-derived.

So the design goal is **falsifiability**, not cleverness. A score is useful only if someone who distrusts it can recompute it from the inputs it names. That one goal explains most of the architecture:

::: S-only
That goal explains the main choices: no AI model runs at scoring time, money is never a floating-point number, the scorer never derives expected findings itself, and the held-out key lives outside the repository.
:::

::: M
- It explains why no AI model runs at scoring time. A model's judgment is not reproducible, so it cannot produce a re-derivable verdict.
- It explains why money is never a floating-point number. A float cannot represent most cents exactly, and rounding drift would break byte-identical output.
- It explains why the scorer never derives expected findings itself. If it did, any bug in its logic would silently become ground truth.
- It explains why the held-out answer key lives outside the repository. A key the agent could read would make every held-out score meaningless.
:::

::: M
The project is a portfolio piece built specification-first. The specification was written through a structured interview tool (it records "Produced by: /specify"), and the decision record began before any code. The specification organizes work into five phases. Phase 1 (`[P1]`, the "credibility core") and phase 2 (`[P2]`, tooling: verify mode, run ledger, documentation, continuous integration) are built. Phases 3 to 5 (larger datasets, compliance categories, audience expansion) are planned, and the specification deliberately writes no requirements for phases 4 and 5 until a real consumer has produced a held-out scorecard (decision D110).
:::

# Repository map

The repository holds 88 tracked files.

| Path | What it is | Why it exists |
|---|---|---|
| `src/goldset_triad/` | The harness package (12 modules) | Loading, validation, scoring, scorecards, verify, ledger, key audit, isolation checks |
| `tests/` | 27 test modules plus a shared `support.py` | 329 tests; about half mapped to acceptance criteria, the rest explicitly exempted |
| `datasets/` | Three public dev splits | Data every check and CI run uses; shipped with their answer keys |
| `docs/` | Runbook, scorecard field reference, example findings | Operating instructions and a reproducible worked example |
| `specs/` | Specification and two phase build prompts | The requirements and acceptance criteria |
| `DECISIONS.md` | Decision record, D0 to D123 | Why each choice was made, including reversals |
| `ISOLATION_ATTESTATION.md` | What is checked by code, by a human, or by neither | The honest account of the isolation claim |
| `.claude/settings.json` | 29 Claude Code deny rules | Second-layer guard against reading the secret tier |
| `.github/workflows/ci.yml` | Continuous integration | Tests, type checks and a cross-platform byte comparison on every push |

::: L
The twelve modules in `src/goldset_triad/`, with approximate line counts:

| Module | Lines | Role |
|---|---|---|
| `cli.py` | 376 | The `goldset-triad` command: `score`, `verify`, `rebuild-ledger` |
| `schema.py` | 323 | The findings format: parsing and strict validation |
| `dataset.py` | 842 | Resolving a dataset and validating it at load (all parts but the policy) |
| `scoring.py` | 225 | The matching and counting engine |
| `scorecard.py` | 302 | Building, serializing and summarizing the scorecard |
| `verify.py` | 530 | Recomputing a stored scorecard and naming differences |
| `ledger.py` | 257 | The derived run ledger |
| `audit_key.py` | 374 | Independent re-derivation of the answer key |
| `check_isolation.py` | 542 | Guard-configuration and placement checks |
| `jsonio.py` | 126 | The single file reader every module uses |
| `constants.py` | 32 | Declared precision, rounding and sentinel values |
| `__init__.py` | 22 | Version and a summary of the component split |

Other top-level files: `pyproject.toml` (package metadata and the three console scripts), `pyrightconfig.json` (type-checker settings targeting Python 3.11), `.gitattributes` (exempts every dataset file from line-ending conversion), `.gitignore` (which also lists secret filenames as a backstop), and `LICENSE` (MIT).
:::

# Architecture

The harness separates four components that most evaluation tools merge. The package's own docstring lists them, and decision D35 explains the separation.

1. **Scoring engine** (in this repository). It loads the answer key and the invoice index, matches findings and counts results. It contains no domain rule at all.
2. **Key generator** (outside the repository, in the secret tier). It applies the domain rules, writes the documents, and authors every answer key.
3. **Key-audit command** (in this repository, never imported by scoring). It re-derives expected findings by a separate implementation of the rules and reports any disagreement with the key.
4. **Matching policy** (a data file in each dataset). It publishes every rule the generator applied, so an agent competes against rules it can read.

![Architecture: the scoring path in the middle, the independent audit and isolation checks beside it, and the out-of-tree generator that authors every dataset](diagrams/architecture.dot)

The scoring path is a straight line. The command resolves a dataset, validates it, parses the agent's findings, scores them, writes a scorecard pair, and appends a ledger record. Two side tools never touch that path. The key audit checks the key, and the isolation checker checks the guards.

::: M
## The three tiers

The harness is one of three folders, which the runbook calls "the three repositories". The two others are separate git repositories that are never published. The decision record says the secret tier is pushed to a remote; the harness cannot show where that remote is hosted.

| Tier | Holds | Agent may read? | May be published? |
|---|---|---|---|
| `goldset-triad-harness` | Scorer, tests, public dev splits | Yes | Yes |
| `goldset-triad-holdout` | Held-out **inputs** (documents only) | **Yes**, it must | **No** |
| `goldset-triad-secret` | Held-out answer key and invoice index, generators, discrepancy plan, a canary file, the deny-rule template | **No** | **No** |

The middle row is the subtle one. The agent has to read the held-out inputs to produce findings, so no guard may block them. But those inputs, plus the published matching policy, are enough to derive the answer key mechanically. So "readable by the agent" and "publishable" are different properties. The harness code encodes this split: `check_isolation.py` keeps separate locators and separate rules for the secret tier and the held-out inputs tier.

By default each tier is found two folders above the harness (`REPO_ROOT.parents[1]`). Environment variables `GOLDSET_TRIAD_SECRET_DIR` and `GOLDSET_TRIAD_HOLDOUT_DIR` override that.
:::

::: S-only
The held-out data is split across two folders outside the repository. One holds the held-out **inputs**, which the agent must be able to read but which must never be published. The other, the **secret tier**, holds the held-out answer key, the generators and the design notes, which the agent must never read. Placement outside the repository is the primary protection; deny rules, a configuration check and a hand-run attestation add layers.
:::

# Components in detail

## The findings format (the "port")

An agent communicates with the harness only through one JSON file, the **findings artifact**. The project calls it "the port" (decision D1, borrowed from the ports-and-adapters pattern), because any agent that writes it can be scored, and the harness never runs the agent. Each finding names:

- a `status`: `DISCREPANCY`, or `MATCH` to assert that nothing is wrong;
- a `category`: exactly one of five;
- a `scope`: `LINE` or `DOCUMENT`;
- a `target`: the invoice's `document_id` and a `line_id`. A document-scoped finding must carry the reserved line id `__DOCUMENT__`.

An optional `confidence` (a JSON number from 0 to 1) and `reasoning` (text) are carried into the scorecard but never scored.

::: M
Validation in `schema.py` is strict, and every rejection names the finding's index and the field:

- The artifact must declare `"schema_version": "1"` as a string. A missing version is rejected rather than assumed (D78), and a number is rejected with a message naming the type.
- Unknown **values** in a closed set (status, category, scope) halt the run, because silently dropping one would make the score confidently wrong (D109).
- Unknown **fields** are accepted and ignored, at every level. The README presents this as a guarantee an agent can build on.
- A document-scoped finding without the sentinel, or a line-scoped one using it, is rejected.
:::

The five categories are a closed list owned by the harness: `PRICE_VARIANCE`, `QTY_UNDER_SHIPMENT`, `QTY_OVER_SHIPMENT`, `QTY_INVOICE_INFLATED` and `TAX_VARIANCE`.

## Dataset loader and validation

`dataset.py` turns a dataset name, or a path to a `manifest.json`, into everything the scorer needs. It validates the key, the invoice index, the purchase orders and the goods receipts before scoring. A dataset consists of:

- a manifest naming the inputs folder, the answer key and the invoice index;
- an `inputs/` folder with purchase orders (JSON), goods receipts (JSON) and invoices (PDF);
- an answer key with `expected_findings` and a `correspondence` table;
- a **structured invoice index**, the invoices' line data as JSON;
- a published `matching_policy.json` beside the manifest, which the loader does not read.

The scorer **never parses a PDF**. Invoice line data comes from the invoice index. In a held-out split that index is itself secret, because it is the correct extraction answer.

::: M
The loader rejects a malformed dataset before any score exists. Each check cites a decision, and several were added after a real defect was found:

- Every timestamp is UTC, second-precision and `Z`-suffixed (D6). Every purchase order and invoice carries a tax field, even when it is zero (D29).
- Every line has a real boolean `taxable` flag. An absent flag once silently changed a tax subtotal (D117).
- A document's own identifier must match its filename, so a copied file cannot have two identities (D71).
- Every expected finding must point at a line that exists. Otherwise it would count as a permanent miss against every agent (D50).
- Every invoice line has exactly one correspondence row, and every row resolves to a real invoice line, purchase order and purchase-order line (D48, D50, D56).
- An invoice spanning several purchase orders with different tax rates is rejected, because how to apportion tax across them is unspecified (D47).

All reads go through one reader, `jsonio.py`. It reads UTF-8 (tolerating a byte-order mark), parses numbers as exact decimals, and names the specific failure: missing, unopenable, not text, or not valid JSON (D77, D94).
:::

## Scoring engine

`scoring.py` matches and counts, and contains no domain rule. The match key is strict: **status, category, scope, document and line** must all agree. Matching is one-to-one.

::: S-only
A `MATCH` entry is set aside, so a wrong assertion counts once, as a miss. A flag naming a line that does not exist is a false positive. When several flags compete for one expectation, the tie is broken by sorting the findings' full text rather than by file order, so reordering the agent's file never changes the score. Precision and recall that would divide by zero are reported as undefined (`null`), never as zero.
:::

::: M
The engine works in five steps:

1. It sets `MATCH` entries aside entirely. They assert correctness, so they can neither be a false positive nor satisfy an expectation. A wrong assertion is counted once, as the miss it already is (D13).
2. It labels any flag whose target is not a real line in the invoice index a false positive with the reason `nonexistent_target`.
3. It groups the remaining flags and the expectations by match key.
4. Within each key it sorts the flags by a canonical string of the whole finding and pairs them one-to-one with expectations. Extra expectations become misses. Extra flags become false positives, labeled `duplicate_contention` when the key had an expectation and `no_match` otherwise. Sorting by content rather than by position means a reversed findings file scores identically (D26).
5. It computes precision and recall overall and per category, plus a false-positive rate per invoice.

The null rules (D25) matter for reading results. Recall is `null` where a category has no expectations. Precision is `null` only where the agent raised no flag in that category; if it raised flags and all were wrong, precision is a real `0.0000`. Flagging comparisons are exact. Reported ratios are computed in Python's `Decimal` type at a pinned 28-digit precision and rounded half-up to four places when written out.
:::

## Scorecard

`scorecard.py` writes two files per run: a JSON scorecard and a plain-text summary that names every miss and false flag. The JSON is the durable record. Its sections:

- `dataset`: the split's identifier and version.
- `fingerprints`: SHA-256 digests of the findings file, the answer key, the invoice index, and all input files combined.
- `workload`: invoice and finding counts.
- `coverage`: which categories this dataset can measure at all.
- `metrics`: the overall and per-category results.
- `missed` and `false_flags`: each item individually.
- `run_metadata`: the timestamp and timings.

`run_metadata` holds exactly the non-deterministic fields and nothing else, so everything outside it must be byte-identical between runs on the same inputs.

::: M
Determinism is enforced at every step that could leak platform or ordering differences:

- Keys are sorted and ratios are emitted as exact strings, so no float ever reaches the output.
- Files are written with LF line endings, using exclusive-create mode, so an existing scorecard can never be overwritten (D49).
- Two runs in the same second get an ordinal suffix (`-2`, `-3`). A race between processes is retried up to eight times and then halts with a named cause (D114).

The **coverage block** (added in scorecard schema version 2, D60) exists because `null` alone is ambiguous. A dataset that holds no expectations in a category cannot measure it, and the scorecard says so rather than letting three nulls read as flawless work. On the zero-defect control, `measures_recall` is `false`, and the summary says recall is undefined there by construction.
:::

::: L
### Reading a scorecard correctly

`docs/SCORECARD.md` defines every emitted field and names the misreading each subtle one invites. A test keeps that reference complete against the code (D100). Five points matter most:

- **The three false-positive counters are not alternatives.** `false_positive_count` is the total. `duplicate_contention_count` and `nonexistent_target_count` are diagnostics that pick out two particular defects inside it. Contention counts surplus flags competing for a real expectation; flags that merely share a key with no expectation are ordinary false positives, not contention (D55).
- **`false_positive_rate` is per invoice,** not per finding. The zero-defect control relies on this: it divides false flags by the number of invoices.
- **`precision: null` and `precision: "0.0000"` are different verdicts.** The first means no flag was raised; the second means every flag raised was wrong.
- **`missed[].reasoning` is the answer key's note, not the agent's.** On the dev split it reads like "seeded PRICE_VARIANCE on INV-2001 line 2". This is why a held-out scorecard counts as answer-key content.
- **Time is reported, never judged.** The reference states that exceeding a performance target would warn and still exit zero, because how long scoring took does not change whether it was right. The specification schedules that budget, as a warning, for phase 3.

The reference also lists what a scorecard deliberately leaves out. It contains no runtime judgment, no calibration verdict on `confidence`, and no claim that the key is correct; that is the audit's job, and the audit claims consistency only. There is no "cannot adjudicate" outcome either. An agent that correctly declines to decide, for example on an invoice with no resolvable purchase order, has no way to say so and would be scored as missing a finding. The datasets currently guarantee such cases never occur (D96), and the outcome class is scheduled for phase 4 (D97).
:::

## Verify, ledger, key audit and isolation check

These four tools sit around the scoring path:

- **`verify`** recomputes a stored scorecard from the dataset and findings file named again on the command line. It reports the first outcome that applies.
- **The run ledger** is a JSON-lines file of one record per run, a convenience view. It can be rebuilt from the scorecards alone.
- **`goldset-triad-audit-key`** re-derives expected findings from the inputs using its own copy of the rules and lists every disagreement with the key.
- **`goldset-triad-check-isolation`** checks that the deny rules are configured correctly and that no secret artifact sits inside the repository tree.

::: M
### Verify

A scorecard records fingerprints, not file paths, because a digest confirms identity but cannot locate a file. So the operator names the dataset and findings again. `verify.py` loads, validates and re-scores them, then compares the result with the stored scorecard. If the named dataset fails validation, verify stops with exit 2 and no verdict. Otherwise its outcomes are ranked, and it reports only the first that applies:

![Verify reports the first applicable outcome and stops](diagrams/verify_outcomes.dot)

The ranking keeps a reader from auditing arithmetic that was never wrong. "You named a different split" and "the inputs moved" are not the same claim as "the numbers differ". The README's table lists five outcomes; the code has a sixth, `summary-differs`. That outcome is reported when the JSON recomputes exactly but the human summary beside it was altered (D118). A summary file that is missing altogether is not treated as a difference. Exit codes are 0 for identical, 1 for any difference, and 2 when verify could not reach a verdict at all.

### Run ledger

`ledger.py` keeps `run-ledger.jsonl` beside the scorecards: one record per run, holding counts, headline metrics and timings. It is gitignored and local. Every field is taken from a scorecard, so `rebuild-ledger` regenerates it identically. Runs are ordered by timestamp and then by the ordinal as a number, not as text, so a tenth run in the same second does not sort before the second. If appending fails, the score still succeeds with a warning, because a derived view must not make a correct score fail (D75).

### Key audit

`audit_key.py` exists, in its own docstring's words, because the answer key is the riskiest artifact: scoring tests show the scorer agrees with the key, and nothing in them can show the key is wrong. The auditor runs the loader's validation first (D62). It then re-implements the threshold, payable-quantity and tax rules without sharing code with the generator, walks every correspondence row, and reports findings that are `DERIVED-BUT-ABSENT` from the key or `IN-KEY-BUT-UNDERIVED`. Both the module and the README call this "a consistency check, not a correctness proof": the generator and the auditor share an author, so the audit can catch slips and drift but not a shared misunderstanding. Exit codes are 0 consistent, 1 divergent, and 2 error.

### Isolation check

`check_isolation.py` runs two deterministic checks and prints two kinds of advisory:

1. **Guard configuration.** The deny rules in `.claude/settings.json` exist, parse, and cover the secret folder and every secret filename, and do not cover the held-out inputs. The generator filename patterns must also be anchored, so they do not block ordinary commands such as `regenerate` (D65).
2. **Placement.** No file or folder with a secret name exists anywhere in the repository tree, including ignored folders. Names are compared without regard to case or extension, so a stray copy such as a compiled `.pyc` is still caught (D45). A scorecard from any split not shipped in `datasets/` also fails, because a held-out scorecard lists missed expectations verbatim and is therefore answer-key content (D93, D104).
3. **Advisory `[durability]`.** An out-of-tree tier has uncommitted or unpushed work.
4. **Advisory `[guard-reach]`.** A parent folder carries its own Claude Code settings, so a session opened there would not load these rules (D91).

Advisories never change the exit code: 0 pass, 1 fail, 2 the checks could not run. Exit 2 also covers a missing `.claude/settings.json`, which is a real guard defect; a malformed settings file surfaces as an unhandled error rather than a named halt.
:::

::: L
### Inside verify's output

Verify reports differences by field path, such as `metrics.per_category.PRICE_VARIANCE.recall: stored X, recomputed Y`, rather than printing two documents for a reader to compare. Every list is capped at ten lines, followed by a count of the remainder (D79). A missing field in the stored scorecard is reported as a malformed scorecard, not as a value that disagrees.

When the combined inputs digest differs, verify faces a real limit. The scorecard stores only the aggregate digest, not one per file, so verify can list the current per-file digests but cannot say which file moved. Given `--baseline-inputs` pointing at a pristine copy of the inputs, it compares the two sets and names each changed, added or removed file (D27, D74).

### Naming as a security property

Several decisions show that file names carry part of the isolation burden:

- An early design told the held-out key from the public dev keys by capital letters alone (D38). On a case-insensitive file system those are the same name. Git's case-folding then made a `.gitignore` rule exclude all three public dev keys. The fix (D42) gave the held-out key a genuinely distinct name, `holdout_answer_key.json`. That let the deny rule for it be unscoped, so it catches a stray copy anywhere, and let the placement check compare names case-insensitively.
- The held-out invoice index was once named like the public indexes, so no filename rule could single it out. Renaming it `holdout_invoice_index.json` gave it the same protection as the key (D45).
- A public artifact's name may never be a substring of its held-out counterpart's (D51), and the list of secret names exists in exactly one place in the code (D52).
:::

# How it works: logical description and data model

The rules live in the generator and are published in each split's `matching_policy.json`. The scorer only compares findings with the key. The rules themselves are short:

- **Payable quantity** is `min(ordered, received)`, with received summed over all goods receipts for the line.
- **Materiality threshold**: `max($0.05, min(2% × basis, $25))`. A variance is flagged when it is at least the threshold. The 2% term and the $25 cap cross at a basis of $1,250; the $0.05 floor binds only below a $2.50 basis.
- **Price variance**: `(invoice price − PO price) × payable quantity`, measured against a basis of `payable quantity × PO price`.
- **Quantity over-billing**: invoiced quantity above payable quantity, valued at the PO price. The category names the constraint that capped the payable quantity: short shipment, over-shipment, or a plain inflated invoice.
- **Tax variance** (document-scoped): expected tax is the PO's tax rate applied to the invoice's own taxable subtotal. It is compared by cross-multiplying, never dividing.

The README is explicit that these thresholds are "this harness's thresholds and this harness's reasoning", not a claimed industry standard.

::: M
Two discipline rules sit under the arithmetic. Every flagging comparison is made at full decimal precision, with no rounding beforehand. No flagging decision divides (D28); the tax test is cross-multiplied, which is why the auditor refuses a negative taxable subtotal, where cross-multiplication would invert the comparison (D117). A short shipment billed correctly for what arrived is not a finding: a shipment problem with no billing impact is out of scope by design.
:::

## A worked example from the public dev split

Invoice `INV-2001` in `datasets/dev` bills six lines against purchase order `PO-3001`, and all goods arrived. Four lines sit around the threshold, two on each side:

| Invoice line | PO price | Invoiced price | Variance | Threshold | Expected finding |
|---|---|---|---|---|---|
| 3 | 500.00 | 510.00 | 10.00 | 10.00 (2% of 500) | `PRICE_VARIANCE` |
| 4 | 500.00 | 509.99 | 9.99 | 10.00 | none |
| 5 | 333.33 | 340.00 | 6.67 | 6.6666 (2% of 333.33) | `PRICE_VARIANCE` |
| 6 | 333.33 | 339.99 | 6.66 | 6.6666 | none |

Line 2 (20 units at 42.50 against 40.00, a variance of 50.00 against a threshold of 16.00) is also flagged. The answer key therefore holds three price findings for this invoice, on lines 2, 3 and 5. An agent that rounds before comparing, or derives a percentage by division, can disagree at exactly these boundaries, and the published policy warns of this.

::: M
## Data model

![How a dataset's parts relate: the manifest names the inputs, key and index, and the answer key's correspondence table links each invoice line to one purchase-order line and its receipts](diagrams/data_model.dot)

The **correspondence** table is part of the answer key, not the inputs (D22). Each row maps an invoice line to exactly one purchase-order line and lists the goods receipts that cover it. The agent has to work this mapping out from the documents. The key states it, so the auditor can re-derive findings line by line, and the loader can check that every invoice line is covered.

The three public splits:

| Split | Invoices | Invoice lines | Expected findings | Purpose |
|---|---|---|---|---|
| `dev` | 4 | 16 | 9 (all five categories) | Realistic data, shipped with its key |
| `dev-synthetic` | 1 | 1 | 1 (price variance) | Values implausible in the domain, labeled `synthetic` |
| `dev-zero-defect` | 1 | 2 | 0 | The control for over-flagging |

The held-out split is out of reach of this report by design. The folder listing of the held-out inputs shows one purchase order, one goods receipt and one invoice. The runbook's sample generator output reports 2 expected findings on 1 invoice, and a code comment in `scorecard.py` says that, at phase 1, it exercised two of the five categories.
:::

::: L
## Document shapes

Every document is JSON except the invoice PDFs. Field names below are taken from the shipped dev split.

| Artifact | Top-level fields | Line fields |
|---|---|---|
| Purchase order | `po_number`, `supplier`, `supplier_category`, `ship_to`, `currency`, `tax`, `timestamp` | `line_no`, `item`, `qty_ordered`, `unit_price`, `extended`, `taxable`, `uom` |
| Goods receipt | `grn_number`, `po_number`, `received_by`, `timestamp` | `po_line_no`, `part_number`, `description`, `qty_received` |
| Invoice index entry | `invoice_id`, `po_number`, `supplier`, `tax`, `taxable_subtotal`, `timestamp` | `line_id`, `qty_invoiced`, `unit_price`, `extended`, `taxable` |
| Answer key | `dataset_identifier`, `dataset_version`, `synthetic`, `expected_findings`, `correspondence` | correspondence rows: `invoice_id`, `invoice_line_id`, `po_number`, `po_line_no`, `grns` |
| Manifest | `identifier`, `version`, `inputs_dir`, `key_path`, `invoice_index_path`, `synthetic`, `generator_sha256` | — |

In the shipped splits, money and quantities are written as decimal strings, such as `"56.39"`. The loader also parses any JSON number as an exact decimal, so no value becomes a float. A purchase-order line is `P1`, `P2` and so on, while an invoice line is `1`, `2`; the two numbering schemes are separate on purpose. The correspondence table is what connects them, and line ids are assigned explicitly rather than by position (D22).

The goods-receipt descriptions differ from the purchase-order wording. In the dev split, "Nitrile gloves L 10x100" on the order arrives as "Nitrile exam gloves, large" on the receipt, so an agent must reconcile documents the way a person does, by meaning and by part reference rather than by identical strings.

## How the generator makes data trustworthy

The generator is outside the repository, but several of its guarantees are visible from here:

- **One canonical record per document.** Each invoice PDF and its invoice-index entry are rendered from the same record, so they agree by construction (D36). After rendering, the generator reads the PDF bytes back and checks that key values appear in them. The traceability map's note on criterion H14 states this check's limits: it tests membership, not position, and covers only a subset of fields. The review that found this is decision D121.
- **Deterministic output.** Generation is seeded, and line endings are pinned to LF (D43). Regenerating without a rule change should produce no diff; the runbook makes that a routine check, and decision D90 records the first time it was verified.
- **A recorded fingerprint of its own source.** Each manifest's `generator_sha256` lets the staleness test notice a rule changed without regeneration (D58). The digest normalizes line endings so the same source checked out on two machines agrees (D63).
- **A published policy derived from the rule constants.** The policy file is generated from the same constants the rules use, never written by hand (D46), and a test checks that every rule the shipped code applies has a published entry describing what the code does (D53, D119).
:::

# Workflows

## Scoring an agent on the dev split

1. Install the package (`python -m pip install -e .`), or run modules with `PYTHONPATH=src`.
2. The agent, run separately, writes `findings.json`.
3. `goldset-triad score --dataset dev --findings findings.json --out scorecards` validates the dataset, scores, and writes `scorecard-dev-<UTC stamp>.json` and `.txt`.
4. The summary is printed. A ledger record is appended.
5. Any malformed input halts with a named cause, exit code 2, and no scorecard.

![The scoring workflow, from dataset resolution to the exclusive write of the scorecard pair](diagrams/scoring_workflow.dot)

::: L
The shipped `docs/example-findings.json` holds nine findings against `dev`. The README prints its result: overall precision and recall of 0.8889, one missed `TAX_VARIANCE` on `INV-2003`, and one false `PRICE_VARIANCE` on `INV-2002` line 4. A test executes every block the documents present as harness output, so this example cannot drift from what the harness prints (D102).
:::

## The held-out workflow

1. The agent reads the held-out inputs folder. It is not given the key.
2. The operator scores with `--dataset` pointing at the held-out manifest in the secret tier, and with `--out` **outside** the harness repository.
3. The scorecard is kept outside the repository. If it lands inside, the isolation check and the test suite fail afterwards, because a held-out scorecard reveals answer-key content (D93).
4. Later, `verify` recomputes it from the same three inputs.

::: M
## Verifying, auditing and checking isolation

- `goldset-triad verify --scorecard <file> --dataset <split> --findings <file>` recomputes a scorecard. `--baseline-inputs <folder>` lets it name which input file changed when the combined digest differs.
- `goldset-triad rebuild-ledger --out <folder>` rewrites the ledger from scorecards.
- `goldset-triad-audit-key --dataset dev` re-derives the key.
- `goldset-triad-check-isolation` runs the guard checks, from inside the repository or with `--repo-root`.

## Regenerating the datasets

Datasets are never edited by hand; the runbook states that the generator is the source of truth. When a rule changes, the operator:

1. confirms all three tiers are committed and clean;
2. runs the generator from the secret tier;
3. inspects `git status` in the harness. If no rule changed, there should be no diff, because generation is seeded and repeatable;
4. re-runs the audit and the tests, then commits all three tiers.

Each manifest records `generator_sha256`, a digest of the generator's source with line endings normalized (D58, D63). A staleness test compares it with the current generator source, so a rule changed without regeneration is caught. That test needs the secret tier, so it skips on a fresh clone.
:::

::: L
## Continuous integration

`.github/workflows/ci.yml` runs on every push and on demand, with read-only permissions. It has four jobs:

1. **tests**, on Ubuntu with Python 3.11 and 3.14. The job first asserts that every dataset file is exempt from line-ending conversion (`text: unset`); otherwise Linux and Windows checkouts would hold different bytes and the inputs digest would differ. It then runs the `unittest` suite. Two assertions guard against silently dropped tests. The number of tests run must equal the number of test methods the traceability module discovers by inspecting the test classes. The skip count must be non-zero, because a clone has no secret tier and the tier-dependent tests must be seen to skip rather than vanish.
2. **pyright**, pinned to version 1.1.411 in standard mode, the type gate (D39).
3. **scorecard**, on Ubuntu and Windows. It scores the dev split with a findings file derived from the shipped key.
4. **cross-platform**, which compares the two scorecards' deterministic bodies and human summaries byte for byte, using the shipped comparison code. This turns the central portability claim (criterion H17) from an argument into an observation (D72, D76).
:::

# Companion tiers

The two companions are separate git repositories in the directory two levels above the harness, unless an environment variable points elsewhere.

**The held-out inputs tier (`goldset-triad-holdout`)** holds only documents: purchase orders, goods receipts and invoice PDFs. There is nothing to run there. It must stay committed, because every held-out scorecard fingerprints exactly those bytes; if they were lost, every held-out result would become unverifiable.

**The secret tier (`goldset-triad-secret`)** is described here only from the harness's own documents; this report did not read it. According to the runbook it holds:

- the held-out manifest, answer key and invoice index;
- the generators: three Python files that write every split's documents and keys, using the ReportLab library for the invoice PDFs;
- the "discrepancy plan" recording where errors were planted;
- a **canary**, a decoy file with a unique marker and no answer-key content, used to test whether the deny rules bind;
- the template from which the harness's `.claude/settings.json` is stamped.

::: M
## How the tiers are isolated

![The three tiers and the layers that keep the answer key away from the agent](diagrams/tiers.dot)

Protection comes in layers, and the project is careful to say which layer proves what:

1. **Placement (primary).** The whole held-out split lives outside the harness tree (D14). This keeps the split out of the repository, its history and anything published from it, whatever agent software is used. It does not stop a process on the same machine from reading the folder; that is what the other layers address.
2. **Deny rules (second layer).** The 29 rules in `.claude/settings.json` (8 `Read` rules and 21 `Bash` rules) work at two levels. The `Read` rules refuse reading the secret folder and any secret filename, wherever it is; the filename rules are deliberately unscoped, so they also catch a stray copy. The `Bash` rules are narrower. Some refuse nine named commands (such as `cat`, `grep`, `Get-Content` and `python -c`) when aimed at the secret folder, and the others refuse any command naming a secret file. Other shell routes into the folder match no rule.
3. **Mirror guards.** According to the decision record (D120 to D123), sessions rooted in the secret tier or in the held-out inputs tier carry their own rules denying edits into the harness tree. They close the route by which answer-key content could be written into the public repository.
4. **Automated checks.** The isolation command and its tests check configuration and placement on every push.
5. **Human attestation.** The project argues that a script cannot test whether the rules bind a live session. A script runs below the tool-call layer the rules govern, so an attempt to open the canary would succeed whether the guards worked or not. Instead, a person opens a session in each tier and attempts reads and writes, recording the results in `ISOLATION_ATTESTATION.md`.
:::

::: L
The attestation log shows why the human layer matters. On 2026-07-27 a canary read **succeeded**: the session had been opened one folder above the repository, where these rules were never loaded. That incident produced the `[guard-reach]` advisory (D91). The latest entry, from 2026-07-28, records refused reads of secret content from all three roots. It also records refused writes into the harness from the secret and held-out roots; the harness root has no write rules, so no write was probed from there. The write probes are backed by a scope control: a write to an unguarded location succeeded, which shows the refusals came from the guards and not from a blanket restriction. The document also lists the shell path around the `Bash` rules as unprobed, and notes that no root denies writes **into** the secret tier.

| Date | Session rooted at | Result |
|---|---|---|
| 2026-07-26 | the harness | Canary read refused; held-out input readable. Later superseded. |
| 2026-07-27 | one folder above the harness | **Failed**: canary read succeeded because the rules were never loaded |
| 2026-07-27 | the harness | Pass on every route |
| 2026-07-28 | the secret tier | Mirror guard reads pass; writes not yet probed |
| 2026-07-28 | all three tiers | Reads refused from all three; writes into the harness refused from the secret and held-out roots, with a scope control |

The attestation makes one more methodological point. A refused write and a write that was never attempted leave the same trace: no file. So the log records the verbatim refusal message, not merely the absence of the probe file.
:::

# Running it

Python 3.11 or newer is required; scoring has no third-party dependencies. The README gives each command for both PowerShell and bash; bash forms are shown here.

```bash
python -m pip install -e .                                   # installs the 3 console scripts
goldset-triad score --dataset dev --findings docs/example-findings.json --out ./scorecards
goldset-triad verify --scorecard ./scorecards/<scorecard>.json --dataset dev --findings docs/example-findings.json
goldset-triad rebuild-ledger --out ./scorecards
goldset-triad-audit-key --dataset dev
goldset-triad-check-isolation
python -m unittest discover -s tests -t .                    # the test suite
PYTHONPATH=src python -m goldset_triad.check_isolation       # any command, without installing
```

Run them from the repository root, or pass `--datasets-root`. They are reproduced from the repository's documentation and were not executed for this report.

::: L
A dataset identifier such as `dev` resolves against `--datasets-root`, which defaults to the relative path `datasets`, and `--out` defaults to `scorecards`. `rebuild-ledger` also accepts `--ledger` to write the ledger elsewhere.
:::

::: M
An AI coding agent working on the repository must be launched from the repository folder itself. Permission rules load from a session's own root, so a session opened in a parent folder does not load the deny rules. The README states this in a warning at the top.
:::

::: L
# How the project keeps itself honest

The repository applies to itself the same rule it applies to agents: a claim is worth what the check behind it is worth. Much of the test suite therefore checks the project's own statements rather than its arithmetic.

## The specification and its criteria

The specification is written in **EARS** (the Easy Approach to Requirements Syntax), so each requirement is a sentence containing **SHALL**. Requirements are grouped by trigger:

- ubiquitous (always active);
- event-driven (WHEN);
- state-driven (WHILE);
- unwanted behavior (IF, for errors);
- optional features (WHERE);
- non-functional.

Each acceptance criterion carries a phase tag such as `[P1]`. The test suite refers to criteria by identifier: `H` for happy-path cases, `E` for edge cases and `C` for constraint validation. Criterion H17, for example, is the cross-platform byte-identity claim. Two build prompts in `specs/` hand phase 1 and phase 2 to a fresh building agent, instructing it to read the specification and the decision record first: D0 to D12 for phase 1, the whole record for phase 2.

## Traceability in both directions

`tests/test_traceability.py` maps criteria from phases 1 and 2 to the tests that cover them, and asserts that each named test exists. The map has 172 entries naming 160 distinct tests. Five entries are marked `MANUAL:` with the reason:

- two concern the out-of-tree generator;
- two are the cross-platform claim (H17, and its phase 2 restatement C74), which the CI comparison job now observes;
- one is the type checker, which runs separately.

The mapping is checked in both directions (D54). Every entry needs a test, and every test method must be mapped to a criterion or listed in an explicit exemption set, which holds 173 supporting tests such as positive controls and internal invariants. Agreement with the specification is checked by count: the number of `[P1]` criteria in the specification must equal a constant in the test file. No check matches each criterion's text to its entry.

## Claims, scanners and sweeps

Several mechanisms keep documents and code from drifting apart:

- **A claim registry (D67).** `tests/test_claim_coverage.py` lists what each artifact claims and the check that compares it, on every split. Its origin is recorded candidly: the rule "every claim gets a check" was first written in D59 and broken in the same commit.
- **Defect-class scanners (D68).** When a kind of defect has been eliminated, a scanner locks it at zero. Most scanners live in `tests/test_defect_classes.py`, though not all: the check for text reads that rely on the platform's default encoding is in `tests/test_coverage_reporting.py`. Another example is absence silently turning into a default value. Each scanner must state the set of files it covers and assert that set is non-empty, because a scanner over nothing passes forever (D82).
- **A rule line on every decision.** From D67 on, every decision ends in a **Rule** naming what enforces it: a test, a scan, or the words "judgment, not checkable". The decision record says a `lint_spec.py` script enforces this; that script is not in this repository.
- **Published documents are bound to reality.** A registry lists every published document (D105). The README's statements are tied to what is verified (D84). One class of status prose is checked against the status: a document calling a built artifact unbuilt (D106). Advertised invocations are executed by tests rather than merely read (D85).
- **Sweeps.** The specification carries a "Last swept" marker naming the version and decision a full review reached. A test counts the decisions recorded since the marker (D108), and the build fails once more than ten have accrued.

## Failure messages as product

The code treats a misleading error as worse than silence, a principle the decision record cites again and again (D50). Halts name the specific artifact and cause. A missing key, an unopenable key and a key that is not text produce three different messages. Commands distinguish "the check failed" (exit 1) from "nothing was checked" (exit 2). Quoted failure messages in the documents are provoked and compared by tests, like any other published output (D112).
:::

# Assessment

This section is the report author's view, kept separate from the description above.

## Strengths

- **The verdict is genuinely re-derivable.** Exact decimals, sorted serialization, a strict separation of non-deterministic fields, embedded fingerprints and a ranked `verify` make each scorecard checkable. CI observes byte-identity across Windows and Linux on the dev split rather than asserting it.
- **Ground truth is protected from the scorer's own bugs.** The scorer holds no domain rule, and the key is checked by an independent derivation plus extensive load-time validation.
- **Isolation is layered, and its limits are stated.** Placement is primary. Configuration is checked by code. Enforcement is attested by a person, with a recorded failure and its fix.

::: M
- **Defects become mechanisms.** From D67 on, every decision must name what enforces it. Recurring defect classes are locked by scanners (D68). A traceability map ties criteria to named tests or documented manual checks (172 entries, 5 manual), and every test must be either mapped or explicitly exempted. The decision record keeps its own mistakes, which makes the reasoning auditable.
- **Published output is executed.** Output blocks and quoted failure messages in the README and runbook are checked against real output by tests. Prose is not covered, and it can drift: the runbook's opening warning says a `[guard-reach]` line means the guards are not in force, while its own section 2.5, the attestation document and the code treat that line as advisory only.
:::

## Limits and risks

- **The data is tiny.** The dev split holds nine expectations, and the runbook reports two held-out ones. Precision and recall on so few cases say little statistically. The specification schedules a portfolio-sized dataset for phase 3; that is the precondition for meaningful scores.
- **The audit shares an author with the generator.** The project states this itself: the audit catches slips and drift, not a shared misunderstanding of a rule.
- **Isolation depends on habits and one tool.** The deny rules are specific to Claude Code, bind only a session rooted in the right folder, and cover only listed shell commands. A held-out scorecard written inside the tree is caught only after the fact.
- **Nothing guards writes into the secret tier.** A key altered before scoring yields a self-consistent scorecard that `verify` cannot flag; only that tier's git history would show the change.

::: M
- **Scope is narrow by design.** There are five arithmetic categories, no "cannot adjudicate" outcome (deferred to phase 4, D97), no reasoning-quality scoring, and no agent runner.
- **Durability of the out-of-tree tiers.** The secret and held-out tiers are separate repositories whose remotes, if any, the harness cannot see. When last noted in the decision record, the held-out tier had no remote. The isolation command only advises when either holds unpushed work. Losing them would make every held-out result unverifiable.
- **Density.** The decision record is about 357 KB, and code comments cite decision numbers heavily. That rigor has a cost: a newcomer needs a guide such as this report or the runbook.
:::

::: L
- **Platform asymmetry in the guard.** CI notes that the backslash forms of the generator `Bash` rules can never match on Linux, so the guard is slightly weaker there; placement still applies.
- **Tests on the author's machine reach the secret tier.** With the secret tier present, staleness, claim-coverage and guard-template tests read its files by design, through subprocess-level code the deny rules do not govern. That is consistent with the project's model, but it means the full suite should not run inside a session that must stay blind.
:::

::: M
# Glossary

- **Agent under test.** The AP matching agent being scored; it writes the findings artifact.
- **Answer key.** The list of expected findings for a split, plus the correspondence table.
- **Attestation.** A dated, manual record of probing whether the deny rules bind a live session.
- **Canary.** A decoy file in the secret tier, holding a unique marker and no secret content, used for attestation probes.
- **Correspondence.** Rows in the answer key linking each invoice line to one purchase-order line and its goods receipts.
- **Coverage block.** The scorecard section stating which categories a split can measure.
- **D-number.** An entry in `DECISIONS.md`, such as D35. Code and tests cite these to explain why something is the way it is.
- **Deny rule.** A Claude Code permission rule that refuses a matching tool call.
- **Deterministic body.** The scorecard without `run_metadata`; it must be byte-identical across runs on the same inputs.
- **Fingerprint.** A SHA-256 digest of an input, embedded in the scorecard.
- **Golden dataset.** Inputs whose correct answers are fixed and audited in advance.
- **Held-out split.** Data kept out of development and publication. The agent reads its inputs only when evaluated and never sees its key, so its score measures generalization.
- **Invoice index.** Structured JSON of the invoices' lines. The scorer reads it instead of parsing PDFs; in the held-out split it is secret.
- **Matching policy.** The published statement of every rule the generator applied.
- **Payable quantity.** `min(ordered, received)`; the anchor for quantity findings.
- **Placement.** Keeping secret artifacts physically outside the repository tree; the primary control.
- **Port.** The findings artifact format, the only interface between agent and harness.
- **Split.** One dataset: `dev`, `dev-synthetic`, `dev-zero-defect`, or the held-out split.
- **Three-way matching.** Comparing purchase order, goods receipt and invoice.
- **Tier.** One of the three folders: the harness, the held-out inputs, or the secret tier.
- **Zero-defect control.** A split with no expected findings, which measures over-flagging only.
:::

::: L
# Appendix

## Exit codes

| Command | 0 | 1 | 2 |
|---|---|---|---|
| `goldset-triad score` | scored | — | malformed input; no scorecard written |
| `goldset-triad verify` | identical | a difference was found | no verdict reached |
| `goldset-triad rebuild-ledger` | rebuilt | — | missing folder or unreadable scorecard |
| `goldset-triad-audit-key` | consistent | divergences listed | the dataset could not be audited |
| `goldset-triad-check-isolation` | both checks pass | a check failed | the checks could not run, including when `.claude/settings.json` is missing |

## Test modules by area

| Area | Modules | Tests |
|---|---|---|
| Findings format | `test_port_schema`, `test_port_tolerance` | 20 |
| Loading and validation | `test_dataset_loading`, `test_cross_artifact_validation`, `test_read_failures` | 46 |
| Scoring and scorecards | `test_scoring_engine`, `test_scorecard_repro`, `test_coverage_reporting`, `test_scorecard_legend` | 42 |
| Ground truth and audit | `test_ground_truth`, `test_key_and_arithmetic`, `test_key_audit`, `test_audit_score_parity`, `test_generator_staleness` | 54 |
| Verify, ledger, CLI | `test_verify_mode`, `test_run_ledger`, `test_cli_end_to_end`, `test_entry_points` | 42 |
| Isolation and shipping | `test_isolation`, `test_repo_shipping` | 42 |
| Claims and documents | `test_claim_coverage`, `test_published_claims`, `test_published_examples`, `test_traceability`, `test_ci_workflow` | 53 |
| Defect-class scanners | `test_defect_classes`, `test_constraints_scan` | 30 |

The constraint scans enforce the project's hard rules mechanically:

- no float on a money path and no division inside a flagging decision;
- standard-library-only imports in the scoring engine, and no network, model or PDF library anywhere;
- no domain rule in the scoring module, and no PDF read by the loader;
- a clean-room rule keeping two terms from the practice application's terminology out of the authored work.

## Project history

The repository has 71 commits, from 2026-07-25 (specification and decision record) to 2026-09-19 (specification 0.42.0). The specification lists 158 acceptance criteria: 141 for phase 1, 10 for phase 2 and 7 for phase 3. Its own note counts 130, 5 and 8 SHALL requirements for those phases, and deliberately none for phases 4 and 5.

## Planned phases

| Phase | Goal | Main contents |
|---|---|---|
| 3 | Dataset expansion | Roughly 100 purchase orders and 75 invoices; more suppliers; document-quality variation (scanned, skewed, noisy, multi-layout) as the main axis; a performance budget; a lenient match mode; alternate cohorts with randomized content under the same filenames |
| 4 | Compliance and enrichment | Statutory tax, segregation of duties, vendor-master and sanctions checks, currency mismatches; a "cannot adjudicate" outcome; reporting of ignored input |
| 5 | Audience expansion | Packaging, external documentation, isolation guidance independent of any one agent tool, an optional runner adapter, confidence-calibration scoring |

The specification makes the first held-out scorecard from a real consumer the trigger for writing phase 4 requirements, so that design follows evidence.

## Deferred design commitments

| Decision | Commitment | Planned phase |
|---|---|---|
| D97 | A "cannot adjudicate" outcome class for cases ending in human review | 4 |
| D98 | Named global tolerance sets chosen by a published rule | 4 |
| D99 | Restoring dimensions cut from the originating fixtures, with document-quality variation as the main axis | 3 and 4 |
| D101 | A published threshold for when an inferred purchase-order match may be concluded | 4 |
:::
