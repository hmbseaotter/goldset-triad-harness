# Build prompt — goldset-triad-harness, PHASE 2 (tooling & scaffolding)

Hand this file to a building agent (a fresh Claude Code session or equivalent) together with the spec. It
targets **phase 2 only**.

## Read first

1. `specs/goldset-triad-harness.md` — the complete specification. Read it fully before writing any code.
   Phase 2's scope is the `### phase 2` block plus every `[P2]` tag in the requirements and acceptance
   criteria.
2. `DECISIONS.md` (repo root) — the decision record **in full, to its last heading**. Do not relitigate these;
   if one looks unsafe or wrong, say so before building. The extent is deliberately not restated here: it read
   `D0–D72` while D73–D82 sat above it, which is the class spec 0.22.0 removed from three other places.
3. `specs/goldset-triad-harness.build-prompt.md` — the **phase 1** prompt. Read it for the constraints that
   still bind (determinism boundary, type discipline, stack, clean-room terminology, the never-do list). Its
   *scope* section is finished work; its *constraints* section is still in force.

**State at handoff:** spec `0.21.0`, decisions `D0–D72`, 190 tests passing, pyright 0 errors, all four keys
audit consistent, regeneration reproduces every dataset byte-for-byte. *(Historical — this is what was true
when the prompt was written, and it stays as written.)*

**State now (2026-07-26, spec `0.23.0` @ D82):** phase 2 is **4 of 5**. Built and verified by execution: the CI
workflow, verify mode, the run ledger, and the cross-platform observation that turned `H17` from a
by-construction claim into a result. **Not built: item 4, the README and methodology write-up** — which is also
the one item in the list below with no `SHALL` in the spec and no acceptance criterion, so nothing failed while
it was missing. Whether it gets a requirement and a criterion before it gets written is an open question, not a
settled one. All six items in the phase-2 acceptance gate at the foot of this file pass; that gate never
covered item 4. An independent sweep over the completed work landed **D77–D82** (twenty-four findings against a
green suite and green CI) — read those before extending any of it.

## Recommended build-time settings

**Model: Claude Opus 5. Reasoning effort: Extra (xhigh).** Phase 2 is lighter on subtle arithmetic than phase
1 but heavier on cross-platform behaviour and on not breaking a heavily-verified core. Do not silently
downgrade.

## Work in this order

1. **Restate the outcome in one sentence.**
2. **Build the CI workflow FIRST and get it green on Linux.** This is an entry gate, not a task ordering
   preference — see below.
3. **List any remaining ambiguities.** Phase 1 surfaced roughly thirty; phase 2's semantics are simpler, but
   the ledger's record shape and verify's comparison scope both have real forks.
4. **PLAN GATE — present an implementation plan and get human approval BEFORE writing further code.**
5. Build **only** phase 2.
6. Verify every `[P2]` acceptance criterion **by running it**.

## The entry gate (D72) — read this before anything else

**CI green on Linux must come first. Nothing else in phase 2 may be built until it is.**

Cross-platform byte-identity is this harness's central claim and is currently asserted **by construction
only** (traceability entry `H17`). Every specific hazard has been individually pinned — shipped output pins LF
(D49), every text read names its encoding (D61, AST-guarded), the generator digest normalizes text so line
endings cannot move it (D63), and `git check-attr` confirms `text: unset` on every dataset input, key and
manifest. That is a mechanism corroborated, not a result observed.

The rule D72 records generalises past this project: **when a claim can only be verified by infrastructure a
later phase will build, make that infrastructure the phase's entry gate. Deferring the verification is
acceptable; building further on the unverified claim is not.**

**A known asymmetry to handle, not discover.** The backslash deny-rule variants (`Bash(*\gen_rules.*)`) can
never match on Linux, so the guard is *weaker* there — not broken, since the space and forward-slash variants
still fire. Decide deliberately what CI should do about this and record it; do not let a Linux run "discover"
it as a surprise.

**Expect the first Linux run to fail on something.** That is the point of the gate. Whatever it finds is a
real finding about a claim the project has been making, and belongs in `DECISIONS.md`.

## Build ONLY phase 2

1. **CI workflow** — GitHub Actions running the pyright gate and the full test suite on push. **Entry gate;
   build first.** It can only ever reach the **dev split**: D14 puts the whole held-out split out of tree, so
   the suite must pass from a clone with no secret tier configured. Several existing tests skip cleanly when
   the secret tier is absent — confirm in CI that they *skip* rather than silently vanish.
2. **`--verify` recompute mode** — recompute a scorecard from its embedded fingerprints and diff it against
   what is stored; exit non-zero on any mismatch. **D66 governs the schema case**: a scorecard whose schema
   version is unrecognised must be reported as *its own outcome*, never as a scoring difference. The
   scorecard schema is currently `"2"` (D60 raised it from `"1"` when the scored body gained a coverage
   block).
3. **Append-only JSONL run ledger** — one record appended per run, and a rebuild command that regenerates it
   **from the scorecard directory alone**. Per D9 the ledger is a *convenience view*: local-only, gitignored
   (`run-ledger.jsonl`, `*.ledger.jsonl` are already ignored), and regenerable — which is precisely why
   deleting it may lose nothing. Scorecards are the durable record and are deliberately **not** ignored.
