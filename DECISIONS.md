# goldset-triad-harness — Decision Record

A running "decision tree": every fork we hit, the options considered, the choice made, and **why**.
Kept so the reasoning behind the design is always reviewable — not just the outcome.

- **Project:** `goldset-triad-harness`
- **Identity:** *A held-out golden-dataset harness that scores an AP document-matching agent's 3-way
  (PO / invoice / goods-receipt) findings against hand-audited ground truth.*
- **Status:** decisions accrue during the `/specify` interview; finalized alongside the spec.
- **Legend:** ✅ decided · 🔶 open / revisit · ⏭️ deferred to a later phase

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

## Document status

Decisions **D0–D13** recorded. Spec emitted at `specs/goldset-triad-harness.md` (linted: 0 errors); build
prompt for phase 1 at `specs/goldset-triad-harness.build-prompt.md`.

Any new fork encountered during the build is to be appended here in the same format — fork, options
considered, decision, why — so this record does not go stale.

