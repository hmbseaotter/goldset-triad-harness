# goldset-triad-harness — Decision Record

A running "decision tree": every fork we hit, the options considered, the choice made, and **why**.
Kept so the reasoning behind the design is always reviewable — not just the outcome.

- **Project:** `goldset-triad-harness`
- **Identity:** *A held-out golden-dataset harness that scores an AP document-matching agent's 3-way
  (PO / invoice / goods-receipt) findings against hand-audited ground truth.*
- **Status:** decisions accrue during the `/specify` interview; finalized alongside the spec.
- **Legend:** ✅ decided · 🔶 open / revisit · ⏭️ deferred to a later phase

<!-- rules-required-from: D67 -->

Every decision from **D67** onward ends in a **Rule** naming what enforces it — a test, a scan, or the
explicit words *judgment, not checkable*. `lint_spec.py` fails the build otherwise. The floor exists because
retroactive enforcement would be theatre: of the 67 entries written before it, **5** carried an extractable
rule, so demanding one from D0 would mean inventing 62 rules from paragraphs and calling that rigour. Earlier
entries get a rule when a sweep next touches them.

The reason for the requirement is D67's own history: the rule *"anything a tool says about itself is a claim,
and every claim gets a check"* was written in D59 **and violated in the same commit**, by its own author. The
next session found both violations as fresh defects (D64). A rule recorded as prose is enforced by whoever
remembers it.

---

## D0 — Name & identity

**Fork:** What to call the harness, and how to describe it in one line.

**Options considered**
- `three-way-match-eval` — plainest, but generic.
- `goldset-triad-eval-harness` — explicit, but `eval` + `harness` are redundant (a harness implies eval).
- `goldset-triad-harness` — drops the redundant token; keeps `goldset` (methodology hook) + `triad` (domain).
- Coupling the name/tagline to the consumer agent (`fin-ops-compliance-specialist`).

**Decision ✅** — Name: **`goldset-triad-harness`**. Tagline: *A held-out golden-dataset harness that
scores an AP document-matching agent's 3-way (PO / invoice / goods-receipt) findings against
hand-audited ground truth.*

**Why** — `goldset` signals the golden-dataset methodology that resonates with an "Agentic Evaluation"
audience; `triad` names the 3-way domain distinctively; dropping `eval` removes redundancy. The identity
is deliberately **agent-agnostic** ("an AP document-matching agent," not *my* agent) so the harness reads
as a standalone tool; `fin-ops-compliance-specialist` is described as its *first consumer*, not baked into
its name. Avoids the requested "reconciliation agent" / "iTradeNetwork" bleed.

---

## D1 — Harness ↔ agent-under-test boundary (ports & adapters)

**Fork:** Should the harness *run* the agent it evaluates, or only *score its output*?

**Options considered**
- **(A) Harness orchestrates** — harness invokes the agent, then scores. Turnkey, but couples the harness
  to the agent's runtime/language and makes key-isolation harder (the scoring process and the agent share
  a process boundary).
- **(B) Harness scores an emitted findings artifact** — the agent runs as a *separate step* and writes
  structured JSON (the `Status / Category / TargetLine / Confidence` payload); the harness ingests that
  JSON and scores it against the key. An optional "runner" adapter can invoke the agent later.

**Decision ✅** — **(B).** The **findings payload schema is the port**; any agent that emits it can be
scored. The optional runner/adapter is **deferred** (⏭️, not P1).

**Why**
- **Isolation falls out for free** — the scoring process can live *with* the answer key while the agent
  process runs elsewhere and never touches it; the canary/"contamination impossible" story holds by
  construction.
- **External / BYO agents become a later add-on, not a refactor** — anyone whose agent emits the schema
  is scorable; supporting them is docs + packaging.
- **Language/runtime-agnostic** — the agent can be anything as long as it emits the payload.
- Mirrors the hexagonal / ports-and-adapters approach used in the robot test-infra guide: volatile things
  (the agent) sit behind a stable port (the schema).

**Consequence** — the **versioned payload schema is the real interface to nail down** in P1.

---

## D2 — Dataset selection & versioning

**Fork:** Is the dataset fixed, or selectable? When does it change?

**Options considered**
- Single hardcoded dataset baked into the harness.
- **Datasets as addressable data** (id / path), loaded at runtime, version-stamped per run.

**Decision ✅** — **Selectable addressable data.** Every run records *which dataset + which version* it
scored. Datasets are data directories, never hardcoded paths. **Public dev/example split + private
held-out split exist from P1.**

**Why**
- "Version-pinned" is about **comparability**: two runs are only comparable if they scored byte-identical
  inputs. A new curated dataset gets a new id/version; old scores stay attributed to the old snapshot.
- Selectability isn't a far-future feature — the **public/held-out split forces at least two datasets from
  day one**, so "select which dataset" is a P1 primitive (just an argument). Adding a third later costs
  nothing.

**Consequence** — outcome statement reworded "fixed" → "**selected** version-pinned golden dataset"; no
conceptual change.

---

## D3 — Sales-tax check: which flavor, which phase

**Fork:** Include a tax check? If so, arithmetic self-consistency or statutory/jurisdiction compliance?

**Context** — the prior work already ships a tax check (PRD rule **R9**: expected rate = PO `tax` ÷
taxable subtotal, applied to lines whose PO counterpart is `taxable:true`, threshold ≥ $0.05), with a
worked answer (Pacific `7729-PDG` "tax overcharge $449.93") and a ready data model (`taxable` per line,
per-PO `tax`, a `matching_policy.json` tax note). Tax miscalc was the *largest discrepancy by value* in
the sample.

**Options considered**
- **(a) Arithmetic / self-consistency** — invoice tax vs the rate the PO itself implies. Pure arithmetic,
  same class as price/quantity variance. Proven; known answer.
- **(b) Statutory / jurisdiction compliance** — is the rate correct for the ship-to jurisdiction? Needs a
  jurisdiction→rate table + ship-to mapping.

**Decision ✅** — **(a) in P1** as a scored `TAX_VARIANCE` category; **(b) deferred to P3** with the
other compliance checks (SOX, sanctions).

**Why** — flavor (a) is low-risk (proven logic, ready data, existing worked answer) and a *headline*
discrepancy, so it belongs in the walking slice; flavor (b) carries external reference data and is a
compliance-class check, so it sits with P3.

**Consequence / caveat for data-gen** — the PRD's "first-PO shortcut" (multi-PO invoice derives one tax
rate invoice-wide) is harmless on today's uniform data but wrong in principle. When P2/P3 add multi-PO
invoices with varying rates, **the answer key must compute tax per-PO/per-line correctly** or the key
itself is wrong.

---

## D4 — Confidence calibration & reasoning quality: exclusion basis

**Fork:** Are "reasoning quality" and "confidence calibration" both simply out of scope for the same
reason?

**Decision ✅** — split them:
- **Reasoning quality → hard out (all phases).** Judging it needs an LLM-judge: subjective,
  non-reproducible run-to-run, and itself in need of evaluation. That poisons the deterministic,
  byte-reproducible verdict that is the harness's whole value proposition.
- **Confidence calibration → deferred P4 deterministic add-on.** Calibration (e.g. a Brier score over
  emitted confidences vs ground-truth correctness) is *deterministically computable* — not subjective. It
  is out of v1 only to keep the verdict simple and the schema light, and to avoid forcing the agent to
  emit calibrated probabilities. May return as a P4 add-on.

**Why** — the two were wrongly bucketed together earlier; only reasoning-quality is excluded *for
subjectivity*. Calibration is a scope/simplicity deferral, not a determinism problem.

---

## D5 — Data-generation methodology (design-time AI, deterministic runtime)

**Fork:** Hand-author all fixtures, or let AI generate them? If AI, where is it allowed?

**Options considered**
- **(A) Fully hand/deterministic authoring** — maximum "built by hand" credibility; slow; risk of human
  blind spots in discrepancy coverage/distribution.
- **(B) AI-assisted, then frozen** — AI assists at *design/authoring time*; output is audited and
  committed as static data + seeded generator code.

**Decision ✅** — **(B).** The credibility property is: *given a seed, the generator produces
byte-identical data AND the matching key, every time, with no model/network call at generation runtime.*
AI is used **at design time** — including designing the discrepancy plan (which categories, how many,
where they land), where its systematic coverage beats human intuition — then a human audits it and it is
frozen into deterministic seeded generation + emitted key.

**The hard line (refined):** *design-time AI = welcome; runtime AI = forbidden.* Not "flavor vs.
discrepancies." Discrepancy planting and key emission are deterministic seeded code; generators live on
the secret side (per the existing answer-key-guard handover).

**Why** — captures AI's coverage/distribution strength (no blind spots) while keeping "hand-audited ground
truth" literally true and every run byte-reproducible.

**Consequence** — the discrepancy-design artifact is audited then committed; re-running the design model
is **not** part of the pipeline (re-running it would break reproducibility).

---

## D6 — Timestamp standard (no "whose midnight") ✅

**Fork:** How are dates/times represented so ordering is never ambiguous across time zones?

**Context** — date-violation checks (invoice-predates-PO, GR-before-PO-approval) are ordering checks, and
the DCs span zones (Portland / Tacoma / Boise). Bare dates make cross-warehouse ordering ambiguous.

**Decision ✅**
- Every timestamp is **UTC ISO-8601 with the `Z` suffix, second precision** (e.g. `2026-07-19T23:15:07Z`).
  All values normalized to UTC — no local offsets stored, no bare dates for anything compared or ordered.