4. **README and methodology write-up** — the portfolio-facing artifact a reviewer actually reads:
   golden-dataset framing, the isolation story, the held-out rationale. **Publish only what is verified**
   (D30): placement and guard configuration are checked automatically, harness enforcement is attested with a
   dated record, and a determined subprocess is outside deny coverage by design. The thresholds and their
   reasoning are published without claiming they represent industry standard practice (D16).
5. **Cross-platform verification** — identical scorecard content on Windows and Linux outside `run_metadata`.
   Largely delivered *by* the entry gate; what remains is converting `H17` in the traceability map from a
   `MANUAL:` entry into an observed result, and recording honestly whatever the Linux run reveals.

**Higher phases are documented-but-not-yet. Do NOT build them, and do NOT make architectural choices that
block them.** Out of this push: dataset expansion, the performance budget, lenient match mode (`[P3]`);
compliance categories (`[P4]`); publishable packaging, the runner adapter, confidence calibration (`[P5]`).

## Constraints that still bind

Everything in the phase-1 prompt's **Non-negotiable constraints** section applies unchanged. The ones phase 2
is most likely to brush against:

- **No LLM call and no network call at runtime.** CI runs the harness; the harness still calls nothing.
- **The scoring engine imports standard library only.** Verify mode and the ledger are harness surface — keep
  them stdlib. A new dependency needs flagging for approval first.
- **`Decimal` for money, never `float`.** Verify mode compares recomputed values; do not let a float creep in
  through a JSON round-trip. The scorecard emits money as exact strings and ratios at declared precision
  (D37, D28) — read them back with `parse_float=Decimal`.
- **Pin `encoding` and `newline` on every text read and write** (D61, D49, D63). Ledger and README included.
  An AST guard already fails the suite on an implicit-encoding call.
- **Timestamps are UTC ISO-8601 `Z` at second precision** (D6). The ledger inherits this; do not reach for
  sub-second precision to make records unique — D49 solved that class with an ordinal instead.
- **Every halt names its specific cause and exits non-zero.** Verify mode's mismatch report is a halt with a
  named cause, not a diff dump.

## Mechanisms you must feed, not just satisfy

Phase 1 ended by converting several remembered rules into mechanisms. New work must register with them or the
suite will fail — by design:

- **Claims registry (D67)** — every claim an artifact makes about another must be registered against the
  check that compares them, on every split. `tests/test_claim_coverage.py` enforces it. Verify mode and the
  ledger both make claims about scorecards; register them.
- **Defect-class scanners (D68)** — each recurring class is locked by a scanner at the moment it reaches
  zero: timing waits, absence-becoming-a-number, unanchored patterns, order-dependent correctness. Do not
  reintroduce one; if phase 2 finds a fifth class, lock it the same way.
- **Criterion ids (D69)** — a numbered, unique, contiguous set, checked as one. Two sessions once appended
  concurrently and produced four duplicate ids. If two sessions may touch phase 2, expect this and check.
- **Traceability, bidirectional** — every `[P1]`/`[P2]` criterion maps to a covering test and every test maps
  to a criterion or an explicit exemption, with a checksum on the criterion count. Adding criteria without
  updating the map fails the suite, which is the intent.

## NEVER do unattended — human checkpoint required

Unchanged from phase 1, and still binding:

- **Never modify, move, or delete any dataset, answer-key, or fixture file.**
- **Never delete or overwrite a prior scorecard.** They are the durable record; `_write_new_file` uses
  exclusive creation so overwriting is impossible rather than merely unintended (D49).
- **Never commit or push** without the author's explicit approval of the commit message.
- **Never route around a denied answer-key read.** A refusal is the mechanism working.
- **Never place any part of the held-out split inside the repository tree.**

## Phase-2 acceptance gate

Every `[P2]` criterion in the spec, each passing **by execution**:

- [ ] Verify mode on an untouched scorecard reports no difference and exits zero.
- [ ] Verify mode on a scorecard whose stored numbers have been altered detects the difference and exits
  non-zero.
- [ ] Verify mode on a scorecard carrying an unrecognised schema version reports the version mismatch as its
  own outcome, and does **not** present the resulting differences as a scoring discrepancy (D66).
- [ ] Deleting the JSONL ledger and regenerating it from the scorecard directory reproduces identical
  contents.
- [ ] The CI workflow runs the pyright gate and the full test suite on push and fails on any error.
- [ ] Running the same dataset and findings artifact on Windows and on Linux yields identical scorecard
  content outside `run_metadata`.

Plus, carried forward: the full phase-1 gate must still pass, and regeneration must still reproduce every
dataset byte-for-byte.

## Record-keeping obligations

- Append any genuine fork to `DECISIONS.md` in the established format — fork, options considered, decision,
  why — continuing from **D72**.
- Bump the spec version and add a changelog line for any spec change.
- Update the **sweep marker** in the spec metadata when a sweep completes. The trigger is change-based:
  roughly 8–10 decisions since the last sweep, before publishing, or at phase completion.
- **A sweep at phase completion is expected.** Five have run so far; each found real defects in the one
  before it, including in work that was already green. Budget for it.

## Quality bar — the regeneration test

Could another agent rebuild this phase from the spec alone and produce behaviourally identical output? If
not, you have found what is missing — say so rather than papering over it.
