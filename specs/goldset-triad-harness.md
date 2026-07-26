# specification: goldset-triad-harness

A held-out golden-dataset harness that scores an AP document-matching agent's 3-way
(PO / invoice / goods-receipt) findings against hand-audited ground truth.

## metadata
- Spec version: 0.1.1
- Status: READY-FOR-BUILD
- Last updated: 2026-07-25
- Author(s): Saso Gale
- Target type: library/service (CLI evaluation harness)
- Build class: build-required
- Role: n/a — purely procedural tool; a persona adds nothing to a deterministic scorer.
- Produced by: /specify @ `821fac1` — note this pre-dates `b248d15`, which added the metadata fields
  below; they were backfilled by hand in 0.1.1 from decisions already recorded in `DECISIONS.md`.
- Artifacts land in: `D:\Claude_Stuff\Claude_Desktop_Code_Projects\goldset-triad-harness` (A1)
- Visibility: private now, public when ready (D11.1). The held-out answer key lives **outside** this
  repository tree, so publishing never exposes it (A8).
- Decision record: `DECISIONS.md` at the repository root — permitted in place of
  `specs/<slug>.decisions.md` because this repo holds a single spec, and root placement is more
  discoverable for a portfolio artifact.
- Reproducibility: **required, byte-identical** — identical dataset version plus findings artifact yields
  an identical scorecard, excepting only the `run_metadata` envelope, which holds exactly the
  non-deterministic fields (U4, D9, D10).
- Timestamp standard: UTC ISO-8601 with a `Z` suffix, second precision. Dataset timestamps are seeded and
  fixed; only the scorecard run stamp reads the real clock (D6).
- Integrity: verify-by-recompute — each scorecard embeds SHA-256 fingerprints of the findings artifact and
  the answer key, so a doctored score is exposed by re-running rather than by trusting git history (D10).

**Phase-tag map.** `[P1]` = credibility core (originally "P1a"). `[P2]` = tooling & scaffolding
(originally "P1b"). `[P3]` = dataset expansion. `[P4]` = compliance categories. `[P5]` = audience
expansion. Tags were renumbered from the interview's P1a/P1b naming because the linter **at the time**
(`821fac1`) accepted integer-only tags. Sub-phase tags — a phase number with a lowercase letter suffix,
P1a-style — became legal in toolkit `b09a99a`, but the renumbering stands: re-tagging every item and the
build prompt would be pure churn for a mnemonic. (Written without brackets deliberately: the linter scans
the whole document for tags, so a bracketed tag mentioned in prose is counted as if it were a real one.)

**Companion document.** `DECISIONS.md` at the repo root is the running decision record (D0–D12): every
fork, the options considered, the choice, and why. This spec states *what*; `DECISIONS.md` preserves *why*.

## outcome

A developer building an AP document-matching agent can run it against a selected, version-pinned golden
dataset and get back an objective scorecard — per-category precision/recall on expected discrepancies, plus
an over-flagging rate from a zero-defect control — in a single command, reproducibly, with the answer key
structurally unable to enter the agent's context. The report pinpoints where and how the agent failed
(missed findings, false flags, wrong category or line), so a regression from a prompt or logic change
surfaces immediately instead of by eyeballing output.

## in scope
- [P1] Findings payload schema v1 — the stable port: closed category enumeration, composite `TargetLine`
  identifier, `Status`, `Confidence`, free-text reasoning.
- [P1] Scoring engine — 1:1 matching under a strict match key, deterministic tie-break, per-category
  precision and recall, false-positive count and rate.
- [P1] Scorecard emission — machine-readable JSON plus a human-readable summary, with embedded input
  fingerprints and a `run_metadata` envelope.
- [P1] A small 3-way golden dataset including goods-receipt discrepancies, plus a zero-defect control case.
- [P1] Initial scored category set — price variance, quantity under-shipment, quantity over-shipment, tax
  variance (arithmetic self-consistency).
