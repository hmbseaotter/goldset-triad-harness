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

## Document status

Decisions **D0–D44** recorded (D37–D41 appended by the phase-1 build session; D42–D44 by the follow-up
consistency work). Spec emitted at `specs/goldset-triad-harness.md`; build prompt for phase 1 at
`specs/goldset-triad-harness.build-prompt.md`.

Any new fork encountered during the build is to be appended here in the same format — fork, options
considered, decision, why — so this record does not go stale.

