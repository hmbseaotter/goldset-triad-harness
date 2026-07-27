# specification: goldset-triad-harness

A held-out golden-dataset harness that scores an AP document-matching agent's 3-way
(PO / invoice / goods-receipt) findings against hand-audited ground truth.

## metadata
- Spec version: 0.23.0
- Status: READY-FOR-BUILD
- Last updated: 2026-07-26
- Author(s): Saso Gale
- Target type: library/service (CLI evaluation harness)
- Build class: build-required
- Role: n/a — purely procedural tool; a persona adds nothing to a deterministic scorer.
- Produced by: /specify @ `821fac1` — note this pre-dates `b248d15`, which added the metadata fields
  below; they were backfilled by hand in 0.1.1 from decisions already recorded in `DECISIONS.md`.
- Artifacts land in: `D:\Claude_Stuff\Claude_Desktop_Code_Projects\goldset-triad-harness` (A1)
- Visibility: private now, public when ready (D11.1). The **entire held-out split** — inputs, answer key,
  generators and discrepancy-design artifact — lives **outside** this repository tree, so publishing never
  exposes it (D14). The dev split ships in full, inputs and key, and is what CI exercises.
- **Last swept: 2026-07-26 @ 0.23.0 @ D82** — an independent sweep over the `[P2]` surface (verify mode, the
  run ledger, the CI workflow) and the mechanisms they register with, run by a session that did not build them.
  Twenty-four findings, six decisions: D77 (one reader, named read failures), D78 (no coercion at a gate),
  D79 (verify's reporting), D80 (a total run order), D81 (assert the message), D82 (a lock declares its
  universe). It also found two closed items still sitting in the negative-space list below. The prior full
  sweep was **0.21.0 @ D72** over spec, decisions, build prompt, all four datasets, the in-repo code, the
  secret-side generator, the guards and cross-platform behaviour. Next sweep due
  when **~8–10 decisions have accrued since the stamp above**, **before publishing**, or **at phase
  completion** — whichever comes first. The trigger
  is deliberately **change-based, not calendar-based**: drift accumulates per decision, not per day. This spec
  ran 0.3.0 → 0.10.0, seven versions and roughly twenty decisions, before its first sweep, and that interval is
  exactly where the defects piled up. A monthly reminder would have fired during quiet weeks and stayed silent
  through the heavy design run. **Update this line whenever a sweep completes**, or it stops meaning anything.
  The threshold is now expressed against the stamp rather than restated as a decision number: this line read
  *"so around D55"* while its own stamp said D72, because a hand-computed value sitting beside its own source is
  a parallel list, and parallel lists drift — the defect class that produced the hand-written subject index
  (0.10.3) and the one-directional traceability map (D54), here inside the very marker that exists to stop a
  document going stale (0.22.0).
- Decision record: `DECISIONS.md` at the repository root — permitted in place of
  `specs/<slug>.decisions.md` because this repo holds a single spec, and root placement is more
  discoverable for a portfolio artifact.
- Reproducibility: **required, byte-identical** — identical dataset version plus findings artifact yields
  an identical scorecard, excepting only the `run_metadata` envelope, which holds exactly the
  non-deterministic fields (U4, D9, D10).
- Timestamp standard: UTC ISO-8601 with a `Z` suffix, second precision. Dataset timestamps are seeded and
  fixed; only the scorecard run stamp reads the real clock (D6).
- Integrity: verify-by-recompute — each scorecard embeds **four** SHA-256 fingerprints: the findings artifact,
  the answer key, the structured invoice index, and an aggregate digest of the dataset inputs. A doctored score
  is exposed by re-running rather than by trusting git history (D10, D27, D34).

**Phase-tag map.** `[P1]` = credibility core (originally "P1a"). `[P2]` = tooling & scaffolding
(originally "P1b"). `[P3]` = dataset expansion. `[P4]` = compliance categories. `[P5]` = audience
expansion. Tags were renumbered from the interview's P1a/P1b naming because the linter **at the time**
(`821fac1`) accepted integer-only tags. Sub-phase tags like `[P1a]` became legal in toolkit `b09a99a`, but
the renumbering stands: re-tagging every item and the build prompt would be pure churn for a mnemonic.

**Companion document.** `DECISIONS.md` at the repo root is the running decision record: every fork, the
options considered, the choice, and why. This spec states *what*; `DECISIONS.md` preserves *why*. Its extent is
deliberately **not restated here** — it said `D0–D36` for thirteen versions after it stopped being true, and the
record states its own range while `lint_spec.py` reports the real one and fails on a gap (0.22.0).

> **Read decisions as a sequence, not in isolation.** Several early entries were later narrowed or overturned:
> **A5→D22**, **A8→D14**, **D7→D33**, **D8→D20**, **D10→D27 and D34**, **D28→D29**, and the D35
> re-attribution, which moved every domain rule off the scoring engine. Superseded entries carry an inline
> note; the changelog below is the authoritative order.

## outcome

A developer building an AP document-matching agent can run it against a selected, version-pinned golden
dataset and get back an objective scorecard — per-category precision/recall on expected discrepancies, plus
an over-flagging rate from a zero-defect control — in a single command, reproducibly, with the answer key
structurally unable to enter the agent's context. The report pinpoints where and how the agent failed
(missed findings, false flags, wrong category or line), so a regression from a prompt or logic change
surfaces immediately instead of by eyeballing output.

## in scope
- [P1] Findings payload schema v1 — the stable port: closed category enumeration, `scope` of `LINE` or
  `DOCUMENT`, composite `TargetLine` identifier anchored on the invoice, `Status`, `Confidence`, free-text
  reasoning (D20, D22).
- [P1] Scoring engine — 1:1 matching under a strict match key, deterministic tie-break, per-category
  precision and recall, false-positive count and rate.
- [P1] Scorecard emission — machine-readable JSON plus a human-readable summary, with embedded input
  fingerprints and a `run_metadata` envelope.
- [P1] A zero-defect control case within the dev split, carrying no expected findings, against which
  over-flagging is measured. *(The dataset itself is specified below under D32; this item names only the control.)*
- [P1] Initial scored category set — `PRICE_VARIANCE`, `QTY_UNDER_SHIPMENT`, `QTY_OVER_SHIPMENT`,
  `QTY_INVOICE_INFLATED`, `TAX_VARIANCE` (arithmetic self-consistency). Five categories (D15).
- [P1] Dataset selection by id or path, with a public dev split shipped in the repo and a fully private
  held-out split resident outside the repository tree.
- [P1] Held-out split isolation — placement outside the repo tree for the whole split, plus harness
  deny-guards scoped to the answer key, generators and design artifact **but deliberately not to the
  held-out inputs**, which the agent must read — verified by an automated guard-configuration check and an
  automated placement check, with harness enforcement recorded as a dated manual attestation using the canary
  as its decoy (D30).
- [P1] Separate goods-receipt documents carrying their own GRN, date, receiver, line items and identifiers, so
  that receipt-to-purchase-order correspondence is genuine work (D31).
- [P1] A realistic dev split shipped in the repository, plus a small, clearly labelled set of synthetic fixtures
  for values that would be implausible in the domain, both loading through the same manifest and loader (D32).
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
- [P3] Lenient match mode — an optional flag dropping only the **line** component from the match key, while
  retaining status, category, scope and document identifier (D20).
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
- Optical character recognition and vision extraction **in the scoring engine** — the scorer reads structured
  data only and never opens a document, so extraction belongs to the agent-under-test. This bars parsing from
  the *scorer*, not from the key generator, which parses its own output back for round-trip verification (D34,
  D36).
- Tamper-proofing via cryptographic signing or notarization — verify-by-recompute (D10) delivers the
  needed integrity property far more cheaply.

## control surface
n/a (not an agent) — invoked as a one-shot CLI command; it runs to completion or halts. There is no
autonomous loop, no iteration budget, and no mid-run human checkpoint to define.

## triggers & scheduling
n/a (not an agent) — on-demand CLI invocation only. Runs are independent and may overlap safely because
each writes a distinctly timestamped scorecard and appends to the ledger atomically.

## tools & permissions
- Allowed: local filesystem reads of the selected dataset inputs, the answer key, the structured invoice index,
  the dataset manifest, and the findings artifact; filesystem writes confined to the scorecard output directory
  and the local ledger.
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
- Deterministic (plain code, NO LLM) — **everything every component does at runtime.** For the **scoring
  engine**: dataset, key and invoice-index loading, schema validation, finding-to-expectation matching,
  tie-breaking, precision/recall arithmetic, false-positive counting, SHA-256 fingerprinting, timestamp
  normalization and ordering, scorecard serialization, ledger append and regeneration, the guard-configuration
  and placement checks. For the **key generator** (secret side): the tax, price and quantity arithmetic that
  authors expected findings, and the round-trip parse-back. For the **key-audit command**: deriving expectations
  and diffing them against the key (D30, D35, D36).
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
- Data generation takes **ReportLab** as a PDF-authoring dependency, from `[P1]`, for clean text-layer invoices.
  Harder format tiers — multi-page dot-matrix layouts, consolidated invoices, scanned documents with no text
  layer — remain `[P3]`. **This does not breach the stdlib-only rule, which is scoped to the scoring engine;
  this dependency lands on the generation side, in the secret tier** (D33).
- Static checker: pyright. "Type-check passes with zero errors" is an acceptance criterion.
- Cross-platform: Windows and Linux are both first-class. Every documented command is given for PowerShell
  and for bash. Use `pathlib`; assume no shell-specific behaviour.
- Do NOT re-architect or import from `practice--reconciliation-agent-manual-from-scratch-app` — reuse its
  proven *patterns* only (Decimal discipline, deterministic finding identifiers, append-never-insert for
  positionally-indexed records).
- Clean-room terminology: the strings "reconciliation agent" and "iTradeNetwork" SHALL NOT appear anywhere
  in this repository.
- Dataset input files must be committed with line-ending conversion disabled — `.gitattributes` marking them
  binary or `-text`. Without it, `autocrlf` gives a Windows checkout different bytes from a Linux one, the
  aggregate inputs digest diverges, and the cross-platform identical-output requirement fails in a way that
  presents as a harness bug (D27).
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
- D8 — Match key defaults to strict `Status` + `Category` + `TargetLine` — **extended by D20 to
  `Status` + `Category` + `scope` + target**; matching is 1:1 with a
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
- D13 — A `MATCH`-status entry asserts correctness and is ineligible to be a flag, so it is never a false
  positive; the missed discrepancy is already counted once as a false negative.
- D14 — The **entire** held-out split lives outside the repository tree. "Outside the repo" and "deny-guarded"
  are different sets: the held-out inputs are out-of-tree yet must stay agent-readable.
- D15 — Quantity discrepancies anchor on `payable = min(ordered, received)`; three categories, named for which
  constraint bound it.
- D16 — Materiality is `max($0.05, min(2% × basis, $25))`, flagged on `>=`, applied to quantity overbills too.
- D17 — Sibling out-of-tree directories; a dataset is a set of locations resolved through a manifest.
- D18 — `invoice_count` and `finding_count` live in the scored body, not `run_metadata`.
- D19 — The two-percent basis is the **payable** extended amount; the invoiced amount is disqualified as
  self-referentially gameable.
- D20 — Findings carry `scope`; the match key becomes status + category + scope + target.
- D21 — `TAX_VARIANCE` is document-scoped and uses the unified threshold against the taxable subtotal.
- D22 — `TargetLine` anchors on the invoice; line ids are explicit, never positional; correspondence is
  declared in the key and withheld from the inputs.
- D23 — Compare at full `Decimal` precision; round only for display, `ROUND_HALF_UP`.
- D24 — Expected tax uses the **invoiced** taxable subtotal, so one root cause yields one finding.
- D25 — Precision is `null` only where no flags were raised; recall is `null` unconditionally on a
  zero-expectation case; undefined is emitted as `null`.
- D26 — Contention resolves by canonical-serialization order, never document position; duplicates are reported
  as a distinct diagnostic.
- D27 — The dataset inputs are fingerprinted; `.gitattributes` must disable line-ending conversion.
- D28 — No division inside a decision; the tax comparison is cross-multiplied; context precision is pinned and
  reported ratios carry a declared output precision.
- D29 — Zero taxable subtotal takes an explicit branch (expected tax zero); a non-zero tax against it is
  malformed; the tax field is always present.
- D30 — Isolation is verified by guard-configuration and placement checks; enforcement is **attested**, not
  tested, because a reachability probe cannot work.