- [P1] Dataset selection by id or path, with a public dev split and a private held-out split.
- [P1] Answer-key isolation — directory placement outside the repo tree plus harness deny-guards — and a
  canary probe that proves the key directory is unreachable.
- [P1] Type discipline — pyright gate, `Decimal` for money, frozen dataclasses, `typing.Final` constants.
- [P1] Test suite covering every `[P1]` acceptance criterion.
- [P2] `--verify` recompute mode — recomputes a scorecard from its embedded fingerprints and diffs it.
- [P2] Append-only JSONL run ledger, regenerable from the scorecard directory.
- [P2] README and methodology write-up — golden-dataset framing, isolation story, held-out rationale.
- [P2] CI workflow running the pyright gate and the test suite on push.
- [P2] Cross-platform verification — identical scorecard output on Windows and Linux.
- [P3] Dataset expansion to roughly 100 purchase orders and 75 invoices with goods receipts, additional
  vendors and customers, wider discrepancy taxonomy.
- [P3] Performance budget — a 10-second target enforced as a warning, never a failure.
- [P3] Lenient match mode — an optional flag dropping `TargetLine` from the match key.
- [P4] Compliance category set — statutory/jurisdiction tax, segregation-of-duties violations, vendor-master
  and sanctions mismatches, currency mismatches.
- [P5] Audience expansion — packaging, external-developer documentation, portable (non-harness-specific)
  isolation guidance.
- [P5] Optional runner adapter that invokes an agent-under-test on the developer's behalf.
- [P5] Confidence-calibration scoring as a deterministic add-on.

## out of scope (v1)
- The agent-under-test itself — it is a separate project, `fin-ops-compliance-specialist`; this harness
  never contains or imports it, per decision D1.
- Scoring the quality of an agent's reasoning prose — judging it requires an LLM judge, which is subjective
  and non-reproducible, and would destroy the deterministic verdict this tool exists to provide (D4).
- Any web UI or dashboard — command line and JSON only, deferred indefinitely.
- Being a general-purpose evaluation framework — deliberately scoped to accounts-payable three-way
  matching rather than "evaluate anything".
- Optical character recognition and vision extraction — the harness scores emitted findings, so document
  parsing belongs entirely to the agent-under-test.
- Tamper-proofing via cryptographic signing or notarization — verify-by-recompute (D10) delivers the
  needed integrity property far more cheaply.

## control surface
n/a (not an agent) — invoked as a one-shot CLI command; it runs to completion or halts. There is no
autonomous loop, no iteration budget, and no mid-run human checkpoint to define.

## triggers & scheduling
n/a (not an agent) — on-demand CLI invocation only. Runs are independent and may overlap safely because
each writes a distinctly timestamped scorecard and appends to the ledger atomically.

## tools & permissions
- Allowed: local filesystem reads of the selected dataset, the answer key, and the findings artifact;
  filesystem writes confined to the scorecard output directory and the local ledger.
- Network access: none. The harness makes no network call at any point.
- Secrets/credentials: none required. The harness needs no API key because it invokes no model.
- NEVER do unattended: the harness SHALL NOT write to, move, or delete any dataset or answer-key file; it
  SHALL NOT delete prior scorecards. All inputs are treated as strictly read-only.

## state & memory
- Persists state between runs: yes, append-only and never mutated.
- What state: timestamped scorecards (the durable, tamper-evident record) and a derived JSONL run ledger.
- Where and format: scorecards as JSON in the output directory, one set per run, never overwritten; the
  ledger as newline-delimited JSON, local-only and gitignored.
- Reset/cleanup: nothing prunes automatically. The ledger is fully regenerable from the scorecards, so
  deleting it loses nothing.