- **All ordering/comparison on the absolute UTC instant** (trivial, since everything is already `Z`).
- **Civil dates only as a documented exception**, where a rule is genuinely calendar-based (e.g. "tax
  point = local date"). Such a case MUST also carry the applicable time zone so the local date can be
  derived from the stored UTC instant.
- **Data timestamps are fixed/seeded**, never wall-clock (reproducibility); only the scorecard's *run
  stamp* uses the real clock (metadata, not scored) — also emitted as `…Z`.

**Why** — eliminates "whose midnight," makes date-violation checks total and reproducible; `Z`-normalized
storage removes offset arithmetic entirely.

---

## D7 — Stack, type discipline, dependency zones

**Fork:** Language/runtime floor, static checker, and where third-party deps are allowed.

**Decision ✅**
- **Python 3.11+** floor (fresh portfolio repo; modern typing — `X | Y`, `Self`).
- **pyright** as the static-checker gate (stricter by default, fast, CI-friendly); "type-check passes" is
  an acceptance criterion.
- **Two dependency zones:** the **scoring engine is pure standard library** (`json`, `decimal.Decimal` —
  never `float`, `dataclasses`, `typing`), zero third-party — it's the auditable credibility core. The
  **data-generation side (P2)** may use a PDF-authoring lib; *which* lib is a P2 decision (PyMuPDF vs
  reportlab), not needed for P1.
- **Immutability:** frozen dataclasses, `Decimal`, `typing.Final` for constants.
- **Cross-platform Windows + Linux**, first-class; every command documented for both shells.
- **Clean-room terminology** — no "reconciliation agent" / "iTradeNetwork"; reuse solid *patterns* from the
  practice app (Decimal discipline, deterministic finding IDs, append-never-insert) but rewrite the
  judgment layer.
- **No new packages without flagging first.**

**Why** — modern-but-stable Python; pyright suits a public repo; a stdlib-only scoring core is trivially
auditable, which is the whole point of a credibility artifact.

**Deferred** — PDF-authoring lib → P2; portable (non-Claude-Code) answer-key isolation → P4 (audience). For
P1, isolation uses the proven Claude Code `.claude/settings.json` deny-guards + canary.

> **Superseded in part.** The PDF-library deferral above was **overturned by D33**: D31 made invoices supplier
> PDFs, so authoring is needed in P1. ReportLab enters at `[P1]` for clean text-layer invoices; only *format
> difficulty* defers. The stdlib-only rule still holds — it is scoped to the scoring engine, while this
> dependency sits on the generation side. The canary's role was also narrowed by **D30**: it is an attestation
> decoy, not an automated probe.

---

## D8 — Scoring semantics (match key, matching model, over-flag measure)

**Fork:** How strictly must an agent finding match an expected finding, and how is over-flagging measured?

**Decision ✅**
- **Match-key default = strict: `Status + Category + TargetLine`.** A "catch" must land on the *right line*,
  not just the right category — the honest, harder bar for a real reviewer. **Lenient mode** (drop
  `TargetLine` → `Status + Category`) → **P2 optional flag** for agents without line-level precision.
- **1:1 matching** — each agent finding matches at most one expected finding and vice-versa; a
  **deterministic tie-break** makes the score independent of input ordering (protects reproducibility, U4).
- **Precision/recall computed per discrepancy category.**
- **Over-flagging measure (zero-defect control)** — since there are no true positives there, precision is
  undefined (0/0); the reported measure is **(a) raw false-positive count and (b) FP-per-invoice rate**.

**Why** — strict + per-line is the credible bar; 1:1 + deterministic tie-break guarantees order-independent,
reproducible scores; FP count/rate is the only well-defined over-flag metric on a clean case.

---

## D9 — Run duration: recording, history, and breach behavior

**Fork:** Should the scorecard record how long evaluation took, and how is that history kept?

**Context** — a bare 10-second threshold is a mystery when it trips: *why*, and *what is normal?* A
threshold without observed history is arbitrary.

**Decision ✅**
- **Record duration**, broken down: `load_ms`, `score_ms`, `total_ms`, plus **invoice count and finding
  count** (a duration is meaningless without knowing the workload it covered).
- **It lives in the `run_metadata` envelope**, which the byte-identical comparison explicitly **excludes**.
  *This is load-bearing:* duration is non-deterministic, so putting it in the scored body would make **U4
  (byte-identical reproducibility) impossible to satisfy** — a future edit that moves it would look like a
  mysterious flake.
- **Durable record = the scorecards** (never overwritten, committed). They are the documentation and cannot
  be lost.
- **Convenience view = an append-only JSONL ledger**, local-only / gitignored, **and REGENERABLE from the
  scorecards**. Because it is derived, deleting it loses nothing — rebuild it and get the same file. (If it
  were *not* regenerable, a deletable local file would be exactly the tamper/loss risk we're avoiding.)
- **Perf breach = WARN, exit 0.** A slow run does not make the score wrong. Correctness breaches (schema,
  dataset, key) keep the non-zero exit; a performance breach emits a prominent warning and exits 0.

**Why** — *"the harness evaluates accounting problems, not agent speed"* (user). Recording durations turns
the 10s figure from an arbitrary number into a calibrated one, without letting a busy laptop invalidate a
valid evaluation.

**Honest caveats to document** — (1) durations are comparable only **on the same machine**; a ledger
spanning a laptop and a CI runner is apples-to-oranges, so it is a **per-machine trend tool** and 10s is a
smoke alarm, not a benchmark. (2) Committed scorecards are **tamper-evident** (edits show in git history),
not tamper-proof — and see **D10**, which supersedes git as the real integrity mechanism.

---

## D10 — Integrity: verify-by-recompute (input fingerprints)

**Fork:** How does a reader know a scorecard reports what it claims to report?

**Context — why git alone is not enough.** Git history is **conditionally** tamper-evident:
- **Locally, a commit can be erased with no trace** — `git rebase -i` / `reset --hard` / `filter-repo`,
  then `git reflog expire --expire=now --all && git gc --prune=now` closes the recovery window entirely.
- **On a remote it is much harder to do quietly** — force-push is a logged event (and blockable by branch
  protection), orphaned commits typically stay fetchable by SHA, and other clones see a non-fast-forward.
- So "tamper-evident" holds **only** when pushed to a remote with force-push disabled on main, and
  weakens toward zero on a purely local repo.

**Decision ✅** — Rely on **determinism, not git forensics**. Since U4 guarantees byte-identical output for
identical inputs, **a scorecard never has to be trusted — it can be recomputed.**
- Each scorecard **embeds a fingerprint of its inputs**: dataset id + version, **SHA-256 of the findings
  artifact**, and **SHA-256 of the answer key**.
- A **`--verify` mode** recomputes from those fingerprints and diffs against the stored scorecard.

**Why** — an edited score is exposed by simply re-running. Without embedded fingerprints, a doctored
scorecard could claim to have scored inputs it never saw; with them, verification is unambiguous. ~10 lines
of stdlib `hashlib`, and it is a strictly stronger property than "we can dig through git history."

**Consequence — a crisp placement rule.** Fingerprints are a *pure function of the inputs*, therefore
deterministic, therefore they belong in the **scored body** (where U4's byte-identical comparison protects
them). Duration is non-deterministic and belongs in `run_metadata`. General rule: **`run_metadata` contains
exactly the non-deterministic fields, and nothing else.**

**Note** — publishing a SHA-256 of the held-out answer key leaks nothing (one-way, and the key is far too
large to brute-force), while proving *which* key version produced the score.

---

## D11 — Resolved at the assumptions gate

Three inferred assumptions were surfaced for review and confirmed as decisions.

### D11.1 — Repo visibility: **private now, public when ready** ✅
- **Options:** public from day one · private until P1/P2 are solid.
- **Why:** key isolation and the public/held-out split are still built in P1 (per D2), but iterating in
  private keeps the cost of a mistake low. **A key leaked into early git history of a public repo is
  permanent and would retroactively invalidate the "held-out" claim** — that asymmetry decides it.

### D11.2 — P1 dataset origin: **new small dataset; existing fixtures are schema reference only** ✅
- **Options:** port the existing 50-PO / 5-invoice set · author a fresh small set.
- **Why:** clean-room (no "Cascade Fresh Foods" content dragged along), fast, and it proves the scoring
  loop end-to-end before scaling in P2. Porting would front-load answer-key authoring for data that gets
  regenerated in P2 anyway. The existing fixtures still inform the **schema** (PO/line/receipt shape,
  `taxable`, tolerances) — that structure is solid and worth reusing.

### D11.3 — Discrepancy categories: **closed enumeration owned by the harness** ✅
- **Options:** free-form category strings · closed enum published by the harness.
- **Why:** per-category precision/recall is only well-defined over a fixed vocabulary. With free-form
  strings, near-miss names (`TAX_ERROR` vs `TAX_VARIANCE`) would silently score as misses. An agent
  emitting an unknown category is therefore a **schema violation** and halts the run (I2).

---

## D12 — Phase composition

**Skeleton floor (P1, required — all retained, none dropped):**
1. Findings payload schema v1 (closed category enum, composite `TargetLine`) — the port; nothing scores
   without the contract.
2. Scoring engine — 1:1 strict matching, deterministic tie-break, per-category precision/recall, FP
   count + rate.
3. Scorecard emission — JSON + human summary, embedded input fingerprints, `run_metadata` envelope.
4. Small 3-way dataset **including goods-receipt discrepancies** + zero-defect control — "triad" is the
   product; GR checks cannot be bolted on later without re-authoring the key.
5. Initial category set — price, quantity (incl. under/over-shipment vs GR), `TAX_VARIANCE`.
6. Dataset selection by id/path + dev / held-out split.
7. Answer-key isolation (placement + deny-guards) + canary probe — retrofitting isolation is how keys leak.
8. Type discipline — pyright gate, `Decimal`, frozen dataclasses.
9. Test suite covering the P1 acceptance criteria — an untested eval harness is self-refuting.

**Optional items chosen for the first push ✅**
- `--verify` recompute mode (makes D10's fingerprints actionable).
- JSONL run ledger + regeneration-from-scorecards (D9).
- README + methodology write-up (the portfolio-facing artifact a reviewer actually reads).
- CI workflow (pyright + tests on push) — makes the type gate and acceptance tests continuously enforced.
- Cross-platform verification on Windows **and** Linux (N3).

**Deferred**
- **Perf budget (<10s, warn-not-fail) → P2** — only meaningful once the dataset is large enough to be slow,
  which is precisely what P2 delivers.
- Lenient match mode → P2 (D8). Dataset expansion → P2. Compliance categories (SOX, sanctions, statutory
  tax, currency) → P3. Audience expansion, optional runner/adapter, confidence calibration → P4.

**Phase-tag renumbering.** The spec linter at the version that produced this spec (`821fac1`) accepted only
`[P<integer>]`, so `[P1a]`/`[P1b]` were rejected as malformed. Final mapping: **P1a → `[P1]`** (credibility
core), **P1b → `[P2]`** (tooling & scaffolding), dataset expansion → `[P3]`, compliance categories →
`[P4]`, audience expansion → `[P5]`. Same plan, legal tags.

> **Update (2026-07-25):** this limitation was itself the first gap fixed upstream — sub-phase tags are
> legal as of toolkit `b09a99a`, so a future split can use `[P3a]`/`[P3b]` directly. The renumbering above
> stands, because re-tagging every item plus the build prompt would be churn for a mnemonic.

**Build-readiness (on the record).** Assessed as a heavy phase — subtle-correctness surface in the 1:1
matching/tie-break, byte-identical reproducibility, and answer-key authoring. Author confirmed **Opus 5 +
Extra (xhigh) effort, both already set**. P1 was **split** into P1a/P1b rather than built as one 14-item
push, to keep each change independently reviewable and avoid mid-build context exhaustion.

---

## D13 — `MATCH`-status entries are not eligible to be false positives ✅

**Fork:** The payload carries `Status: MATCH | DISCREPANCY`. When an agent emits a `MATCH` entry for a line
where the key expects a discrepancy, what happens?

**Options considered**
- **(A) Treat a `MATCH` entry as a flag** — i.e. count it among the agent's assertions and let it become a
  false positive.
- **(B) Treat `MATCH` as an assertion of correctness, ineligible to be a flag** — it cannot be a false
  positive; the expected discrepancy it fails to report is simply counted as a false negative (miss).

**Decision ✅ (provisional — flagged for the author)** — **(B).**

**Why** — a false positive means *"the agent raised an alarm that was not real."* A `MATCH` raises no alarm;
it asserts the opposite. Counting it as an over-flag would double-punish a single error (once as a miss,
once as a false flag) and would corrupt the over-flagging metric that the zero-defect control exists to
measure. The miss is already captured as a false negative, so the error is counted exactly once.

**Status** — surfaced during spec drafting rather than in the interview, then **explicitly confirmed by the
author (2026-07-25)**, since it defines what "over-flagging" means.

---

## D14 — What exactly lives outside the repository tree ✅

**Fork:** The spec stated that *answer keys* live outside the tree (A8) and named a "private held-out
split" (D2), but never **enumerated the full set**. Which artifacts are out, exactly?

**Options considered**
- **(A) Key + generators only** — simplest. But the discrepancy-design artifact describes *where errors
  were planted*, so leaving it in-repo substantially weakens the held-out claim.
- **(B) Key + generators + design out; held-out INPUTS published** — the benchmark / Kaggle pattern. Lets
  anyone run the eval, but published inputs are memorizable by a future model even with no labels
  attached, and it makes "private held-out split" a misnomer for "private key".
- **(C) Fully private held-out split** — key, generators, design artifact **and** inputs all outside.

**Decision ✅** — **(C).**

**Why** — published inputs are a contamination vector *on their own*: a model trained on the repo can
memorize the documents without ever seeing a label, and the labels are **derivable from the inputs** by
simply doing the task correctly. Keeping the whole split out preserves "contamination structurally
impossible" as a literal claim, rather than one resting on labels being the only secret. The **dev split**
ships in full — inputs *and* key — and is what demonstrates the methodology publicly and what CI runs.

### Consequence — two axes that were being conflated

| | in-repo | out-of-repo |
|---|---|---|
| **agent-readable** | dev split (inputs + key) | **held-out inputs** |
| **agent-denied** | — | held-out key, generators, design artifact |

**The held-out inputs are out-of-repo but MUST remain agent-readable** — the agent cannot produce findings
without reading them. So *"outside the repo"* and *"deny-guarded"* are **not the same set**, and the
deny-guard must **not** cover the held-out inputs or the agent cannot run at all. This is the trap: a guard
scoped to "the held-out directory" instead of "the held-out key/generators/design" silently breaks
evaluation rather than protecting it.

### Resulting three tiers

1. **Repo** (private now, public when ready) — harness code, tests, and the dev split **in full**.
2. **Out-of-repo, agent-readable** — held-out dataset inputs.
3. **Out-of-repo, agent-denied** (deny-guards + canary) — held-out answer key, generators, and the
   discrepancy-design artifact.

### Further consequences

- **CI (`[P2]`) can only exercise the dev split**; the held-out split is unreachable from CI by
  construction. Every acceptance criterion requiring a dataset is therefore a *dev-split* criterion.
- **Dataset selection by path (D2) is what makes this work** — an out-of-tree held-out split needs no code
  change, only a path. That decision is now load-bearing for isolation, not just comparability.
- **The dev split's answer key is public by design** and is *not* deny-guarded. Guards apply to tier 3 only.
- Supersedes the narrower wording of **A8**, which named only the answer key.

---

## D15 — Quantity categories: three, anchored on the payable quantity ✅

**Fork:** Which lines does the key mark as quantity discrepancies, and on which axis?

**Context — the enum names presuppose the wrong axis.** `QTY_UNDER_SHIPMENT` / `QTY_OVER_SHIPMENT` describe
the *shipment* (received vs ordered). But a supplier who ships 80 of 100 and bills 80 has a shipment
anomaly and **no billing problem**; marking that line would train the harness to reward flagging non-issues.

**Options considered**
- **(A) Shipment axis only** (received vs ordered) — matches the names literally and is symmetric, but flags
  correctly-billed short shipments and *misses* the invoice-exceeds-receipt overbill that 3-way matching
  exists to catch (the Pacific case the old 2-way app passed silently).
- **(B) Two categories, documented mapping** — the payable rule below, with the `ordered == received` case
  folded into `QTY_OVER_SHIPMENT` and a caveat. Keeps the enum as originally specified, at the cost of a
  category whose name misdescribes some lines it marks.
- **(C) Three categories** — add `QTY_INVOICE_INFLATED`.

**Decision ✅** — **(C).** One rule, with the category naming *which constraint bound the payable quantity*:

```
payable_qty = min(qty_ordered, qty_received)
overbilled  = qty_invoiced > payable_qty
```

| Condition | Category |
|---|---|
| `qty_received < qty_ordered` | `QTY_UNDER_SHIPMENT` — the receipt bound it |
| `qty_ordered < qty_received` | `QTY_OVER_SHIPMENT` — the order bound it |
| `qty_ordered == qty_received` | `QTY_INVOICE_INFLATED` — no shipment anomaly; the invoice is simply wrong |

**Why** — the payable quantity is what an AP agent is actually judged on, and it is what the 2-way
predecessor structurally could not see. Three situations exist, so two categories necessarily mislabel one
of them; per-category precision/recall is only meaningful when a category's name matches the lines it marks.

**Consequences** — the P1 enum grows to five categories (three quantity, plus `PRICE_VARIANCE` and
`TAX_VARIANCE`). Phantom billing (`qty_received == 0`) falls under `QTY_UNDER_SHIPMENT` for now; it gets its
own category if the taxonomy expands in `[P4]`.

---

## D16 — Price-variance threshold: how 2% and $25 combine ✅

**Fork:** The reference policy carries both a 2% and a $25 threshold without saying how they combine.

**Options considered**
- **(A) Exceed BOTH — `max(2% × extended, $25)`.** The standard AP "whichever is greater" tolerance;
  suppresses small-dollar and small-percentage noise. **Rejected:** it tolerates a **$1,999 variance on a
  $100,000 line**. For a harness built to catch money leaving, that blind spot is disqualifying — a false
  negative on $2,000 is far worse than a false positive on $3.
- **(B) Exceed EITHER — `min(2% × extended, $25)`.** The tighter bound always governs.
- **(C) Percentage only** — immaterial findings pile up on cheap lines.
- **(D) Flat $25 only** — pure materiality; gives up detection of proportionally large errors on cheap
  lines that signal a broken contract price.

**Decision ✅** — **(B), with a rounding floor:**

```
threshold = max($0.05, min(0.02 × extended_amount, $25.00))
flag iff |variance| >= threshold
```

**Why — the two thresholds serve different purposes, which is what justifies OR between them:**
- **$25 is materiality.** At a median US accountant's ~$31.45/hr, $25 ≈ **47 minutes** of chase time: a
  discrepancy worth more than the time to pin it down is worth the effort. This is the *only* threshold that
  governs large lines.
- **2% is a systematic-error signal.** A proportionally large error on a cheap line indicates wrong contract
  pricing that will **recur** across many lines and invoices — worth catching even at $3, where materiality
  alone would not justify it.
- **$0.05 floor** protects the zero-defect control from rounding noise (`min` alone would set a $0.20
  threshold on a $10 line). Precedented: the prior work used `>= $0.05` for R9 and R11.

**The "equilibrium value" framing.** The thresholds cross at **$1,250** (2% of $1,250 = $25). Under `min`,
the percentage governs *below* that point and the $25 cap governs *above* — so **the 2% never applies to
large lines**, and the "2% of $100K = $2,000" objection never arises. `min` delivers value-tiering for free:
the $25 cap *is* the high-value tier.

**`>=`, not `>`** — a variance sitting exactly on the threshold flags rather than passes, so a boundary case
is never a silent miss. Matches the prior work's `>= $0.05` on R9/R11.

**Measured on the extended amount at the *payable* quantity:**
`price_variance = (invoice_unit_price − po_unit_price) × payable_qty`. Isolating the price leg stops a
quantity error from masquerading as a price error and being counted twice across two categories.

**Published, not hidden** — the rule lives in the dataset's matching policy. The agent cannot compete
against a threshold it cannot read.

**Quantity overbills use the same materiality threshold ✅ (confirmed by the author, 2026-07-25).** A
quantity overbill is valued as `(qty_invoiced − payable_qty) × po_unit_price` and passed through the
threshold above. One materiality rule across all monetary categories is simpler than two and keeps the
zero-defect control coherent. The rejected alternative was exact quantity matching with no tolerance, which
would mark 1-unit overbills on trivially cheap items — findings that cost more to chase than they are worth,
by the same accountant-time reasoning that sets the $25 floor.

**Not claimed as an industry norm.** The methodology write-up publishes *this harness's* thresholds and the
reasoning above; it does not assert what standard corporate practice is. Percentage tolerances in the low
single digits are unremarkable, but that was not verified to a citable standard.

---

## D17 — Out-of-tree layout for the held-out split ✅

**Fork:** D14 made the layout load-bearing. What concrete structure satisfies "inputs readable, key /
generators / design denied"?

**Options considered**
- **(A) One parent with `inputs/` and `secret/` children** — tidier, keeps the split together. **Rejected:**
  it invites the exact trap D14 warns about; a careless `holdout\**` deny rule covers the inputs too and
  evaluation silently returns nothing.
- **(B) Two sibling directories** — physical separation makes the dangerous rule awkward to write.

**Decision ✅** — **(B), siblings:**

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

**Why** — choose the layout that makes the wrong guard structurally awkward, not merely documented against.

**Consequences**
- **A "dataset" is a *pair* of locations** (inputs + key), and for the held-out split they diverge. Resolved
  by a **manifest** naming `inputs_dir` and `key_path`. The dev manifest ships in-repo under `datasets/dev/`;
  the held-out manifest lives on the secret side — readable by the scoring process, which legitimately holds
  key access, and unreachable by the agent, which only ever needs the inputs directory.
- The **canary is covered by the directory rule only**, never a filename rule, so it exercises the weakest
  layer — same reasoning as the earlier guard work.

---

## D18 — `run_metadata` holds only non-deterministic fields; the counts move ✅

**Fork:** D10 requires `run_metadata` to contain *exactly* the non-deterministic fields, but D9 placed
`invoice_count` and `finding_count` inside it — and both are deterministic. A genuine contradiction.

**Options considered**
- **(A) Weaken the rule** to "run-scoped context, of which only some is excluded from comparison" — messy,
  and it discards a crisp, load-bearing invariant.
- **(B) Exclude specific fields** rather than the whole envelope — complicates the byte comparison.
- **(C) Move the counts into the scored body.**

**Decision ✅** — **(C).** `run_metadata` keeps the run timestamp and `load_ms` / `score_ms` / `total_ms`,
and nothing else.

**Why — this closes a latent hole, not just a wording inconsistency.** Everything inside `run_metadata` is
**excluded from the byte-identical comparison**. As written, a regression that silently miscounted invoices
would have been **invisible to U4**. Moving the counts into the body puts them under that protection.

**Consequence** — D9's intent ("a duration is meaningless without knowing the workload it covered") is
unaffected: the counts sit in the same file, and the `[P2]` ledger reads them from the body when it
regenerates from scorecards.

---

## D19 — Which `extended_amount` is the 2% basis ✅

**Fork:** D16's threshold divides by "the line's extended amount". Which one? The choice only bites *below*
the $1,250 crossover — above it everything collapses to the $25 cap — but below it, it flips findings.

**Options considered**
- **(A) Invoice extended** (`qty_invoiced × invoice_unit_price`) — **disqualified.** Self-referentially
  gameable: an inflated invoice enlarges its own denominator, so the worse the overbill, the *smaller* the
  variance ratio appears. PO 10 × $10 billed as 10 × $20 reads as 100% against the PO and only 50% against
  the invoice. A leg that exists to detect proportionally large errors cannot divide by the disputed value.
- **(B) PO extended** (`qty_ordered × po_unit_price`) — the authorized line value straight off the PO.
  Simplest to explain and audit, stable regardless of what arrived. But a heavily short-shipped line keeps a
  large denominator, leaving the threshold loose on what is actually a small invoice.
- **(C) Payable extended** (`payable_qty × po_unit_price`).

**Decision ✅** — **(C), payable extended.**

**Why**
- Measures proportion against **the dollars actually in play**. On a PO of 100 @ $10 where 10 arrived, the
  line is worth ~$100, not $1,000, and a $3 error there is proportionally significant.
- Uses **authorized pricing**, so it cannot be gamed like (A).
- **Degrades correctly for phantom billing**: `payable_qty = 0` → basis $0 → `min(0, 25) = 0` →
  `max($0.05, 0) = $0.05`, so anything billed for goods never received always flags. That falls out of the
  formula rather than needing a special case.
- Consistent with D16 already measuring price variance *at the payable quantity*.

---

## D20 — Findings carry an explicit `scope`; the match key extends ✅

**Fork:** Tax is charged once per invoice, but `TargetLine` is document id + line id. How is an
invoice-level finding anchored?

**Context — this is a schema gap, not a tax question.** Tax is not the only document-level finding coming:
**duplicate invoice, invalid PO reference, currency mismatch, segregation-of-duties, and
vendor-master/sanctions** are all document-scoped, and all sit in the `[P3]`/`[P4]` taxonomy. Since the
payload schema is **the port** (D1), discovering this at P4 means breaking the contract after agents depend
on it.

**Options considered**
- **(A) Distribute the tax error across taxable lines** — multiplies one error into N findings, inflates both
  the key and the agent's required output, and corrupts per-category precision/recall. Rejected.
- **(B) Anchor to a physical totals/tax line** — a layout artifact; not every invoice has one.
- **(C) Reserved sentinel line id only** (e.g. `__DOCUMENT__`) — smaller schema, but scope becomes implicit
  in a magic string and validation cannot distinguish a document-level finding from a malformed line id.
- **(D) Explicit `scope` field.**

**Decision ✅** — **(D).** A finding carries `scope: LINE | DOCUMENT`. `target_line` is **required** when
scope is `LINE` and a **reserved sentinel — never empty, never absent** — when scope is `DOCUMENT`.

**The match key becomes `Status + Category + scope + target`** (target being the document id, plus the line
id only for `LINE` scope). This **extends D8**, which named `Status + Category + TargetLine`.

**Why** — fixes tax anchoring *and* pre-empts every document-scoped category in P3/P4 without a later
breaking change to the port. Making scope explicit also lets schema validation reject a malformed finding
instead of silently treating it as document-level.

**Consequence** — `[P3]` lenient matching drops the **line** component only; scope and document id stay in
the key, so a document-level finding never becomes indistinguishable from a line-level one.

---

## D21 — `TAX_VARIANCE` uses the unified threshold ✅

**Fork:** Does tax use D16's unified materiality threshold, or D3's flat `>= $0.05` floor?

**Options considered**
- **(A) Flat `>= $0.05`** (the prior work's R9 precedent) — tax is arithmetic, so any deviation beyond
  rounding is an error, and a wrong *rate* is systematic: it recurs on every invoice. Catches small rate
  errors the unified rule passes, at the cost of a second materiality rule.
- **(B) Unified threshold, basis = the invoice's taxable subtotal.**

**Decision ✅** — **(B).**

**Why — D3 already implied it.** D3 scoped P1's tax check as *arithmetic self-consistency* and deferred
statutory/jurisdiction compliance to `[P4]`. A **materiality** check therefore uses the materiality rule;
**compliance** semantics — where a small deviation matters *because* it is systematic — belong to the P4
statutory check. One rule everywhere in P1.

**Accepted cost, stated plainly** — on a $10,000 taxable subtotal a rate error ≥0.25% flags, which is fine.
But below the $1,250 crossover the 2% leg governs, so only rate errors ≥2 percentage points flag: a **$10 tax
error on a $1,000 subtotal passes**. D3's flat floor would have caught it. Revisit if the P4 statutory check
does not adequately cover small-invoice rate errors.

**Scope** — `TAX_VARIANCE` is a `DOCUMENT`-scoped finding (D20).

---

## D22 — Line correspondence: the key declares it, the inputs do not ✅

**Fork:** How is an invoice line matched to its PO line and goods-receipt line? The harness never computes
this, but the key author and any independent auditor must — and an ambiguous correspondence makes the key
ambiguous.

**Options considered**
- **(A) By SKU / part number** — the natural key, but the taxonomy *deliberately* breaks it: "6ft USB-C
  Cable" / "Charging Cord Type C" / "Part #X792" for one item.
- **(B) By line number / position** — fragile by construction, and the taxonomy includes swapped lines. Same
  positional-fragility trap that breaks indexed records.
- **(C) Declared explicitly as ground truth in the dataset.**
- **(D) Declared in the key only, not in the agent-readable inputs.**

**Decision ✅** — **(D).**

**The resolution follows from what the target actually names.** `TargetLine` anchors on the **invoice** line —
document id is the invoice being scored. The agent never has to *express* PO/GR correspondence in a finding;
resolving it is internal reasoning that decides whether and what to flag, but it never enters the match key.
That keeps the port stable.

Three things must therefore hold:
1. **Invoice line ids are explicit and stable in the dataset**, never positional.
2. **The canonical correspondence (invoice line → PO line → receipt line) is declared in the answer key**, on
   the secret side — which is what makes the key unambiguous and independently reproducible by an auditor.
3. It is **absent from the agent-readable inputs**, because resolving correspondence across differing
   descriptions, part numbers and UOM **is the capability under test**. Publishing the mapping would delete a
   whole class of difficulty the taxonomy exists to create.

**Why it matters for scoring** — the key recording the *intended* correspondence is what makes a wrong-line
answer **scoreable as wrong rather than arguable**.

**Extends A5**, which said `TargetLine` is "document id + line id, defined canonically by the dataset"
without naming *which* document or requiring stable ids.

---

## D23 — Rounding: compare exact, round only for display ✅

**Fork:** No rounding policy was specified, yet the `>=` boundary depends on one. On a $333.33 basis the 2%
term is $6.6666 — whether that becomes $6.67, $6.66, or stays exact decides whether a $6.666 variance flags.

**Key realization that collapses the problem** — **dollar amounts are not part of the match key** (which is
`status + category + scope + target`, D20). So rounding can never change *which* finding matches *what*. It
decides only (a) whether a finding **exists** — the threshold comparison — and (b) how amounts are
**displayed**. One rule covers both.

**Options considered**
- **(A) Quantize the threshold to cents (HALF_UP), then compare** — every threshold sits on a cent boundary,
  so "one cent below" is well-defined exactly as originally written. But it makes a rounding *mode*
  load-bearing and shifts the boundary by up to half a cent.
- **(B) Exact comparison, display-only rounding.**

**Decision ✅** — **(B).** Compute and compare at full `Decimal` precision, **never rounding before a
comparison**. Round to 2dp **only at emission**, explicitly `ROUND_HALF_UP`, and never feed a rounded value
back into a comparison.

**Why**
- Rounding intermediates is **path-dependent** (round-then-multiply ≠ multiply-then-round), which is exactly
  what makes a key ambiguous and an independent auditor's recomputation diverge.
- Unit prices in produce and commodity pricing routinely carry 4 decimals, so almost nothing is naturally
  cent-aligned; a policy that assumes cent alignment would be fighting the data.
- **`ROUND_HALF_UP` must be stated explicitly**, because Python's `Decimal` defaults to `ROUND_HALF_EVEN`
  (banker's rounding). Leaving it implicit silently yields something other than what an accountant expects.

**Consequence — the boundary criterion had to be restated.** "One cent below the threshold" presumed cent
alignment. Replaced by two criteria: one on a deliberately cent-aligned basis ($500 → 2% = $10.00 exactly)
testing at-threshold and one-cent-below, and one on a **non**-aligned basis ($333.33 → $6.6666) where $6.67
flags and $6.66 does not — the latter is what actually proves exact comparison.

---

## D24 — Expected tax is computed on the INVOICED taxable subtotal ✅

**Fork:** D21 settled the *threshold basis* for tax. This is the *expected value* computation — and it decides
whether a price or quantity error **also** generates a tax finding.

**Options considered**
- **(A) Payable taxable subtotal** (what should have been billed) — truer to the real total overcharge, since
  an inflated price does inflate the tax actually charged. **Rejected:** it **cascades.** Any price or
  quantity error changes the correct tax base, so the invoice's tax necessarily differs and one root cause
  produces **two** findings. `TAX_VARIANCE` recall becomes polluted by price errors, and an agent that
  correctly identifies the single root cause is penalised for "missing" that finding's own consequence.
- **(B) PO-authorized taxable subtotal** — same cascade problem, and further from what the invoice asserts.
- **(C) Invoiced taxable subtotal.**

**Decision ✅** — **(C).** Expected tax = the PO-derived rate × **the invoice's own taxable subtotal**.

**Why** — it isolates the check to what D3 actually scoped: *arithmetic self-consistency of the tax charge*.
One root cause, one finding. It also matches the prior work's R9, which applied the derived rate to
**invoiced** lines.

**Accepted cost, stated plainly** — a seeded price error produces **no** tax finding, even though real-world
tax would also be wrong. Deliberate: the harness tests whether each root cause is detected once. Recovering
full dollar impact including consequent tax is what a **residual** check does, and residual is not among P1's
five categories.

---

## D25 — Precision and recall on a zero-expectation case ✅ (corrects the spec)

**Fork:** The spec suppressed precision on the zero-defect control as "mathematically undefined (0/0)". That
is only true when the agent raised **no flags at all**.

**The error.** Precision is `TP / (TP + FP)`. On the control `TP = 0` always, so:

| Agent behaviour | Precision | Report |
|---|---|---|
| No flags raised (`FP = 0`) | `0/0` — genuinely undefined | `null` |
| Flags raised (`FP = 3`) | `0/3 = 0.0` — **defined** | `0.0` |

Suppressing the second case **discards the signal**, since `0.0` there is the meaningfully bad result. The
original wording conflated "no expectations" with "no flags".

**Decision ✅**
- **Precision** on a zero-expectation case: `null` only when the agent raised no flags; otherwise the computed
  value, which is `0.0`.
- **Recall** on a zero-expectation case: **always** `null` — with no expectations at all, `TP/(TP+FN)` really
  is unconditionally `0/0`.
- Undefined is represented as **`null`** — never `0`, which reads as failure when the result was perfect, and
  never an omitted key, which makes the field unstable across runs and breaks byte-identical comparison (U4).
- The primary control measures remain the **false-positive count and rate** (D8), which are always defined.

---

## D26 — Duplicate contention: tie-break, and a distinct diagnostic ✅

**Fork:** Two findings contending for one expectation are by definition **identical on the match key**, so
they differ only in `Confidence` and reasoning — and confidence is carried but never scored. What breaks the
tie?

**The reframing that resolves it** — **the tie-break cannot change any metric.** Whichever duplicate is
chosen, the outcome is one TP and one FP; precision, recall and FP counts are identical. So the tie-break
exists **purely for output determinism** (U4), not for fairness or scoring.

**Options considered**
- **(A) Document order — first occurrence wins.** The obvious choice, and **disqualified**: the spec already
  requires that reversing the findings artifact produce an identical scorecard.
- **(B) Lowest content hash** — total and order-independent, but opaque to debug.
- **(C) Canonical serialization order.**

**Decision ✅** — **(C).** Order contending findings by a canonical serialization of the whole finding and
take the first. Total, order-independent, and **inspectable**, unlike a hash.

**Why using confidence in that ordering is not "scoring" it** — the ordering cannot move any metric. It
affects only which of two identical-keyed findings is *labelled* the TP in the report. Two byte-identical
duplicates are symmetric, so any total order resolves them identically.

**Addition — duplicates get their own diagnostic.** An agent emitting duplicate findings has a **defect**, and
folding that silently into the ordinary FP count hides it. Duplicates still count as false positives in the
metrics, but the scorecard reports duplicate contention **distinctly** — the same treatment I6 gives
"references non-existent target".

---

## D27 — The dataset inputs are fingerprinted too ✅ (completes D10)

**Fork:** D10 fingerprinted the findings artifact and the answer key, but **not the dataset inputs** — yet the
inputs move the score.

**Why this defeated D10's whole premise.** D10 exists so a scorecard need not be *trusted* because it can be
*recomputed*. Recomputation is only pinned if every score-determining input is pinned. The inputs set the
FP-rate denominator (invoice count) and drive target validation (which lines exist, per I6), so **an edited
input with an unchanged key and version scores differently while the provenance block looks identical** —
precisely the tampering D10 was meant to expose.

**Options considered**
- **(A) Store the full per-file digest list in every scorecard** — a mismatch is diagnosable straight from the
  stored record with nothing to recompute, at a cost of ~75–150 entries per scorecard at P3 scale, in files
  that are the durable committed record.
- **(B) Aggregate digest stored; per-file recomputed on mismatch.**

**Decision ✅** — **(B).** One aggregate digest per scorecard; `--verify` recomputes per-file **only** when the
aggregate diverges, and reports which file changed. Diagnostic depth computed when needed rather than stored
always.

**The algorithm must be specified precisely, or it is not reproducible either:**
1. Include every file under `inputs_dir`, recursively.
2. Normalize each path **relative to `inputs_dir`, with forward slashes** — a Windows backslash would
   otherwise digest differently from a Linux checkout of identical data.
3. Sort by normalized path, byte-wise.
4. Digest each file's **raw bytes**. No text transformation of any kind: the invoices are PDFs.
5. Hash the concatenation of `path + file_digest` pairs in that order.

**Hazard this exposes — git line-ending conversion.** If `autocrlf` normalizes the JSON inputs, a Windows and
a Linux checkout hold **different bytes**, so the digest differs and the cross-platform identical-output
requirement (N3) fails in a way that looks like a harness bug. Dataset files require `.gitattributes` marking
them binary / `-text`.

**The manifest is deliberately not fingerprinted** — it only *points* at the inputs and key, so any redirection
already surfaces as a changed inputs or key digest.

---

## D28 — No division inside a decision; pinned precision for everything else ✅

**Fork:** D23 says compare at full `Decimal` precision, never rounding before a comparison. But the tax rate is
`po_tax ÷ po_taxable_subtotal`, generally non-terminating — and `Decimal` division rounds to the **ambient
context precision**. That is the one place "exact" cannot be taken literally, and an auditor recomputing at a
different precision could diverge.

**Options considered**
- **(A) Pin the context precision only** — declare a fixed precision so the derived rate rounds identically
  everywhere, keeping the straightforward divide-then-compare form. Reproducible in practice, but "exact"
  degrades to "exact to N significant digits" and a rounding step stays in the decision path.
- **(B) Cross-multiply the decision, and pin precision as well.**

**Decision ✅** — **(B).**

**Remove the division from the decision.** Since `po_taxable_subtotal > 0`:

```
LHS = | inv_tax × po_taxable − po_tax × inv_taxable |
RHS = threshold × po_taxable
flag iff LHS >= RHS
```

Algebraically identical to comparing the variance against the threshold, but **multiplication and subtraction
only** — genuinely exact, with zero precision dependence. The dollar variance still needs a division to
*display*, which is harmless because display rounding never feeds a comparison (D23).

**It degrades correctly:** with `inv_taxable = 0` and tax charged anyway, the inequality reduces to
`inv_tax >= $0.05` — tax billed on nothing always flags.

**Second precision hole this exposed.** Precision, recall and FP-per-invoice are **also divisions**, and unlike
the tax rate they are *reported values under the byte-identical comparison*. Left at the ambient context
precision, two runs on differently-configured interpreters could emit different scorecard bytes — making **U4
quietly unenforceable**. So:
- Pin the `Decimal` context precision as a **declared constant**, covering any incidental division.
- Give every reported ratio an **explicit output precision and `ROUND_HALF_UP`**, so the emitted bytes are
  fixed by the spec rather than by the environment.

---

## D29 — Zero taxable subtotal: the degenerate tax branch ✅ (fixes a defect in D28)

**Fork:** What does the tax check do when the purchase order has no taxable lines at all
(`po_taxable_subtotal = 0`)? No rate is derivable, and D28's cross-multiplied comparison collapses.

**The defect.** Multiplying an inequality through by `po_taxable` is valid **only when it is positive**. At
zero the transformation destroys the inequality:

```
LHS = | inv_tax × 0 − po_tax × inv_taxable |  =  0     (po_tax is 0 here)
RHS = threshold × 0                          =  0
0 >= 0  →  always flags
```

Worse, it flags **identically whether the invoice charged $0 or $50** — `inv_tax` is annihilated by the
multiplication, so all information is lost. D28 stated the precondition `po_taxable > 0` but never specified
the behaviour when it fails.

**An epistemic correction worth recording.** This was first argued from the reference fixtures, where 36 of 50
POs carry `tax: 0.0`. The author rightly objected that **those fixtures were AI-generated, so their
distribution is evidence about a generator, not about the world.** The sound basis is the domain itself:
unprepared food is sales-tax-exempt in most US states, and the scenario is a food distributor, so
mostly-exempt POs are plausible on the merits. **And the defect does not depend on frequency at all** — the
formula is wrong for even one exempt PO. Frequency affected only how loudly it would fail.

**A distinction clarified by the author.** "No taxable lines" is *not* "no tax line". A real PO or invoice
printing system uses **one template** and prints `Tax: 0.00` — as a grocery receipt does — and the reference
data agrees: `"tax": 0.0` is present with value zero, never absent. What is missing is a derivable **rate**,
not a field.

**Decision ✅** — an explicit branch, bypassing cross-multiplication because there is nothing to divide:

```
if po_taxable_subtotal == 0:
    expected_tax = 0
    variance     = inv_tax
    basis        = 0  →  threshold = max($0.05, min(0, $25)) = $0.05
    flag iff |inv_tax| >= $0.05        # category TAX_VARIANCE, DOCUMENT scope
```

Correctly printing `Tax: 0.00` on an exempt order produces **no finding**; charging 5¢ or more **flags**. The
floor falls out of the existing threshold formula — no new constant. This restores the distinction the
collapsed form had destroyed.

**Relies on taxability being PO-determined, not invoice-claimed** (the R9 precedent: the derived rate applies
to invoiced lines whose *PO counterpart* is `taxable: true`). So when no PO line is taxable, the invoiced
taxable subtotal is zero too.

**Two supporting rules, both confirmed by the author:**

| `po_taxable` | `po_tax` | Status |
|---|---|---|
| 0 | 0.00 | **normal and coherent** — the common exempt case; expected tax = 0 |
| 0 | > 0 | **malformed — reject the dataset at load**, naming the PO |
| > 0 | ≥ 0 | rate derivable; D28's cross-multiplied comparison applies |

Rejecting row 2 is what makes "expected tax = 0" a **safe convention** for row 1 rather than an assumption
that could silently contradict the PO's own tax field.

- **The tax field SHALL always be present**, as `0.00`, never absent or null, on both PO and invoice. This
  matches single-template printing behaviour and removes an entire class of bug where the harness must
  distinguish *absent* from *zero* — and it stops the key author omitting it by accident.

**Systematic sweep applied to the other multiply-through formulas** — every formula that multiplies by a
quantity needs its zero behaviour stated. The threshold's `2% × basis` degrades correctly to the `$0.05` floor;
quantity materiality's `excess × po_unit_price` correctly yields no finding for a zero-priced item, since no
money moves. **Tax was the only one that broke.**

---

## D30 — The isolation check: verify configuration and placement; attest enforcement ✅

**Fork:** The criterion said a canary probe "confirms the guarded area is unreachable from an agent context".
What actually ships?

**The defect — the criterion was unsatisfiable as written.** Deny rules are enforced by the harness **at the
tool-call layer**. A Python probe runs *below* that boundary, so it will always `open()` the canary
successfully. A reachability probe would therefore report failure **unconditionally**, and would fail
*identically* whether the guards were perfect or entirely absent. It would prove nothing while looking like
verification — the worst possible outcome for a credibility artifact. This is the "arbitrary subprocesses are
outside deny coverage" gap the prior handover already recorded, but its consequence for the *probe* was missed.

**Decision ✅** — split it by what is actually provable.

**Ships as code (deterministic, automatable):**
1. **Guard-configuration check** — the deny rules exist, parse, and **cover every path in the secret tier**:
   the directory, the answer-key filename, the generator filenames, the design artifact. This catches the
   realistic regression — a guard file lost, hand-edited, or left stale when a new secret file was added.
2. **Placement check** — no secret artifact exists anywhere inside the repo tree. Per D14, **placement is the
   primary control**; deny rules are the second layer.

**Not code — manual attestation.** Harness enforcement is verified as the prior work did it: a session attempts
a tool-level read, the refusal is observed, and the outcome is recorded **with date and method**. The canary
survives unchanged in role — a decoy covered *only* by the directory rule, so it exercises the weakest layer —
but it is an **attestation instrument, not an automated assertion**.

**The README claim must match what is verified.** "Contamination structurally impossible, verified by automated
probe" would be false. The honest claim: *placement and guard configuration are automatically verified;
harness enforcement is attested with a dated record; a determined subprocess is outside deny coverage by
design, which is precisely why placement outside the tree is the primary control.*

**Why this is the stronger portfolio position** — for an agentic-evaluation artifact, demonstrating that you
know the limits of your own verification beats claiming more than you can show. Same discipline as the
documented scoring caveats.

---

## D31 — Goods receipts are separate documents ✅

**Fork:** How are goods receipts represented? D17's illustrative tree listed only `invoices/` and
`po_database/`; the reference fixtures embed a `receipts[]` array inside each PO record.

**Options considered**
- **(A) Embedded `receipts[]` inside each PO record** — the existing fixture shape, one fewer input directory,
  PO-line-to-receipt correspondence already aligned. **Rejected** for the reason the prior handover itself
  flagged: with receipts inside the PO JSON, **a lazy agent can diff `qty_ordered` against `qty_received` in a
  single file and surface quantity discrepancies without ever opening an invoice.** That undercuts what the
  harness measures.
- **(B) Separate goods-receipt documents.**

**Decision ✅** — **(B).** Receipts become their own documents, carrying GRN, date, receiver, line items, and
**their own identifiers and descriptions**.

**Why** — it makes GR→PO correspondence genuine work, and it is what the taxonomy already assumes: *"GR says
Part #X792"* is only expressible if the receipt is a distinct document with its own identifiers.

**Format split, which falls out realistically** — `invoices/` are **supplier PDFs** (external documents that
arrive and must be extracted); `po_database/` and `goods_receipts/` are **internal structured JSON** (systems
of record). This keeps the extraction challenge exactly where it belongs.

**Consequence that D15 did not state** — with separate receipts and partial deliveries, the received quantity
in `min(qty_ordered, qty_received)` is a **sum across all goods receipts for that PO line**, not a single
field. A key computed against one receipt where two exist would be **wrong**.

---

## D32 — Three data families; only implausible values go synthetic ✅

**Fork:** Criteria demand a $100,000 extended line, a $333.33 non-aligned basis, and a fully-exempt PO. Forcing
those into a realistic small dataset would make the headline artifact absurd.

**The premise is right, but the line is not "boundary tests are synthetic"** — most of those values are
perfectly realistic:

| Criterion | Plausible in food distribution? |
|---|---|
| Fully-exempt PO | **Yes** — the common case (D29) |
| $500 extended line (aligned basis) | Yes |
| $333.33 extended line (non-aligned basis) | Yes |
| Zero-priced item (promo / sample) | Yes |
| **$100,000 extended line** | **No** — synthetic |

**Decision ✅** — **a criterion moves to a synthetic fixture only where its required value would be implausible
in the domain.** Three data families:

1. **`datasets/dev/`** — realistic, small, portfolio-facing; ships in the repo with its key. Demonstrates the
   methodology end to end, and shows boundary cases arising **naturally** rather than being contrived.
2. **Synthetic fixtures** — a handful, clearly labelled as such, for extreme-magnitude arithmetic only. They
   load through the **same manifest and loader**, so tests exercise the real code path rather than a parallel
   one.
3. **Held-out split** — realistic, out-of-tree (D14), the actual evaluation.

**Why the labelling matters** — a reviewer must never mistake a synthetic fixture for the showcase dataset. A
$100,000 head of lettuce in the portfolio artifact would undermine the domain credibility the realistic dev
split exists to establish.

---

## D33 — PDF authoring enters P1, but only the clean tier ✅ (corrects a stale constraint)

**Fork:** D31 makes invoices supplier PDFs, but the constraints block still defers the PDF-authoring library to
`[P3]` as "not needed now" — and authoring the dev split's invoices needs it now.

**The deferral conflated two things.** What P1 needs is **clean, text-layer invoice PDFs**. What can still
defer is **format difficulty** — multi-page dot-matrix layouts, consolidated invoices, and scanned/OCR-only
documents, the tiering the old fixtures used.

**Decision ✅** — **ReportLab, in P1, clean text-layer invoices only.** Hard format tiers remain `[P3]` with the
dataset expansion.

**Why ReportLab over PyMuPDF** — a decisive technical reason rather than preference: **PDF writers embed a
creation timestamp and a document ID by default, so regenerating the same dataset produces different bytes.**
That changes the D27 inputs digest and collapses byte-reproducibility **at the data layer**, while presenting
as tampering. ReportLab documents an invariant/deterministic-output mode aimed at exactly this; PyMuPDF does
not advertise one for authoring. **Verify this early in the build** rather than discovering it after the first
regeneration.

**Generation must therefore pin** the document creation and modification dates to the seeded timestamp (D6) and
pin or suppress the document ID.

**This does not breach the stdlib-only rule.** That constraint is scoped to the **scoring engine**; this
dependency lands on the **generation side**, which lives in the secret tier. The constraints block must say so
explicitly, because "no third-party dependencies" and "we need a PDF library" otherwise read as a contradiction.

---

## D34 — A structured invoice index, key-side and agent-denied ✅

**Fork:** Once invoices are PDFs, where does the harness get the structured invoice data it needs — tax-field
presence (D29), invoice count, line identifiers for target validation, timestamp validation — while never
parsing documents?

**Options considered**
- **(A) The harness parses the PDFs** — rejected twice over: extraction is explicitly out of scope, and it would
  drag a PDF library into the **scoring engine**, breaking the stdlib-only rule that makes the credibility core
  auditable.
- **(B) A structured sidecar beside the PDFs, agent-readable** — **the trap.** If the agent can read structured
  invoice data, extraction is bypassed entirely and the PDF becomes decoration.
- **(C) Fold a full line inventory into the answer key** — one artifact instead of two, but it blurs what the key
  *is*: expected findings become mixed with input restatement, and the key's fingerprint would then change
  whenever the inputs change even though no expectation did.
- **(D) A separate structured invoice index, key-side and agent-denied.**

**Decision ✅** — **(D).**

**Why it belongs with the key** — the index is **ground truth about what the documents contain**, the same
category as the invoice→PO→receipt correspondence D22 already placed key-side. Both answer *"what do these
documents actually say"*, which is exactly what the agent must derive for itself.

**Why the key alone is insufficient** — the key lists *expected findings*, covering only lines that carry a
discrepancy. Target validation (I6, a finding referencing a non-existent line) needs a **complete line
inventory including clean lines**. So it is a separate artifact, not a field on the key.

**Resulting tier model:**

| | agent-readable | agent-denied |
|---|---|---|
| **inputs** | invoice PDFs, PO JSON, goods-receipt JSON | — |
| **ground truth** | — | expected findings, **invoice index**, correspondence, generators, design artifact |

The asymmetry is realistic rather than arbitrary: purchase orders and receipts are *our* internal systems of
record, so structured data is genuinely what we would hold; invoices arrive from outside as documents.

**Consequence — the index must be fingerprinted.** By D27's own reasoning, every score-determining artifact must
be pinned or recomputation is not pinned. The invoice index drives the false-positive-rate denominator and
target validation, so an edited index under an unchanged key would score differently under identical-looking
provenance — reopening precisely the hole D27 closed. The scorecard therefore carries **four** fingerprints:
findings artifact, answer key, inputs aggregate, and invoice index.

---

## D35 — The scorer loads and matches; it never derives ✅ (corrects a misattribution throughout the spec)

**Fork:** Does the harness derive expected findings from the inputs at scoring time, or load them from the
answer key and only match? The spec said both — phrasing scoring semantics as things *"the harness SHALL
compute"* while treating the key as indispensable ground truth.

**The defect: the domain rules were attributed to the wrong actor.** What the scorer actually needs is small —
the match key for matching, counting for the metrics, the invoice index for target validation and the
false-positive-rate denominator. **It needs no domain rule at all.** The payable-quantity rule, the materiality
threshold, the tax comparison: those are applied by the **key generator** when authoring expectations, and
published in the **matching policy** so the agent can implement them too.

**Why this matters beyond tidiness** — if the scorer derived expectations, it would be scoring the agent
against **its own implementation of the rules**, not against audited ground truth. Any bug in that
implementation would silently *become* truth, and "held-out golden dataset" would collapse into "reference
implementation", which is a materially weaker claim. It is not even achievable in full: derivation needs the
invoice→PO→receipt correspondence, which D22 deliberately places in the key.

**Decision ✅**
- **The scoring engine loads expected findings from the answer key and confines itself to matching and
  counting.** No domain rule executes at scoring time.
- **Domain rules are re-attributed** to the key generator, and SHALL appear in the published matching policy —
  the agent cannot compete against rules it cannot read.
- **A separate key-audit command** derives expected findings from the structured inputs and diffs them against
  the declared key.

**Why the audit command is a distinct command** — it addresses the risk named repeatedly across this project:
*the answer key is the riskiest artifact, because a wrong key produces confidently wrong scores that nothing
downstream can detect.* Deriving catches arithmetic slips, drift after regeneration, and hand-edits. But it
**must never run inside a scoring run**, or a derivation bug could quietly become ground truth mid-score.

**Labelled honestly: a consistency check, not a correctness proof.** Generator and auditor share an author, so
their independence is weak. It catches transcription and drift, not shared misunderstanding.

---

## D36 — PDF and index agree by construction, with a round-trip closing the residual ✅

**Fork:** Nothing in the repository can prove the committed invoice PDFs and the committed invoice index agree,
since proving it means parsing a PDF — barred from the scoring engine by D34.

**Decision ✅** — two layers, neither of which is repository-side verification:

1. **Agreement by construction.** The generator emits the PDF **and** the index from **one canonical invoice
   record in a single pass**. They cannot diverge, because they have one source. Post-hoc hand-edits are caught
   by fingerprints — the inputs digest covers the PDF, the index fingerprint covers the index (D27, D34).
2. **Round-trip parse-back at generation time.** Construction does not cover a **rendering bug** — correct data
   in the index, mis-rendered into the PDF, a dropped digit or truncated column. So the generator writes the
   PDF, **reads it back, and asserts it matches the index**.

**Parsing is permitted here.** D34 bars a parser from the **scoring engine**, not from the generator, which
already carries ReportLab. A reader for a self-check sits on the same side of that boundary.

**Two honest limits**
- Round-trip extraction is reliable only for the **clean text-layer tier**. P3's dot-matrix and scanned tiers
  fall back to construction alone — and for a scanned tier that is unavoidable, since the whole point is that
  it has no text layer.
- The check lives **secret-side with the generator**, so its result is **attested, not shipped** — the same
  verify-what-you-can, attest-the-rest pattern as D30.

---

## Open items

> **T1 and T2 below were completed in spec 0.10.2.** Requirements are refiled to their correct EARS patterns,
> the `ubiquitous` block is subject-grouped, and a **subject index** names every section each subject touches.
> The entry is retained because the *reasoning* still applies: EARS groups by pattern, so a subject will always
> span sections, and the index — not co-location — is what makes that survivable. **The consistency-mechanism
> gap below remains open.**

- ~~**Structural regrouping of the requirements block (T1/T2 from the 0.10.1 sweep).**~~ **Done in 0.10.2.**
  Two defects, originally deferred so a large reorganisation would not ride along with semantic fixes:
  - **Misfiled EARS patterns** — the `ubiquitous (always active)` block now holds `WHEN`, `WHERE` and `IF`
    requirements, everything added by D24, D28, D29, D35 and D36. The categorisation is meaningless there, and
    `lint_spec.py` checks structure, not placement, so it cannot catch this.
  - **Scattering by subject** — tax rules sit in two blocks, quantity rules in two, fingerprint rules in three.
    **This is the root cause of the sweep's findings:** the contradicting lines were hundreds of lines apart, so
    each round's question only ever touched the half it was about.
- **The spec has no consistency mechanism.** The linter verifies structure; nothing verifies that a decision
  applied in one place was applied everywhere. Every contradiction the 0.10.1 sweep found was of exactly that
  shape. Until the regrouping lands, a periodic whole-document read is the only defence — the audit command
  (D35) does the equivalent job for the *data*, but has no counterpart for the *spec*.

---

## D37 — Scorecard serializes every `Decimal` as an exact JSON string ✅ (build)

**Fork:** How are monetary/ratio values emitted so the scorecard is byte-reproducible and float-free?

**Options considered**
- **(A) JSON number literal** (e.g. `0.6667`) — the plan's first instinct. But `json.dumps` cannot emit a
  `Decimal` as a number without a custom encoder, and a `float` bridge cannot represent `0.6667` exactly, which
  would break U4 byte-identity.
- **(B) Exact JSON string** (`"0.6667"`, `null` for undefined).

**Decision ✅** — **(B).** Ratios quantize to the declared places (`ROUND_HALF_UP`) and emit as strings; an
undefined metric emits `null`; counts are JSON integers (exact). Read back with `parse_float=Decimal`.

**Why** — a string is exact and byte-stable and keeps `float` off the emission path entirely, which the
"no float on a monetary path" scan then confirms. Refines the plan's call 4 (string, not number literal).

---

## D38 — The held-out answer key is named `ANSWER_KEY.json`; the dev key stays `answer_key.json` ⛔ SUPERSEDED by D42

> **Superseded 2026-07-26 — the reasoning below is invalid and the naming caused two live bugs.** Kept
> verbatim as the record of what was tried and why it failed. `ANSWER_KEY.json` and `answer_key.json` are the
> **same name** on a case-insensitive filesystem, so case cannot distinguish them: the fix only works under the
> assumption that makes it unnecessary, and fails under the assumption that motivated it. See **D42**.

**Fork:** The primary guard is the secret *directory*, but the spec asks the guard to cover "the answer-key
filename." A bare `**/answer_key.json` deny rule would also match the **public** dev key on a case-insensitive
Windows filesystem and wrongly block it.

**Decision ✅** — the held-out (secret-side) key uses the distinct, guardable name **`ANSWER_KEY.json`**
(matching the prior answer-key-guard convention); the in-repo dev key keeps the lowercase `answer_key.json`.
The deny rule `Read(**/goldset-triad-secret/**/ANSWER_KEY.json)` then covers the held-out key by filename
without any chance of matching the public dev key.

**Why** — filename coverage without a case-insensitivity collision that would break the dev split.

---

## D39 — pyright runs in `standard` mode, not `strict` ✅ (build)

**Fork:** Which pyright configuration is the zero-error gate?

**Options considered**
- **(A) `strict` + `reportUnknown*`** — flagged 158 errors, ~86 in the scoring core, essentially all from
  `json.loads` returning `Any` at data-loading boundaries. Reaching zero would need pervasive `cast()` at every
  JSON access — churn that adds no runtime safety.
- **(B) `standard` mode.**

**Decision ✅** — **(B).** Standard mode still catches genuine type errors (it caught a real one — a test helper
typed `object` instead of `LineInventory`) and reaches **0 errors, 0 warnings**. The acceptance criterion is
"pyright reports zero errors," which standard mode satisfies; D7's "stricter by default" describes pyright vs
mypy, not the maximal mode.

**Why** — a conventional, CI-appropriate gate that enforces real type correctness without treating unavoidable
`Any` at JSON boundaries as an error.

---

## D40 — PDF parse-back is dependency-free ✅ (build)

**Fork:** D36's generation-time parse-back needs to read the PDF back. With what?

**Options considered**
- **(A) A PDF-reader dependency** (pypdf/pdfminer) — a *second* generation-side third-party package beyond the
  approved ReportLab.
- **(B) A regex over the uncompressed content stream** — disable PDF compression (`pageCompression=0`), draw
  each index value as its own cell, and extract the `(value) Tj` text tokens directly.

**Decision ✅** — **(B).** Keeps the flagged-dependency list to exactly **ReportLab (generation) + pyright
(type gate)**, as approved. Reliable for the clean text-layer tier, which is all P1 authors (P3's scanned tier
would need OCR and falls back to single-source construction per D36).

---

## D41 — Dataset *validation* is a loader task, distinct from the scored domain rules ✅ (build)

**Fork:** The D29 malformed checks (zero-taxable-with-tax, absent tax field) and D6 timestamp checks need to
read PO/invoice tax fields and timestamps — but the scoring engine must contain "no domain rule."

**Decision ✅** — dataset *integrity validation* lives in the loader (`dataset.py`) and is treated as separate
from the scored *domain rules* (payable quantity, materiality, tax comparison), which live only in the key
generator and the audit command (D35). The "scoring engine implements no domain rule" scan targets the
matching core (`scoring.py`), which genuinely computes none. The scorer reads only the key (expected findings),
the invoice index (line inventory + count) and the findings artifact; it never parses a PO, receipt or PDF for
*scoring* — only the loader parses PO/GR/index JSON for *validation*.

**Why** — validating whether a dataset is coherent is a different act from deciding whether a discrepancy
exists; conflating them would either weaken the "no domain rule in the scorer" claim or make malformed-input
rejection impossible.

---

## D42 — Key filenames must be genuinely distinct, never case variants ✅ (supersedes D38)

**Fork:** D38 distinguished the held-out key from the public dev key by **capitalisation alone** —
`ANSWER_KEY.json` versus `answer_key.json` — to let a filename deny rule cover the secret key without matching
the public one.

**Why that cannot work.** The two names are **identical on a case-insensitive filesystem**, which is the very
condition D38 invoked. The logic is self-defeating:

- If matching is case-**sensitive**, the names are distinct — but then no collision existed to solve.
- If matching is case-**insensitive** (D38's premise), the names are the same and the fix does nothing.

**It only works in the world where it is not needed.** D38's rule happened to be safe, but for a reason it did
not state: `Read(**/goldset-triad-secret/**/ANSWER_KEY.json)` is **path-scoped**, and the path segment — not the
capitalisation — is what excluded the dev keys.

**Two live bugs the naming actually caused:**

1. **All three public dev keys were silently excluded from the repository.** `core.ignorecase` is true on
   Windows, so the `.gitignore` rule `ANSWER_KEY*` matched `datasets/*/answer_key.json`. Nothing under
   `datasets/` was tracked. The spec requires the dev split to "ship complete in the repository, inputs and
   answer key together" — it did not, and a fresh clone could not have run a single dev-split test.
2. **The placement check had a case-variant blind spot.** `check_isolation.py` compared filenames with
   `name in SECRET_ARTIFACT_NAMES`, a case-**sensitive** Python comparison. It had to be: case-folding would have
   flagged the legitimate dev keys. But a case-sensitive comparison cannot see a stray copy that arrives under
   different casing — precisely the leak a filename check exists to catch.

**A third, structural cost:** path-scoping the filename rule made it **redundant with the directory rule above
it**. A filename rule's only added value is catching a **stray copy that escaped the secret tier**, and a rule
scoped inside that tier cannot do that. Unscoping it was impossible while a public file shared the name.

**Decision ✅** — genuinely distinct names, differing by more than case:

| | Name | Location |
|---|---|---|
| Held-out key | `holdout_answer_key.json` | secret tier, out of tree |
| Dev keys (×3) | `dev_answer_key.json` | in repo, public by design |

Consequences, all applied:
- The deny rule becomes **unscoped** — `Read(**/holdout_answer_key.json)` — regaining the stray-copy coverage
  that was the whole point of a filename rule, with no possibility of matching a public key on any platform.
- `check_isolation.py` now compares **case-insensitively** (`_is_secret_name`), closing the blind spot. That is
  only safe because the names are genuinely distinct.
- `.gitignore` names the held-out key exactly, so the dev keys are tracked.
- Guard template updated on the secret side and re-stamped into the repo, per its own instruction.

**Rule to carry forward:** *case must never be load-bearing.* Beyond case-insensitive filesystems, git
normalises case on some checkouts and renames — the same family of cross-platform hazard as the `autocrlf`
byte-mangling already recorded in D27. Where two things must be distinguished, give them different names.

**Verified:** all 95 tests pass; `git check-ignore` no longer matches the dev keys; the guard file contains the
unscoped rule.

---

## D43 — The generator pins LF; generation must be deterministic, not merely preserved ✅

**Fork:** The generator wrote files with Python's default newline translation, so it emitted **CRLF on Windows
and would emit LF on Linux** — different bytes for identical data. Which line ending should it pin?

**Why this mattered more than it looks.** The aggregate inputs digest (D27) hashes **raw bytes**, so a
platform-dependent newline makes the digest platform-dependent, which breaks the cross-platform identity
requirement (N3). The failure was masked: `.gitattributes` marks dataset files `-text`, so git does not convert
*already-committed* bytes and a Linux clone matched. But that protects **transport**, not **generation** — a
regeneration on Linux would have produced a different digest for identical data, and the discrepancy would have
surfaced as an apparent tampering signal rather than as a newline difference.

**How it was found** — by checking that regenerating reproduces the committed tree. The keys, indexes and PDFs
regenerated byte-identically while the three manifests came back modified; the manifests had been hand-edited
with LF while the generator emitted CRLF. The one-line divergence exposed the platform dependency behind it.

**Options considered**
- **(A) Pin CRLF** — matched what was already committed, so zero diff. **Rejected:** it bakes a Windows-ism into
  a cross-platform artifact, and a Linux regeneration would still diverge.
- **(B) Leave the platform default** — status quo. **Rejected:** it makes generation non-deterministic across
  platforms, which is precisely what D27 exists to prevent.
- **(C) Pin LF explicitly** (`newline="\n"`).

**Decision ✅** — **(C).** LF is the portable default; pinning it makes generation deterministic *at the source*
rather than relying on `.gitattributes` to hide the difference downstream.

**Consequences**
- Every generated JSON was regenerated to LF: 966 insertions against 966 deletions, with
  `git diff --ignore-cr-at-eol` empty — **line endings only, no content change**. PDFs are binary and untouched.
- The aggregate inputs digest changed. Nothing depended on a baked value: digests are computed at run time and
  no scorecard is committed.
- **Regeneration is now idempotent** — running the generator twice leaves the tree byte-identical. That is what
  makes "does regeneration reproduce the committed tree?" a meaningful drift check rather than a noisy one.
- `.gitattributes` stays as it is. It remains necessary: it protects the committed bytes in transit, while this
  decision fixes the bytes at the point they are written.

**Same commit also repaired** the generator's key filenames, which were still the pre-D42 names — regenerating
would have repointed the manifests at `answer_key.json` and stranded `dev_answer_key.json` as a stale orphan
that the tests still read, so harness and tests would have diverged silently. That fix changed no data, because
the names on disk were already correct.

---

## D44 — Repository composition is asserted over the git index, not the filesystem ✅

**Fork:** D42 fixed the `ANSWER_KEY*` ignore rule that would have dropped the three **public** dev keys from
the commit. That fix removed the instance. What removes the *class*?

**Why nothing already in the suite could have caught it.** Every check — placement, isolation, dataset
loading — reads the **filesystem**, and on the filesystem the excluded file is plainly present and valid. The
suite would have stayed fully green while a fresh clone lacked the keys, so *"the dev split ships complete"*
and *"the full acceptance suite passes from the repository alone"* would both have been false, silently. A
green suite asserting the wrong surface is worse than no check, because it manufactures confidence.

**Options considered**
- **(A) Assert the specific fact** — "the three dev keys are tracked." Closes the instance, not the class: the
  next ignore rule to over-match some other required file is undetected.
- **(B) Assert over the git index and ignore rules**, generalised to every file that must ship.

**Decision ✅** — **(B).** Four assertions: no file in the shipping trees (`src`, `tests`, `datasets`) may be
excluded by an ignore rule; named critical files must be tracked; each dev split must ship its inputs *and* its
key; and no secret artifact may be tracked — the **dual** of the placement check, since a `git add -f` leak is
invisible to a filesystem walk of an otherwise clean tree.

**Scoped deliberately to *silent* exclusion.** A file merely not yet `git add`-ed is **loud**: `git status`
shows it, and a CI checkout contains only committed files. Asserting "every on-disk file is tracked" would fail
on ordinary in-progress work and train readers to ignore the signal — the failure mode that makes a noisy guard
worse than none. An ignore rule is the silent case, so that is what is asserted.

**Two implementation details are load-bearing, both found by the check failing against itself**
- **`--no-index`.** By default `git check-ignore` consults the index and will **not** report an already-tracked
  path as ignored. Without this flag the check passes vacuously from the moment the file is committed —
  reporting health precisely when the damage is done.
- **`-z` with byte-mode I/O.** In text mode `subprocess` translates `\n` to the platform line ending when
  writing stdin, so on Windows git received each path with a trailing CR and checked a filename that does not
  exist, yielding false negatives against exact-name rules. The same newline-translation class as **D43**,
  hit twice in one session — which is itself the argument for never leaving a newline implicit.

**A guard that cannot fail is worth nothing.** Because this one has two specific ways of rotting into a vacuous
pass, the suite **self-verifies**: it injects the historical `*ANSWER_KEY*` pattern through a temporary excludes
file — the repository's own `.gitignore` untouched — and asserts all three dev keys are caught, and that the
returned paths carry no CR and no quoting.

**Consequence** — a `[P1]` acceptance criterion now covers repository composition, so this is a binding
requirement a future rebuild must satisfy rather than a test someone could quietly delete.

---

## D45 — Every secret artifact needs a distinct name and extension-agnostic coverage ✅ (sweep)

**Fork:** D42 fixed the answer key's name. Did anything else share the same flaw?

**Two artifacts did.**

**The held-out invoice index.** It is agent-denied ground truth under D34 — the *extraction answer* — but every
split called it `invoice_index.json`, so the held-out copy shared a name with three **public** dev indexes. It
could therefore be given **no filename deny rule and no placement-check entry** without flagging the public
ones. Verified absent from both. It was protected by directory placement alone: **uniquely weaker than every
other secret artifact**, and for exactly the reason D42 diagnosed.

**Generator bytecode.** `_generators/__pycache__/gen_rules.cpython-314.pyc` exists on disk today. A `.pyc` is
decompilable, so it carries the discrepancy-planting rule just as the source does — and the rules named
`gen_rules.py`, so a stray `.pyc` copy would have evaded every filename rule and the placement check alike.

**Decision ✅**
- The held-out index is renamed **`holdout_invoice_index.json`**, with its own unscoped deny rule, and it joins
  `SECRET_ARTIFACT_NAMES`.
- Filename deny rules use an **extension wildcard** — `gen_rules.*`, not `gen_rules.py`.
- The placement check matches on the **stem** (text before the first dot), case-insensitively, so
  `gen_rules.cpython-314.pyc` and `gen_rules.py.bak` are both caught.
- The generator's `.gitignore` excludes bytecode: a `.pyc` adds no recoverability, only churn and a second copy
  of the rules.

**A trap this exposed, worth remembering.** The rename was first applied *by hand* to the file and manifest —
and the next `generate.py` run **silently reverted it**, because the generator is the source of truth for both.
Renaming generated artifacts by hand is always undone. `index_filename` is now a `DatasetSpec` field with a
held-out override, mirroring how `key_filename` already worked.

**Generalised rule:** *every artifact that exists on both the secret and the public side needs a name that
differs by more than case or extension.* D42 established it for one artifact; it is a property of the tier
boundary, not of the answer key.

---

## D46 — The published policy is derived from the rule constants, never hand-written ✅ (sweep)

**Fork:** `matching_policy.json` is what D35 requires the generator to publish so an agent can compete. Was it
guaranteed to match the rules actually applied?

**No.** The threshold text was a **hand-written string literal** in `generate.py`
(`"max($0.05, min(2% x basis, $25))"`), while the real constants lived in `gen_rules.py` as `FIVE_CENTS`,
`TWENTY_FIVE`, `TWO_PERCENT`. Change `TWENTY_FIVE` to 50 and the published policy would still promise $25 —
and **nothing would catch it**, because the key-audit command never reads the policy. An agent would be
competing against a rule that is not the rule.

**Decision ✅** — the threshold text is **interpolated from the constants**, following the precedent already set
by `categories`, which was derived from the `Cat` enum. Divergence is now impossible by construction rather
than by discipline.

**Also published: the precision rule.** The policy omitted D23's compare-at-full-precision and D28's
division-free requirement — yet both decide whether an agent flags a **boundary** case. An agent that rounds
before comparing, or divides to derive a tax rate, can disagree with the key on identical inputs. Scorer-only
concerns (display places, ratio places) are deliberately *not* published: they cannot change a flag decision.

**Verified** — regeneration changed **only** `matching_policy.json`; every input, key and index stayed
byte-identical, confirming D33's determinism. The derived text reproduces the previous string exactly, so the
interpolation is correct rather than merely different.

---

## D47 — Multi-PO tax attribution is UNSPECIFIED and must be rejected until specified 🔶 (sweep)

**Fork:** Which PO's tax rate governs an invoice that references **several** POs?

**Nothing decided this, and code silently chose.** Both the generator and the auditor iterate per
*(invoice, PO)* pair, so an invoice spanning two POs is tested once per PO and flagged if **either** rate says
material. That behaviour lives only in code. **D3's own consequence note predicted exactly this:** *"When P2/P3
add multi-PO invoices with varying rates, the answer key must compute tax per-PO/per-line correctly or the key
itself will be wrong."*

**Latent, not live — for now.** Verified: **zero multi-PO invoices** across all four splits. It becomes live at
`[P3]`'s ~75 invoices, where multi-PO invoices are ordinary.

**The intended resolution**, recorded so it is not re-derived: expected tax is the **sum over referenced POs**
of each PO's rate applied to the invoiced taxable subtotal attributable to *that PO's* lines — available via the
correspondence. Keeping it division-free (D28) generalises the cross-multiplication: with `D` the product of all
PO taxable subtotals and `D_p` the product of the others, compare
`|inv_tax × D − Σ_p (po_tax_p × inv_taxable_p × D_p)| >= threshold × D`. All multiplication, exact.

**Caveat on that formula:** the products grow with the number of POs, so with many POs it could exceed the
pinned 28-digit context and lose exactness — the one place D28's precision pin becomes a real constraint rather
than a formality.

**Decision for now ✅** — a multi-PO invoice whose POs have **differing derived rates** SHALL be **rejected by
dataset validation** as unspecified, rather than silently keyed by whichever PO happens to flag. Same rates on
all referenced POs is unambiguous and remains allowed.

**✅ IMPLEMENTED** — `_validate_multi_po_tax_rates` in `dataset.py`, a cross-artifact validation (it needs the
key's correspondence *and* the POs, so it cannot sit in a per-artifact validator). Rejected at load, naming both
POs. A test asserts no shipped dataset has a multi-PO invoice, so **the moment `[P3]` authors one, that test
fails and forces the apportionment to be implemented** rather than silently keyed.

**A tolerance is required, and exact equality would have been a bug — caught by its own test.** A PO's tax is a
rate applied to a subtotal *then quantized to cents*, so two POs authored at the **same** rate derive slightly
different ones: at 8.7%, subtotals of 3312.51 and 912.00 give 288.19 and 79.34, cross-multiplying to 262829.28
against 262814.54. Exact comparison would have rejected a legitimate same-rate invoice. The residual is bounded
by the quantization — half a cent on each side, so at most `0.005 × (sub_a + sub_b)` — and a genuinely different
rate exceeds that by orders of magnitude. The check compares against that bound, still using only multiplication
and addition. **The test that proves equal rates are allowed is what exposed this**; a rejection-only test would
have passed a check that rejected everything.

---

## D48 — The key audit's completeness is bounded by the correspondence it audits 🔶 (sweep)

> **Numbering note.** These four sweep entries were first written as D43–D46 and renumbered to D45–D48: the
> build session had already committed its own D43 and D44 while this sweep was in progress. Caught by checking
> the heading list before finalising. The lesson generalises — **read the current maximum before numbering**,
> because two sessions appending to one record will collide, and a duplicate number silently breaks every
> reference to it.

**Fork:** How complete is the D35 key audit, actually?

**A structural limit, previously unrecorded.** `_derive_expected` iterates the **correspondence declared in the
key it is auditing**. So a key that omits *both* a correspondence entry *and* the finding that entry would have
produced is **self-consistently wrong and passes the audit**. The auditor never looks at that line, so it
cannot report it missing.

This is inherent to D22 placing the correspondence in the key — the auditor has no other source for it — so it
cannot be removed, only bounded.

**Decision ✅** — state the limit plainly wherever the audit's guarantee is described: it verifies that
*declared* correspondence yields *declared* findings, not that the correspondence is complete. Combined with
D35's existing caveat (generator and auditor share an author), the audit catches arithmetic slips,
transcription errors and post-regeneration drift — not omissions and not shared misunderstanding.

**✅ MITIGATION IMPLEMENTED** — `_validate_correspondence_completeness` in `dataset.py` rejects a dataset whose
index contains any invoice line with no correspondence entry, naming the offending lines. **The hole cannot be
closed from inside the audit** — the correspondence has no other source (D22) — but it can be closed *here*: if
every line is covered, the audit has looked at every line. Placed at load, so it guards the scorer too, not only
the audit command.

All four splits were already complete (16/16, 1/1, 2/2, 2/2, verified during this sweep); the invariant is now
asserted rather than assumed, with a negative test that drops an entry and confirms rejection.

---

## D49 — Scorecards cannot be overwritten, and their bytes are platform-independent ✅

**Fork:** The scorecard filename derived from the run stamp, which is second-precision because **every**
timestamp this harness writes is (D6). Two runs inside one second therefore derived the **same filename** and
the second silently destroyed the first — against *"Never delete or overwrite a prior scorecard; they are the
durable record"* and against the spec's own claim that *"runs may overlap safely because each writes a
distinctly timestamped scorecard."* Demonstrated: three back-to-back runs left one file.

**Options considered**
- **(A) Sub-second precision in the filename** — smallest change. **Rejected:** it puts a
  finer-than-second timestamp into an artifact name, contradicting the second-precision rule it would be
  working around.
- **(B) Content digest as the suffix** — deterministic. **Rejected:** two runs on identical inputs produce an
  identical digest, so the collision returns for exactly the case that provokes it.
- **(C) Ordinal on collision, plus exclusive creation.**

**Decision ✅** — **(C).** The stem stays second-precision; if it is taken, an ordinal (`-2`, `-3`) is appended,
checking both extensions together so the pair never straddles two stems. Files are created with mode `"x"`, so
overwriting is **impossible at the operating-system level** rather than merely unintended.

**The same commit pinned the writer's newline.** `write_text` without `newline=` emitted CRLF on Windows and LF
on Linux, so the scorecard — the durable record — had platform-dependent bytes, contradicting *"identical
scorecard content on Windows and on Linux."* This is the **third** instance of the newline-translation class
(D43 in the generator, D44 in a subprocess stdin), and the first in shipping code, because D43 pinned only the
out-of-tree generator. `.gitattributes` now covers the `.txt` summary as well as the `.json`.

**How it hid:** the reproducibility test slept 1.05 s to obtain distinct stamps. That worked around the defect
instead of exposing it — a sleep inserted to make a test pass is worth re-reading as a symptom.

---

## D50 — Ground-truth references are resolved at load, not trusted ✅

**Fork:** D48 established that every invoice line needs a correspondence entry. Five neighbouring holes
remained, all demonstrated as accepted by the loader.

**Decision ✅** — reject each at load, naming the specific cause:
1. **An expected finding naming a target absent from the index.** The severe one: such an expectation can never
   be matched, so it becomes a **permanent false negative** scoring every agent worse than it performed, on a
   dataset that looks healthy. Exactly the "wrong key, confidently wrong scores" failure the key is the
   riskiest artifact for.
2. **An empty correspondence list.** The completeness check returned early when the list was empty, so the rule
   enforced only *"if you declare some, declare all"* while D22 requires one entry per line. An escape hatch
   that exempts the largest possible omission is not an exemption, it is a hole.
3. **A correspondence row naming a nonexistent invoice line** (an orphan — D48 checked only the converse).
4. **A row naming a nonexistent purchase order.** It had been silently defaulted to a zero-rated PO by the
   multi-PO rate check.
5. **A row naming a nonexistent line on a real purchase order.**

**Ordering is deliberate:** reference resolution runs **before** the D47 rate check. Previously a phantom PO,
where it surfaced at all, surfaced as *"tax rates differ … apportionment UNSPECIFIED"* — sending a reader to
implement apportionment over what was actually a typo. A check that misdiagnoses is worse than one that is
silent, because it directs effort at the wrong thing.

**The audit command keeps its own guards.** `audit()` resolves the manifest directly and does **not** run the
loader's validation, so it can still meet an unresolved reference; it reported `KeyError ('PO-3001','P999')`,
naming a tuple rather than the fault. Both lookups now raise named causes, per *"every halt SHALL name its
specific cause."*

---

## D51 — A public artifact name may never be a substring of its held-out counterpart ✅

**Fork:** D45 renamed the held-out index to `holdout_invoice_index.json` but left the public one
`invoice_index.json` — which is a **substring** of the held-out name.

**Why that is the same bug D42 fixed, in a new disguise.** D42's lesson was "case must never be load-bearing;
where two things must be distinguished, give them different names." Substring containment defeats distinction
just as case-insensitivity does: any deny rule written against the held-out tail — `*invoice_index.json*` —
also matches all three **public** dev indexes and silently over-blocks the dev split, which is the D14 trap.
The *key* names were already mutually non-containing; the index names were not.

**Decision ✅** — the public index becomes `dev_invoice_index.json`, symmetrical with `dev_answer_key.json`, so
neither name contains the other. Recorded as a general rule rather than a rename: **no public artifact name may
be a substring of its held-out counterpart.**

**A vacuous test fell out of it.** The assertion that no index appears under `inputs/` pinned the literal old
filename, so the rename would have made it pass while checking nothing. It now matches any `*invoice_index*`
and additionally asserts the index it expects does exist, so it cannot be satisfied by absence.

---

## D52 — The secret-artifact vocabulary has exactly one source ✅

**Fork:** The list of secret artifact names existed twice — canonically in `check_isolation` (filesystem
placement) and as a private copy in the git-index check.

**It drifted within one commit cycle.** The copy never learned about `holdout_invoice_index.json` (D45), and
because its entries carried a `.py` suffix it could not have caught a tracked `gen_rules.cpython-314.pyc` —
the very bytecode case D45 added stem matching for. So the index-side check silently covered less than the
filesystem-side one.

**Decision ✅** — the git-index check imports the canonical set and its matcher. A test asserts the matcher
recognises every artifact type **including** bytecode and backup extensions, and equally that it does **not**
claim the public dev artifacts — because a placement check that flagged `dev_answer_key.json` would be as
broken as one that missed the held-out key.

---

## D53 — The published policy is bound to the implementation that ships ✅

**Fork:** D46 interpolated the policy from the generator's constants, removing authoring-time drift. But the
generator does **not** ship, so nothing in the repository could detect the published rule diverging from an
implementation a reader can actually run.

**Decision ✅** — a test binds the policy's stated floor, cap and percentage to `audit_key`'s constants, which
do ship. The tokens are **derived** from those constants rather than restated, so the test cannot drift either.

**Why it matters beyond tidiness** — an agent competes against the published rule. If the published rule
disagrees with the rule the harness scores by, the agent is judged against a threshold it was never told, and
the scorecard is not measuring what it claims to measure.

---

## D54 — Traceability must be bidirectional ✅

**Fork:** The traceability map asserted that every mapped criterion resolves to a real test. It never asserted
the converse.

**So it had already fallen behind.** 28 test methods were unmapped, including all five cross-artifact tests
added with D47/D48 — and a criterion added to the spec with no map entry was equally invisible. The map is a
hand-authored parallel copy of the spec's criteria list, which is the exact pattern the 0.10.3 sweep condemned
when it found the hand-written subject index wrong in six of nine rows and replaced it with a generated one.
That lesson had not been carried across.

**Decision ✅** — two further assertions:
- **test → map:** every test method is mapped to a criterion or listed in an explicit exempt set. Exempt is for
  positive controls, self-verifications of another guard, and internal invariants; listing one is a deliberate
  act, which is the point.
- **spec → map:** the count of `[P1]` criteria is checksummed, in the tradition the 0.10.2 sweep established
  when a SHALL count caught nine silently duplicated requirements. Adding a criterion fails the test until the
  entry and the count are both updated.

**Not the ideal fix, and recorded as such.** Deriving the map from the spec text would remove the parallel list
altogether. The checksum only forces a human to notice; it does not prove the new entry covers the new
criterion. That remains open.

---

## D55 — The scoring micro-semantics are stated, not merely implemented ✅

**Fork:** Three matching behaviours existed only in `scoring.py`. Each was a judgment call made while
building, none was written down, and the payload schema is the port that external agents bind to — so an
agent author could only discover them by reading the scorer, which is precisely what a published contract is
supposed to make unnecessary.

**A correction to the sweep's own first pass.** Five micro-semantics were originally listed as undocumented.
Checking properly — against the spec with line-wrapping collapsed, because a phrase grep on a wrapped
document silently under-reports — showed two were already stated: the tie-break orders by a canonical
serialization of each **whole** finding (which covers confidence and reasoning, the point D26 argued), and the
false-positive denominator is the dataset's invoice count. Only three were genuinely absent.

**Decision ✅** — state all three as requirements:
1. **`MATCH` is ineligible to satisfy an expectation**, not only ineligible to be a flag. D13 settled that a
   `MATCH` is never a false positive; it never said what happens when one lands on a line that *does* carry an
   expected discrepancy. The entry asserts the opposite of the finding, so it cannot be a true positive; the
   expectation stays a miss, and the entry is still not a flag — the single wrong assertion counted exactly
   once, which is the property D13 was protecting.
2. **A finding whose target is absent from the dataset is excluded from matching altogether**, rather than
   being allowed to consume an expectation.
3. **Surplus flags on a key holding no expectation are ordinary false positives, never duplicate contention.**
   Contention means contending *for an expectation*; counting unexpected duplicates there would inflate the
   very diagnostic that exists to reveal an agent emitting duplicates against real findings.

**An honest note on (2).** Since D50 now rejects any expected finding naming an absent target, every
expectation names a real line — so a bogus-target flag could not have matched one anyway, and the exclusion is
**defensive rather than load-bearing**. Its one observable effect is the label: the flag is reported as
referencing a non-existent target instead of as an ordinary non-match. Recorded as a stated invariant so a
future refactor cannot quietly drop it and change that label.

---

## D56 — Exactly one correspondence entry per invoice line ✅

**Fork:** D48 required every invoice line to have a correspondence entry. Nothing constrained how *many*.

**Demonstrated ambiguity.** Two rows mapping one invoice line to two different purchase-order lines were
accepted, and so were exact duplicates. The key audit walks **every** row, so it derives from both mappings and
unions the results — admitting a finding that only one mapping justifies, with nothing deciding which
purchase-order line governs the price and quantity comparison. That is not a stylistic issue: it makes the
derived truth depend on which rows happen to exist rather than on the data.

**Decision ✅** — exactly one entry per invoice line, exact duplicates included, rejected at load naming the
conflicting mappings. A positive control asserts the rule does not over-fire on the shipped datasets.

---

## D57 — Dataset coverage is asserted, and phase-scoped shape gets a tripwire ✅

**Fork:** The dev split's coverage — all five categories, both directions of the materiality boundary on both
basis kinds, a control with no expectations — was a property of how the data happened to be authored, asserted
nowhere. And the single-purchase-order shape of every shipped invoice was a phase-scoped assumption.

**Why coverage needs asserting.** A dataset that quietly stopped exercising a category would leave that
category's precision and recall permanently `null`, and every scorecard would still look healthy — the same
shape of silent failure as a wrong key. Both boundary *directions* matter for the same reason a
rejection-only test is insufficient: a dataset of flagging cases alone cannot distinguish a correct threshold
from one that flags everything.

**Options considered for the phase-scoped shape**
- **(A) A `profile` field in the manifest**, declaring the shape and enforced at load — the approach this
  sweep originally proposed. **Rejected:** D47 already deliberately *allows* equal-rate multi-purchase-order
  invoices, so "one PO per invoice" is not a rule the harness wants; and D47's existing test already fails the
  moment multi-PO data arrives, which is the tripwire a profile would duplicate. Adding manifest schema for a
  property that is already guarded, and partly contradicted, is machinery for its own sake.
- **(B) Record the property as phase-scoped and name its tripwire.**

**Decision ✅** — **(B).** Coverage invariants become requirements with tests. The single-PO shape is recorded
as a phase-scoped property whose named tripwire is D47's existing assertion — which fails when `[P3]` authors
its first multi-PO invoice and thereby *forces* the deferred apportionment to be implemented rather than
guessed. The general rule: **a property that holds only for the current phase is enforced by a named tripwire,
never assumed.**

---

## D58 — Every dataset records the generator source that made it ✅

**Fork:** The generator lives out of tree and agent-denied (D14, D17). Nothing inside the repository could
notice that a domain rule in `gen_rules.py` changed and the datasets were never regenerated. How is that
detected?

**Why this is the worst failure class the project has.** A stale dataset fails no existing check. The key is
self-consistent, the invoice index matches it, all four fingerprints verify, the audit command agrees — because
the audit re-derives from the *inputs*, and the inputs are stale in exactly the same way the key is. Every
mechanical signal stays green while the whole dataset describes rules that no longer exist. The scorecard is not
wrong-looking; it is confidently wrong. Compare D50's principle that a check which misdiagnoses is worse than
one that stays silent: this was worse still — a check that *affirms*.

The cost of fixing also rises with deferral, which is why it went first. The fix requires regenerating every
split. At `[P1]` that is four tiny datasets and one command. At `[P3]`, with roughly 75 hand-audited invoices,
regeneration is an event with its own risk, and the temptation to skip it is exactly when the detector is most
needed.

**Options considered**
- **(A) Version the generator by hand** — a `generator_version` field bumped when rules change. **Rejected:**
  it detects only the changes someone remembered to declare, and the failure mode is forgetting. A detector that
  depends on the discipline whose absence it detects is not a detector.
- **(B) Copy the generator into the repository** so the tests can diff it. **Rejected:** it publishes the rules
  the held-out split depends on, which is the entire isolation architecture (D14, D17). Never.
- **(C) Re-derive the datasets in a test and compare** — the strongest possible check, and unavailable: the
  generator is out of tree, so the comparison could not run from a clone, and D14 requires the suite to pass
  there.
- **(D) Stamp a digest of the generator's source into every manifest, and verify it when the generator is
  reachable.**

**Decision ✅** — **(D).** Each manifest carries `generator_sha256`. Verification splits in two: every shipped
dataset must *carry* a stamp and all splits must agree on it (needs no generator, so it runs in CI), and the
stamp must *match* the generator's current source (skips cleanly when the generator is absent).

**Why each part is shaped the way it is**

- **The skip is load-bearing, not a concession.** A check that failed without the secret side would make the
  suite red on every clone, and a suite that is always red is a suite nobody reads. D14 already settled that the
  held-out split cannot be exercised in CI; this is the same constraint, so it gets the same answer. An
  explicitly-set `GOLDSET_TRIAD_GENERATOR_DIR` that does not resolve is the exception — that is a
  misconfiguration, and reporting "skipped" to someone who believes the check ran is the failure this whole
  decision is about, so it fails.
- **All splits must share one stamp.** One generator run emits every split. Disagreement means a partial
  regeneration — some current, some stale — and no per-dataset check would notice the mixture.
- **The digest is computed by the shipped helper, imported by the generator.** This is the one place the
  generator deliberately borrows harness code, and it is not a breach of D35. D35 keeps the *domain rules*
  independent so the audit can genuinely disagree with the key. A digest has nothing to disagree about: two
  implementations of it could only drift, and drift is the exact condition this stamp exists to catch.
- **Bytecode is excluded and paths are normalized**, for the same reasons as the aggregate inputs digest (D27) —
  a `.pyc` name carries an interpreter version, so including it would report every machine as stale, which is
  the false-positive twin of the failure being prevented.
- **The stamp lives in the manifest, outside `inputs_dir`.** So it does not enter the inputs digest, and
  re-stamping cannot invalidate a scorecard already emitted. Verified: adding it changed the three dev manifests
  and nothing else.
- **The loader treats it as optional; a test requires it.** Provenance is not a scoring input — a dataset with
  no stamp still scores correctly, it merely cannot be checked. Making the loader refuse it would turn a missing
  stamp into an inability to score, which is a worse outcome than the one being prevented.

**The digest must be shown to move.** A stamp that never changes detects nothing while looking like a
detector — the same trap as a rejection-only test. So the check is proven on a copy: editing a generator source
must move the digest, and adding bytecode must not.

**Rule** — **any artifact authored by an out-of-tree tool records a digest of that tool's source.** Isolation
means the repository cannot see the authority its data derives from; a stamp is how the repository regains the
ability to notice that the authority moved.

---

## D59 — Every advertised command exists, and every command knows what it inspects ✅

**Fork:** `audit_key`'s own `--help` introduced itself as `goldset-triad-audit-key`, and `pyproject.toml`
declared only `goldset-triad`. Following the tool's own instructions produced command-not-found. The isolation
check had no console script either.

**Why it stayed invisible.** Every test and every manual run invoked these as
`python -m goldset_triad.<module>`, which works whether or not an entry point is declared. Nothing ever
exercised the advertised path — the `prog=` string was a claim no check read. This is the same shape as the
staleness gap in D58: not a wrong answer, but a claim nothing was comparing against reality.

**Decision ✅** — declare all three console scripts, and add three checks that run in opposite directions:
module → declaration (a `main` must be reachable as a command), declaration → module (a declared command must
resolve to a real callable, so a manifest typo fails here rather than for a user), and advertised name →
declaration (whatever a parser calls itself must exist). The third is the regression test for the actual defect;
the first alone would have passed a package that declared some *other* name for `audit_key`.

**What the fix exposed.** Two things that were harmless while these ran only as `python -m ...`:

1. **`check_isolation.main` accepted `argv` and ignored it**, so the newly-advertised command treated `--help`
   as a request to run the check and swallowed typos silently. It now parses — parsing nothing is still parsing,
   because it rejects a mistake instead of ignoring it.
2. **The repository root came solely from `__file__`.** Installed, that resolves into `site-packages`, and the
   command announced *"guard settings not found … the deny-guards are unconfigured"* — reporting an isolation
   failure when the truth was that it had been handed nowhere to look. Verified in a throwaway venv before the
   fix. This is exactly D50's rule, and in the alarming direction: it named a failure that had not occurred, in
   the one area of this project where a false alarm costs the most trust.

   The root is now explicit: `--repo-root` if given, else this package's own checkout, else the current
   directory if that is one, else an error stating *nothing has been checked*. The discriminator for "is this a
   checkout" is deliberately `pyproject.toml` plus `src/goldset_triad` and **not** `.claude/settings.json` — a
   missing settings file is a genuine failure this tool must report, so using its absence to decide where to
   look would convert that failure into a silent redirect.

**Verified in a venv, not by inspection.** All three commands install and respond; `--help` prints; a typo exits
2; the no-checkout case reports that nothing was checked; `--repo-root` is honoured.

**Rule** — **anything a tool says about itself is a claim, and every claim gets a check.** A `prog=` name, a
usage string, a documented flag: if nothing compares it to what the package actually provides, it will drift,
and it will drift into the reader's hands rather than into a failing test.

---

## D60 — The scorecard states what the dataset could not measure ✅

**Fork:** Per-category metrics are emitted for all five categories on every run. The held-out split at `[P1]`
holds **1 invoice, 2 expected findings, 2 of 5 categories**, so three categories come back with zero counts and
`null` precision and recall. D25 fixed `null` as the representation of "undefined", which is right — but a
`null` on a category the agent was never asked about is indistinguishable from a `null` on a category it handled
flawlessly, and a row of zeros reads as a clean sheet.

**Why this is a credibility problem, not a cosmetic one.** This harness exists to be *shown* — its whole claim is
that it measures honestly. A scorecard whose most flattering reading is also its most natural reading undermines
that claim, and it does so specifically on the held-out split, the one whose results carry weight. Compare D25's
own reasoning for choosing `null` over zero: *zero reads as failure where the result was in fact perfect*. This
is the mirror image — **null reads as perfect where the result is in fact unknown** — and D25 solved only the
first half.

**Nothing needed computing.** Every expectation is either matched or missed, so `tp + fn` already *was* the
number of expectations the key holds in a category. The information was in the scorecard all along; what was
missing was the willingness to state it. That is worth naming as a category of defect: the data present, the
inference available, and the reader left to perform it.

**Options considered**
- **(A) Suppress unexercised categories from the scorecard.** **Rejected:** it makes the omission invisible
  rather than explicit, and a consumer diffing two scorecards would see a category appear and disappear. A stable
  set of keys is worth more than a tidy one.
- **(B) A separate coverage report alongside the scorecard.** **Rejected:** the scorecard is the durable record
  (D9); a caveat that travels in a different file is a caveat that gets separated from the number it qualifies.
- **(C) State coverage inside the scorecard, in both the JSON and the summary.**

**Decision ✅** — **(C).** A `coverage` block in the **scored body** — deterministic, since it derives from the
key — naming the categories exercised, those not exercised, the total expectation count, and whether the dataset
measures recall at all. Per-category rows gain `expected_count` and `exercised_by_dataset`. The summary marks
each unexercised row inline and states the consequence in words: *their null metrics mean the data lacks these
cases, NOT that the agent handled them correctly.*

**The zero-defect control gets the same treatment, and needs it most.** It declares no expectations by design
(D57), so every category is unexercised and every recall is undefined by construction. Unstated, the control
presents as an agent that recalled nothing — the exact inversion of what it proves. It now says so.

**Two things this exposed**

- **The summary printed `None`.** `null` is correct in JSON and is the language's repr leaking into the durable
  human record when interpolated into text. Undefined metrics now render `n/a` for readers while the JSON still
  emits `null`, with a test that the display form does not leak back the other way.
- **The scored body's shape changed**, so `SCORECARD_SCHEMA_VERSION` goes `"1"` → `"2"`. Byte-identity is
  promised between runs on the same inputs, never across schema versions, and a consumer written against `"1"`
  should be told rather than left to discover it.

**On the held-out split's thinness.** Per D57's rule, a property that holds only for the current phase needs a
named tripwire rather than an assumption. Here the honest answer is that **no in-repo test can be that
tripwire** — D14 puts the held-out split beyond CI's reach, and a tripwire that cannot run is worse than none
because it looks like coverage. What is enforceable, and now enforced, is that *any* scorecard the split produces
**self-reports** its thinness. That is a stronger guarantee than a tripwire: it cannot be bypassed by forgetting
to run something, and it travels with the result to whoever reads it. The `[P3]` expansion is what closes the
underlying thinness; until then, every held-out scorecard says out loud that it measures two categories of five.

**Rule** — **a metric that is undefined states WHY it is undefined.** "Undefined" spans "not applicable", "not
attempted" and "not asked", and a reader who cannot tell them apart will pick the flattering one.

---

## D61 — Every text read and write names its encoding and newline ✅

**Fork:** `Path.read_text()` with no `encoding` decodes with the platform default — cp1252 on Windows, UTF-8 on
Linux. Several suites read source and spec files that way to scan them.

**How it surfaced.** It fired during this session. A file mangled by a PowerShell `Get-Content`/`Set-Content`
round-trip acquired a byte cp1252 leaves undefined, and the suite failed with `UnicodeDecodeError` — in a test
that had nothing to do with the file's content. Repairing the file made the failure vanish, which is precisely
what makes this dangerous: the defect is latent until some file acquires a triggering character, and it *fails
only on Windows*. Every em dash and curly quote this project writes freely is a candidate; em dashes happen to
decode cleanly under cp1252 and curly quotes do not, which is the kind of distinction nobody should have to hold
in their head.

The shipped code under `src/` was already clean — every read there names its encoding. The exposure was entirely
in the suite, which is the part that reads *other files as data*.

**Decision ✅** — every text read and write in the repository names `encoding="utf-8"`, and every write pins
`newline="\n"`. A guard walks the AST of every module in `src/` and `tests/` and fails on any `read_text`,
`write_text` or text-mode `open` without an explicit encoding — judged by actual keyword arguments rather than by
whether the word appears on the line, and proven to fire on a bare call.

**Why the newline half rides along.** `write_text` without a pinned newline translates `\n` to the platform
ending, which is the fourth appearance of the line-ending class recorded in D49. Fixing one and not the other
would leave the same trap open in the same call sites.

**Rule** — **the platform default is never the intended encoding.** A default that differs between the machine
you develop on and the machine that runs CI is not a default, it is an unstated dependency.

---

## D62 — The audit refuses what the scorer refuses, and by name ✅

**Fork:** `audit()` called `resolve_manifest` and read the artifacts itself, never calling the loader. Every
validator a scoring run applies was therefore skipped on the audit path: reference resolution (D50),
correspondence completeness (D48, D56), one-row-per-line (D56), multi-purchase-order rates (D47), tax-field
presence (D29).

**What this actually cost — and a correction.** This was ranked last of the four post-build review issues on the
grounds that its failure mode was a confusing message rather than a wrong result. **That assessment was wrong**,
and measuring it is what showed so. With the shared front door removed and seven malformations applied to the dev
split, the pre-fix auditor:

- reported **"consistent"** — exit 0 — for **a dropped correspondence row**, **a duplicated correspondence row**,
  and **tax charged against nothing taxable**;
- reported a **key divergence** — exit 1 — for two others, sending a reader to correct the key when the *data*
  was malformed.

So three of seven invalid datasets were *blessed* by the one check that exists to catch a bad key. The mechanism
is the self-consistency trap D48 was written for, now shown to apply to the auditor itself: the auditor walks the
correspondence rows it is given, so a **dropped** row is a line it never examines — it derives nothing there, the
key declares nothing there, and the two agree perfectly. An omission silences the auditor by shrinking what it
looks at. Had this been left for later, the held-out key could have been audited "clean" while carrying exactly
the defect the audit exists to find.

**Decision ✅** — `audit()` calls `load_dataset` first, so validity comes through the same front door as a
scoring run, and only then performs its own independent derivation.

**Why this does not weaken D35.** The independence D35 requires is in deriving **findings** by a separate
implementation, which the auditor still does, from its own read of the artifacts — asserted by a test that a
mis-targeted expectation on a structurally valid dataset is still caught. The loader applies no domain rule; it
decides whether the dataset is well-formed at all, and there is no value in two answers to that question. Two
implementations of *validity* would not be a cross-check, only a second place to be wrong.

**Two smaller repairs in the same area**
- `assert isinstance(key, dict)` became a raised `DatasetError`. `python -O` strips asserts, which would have let
  the failure resurface later as an unrelated `TypeError` inside the derivation.
- `main` caught `(DatasetError, KeyError)` and printed a bare `KeyError` as a quoted string with nothing to
  indicate the data was at fault. It now names the malformation and the exception type, catching a listed set of
  data-shape families rather than `Exception` — because catching everything would swallow genuine auditor bugs,
  which must stay loud.

**The parity is one-directional on purpose.** Everything the scorer refuses, the auditor must refuse. The
converse is not asserted: the auditor legitimately rejects things the scorer never examines, because it derives
from inputs the scorer never reads.

**Rule** — **when two commands read the same artifact, they share one definition of "valid" and disagree only
about meaning.** Independence is valuable where two answers can be compared; on admissibility there is nothing
to compare, only a second chance to be silent.

---

## D63 — The generator digest hashes normalized text, not raw bytes ✅

**Fork:** D58's staleness stamp digested the generator's **raw source bytes**. Which representation?

**Demonstrated defect.** Converting the generator's line endings — and proving the result AST-identical to the
original — changed the digest. The staleness check would then report a **stale dataset** when the source was
semantically unchanged. That is a misdiagnosis in the alarming direction, which **D50** and **D59** both hold to
be worse than staying silent.

**Why D27's answer does not transfer.** The inputs digest hashes raw bytes and relies on `.gitattributes` to
stop line endings diverging between machines. The generator lives **outside the repository** (D14, D17), so
git attributes cannot reach it: nothing prevents a transport, restore or cross-platform move from rewriting
those bytes. Raw bytes are right for dataset inputs — they include binary PDFs and are read byte-for-byte by an
agent. For *source*, semantic content is the thing and a line ending is transport.

**Decision ✅** — digest `"\n".join(text.splitlines())` per file. `splitlines()` handles CR, LF and CRLF alike,
so the digest depends on what the source says rather than how a checkout stored it. Verified in both
directions: stable across a line-ending rewrite, and still moves when a materiality constant changes.

**Consequence** — every manifest stamp was reissued under the new definition.

---

## D64 — The two remaining unverified drift paths are closed ✅

**Fork:** Two artifacts declared an authority that nothing enforced.

**(a) The held-out stamp was never compared.** All three staleness checks iterate the *dev* splits, so the
held-out manifest carried a `generator_sha256` that nothing read. That is the split whose numbers carry weight —
the ground on which **D60** added coverage reporting — and a stale held-out key is D58's failure in its most
costly form: confidently wrong scores on the evaluation that matters, with the key self-consistent and all four
fingerprints verifying.

**(b) The stamped guard was never compared to its template.** The template declares itself the source of truth
and instructs *"edit here and re-stamp; never hand-edit the repo copy"* — while the isolation check reads only
the stamped copy. The instruction **was** the enforcement, so editing the template and forgetting to re-stamp
left the repository guarded by older rules with nothing noticing.

**Decision ✅** — both are checked, using D58's established two-halves pattern: run when the secret tier is
present, **skip cleanly when it is absent**, since D14 requires the whole suite to pass from a clone. An
explicit env override that fails to resolve is an error rather than a skip, because reporting "skipped" to
someone who believes the check ran is the same misdiagnosis D50 names. Neither check reads answer-key content:
one reads a digest, the other reads deny rules. The held-out check was proven to fire by mutating a copied
stamp.

---

## D65 — Over-blocking is its own failure class, and now checked ✅

**Fork:** The generator Bash rules were written unanchored — `Bash(*generate.*)`.

**Demonstrated over-block.** That pattern denies `bash regenerate.sh`, `npm run pregenerate.build`,
`echo 'we regenerate. now'` and `git log --grep=generate.py`, because the stem appears **inside ordinary
words** — and *regenerate* is this project's own workflow verb, so the rule obstructs the very task the
generator exists for.

**Why this is not a minor cousin of under-coverage.** An over-broad rule leaks nothing; it obstructs. D14
already recorded that a guard scoped wrongly can break evaluation rather than protect it, and the guard-config
check has asserted since D30 that no rule covers the held-out inputs — but that was the only over-block tested,
as though it were the only one possible. **A guard that obstructs routine work is one people switch off**, which
converts a protection into a nuisance and then into nothing.

**Decision ✅** — anchor every generator pattern on a separator or a space, and have
`check_guard_configuration` reject any bare `*<stem>.` pattern. The stems are derived from the artifact names
already declared, so a new generator file cannot be added in one place and forgotten in the other. Tested in
both directions: the anchored rules still deny every real invocation, and no longer deny the innocent words.

---

## D66 — The scorecard's schema version is a rule, not just a constant ✅

**Fork:** D60 changed the scored body's shape and bumped `SCORECARD_SCHEMA_VERSION` to `"2"`. Nothing required
a scorecard to carry a version, or required the version to move when the shape did.

**Why it becomes load-bearing at `[P2]`.** Verify mode recomputes a stored scorecard and diffs it against what
is on disk. Without a declared shape, a **shape change and a scoring difference are indistinguishable** — verify
would report a schema migration as a scoring discrepancy, which is the misdiagnosis pattern this project keeps
finding, aimed at the one feature whose entire purpose is to say whether a score can be trusted.

**Decision ✅** — the scorecard SHALL carry a schema version, incremented whenever the scored body's shape
changes; and verify mode SHALL report an unrecognised version as its own outcome rather than as a scoring
difference. Recorded now, before `[P2]` is designed, so verify mode is built against a rule instead of
inventing one.

---

## D67 — Every claim is registered against the check that compares it, on every split ✅

**Fork:** Four decisions were the same defect in different clothes: **D58** (the generator declared the rules
the data was authored under; nothing compared them), **D59** (`--help` declared a command name that did not
exist), **D64a** (the held-out manifest carried a stamp nothing read), **D64b** (the guard template declared
itself the source of truth and nothing compared the stamped copy). Four sweeps, one class.

**Why attention cannot fix this.** D59 stated the rule outright — *anything a tool says about itself is a claim,
and every claim gets a check* — and the same commit shipped two unchecked claims. Its author wrote the rule and
broke it within minutes. So the failure is not carelessness; it is that a rule living in prose is applied by
memory, and memory is per-session. Two sessions reviewing each other converge eventually, but one instance at a
time.

**D64a is the sharper lesson: the gap was structural, not attentional.** Every staleness check iterated
`DEV_DATASETS`, so the held-out split sat *outside the loop's universe*. No amount of care inspects a set you did
not enumerate. Re-reading the checks would never have found it; only re-reading the *enumeration* would.

**Options considered**
- **(A) Mine the existing decisions into a checklist.** **Rejected on measurement:** only **5 of 67** entries
  carry an extractable `**Rule**` line, and all five were written in one recent session. The other 62 bury the
  lesson in paragraphs, so "extract the rules" would mean inventing them.
- **(B) Rely on the two-session review.** It works — it produced D63–D66 — but it scales one instance per pass
  and never terminates.
- **(C) A registry of claims, each bound to the check that compares it, plus one enumeration of splits used by
  every split-level check.**

**Decision ✅** — **(C).** `tests/test_claim_coverage.py` holds a `REGISTRY` of (artifact, field, what it
asserts, checks). Two halves:

1. **Discovery** — every claim-shaped field on disk (name containing `sha256`, `digest`, `generator`) must be
   registered. Adding a stamp without registering a check fails. This half needs nobody to remember anything.
2. **Symmetry** — every registered claim is checked on **every split `known_splits()` can see**, held-out
   included. Narrower coverage must state a reason.

`support.known_splits()` becomes the single enumeration for split-level properties, so a dev-only loop is no
longer expressible without saying so. `DEV_DATASETS` stays correct for exercising behaviour on a mutable copy;
the division is stated where both are defined.

**It found three more instances of its own class while being written.** Both `PolicyTests` read
`datasets/dev/matching_policy.json` alone, so the policy published beside `dev-synthetic`, `dev-zero-defect` and
**held-out** was never compared to the shipped rule. All four come from one generator run and are identical
today — an assumption nothing asserted. An agent competes against the policy shipped with the split it is scored
on, so a drifted held-out policy would judge it against a threshold it was never told. Both checks now iterate
`known_splits()`. Also closed: the key's `dataset_version` and `dataset_identifier` were compared to the
manifest's by nothing at all, on any split.

**Proven to fire**, both halves, on copies: planting an unregistered `policy_sha256` fails discovery, and
dropping held-out from the universe while the secret tier is present fails the symmetry premise — D64a's exact
shape, reproduced deliberately and caught.

**Rule** — **a claim gets a registry entry naming its check, and any property of "every split" iterates one
shared enumeration.** Enforced by `test_claim_coverage.py`: discovery fails on an unregistered claim, and
`test_the_held_out_split_is_in_the_universe_when_present` fails if the enumeration silently narrows.

---

## D68 — Each recurring defect class is locked by a scanner, at the moment it reaches zero ✅

**Fork:** Four classes have been found, fixed, and found again: timing waits, absence-becoming-a-number,
unanchored patterns, and correctness that depends on call order. Each fix addressed an instance; the class stayed
open.

**The specimen worth remembering.** A `time.sleep(1.05)` existed to force a distinct run stamp. **D49** removed
its reason by giving scorecards collision-free names — and the sleep survived roughly four further sweeps, *while
the neighbouring test's own docstring criticised it in writing*: "Note this test has NO sleep: an earlier
reproducibility test slept 1.05s to…". The knowledge sat in the repository, in prose, beside the defect, for four
sweeps. **A comment recording a problem is not a mechanism.**

**Decision ✅** — `tests/test_defect_classes.py`, one scanner per class:

- **Timing waits → zero, pinned.** The cheapest moment to lock a class is when it reaches zero, which it did one
  commit ago. Scoring is deterministic and single-threaded, so a sleep is always a symptom: hiding a defect, as
  the 1.05s wait hid the collision D49 fixed, or tolerating a race.
- **Absence becoming a number → justified per site.** Scope is deliberately **numeric defaults only** (8 sites),
  not every container default (24). A missing value that becomes a number enters arithmetic and changes a verdict
  silently — that is what D50 was. A missing value that becomes `""` or `[]` is a structural absence, and the
  loader already rejects the ones that matter loudly (D29, D50, D56). Eight reviewed justifications beat
  twenty-four thin ones; widening later is a decision, not an oversight.
- **Unanchored patterns → checked across every rule list**, not only `deny`, so adding an `allow` or `ask` list
  cannot reopen D65.
- **Order-dependent correctness → asserted.** Two `facts.get(..., (Decimal(0), Decimal(0)))` defaults are
  unreachable only because reference resolution runs first. Verified load-bearing: swapping the calls resurrects
  D50's misdiagnosis. One existing test happened to catch the swap; the dependency is now asserted directly, so
  it is protected on purpose rather than by luck.

**The justification requirement caught its own author.** Two entries were first written as "same as X above"; the
check that a justification exceeds a minimum length rejected both, and they were rewritten to say why.

**Rule** — **when a defect class reaches zero, lock it there in the same change that empties it**, and where a
default or an ordering is deliberate, record why at the site rather than in a comment a later reader must find.
Enforced by `test_defect_classes.py`, which fails on a new sleep, an unjustified numeric default, a bare-stem
pattern in any rule list, or a reordering of the two validators.

---

## D69 — Criterion ids are a numbered set, and now checked like one ✅

**Fork:** Two sessions appended to the acceptance-criteria map concurrently. Both reached for the next four ids,
so **C46, C47, C48 and C49 each named two unrelated criteria** — found live while wiring D67 up.

**Why it survived.** The rule was already stated and already generalized: *any numbered set should be unique and
contiguous, because a duplicate makes every reference ambiguous and a gap usually means an entry was deleted.*
The linter enforces it for decision numbers, phase tags and markdown ordered lists. It never reached these ids,
because they live in a **Python list** rather than in markdown the linter parses. So the rule held in principle
and lapsed in practice, at exactly the boundary of what the existing tool could read — which is the same shape
as D64a: correct rule, wrong universe.

**Decision ✅** — the later-committed entries renumber (never reuse), and `CriteriaNumberingTests` asserts
uniqueness across the C, H and E series plus contiguity of the C numbers, with suffixed ids (`C25a`/`C25b`)
counted once. The check lives beside the list, not in the linter, for the reason the subject-index check lives
beside the index: a second implementation would have to parse Python to find these, and would drift.

**Rule** — **when a rule is generalized to "any X", enumerate the X that exist and confirm the enforcement
reaches each one.** A generalization is only as wide as the places it can actually see. Enforced by
`CriteriaNumberingTests` for this project's fourth numbered set; the other three are enforced by `lint_spec.py`.

---

## D70 — The secret tier's committed state is checked, and only advised about ✅

**Fork:** Every isolation check reads the secret tier's **working tree** — the stamped guard against the template
on disk (D64b), each manifest's digest (D58, D63). Nothing looked at what was *committed*.

**Found by observation, immediately after building D67.** The guard template and the held-out manifest sat
uncommitted while the harness side of the same two decisions (D63, D65) was already pushed. The template is the
**source of truth** that the repository's `.claude/settings.json` is stamped from, so at that moment a disk
failure would have:

- lost D65's anchored rules and D63's re-stamp outright; and
- on restore, left the template *behind* the stamped copy that declares itself derived from it — **inverting
  which artifact is authoritative**, with the harness half already public.

Losing the held-out re-stamp would separately have made every held-out scorecard unverifiable. Closing that
single-disk risk is the entire reason the secret repository exists, so a check that never looks at its history was
watching the wrong thing.

**Committed is not the same as safe**, either: an unpushed commit dies with the disk exactly as an uncommitted edit
does. The check reports both, reading `git status --porcelain -b` so the branch line's `[ahead N]` is visible.

**Options considered**
- **(A) A failing test in the suite.** **Rejected:** it would fire during any normal editing session on the secret
  side. D65 already established that a guard obstructing routine work is one people switch off — and this one would
  obstruct precisely the work it is meant to protect.
- **(B) Advisory output from the isolation command.**

**Decision ✅** — **(B).** `check_secret_tier_durability()` reports uncommitted changes and unpushed commits;
`IsolationResult.durability_warnings` is deliberately excluded from `ok`, so the exit code never changes. An
uncommitted tier is a durability risk, not an isolation breach — nothing has leaked and nothing is mis-guarded, and
reporting it as a failure would make routine editing look like a security finding. It surfaces when isolation is
checked, which is when you are about to rely on the guards. Absent tier or absent git: silent, per D14.

**Proven to fire** against a throwaway git repo via the env override — modified file, untracked file, and clean —
with the exit code staying 0 in every case, and the real tier never touched.

**Rule** — **the artifact you inspect and the artifact that survives are different artifacts; check both.** A tool
that reads a working tree is reporting on state that may exist nowhere else. Enforced by
`SecretTierDurabilityTests`, including that a durability warning never fails the check.

---

## D71 — The held-out tier gets a durability story, and three gaps close ✅

**Fork:** The `## Not checked` list named several gaps. Three had no downside to closing, so they closed; the rest
stay recorded. Plus the held-out inputs tier became a git repository, which changed what was possible.

**(a) The held-out inputs tier is now versioned, and covered.** It was the last tier with no durability story:
losing it is worse than losing the secret tier, because a scorecard embeds an aggregate digest of *exactly those
bytes* (D27) — without the bytes there is nothing left to recompute against, and every held-out result becomes
permanently unverifiable. D70's check now covers both out-of-tree tiers.

Two things the new repository needed before anything was committed:

- **`.gitattributes` pinning `-text`.** The inputs digest hashes raw bytes, so a clone that normalized line
  endings would diverge and every held-out scorecard would fail verification while looking like a harness bug.
  Attributes do not cross repository boundaries, so the harness's own rules could never have reached these files —
  the reasoning has to be repeated per tier, which is worth stating because it is exactly the kind of thing assumed
  to be inherited.
- **A README refusing publication, with the reason.** The matching policy is *deliberately* published (D53), so
  **these inputs plus that policy are enough to derive the answer key** — mechanically, which is precisely what the
  audit command does. A public holdout repository would end the held-out property outright. This tier is the one
  that invites the mistake, because the agent under test *is* allowed to read it: **readable-by-the-agent and
  publishable are different properties**, and only the first applies.

**(b) A rule's named enforcement must exist.** The D67 rule check confirmed an enforcement-shaped *word* was
present and nothing more — `Enforced by test_completely_imaginary_module.py` passed clean. **Demonstrated before
being fixed**, because that is D59's defect (a claim nothing compares) sitting inside the mechanism built to stop
it. Now graded: if *nothing* a rule names exists, that is an error; if some resolve and some do not, a warning,
because the unresolved one is usually a tool in another repository. That distinction was not theoretical — the
first run flagged a rule correctly citing `lint_spec.py`, which lives in the toolkit, not the harness.

**(c) The guard file's shape is asserted.** Anchoring was checked across whatever lists happened to exist and the
coverage rules read `deny`, so a new list would have been half-examined. An `allow` list is the case that matters:
it grants reach in the file whose entire purpose is to withhold it.

**(d) Document identity no longer falls back to the filename.** `raw.get("po_number", po_path.name)` was worse
than it looked: the fallback keeps the `.json`, so a purchase order omitting its `po_number` was registered as
`PO-3001.json`, which no correspondence row can match. The reference check then reported *"names purchase order
PO-3001, which the inputs do not contain"* — pointing a reader at the answer key when the defect was in the input
document. The field is now required, and asserted to match the filename stem, which additionally catches a file
copied and not renamed. Every shipped document across all four splits already satisfied both.

**Two under-isolated tests exposed by this work.** Extending the durability check to a second tier made three tests
fail, because they pinned only the secret override and the real held-out tier leaked into their results. And
routing rules through the new shape helper bypassed the `_deny_rules` seam the suite substitutes, so three guard
tests silently began asserting against the shipped rules rather than their own fixtures — green, and measuring
something else. **Under-isolated tests are indistinguishable from correct ones until the code reaches past what
they pinned.**

**Left recorded, not closed:** the remaining 15 container defaults (15 thin justifications would dilute the 8
reviewed ones), a generator test suite (the audit command already cross-checks its output by independent
derivation — that *is* the check), and `[ahead N]` versus true remote state (closing it needs network, making the
isolation check slow and unreliable).

**Rule** — **a tier is not protected by another tier's configuration**: byte-pinning, ignore rules and durability
each stop at a repository boundary and must be restated per tier. Enforced by `_git_durability` covering both tiers
in `check_isolation.py`, asserted by `test_both_out_of_tree_tiers_are_covered`; the per-tier `.gitattributes` is
verified by `git check-attr` and is judgment beyond that, since no shipped check can read another repository's
attributes.

---

## D72 — CI green on Linux is the gate into `[P2]`, not an item within it ✅

**Fork:** Cross-platform behaviour is asserted **by construction** (`H17`) and has never been observed. Should a
Linux run happen before `[P2]` begins?

**What is actually verified today.** Every specific hazard that motivated the concern has been individually
pinned: shipped output pins LF (D49), every text read names its encoding (D61, AST-guarded), the generator digest
normalizes text so line endings cannot move it (D63), and `git check-attr` confirms `text: unset` on every dataset
input, key and manifest — so a Linux checkout receives identical bytes. That is `H17`'s mechanism corroborated
rather than merely asserted.

**What is not.** Unknown unknowns, and one known asymmetry: the backslash deny-rule variants
(`Bash(*\gen_rules.*)`) can never match on Linux, so the guard is *weaker* there — not broken, since the space and
forward-slash variants still fire.

**Why not simply run it now.** WSL on this machine has Ubuntu registered as **version 1**, which the current
configuration refuses to run; converting needs elevation and probably a reboot, and there is no Docker. A local
Linux run is a setup project, not a quick check, and it buys a single snapshot.

**Decision ✅** — no Linux work before `[P2]`. The GitHub Actions workflow becomes `[P2]`'s **first item and entry
gate**: it must be green on Linux before anything else in `[P2]` is built. CI is already on the `[P2]` list, it is
the cheapest Linux available, and it checks *every* future commit instead of one snapshot. Recorded now so it is a
rule rather than an intention — the distinction this whole run has been about.

**Rule** — **when a claim can only be verified by infrastructure a later phase will build, make that
infrastructure the phase's entry gate.** Deferring the verification is acceptable; building further on the
unverified claim is not. Enforced by the `[P2]` phase entry in the spec naming CI first, and by this decision;
judgment beyond that, since no test can assert the order in which a future phase is built.

---

## D73 — The guard's self-verification was itself case-dependent ✅ (first Linux run)

**Fork:** The first CI run on Linux — the D72 entry gate — failed exactly one test,
identically on Python 3.11 and 3.14. What does the failure mean, and what shape should the
fix take?

**What failed.** `test_the_check_actually_fires_on_a_known_bad_pattern`, the
self-verification of the D44 repository-composition guard. It injects the historical
`*ANSWER_KEY*` ignore pattern through a throwaway excludes file and asserts all three
public dev keys are caught, thereby proving the guard can fire at all. On Linux it caught
**none**: `AssertionError: 0 != 3`.

**Why — established by experiment, not inferred from the message.** `git check-ignore`
casefolds a wildmatch only where `core.ignorecase` is true. Measured directly against the
three shipped keys:

| decoy pattern | `core.ignorecase=true` | `core.ignorecase=false` |
|---|---|---|
| `*ANSWER_KEY*` | all three caught | **nothing caught** |
| `*answer_key*` | all three caught | all three caught |

So the historical pattern reaches `dev_answer_key.json` only on a case-folding checkout.
That is not incidental to the test — **the D38/D42 defect it reproduces was itself only
ever possible on such a filesystem.** `core.ignorecase` is true on Windows, which is
precisely why `ANSWER_KEY*` silently excluded three lowercase public keys there and could
not have done so on Linux. The decoy inherited the original defect's preconditions along
with its shape.

**What was and was not broken, because that distinction is the finding.** The guard is
intact and passed on both platforms: `test_no_shipping_file_is_excluded_by_an_ignore_rule`
reads the real ignore rules against the real files, and case-insensitive matching is a
superset of case-sensitive, so Windows is the strictly stronger platform for it. What was
vacuous on Linux is the **proof that the guard can fire** — and a self-verification that
quietly proves nothing is worse than none, because it presents as coverage. D44 recorded
that principle in the same breath as writing this test ("a guard that cannot fail is worth
nothing"); this is that principle failing on the one axis D44 never ran on.

**The rule that had already been written.** D42: *case must never be load-bearing.* It was
applied to artifact names — it is the entire reason `holdout_answer_key.json` and
`dev_answer_key.json` differ by more than case — and it never reached the probe that proves
the ignore guard works. Correct rule, wrong universe: the same shape as **D64a** (every
staleness check iterated a set that excluded the held-out split) and **D69** (the
numbered-set rule never reached a Python list). Three instances now, each surfaced by a
mechanism the previous one built.

**Options considered**
- **(A) Keep the historical pattern; skip the assertion on a case-sensitive checkout.**
  **Rejected:** a skip states nothing, and it would leave the plumbing proof — the part that
  catches `--no-index` being dropped or the fed paths being mangled, both of which happened
  while D44 was being written — running on one platform only, which is how this arose.
- **(B) Force `core.ignorecase=true` for the probe.** **Rejected:** that setting is git's
  record of what the filesystem actually does and is documented as not to be set by hand.
  Making a test lie about its platform to keep an assertion green is the vacuous pass in a
  new costume.
- **(C) A case-exact decoy for the plumbing proof, plus the historical pattern asserted in
  both directions.**

**Decision ✅** — **(C).** The decoy becomes `*answer_key*`, byte-exact against the shipped
names, so the plumbing proof fires on any filesystem and cannot be satisfied or defeated by
the checkout's manners. The historical `*ANSWER_KEY*` is still probed, and its result is
asserted **in whichever direction this checkout runs**: all three keys where case folds,
none where it does not. `core.ignorecase` is read from the config rather than observed,
because inferring it from whether the uppercase decoy matched would make the assertion
tautological — proving only that git agrees with itself. The platform difference stops
being an unstated assumption one platform happened to satisfy and becomes a fact the suite
states out loud.

**Verified in both directions, not only the one that was red.** Windows checkout
(`core.ignorecase=true`): 190 tests, OK, pyright 0 errors. A throwaway clone with
`core.ignorecase=false` and neither out-of-tree tier reachable — the CI condition
reproduced locally — 190 tests, OK (skipped=8).

**What the gate bought, stated plainly.** This is one test and the fix is small. The finding
is that a mechanism had run on one platform for its entire life while describing itself as
general, and **no amount of re-reading it on Windows could have surfaced that, because on
Windows it works.** D72 argued that CI was worth building before anything else in `[P2]`
rather than alongside it; it returned a defect of the project's recurring class on its first
run, for the price of one push.

**Rule** — **a self-verification must be at least as platform-independent as the guard it
proves.** A decoy chosen to reproduce a historical defect inherits that defect's
preconditions, and where those preconditions are a property of the machine, the proof
silently narrows to machines that have them while still reporting success on them. Enforced
by `test_the_check_actually_fires_on_a_known_bad_pattern` in `tests/test_repo_shipping.py`,
which now asserts a case-exact decoy on every platform and the historical pattern in both
directions.

---

## D74 — Verify mode: named inputs, ranked outcomes, and an honest per-file limit ✅

**Fork:** `[P2]`'s `--verify` recompute mode had four unsettled questions at once — how it
finds what to recompute, how it ranks what it finds, what it compares, and what it can
actually say when the inputs digest moves.

**(a) It cannot locate anything from the scorecard alone.** A scorecard records the dataset
identifier and version and four SHA-256 fingerprints, and **never a path**. D10's phrasing —
*"a `--verify` mode recomputes from those fingerprints"* — is not literally achievable: a
digest confirms identity, it does not find a file.

- **Rejected: record paths in the scorecard.** It collides with D18. `run_metadata` holds
  *exactly* the non-deterministic fields, and a machine-specific absolute path is neither a
  run measurement nor deterministic, so it belongs in neither half — and putting it in the
  scored body would make byte-identity depend on where a checkout lives.
- **Decision ✅** — the dataset and findings artifact are **named again on the command
  line**, and the stored digests are used to *confirm* that what was handed over is what was
  scored. Verify says so in its own `--help`, because a tool that quietly needed more than it
  advertised is D59's defect.

**(b) Outcomes are ranked, and the ranking is the substance.** A difference has several
causes and they are not equally informative. Precedence, highest first:

1. **Unrecognised schema version** (D66) — reported alone, with **nothing else compared**,
   and before the dataset is even loaded. A shape change and a scoring difference are
   indistinguishable once fields are compared.
2. **A fingerprint differs** — the inputs moved. *"You scored different data"* and *"the
   numbers are wrong"* are different findings, and reporting the second when the first is
   true sends a reader to audit arithmetic that was never at fault (D50).
3. **The scored body differs** on identical inputs — the real discrepancy.
4. **Identical.**

The ranking is asserted rather than assumed: scoring a *different* findings artifact makes
causes 2 and 3 both true at once, and a test fixes which one is reported.

**(c) Compared as parsed structures, not re-serialized bytes.** Every difference is named by
its key path — `metrics.per_category.PRICE_VARIANCE.true_positives: stored 99, recomputed 4`
— because *"every halt names its specific cause"* and a byte comparison can only say
*differs*. JSON that parses to the same object **is** the same scorecard: key order is fixed
by the serializer (U4), so a reordering is not a change in what was scored, while a changed
value is, and that is what verify must localize.

**(d) D27's per-file diagnosis has a limit in verify, and it is stated.** D27 stored one
aggregate digest rather than ~75–150 per-file entries in every durable record, and said a
mismatch would be diagnosed by recomputing per-file digests and reporting which files
diverged. **That wording assumed both sides were in hand.** In verify they are not: the
scorecard holds the aggregate alone, so recomputing yields the current set with nothing to
diverge *from*. The phase-1 test that proves per-file localization works compares two
*directories*.

- **Rejected: store per-file digests after all** — overturns D27 on the grounds D27 already
  weighed, and pays the cost in every committed scorecard forever.
- **Rejected: localize against git** — precise for the dev split, but it binds verify to git
  and cannot reach the held-out inputs, which live in a separate repository (D71).
- **Decision ✅** — verify names the aggregate mismatch, prints the current per-file
  digests, and **states plainly that it cannot say which file moved without a reference**,
  naming `--baseline-inputs <dir>` as what would let it. Handed the other side, it delivers
  exactly the diagnosis D27 described. Claiming a localization it cannot perform would be
  the misdiagnosis D50 rules worse than silence; performing it silently worse still.

**Two mechanism gaps this surfaced, one closed and one recorded.**

**Closed — traceability had no `[P2]` checksum.** `EXPECTED_SPEC_P1_CRITERIA` guards `[P1]`
alone, so a `[P2]` criterion could have been added to the spec with no map entry and nothing
would have said so. Not hypothetical: **D66's criterion was missing from the spec for two
versions** while its requirement sat in the `optional feature` block, and `lint_spec.py`'s
"fewer acceptance criteria than SHALL requirements" warning was pointing at exactly it,
unread. The rule was right and its enforcement reached only the phase the mechanism was
written during — D64a, D69 and D73's shape again, now four instances. `EXPECTED_SPEC_P2_CRITERIA`
closes it.

**Recorded, not closed — the claims registry cannot see a scorecard.** D67's discovery half
iterates `known_splits()` across `manifest`, `key`, `index` and `policy`: **split artifacts
on disk.** A scorecard is a *runtime* artifact, never committed, so a claim-shaped field
added to one would not be discovered — and `test_registry_has_no_stale_entries` would reject
a registry entry naming an artifact that exists on no split, so it cannot simply be added.
The substantive requirement is met: the scorecard's fingerprints now have a check, and that
check is verify mode itself. What is missing is the *mechanism's* reach, which is D64a's
shape inside the mechanism built to end D64a's shape. Left recorded because closing it means
widening discovery to a scorecard built in memory rather than read from a split, which is a
change to D67 and deserves its own decision rather than riding along here.

**Verified by execution.** All four outcomes exercised end to end through the CLI and
asserted in the suite: identical exits 0; altered stored numbers report `score-differs`
naming the field; an unrecognised version reports `schema-unrecognised` and the altered
number planted alongside it provably does **not** surface; a changed findings artifact
reports `fingerprint-mismatch` while the body difference it also causes does not. 199 tests,
pyright 0 errors.

**Rule** — **a recompute check names what it was given, ranks what it finds, and states what
it cannot determine.** Each half is a way the same feature lies: pretending to locate inputs
it was never told about, collapsing distinct causes into "it differs", or implying a
diagnosis its stored evidence cannot support. Enforced by `tests/test_verify_mode.py`, whose
precedence and per-file-limit tests fail if any of the three is quietly dropped.

---

## D75 — The run ledger: what it records, where it lives, and what order it is in ✅

**Fork:** D9 settled *what the ledger is* — a derived, local-only, gitignored convenience
view, regenerable from the scorecard directory alone, because scorecards are the durable
record. It did not settle the record's shape, the file's location, its ordering, or what a
run should do when it cannot be written. All four are decided by one constraint and one
surprise.

**The constraint: every field must be recoverable from the directory,** or the regeneration
guarantee is unmeetable. That is what shapes the record rather than "what would be useful
here". One field comes from the *filename* instead of the contents — the D49 collision
ordinal, which exists nowhere else.

**(a) No fingerprints, deliberately.** Copying the scorecard's four digests into the ledger
was considered and rejected. D9 scopes this to a per-machine duration and workload trend;
the scorecard already carries provenance under the byte-identical comparison; and a derived
artifact repeating claim-shaped fields would **manufacture claims that nothing compares**,
which is the shape D67 exists to end — sharpened by D74's finding that the claims registry
cannot even see a runtime artifact, so such fields would sit undiscovered by construction.
Provenance questions are answered by the scorecard and by `verify`.

**(b) The ledger lives in the directory it describes.** A ledger at a fixed path would
outlive its relationship: a run writing to a different output directory would append to a
file describing a directory it no longer reads, while the guarantee is stated against *the
scorecard directory alone*. `.gitignore` already carries a bare `run-ledger.jsonl`, which
matches at any depth, so this needed no ignore-rule change — checked rather than assumed.

**(c) The surprise: run order is not filename order.** Scorecard stems carry the D49
ordinal, and an ordinal is **lexicographic** in a filename. Measured, not reasoned about:

```
sorted() over three runs in one second gives
    scorecard-dev-20260727T050000Z-10.json     <- run 10
    scorecard-dev-20260727T050000Z-2.json      <- run 2
    scorecard-dev-20260727T050000Z.json        <- run 1
```

Appends happen chronologically, so a filename-sorted rebuild would produce a **differently
ordered ledger holding identical records** — and *"regenerating reproduces identical
contents"* would fail on a case nobody would think to test, in the one guarantee that makes
the ledger safe to delete. The sort key is `(run_timestamp, ordinal-as-integer)`. The test
asserts the naive sort really does mis-order first, so it cannot pass by the ordinals
happening not to collide. This is the positional-fragility family the project inherited as a
*pattern to reuse carefully* from the prior work, arriving as an ordering rather than an
index.

Reading the ordinal treats a missing suffix as 1. That is **not** an absence becoming a
number (D68): the writer omits the suffix *exactly when* the ordinal is 1
(`stem if ordinal == 1 else f"{stem}-{ordinal}"`), so this is the inverse of an encoding
rather than a guess about missing data — recorded here because the distinction is invisible
at the call site.

**(d) An unwritable ledger warns and the run exits zero.**

- **Rejected: halt non-zero**, for uniformity with every other failure. It would report a
  valid, correctly-scored run as a failure because a *derived local cache* could not be
  extended — and the scorecard, which is the thing that matters, was already written.
- **Rejected: append best-effort and silently.** An absence nobody is told about is the
  class D68 locked.
- **Decision ✅** — a prominent warning naming the cause, the rebuild command that fixes
  it, and exit zero. This is the same shape as D9's own performance-breach exception, which
  is the one other place in this harness where a warning coexists with success, and it is
  justified by the same reasoning: the condition does not make the score wrong.

**(e) A file that is not a scorecard halts the rebuild, naming it.** It cannot be placed in
run order, and guessing a position would put an invented ordering into the record. Skipping
it silently would be worse still: a directory quietly holding something unaccounted for is
how a "regenerated identically" claim stops meaning anything.

**Verified by execution.** Three runs append three records; deleting the ledger and
rebuilding reproduces the file **byte for byte**, not merely line for line — bytes assert
records, order and serialization at once. 204 tests, pyright 0 errors.

**Rule** — **a derived view records only what its source can regenerate, and states its
order explicitly.** The first half is what keeps "delete it, rebuild it, get the same file"
true; the second is what stops that guarantee resting on a sort nobody examined. Enforced
by `tests/test_run_ledger.py`, whose ordering test asserts the naive sort mis-orders before
asserting the real one does not.

---

## D76 — H17 becomes an observed result, checked on every push ✅

**Fork:** *"The harness SHALL produce identical scorecard content when run on Windows and on
Linux"* is this project's central portability claim, and `H17` carried it as `MANUAL:
platform-independent **by construction**`. D72 built CI so it could stop being that. How is
the comparison actually made?

**Options considered**
- **(A) Run both by hand once and record a dated attestation** in D30's style. Cheapest, and
  the weakest: it buys one snapshot of one commit, and the class of defect being guarded
  against — a platform difference introduced by a later change — is precisely the one a
  snapshot cannot see.
- **(B) Compare the aggregate inputs digest alone**, which is what `H17`'s wording literally
  names. Narrower and cheaper, but it leaves the rest of the scorecard's cross-platform
  identity asserted by construction, which is the condition being escaped.
- **(C) A `windows-latest` leg in CI, with a third job comparing the two scorecards.**

**Decision ✅** — **(C).** Both platforms score the dev split and upload their scorecard; a
comparison job asserts byte-identity. It runs on **every push** rather than once, which is
the same argument D72 made for CI over a local Linux run.

**Four details that decide whether the comparison means anything.**

- **Both halves are compared, not just the JSON.** D49 claims *both* files in the pair carry
  platform-independent bytes. The human summary references no `run_metadata` and is therefore
  wholly deterministic, so comparing only the JSON would half-check a claim while reporting
  it fully checked.
- **One pinned Python version on both legs.** The claim under test is about the *platform*.
  Leaving the interpreter free would confound the two, and a failure could then be either
  with no way to say which.
- **The findings artifact is derived from the shipped key, not committed.** A committed
  fixture is a second copy of the key's content that can drift from it — D46's lesson — and
  deriving it puts the artifact's *own bytes* inside what is compared: if they differed by
  platform, the findings fingerprint in the scored body would differ and the job would say
  so.
- **The comparison reuses the shipped `deterministic_body` and verify's differ** rather than
  reimplementing either. A second implementation of "what two runs must match" could only
  drift from the one that ships, and drift is the condition this job exists to detect (D58).

**A wording defect caught before it shipped.** Reusing verify's differ made the cross-platform
report read *"stored 4, recomputed 5"* — verify's vocabulary, naming the wrong distinction
entirely for a difference between two operating systems. `_differences` now takes the two
side labels, defaulting to verify's own. A message that misidentifies what it compared is the
misdiagnosis D50 ruled worse than silence, and it would have been read by whoever was
debugging the project's most load-bearing claim.

**`H17` stays `MANUAL:` in form, and that is honest rather than a shortfall.** A result
produced by running on two operating systems cannot be produced by a single-platform unit
suite, however it is written. What changed is its *content*: from "platform-independent by
construction" to an observed comparison naming the job that performs it. The workflow's
**configuration** is separately checked by `tests/test_ci_workflow.py`, because the spec
makes claims about what CI does and D67 requires every claim to have a check — but that test
deliberately does **not** carry the cross-platform criterion, since it shows the comparison
is configured and not that it passed. Binding a result to a configuration check is D30's
rejected reachability probe in new clothes.

**The manual ceiling moves 5 → 6, deliberately.** A ceiling nudged upward whenever it binds
is not a ceiling, so the raise is recorded with its reason. The sixth entry is `C74`, and
every one of the six is generation-side, environment-level, or this same cross-platform
observation. **None of the six is a criterion that could have been automated in the suite
and was not.**

**Rule** — **a claim asserted by construction is not verified until something observes the
result, and the thing that observes it should run more than once.** Corroborating every
hazard individually is what makes a claim plausible; a run is what makes it true, and a run
that happens on every commit is what keeps it true. Enforced by the `cross-platform` job in
`.github/workflows/ci.yml` and by `tests/test_ci_workflow.py`, which fails if that job stops
naming two platforms.

---

## D77 — A pinned encoding needs a named failure, and five readers had none ✅

**Fork:** Every module that loaded JSON had grown its own read-parse-validate sequence, and
each guarded a different subset of the ways a read can fail. `dataset` checked existence and
`OSError`; `cli` dropped the `OSError`; `ledger` dropped the existence check as well;
`audit_key` and `check_isolation` guarded nothing. A caller could not know which protections
applied without reading the callee, and the protections were nobody's subject, which is the
condition under which copies drift.

**The defect all five shared.** D61 required every text read to state its encoding, and every
one of them did. Nothing said what happens when the stated encoding does not apply.
`UnicodeDecodeError` is a `ValueError`, not an `OSError` — so `dataset`'s deliberate
`except OSError`, placed *directly around a pinned-encoding read for exactly this class of
problem*, caught the file being unreadable and missed the file not being text. Measured, on
five paths:

```
score --findings <a PDF>          UNCAUGHT UnicodeDecodeError   (traceback, exit 1)
verify --scorecard <a zip>        UNCAUGHT UnicodeDecodeError
answer key / manifest / index     UNCAUGHT UnicodeDecodeError
rebuild-ledger --ledger <no dir>  UNCAUGHT FileNotFoundError
```

Each is an ordinary operator error — a wrong path — reported as a defect in the harness, in
a project whose failure policy is that **every halt names its specific cause and exits
non-zero**. It also means acceptance criterion **E10** ("an unreadable answer key halts")
was only ever covered for the *absent* case: its test deletes the file.

**Options considered**
- **Rejected: add `except UnicodeDecodeError` at each of the ten read sites.** It closes
  today's instances and leaves the eleventh site free to omit it, which is how the five came
  to disagree. The rule would still be enforced by whoever remembers it (D67's argument).
- **Rejected: catch `Exception` in `cli.main`.** One blanket rescue would stop the traceback
  and produce exactly the generic message the observability requirement forbids, converting a
  named failure class into "something went wrong".
- **Decision ✅** — one reader, `jsonio.read_text_file` / `read_json_file` /
  `read_json_object`, used by all five modules, naming **absent**, **unopenable** and
  **undecodable** as three separate causes, each carrying the artifact's *role* rather than
  only its path. `parse_float=Decimal` is pinned there too, so no caller can forget it and
  let a monetary value become a float (D3). `DatasetError` moved with it: five modules raise
  it and it was never specific to a dataset. Two redundant presence checks went with the
  change — one of them reported an *absent* answer key as `"unreadable"`, conflating the
  wrong path with the unopenable file, which is the same conflation in miniature.

**And the findings artifact had two loaders.** `cli.run_score` and `verify._recompute` each
held a four-line copy. That is the drift surface D58's reasoning condemns, sitting at the
worst place in the project for it: **verify's entire premise is that it reproduces what
scoring did.** A rejection added to one copy and not the other would make verify compare a
scorecard against a recomputation whose inputs it had validated on different terms — and
report the disagreement as a scoring difference. Now `dataset.load_findings_artifact`, once.

**Verified by execution.** All five paths halt at exit 2 naming the artifact and the byte
offset; the three causes are asserted distinct. 232 tests, pyright 0 errors.

**Rule** — **pinning a behaviour is half a decision; the other half is naming what happens
when the pinned thing fails.** D61 pinned encodings and stopped there, so the project spent
five modules and two phases with a failure mode it had explicitly thought about and not
handled. Enforced by `tests/test_read_failures.py`, whose lock asserts that **exactly one
function in the package reads text** — asserting today's call sites is a snapshot, asserting
that a sixth reader cannot arrive is the class staying closed.

---

## D78 — A gate must not coerce what it then reports ✅

**Fork:** Two modules normalised a value in order to *make a decision*, and then let the
un-normalised value flow onward into a *report*. Both produced the exact misdiagnosis their
own decision record forbids. They were found independently and are one defect.

**(a) `verify`: `str(stored["schema_version"])`.** The coercion made the gate accept a
scorecard carrying the int `2` as though it carried `"2"`. The raw value then reached the
body comparison below and surfaced as:

```
outcome: score-differs
  the same inputs recompute to a different score, so the stored scorecard does not
  report what it claims to report:
  schema_version: stored 2, recomputed '2'
```

A **shape** defect reported as a **scoring** difference — which is, word for word, what D66
recorded this feature to prevent, aimed at the one feature whose entire purpose is to say
whether a score can be trusted. The criterion existed (E13), the test existed, and both
tested the *value* case while a `str()` three lines above defeated them on the *type* case.

**(b) `schema`: `raw.get("schema_version", SCHEMA_VERSION)`.** Two defects in one line. An
artifact declaring nothing was read as declaring the current version — absence becoming
precisely the value that makes the artifact acceptable — so `{"findings": []}` **scored and
exited zero**. And the comparison never checked the type, so `{"schema_version": 1}` was
rejected with `unsupported schema_version '1'; this harness scores v1`, a message that reads
as a contradiction because an int and a str render identically inside quotes.

**The two are opposite answers to one question.** Verify decided, deliberately and in
writing, that a scorecard with no declared version is *unrecognised*, because absence is not
a version. The findings port decided that absence is the current version. One module apart,
in the same codebase, with no note that the question had been answered twice.

**Options considered**
- **Rejected: keep the default and record a justification.** D68's scanner is the mechanism
  for that, and it could not see this site — its universe is *numeric* defaults and this
  default is a string (D82). Justifying it would have documented the leniency without
  reconciling it with verify's opposite ruling.
- **Rejected: coerce consistently — `str()` at the gate and carry the coerced value into the
  comparison.** It would silence the misdiagnosis, and it would also mean a scorecard that is
  not the shape this harness emits verifies clean. Leniency about a declaration is exactly
  what a version declaration is for.
- **Decision ✅** — neither gate coerces. A wrong-typed declaration is rejected naming the
  type it found; an absent one is rejected naming the field; a correctly-typed unsupported
  version keeps its own message. `verify` reports both the absent and the wrong-typed case as
  `schema-unrecognised`, its own outcome, comparing nothing.

**Verified by execution.** `{"schema_version": 2}` now reports `schema-unrecognised` and no
longer surfaces as a scoring difference; `{"findings": []}` halts at exit 2 naming the field.
232 tests, pyright 0 errors.

**Rule** — **a gate either rejects a value or normalises it and carries the normalised value
forward; it must never normalise for the decision and report the original.** Both instances
here were leniencies nobody asked for, and both turned a malformed artifact into a false
report about a well-formed one. Enforced by
`tests/test_port_schema.SchemaVersionDeclarationTests` and
`tests/test_verify_mode.VerifyModeTests.test_a_wrong_typed_schema_version_is_unrecognised_not_a_scoring_difference`.

---

## D79 — Verify names what it was pointed at, and bounds what it prints ✅

**Fork:** D74 got verify's outcome *ranking* right and left three gaps in what the report
actually says. Each is the same failure at a different scale: the report describes something
other than what happened.

**(a) It never checked it was looking at the right dataset.** A scorecard records the dataset
identifier and version, and verify holds both before it compares a single digest. Pointing it
at the wrong split — the likeliest operator error on a command taking three separate paths —
produced three digest mismatches *and* a paragraph advising the reader to obtain a pristine
inputs directory and re-run with `--baseline-inputs`, sending them to hunt a file that never
moved. The one-line answer was in hand the whole time, which is what makes it the
misdiagnosis D50 rules worse than silence rather than merely a thin report.

- **Rejected: fold it into the fingerprint outcome.** "The answer key digest differs" is true
  when you name the wrong split, and useless: it is true *because* you named the wrong split.
- **Decision ✅** — a new outcome, `dataset-mismatch`, ranked **above** fingerprints and below
  schema. It names the stored identifier and the resolved one and compares nothing further.

**(b) An absent fingerprint was reported as a value.** `stored_fingerprints.get(field)`
returned `None` for a missing digest, and the report read *"the scorecard records None, the
artifact on disk digests to '9f3…'"* — a scorecard described as holding a value it does not
hold. The fingerprints **block** was shape-checked; its **members** were not. A scorecard
that omits a digest is malformed; a scorecard whose digest disagrees with disk is evidence.
`.get()` collapsed the first into the second.

- **Decision ✅** — `_required_field` throughout, never `.get()`. An absent field raises
  naming the field and the shape it claims, and exits 2: a verification that could not
  happen, not one that failed.

**(c) One of the four cause lists was unbounded.** `MAX_REPORTED` capped the score-difference
list and the no-baseline per-file listing; the *with-baseline* divergence list had no cap.
Measured at 15 lines against a cap of 10 on the four-file dev split — on the held-out split's
75–150 inputs it is one line per file, which is the diff dump this module's own docstring
promises never to produce, in the branch a reader reaches only when something is already
wrong.

- **Decision ✅** — one `_bounded` helper at every site. The **count is still stated in
  full** (`"31 file(s) diverge …"`) and only the enumeration is capped: bounding what is
  printed must not bound what is reported, or the cap becomes its own quiet omission.

**Verified by execution.** Naming a different split now reports `dataset-mismatch` with no
digest noise and no `--baseline-inputs` advice; a scorecard missing `answer_key_sha256` halts
at exit 2 with no `None` in the message; a whole-tree divergence prints ten lines and a
remainder count. 232 tests, pyright 0 errors.

**Rule** — **a diagnostic tool is only as good as the thing it names, so it must name the
most upstream cause it can already see, never describe an absence as a value, and never
answer a question with a dump.** All three failures here were the report drifting away from
what the code actually knew. Enforced by `tests/test_verify_mode.py`.

---

## D80 — The ledger's run order was not a total order ✅

**Fork:** D75 identified that filename order is not run order — the D49 ordinal sorts
lexicographically, so a naive sort yields run 10, run 2, run 1 — and fixed it with the sort
key `(stamp, ordinal)`. That key is not total, and D75 did not notice because its test uses
one dataset identifier.

**The measurement.** Three splits scored into one directory inside one second:

```
scorecard-dev-20260727T050000Z.json               ordinal 1
scorecard-dev-synthetic-20260727T050000Z.json     ordinal 1
scorecard-dev-zero-defect-20260727T050000Z.json   ordinal 1
distinct sort keys: 1 of 3
```

The ordinal was reserved **per stem**, and a stem carries the identifier — so filenames were
unique, which is all D49 asked for, while the sort key tied. Python's sort is stable, so
order then fell through to `Path.glob` order: `os.scandir` order, **name-ordered on NTFS and
hash-ordered on ext4**. Appends happen chronologically. So a rebuild could reorder on Linux
and hold on Windows, and *"delete the ledger, rebuild it, get the same file"* — the `[P2]`
criterion C72, the guarantee that makes the ledger safe to delete — would fail on a platform
nobody had run it on. That is the worst shape a portability defect can take, and it is the
same shape D73 was.

**Options considered**
- **Rejected: add the filename as a final tie-break.** It makes the key total and *not*
  chronological, so the rebuild would produce a stable order that is not the append order —
  C72 would still fail, now deterministically.
- **Rejected: detect the tie and state the limit** in D74's honest-account style. Honest, and
  it leaves the project's own guarantee conditionally false when the condition is "score two
  splits in a shell loop".
- **Decision ✅** — the ordinal is reserved across the whole **directory-second** rather than
  per stem, so it means *the nth run in this directory in this second*, which is what a run
  order needs it to mean. The three splits above now take ordinals 1, 2, 3; the key is total
  **and** chronological; appended and rebuilt ledgers are byte-identical. A residual tie can
  still be constructed by hand-placing files, so it **halts naming both files**: an order the
  ledger cannot justify is not an order.

**Two smaller things in the same module.** `_stamp_of` and `_ordinal_of` each re-ran the same
regex and raised a different message for the identical failure — and which one a reader saw
depended on the order Python evaluated a sort-key tuple, so the more helpful of the two, the
one naming the expected filename shape, was **unreachable from every path that existed**. One
`parse_scorecard_name` now. And `_require` checked *presence* and called that validation, so
`"run_timestamp": null` passed straight into the ledger — the field the whole run order rests
on. Nullability is now declared per field, because three ratios genuinely may be null: D40
emits an undefined metric as `null` rather than as zero, so a null precision is a value
meaning "undefined on this split", while a null timestamp is not a value at all.

**Verified by execution.** Ordinals 1, 2, 3 across three identifiers in one fixed second;
append equals rebuild byte-for-byte; a hand-placed duplicate halts naming both files. The
ordering test drives the reservation **directly with a fixed stamp** rather than scoring
three splits and hoping they land inside one second — that would be a timing dependency
wearing a different hat, the class C62 locked, and it would skip on a slow machine, which is
when it most needs to run. 232 tests, pyright 0 errors.

**Rule** — **a derived view must state its order, and the order must be a total one; a sort
key that ties hands the tie to the filesystem.** D75 stated the order and got it half right,
and the half it missed was invisible on the machine it was written on. Enforced by
`tests/test_run_ledger.py`.

---

## D81 — A decision whose substance is a message is not tested until the message is ✅

**Fork:** Six checks across the ledger and the CI workflow asserted something weaker than
what they claimed, and in every case the untested half was the **output**: the warning text,
the error path, the thing a human reads. The project is consistently strong at deciding and
weaker at exposing, and this is that pattern with names attached.

**What was measured**

| Where | What it claimed | What it checked |
|---|---|---|
| `test_an_unwritable_ledger_warns…` | D75's warn-and-continue | exit code and a scorecard — both true of a **silent** failure |
| `assertIn("on:", text)` | the push trigger exists | matched `runs-on:`, `python-version:`, `node-version:` — 8 lines, none the trigger |
| `assertIn("ubuntu-latest", text)` | the matrix names two platforms | `ubuntu-latest` is on three other `runs-on:` lines, so narrowing to Windows passes |
| `assertNotIn("npx --yes pyright\n")` | pyright is version-pinned | a bare `npx pyright` sails past |
| the `git check-attr` step | *"anything but `text: unset` means the platforms hold different bytes"* | printed a `uniq -c` summary; **could not fail** |
| `if [ "$ran" -lt 150 ]` | discovery has not collapsed | a floor of 150 against a suite of 207 — 57 tests could vanish |

The ledger row is the sharpest. D75 chose "warn and continue" over "fail silently" **on the
explicit grounds that an absence nobody is told about is a locked defect class (D68)** — and
then nothing checked that anybody was told.

**Options considered**
- **Rejected for the test count: raise the floor to 200.** A looser literal is the same
  parallel list D54 condemned, one sweep further from drifting.
- **Decision ✅** — assert the messages, anchor the patterns, make the observation step
  fail, and derive the count. The suite floor becomes `ran == len(all_test_methods())`,
  asked of the traceability map, which already enumerates every test method under a check
  that fails when the enumeration falls behind. One list, one owner. The pyright pin is
  asserted **positively** (`npx --yes pyright@\d+\.\d+\.\d+`) rather than by excluding one
  spelling of the defect, and the platform matrix is read **off the `os:` entry** rather than
  searched for in the file.

**Verified by execution.** Both new CI steps were run locally against this checkout before
being committed: `check-attr` reports `unset` across 31 dataset artifacts and would exit 1 on
anything else; the derived count reports 232 and matches what the suite runs. 232 tests,
pyright 0 errors.

**Rule** — **if a decision's substance is a message, the test asserts the message; if a step
exists to observe something, it must be able to fail.** An observation nobody is required to
read is not a check, which is the distinction D30 drew about the reachability probe, arriving
here as a `uniq -c` in a green log. Enforced by `tests/test_ci_workflow.py`, which now checks
that the workflow's own checks can fire.

---

## D82 — Every lock declares the universe it scans, and asserts it ✅

**Fork:** *Correct rule, wrong universe* is this project's most-repeated defect. D64a, D69,
D73 and D74 are each an instance, and each was closed individually. This sweep found four
more — one of them **inside the mechanism built to end the class** — which says the
individual closures are not converging and the shape itself needs a rule.

**The four**

1. **The absence-default scanner.** `NUMERIC_DEFAULTS` scans `X.get(k, <numeric>)` and
   `continue`s past everything else. Its scoping comment weighed numeric defaults against
   empty-container defaults and concluded, correctly, that only the first needs individual
   justification. It never considered a third bucket: a **substantive** default, a real value
   standing in for an absent declaration. There was exactly one — `schema.py`'s
   `raw.get("schema_version", SCHEMA_VERSION)` — and it decided whether an artifact declaring
   no version was accepted (D78). The scanner's universe was one bucket while the rule's was
   three, so the instance was not merely unjustified, it was **invisible**.
2. **`test_audit_not_imported_by_any_scoring_module`** iterated a hand-written tuple of six
   module names, written when those were all the modules. `verify`, `ledger` and `jsonio`
   were never in it. It also scanned raw **text**, so it could not tell an import from a
   mention — widening it immediately caught `__init__.py`'s module docstring, which names the
   audit command while describing the separation D35 requires.
3. **`EXEMPT_TESTS`** is a parallel list with no staleness check, so a deleted or renamed test
   leaves its exemption behind forever. The claims registry one file away has
   `test_registry_has_no_stale_entries` for exactly this; the two lists are the same shape and
   only one was guarded.
4. **`_spec_criteria`** matched `^- \[ \] \[{tag}\]` — an **unticked** box, literally. Ticking
   a criterion off would drop the count and fail with *"the spec now has 5 [P2] criteria but
   this map expects 6 … Add the missing entries"*, reporting a satisfied criterion as a
   deleted one. A checklist whose guard breaks when you use it as a checklist.

**Options considered**
- **Rejected: fix the four and move on.** That is what was done for D64a, D69, D73 and D74,
  and the class has now recurred four more times including inside its own mechanism.
- **Rejected: one scanner over everything.** The original scoping was right that 8 reviewed
  justifications beat 24 thin ones. The problem was never the exemption, it was that the
  exemption was unnamed.
- **Decision ✅** — a lock **names its buckets and fails on anything that fits none**. The
  default scanner classifies every two-argument `.get()` into `numeric` (justified
  individually), `empty-container` (justified once, as a bucket) or `substantive` (empty
  registry — the one instance was removed rather than justified), and a census test asserts
  the buckets partition a non-trivial total, so the scan cannot go quiet. The module list is
  discovered from the package and checked over parsed imports. `EXEMPT_TESTS` gets its
  staleness check. The criteria pattern accepts a ticked box.

**Verified by execution.** The classifier was exercised on nine default expressions:
`get(k, SCHEMA_VERSION)` and `get(k, True)` classify as substantive and fail;
`[] {} "" ()` as empty-container; `0` and `Decimal(0)` as numeric. 21 sites classified, 8
numeric, 13 empty-container, 0 substantive. 232 tests, pyright 0 errors.

**Rule** — **a lock must declare the universe it scans and assert that the universe is
covered, because a scanner silently skipping what it does not recognise is indistinguishable
from a scanner finding nothing.** Every instance of this class has the same signature: the
rule generalises and the enforcement stays at the boundary of whatever someone enumerated
once. Enforced by `tests/test_defect_classes.NumericDefaultTests`,
`tests/test_traceability.TraceabilityTests.test_no_exemption_outlives_its_test` and
`tests/test_key_audit.py`.

---

## D83 — A derived view's naming rules may not halt the durable write ✅

**Fork:** D80 fixed a real defect — the ledger's sort key was not total, so three splits
scored in one second tied and run order fell through to `glob` order, name-ordered on NTFS
and hash-ordered on ext4. The fix widened the ordinal reservation from one stem to the whole
directory-second. What should reservation do about a neighbouring file whose name it cannot
parse?

**What it did, measured.** `_reserve_scorecard_paths` parsed every `scorecard-*.json` in the
output directory and let the failure propagate:

```
$ goldset-triad score --dataset dev --findings f.json --out out/
error: scorecard-backup-copy.json does not look like a scorecard emitted by this
harness, so the ledger cannot place it in run order; expected
scorecard-<identifier>-<YYYYMMDDTHHMMSSZ>[-<ordinal>].json
                                                                          exit 2
```

So an unrelated neighbouring file made the harness **refuse to write the durable record** —
and blame *the ledger*, a derived convenience view the caller never invoked, for a `score`
run that had already loaded, validated and scored successfully.

**It crosses a line D75 had already drawn.** D75 decided that an unwritable ledger **warns
and the run exits zero**, in as many words: *"the ledger is a derived, regenerable
convenience view (D9), so an unwritable one cannot make a correct score wrong."* D80 then let
the ledger's **filename grammar** do precisely what D75 ruled the ledger's **file** must never
do. Neither session saw it, because the coupling arrived through a different door: D75 guarded
the append, and this is the reservation. The message is separately the D50 misdiagnosis
class — naming the wrong subsystem and the wrong consequence — which is the very thing D79
had just fixed in verify, one sweep earlier and one module away.

**Options considered**
- **Rejected: keep the halt, fix only the message.** The message is indefensible either way,
  but it is the smaller half. The substantive question is whether a derived view's naming
  rules may block the primary write, and D75 already answered it.
- **Rejected: skip unparseable names everywhere, ledger included.** That is the opposite
  defect. The ledger's whole guarantee is that a rebuild reproduces the append order, and an
  order it cannot justify is not an order — D80's own reasoning, which stands.
- **Decision ✅** — **reservation skips what it cannot parse; the ledger still refuses it.**
  Reservation needs only the ordinals *this harness allocated in that second*; a name that
  does not match the grammar holds none, and it can never equal a generated name, which
  always matches. Collision safety is unaffected: it rests on the `.exists()` pair-check and
  on mode `"x"`, which makes overwriting impossible at the operating-system level (D49). The
  halt stays in `ledger.rebuild_text`, where the order genuinely cannot be justified.

**Verified by execution.** A `score` run beside `scorecard-backup-copy.json` now succeeds and
emits its scorecard; `rebuild_text` on the same directory still halts naming that file. Both
halves are asserted, because passing only the first would be the opposite defect. 233 tests,
pyright 0 errors.

**Rule** — **a derived view may not make the durable write fail, through its file or through
its grammar.** D75 stated the first half and D80 crossed it through the second, which is the
same shape as *correct rule, wrong universe* (D82) with the universe being the *paths* a rule
reaches rather than the *items* a scan enumerates. When a rule protects one direction, ask
which other doors lead into the same room. Enforced by
`tests/test_run_ledger.RunLedgerTests.test_a_neighbour_this_harness_did_not_emit_does_not_block_scoring`,
which asserts both halves.

---

## D84 — The README is a published claim, and the rule governing it had no criterion ✅

**Fork:** `[P2]`'s last item is the portfolio-facing write-up. What binds it to the truth?

**The gap it exposed, which is older than the README.** D30 has required since `[P1]` that
*"published claims about isolation SHALL state only what is verified — that placement and
guard configuration are checked automatically, that enforcement is attested manually, and
that a determined subprocess is outside deny coverage by design."* Checking the acceptance
criteria for it turned up **none**. The requirement had sat for two phases with nothing able
to fail, for the honest reason that nothing was published yet — and it went live the instant
a README existed. That is exactly D66's shape: a rule recorded before the artifact it
governs, waiting for the artifact to arrive and for somebody to remember. Nobody would have.

**Options considered**
- **Rejected: write the README carefully and rely on review.** The whole record argues
  against this. D53 is the closest precedent: the published matching policy carried a
  hand-written threshold while the real constants lived elsewhere, so changing one would have
  left the policy promising the other with nothing to notice — and the fix was not care, it
  was binding the published text to the shipped constant under a test.
- **Rejected: one criterion covering the whole README.** Prose quality is not testable, and a
  criterion that pretended otherwise would be the overstatement this decision is about.
- **Decision ✅** — a `[P2]` criterion covering exactly what D30 states, bound to a test that
  asserts the three required claims **and** the forbidden one, plus four supporting checks:
  the materiality floor, cap and percentage **derived from `audit_key`'s constants** rather
  than restated (D53's pattern applied to prose); the industry-norm disclaimer required
  (D16); every command named must be one the package declares (D59's rule, wider audience);
  and each given for both shells, counted in pairs so a block added for one shell alone
  fails.

**A defect in the check, found by the check.** The industry-norm assertion failed on a README
that plainly contained the disclaimer — because the line wrap fell between *"not claimed"*
and *"to represent"*, and a phrase scan on a wrapped document silently under-reports. **D55
recorded that exact trap** after being caught by it on the spec, and the lesson had not
reached this file. Every phrase assertion now runs against whitespace-collapsed prose, with
its own premise test proving the raw form genuinely fails to match and the flattened form
finds it. The direction that matters is the other one: a *forbidden* phrase could have
slipped past `assertNotRegex` simply by being wrapped, and that failure would have been
silent.

**What the README claims, and does not.** It states the isolation position in D30's own
terms and stops there; it publishes the thresholds with the reasoning that produced them and
says outright they are **not** claimed to represent standard corporate practice; and it
carries a *"what this harness does not do"* section covering reasoning quality, running the
agent, parsing documents, the audit's bounded completeness, and durations being comparable
only within one machine. A tool that hides its limits is asking to be trusted past them.

**Verified by execution.** 239 tests, pyright 0 errors, `lint_spec` 0 errors.

**Rule** — **a requirement about a published artifact needs its criterion written when the
requirement is, not when the artifact is** — otherwise it waits, unfailable, for the one
session that both creates the artifact and remembers the rule. Enforced by
`tests/test_published_claims.py` and by criterion C75.

---

## D85 — An advertised invocation is executed, not read ✅ (phase-completion sweep)

**Fork:** Two documents told a reader how to run this harness without installing it:

```
README.md                 "Without installing, every command also runs as
                           python -m goldset_triad.<module>"
ISOLATION_ATTESTATION.md  "...or python -m goldset_triad.check_isolation from a
                           source checkout"
```

Both are false. The package lives under `src/`, so the bare form fails:
`ModuleNotFoundError: No module named 'goldset_triad'`.

**This is D59's defect, one layer out.** D59's rule — *anything a tool says about itself is
a claim, and every claim gets a check* — was written about a `prog=` string naming a command
that did not exist. Here the name exists and the **invocation** does not work, and it
survived for D59's exact reason: every test reaches the package through `tests/support.py`,
which inserts `src` into `sys.path`, and every manual run used an installed console script.
**The advertised route was the one path nobody took.** `test_entry_points` checked module →
declaration, declaration → callable, and advertised-name → declaration; all three compare
*names*, and none runs anything.

**Options considered**
- **Rejected: assert the documents mention `PYTHONPATH`.** A text check on a text defect,
  which is how the `assertIn("on:", …)` family of D81 came about — it would pass on a
  document that mentioned the variable while showing a broken command.
- **Decision ✅** — the invocation is **run**, in a subprocess that does not inherit the
  suite's own path fixing, and its `--help` output is asserted. The premise is proven too:
  omitting `PYTHONPATH` must genuinely fail, or documenting it is cargo. Both documents now
  show the working form, and a per-line check refuses any concrete `python -m goldset_triad`
  line without it — a line carrying the `<module>` placeholder is exempt, being prose that
  describes the form rather than a command anyone types.

**A defect in the check, caught while writing it.** The premise test first asked
`importlib.util.find_spec("goldset_triad")` in-process to decide whether the package was
installed — and `support.py` had already put `src` on the path, so it answered *"installed"*
and skipped itself. The check would have been permanently vacuous **because of the very
path fixing that hid the original defect**. It now asks in a clean subprocess run from
elsewhere.

**Rule** — **a documented invocation is executed by a test, from an environment that does
not resemble the suite's.** A name can be compared; a command has to be run. Enforced by
`tests/test_entry_points.AdvertisedInvocationTests`.

---

## D86 — A criterion's test must exercise the case the criterion names ✅

**Fork:** Two `[P1]` criteria were bound to tests that demonstrated something narrower or
other than what they say.

**(a) E7 promised a message nothing read.** *"A malformed findings artifact halts, exits
non-zero, **names the offending finding and field**, and writes no scorecard."* Its test
asserted the exit code and the absent scorecard — both of which a halt with a generic
message also satisfies. The harness had been naming them correctly all along
(`category 'NOT_A_CATEGORY' … [finding #0, field 'category']`); nothing compared that to the
promise. D81's rule, one criterion further on.

**(b) E10 tested absence where it says unreadable.** *"An unreadable answer key halts."* The
test **deleted** the key. The previous sweep found this and wrote it down — *"E10 was only
ever covered for the absent case: its test deletes the file"* — closed the underlying class
in `jsonio` (D77) and left the binding pointing at the wrong case. **A recorded gap is not a
closed one**, and the criterion went on reading as satisfied.

**Measured rather than assumed.** All thirty criteria promising a named cause were scanned
for a test that never inspects the message. Five came back; four (H57, C7, C46, C48) were
false positives of a crude pattern and do assert their messages. **E7 was the only genuine
instance** — which is what makes this the moment D68 names: a class at one, cheap to empty
and cheap to lock.

**Decision ✅** — E7 asserts the offending value, the finding index and the field name. E10
is rebound to a key that is present and not decodable, asserting the halt names the artifact
*by role*; the absent case keeps a test of its own, because absence and unreadability send a
reader to different places (D77).

**Rule** — **when a criterion names a case, its test exercises that case; when a criterion
promises a message, its test reads the message.** A test that passes for a narrower reason
than the criterion states is a criterion that cannot fail. Enforced by the two tests
themselves, and by the scan above being repeatable.

---

## D87 — Every document restating the criteria is bound to them ✅

**Fork:** The phase-2 build prompt opens its gate with *"Every `[P2]` criterion in the
spec"* and enumerated **six of eight**. It had fallen behind twice: once when D79 added the
dataset-mismatch criterion, once when D84 added the README one.

**Why nothing noticed.** `EXPECTED_SPEC_P2_CRITERIA` binds the spec to the traceability map.
Nothing bound either to the prompt — a **third** copy of the same list, in the document a
fresh build session actually reads. The 0.10.3 sweep found six of its eight defects in that
document for precisely this reason, and the lesson reached the spec and the map and stopped
there: D82's *correct rule, wrong universe*, with the universe being which documents the
mechanism can see.

**Decision ✅** — the prompt's gate is completed, and a test asserts its checkbox count
equals the spec's `[P2]` criterion count. Counted rather than diffed line by line, because
the prompt legitimately paraphrases; what must not drift is **how many gates there are**. A
builder working from a short list stops early and believes they are done.

**Rule** — **any document that restates the criteria is bound to the count.** Enforced by
`test_traceability.TraceabilityTests.test_the_build_prompt_gate_lists_every_phase_two_criterion`.

---

## D88 — An assert in shipped code declares why removing it is safe ✅

**Fork:** Seven bare `assert`s live in shipped code — six in `audit_key`, one in `scoring`.
`python -O` strips every one.

**D62 already ruled on this.** It converted `assert isinstance(key, dict)` into a raised
`DatasetError` because under `-O` the failure would resurface later as an unrelated
`TypeError` inside the derivation — and it fixed **one site in that same file and left six**.
The class was ruled on and never locked, which is this project's most-repeated shape.

**Measured before being called a defect.** A malformed purchase order is caught by the
shared loader with a named cause and exit 2 **before any assert runs**; all splits audit
clean under `-O`; the full suite passes under `-O`. So every one of the seven is
type-narrowing — telling the checker what a prior check already guarantees — and the code is
correct today. **The finding is not that they are wrong; it is that nothing says why they
are right.** An assert that narrows a type and one that validates data are indistinguishable
at the site, and D68's scanner, which exists to force exactly this "unreachable by a prior
check" reasoning into writing for `.get()` defaults, cannot see an `assert`.

**Decision ✅** — asserts get the registry-and-census treatment the defaults already have,
in D82's shape: every site carries a justification naming the prior check that makes it
unreachable, a staleness test refuses a justification whose site has gone, a bucket test
keeps the **load-bearing** set empty, and a census refuses to let the scan go quiet.

**Rule** — **a construct the interpreter can silently remove must record why its removal is
safe.** `-O` is to asserts what a missing key is to a default: the condition under which
correct-looking code stops checking. Enforced by
`tests/test_defect_classes.ShippedAssertTests`.

---

## D89 — Byte-identity observed under a randomised hash, not held by construction ✅

**Fork:** `score()` iterates `set(expected_by_key) | set(flags_by_key)` — a set of tuples of
strings — and Python randomises string hashing per process, so that order differs run to
run. Nothing emitted depends on it, because every list reaching the scorecard is either
sorted or reduced to a count. Is that enough?

**No, and the project already knows why.** That is a construction argument spanning two
modules, and H17 was a construction argument corroborated hazard by hazard for two phases —
which failed on its first real observation (D73). The existing reproducibility tests run
twice inside **one process**, so they share one hash seed and could never have seen this.

**Measured first, four seeds, with duplicate contention and a phantom target planted so the
sets had something to reorder:**

```
seed      0 : body sha256 d9a484cd4fcface5
seed      1 : body sha256 d9a484cd4fcface5
seed  12345 : body sha256 d9a484cd4fcface5
seed  99999 : body sha256 d9a484cd4fcface5
```

**Decision ✅** — the property holds, and it is now asserted rather than argued: two
subprocesses at different `PYTHONHASHSEED` values must produce an identical scored body.
Subprocesses are the substance, not overhead — a same-process test cannot vary the seed.

**Rule** — **a determinism claim that spans modules is verified across processes, because a
single process fixes the very thing that could break it.** Enforced by
`tests/test_scorecard_repro.HashSeedDeterminismTests`.

---

## D90 — Regeneration idempotence, verified at last; and one thing for the author ✅

**Fork:** *"Regenerating the dev split's invoice PDFs from the same seed produces
byte-identical files, leaving the aggregate inputs digest unchanged"* is a `[P1]` criterion
(H6), carried as `MANUAL:` since the phase-1 build. It had gone **unverified for three
consecutive sweeps**, because running the generator rewrites dataset files and *"never
modify, move or delete any dataset, answer-key or fixture file"* is a human-checkpoint item.
The author authorised a single run.

**Method.** Digest all 31 tracked dataset artifacts; run the generator; compare. Git is the
safety net — every dataset file is tracked, so any divergence is both visible and
restorable.

**Result: byte-identical, everywhere.**

```
git status --porcelain datasets/     (empty)
31 artifacts, sha256 before == after  ALL IDENTICAL
untracked artifacts introduced        none
```

The generator emitted all four splits, held-out included. The out-of-tree tiers came back
identical too — `check_isolation` reports **no durability warnings**, and D70's check reads
each tier's git state, so a changed byte there would have surfaced as an uncommitted change.
Suite 250 green afterwards; all splits still audit consistent.

**What this closes.** D33 chose ReportLab specifically because PDF writers embed a creation
timestamp and document ID by default, which would change the inputs digest on every
regeneration and *present as tampering*; D43 pinned the generator's newline for the same
class of reason. Both were argued and neither had been observed end to end since. It is
now observed — and it is the third construction-only claim this project has converted to an
observed one, after H17 (D76) and hash-seed determinism (D89).

**One observation the author should settle, because I cannot.** The invocation used was
`cd <secret tier>/_generators && python generate.py`, and the deny list carries
`Bash(* generate.*)`, which that command's text appears to match. It was not refused. From
inside the session I cannot tell whether the rule failed to match, whether compound commands
are matched differently, or whether the session's permission mode allowed it — and **D30 is
explicit that harness enforcement cannot be settled by code from within**, which is exactly
why it is attested rather than tested. This is new evidence bearing on a dated attestation,
so the attestation is worth re-running rather than assumed to still hold. Recorded here
rather than acted on: the never-do list forbids routing around a guard, and it equally
forbids quietly concluding one works.

**Rule** — **a `MANUAL:` criterion that no agent may execute needs a scheduled human run,
not an entry on a list.** H6 sat unverified for three sweeps not because anyone judged it
low-value but because every pass correctly declined to run it, and *"deliberately not
examined"* is indistinguishable from *"never examined"* once it repeats. Enforced by
judgment, not checkable — but the negative-space list now says so in those terms.

---

## D91 — The deny rules bind a session rooted here, and nothing said so ✅

**Fork:** D90 recorded an open question — a generator invocation whose text appears to match
`Bash(* generate.*)` ran without being refused, and D30 holds that harness enforcement
cannot be settled from inside a session. Re-running the attestation settled it, in the
direction nobody wanted.

**The measurement.** A tool-level Read of the canary, which the attestation dated
2026-07-26 records as *refused with no content returned*, **succeeded**. The marker
`CANARY_GTH_9F75AF06_GUARDED_DIR_REACHABLE` surfaced.

**The cause, established rather than inferred:**

| | |
|---|---|
| Deny rules live in | `goldset-triad-harness/.claude/settings.json` |
| The session's project root was | `D:\Claude_Stuff\Claude_Desktop_Code_Projects` — **the parent** |
| That directory's `.claude/settings.local.json` carries | an `allow` list and **zero deny rules** |

Claude Code loads permission settings from the session's own root. A session opened at a
parent folder — a workspace holding several projects, which is an ordinary way to work —
loads *that* folder's settings, and this repository's rules are never read. **The rules did
not fail to match; they were never loaded.** The same absence explains D90's generator run.

**What this does and does not mean, stated precisely because the distinction is the whole
value of D30's framing.**

- **No contamination occurred.** The canary exists for exactly this probe and holds no
  answer-key content — its own text says so. No key, generator source or design artifact was
  read.
- **The primary control held throughout.** D14 and D30 both state that placement outside the
  repository tree is primary and deny rules are the second layer. The entire held-out split
  remained outside the tree, whatever settings were loaded.
- **The second layer was absent for a whole working session, unnoticed**, and the attestation
  had no way to say so: it describes the rooting as a property of *the test* (*"open a
  session rooted in this repository"*) and never as the **precondition for the protection to
  exist**.

**A second-order instance of the same shape.** D71 asserts the stamped guard file's shape —
deny-only, no `allow` list — but that check reads one file, `goldset-triad-harness/.claude/settings.json`.
A parent-level settings file carrying an `allow` list sits entirely outside what any shipped
check can see. D82's *correct rule, wrong universe*, with the universe being which settings
files exist **above** the one enumerated.

**Author's confirmation, which narrows what this finding is.** Asked directly, the author
confirmed that *"it was known from the start that the guards only work if AI is launched from
the project"*, and that **the current placement is correct**. So this is **not** a design
defect and the rules are not moving. What was defective is narrower and still worth the
entry: the precondition was known to the author and **written down nowhere**, so the
attestation was run from the wrong root and recorded a PASS that a differently-rooted session
silently reversed. A guard whose operating condition lives only in the author's memory is
enforced by whoever remembers it — D67's thesis, applied to a configuration rather than a
rule. The fix is therefore visibility, not relocation: state it early in the README, state it
in the runbook, state it in the attestation's own method, and have the isolation command say
when it does not hold.

**Options considered**
- **Rejected: fail the isolation check when an uncovered ancestor is found.** Where somebody
  opens their editor is not a property of this repository, and failing the build over it
  reports a working habit as a security defect — D65's lesson about guards people switch off.
- **Rejected: copy the deny rules up into the workspace settings.** That edits a file
  governing other projects; the author has since confirmed the current placement is the
  intended one, so this stays rejected on the merits rather than merely deferred.
- **Decision ✅** — an advisory `[guard-reach]` line, reported whenever isolation is checked,
  naming the ancestor and its settings file. Excluded from `ok`, so the exit code never
  moves — the same construction D70 chose for durability, for the same reason. The
  attestation now carries the failed re-run **and** states the rooting precondition, and the
  2026-07-26 entry is kept rather than withdrawn, because it remains the evidence that the
  rules *do* bind when loaded.

**Rule** — **a guard's coverage depends on how it was loaded, not only on what it says, and
the loading condition is part of the claim.** Every check here read the *content* of the
rules and none asked whether they were in force. Enforced by `check_guard_reach` in
`check_isolation.py` and `tests/test_isolation.GuardReachTests`; the enforcement half of the
attestation remains, by D30, judgment for a human.

---

## D92 — Usability is a deliverable, and its examples are executed ✅

**Fork:** The harness was complete, tested and swept, and still unusable by a newcomer: three
repositories with no map, a generator nobody outside the author could run, a `findings.json`
described but never shown, and a scorecard nobody had seen. A tool a reader cannot start is
not finished, whatever its test count.

**Options considered**
- **Rejected: expand the README until it covers everything.** The README's job is to make a
  reviewer understand *what this is and why it is trustworthy* in one read. Step-by-step
  operational detail — prerequisites, three-repo layout, regeneration, troubleshooting —
  buries that.
- **Decision ✅** — split by audience. `README.md` keeps the argument and gains a **worked
  example**; `docs/RUNBOOK.md` holds the procedures, every command given for PowerShell and
  bash. Both are bound by checks: the README's isolation and threshold claims already are
  (D84), and the runbook joins the documents whose advertised invocations must actually run
  (D85).

**The examples are real output, not illustrations.** `docs/example-findings.json` ships in
the repository and produces exactly the scorecard the README prints — an agent that gets all
but one expectation right and raises one flag on a clean line, so the reader sees a **miss**
and a **false flag** rather than a flattering perfect score. Writing it by hand and hoping
would have violated the project's own rule about publishing only what is verified.

**Two things writing it caught.**

- **`confidence` must be a JSON number, and the first draft used a string** — rejected, with
  the field named. Correct behaviour, and precisely the trap a worked example exists to spare
  a reader: the *artifact* takes numbers while the *scorecard* emits strings (D37), which is
  deliberate and surprising.
- **`test_confidence_must_be_number_in_unit_interval` was rejection-only.** It proved the
  guard fires and never that it accepts a valid value — the shape D68 named when it observed
  that a rejection-only test would pass a check that rejected everything. Now both directions,
  with the accepted value asserted to arrive as a `Decimal`, which is the type the real path
  produces.

**Rule** — **a published example is generated and re-run, never written.** A hand-written
snippet is a claim about behaviour with nothing comparing it, which is D59's class aimed at
the reader who most needs it: the one who has not yet got the tool working. Enforced by
`docs/example-findings.json` shipping in the repository, so the documented numbers can be
reproduced by anyone in one command.

---

## D93 — A held-out scorecard is answer-key content, and "scorecards are committed" was not written about it ✅

**Fork:** Documenting the held-out workflow end to end raised a question nobody had asked:
**may a held-out scorecard be published?** The project's standing policy says scorecards are
the durable, tamper-evident record, `.gitignore` deliberately does **not** ignore them, and
the README's own table answers *"Committed? Yes"*.

**What a scorecard actually contains, read from the emitter rather than produced by a run.**
`build_scorecard` puts `_finding_json(f)` into `missed` for **every expectation the agent
failed to find** — status, category, scope, `target.document_id`, `target.line_id` and
`reasoning`. An expected finding's reasoning is the generator's own note:

```
"reasoning": "seeded TAX_VARIANCE on INV-2003"
```

So a held-out scorecard with a single miss publishes **which invoice, which line, which
category, and what was deliberately planted there** — verbatim answer-key content in a file
whose name says "results". With zero misses it still publishes the key's *shape*, because
`coverage` states which categories are exercised and `per_category.expected_count` how many
expectations each holds.

Deliberately established **by reading the emitter, not by scoring the held-out split**:
producing one would have put those expectations into this session's context, which is the
contamination the whole architecture exists to prevent.

**Why it went unnoticed.** D14 enumerated what lives outside the tree — inputs, answer key,
generators, discrepancy design — and it is a list of *authored* artifacts. A scorecard is
**derived**, produced later by an ordinary command, and it inherits the sensitivity of the
split it scored without inheriting the rule. The policy "scorecards are committed" is
correct, and was written about the dev split, whose key is public by design. Correct rule,
wrong universe (D82) — the universe here being *which splits a rule about scorecards ranges
over*.

**Options considered**
- **Rejected: redact `missed` on non-dev splits.** It would break verify — the scored body
  must recompute identically — and a scorecard that omits its misses is no longer the record
  it claims to be.
- **Rejected: gitignore a `scorecard-held-out-*` pattern.** It guesses the identifier, and an
  ignore rule is the *silent* control this project has twice been bitten by (D42, D44): a
  file merely ignored is still present on disk and still readable.
- **Decision ✅** — state the rule where the work happens and check it where the damage
  would land. The runbook's held-out section carries the warning and routes `--out` outside
  the repository; a check refuses any **tracked** scorecard whose identifier is not a dev
  split. Nothing is tracked today, so this locks the class **before** an instance exists —
  which is the one time D68 says locking is cheap.

**Verified by execution.** The check passes on the current tree, and its premise test
confirms the pattern classifies `scorecard-held-out-<stamp>.json` as a leak while leaving
`scorecard-dev-<stamp>.txt` alone — both directions, because a rule that flagged legitimate
dev scorecards would be as broken as one that missed held-out ones.

**Rule** — **a derived artifact inherits the sensitivity of what it was derived from, and a
publication rule written about one split does not range over the others.** The question to
ask of any output is not *"is this a results file?"* but *"what does it let a reader
reconstruct?"* Enforced by
`test_repo_shipping.RepositoryShippingTests.test_no_scorecard_from_a_non_dev_split_is_tracked`.

---

## D94 — A byte-order mark is accepted, because Windows is first-class or it is not ✅

**Fork:** The author, following this project's own runbook, hit:

```
error: findings artifact is not valid JSON: empty.json
       (Unexpected UTF-8 BOM (decode using utf-8-sig): line 1 column 1 (char 0))
```

The command that produced the file was `Out-File -Encoding utf8`, taken verbatim from the
runbook written one commit earlier. **In Windows PowerShell 5.1 that writes a BOM despite its
name** — verified: `EF BB BF`, where `-Encoding ascii` and `[IO.File]::WriteAllText` do not.
So the documentation was wrong, and it was wrong in the direction that matters: a first-time
user following the instructions exactly gets an error.

**But fixing only the documentation would have missed the larger point.** The spec makes
Windows and Linux **both first-class**, and Windows tooling adds a BOM freely — `Out-File`,
Notepad's "UTF-8", numerous editors. An agent under test running on Windows can emit one just
as easily as a human can. Refusing to score its findings over three bytes that carry no
meaning is declining to do the work for a reason unrelated to the work. And the harness's own
error message **named the fix it was not applying** (`decode using utf-8-sig`), which is a
tool describing its own remedy and then not taking it.

**Options considered**
- **Rejected: fix the runbook and keep rejecting.** It leaves the harness first-class on
  Windows with an asterisk, and leaves every future Windows-authored artifact one silent
  trap away from an error about encoding rather than about accounting.
- **Rejected: catch the BOM and report it better.** A clearer message about a condition that
  need not be an error at all is polish on a decision that should be reversed.
- **Decision ✅** — the shared reader (D77) decodes with **`utf-8-sig`**, which strips a BOM
  when present and is identical to `utf-8` when it is not. One line, one place, because there
  is only one function in the package that reads text.

**What this does not weaken, checked rather than assumed.**
- **D61 is satisfied.** Its rule was never "use utf-8"; it was *never rely on the platform
  default*. `utf-8-sig` is explicitly named, and the AST guard tests for the presence of an
  `encoding` keyword rather than its value.
- **No digest changes.** Every fingerprint in this project hashes **raw bytes** via
  `read_bytes` — the aggregate inputs digest (D27), the key, the index, the findings
  artifact. A BOM'd file still digests differently from a clean one, which is correct: they
  really are different files. What widened is what the harness **accepts**, not what it
  treats as the same input. The test asserts exactly that, by comparing the two files' bytes
  after both parse successfully.

**Verified by execution.** A BOM'd findings artifact parses to the same object as a clean one
and **scores end to end** through the CLI, not merely through the reader in isolation — the
reader is not the path a user takes. 257 tests, pyright 0 errors.

**Rule** — **when an error message names its own remedy, ask why the code is not applying
it.** `"decode using utf-8-sig"` was in the output the whole time. A harness that states the
fix and refuses to perform it has diagnosed the problem and declined to solve it. Enforced by
`test_read_failures.OneReaderTests.test_a_leading_byte_order_mark_is_accepted` and
`test_a_bom_artifact_scores_end_to_end`.

---

## D95 — A fence's language tag is invisible to the reader it was written for ✅

**Fork:** Every command in this project's user-facing documentation is given twice, once for
PowerShell and once for bash, distinguished only by the fenced block's language tag —
` ```powershell ` and ` ```bash `. The author pointed out that **a rendered markdown viewer
shows none of that.** On GitHub, the two blocks appear as two adjacent, unlabelled boxes of
text, and a reader has to already know which one is theirs.

**Why that is worse here than in most projects.** The convention exists precisely *because*
the two shells differ — path separators, line continuations (`` ` `` versus `\`), environment
syntax (`$env:X = 'v'` versus `X=v`). A reader who picks the wrong block does not get a
graceful failure; they get a syntax error in a shell they may not know well, while following
instructions written for them. The information distinguishing the blocks was present in the
source and absent from the artifact anybody actually reads.

**Decision ✅** — a visible bold label above every shell block:

```
**Windows — PowerShell:**
**Linux / macOS — bash:**
```

Applied to all 68 shell blocks across `README.md`, `docs/RUNBOOK.md` and
`ISOLATION_ATTESTATION.md`, by script rather than by hand — sixty-eight manual insertions is
an invitation to miss one, and the miss would be invisible for exactly the reason the change
exists. The script tracks fence state so a ``` inside a code block is never mistaken for an
opening fence, and preserves a blockquote prefix so labels inside a `>` block stay inside it.
`goldset-triad-secret` is deliberately out of scope, per the author: it is the author's own
tier and not user-facing.

**And it is checked, because a documentation convention with no check is a convention until
somebody adds a block.** `ShellLabelTests` walks the same three documents and fails on any
`bash` or `powershell` fence whose preceding non-blank line is not the matching label. The
document list is **named rather than globbed** — "whatever markdown happens to exist" is not
a universe (D82), so a new user-facing document has to be added deliberately.

**Rule** — **check what the reader sees, not what the source says.** A language tag, a
comment, an HTML attribute: anything the renderer consumes is invisible to the audience the
document was written for, and documentation is judged on the rendered artifact. The same
shape as D60's finding that a `null` metric needed to state *why* it was null — the
information was present and the reader was left to supply it. Enforced by
`tests/test_published_claims.ShellLabelTests`.

---

## Not checked — as of 0.25.0 @ D90

What each pass deliberately did **not** examine. Recorded because the recurring cost is not the defect a sweep
finds, it is the gap a sweep knowingly leaves and never writes down: **D64a existed because "the staleness checks
iterate only the dev splits" was true, deliberate and unrecorded.** The next reader starts here — and the
phase-completion sweep did exactly that, taking the list below as its agenda and finding three of its five
things by walking it.

### The phase-completion sweep (0.25.0, D85–D89)

It worked the previous sweep's negative-space list as its agenda, which is what that list is
for and the first time it has been used that way. It examined the scoring engine, the
advertised invocations, the `[P1]` criteria that promise a named cause, the phase-2 build
prompt, and this session's own unreviewed work. It did **not** examine:

- ~~**Dataset regeneration.**~~ **Closed by D90**, on the author's explicit one-time
  authorisation: all 31 tracked artifacts came back byte-identical, no untracked artifacts
  appeared, and the out-of-tree tiers reported no durability warning, so the held-out split
  regenerated identically too. H6 and the D33/D43 idempotence argument are now observed
  rather than argued. **What remains open here is the guard question D90 raises**, which
  only a human can settle: a command whose text appears to match `Bash(* generate.*)` was
  not refused, and D30 rules that harness enforcement cannot be probed from inside. The
  dated attestation is worth re-running.
- **`pip install -e .`** as a live step. The console-script declarations are checked three
  ways (D59) and the module invocation is now executed (D85), but the install itself would
  modify the environment, so it was not run. D59 last verified it in a throwaway venv.
- **The other ~94 `[P1]` criteria.** Thirty were scanned — those promising a *named cause*,
  chosen because D81 showed message assertions are this project's weak spot. One genuine
  instance came back (E7). The remaining criteria were not re-read against their tests, and
  E10 is the standing warning that a binding can be wrong for two phases while looking
  satisfied.
- **`scorecard.py`'s rendering.** `scoring.py` was read line by line; the summary renderer
  was read only for its `run_metadata` independence (which the cross-platform job depends
  on) and not for its arithmetic or formatting.
- **The generator's own rules.** Unchanged from every prior sweep: the secret tier has no
  test suite, and a rule change that is self-consistently wrong still passes.
- **The reserve-then-create race**, carried forward from the last sweep and now slightly
  wider: D83 made reservation skip unparseable neighbours, which does not touch the
  check-then-create shape. Two concurrent `score` runs can still pick one ordinal and one
  will raise `FileExistsError`. Still no test covers concurrent runs.

### The D77–D82 sweep (0.23.0)

It examined the `[P2]` surface — verify mode, the run ledger, the CI workflow — the mechanisms those register
with, and every read and write path they touch. It did **not** examine:

- **The scoring engine's arithmetic.** `scoring.py` and `scorecard.py` were read for types and call signatures
  and not reviewed. Matching, contention, the per-category counts and the ratio quantization were taken as
  covered by the `[P1]` gate. The `[P1]` gate is 124 criteria and was itself written by the sessions that wrote
  the code, which is the condition under which this sweep found twenty-four things.
- **`audit_key`'s independent re-derivation.** Only its file read changed (D77). The derivation that makes the
  audit a second opinion rather than an echo (D35) was not examined, and it is the one place where a defect
  would make two artifacts agree for the wrong reason.
- **The datasets themselves.** No key content, boundary value or regeneration was re-audited. The suite asserts
  audit-consistency on every split and that stands; nothing here looked past it.
- **The secret and held-out tiers' contents.** Both were confirmed untouched by `[P2]` and clean in git, which
  is a statement about their *state*, not their *correctness*. The generator's rules were not read.
- **`check_isolation`'s rule matching.** One read site changed (D77); the guard-coverage logic around it did
  not, and was not reviewed. The attestation's automated half was re-run and passes.
- **The reserve-then-create race in `cli._reserve_scorecard_paths`.** It checks `.exists()` and then creates
  with mode `"x"`, so two concurrent `score` runs can pick the same ordinal and one will raise an uncaught
  `FileExistsError`. Pre-existing and unchanged in kind by D80, which widened the scan from one stem to the
  directory-second without altering the check-then-create shape. Left alone deliberately: D49 chose exclusive
  creation so that overwriting is impossible rather than merely unintended, and a retry loop around it is a
  design decision, not a bug fix. **No test covers concurrent runs at all.**
- **Whether `[P1]`'s own criteria are honest.** This sweep added four criteria and did not re-read the other
  124. E10 is the warning: *"an unreadable answer key halts"* was covered by a test that deletes the file, so
  the criterion read as satisfied for two phases while the unreadable case tracebacked (D77). One instance
  found by accident is not evidence that it is the only one.

### The D72 sweep (0.21.0)

- **The non-numeric absence defaults** in shipped code (`.get(k, "")`, `.get(k, [])`, `.get(k, {})`). **Narrowed
  by D82, not closed.** They are now a *named* bucket — `empty-container` — that the scanner classifies rather
  than skips, and a default fitting no bucket fails the suite; that is what caught the one this bullet could
  never have caught, a substantive default supplying a real value for an absent declaration (D78). What remains
  open is the original scoping call, which stands: the thirteen empty-container sites are justified **as a
  bucket** and still not reviewed **individually**. **The count that used to open this bullet is deliberately
  gone.** It read 16 while D71's own text read 15, and the two disagreed for a
  specific reason: this bullet also named `dataset.py`'s `raw.get("po_number", po_path.name)` as the one to look
  at first, and **D71(d) removed that fallback in the same session that wrote this line.** So the negative-space
  list — whose entire purpose is to be the honest record of what a sweep knowingly left — was both counting a
  closed defect and sending the next reader to it, which is this section's own failure mode turned on itself. A
  hand-copied total sitting beside its own source drifts; spec 0.22.0 removed three more of exactly that shape
  in the same pass. If a number is wanted here, count it at the time, and D68's scanner in
  `tests/test_defect_classes.py` is where a real one would come from rather than from prose.
- **`.claude/settings.json` beyond the deny list.** Pattern anchoring is now checked on every rule list, but
  nothing asserts which lists may exist. An `allow` list appearing there would be scanned for anchoring and
  otherwise unremarked.
- **The generator's own correctness.** The secret tier has no test suite; `generate.py` asserts each computed
  finding against the line's stated intent at generation time, and that is the only check on it. A rule change
  that is self-consistently wrong would pass.
- ~~**`[P2]` verify mode against the D66 schema rule.**~~ **Closed by D74** — verify mode exists, the rule is
  now a `[P2]` acceptance criterion (it was a requirement with no criterion, which is why nothing could have
  failed), and `test_unrecognised_schema_version_is_its_own_outcome` plants an altered number alongside the
  stale version and asserts it does **not** surface.
- **The claims registry cannot see a scorecard** (D74, recorded when verify mode was built). D67's discovery
  half iterates `known_splits()` across `manifest`, `key`, `index` and `policy` — split artifacts **on disk** —
  so a claim-shaped field added to a *runtime* artifact would not be discovered, and a registry entry naming
  one would be rejected as stale. The scorecard's fingerprints do now have a check, namely verify mode itself;
  what is unreached is the mechanism, which is D64a's shape inside the mechanism built to end D64a's shape.
  Closing it means discovery scanning a scorecard built in memory rather than read from a split — a change to
  D67, so it gets its own decision rather than riding along with verify mode.
- ~~**The cross-platform digest COMPARISON.**~~ **Closed by D76.** The `cross-platform` job scores the dev
  split on `ubuntu-latest` and `windows-latest` at one pinned interpreter and compares the scored bodies, which
  carry the aggregate inputs digest — so a value computed on Windows is now set beside one computed on Linux on
  every push, which is exactly what this bullet said had never happened. It went on saying it for two
  decisions after D76 made it false, which is this section's own failure mode: a negative-space list that keeps
  a closed item is not a conservative record, it is a wrong one, and it sends the next reader to work that is
  already done. Found by the D77–D82 sweep.
- **Whether the secret tier's remote actually has the commits.** D70 reads `[ahead N]` from local git, which
  reflects the last fetch rather than the remote's true state. A tier that is level with a *stale* tracking ref
  reports clean. Closing that means talking to the remote, which the check deliberately does not do.
- **The `goldset-triad-holdout` inputs directory.** ~~Not a git repository at all~~ — **D71 made it one**, and
  this bullet went on describing the state D71 had already changed, in the same section and the same pass as the
  cross-platform bullet above. What remains open is narrower and still real: the tier has exactly one commit and
  no remote, so D70's `[ahead N]` durability check has nothing to compare against, and no digest binds those
  bytes beyond the aggregate inputs hash inside a scorecard.

---

## Document status

Decisions are numbered from **D0** and run to the last heading in this file. That extent is deliberately **not
restated here**: this line read `D0–D68` while D69–D73 sat above it — a derived value copied beside its own
source, the same class spec 0.22.0 removed from three places in the same pass. `lint_spec.py` reports the real
range and fails on a duplicate or a gap, which is a mechanism rather than a sentence someone must maintain.

Attribution by session: D37–D41 by the phase-1 build; D42–D44 by the first consistency pass; D45–D48 by the
pre-phase-2 sweep; D49–D54 by the second sweep over code, data and generator; D55–D57 formalizing the behaviours
that had lived only in code; D58–D71 closing the post-build review's open issues and the two sweeps after it;
D72 gating `[P2]` on a Linux CI run; **D73 by that run itself, on its first attempt.** D74–D76 by the `[P2]`
build; **D77–D82 by an independent sweep over that build**, run by a session that did not write it, against a
green suite and green CI — which is the only reason those twenty-four findings were findable at all.

Spec emitted at `specs/goldset-triad-harness.md`; build prompts at
`specs/goldset-triad-harness.build-prompt.md` (phase 1) and
`specs/goldset-triad-harness.p2.build-prompt.md` (phase 2).

Any new fork encountered during the build is to be appended here in the same format — fork, options
considered, decision, why — so this record does not go stale.