- D31 — Goods receipts are separate documents; received quantity sums across all receipts for a line.
- D32 — Three data families; only implausible values go synthetic.
- D33 — ReportLab from `[P1]` for clean text-layer invoices; generated PDFs must be byte-deterministic.
- D34 — A structured invoice index, key-side and agent-denied, separate from the key and fingerprinted.
- D35 — The scoring engine loads and matches; every domain rule belongs to the key generator and the published
  policy; a separate audit command derives and diffs.
- D36 — Document and index are emitted from one canonical record; a generation-time parse-back closes the
  rendering-bug residual.

*(Condensed. `DECISIONS.md` carries each fork's rejected options and full reasoning.)*

## requirements

**Four components, deliberately separated (D35).** Requirements below name whichever they bind.

| Term | What it is | Domain rules? | Ships? |
|---|---|---|---|
| **scoring engine** | loads the key and the invoice index, matches, counts, emits the scorecard | **none, ever** | yes |
| **key generator** | applies the domain rules, authors expected findings, emits documents and index | yes | no — secret side |
| **key-audit command** | independently derives expectations and diffs them against the key | yes | yes, but **never invoked by a scoring run** |
| **matching policy** | published statement of every rule the generator applied | documents them | yes |

**"The harness" means the shipped tool as a whole** — scoring engine, audit command and the isolation checks.
Where a requirement constrains scoring specifically, it names the **scoring engine**. This distinction is
load-bearing: the audit command deliberately implements domain rules, which the scoring engine must never do,
and only the scoring engine is bound by the standard-library-only rule.

**Subject index — every subject spans several EARS sections; check all of them before changing one.** EARS
groups by *pattern*, so rules about one subject necessarily scatter. That scattering is what let contradictions
survive seven versions until the 0.10.1 sweep, because each round's question only ever touched the section it
was about. When amending a subject, read every row entry below.

*Generated by the toolkit's `scripts/subject_index.py` against actual section membership, never written by hand
— an index asserted from memory is worse than none, because a missing row actively misdirects a sweep. It
**errs toward over-inclusion**: a spurious "check here" costs a glance, a missing one costs a contradiction.
Regenerate it during every sweep: the 0.11.0 sweep found three rows stale, because the shipped generator counts
the `non-functional` block's labelled `- Security: [P1] …` form that the original throwaway script missed.*

| Subject | Sections containing its requirements |
|---|---|
| Tax | ubiquitous · event-driven · unwanted behavior |
| Quantity | ubiquitous · event-driven |
| Price & materiality | ubiquitous · event-driven · non-functional |
| Matching & scope | ubiquitous · event-driven · unwanted behavior · optional feature |
| Metrics & undefined values | ubiquitous · event-driven · state-driven · unwanted behavior |
| Fingerprints & integrity | ubiquitous · event-driven · unwanted behavior |
| Ground-truth artifacts | ubiquitous · event-driven · state-driven · unwanted behavior · non-functional |
| Isolation | ubiquitous · unwanted behavior · non-functional |
| Generation | ubiquitous · event-driven · optional feature · non-functional |

> **Note on the non-functional block:** its items are written `- Security: [P1] …` rather than `- [P1] …`, so
> pattern-based tooling counts zero requirements there. The formatting follows the template, but any script
> auditing this spec must special-case it — including the generator of this index, which cannot see inside it.

### ubiquitous (always active)

*Truth-source architecture (D35)*
- [P1] The scoring engine SHALL load expected findings from the answer key and SHALL confine itself to matching
  and counting, and SHALL NOT apply any domain rule at scoring time — because a scorer that derived expectations
  would score the agent against its own implementation rather than against audited ground truth, making any bug
  in that implementation silently authoritative (D35).
- [P1] Every rule determining whether a discrepancy exists, its category, or its materiality SHALL be applied by
  the key generator when authoring expected findings, and SHALL be stated in the published matching policy (D35).
- [P1] The harness SHALL provide a key-audit command, separate from scoring, that derives expected findings from
  the structured inputs and reports every divergence from the declared answer key — and that command SHALL NOT
  execute during a scoring run, so that a derivation defect can never become ground truth mid-score (D35).
- [P1] The key-audit command SHALL describe its result as a consistency check rather than a proof of
  correctness, because generator and auditor share an author and their independence is therefore weak (D35).

*Ground-truth artifacts (D22, D31, D34)*
- [P1] The answer key SHALL declare the canonical correspondence from each invoice line to its purchase-order
  line and its goods-receipt line, so the key is unambiguous and independently reproducible (D22).
- [P1] The agent-readable inputs SHALL NOT declare that correspondence, because resolving it across differing
  descriptions, part numbers and units of measure is the capability under evaluation (D22).
- [P1] Goods receipts SHALL be represented as documents separate from the purchase order, each carrying its own
  receipt number, date, receiver, line items and identifiers, so that resolving receipt-to-purchase-order
  correspondence is part of the evaluated task rather than given away by co-location (D31).
- [P1] The harness SHALL obtain structured invoice data — line identifiers, quantities, prices, the tax field,
  timestamps and the invoice count — from a structured invoice index, and SHALL NOT parse any invoice document,
  because extraction is out of scope and a document parser in the scoring engine would breach the
  standard-library-only rule (D34).
- [P1] The structured invoice index SHALL be a complete line inventory covering clean lines as well as discrepant
  ones, because target validation must be able to distinguish a line that exists from one that does not, which
  the expected findings alone cannot support (D34).
- [P1] The structured invoice index SHALL reside in the agent-denied tier alongside the answer key, and SHALL NOT
  be readable by the agent-under-test, because structured invoice data would bypass the extraction that the
  document form exists to require (D34).
- [P1] The structured invoice index SHALL be a separate artifact from the answer key, so that the key remains a
  statement of expected findings rather than a restatement of the inputs, and so that the key's fingerprint does
  not change when only the inputs change (D34).
- [P1] The answer key SHALL declare **exactly one** correspondence entry per invoice line, not merely at least
  one: the key audit derives from every row, so two rows mapping one line to different purchase-order lines
  would union conflicting derivations and admit a finding only one mapping justifies (D56).
- [P1] The dev split SHALL exercise every category in the closed enumeration, and SHALL contain both a flagging
  and a non-flagging case on each materiality basis kind — cent-aligned and non-aligned — because a dataset of
  flagging cases alone cannot distinguish a correct threshold from one that flags everything (D57).
- [P1] The zero-defect control SHALL declare no expected findings while still declaring correspondence for
  every one of its invoice lines, since it is the whole basis of the over-flagging measure and an expectation
  appearing there would silently change what the false-positive rate means (D57).
- [P1] A dataset property that holds only for the current phase SHALL be enforced by a named tripwire that
  fails when the property stops holding, rather than assumed — the single-purchase-order shape of every shipped
  invoice is such a property, and its tripwire is what forces `[P3]` to implement the deferred tax
  apportionment instead of guessing it (D57, D47).

*Generation invariants (D33, D36, D58)*
- [P1] Generated invoice documents SHALL be byte-identical on regeneration from the same seed, with document
  creation and modification dates pinned to the seeded timestamp and the document identifier pinned or
  suppressed — otherwise the aggregate inputs digest changes on every regeneration and presents as tampering
  (D33).
- [P1] The key generator SHALL emit each invoice document and its entry in the structured invoice index from a
  single canonical record in one pass, so that document and index cannot diverge by construction (D36).
- [P1] The key generator SHALL read back each generated invoice document and SHALL assert that it matches the
  structured invoice index, closing the residual case of correct data mis-rendered into the document — this
  parse-back being permitted because it runs on the generation side, which the scoring engine's
  standard-library-only rule does not bind (D36).
- [P1] The key generator SHALL stamp a digest of its own source into every manifest it emits, and the harness
  SHALL verify that stamp whenever the generator is reachable — because the generator lives out of tree and
  agent-denied, so without a stamp nothing in the repository can notice that a domain rule changed and the
  datasets were never regenerated, and every other check stays green while describing data authored under rules
  that no longer exist (D58).
- [P1] The staleness stamp SHALL be computed by the shipped implementation that the verifying check uses, and
  SHALL NOT be reimplemented on the generation side, because it is a mechanical digest rather than a domain rule
  and a second implementation could only drift — which is the very condition the stamp exists to detect (D58,
  D35).
- [P1] The staleness stamp SHALL cover generator source files only, SHALL exclude compiled bytecode, and SHALL
  hash raw bytes under forward-slashed relative paths sorted byte-wise, so that two machines agree on it for the
  same reasons the aggregate inputs digest does (D58, D27).
- [P1] The staleness verification SHALL skip with a message naming why when the generator is not reachable, and
  SHALL NOT fail, because a suite that is red on every clone is a suite nobody reads (D58, D14).
- [P1] The staleness stamp SHALL live in the manifest, which sits outside the inputs directory, so re-stamping
  SHALL NOT alter the aggregate inputs digest and SHALL NOT invalidate any scorecard already emitted (D58, D27).

*Claim coverage and defect-class locks (D67, D68)*
- [P1] Every field in which an artifact asserts something about other state SHALL be registered against the
  check that compares it, and a field matching the declared claim-shaped naming SHALL fail the suite when
  unregistered — because four separate decisions (D58, D59, D64) were one class: an artifact declaring an
  authority nothing held it to (D67).
- [P1] Any property asserted of "every dataset split" SHALL iterate one shared enumeration that includes the
  held-out split whenever it is reachable, and SHALL NOT iterate the in-repo splits alone, because a check
  cannot inspect a set it does not enumerate and no amount of review finds that (D67, D64).
- [P1] A registered claim covering fewer than all known splits SHALL state a reason, and the registry SHALL
  fail when it names a field that exists on no split, so the register itself cannot go stale (D67).
- [P1] The harness SHALL contain no timing wait, because scoring is deterministic and single-threaded, so a
  wait is either concealing a defect or tolerating a race (D68, D49).
- [P1] Every site in shipped code where a missing key yields a numeric value SHALL record why that is sound —
  domain-zero, unreachable by a prior check, or otherwise — because a missing value that becomes a number
  enters arithmetic and changes a verdict silently (D68, D50).
- [P1] No permission rule in any rule list SHALL be anchored on a bare stem, because a stem matches inside
  ordinary words and a guard that obstructs routine work is one people switch off (D68, D65).
- [P1] The ordering SHALL be asserted wherever one validator's correctness depends on another running first,
  rather than left to a comment a later reader must find (D68, D50).
- [P1] The isolation command SHALL report uncommitted changes and unpushed commits in the secret tier whenever it
  is reachable, because every other check reads that tier's working tree and the artifact inspected is therefore
  not the artifact that survives a disk failure (D70).
- [P1] A durability finding SHALL be advisory and SHALL NOT alter the isolation command's exit code, because an
  uncommitted tier is a durability risk rather than an isolation breach, and a guard that reports routine editing
  as a failure is one people switch off (D70, D65).
- [P1] The durability check SHALL cover every out-of-tree tier, held-out inputs included, because losing those
  inputs makes every held-out scorecard permanently unverifiable — the scorecard embeds a digest of exactly those
  bytes and nothing remains to recompute against (D71, D27).
- [P1] Each out-of-tree tier SHALL pin its own bytes and state its own publication rule, because attributes and
  ignore rules stop at a repository boundary and cannot be inherited from the harness (D71).
- [P1] The stamped guard SHALL declare only the permission lists the harness expects, because a list nobody
  asserted would be half-examined — the coverage rules read `deny` alone (D71).
- [P1] Every input document SHALL carry its own identifier and that identifier SHALL match its filename, and the
  loader SHALL NOT fall back to the filename, because the fallback yields an identity no correspondence row can
  match and the omission then surfaces as a phantom reference against the answer key (D71, D50).
- [P1] A rule's named enforcement SHALL be resolved rather than merely matched as a word, and a rule naming
  nothing that exists SHALL fail — a rule citing a test that does not exist is the unchecked claim the rule
  requirement exists to prevent (D71, D59).

*Portability and shared validity (D61, D62)*
- [P1] Every text read and write in the repository SHALL name its encoding explicitly, every text write SHALL pin
  its newline, and a check SHALL fail on any call that does not — because the platform default differs between the
  development machine and CI, which makes it an unstated dependency rather than a default (D61, D49).
- [P1] The key-audit command SHALL validate a dataset through the same loader a scoring run uses before
  performing its own derivation, so that every dataset the scorer refuses the audit also refuses (D62).
- [P1] The key-audit command SHALL continue to derive expected findings by an implementation independent of the
  generator, because the independence D35 requires concerns deriving findings and not deciding admissibility, on
  which a second implementation offers nothing to compare (D62, D35).

*Coverage disclosure (D60)*
- [P1] The scorecard SHALL state which discrepancy categories the dataset holds expectations for and which it
  does not, and SHALL report the count of expectations per category, because an undefined metric on a category
  the data never exercised is indistinguishable from a perfect result and reads as one (D60, D25).
- [P1] The coverage statement SHALL live in the scored body rather than the `run_metadata` envelope, because it
  is a property of the answer key and therefore deterministic (D60, D10).
- [P1] The human-readable summary SHALL render an undefined metric as a reader-facing token and SHALL NOT
  interpolate the language's null representation, while the machine-readable scorecard SHALL continue to emit
  null (D60, D25).
- [P1] The scorecard SHALL carry a schema version, and that version SHALL be raised whenever the scored body's
  shape changes, because byte-identity is promised between runs on the same inputs and never across schema
  versions, so a reader — and `[P2]` verify mode, which recomputes a stored scorecard and diffs it — can tell a
  shape change from a scoring difference rather than reporting one as the other (D60, D66).

*Command-line surface (D59)*
- [P1] Every module exposing a `main` entry point SHALL be declared as a console script, and the name a command
  advertises for itself in its own help output SHALL be a command that exists — because a tool whose help names a
  command the package never declared sends a reader to a command-not-found (D59).
- [P1] A command that inspects the repository SHALL resolve which tree to inspect explicitly, and IF no checkout
  can be found it SHALL report that nothing was checked rather than reporting an isolation failure, because
  naming a failure that did not occur is the misdiagnosis D50 ruled worse than silence (D59, D50).

*Category and scope invariants (D19, D20, D21)*
- [P1] A `TAX_VARIANCE` finding SHALL be document-scoped, because tax is charged once per invoice rather than
  per line, and SHALL NOT be distributed across the invoice's taxable lines (D20, D21).
- [P1] For a line-scoped finding, the basis for the two-percent term SHALL be the **payable extended amount**,
  being the payable quantity multiplied by the purchase-order unit price; the invoiced extended amount SHALL NOT
  be used, because an inflated invoice would enlarge its own denominator and understate the variance ratio (D19).
- [P1] For a document-scoped finding concerning tax, the basis for the two-percent term SHALL be the invoice's
  taxable subtotal (D21).

*Numeric and value discipline (D23, D28)*
- [P1] The harness SHALL represent every monetary value as `Decimal` and never as `float`.
- [P1] The harness **and the key generator** SHALL compute and compare every monetary value at full `Decimal`
  precision and SHALL NOT round any value before a comparison, because rounding an intermediate is
  path-dependent and would make an independent auditor's recomputation diverge (D23).
- [P1] The harness SHALL round monetary values to two decimal places only when emitting them for display,
  SHALL use `ROUND_HALF_UP` explicitly rather than the language default, and SHALL NOT admit a rounded value
  back into any comparison (D23).
- [P1] The key generator SHALL NOT perform a division inside any flagging decision, and SHALL confine division
  to values that are only displayed or only reported (D28).
- [P1] The harness SHALL pin the decimal context precision to a declared constant rather than relying on the
  language default, so that any incidental division is reproducible across environments (D28).
- [P1] The harness SHALL emit every reported ratio — precision, recall, and the false-positives-per-invoice
  rate — at a declared number of decimal places using `ROUND_HALF_UP`, because these are divisions whose
  emitted bytes fall under the byte-identical comparison and would otherwise be fixed by the environment
  rather than by this specification (D28).
- [P1] The harness SHALL represent every timestamp as UTC ISO-8601 with a `Z` suffix at second precision.
- [P1] For any metric that is undefined, the harness SHALL emit null, and SHALL NOT emit zero nor omit the
  field, because zero reads as failure where the result was in fact perfect and an omitted key makes the
  field unstable across runs (D25).

*Determinism, integrity and read-only inputs (D10, D18, D27)*
- [P1] The harness SHALL perform all scoring in deterministic plain code, making no LLM call and no network
  call at any point during a run.
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
- [P1] WHEN matching, the harness SHALL compose the strict match key from the finding's status, category,
  scope, and target — the target being the document identifier alone for a document-scoped finding and the
  document identifier together with the line identifier for a line-scoped finding (D8, D20).
- [P1] WHEN a finding is document-scoped, the harness SHALL require a reserved sentinel in place of the line
  identifier, and SHALL reject as malformed any document-scoped finding whose line identifier is absent or
  empty rather than treating it as document-level by inference (D20).
- [P1] WHEN a finding identifies a target, the document identifier SHALL name the invoice under evaluation,
  and the line identifier SHALL be an identifier the dataset assigns explicitly rather than a position within
  a list (D22).
- [P1] WHEN an expected finding has no matching agent finding, the harness SHALL record it as a false
  negative and name the expectation that was missed.
- [P1] WHEN an agent finding matches no expected finding, the harness SHALL record it as a false positive.
- [P1] WHEN scoring completes, the harness SHALL compute precision and recall for each discrepancy category
  in the closed enumeration.
- [P1] WHEN scoring the zero-defect control case, the harness SHALL report the raw false-positive count and
  the false-positives-per-invoice rate, which are always defined.
- [P1] WHEN a case carries no expectations, the harness SHALL report recall as null unconditionally, since
  with no expectations the recall quotient has a zero denominator (D25).
- [P1] WHEN a case carries no expectations, the harness SHALL report precision as null only where the agent
  raised no flags at all, and SHALL otherwise report the computed value — which is zero, is well defined, and
  is the result that carries the signal (D25).
- [P1] WHEN a run completes, the harness SHALL record in the scorecard the dataset identifier, the dataset
  version, a SHA-256 fingerprint of the findings artifact, a SHA-256 fingerprint of the answer key, and an
  aggregate SHA-256 digest of the dataset inputs, because the inputs determine the false-positive-rate
  denominator and target validation and therefore move the score (D27).
- [P1] WHEN computing the aggregate inputs digest, the harness SHALL include every file beneath the inputs
  directory recursively, SHALL normalize each path relative to that directory using forward slashes, SHALL
  sort those paths byte-wise, SHALL digest each file's raw bytes without any text transformation, and SHALL
  hash the concatenation of path and file-digest pairs in that order (D27).
- [P1] WHEN a run completes, the harness SHALL record in `run_metadata` the run timestamp and the elapsed
  load, score and total durations in milliseconds, and nothing else.
- [P1] WHEN a run completes, the harness SHALL record the invoice count and the finding count in the
  scorecard's scored body, not in `run_metadata`, because both are deterministic and therefore SHALL fall
  under the byte-identical comparison (D18).
- [P1] WHEN an agent finding carries a status of MATCH rather than DISCREPANCY, the harness SHALL treat it
  as an assertion of correctness that is ineligible to be a flag, and SHALL NOT count it as a false
  positive.
- [P1] WHEN an agent finding carries a status of MATCH, the harness SHALL ALSO treat it as ineligible to
  satisfy an expected finding, so a MATCH on a line that does carry an expected discrepancy leaves that
  expectation recorded as a miss — the entry asserts the opposite of the finding, and the single wrong
  assertion is therefore counted exactly once (D55, extending D13).
- [P1] WHEN a finding's target is absent from the dataset, the harness SHALL exclude that finding from 1:1
  matching altogether rather than allowing it to consume an expectation, and SHALL count it as a false
  positive labelled as referencing a non-existent target (D55).
- [P1] WHEN determining a quantity discrepancy on a line, the key generator SHALL compute the payable quantity as
  the lesser of the ordered and received quantities, and SHALL treat the line as overbilled only when the
  invoiced quantity exceeds that payable quantity (D15).
- [P1] WHEN establishing the received quantity for a purchase-order line, the key generator SHALL sum the
  quantities recorded across **all** goods receipts referencing that line, because partial deliveries produce
  several receipts and a quantity taken from one receipt where two exist would be wrong (D31).
- [P1] WHEN a run completes, the harness SHALL additionally record a SHA-256 fingerprint of the structured
  invoice index, because that index determines the false-positive-rate denominator and target validation and
  therefore moves the score (D34, D27).
- [P1] WHEN a line is overbilled on quantity, the key generator SHALL assign the category by which constraint
  bound the payable quantity: `QTY_UNDER_SHIPMENT` where the received quantity is less than the ordered
  quantity, `QTY_OVER_SHIPMENT` where the ordered quantity is less than the received quantity, and
  `QTY_INVOICE_INFLATED` where the ordered and received quantities are equal (D15).
- [P1] WHEN measuring a price variance on a line, the key generator SHALL compute it as the difference between
  the invoiced and purchase-order unit prices multiplied by the **payable** quantity, so that a quantity error
  cannot present as a price error and be counted twice (D16).
- [P1] WHEN deciding whether a monetary variance is material, the key generator SHALL apply a single threshold —
  the greater of five cents and the lesser of two percent of the applicable basis and twenty-five dollars —
  and SHALL flag the variance when its absolute value is **equal to or greater than** that threshold (D16).
- [P1] WHEN assessing a quantity overbill for materiality, the key generator SHALL value it as the excess
  quantity multiplied by the purchase-order unit price and SHALL apply the same threshold as monetary variances
  (D16).
- [P1] WHEN computing the expected tax for an invoice, the key generator SHALL apply the purchase-order-derived
  rate to the invoice's **own** taxable subtotal, so that a price or quantity error yields one finding in its own
  category rather than additionally producing a tax finding (D24).
- [P1] WHEN deciding whether a tax variance is material, the key generator SHALL evaluate the comparison in
  cross-multiplied form, comparing the absolute difference between the invoiced tax times the purchase-order
  taxable subtotal and the purchase-order tax times the invoiced taxable subtotal against the threshold times
  the purchase-order taxable subtotal — so that the decision uses multiplication and subtraction only and
  performs **no division**, the tax rate being generally non-terminating (D28).
- [P1] WHEN the purchase order has no taxable lines, so that its taxable subtotal is zero and no rate is
  derivable, the key generator SHALL treat the expected tax as zero and SHALL compare the invoiced tax directly
  against the threshold, which degenerates to five cents — and SHALL NOT apply the cross-multiplied comparison,
  which at a zero subtotal reduces to zero against zero and would flag every such invoice while annihilating
  the invoiced tax (D29).
- [P1] WHEN a dataset is resolved, the harness SHALL read a manifest naming the inputs directory, the
  answer-key path and the structured-invoice-index path separately, so that a split whose inputs and
  ground-truth artifacts reside in different locations is loadable without special-casing (D17, D34).
- [P2] WHEN invoked in verify mode against an existing scorecard, the harness SHALL recompute the score from
  the fingerprinted inputs and SHALL report any difference from the stored scorecard.
- [P2] WHEN a run completes, the harness SHALL append one record to the JSONL run ledger.
- [P2] WHEN invoked to rebuild the ledger, the harness SHALL regenerate it from the scorecard directory
  alone.

### state-driven (WHILE — true for the duration of a state)
- [P1] WHILE a run is in progress, the harness SHALL leave every input file unmodified.
- [P1] WHILE emitting a scorecard, the harness SHALL serialize with a stable key ordering so that identical
  inputs yield identical bytes.
- [P1] WHILE scoring a dataset whose answer key declares no expected findings at all, the harness SHALL state in
  the scorecard that the dataset measures over-flagging only and that every recall figure is undefined by
  construction, so the zero-defect control is not read as an agent that recalled nothing (D60, D57).

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
- [P1] IF the purchase order's taxable subtotal is zero while its tax amount is greater than zero, the harness
  SHALL reject the dataset as malformed and SHALL name the offending purchase order, because an authorized tax
  against nothing taxable would let the expected-tax-is-zero rule silently contradict the record (D29).
- [P1] IF a purchase order or an invoice omits its tax field, or presents it as null, the harness SHALL reject
  the dataset as malformed — the field SHALL always be present, carrying zero where nothing is taxable, so that
  absent is never confusable with zero (D29).
- [P1] IF two or more agent findings contend for the same expected finding, the harness SHALL count exactly
  one true positive, SHALL treat the remainder as false positives, and SHALL resolve the contention by a
  deterministic tie-break so the result never depends on input ordering.
- [P1] IF contention must be resolved, the harness SHALL order the contending findings by a canonical
  serialization of each whole finding and SHALL select the first, and SHALL NOT resolve contention by position
  within the findings artifact, because order-dependence would violate the requirement that reversing that
  artifact yield an identical scorecard (D26).
- [P1] IF contending findings are counted as false positives, the harness SHALL additionally report the
  duplicate-contention count as a distinct diagnostic, because an agent emitting duplicates has a defect that
  an undifferentiated false-positive count would conceal (D26).
- [P1] IF two or more agent findings share a match key for which the answer key holds NO expectation, the
  harness SHALL count each as an ordinary false positive and SHALL NOT report them as duplicate contention,
  because contention means contending for an expectation and inflating that diagnostic would obscure the
  defect it exists to reveal (D55).
- [P1] IF an agent finding references a target line or document absent from the dataset, the harness SHALL
  record it as a false positive distinctly labelled as referencing a non-existent target.
- [P1] IF verification detects a mismatch in the aggregate inputs digest, the harness SHALL recompute
  per-file digests and SHALL report which files diverged, so that diagnostic depth is computed on demand rather
  than stored in every scorecard (D27).
- [P1] IF the guard-configuration check finds any secret path uncovered by the deny rules, or the placement
  check finds a secret artifact inside the repository tree, the harness SHALL report a failed isolation check
  prominently and exit non-zero (D30).
- [P1] IF a dataset is malformed in a way the loader does not model, the key-audit command SHALL report that the
  dataset is malformed and name the fault, and SHALL NOT surface a bare exception nor report the condition as a key
  divergence (D62, D50).
- [P3] IF a run exceeds the performance target, the harness SHALL emit a prominent warning and SHALL exit
  zero, because elapsed time does not affect scoring correctness.

### optional feature (WHERE — behind a flag / config)
- [P2] WHERE verify mode is requested, the harness SHALL compare recomputed results against the stored
  scorecard and exit non-zero on any mismatch.
- [P2] WHERE verify mode meets a scorecard whose schema version it does not recognise, it SHALL report the
  version mismatch as its own outcome and SHALL NOT present the resulting differences as a scoring
  discrepancy (D66).
- [P3] WHERE a document tier has no reliable text layer, the round-trip parse-back SHALL be recorded as
  inapplicable and agreement SHALL rest on single-source construction alone (D36).
- [P3] WHERE lenient matching is enabled, the harness SHALL drop only the **line** component from the match
  key, SHALL retain status, category, scope and document identifier, and SHALL record in the scorecard that
  lenient matching was used — so a document-scoped finding never becomes indistinguishable from a line-scoped
  one (D20).

### non-functional
- Security: [P1] The answer key SHALL NOT be readable from the agent-under-test's execution context,
  enforced by directory placement outside the repository tree plus harness deny-guards.
- Security: [P1] The harness SHALL ship a guard-configuration check asserting that the deny rules exist, parse,
  and cover every path in the secret tier — the directory, the answer-key filename, the generator filenames and
  the design artifact — and SHALL fail loudly naming any secret path left uncovered (D30).
- Security: [P1] The harness SHALL ship a placement check asserting that no secret artifact exists at any path
  inside the repository tree (D30).
- Security: [P1] The harness SHALL NOT claim to verify harness enforcement of the deny rules by executing code,
  because deny rules bind tool calls while a subprocess runs beneath that boundary — a reachability probe would
  report failure unconditionally and prove nothing (D30).
- Security: [P1] Harness enforcement SHALL instead be recorded as a dated manual attestation naming the method
  used, and the canary SHALL serve as the decoy for that attestation, remaining covered by the directory rule
  alone so that it exercises the weakest layer (D30).
- Security: [P1] Published claims about isolation SHALL state only what is verified — that placement and guard
  configuration are checked automatically, that enforcement is attested manually, and that a determined
  subprocess is outside deny coverage by design, which is why placement is the primary control (D30).
- Security: [P1] The repository SHALL NOT contain, at any path, the held-out split's answer key, its
  generators, its discrepancy-design artifact, or its dataset inputs. Every one of those SHALL reside
  outside the repository tree (D14).
- Security: [P1] The deny-guards SHALL cover the held-out answer key, generators and discrepancy-design
  artifact, and SHALL NOT cover the held-out dataset inputs — the agent-under-test SHALL retain read access
  to those inputs, because it cannot produce findings without them.
- Security: [P1] The dev split SHALL ship complete in the repository, inputs and answer key together, and
  SHALL NOT be deny-guarded — it is public by design and is the split every automated check runs against.
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
- [ ] [P1] The scorecard embeds four fingerprints — of the findings artifact, the answer key, the structured
  invoice index, and an aggregate digest of the dataset inputs.
- [ ] [P1] Editing the structured invoice index while leaving the key, the inputs and the version untouched
  changes the recorded index fingerprint, so the altered run cannot masquerade as the original.
- [ ] [P1] Regenerating the dev split's invoice PDFs from the same seed produces byte-identical files, leaving
  the aggregate inputs digest unchanged.
- [ ] [P1] No PDF or document-parsing library is importable from the scoring engine, and the harness reads no
  invoice document at any point.
- [ ] [P1] A scan of the agent-readable inputs confirms the structured invoice index is absent from them.
- [ ] [P1] A scan of the scoring engine finds no implementation of any domain rule — no payable-quantity
  computation, no materiality threshold, no tax comparison — confirming expectations are loaded, never derived.
- [ ] [P1] Replacing an expected finding in the answer key changes the score, while leaving the inputs untouched
  — demonstrating the key, not the inputs, is what the scorer treats as truth.
- [ ] [P1] The key-audit command run against a deliberately corrupted answer key reports the divergence and
  names the affected finding; run against the shipped key it reports none.
- [ ] [P1] The key-audit command is not invoked by any scoring code path.
- [ ] [P1] Every rule the key generator applies appears in the published matching policy, verified by comparing
  the policy against the generator's rule set.
- [ ] [P1] Generation emits each invoice document and its index entry from one canonical record, and the
  generation-time parse-back confirms the document matches the index for every clean-tier invoice.
- [ ] [P1] Editing one byte of one input file, leaving the answer key and dataset version untouched, changes
  the aggregate inputs digest — so the altered run cannot masquerade as the original.
- [ ] [P1] Verification against a scorecard whose inputs have changed reports which specific files diverged,
  not merely that the aggregate mismatched.
- [ ] [P1] The aggregate inputs digest is identical when computed on Windows and on Linux from the same data,
  confirming path normalization and the absence of any text transformation.
- [ ] [P1] The zero-defect control scored against an empty findings artifact reports a false-positive count
  of 0, a rate of 0.0, and precision as `null` — emitted, not omitted (D25).
- [ ] [P1] The seeded tax overcharge, flagged as a **document-scoped** finding against the correct invoice,
  scores as a true positive under `TAX_VARIANCE`; the same overcharge flagged as line-scoped does **not** match
  (D20, D21).
- [ ] [P1] A seeded goods-receipt under-shipment, flagged on the correct line, scores as a true positive.
- [ ] [P1] A seeded goods-receipt over-shipment, flagged on the correct line, scores as a true positive.
- [ ] [P1] `run_metadata` carries the run timestamp plus load, score and total durations — and nothing else.
- [ ] [P1] The invoice count and finding count appear in the scored body, and altering either changes the
  byte comparison — proving they are protected by it rather than excluded with `run_metadata`.
- [ ] [P1] A line where the invoice bills more than was received but no more than was ordered scores as
  `QTY_UNDER_SHIPMENT`; a line where more was received than ordered and the invoice follows the receipt
  scores as `QTY_OVER_SHIPMENT`; a line where ordered equals received and the invoice exceeds both scores as
  `QTY_INVOICE_INFLATED`.
- [ ] [P1] A short shipment that is billed correctly for the received quantity produces **no** finding —
  a shipment anomaly with no billing impact is not a discrepancy.
- [ ] [P1] On a basis chosen so the two-percent term lands exactly on a cent — five hundred dollars, giving
  ten dollars — a variance of exactly ten dollars is flagged and one of nine dollars ninety-nine is not.
- [ ] [P1] On a basis where the two-percent term does **not** land on a cent — three hundred thirty-three
  dollars thirty-three, giving six dollars six thousand six hundred sixty-six ten-thousandths — a variance of
  six dollars sixty-seven is flagged and one of six dollars sixty-six is not, proving the comparison is exact
  rather than quantized.
- [ ] [P1] Rounding a value for display never alters a flagging decision: the same dataset scored with display
  rounding applied and with it suppressed yields identical findings.
- [ ] [P1] On a $100,000 extended line a $26 variance is flagged, confirming the twenty-five dollar cap
  governs large lines rather than two percent.
- [ ] [P1] A line carrying both a wrong unit price and a wrong quantity yields one price finding measured at
  the payable quantity and one quantity finding, with neither absorbing the other's dollars.
- [ ] [P1] A one-unit quantity overbill whose dollar value falls below the materiality threshold produces no
  finding, while the same one-unit overbill on a line priced above the threshold does — confirming quantity
  overbills pass through the same materiality rule as monetary variances.
- [ ] [P1] A dataset whose inputs directory and answer-key path lie in different locations loads correctly
  from its manifest, with neither path hardcoded anywhere in the harness.
- [ ] [P1] A `TAX_VARIANCE` finding scores as document-scoped against a single expected finding, and is
  neither duplicated across taxable lines nor rejected for lacking a line identifier.
- [ ] [P1] A document-scoped finding whose line identifier is absent or empty is rejected as malformed rather
  than inferred to be document-level.
- [ ] [P1] A line-scoped and a document-scoped finding that share status, category and document identifier do
  **not** match each other, proving `scope` participates in the match key.
- [ ] [P1] The two-percent term is computed on the payable extended amount: a line short-shipped to a tenth
  of its ordered quantity flags a variance that the ordered-quantity basis would have passed.
- [ ] [P1] A tax variance is assessed against the invoice's taxable subtotal, not against a line amount.
- [ ] [P1] The answer key contains the invoice-to-PO-to-receipt correspondence for every line, and a scan of
  the agent-readable inputs confirms that correspondence is absent from them.
- [ ] [P1] Reordering the lines within an invoice input file changes no line identifier and no finding,
  proving identifiers are explicit rather than positional.
- [ ] [P1] The zero-defect control scored against an empty findings artifact reports precision as null; scored
  against three spurious findings it reports precision as zero, not null.
- [ ] [P1] The zero-defect control reports recall as null in both of the cases above.
- [ ] [P1] Every undefined metric is emitted as null, and no undefined metric is emitted as zero or omitted —
  asserted against the scorecard schema.
- [ ] [P1] A seeded price error on a taxable line produces exactly one finding, in `PRICE_VARIANCE`, and no
  `TAX_VARIANCE`, confirming expected tax is computed on the invoiced taxable subtotal.
- [ ] [P1] Two duplicate findings contending for one expectation are reported with a duplicate-contention
  count of one, distinct from the plain false-positive total, and the scorecard is byte-identical when the two
  are swapped in the input.
- [ ] [P1] A display-rounded amount appearing in the human summary matches the `ROUND_HALF_UP` result, and a
  value ending in exactly half a cent rounds away from zero rather than to even.
- [ ] [P1] A tax variance whose derived rate is non-terminating — purchase-order tax over a taxable subtotal
  that does not divide evenly — produces the same verdict when scored under two different decimal context
  precisions, confirming the decision performs no division.
- [ ] [P1] Tax charged on an invoice whose taxable subtotal is zero flags whenever the tax equals or exceeds
  five cents.
- [ ] [P1] An invoice against a purchase order with no taxable lines, correctly showing tax of zero, produces
  **no** finding — the case that the cross-multiplied form alone would have flagged.
- [ ] [P1] The same invoice charging five cents or more in tax flags as `TAX_VARIANCE`, and charging fifty
  dollars flags too — confirming the invoiced tax is not annihilated by a zero subtotal.
- [ ] [P1] A purchase order whose taxable subtotal is zero while its tax exceeds zero is rejected as malformed,
  naming that purchase order.
- [ ] [P1] A purchase order or invoice whose tax field is absent or null is rejected as malformed, rather than
  being treated as zero.
- [ ] [P1] A purchase-order line delivered across two goods receipts has its received quantity computed as the
  sum of both, and a key computed against only one of them is demonstrably different — proving receipts are
  aggregated rather than read singly.
- [ ] [P1] Goods receipts load from their own documents, and an invoice-to-receipt correspondence is resolvable
  only through the answer key, not by co-location inside the purchase-order record.
- [ ] [P1] The realistic dev split contains a fully exempt purchase order, a $500 extended line and a $333.33
  extended line, all at plausible domain values; the $100,000 line appears only in a synthetic fixture.
- [ ] [P1] Every synthetic fixture is labelled as synthetic and loads through the same manifest and loader as
  the dev split, so no parallel code path exists.
- [ ] [P1] A scan of the scoring path finds no division operation reachable from a flagging decision.
- [ ] [P1] Reported precision, recall and false-positive rate are emitted at the declared decimal places, and a
  run under a different ambient decimal precision produces a byte-identical scorecard.
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
- [ ] [P1] A findings artifact that declares no `schema_version`, or declares one of the wrong type, is
  rejected naming the field: an undeclared version is never assumed to be the current one, and no gate
  coerces a value it then reports un-coerced (D78).
- [ ] [P1] A missing or unreadable dataset halts, exits non-zero, names the dataset, and writes no partial
  score.
- [ ] [P1] An unreadable answer key halts and exits non-zero rather than passing by default.
- [ ] [P1] A file the harness is pointed at that is not valid UTF-8 halts naming the artifact by its role and
  the offending byte, on every read path — findings artifact, manifest, answer key, invoice index and stored
  scorecard — and absent, unopenable and undecodable are reported as three distinct causes (D77).
- [ ] [P1] A dataset containing a timestamp lacking the `Z` suffix or second precision is rejected as
  malformed.
- [ ] [P2] Verify mode on a scorecard whose stored numbers have been altered detects the difference and
  exits non-zero.
- [ ] [P2] Verify mode pointed at a dataset other than the one a scorecard records reports that as its own
  outcome, naming the stored and the resolved identifier, and compares nothing further — neither fingerprints
  nor scored body, since digests of a different dataset differ for a reason that is not tampering (D79).
- [ ] [P2] Verify mode on a scorecard carrying an unrecognised schema version reports the version mismatch as
  its own outcome and does **not** present the resulting differences as a scoring discrepancy — the rule D66
  recorded before the feature existed, and which had a requirement in the `optional feature` block but no
  criterion, so nothing would have failed had verify been built without it (D66).

### constraint validation
- [ ] [P1] The same dataset version and findings artifact scored twice produce byte-identical scorecards
  apart from `run_metadata`.
- [ ] [P1] pyright reports zero errors across the repository.
- [ ] [P1] An import scan confirms the scoring engine imports only standard-library modules.
- [ ] [P1] An automated scan confirms no `float` appears on any monetary code path.
- [ ] [P1] An automated scan confirms no networking or model-client import exists anywhere in the scoring
  path.
- [ ] [P1] The guard-configuration check passes against the shipped deny rules, and fails naming the offending
  path when a secret path is deliberately removed from their coverage.
- [ ] [P1] The placement check passes on a clean tree and fails when a decoy secret artifact is planted inside
  the repository, including beneath an ignored directory.
- [ ] [P1] No shipped check claims to test harness enforcement by executing code; the attestation record exists
  and carries a date and the method used.
- [ ] [P1] A scan of the repository finds no held-out answer key, generator, discrepancy-design artifact,
  or held-out dataset input at any path — including under any ignored directory, since `.gitignore` hides
  a file from git but not from the filesystem.
- [ ] [P1] The agent-under-test context **can** read the held-out dataset inputs while **cannot** read the
  held-out answer key — both halves asserted, because a guard that blocks the inputs breaks evaluation
  instead of protecting it.
- [ ] [P1] The full acceptance suite passes using **only** the dev split shipped in the repository, with no
  out-of-tree path configured — proving CI can verify the harness without access to the held-out split.
- [ ] [P1] The scorecard carries a schema version, and the version in the code matches the one the emitted
  scorecard declares (D66).
- [ ] [P1] A `MATCH` entry on a line that carries an expected discrepancy yields no true positive, leaves the
  expectation recorded as a miss, and is still not a false positive — the wrong assertion counted exactly once
  (D55).
- [ ] [P1] Two agent findings sharing a match key for which no expectation exists are two ordinary false
  positives with a duplicate-contention count of zero, while the same pair against a real expectation reports a
  count of one (D55).
- [ ] [P1] An invoice line carrying two correspondence entries is rejected, whether the entries name different
  purchase-order lines or are exact duplicates, and the shipped datasets map every line exactly once (D56).
- [ ] [P1] The dev split exercises all five categories and carries a flagging and a non-flagging case on each
  materiality basis kind; the zero-defect control declares no expected findings yet still declares
  correspondence for every line (D57).
- [ ] [P1] Two runs completing within the same second each leave their own scorecard, and
  writing over an existing scorecard is refused by the operating system rather than merely
  avoided, because scorecards are the durable record (D49).
- [ ] [P1] Both halves of an emitted scorecard — the JSON and the human summary — are
  written with pinned LF endings, so the bytes do not differ between Windows and Linux
  (D49).
- [ ] [P1] An expected finding naming a target absent from the invoice index is rejected at
  load, because such an expectation can never be matched and would score as a permanent
  false negative against every agent (D50).
- [ ] [P1] Every correspondence row resolves on both sides — a real invoice line, a real
  purchase order, and a real line on that purchase order — and a phantom purchase-order
  reference is reported as such rather than misdiagnosed as a differing tax rate (D50).
- [ ] [P1] An empty correspondence list is rejected rather than exempted, since D22
  requires an entry for every invoice line (D50).
- [ ] [P1] An unresolved correspondence reference reaching the audit command names its
  specific cause rather than surfacing as a raw key error (D50).
- [ ] [P1] No public dataset artifact's filename is a substring of its held-out
  counterpart's, so no filename deny rule written for the held-out artifact can silently
  over-block the public split (D51).
- [ ] [P1] The secret-artifact vocabulary has a single source shared by the filesystem
  placement check and the git-index check, so neither can fall behind the other (D52).
- [ ] [P1] The published matching policy states the same materiality floor, cap and
  percentage that the shipped rule implementation applies (D53).
- [ ] [P1] Every test is either mapped to an acceptance criterion or explicitly exempt, and
  the count of `[P1]` criteria is itself checksummed, so neither a new criterion nor a new
  test can arrive unaccounted for (D54).
- [ ] [P1] No ignore rule excludes any file the repository must ship — asserted over git's ignore rules with
  the index disregarded, since a tracked path is not reported as ignored and the check would otherwise pass
  vacuously from the moment the file was committed; the dev split's inputs and answer key are confirmed
  tracked, and no secret artifact appears in the index (D44).
- [ ] [P1] A scan confirms zero occurrences of "reconciliation agent" and "iTradeNetwork" in the repository.
- [ ] [P1] No input dataset or answer-key file is modified by any run, verified by comparing file hashes
  before and after.
- [ ] [P1] Every shipped dataset's manifest records a digest of the generator source that emitted it, so a
  dataset authored under rules that have since changed can be identified rather than merely trusted (D58).
- [ ] [P1] All shipped splits carry the same generator digest, so a partial regeneration leaving some splits
  current and others stale is detected (D58).
- [ ] [P1] When the generator is reachable, each manifest's recorded digest still matches the generator's
  current source; when it is not reachable the check skips with a message naming why, so the suite still
  passes from a clone with no out-of-tree path (D58, D14).
- [ ] [P1] The staleness digest provably moves when a generator source is edited and provably does not move
  when bytecode is added, so the check detects a rule change without reporting every machine as stale (D58).
- [ ] [P1] Every module with a `main` is declared as a console script, every declared script resolves to a real
  callable, and every program name a command advertises in its own help is a command that exists (D59).
- [ ] [P1] Run where no checkout can be found, the isolation command reports that nothing was checked and does
  not report an isolation failure; an explicit `--repo-root` is honoured and a nonexistent one is named (D59).
- [ ] [P1] A dataset exercising only some categories yields a scorecard naming the categories it cannot measure,
  with each such category's expectation count at zero and flagged unexercised, and a summary stating that their
  null metrics mean absent data rather than a correct agent (D60).
- [ ] [P1] The zero-defect control's scorecard states that it measures over-flagging only and that every recall
  figure is undefined by construction (D60).
- [ ] [P1] The coverage statement appears in the scored body and not in `run_metadata`; the human summary renders
  undefined metrics as a reader-facing token while the JSON still emits null (D60).
- [ ] [P1] No text read or write in `src/` or `tests/` relies on the platform default encoding, asserted over the
  parsed syntax rather than by text search, and the check is shown to fire on a bare call (D61).
- [ ] [P1] Every malformation the loader rejects is also rejected by the key-audit command, with an error naming the
  fault rather than a traceback, a bare exception repr, or a key-divergence report (D62).
- [ ] [P1] Sharing the loader has not made the audit defer to the key: a mis-targeted expectation on a structurally
  valid dataset is still reported as a divergence (D62).
- [ ] [P1] A claim-shaped field planted on an artifact with no registered check fails the suite, and a registry
  entry naming a field that exists on no split fails too (D67).
- [ ] [P1] With the secret tier present, the split enumeration includes the held-out split; dropping it fails,
  reproducing the exact shape of the defect where staleness checks iterated the dev splits alone (D67).
- [ ] [P1] The published matching policy is compared to the shipped rule on every known split, not on `dev`
  alone, and each key's declared version and identifier match its manifest's (D67).
- [ ] [P1] No timing wait exists anywhere in the package or the suite, and a newly introduced one fails (D68).
- [ ] [P1] Every numeric absence-default in shipped code carries a recorded justification; an unjustified new one
  fails, and a justification whose site has gone fails too (D68).
- [ ] [P1] No rule in any permission list is anchored on a bare stem, and the shipped guard-configuration check
  still rejects that shape (D68).
- [ ] [P1] Reference resolution is asserted to run before the multi-purchase-order rate check, so the ordering
  the unreachable defaults depend on is protected on purpose (D68).
- [ ] [P1] An uncommitted change or an untracked file in the secret tier is reported by the isolation command, a
  clean or absent tier reports nothing, and a durability finding never changes the exit code (D70).
- [ ] [P1] The held-out inputs tier is covered by the same durability check as the secret tier, with a clean secret
  tier left unreported (D71).
- [ ] [P1] An `allow` list planted in the stamped guard is rejected as an unexpected permission list, and the file
  as shipped does not trip that check (D71).
- [ ] [P1] A purchase order or goods receipt omitting its identifier is rejected naming the file and the field, an
  identifier disagreeing with its filename is rejected, and every shipped document on every split matches (D71).
- [ ] [P2] Deleting the JSONL ledger and regenerating it from the scorecard directory reproduces identical
  contents.
- [ ] [P2] The CI workflow runs the pyright gate and the full test suite on push and fails on any error.
- [ ] [P2] Running the same dataset and findings artifact on Windows and on Linux yields identical scorecard
  content outside `run_metadata`.
- [ ] [P3] A roughly 75-invoice dataset scores in under 10 seconds; when the threshold is breached a warning
  appears and the exit code remains zero.
- [ ] [P3] Under lenient matching, a finding with the right category but the wrong line identifier scores as a
  true positive, a document-scoped finding still does not match a line-scoped one, and the scorecard records
  that lenient matching was used.

---

## implementation phases

### phase 1 — credibility core (the walking slice)
- Goal: a single command scores a findings artifact against a held-out 3-way golden dataset and emits a
  trustworthy, reproducible scorecard.
- Includes: findings payload schema v1; scoring engine with strict 1:1 matching and deterministic
  tie-break; per-category precision/recall plus false-positive count and rate; scorecard emission as JSON
  and human summary with embedded fingerprints — of the findings artifact, the answer key and the inputs — plus a
  `run_metadata` envelope; a small newly-authored 3-way dataset with separate goods-receipt documents and a
  zero-defect control, alongside a labelled synthetic fixture set for values implausible in the domain; the
  initial five-category enumeration (price variance, quantity under-shipment, quantity over-shipment, quantity
  invoice-inflated, tax variance) with an explicit `LINE` or `DOCUMENT` scope; dataset selection by identifier or
  manifest path across a dev split and an out-of-tree held-out split; held-out isolation by placement plus
  deny-guards, verified by a guard-configuration check and a placement check with enforcement attested; type
  discipline under a pyright gate; and a test suite covering every `[P1]` criterion.
- Skeleton floor: all nine floor items were retained. None were dropped, so no override reason is recorded.
- Done when: every `[P1]` acceptance criterion passes by execution.

### phase 2 — tooling & scaffolding
- Goal: make the integrity story actionable and the project continuously verified.
- **Entry gate (D72): the CI workflow comes first and must be green on Linux before anything else here is
  built.** Cross-platform byte-identity is the harness's central claim and is currently asserted by
  construction only (`H17`) — every specific hazard is pinned (D49, D61, D63, and `git check-attr` confirming
  `text: unset` on every input), but never observed. CI is the cheapest Linux available and checks every
  future commit rather than one snapshot, so deferring the verification is acceptable while building further
  on the unverified claim is not.
- Includes: `--verify` recompute mode, which must report an unrecognised scorecard schema version as its own
  outcome rather than a scoring difference (D66); append-only JSONL ledger with regeneration from scorecards;
  README and methodology write-up; CI workflow running pyright and tests; cross-platform verification on
  Windows and Linux.

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
  canonically by the dataset — risk if wrong: strict matching cannot work. **Confirmed** — and **extended by
  D22**: the document is specifically the invoice under evaluation, and line identifiers are explicitly
  assigned rather than positional.
- [x] The `[P1]` dataset is newly authored, with the existing fixtures serving as schema reference only —
  risk if wrong: wasted effort or terminology bleed. **Confirmed.**
- [x] The zero-defect control comprises at least one fully clean invoice with zero expected findings — risk
  if wrong: the over-flagging measure has no basis. **Confirmed.**
- [x] Held-out answer keys live outside the repository tree in a project-specific secret directory — risk if
  wrong: keys inside the repository make the held-out claim false. **Confirmed** — and **widened by D14**:
  the whole held-out split is outside the tree, not the key alone.

---

## decisions made
Architectural calls made during the phase-1 build (full fork/options/why in `DECISIONS.md` D37–D41):
- **D37** — the scorecard serializes every `Decimal` as an exact JSON string (`null` for undefined), never a
  float or number literal, so output is byte-reproducible and float-free.
- ~~**D38**~~ — **superseded by D42.** Distinguishing the two keys by capitalisation alone could not work: the
  names are identical on a case-insensitive filesystem, so the fix only held under the assumption that made it
  unnecessary. It caused two live bugs — `core.ignorecase` made `.gitignore`'s `ANSWER_KEY*` exclude all three
  public dev keys from the repository, and the placement check had to stay case-sensitive and so was blind to a
  case-variant stray copy.
- **D42** — key filenames are **genuinely distinct, never case variants**: `holdout_answer_key.json` on the
  secret side, `dev_answer_key.json` in the repo. That lets the filename deny rule be **unscoped**, regaining
  the stray-copy coverage a filename rule exists for, and lets the placement check compare case-insensitively.
  **Case must never be load-bearing** — git normalises it on some checkouts, the same hazard family as D27.
- **D39** — pyright runs in `standard` mode (0 errors), not `strict`, because strict flags only unavoidable
  `Any` from `json.loads` at loading boundaries.
- **D40** — the D36 parse-back is dependency-free (a regex over the uncompressed PDF content stream), keeping
  the third-party set to ReportLab (generation) + pyright (type gate).
- **D41** — dataset integrity validation (timestamps, D29 tax checks) is a loader task, kept distinct from the
  scored domain rules; the scoring engine parses no document and implements no domain rule.
- Supporting implementation choices: declared constants (decimal context precision 28, ratio output 4 places,
  sentinel `"__DOCUMENT__"`); the D25 null rules applied per category as well as per case; a zero-invoice
  dataset rejected at load (the FP-rate denominator); `confidence`/`reasoning` optional but validated when
  present; stdlib `unittest` as the test framework (zero third-party test deps).

---

## emitted artifacts
n/a (build-required — see `specs/goldset-triad-harness.build-prompt.md`)

---

## changelog
- 0.23.0 (2026-07-26): **an independent sweep over the `[P2]` surface: twenty-four findings, six decisions
  (D77–D82)**. Run by a session that did not build phase 2, against green CI and a green suite — every finding
  below was invisible to both. Three are defects a user meets: a file that is not UTF-8 produced a **traceback
  rather than a named halt on five read paths** (D77), because D61 pinned every encoding and nothing named what
  happens when a pinned encoding fails — `UnicodeDecodeError` is a `ValueError`, so `dataset`'s deliberate
  `except OSError`, wrapped around a pinned read for exactly this class, missed it; a scorecard carrying
  `"schema_version": 2` instead of `"2"` was **reported as a scoring difference**, which is precisely what D66
  recorded verify mode to prevent, defeated by a `str()` at the gate (D78); and the run ledger's sort key
  **was not total**, so two splits scored inside one second tied and the rebuild order fell through to
  `os.scandir` — name-ordered on NTFS, hash-ordered on ext4 — meaning `[P2]`'s own regeneration guarantee would
  have failed on Linux and held on the machine it was written on (D80). The rest are the project's stated
  weakness with names attached: verify never checked it was pointed at the right *dataset*, and misdiagnosed the
  commonest operator error as three digest mismatches plus advice to hunt a file that never moved (D79); six
  checks asserted less than they claimed, including a CI step that could not fail, a test-count floor of 150
  against a suite of 207, and D75's warn-and-continue decision whose warning nothing asserted (D81); and four
  more instances of *correct rule, wrong universe*, one of them inside the mechanism built to end that class
  (D82). 4 acceptance criteria added (E14–E16 and the `[P2]` dataset-identity outcome); 207 → 232 tests; pyright
  0 errors. **`[P2]` remains 4 of 5: the README and methodology write-up is not built**, and is the one scope
  item with no requirement and no acceptance criterion — which is why nothing failed while it was missing.
- 0.22.0 (2026-07-26): **`[P2]`'s entry gate opened, and the first Linux run found a defect (D73)**. The CI
  workflow lands as D72 required — pyright and the full suite on `ubuntu-latest`, across Python 3.11 and 3.14,
  because 3.11 is the floor `pyproject.toml` declares and `pyrightconfig.json` targets while every verification
  to date ran on this machine's 3.14. The workflow also **asserts** that the tier-dependent tests skip rather
  than merely letting them not run: D14 puts the held-out split out of tree, so a clone must skip them, and a
  test that vanished is indistinguishable from one that skipped inside a green tick. The first run was green on
  pyright and red on exactly one test, identically on both interpreters. **D73:** the self-verification of the
  D44 repository-composition guard injects the historical `*ANSWER_KEY*` pattern and asserts the three public
  dev keys are caught — but `git check-ignore` casefolds only where `core.ignorecase` is true, so on Linux it
  caught none. The guard itself passed on both platforms; what was vacuous is the **proof that it can fire**,
  the harder failure to notice because it presents as coverage. The decoy had inherited the preconditions of the
  defect it reproduces, since the D38/D42 bug was itself only ever possible on a case-folding filesystem. D42's
  rule that case must never be load-bearing had reached artifact names and never reached the probe: correct
  rule, wrong universe, the same shape as D64a and D69. Adds the `[P2]` criterion **D66 required but never
  got** — verify mode must report an unrecognised schema version as its own outcome — which had a requirement
  in the `optional feature` block and no criterion, so verify could have been built without it and nothing
  would have failed. Also removes three restated decision ranges (`so around D55`, `D0–D36`, `D0–D68`), every
  one of them wrong, every one derivable, and all the same class as the hand-written subject index the 0.10.3
  sweep replaced with a generated one. 1 acceptance criterion added; 190 tests.
- 0.21.0 (2026-07-26): **the held-out tier gets a durability story, three gaps close, and Linux becomes `[P2]`'s
  entry gate (D71, D72)**. The held-out inputs tier is now a git repository — the last tier with none, and the one
  whose loss is worst: a scorecard embeds a digest of exactly those bytes (D27), so without them every held-out
  result is permanently unverifiable. It needed its own `.gitattributes` (attributes stop at a repository boundary,
  so the harness's byte-pinning could never reach it) and a README refusing publication with the reason stated:
  the matching policy is deliberately published (D53), so **these inputs plus that policy are enough to derive the
  key**, and readable-by-the-agent is not the same property as publishable. Three gaps closed: a rule's named
  enforcement is now **resolved** rather than word-matched — `Enforced by test_completely_imaginary_module.py`
  passed clean before, D59's defect inside the mechanism built to stop it, demonstrated before being fixed; the
  guard file's shape is asserted, since an `allow` list would grant reach in the file whose purpose is to withhold
  it; and document identity no longer falls back to the filename, which kept the `.json` extension and so turned a
  missing `po_number` into a phantom-reference report against the answer key. Two under-isolated tests surfaced:
  three pinned only one tier override, and three more silently bypassed the `_deny_rules` seam and began asserting
  against shipped rules instead of their fixtures. **D72** makes CI-green-on-Linux `[P2]`'s entry gate rather than
  an item within it: every specific cross-platform hazard is pinned (D49, D61, D63, plus `git check-attr`
  confirming `text: unset` on every input), but never observed, and WSL here is registered as version 1 which this
  machine will not run. 7 acceptance criteria added; 190 tests.
- 0.20.0 (2026-07-26): **the tier you inspect is not the tier that survives (D70)** — found minutes after D67
  shipped, and by the same reasoning. Every isolation check reads the secret tier's **working tree**: the stamped
  guard against the template on disk, each manifest's digest. Nothing looked at what was *committed* — and the
  guard template and held-out manifest were sitting uncommitted while the harness half of the same two decisions
  was already pushed. A disk failure then would have lost D65's anchored rules and D63's re-stamp, and a restore
  would have left the template **behind** the stamped copy that claims to derive from it, inverting which one is
  authoritative. Closing that single-disk risk is why the secret repository exists, so a check that never read its
  history was watching the wrong thing. `check_secret_tier_durability()` now reports uncommitted changes and
  unpushed commits — committed is not safe either — and is **advisory by construction**: excluded from `ok`, so
  the exit code never moves. A failing test was rejected because it would fire during any normal editing session on
  the secret side, and D65 already established that a guard obstructing routine work is one people switch off.
  2 acceptance criteria added; 183 tests.
- 0.19.0 (2026-07-26): **the recurring classes get mechanisms instead of memory (D67, D68, D69)** — a response
  to the observation that two sessions reviewing each other kept re-finding the same shapes. The diagnosis is in
  D67: **D59 stated the rule "every claim gets a check" and the same commit shipped two unchecked claims**, which
  the next session found as D64. The failure is not carelessness; a rule living in prose is applied by memory, and
  memory is per-session. **D67** adds a claim registry — every claim-shaped field bound to the check that compares
  it — and, more importantly, one shared `known_splits()` enumeration, because D64a's gap was *structural*: every
  staleness check iterated the dev splits, so no amount of care could inspect the held-out one. Writing it
  surfaced three more instances of its own class: both policy checks read `datasets/dev` alone, leaving the
  published rule uncompared on the other three splits including held-out. **D68** locks four recurring classes
  with scanners — timing waits (at zero as of one commit ago; a `sleep(1.05)` had survived four sweeps *while a
  neighbouring docstring criticised it*), numeric absence-defaults, unanchored patterns across every rule list,
  and order-dependent correctness. **D69** closes a live collision found while wiring this up: two sessions
  appended to the criteria map concurrently and both took C46–C49, so four ids each named two criteria — the
  duplicate-numbering rule existed and its enforcement had never reached a Python list. A `## Not checked`
  section now records what a sweep deliberately left, and the linter requires it to be stamped current.
  Two numbered sets collided in this one session, in fact: the criteria ids, and **this changelog's own version
  numbers**, where both sessions minted a `0.18.0`. `lint_spec.py` now checks changelog versions for uniqueness
  and descending order as well. 15 acceptance criteria added; 178 tests.
- 0.18.0 (2026-07-26): fifth sweep — reviewing the fourth's work found eight issues, five of them defects.
  **D63:** the generator staleness digest hashed raw bytes of source that lives outside git, so a
  line-ending-only change — proven AST-identical — reported a stale dataset; it now digests normalized text.
  **D64:** two artifacts declared an authority nothing enforced — the held-out stamp was never compared
  (the split whose numbers carry weight), and the stamped guard was never compared to the template that calls
  itself the source of truth; both now checked under D58's skip-when-absent pattern. **D65:** the generator
  Bash deny rules were unanchored, denying `regenerate.sh` and `git log --grep=generate.py` — over-blocking is
  its own failure class, since a guard that obstructs routine work is one people switch off; patterns anchored
  and the check now rejects a bare stem. **D66:** the scorecard schema version becomes a requirement, recorded
  before `[P2]` designs verify mode, so a shape change cannot be reported as a scoring difference. Also removed
  a vestigial 1.05s sleep the neighbouring test criticised, and distinguished `[P1]` console-script declaration
  from `[P5]` publishable packaging. 2 acceptance criteria added.
- 0.17.0 (2026-07-26): **the audit refuses what the scorer refuses (D62)**, plus **explicit encodings (D61)**.
  `audit()` never called the loader, so every validator a scoring run applies was skipped on the audit path. This
  was ranked *last* of the four review issues on the belief that its failure mode was a confusing message —
  **that was wrong, and measuring it showed so**: with the fix neutralized, three of seven malformed datasets
  came back **"consistent"**, including a dropped correspondence row, and two more were reported as key
  divergences. The auditor walks the correspondence it is given, so an omission is a line it never examines —
  D48's self-consistency trap, now shown to apply to the auditor itself. Validity now comes through the same
  front door; derivation stays independent, asserted by a test that a mis-targeted expectation is still caught.
  D61 rides along because it fired during this work: text reads with no encoding decode with the platform
  default, which is cp1252 here, so any file acquiring a byte cp1252 leaves undefined breaks the suite **on
  Windows only** — the fourth appearance of the line-ending/encoding class from D49. An AST guard now fails on
  any implicit-encoding call. 6 acceptance criteria added; 152 tests.
- 0.16.0 (2026-07-26): **the scorecard states what the dataset could not measure (D60)** — the held-out split
  exercises 2 of 5 categories, so three came back `null`, and D25's `null` means "undefined" without saying
  *why*. Undefined spans "not applicable", "not attempted" and "not asked", and a reader who cannot tell them
  apart picks the flattering one — on the one split whose numbers carry weight. Nothing needed computing:
  `tp + fn` already was the expectation count, so the defect was the scorecard declining to state what it
  already knew. A `coverage` block in the scored body names what is and is not exercised; the summary marks each
  unexercised row and spells out the consequence. The zero-defect control now says it measures over-flagging
  only, rather than presenting as an agent that recalled nothing. Two things this exposed: the summary printed
  Python's `None` into the durable human record (now `n/a`, with JSON still emitting `null`), and the scored
  body's shape changed, so the scorecard schema goes `"1"` → `"2"`. 3 acceptance criteria added; 147 tests.
- 0.15.0 (2026-07-26): **every advertised command exists (D59)** — `audit_key`'s own help introduced itself as
  `goldset-triad-audit-key` while `pyproject.toml` declared only `goldset-triad`, so following the tool's
  instructions produced command-not-found; the isolation check had no script at all. Invisible because every test
  and every manual run used `python -m goldset_triad.<module>`, which works either way — the same shape as D58:
  a claim nothing compared against reality. Three checks now run in opposite directions (module → declaration,
  declaration → callable, advertised name → declaration). Declaring the scripts then exposed two latent faults:
  `check_isolation.main` ignored the arguments it accepted, so the new command swallowed `--help` and typos; and
  the repository root came from `__file__`, so an installed copy announced *"the deny-guards are unconfigured"* —
  an isolation failure that had not occurred, D50's misdiagnosis in the most trust-costly direction. Verified in
  a throwaway venv. 2 acceptance criteria added; 140 tests.
- 0.14.0 (2026-07-26): **generator staleness becomes detectable (D58)** — closes the first of four issues the
  post-build review left open, taken first because it is the only one whose cost of fixing *rises* with delay:
  the fix requires regenerating every split, which is one command over four tiny datasets at `[P1]` and an event
  with its own risk at `[P3]`. The generator lives out of tree and agent-denied (D14, D17), so nothing in the
  repository could notice that a domain rule changed and the data was never regenerated — and a stale dataset
  fails no existing check, because the audit re-derives from inputs that are stale in the same way the key is.
  Every mechanical signal stays green while the whole dataset describes rules that no longer exist. Each manifest
  now carries `generator_sha256`, verified in two halves: carrying a stamp and agreeing across splits needs no
  generator and runs in CI, while matching the current source skips cleanly when the generator is absent, since
  D14 requires the suite to pass from a clone. Proven by mutating a rule and observing the suite go red, naming
  the stale dataset. 4 acceptance criteria added; 132 tests.
- 0.13.0 (2026-07-26): **formalizes the behaviours that lived only in code** — the remaining unrecorded
  assumptions. **D55:** three scoring micro-semantics become requirements — a `MATCH` is ineligible to *satisfy*
  an expectation as well as to be a flag (D13 settled only the latter), a finding whose target is absent is
  excluded from matching outright, and surplus flags on a key holding no expectation are ordinary false
  positives rather than duplicate contention. Two further micro-semantics initially listed as undocumented
  turned out already stated; a phrase grep over a line-wrapped document had under-reported them. **D56:** the
  answer key declares **exactly one** correspondence entry per invoice line — two rows mapping one line to
  different purchase-order lines made the audit union conflicting derivations. **D57:** the dev split's coverage
  is asserted rather than assumed, the zero-defect control is pinned to zero expectations, and a phase-scoped
  dataset property is enforced by a named tripwire — the manifest `profile` field this sweep first proposed was
  rejected as machinery duplicating D47's existing tripwire and partly contradicting it. 4 acceptance criteria
  added; 128 tests.
- 0.12.0 (2026-07-26): **second sweep, over code and data as well as documents** — 13 findings, all fixed,
  recorded as D49–D54. Two were live rule violations: scorecards written inside the same second **overwrote**
  each other (the run stamp is second-precision by D6), and the scorecard writer emitted platform-dependent
  line endings, so the durable record's bytes differed between Windows and Linux — the third instance of the
  newline-translation class and the first in shipping code (**D49**). Five ground-truth reference holes were
  demonstrated accepted at load and are now rejected with named causes, including an expected finding naming a
  line that does not exist, which would have scored as a permanent false negative against every agent
  (**D50**). The public invoice-index name was a **substring** of the held-out one, so a deny rule for the
  held-out artifact would silently over-block the public split — D42's lesson in a new disguise (**D51**). The
  secret-artifact vocabulary existed twice and the copy had already drifted (**D52**). The published policy was
  bound only to the non-shipping generator (**D53**). Traceability was one-directional and had already fallen
  behind by 28 tests (**D54**). Also corrected the sweep marker, which read `@ D46` although the same commit
  added D45–D48. 11 acceptance criteria added; 121 tests.
- 0.11.0 (2026-07-26): **full pre-phase-2 sweep** over spec, decisions, build prompt, all four datasets, the
  in-repo code, the secret-side generator, the guards and cross-platform behaviour — the first sweep to cover
  code and data rather than documents alone. Four decisions recorded. **D45:** two more artifacts had D42's
  flaw. The held-out invoice index — agent-denied ground truth under D34 — was named `invoice_index.json` like
  three *public* dev indexes, so it could be given **no filename deny rule and no placement-check entry**,
  leaving it protected by directory placement alone, uniquely weaker than every other secret artifact; and
  generator **bytecode** (`__pycache__` exists on disk) is decompilable yet evaded rules naming only `.py`.
  Renamed to `holdout_invoice_index.json`, filename rules widened to an extension wildcard, and the placement
  check now matches on the **stem**, case-insensitively, so `gen_rules.cpython-314.pyc` is caught. **D46:** the
  published `matching_policy.json` threshold was a **hand-written literal** while the real constants lived in
  `gen_rules.py` — change one and the policy would have promised the other, undetected, because the audit never
  reads the policy. Now interpolated from the constants, and the D23/D28 precision rule is published because it
  decides **boundary** cases. **D47:** multi-PO tax attribution was decided *only in code* (flag if any PO's
  rate says material); zero multi-PO invoices exist today, so it is latent, but it goes live at `[P3]` — a
  differing-rate multi-PO invoice must now be rejected as unspecified, with the intended apportionment formula
  recorded. **D48:** the key audit's completeness is bounded by the correspondence in the key it audits, so an
  omission that is self-consistent passes; stated as a limit, with a completeness check noted. Also refreshed the
  subject index (three rows stale) and the sweep marker. Verified: regeneration changed **only**
  `matching_policy.json`, every input, key and index byte-identical, confirming D33; 100 tests, pyright 0, lint
  0 errors with all 29 decision references resolving.
- 0.10.6 (2026-07-26): adds a `[P1]` acceptance criterion covering **repository composition** (D44). Every
  existing check reads the filesystem, where a file excluded from git is still plainly present -- so the
  `ANSWER_KEY*` ignore rule fixed in D42 would have dropped all three public dev keys from the commit while the
  entire suite stayed green, making "the dev split ships complete" and "the suite passes from the repository
  alone" silently false. The new criterion asserts over git's ignore rules and index instead. No requirement,
  scope item or phase changed; one criterion added.
- 0.10.5 (2026-07-26): phase-1 build completed. Filled the `## decisions made` block and appended D37–D41 to
  `DECISIONS.md` (scorecard Decimal-as-string; held-out key filename; pyright standard mode; dependency-free
  parse-back; loader-validation vs scored-rules boundary). No requirement, criterion, scope item or phase
  changed — the build implemented the existing `[P1]` spec. All `[P1]` acceptance criteria pass by execution
  (95 tests, pyright 0 errors, key-audit consistent, isolation checks pass); the four generation-side /
  environment-level criteria are verified and documented in the traceability map.
- 0.10.4 (2026-07-26): adds a **staleness marker and sweep trigger** to metadata. Three maintenance passes
  happened only because someone asked for them — an observation that periodic maintenance finds drift is not a
  mechanism. The marker records when the spec was last swept, at which version and decision number, so "is a
  sweep due?" is answerable at a glance rather than from memory. The trigger is **change-based rather than
  calendar-based**, because drift accumulates per decision and not per day: this spec ran seven versions and
  roughly twenty decisions before its first sweep, and that is precisely the interval where the defects
  accumulated, while a monthly reminder would have fired during quiet weeks and stayed silent through the heavy
  design run. Mechanical drift — duplicate requirements, misfiled EARS patterns, dangling decision references —
  is now caught by `lint_spec.py` as of toolkit `647d185`, so the sweep's remaining job is the part no linter
  can do: spec-to-build-prompt agreement.
- 0.10.3 (2026-07-26): **confirmation pass after the sweep and restructure** — deliberately scoped to what those
  two had *not* tested, rather than repeating them. Eight findings, six of them in the **build prompt, which
  neither earlier pass had opened** — and which is the document the build session actually reads, so drift there
  is worse than drift in the spec. Build prompt: the match key was still the pre-D20 `Status + Category +
  TargetLine`, **missing `scope` entirely**, so a builder working from it would have implemented the wrong key;
  two fingerprints named where there are four; the actor table still said "three actors" after 0.10.1 made it
  four; the manifest still called a dataset "a pair of locations" naming only inputs and key, omitting the
  invoice index; the floor items were numbered 1–7, 10, 8, 9 after an insertion; and the dev split was described
  twice. Spec: the **subject index added in 0.10.2 was wrong in six of nine rows** — including two rows made
  wrong by moves performed minutes earlier in that same commit, since it was written by hand before the moves
  finished. It is now **generated by script from actual section membership** and errs toward over-inclusion,
  because a spurious "check here" costs a glance while a missing one costs a contradiction. Also documented that
  the non-functional block's `- Security: [P1] …` formatting makes it invisible to pattern-based tooling,
  including that generator.
- 0.10.2 (2026-07-26): **structural regrouping (T1/T2 from the sweep).** Pure reorganisation — no requirement
  was added, removed or reworded except where an EARS keyword had to change to match its new section. **T1:**
  every misfiled requirement moved to its correct pattern. The `ubiquitous` block had accumulated `WHEN`, `IF`
  and `WHERE` statements from D24, D28, D29 and D36, while `event-driven` held a dozen always-true statements
  from D22, D31, D33, D34 and D35 that trigger on nothing. Two `WHERE` clauses were mislabelled rather than
  misplaced: an undefined metric is not a feature flag, so it becomes ubiquitous, and a digest mismatch is a
  detected fault, so it becomes `IF`. **T2:** the `ubiquitous` block is now grouped by subject under italic
  sub-headings — truth-source architecture, ground-truth artifacts, generation invariants, category and scope,
  numeric discipline, determinism and integrity. Because EARS groups by *pattern*, a subject must still span
  sections, so a **subject index** was added naming every section each subject touches, with an explicit
  instruction to read all of them before amending one. That scattering is what let contradictions survive seven
  versions until the 0.10.1 sweep. **Verification:** the SHALL count was used as a checksum and returned to
  exactly 127, its pre-restructure value — an intermediate state briefly hit 136, which caught nine duplicates
  created mid-move and would otherwise have been invisible. Criteria unchanged at 90.
- 0.10.1 (2026-07-26): **consistency sweep** — the first pass reading the spec as a whole rather than answering
  a question against it. Found five contradictions and eight stale passages, every one of them a later decision
  correctly applied in one place and missed in another. **Contradictions:** a criterion suppressed precision on
  the control while D25 requires `null`; a criterion had the tax overcharge "flagged on the correct line" though
  D20/D21 made tax document-scoped; the determinism boundary still credited the *harness* with the key's
  arithmetic and with canary probing, both moved or abolished by D35 and D30; out-of-scope barred document
  parsing outright although D36 requires the generator to parse its own output; and "harness" versus "scoring
  engine" had become load-bearing but undefined, making the audit-command requirement self-contradictory — now
  resolved by a four-component table. **Stale:** two fingerprints named where there are four, a stale date, the
  decision record cited as D0–D12, the prior-decisions block missing D13–D36 entirely, lenient mode still
  dropping the whole `TargetLine`, permissions omitting the invoice index, the manifest naming two artifacts
  instead of three, and two overlapping in-scope dataset items. No behavioural change: every fix aligns the spec
  with a decision already taken. Structural regrouping (misfiled EARS patterns, scattered subjects) is
  deliberately left to a separate change.
- 0.10.0 (2026-07-26): **corrects a misattribution running through the whole requirements block.** **D35:** the
  spec phrased scoring semantics as things "the harness SHALL compute" while also treating the answer key as
  indispensable ground truth — saying both. The scorer in fact needs **no domain rule at all**: it needs the
  match key, counting, and the invoice index for target validation and the FP-rate denominator. So the
  payable-quantity rule, the materiality threshold, the price measurement, the tax expectation and its
  cross-multiplied comparison, the zero-taxable branch and the receipt summation are all **re-attributed to the
  key generator**, and must appear in the published matching policy so the agent can implement them. This is not
  tidiness: a scorer that derived expectations would score the agent against its own rule implementation rather
  than audited truth, making any bug in it silently authoritative and collapsing "golden dataset" into
  "reference implementation" — and it is not even achievable, since derivation needs the correspondence D22
  places in the key. A **separate key-audit command** derives and diffs against the key, addressing the standing
  risk that a wrong key produces confidently wrong scores; it never runs inside a scoring run, and is labelled a
  consistency check rather than a correctness proof, since generator and auditor share an author. **D36:** the
  invoice document and its index entry are emitted from **one canonical record in a single pass**, so they cannot
  diverge by construction, with a **generation-time parse-back** closing the residual rendering-bug case.
  Parsing is permitted there because D34 bars a parser from the *scoring engine*, not from the generator. Two
  limits recorded: parse-back suits only the clean text-layer tier, and the check is attested rather than
  shipped. Adds a three-actor preamble to the requirements block.
- 0.9.0 (2026-07-26): resolves the contradiction D31 created and answers where structured invoice data comes
  from. **D33 corrects a stale constraint:** the PDF-authoring library was deferred to `[P3]` as "not needed
  now", but D31 made invoices supplier PDFs and the dev split needs authoring immediately. The deferral had
  conflated the *library* with *format difficulty* — ReportLab enters at `[P1]` for clean text-layer invoices
  while dot-matrix, consolidated and scanned tiers stay `[P3]`. ReportLab specifically because PDF writers embed
  a creation timestamp and document ID by default, so regeneration yields different bytes, changing the D27
  inputs digest and collapsing byte-reproducibility at the data layer while presenting as tampering; ReportLab
  documents an invariant output mode for exactly this. Generation must pin document dates to the seeded
  timestamp and pin or suppress the ID. The stdlib-only rule is unaffected — it is scoped to the scoring engine,
  and this dependency sits on the generation side. **D34:** the harness obtains structured invoice data from a
  **structured invoice index** held in the agent-denied tier, never by parsing documents. It is a complete line
  inventory including clean lines, because target validation must distinguish a line that exists from one that
  does not — something the expected findings alone cannot support. It is agent-denied because structured invoice
  data would bypass the extraction the document form exists to require, and it is separate from the key so the
  key stays a statement of expected findings rather than a restatement of inputs. By D27's own reasoning it is
  also fingerprinted, bringing the scorecard to four fingerprints: findings, key, invoice index, and inputs
  aggregate.
- 0.8.0 (2026-07-26): **removes an unsatisfiable criterion** and settles dataset shape. **D30:** the canary
  criterion required code to confirm the guarded area is "unreachable from an agent context" — impossible, since
  deny rules bind tool calls while a subprocess runs beneath that boundary, so a reachability probe would report
  failure unconditionally and fail identically whether the guards were perfect or absent. Replaced by two
  genuinely deterministic checks — deny rules cover every secret path; no secret artifact anywhere in the tree —
  with harness enforcement recorded as a **dated manual attestation** using the canary as its decoy, and a
  requirement that published claims state only what is actually verified. **D31:** goods receipts become
  **separate documents** with their own identifiers, rather than a `receipts[]` array inside each PO record,
  because co-location lets an agent find quantity discrepancies by diffing two fields in one file without ever
  opening an invoice. Invoices stay supplier PDFs; PO database and receipts are internal structured JSON. Adds
  the rule D15 omitted: received quantity is the **sum across all receipts** for a line, since partial
  deliveries produce several. **D32:** three data families — a realistic portfolio-facing dev split, a small
  labelled synthetic fixture set for values implausible in the domain (only the $100,000 line qualifies), and
  the out-of-tree held-out split; synthetic fixtures load through the same manifest and loader so no parallel
  code path exists.
- 0.7.0 (2026-07-25): **fixes a defect in D28.** D28's cross-multiplied tax comparison is valid only where the
  purchase-order taxable subtotal is positive; at zero the transformation destroys the inequality, reducing to
  zero against zero so that **every** such invoice flags — and flags identically whether the invoice charged
  nothing or fifty dollars, the invoiced tax being annihilated by the multiplication. **D29** adds an explicit
  branch: with no taxable lines, expected tax is zero and the invoiced tax is compared directly against a
  threshold that degenerates to five cents, so a correct `Tax: 0.00` produces no finding while any real charge
  flags. Two supporting rules: a purchase order with a zero taxable subtotal but non-zero tax is **malformed**
  and rejected at load, which is what makes the expected-tax-is-zero convention safe; and the tax field SHALL
  always be **present** as `0.00` rather than absent, matching single-template printing behaviour and removing
  the absent-versus-zero ambiguity. Also records that the original frequency argument leaned on AI-generated
  fixtures — weak evidence, correctly challenged — while the defect itself holds for even one exempt purchase
  order. A sweep of the other multiply-through formulas confirmed tax was the only one that broke.
- 0.6.0 (2026-07-25): fourth round of build-session questions — both found holes in earlier decisions rather
  than unspecified detail. **D27 completes D10:** the dataset inputs are now fingerprinted. D10's premise is
  that a scorecard is recomputable rather than trustworthy, but recomputation is only pinned if every
  score-determining input is pinned — and the inputs set the false-positive-rate denominator and drive target
  validation, so an edited input under an unchanged key and version scored differently while provenance looked
  identical. Adds a precisely specified aggregate digest (recursive, forward-slash-normalized relative paths,
  byte-wise sorted, raw file bytes) with per-file digests recomputed on mismatch, plus a `.gitattributes`
  constraint: without disabling line-ending conversion, a Windows and a Linux checkout digest differently and
  the cross-platform requirement fails as an apparent harness bug. **D28 removes the one place D23's "exact"
  was untrue:** the derived tax rate is generally non-terminating, and `Decimal` division rounds to the ambient
  context precision. The tax decision is now evaluated in cross-multiplied form — multiplication and
  subtraction only, no division, genuinely exact. That also exposed a second hole: precision, recall and the
  false-positive rate are divisions whose emitted bytes fall under the byte-identical comparison, so they now
  carry a declared output precision and `ROUND_HALF_UP`, and the decimal context precision is pinned to a
  declared constant. Without that, U4 was quietly unenforceable.
- 0.5.0 (2026-07-25): third round of build-session questions, one of which **corrected an error in this spec**.
  **D23:** rounding policy — compute and compare at full `Decimal` precision, never rounding before a
  comparison; round to 2dp only for display, explicitly `ROUND_HALF_UP` because Python's `Decimal` defaults to
  banker's rounding. Amounts are not part of the match key, so rounding decides only whether a finding exists
  and how it is shown. The "one cent below" criterion was restated: it presumed a cent-aligned threshold, and
  is now two criteria, one aligned and one deliberately not. **D24:** expected tax is computed on the
  **invoiced** taxable subtotal, not the payable one, so a price or quantity error does not cascade into an
  additional `TAX_VARIANCE` and pollute per-category recall. **D25 (correction):** the previous requirement
  suppressed precision on the zero-defect control as undefined, but `0/3` is defined and is the result that
  carries the signal — precision is null only where the agent raised no flags, recall is null unconditionally,
  and undefined is emitted as null rather than zero or an omitted key. **D26:** contention is resolved by
  canonical-serialization order, never by position in the findings artifact, which would violate
  order-reversal invariance; duplicate contention is additionally reported as its own diagnostic, since an
  agent emitting duplicates has a defect an undifferentiated false-positive count would hide.
- 0.4.0 (2026-07-25): second round of build-session semantics questions. **D19:** the two-percent term's basis
  is the **payable** extended amount (payable quantity × PO unit price); the invoiced extended amount is
  disqualified because an inflated invoice would enlarge its own denominator and understate the variance
  ratio. **D20:** findings gain an explicit `scope` of `LINE` or `DOCUMENT`, and the match key becomes status
  + category + scope + target — a **schema change made now rather than at P4**, because duplicate invoice,
  invalid PO reference, currency, segregation-of-duties and sanctions are all document-scoped and the payload
  schema is the port. **D21:** `TAX_VARIANCE` is document-scoped and uses the unified threshold against the
  taxable subtotal, per D3 scoping P1's tax check as arithmetic rather than compliance. **D22:** `TargetLine`
  anchors on the invoice; line identifiers are explicit, never positional; the invoice→PO→receipt
  correspondence is declared in the answer key but withheld from agent-readable inputs, because resolving it
  is the capability under test. Also promoted the match-key composition from a prior decision to an explicit
  requirement, where it belonged. Minor-version bump: schema and requirements both widened.
- 0.3.0 (2026-07-25): resolved four questions raised by the build session — the scoring semantics that decide
  which lines the answer key marks. **D15:** quantity discrepancies anchor on the payable quantity, the
  lesser of ordered and received, and the category names which constraint bound it; a third category
  `QTY_INVOICE_INFLATED` was added because three situations exist and two categories necessarily mislabel
  one. **D16:** the 2% and $25 thresholds combine as `max($0.05, min(2% × extended, $25))` flagged on `>=`,
  measured at the payable quantity; the previously-recommended `max(2%, $25)` was rejected for tolerating a
  $1,999 variance on a $100,000 line. **D17:** the out-of-tree layout uses sibling directories, and a dataset
  is resolved through a manifest naming inputs and key separately. **D18:** `invoice_count` and
  `finding_count` move out of `run_metadata` into the scored body — they are deterministic, and leaving them
  in the excluded envelope made a miscount invisible to the reproducibility check. Minor-version bump: the
  category enum grew and requirements were added.
- 0.2.0 (2026-07-25): **added requirements** — enumerated exactly what lives outside the repository tree
  (D14). Previously the spec named only the answer key, leaving the generators (recorded as secret-side in
  D5 but never stated as a requirement), the discrepancy-design artifact, and the held-out dataset inputs
  unspecified. The whole held-out split is now outside the tree. Adds the distinction the earlier wording
  conflated: *outside the repo* and *deny-guarded* are different sets — the held-out inputs are out-of-repo
  yet must stay agent-readable, or evaluation cannot run at all. Four security requirements and four
  acceptance criteria added; minor-version bump because this widens scope rather than restating it.
- 0.1.2 (2026-07-25): documentation correction only. Removed a caveat in the phase-tag map warning that a
  bracketed tag written in prose would be miscounted as a real tag — true when 0.1.1 was written, and fixed
  upstream in toolkit `4a55439`, which reads tags only from bullet lines in the blocks that carry tagged
  items. No requirement, criterion, scope item or phase changed.
- 0.1.1 (2026-07-25): metadata backfill only — added `Produced by`, `Artifacts land in`, `Visibility`,
  `Decision record`, `Reproducibility`, `Timestamp standard` and `Integrity`. These fields were introduced
  to the toolkit template in `b248d15`, after this spec was written at `821fac1`. No requirement,
  criterion, scope or phase changed: every value was already decided (A1, A8, D6, D9, D10, D11.1) and is
  merely now stated where the template expects it.
- 0.1.0 (2026-07-25): initial specification. Interview-derived; decisions D0–D12 recorded in
  `DECISIONS.md`. Phase tags renumbered from the interview's P1a/P1b to `[P1]`/`[P2]` for linter
  conformance.