## model & cost routing + determinism boundary
- Deterministic (plain code, NO LLM) — **everything the harness does at runtime**: dataset and key loading,
  schema validation, finding-to-expectation matching, tie-breaking, precision/recall arithmetic,
  false-positive counting, tax and price and quantity arithmetic in the key, SHA-256 fingerprinting,
  timestamp normalization and ordering, scorecard serialization, ledger append and regeneration, canary
  probing.
- Requires judgment (LLM): **none at runtime.** This is deliberate, not an omission — a non-deterministic
  scorer cannot produce the byte-reproducible verdict that makes the tool credible. LLM judgment lives
  entirely inside the agent-under-test, which is out of scope.
- LLM use at design time only: AI assists in *designing* the discrepancy plan (category coverage,
  distribution, placement) before the data is frozen. Its output is human-audited and committed as seeded
  deterministic generator code. Re-running a design model is not part of any pipeline (D5).
- Model tier per judgment task: n/a — no runtime judgment tasks exist.
- Type & value discipline: type hints throughout, gated on pyright with zero errors; `Decimal` for every
  monetary value and never `float`; frozen dataclasses for records; `typing.Final` for constants.
- Cost/budget guardrails: zero token cost by construction — the harness has no model call to budget.
- Stop/escalate when: any integrity precondition fails (see failure & escalation) — halt, never degrade.

## constraints
- Stack: Python 3.11 or newer.
- Scoring engine: standard library only — `json`, `decimal`, `dataclasses`, `typing`, `hashlib`, `pathlib`.
  Zero third-party dependencies, so the credibility core stays trivially auditable.
- Data-generation side may take a PDF-authoring dependency; which library is a `[P3]` decision, not needed
  now.
- Static checker: pyright. "Type-check passes with zero errors" is an acceptance criterion.
- Cross-platform: Windows and Linux are both first-class. Every documented command is given for PowerShell
  and for bash. Use `pathlib`; assume no shell-specific behaviour.
- Do NOT re-architect or import from `practice--reconciliation-agent-manual-from-scratch-app` — reuse its
  proven *patterns* only (Decimal discipline, deterministic finding identifiers, append-never-insert for
  positionally-indexed records).
- Clean-room terminology: the strings "reconciliation agent" and "iTradeNetwork" SHALL NOT appear anywhere
  in this repository.
- No new packages without flagging for approval first.

## prior decisions
- D1 — The harness scores an emitted findings artifact and does not run the agent: the payload schema is the
  port, so isolation is free, external agents become an add-on rather than a refactor, and the harness stays
  runtime-agnostic. An optional runner adapter is deferred to `[P5]`.
- D2 — Datasets are selectable addressable data, version-stamped per run: comparability demands
  byte-identical inputs, and the public/held-out split means two datasets exist from day one.
- D3 — Tax checking enters at `[P1]` as arithmetic self-consistency (`TAX_VARIANCE`); statutory/jurisdiction
  tax defers to `[P4]`. The prior work already proves the arithmetic form and it was the largest discrepancy
  by value in the earlier sample.
- D4 — Reasoning-quality scoring is permanently excluded for subjectivity; confidence calibration is merely
  deferred to `[P5]` because it is deterministically computable but adds schema weight.
- D5 — Design-time AI is welcome, including designing the discrepancy plan where systematic coverage beats
  human intuition; runtime AI is forbidden. The design is frozen into seeded generator code.
- D6 — All timestamps are UTC ISO-8601 with a `Z` suffix at second precision; ordering compares absolute
  instants; civil dates only as a documented exception carrying an explicit time zone.
- D7 — Python 3.11+, pyright, stdlib-only scoring core, two dependency zones.
- D8 — Match key defaults to strict `Status` + `Category` + `TargetLine`; matching is 1:1 with a
  deterministic tie-break; over-flagging on the zero-defect control is reported as raw false-positive count
  and false-positives-per-invoice.
- D9 — Duration is recorded broken down by phase inside `run_metadata`, which the reproducibility comparison
  excludes; scorecards are the durable record and the JSONL ledger is a regenerable convenience view; a
  performance breach warns and exits zero because the harness evaluates accounting correctness, not speed.
- D10 — Integrity comes from verify-by-recompute, not git forensics: each scorecard embeds fingerprints of
  its inputs, and `run_metadata` contains exactly the non-deterministic fields.
- D11 — Repository stays private until ready; the `[P1]` dataset is newly authored with the existing
  fixtures serving as schema reference only; discrepancy categories are a closed enumeration owned by the
  harness.
- D12 — Phase composition as recorded in the implementation phases block.

## requirements

### ubiquitous (always active)
- [P1] The harness SHALL perform all scoring in deterministic plain code, making no LLM call and no network
  call at any point during a run.
- [P1] The harness SHALL represent every monetary value as `Decimal` and never as `float`.
- [P1] The harness SHALL represent every timestamp as UTC ISO-8601 with a `Z` suffix at second precision.
- [P1] The harness SHALL treat every dataset file, answer-key file, and findings artifact as strictly
  read-only.
- [P1] Re-running the harness on the same dataset version and the same findings artifact SHALL produce a
  byte-identical scorecard, excepting only the fields inside the `run_metadata` envelope.
- [P1] The `run_metadata` envelope SHALL contain exactly the non-deterministic fields and nothing else.

### event-driven (WHEN — triggered by an action)
- [P1] WHEN invoked with a dataset identifier and a findings artifact path, the harness SHALL emit a
  scorecard as both machine-readable JSON and a human-readable summary.
- [P1] WHEN loading a dataset, the harness SHALL resolve it by identifier or path as addressable data and
  SHALL NOT rely on any hardcoded dataset location.
- [P1] WHEN matching, the harness SHALL pair each agent finding with at most one expected finding and each
  expected finding with at most one agent finding.
- [P1] WHEN an expected finding has no matching agent finding, the harness SHALL record it as a false
  negative and name the expectation that was missed.
- [P1] WHEN an agent finding matches no expected finding, the harness SHALL record it as a false positive.
- [P1] WHEN scoring completes, the harness SHALL compute precision and recall for each discrepancy category
  in the closed enumeration.
- [P1] WHEN scoring the zero-defect control case, the harness SHALL report the raw false-positive count and
  the false-positives-per-invoice rate, and SHALL NOT report precision for that case because it is
  mathematically undefined there.
- [P1] WHEN a run completes, the harness SHALL record in the scorecard the dataset identifier, the dataset
  version, a SHA-256 fingerprint of the findings artifact, and a SHA-256 fingerprint of the answer key.
- [P1] WHEN a run completes, the harness SHALL record in `run_metadata` the run timestamp and the elapsed
  load, score, and total durations in milliseconds, together with the invoice count and finding count.
- [P1] WHEN an agent finding carries a status of MATCH rather than DISCREPANCY, the harness SHALL treat it
  as an assertion of correctness that is ineligible to be a flag, and SHALL NOT count it as a false
  positive.
- [P2] WHEN invoked in verify mode against an existing scorecard, the harness SHALL recompute the score from
  the fingerprinted inputs and SHALL report any difference from the stored scorecard.
- [P2] WHEN a run completes, the harness SHALL append one record to the JSONL run ledger.
- [P2] WHEN invoked to rebuild the ledger, the harness SHALL regenerate it from the scorecard directory
  alone.

### state-driven (WHILE — true for the duration of a state)
- [P1] WHILE a run is in progress, the harness SHALL leave every input file unmodified.
- [P1] WHILE emitting a scorecard, the harness SHALL serialize with a stable key ordering so that identical
  inputs yield identical bytes.

### unwanted behavior (IF — error handling)
- [P1] IF the findings artifact violates the payload schema, the harness SHALL halt with an error naming the
  offending finding and field, and SHALL NOT emit a scorecard.
- [P1] IF a finding carries a category absent from the closed enumeration, the harness SHALL treat it as a
  schema violation and halt.
- [P1] IF the requested dataset identifier or version is missing or unreadable, the harness SHALL halt
  naming the dataset, and SHALL NOT emit a partial score.
- [P1] IF the answer key is unreadable from the scoring context, the harness SHALL halt, and SHALL NOT treat
  the absence of ground truth as a pass.
- [P1] IF any timestamp in a dataset is not `Z`-suffixed second-precision ISO-8601, the harness SHALL reject
  the dataset as malformed.
- [P1] IF two or more agent findings contend for the same expected finding, the harness SHALL count exactly
  one true positive, SHALL treat the remainder as false positives, and SHALL resolve the contention by a
  deterministic tie-break so the result never depends on input ordering.
- [P1] IF an agent finding references a target line or document absent from the dataset, the harness SHALL
  record it as a false positive distinctly labelled as referencing a non-existent target.
- [P1] IF the canary probe reaches inside the answer-key directory, the harness SHALL report a failed
  isolation check prominently and exit non-zero.
- [P3] IF a run exceeds the performance target, the harness SHALL emit a prominent warning and SHALL exit
  zero, because elapsed time does not affect scoring correctness.

### optional feature (WHERE — behind a flag / config)
- [P2] WHERE verify mode is requested, the harness SHALL compare recomputed results against the stored
  scorecard and exit non-zero on any mismatch.
- [P3] WHERE lenient matching is enabled, the harness SHALL drop `TargetLine` from the match key and SHALL
  record in the scorecard that lenient matching was used.

### non-functional
- Security: [P1] The answer key SHALL NOT be readable from the agent-under-test's execution context,
  enforced by directory placement outside the repository tree plus harness deny-guards. [P1] The harness
  SHALL ship a canary probe that verifies this unreachability.
- Performance: [P3] The harness SHALL score a dataset of roughly 75 invoices in under 10 seconds on
  commodity hardware, treated as a warning threshold only.
- Error handling / observability: [P1] Every halt SHALL name its specific cause and exit non-zero. [P1] The
  human-readable summary SHALL identify each missed finding and each false flag individually rather than
  reporting aggregate numbers alone.
- Portability: [P1] The harness SHALL produce identical scorecard content when run on Windows and on Linux.
- Privacy: [P1] The harness SHALL transmit no data anywhere, having no network capability at all.

## failure & escalation
- Recoverable error: none by design. Every integrity precondition is binary, so there is nothing to retry
  and no backoff policy to define.
- Unrecoverable error: halt immediately, name the specific cause on stderr, exit non-zero, and emit no
  scorecard. Partial or silently-degraded scoring is never acceptable, because a distorted score is worse
  than no score.
- Stuck / uncertain: not reachable — the harness makes no judgment call that could leave it uncertain.
- Escalation channel: stderr message plus a non-zero exit code. A performance breach is the sole exception:
  it warns and exits zero (D9).

## acceptance criteria

### happy path
- [ ] [P1] A findings artifact containing exactly the expected findings scores recall 1.0 and precision 1.0
  in every category.
- [ ] [P1] The scorecard is emitted both as JSON that parses and as a human-readable summary.
- [ ] [P1] The scorecard records the dataset identifier and version.
- [ ] [P1] The scorecard embeds a SHA-256 fingerprint of the findings artifact and of the answer key.
- [ ] [P1] The zero-defect control scored against an empty findings artifact reports a false-positive count
  of 0 and a rate of 0.0, and reports no precision figure.
- [ ] [P1] The seeded tax overcharge, flagged on the correct line, scores as a true positive under
  `TAX_VARIANCE`.
- [ ] [P1] A seeded goods-receipt under-shipment, flagged on the correct line, scores as a true positive.
- [ ] [P1] A seeded goods-receipt over-shipment, flagged on the correct line, scores as a true positive.
- [ ] [P1] `run_metadata` carries the run timestamp plus load, score, and total durations, and the invoice
  and finding counts.
- [ ] [P1] Every field inside `run_metadata` is non-deterministic, and no deterministic field appears there
  — asserted by confirming that excluding `run_metadata` is sufficient to make two runs byte-identical.
- [ ] [P1] The human-readable summary names each missed finding and each false flag individually rather
  than reporting aggregate counts alone.
- [ ] [P2] Verify mode on an untouched scorecard reports no difference and exits zero.

### edge cases
- [ ] [P1] Omitting one expected finding records it as a miss and reduces that category's recall by exactly
  one over the category's expectation count.
- [ ] [P1] Adding one spurious finding records a false positive and reduces precision accordingly.
- [ ] [P1] Two agent findings contending for one expected finding yield exactly one true positive and one
  false positive, and the scorecard is identical when the findings artifact order is reversed.
- [ ] [P1] A finding with the correct category but the wrong `TargetLine` is not a true positive under
  strict matching; it counts as both a false negative and a false positive.
- [ ] [P1] A finding referencing a non-existent line is recorded as a false positive labelled as
  referencing a non-existent target.
- [ ] [P1] A finding whose status is MATCH is not counted as a false positive.
- [ ] [P1] A malformed findings artifact halts, exits non-zero, names the offending finding and field, and
  writes no scorecard.
- [ ] [P1] A finding bearing a category outside the closed enumeration halts as a schema violation.
- [ ] [P1] A missing or unreadable dataset halts, exits non-zero, names the dataset, and writes no partial
  score.
- [ ] [P1] An unreadable answer key halts and exits non-zero rather than passing by default.
- [ ] [P1] A dataset containing a timestamp lacking the `Z` suffix or second precision is rejected as
  malformed.
- [ ] [P2] Verify mode on a scorecard whose stored numbers have been altered detects the difference and
  exits non-zero.

### constraint validation
- [ ] [P1] The same dataset version and findings artifact scored twice produce byte-identical scorecards
  apart from `run_metadata`.
- [ ] [P1] pyright reports zero errors across the repository.
- [ ] [P1] An import scan confirms the scoring engine imports only standard-library modules.
- [ ] [P1] An automated scan confirms no `float` appears on any monetary code path.
- [ ] [P1] An automated scan confirms no networking or model-client import exists anywhere in the scoring
  path.
- [ ] [P1] The canary probe confirms the answer-key directory is unreachable from an agent context; a
  reachable canary fails the check loudly and exits non-zero.
- [ ] [P1] A scan confirms zero occurrences of "reconciliation agent" and "iTradeNetwork" in the repository.
- [ ] [P1] No input dataset or answer-key file is modified by any run, verified by comparing file hashes
  before and after.
- [ ] [P2] Deleting the JSONL ledger and regenerating it from the scorecard directory reproduces identical
  contents.
- [ ] [P2] The CI workflow runs the pyright gate and the full test suite on push and fails on any error.
- [ ] [P2] Running the same dataset and findings artifact on Windows and on Linux yields identical scorecard
  content outside `run_metadata`.
- [ ] [P3] A roughly 75-invoice dataset scores in under 10 seconds; when the threshold is breached a warning
  appears and the exit code remains zero.

---

## implementation phases

### phase 1 — credibility core (the walking slice)
- Goal: a single command scores a findings artifact against a held-out 3-way golden dataset and emits a
  trustworthy, reproducible scorecard.
- Includes: findings payload schema v1; scoring engine with strict 1:1 matching and deterministic
  tie-break; per-category precision/recall plus false-positive count and rate; scorecard emission as JSON
  and human summary with embedded fingerprints and a `run_metadata` envelope; a small newly-authored 3-way
  dataset carrying goods-receipt discrepancies and a zero-defect control; the initial category enumeration
  (price variance, quantity under-shipment, quantity over-shipment, tax variance); dataset selection by
  identifier or path across a dev split and a held-out split; answer-key isolation by placement plus
  deny-guards with a canary probe; type discipline under a pyright gate; and a test suite covering every
  `[P1]` criterion.
- Skeleton floor: all nine floor items were retained. None were dropped, so no override reason is recorded.
- Done when: every `[P1]` acceptance criterion passes by execution.

### phase 2 — tooling & scaffolding
- Goal: make the integrity story actionable and the project continuously verified.
- Includes: `--verify` recompute mode; append-only JSONL ledger with regeneration from scorecards; README
  and methodology write-up; CI workflow running pyright and tests; cross-platform verification on Windows
  and Linux.

### phase 3 — dataset expansion
- Goal: scale the dataset to portfolio size and add the metrics that only matter at scale.
- Includes: roughly 100 purchase orders and 75 invoices with goods receipts; additional vendors and
  customers; wider discrepancy taxonomy; the 10-second performance budget as a warning; lenient match mode.

### phase 4 — compliance categories
- Goal: cover the rare, expensive checks that go beyond arithmetic.
- Includes: statutory and jurisdiction tax; segregation-of-duties violations; vendor-master and sanctions
  mismatches; currency mismatches.

### phase 5 — audience expansion
- Goal: make the harness usable by a developer who is not its author.
- Includes: packaging and external documentation; portable isolation guidance that does not assume a
  specific agent harness; the optional runner adapter; confidence-calibration scoring.

---

## assumptions

All eight assumptions below were walked and confirmed at the review gate on 2026-07-25, and are therefore
folded into prior decisions. They are retained here as the record of what was inferred rather than stated.

- [x] Repository root is `D:\Claude_Stuff\Claude_Desktop_Code_Projects\goldset-triad-harness` — risk if
  wrong: files land in the wrong tree. **Confirmed.**
- [x] The repository stays private until it is ready to publish — risk if wrong: a key leaked into early
  public git history is permanent and retroactively voids the held-out claim. **Confirmed.**
- [x] The findings artifact is a single JSON file whose path is passed as a command-line argument — risk if
  wrong: the ingest contract is wrong for multi-file or streaming agents. **Confirmed.**
- [x] Discrepancy categories form a closed enumeration owned by the harness — risk if wrong: per-category
  metrics become undefined and near-miss category names silently score as misses. **Confirmed.**
- [x] `TargetLine` is a composite identifier of document identifier plus line identifier, defined
  canonically by the dataset — risk if wrong: strict matching cannot work. **Confirmed.**
- [x] The `[P1]` dataset is newly authored, with the existing fixtures serving as schema reference only —
  risk if wrong: wasted effort or terminology bleed. **Confirmed.**
- [x] The zero-defect control comprises at least one fully clean invoice with zero expected findings — risk
  if wrong: the over-flagging measure has no basis. **Confirmed.**
- [x] Held-out answer keys live outside the repository tree in a project-specific secret directory — risk if
  wrong: keys inside the repository make the held-out claim false. **Confirmed.**

---

## decisions made
- [the building agent appends architectural calls the spec did not cover]

---

## emitted artifacts
n/a (build-required — see `specs/goldset-triad-harness.build-prompt.md`)

---

## changelog
- 0.1.1 (2026-07-25): metadata backfill only — added `Produced by`, `Artifacts land in`, `Visibility`,
  `Decision record`, `Reproducibility`, `Timestamp standard` and `Integrity`. These fields were introduced
  to the toolkit template in `b248d15`, after this spec was written at `821fac1`. No requirement,
  criterion, scope or phase changed: every value was already decided (A1, A8, D6, D9, D10, D11.1) and is
  merely now stated where the template expects it.
- 0.1.0 (2026-07-25): initial specification. Interview-derived; decisions D0–D12 recorded in
  `DECISIONS.md`. Phase tags renumbered from the interview's P1a/P1b to `[P1]`/`[P2]` for linter
  conformance.
