# goldset-triad-harness

A held-out golden-dataset harness that scores an AP document-matching agent's 3-way
(purchase order / invoice / goods-receipt) findings against hand-audited ground truth.

Point it at a dataset and an agent's findings; get back an objective scorecard —
per-category precision and recall on expected discrepancies, plus an over-flagging rate
measured on a zero-defect control — in one command, reproducibly, with the answer key
structurally unable to enter the agent's context.

---

## Why this exists

Evaluating an agent on accounts-payable matching usually degrades into eyeballing output.
That fails in a specific way: a prompt change improves one invoice and quietly breaks
another, and nobody notices until the numbers stop adding up. What is missing is not
cleverness, it is a **verdict you can re-derive** — one that says where and how the agent
failed, and gives the same answer tomorrow.

So the design constraint is not accuracy, it is **falsifiability**. Every number this
harness emits can be recomputed from the inputs it names, by someone who does not trust it.

---

## Quickstart

Python 3.11 or newer. The scoring engine has **zero runtime dependencies** — standard
library only — which is deliberate: nothing third-party sits between a dataset and its
score.

Every command below is given for both shells, because Windows and Linux are both
first-class here and neither is the "real" one.

**Install (editable, for the console scripts):**

```bash
python -m pip install -e .
```

```powershell
python -m pip install -e .
```

**Score an agent's findings against the shipped dev split:**

```bash
goldset-triad score --dataset dev --findings ./findings.json --out ./scorecards
```

```powershell
goldset-triad score --dataset dev --findings .\findings.json --out .\scorecards
```

**Verify a scorecard by recomputing it:**

```bash
goldset-triad verify --scorecard ./scorecards/scorecard-dev-20260727T050000Z.json \
  --dataset dev --findings ./findings.json
```

```powershell
goldset-triad verify --scorecard .\scorecards\scorecard-dev-20260727T050000Z.json `
  --dataset dev --findings .\findings.json
```

**Rebuild the run ledger from the scorecards alone:**

```bash
goldset-triad rebuild-ledger --out ./scorecards
```

```powershell
goldset-triad rebuild-ledger --out .\scorecards
```

**Check the answer key against an independent derivation, and check isolation:**

```bash
goldset-triad-audit-key --dataset dev
goldset-triad-check-isolation
```

```powershell
goldset-triad-audit-key --dataset dev
goldset-triad-check-isolation
```

Without installing, every command also runs as `python -m goldset_triad.<module>`.

---

## What makes the verdict trustworthy

Four properties, each chosen because it removes a way the score could be wrong without
anyone noticing.

### 1. Nothing judges anything at runtime

The harness makes **no model call and no network call, ever.** Loading, schema validation,
matching, tie-breaking, the arithmetic, fingerprinting and serialization are all plain
deterministic code. This is not an omission — a non-deterministic scorer cannot produce a
reproducible verdict, and a verdict you cannot reproduce is an opinion.

AI is used at **design time**, to plan discrepancy coverage before the data is frozen. That
output is human-audited and committed as seeded generator code. No model is invoked by any
pipeline.

### 2. The same inputs produce byte-identical output

Re-running on the same dataset and findings artifact yields a **byte-identical** scorecard,
excepting one envelope — `run_metadata` — which holds exactly the non-deterministic fields
(the run timestamp and elapsed durations) and nothing else. Every deterministic value,
including the invoice and finding counts, lives in the scored body where that comparison
protects it.

Money is `Decimal` throughout and never `float`. Comparisons happen at full precision and
are never rounded beforehand; rounding is a display step only, explicitly `ROUND_HALF_UP`
rather than Python's banker's-rounding default. Reported ratios carry a declared precision
so their emitted bytes are fixed by the specification rather than by whichever interpreter
happens to run.

### 3. A scorecard never has to be trusted, because it can be recomputed

Each scorecard embeds **four SHA-256 fingerprints** — the findings artifact, the answer key,
the structured invoice index, and an aggregate digest of the dataset inputs. `verify`
recomputes the score and reports the first applicable outcome:

| Outcome | Meaning |
|---|---|
| `schema-unrecognised` | The scorecard's declared shape is not one this harness emits. **Nothing is compared** — a shape change is not a scoring difference. |
| `dataset-mismatch` | It was pointed at a different split from the one the scorecard names. |
| `fingerprint-mismatch` | The inputs moved. *"You scored different data"* is not *"the numbers are wrong."* |
| `score-differs` | Same inputs, different numbers. The real discrepancy, reported by field name. |
| `identical` | Every scored field matches. |

The ranking is the substance. Collapsing these into "verify failed" would send a reader to
audit arithmetic that was never at fault.

### 4. The scorer loads expectations; it never derives them

The scoring engine reads expected findings from the answer key and confines itself to
matching and counting. **No domain rule executes at scoring time.** A scorer that derived
expectations would be scoring the agent against its own implementation rather than against
audited ground truth — any bug in it would silently *become* truth, and "golden dataset"
would collapse into "reference implementation".

Every rule lives in two places instead: the key generator that applied it, and the
**published matching policy** shipped beside each split, so an agent can compete against
rules it can read. A separate `audit-key` command derives expectations independently and
diffs them against the declared key.

---

## The held-out split, and what isolation actually means here

The **entire** held-out split — inputs, answer key, generators and the discrepancy-design
artifact — lives **outside this repository tree**. Not just the key. Published inputs are a
contamination vector on their own: a model trained on the repo can memorise the documents
without ever seeing a label, and the labels are derivable from the inputs by simply doing
the task correctly.

The dev split ships here in full, key included. It is public by design, and it is what every
automated check and CI run against.

Two axes are easy to conflate, and conflating them produces a harness that cannot evaluate
anything:

|  | in repository | outside repository |
|---|---|---|
| **agent-readable** | dev split (inputs **and** key) | **held-out inputs** |
| **agent-denied** | — | held-out key, generators, design artifact |

The held-out inputs are out-of-tree **and must stay agent-readable** — the agent cannot
produce findings without them. A guard scoped to "the held-out directory" instead of to the
key, generators and design artifact silently breaks evaluation rather than protecting it.

### What is verified, stated precisely

This is the part most worth reading carefully, because it is where a harness is most
tempted to claim more than it can show.

- **Placement is checked automatically.** No secret artifact exists at any path inside the
  repository tree, including under ignored directories — `.gitignore` hides a file from git,
  not from the filesystem or from a reading agent. It is also asserted over the git index,
  because a file excluded by an ignore rule is plainly present on disk while absent from a
  fresh clone.
- **Guard configuration is checked automatically.** The deny rules exist, parse, and cover
  every path in the secret tier, while deliberately not covering the held-out inputs.
- **Harness enforcement is attested, not tested.** Deny rules bind tool calls; a subprocess
  runs beneath that boundary, so a probe that tried to `open()` the guarded file would
  succeed and would report failure *identically* whether the guards were perfect or absent.
  Such a probe would prove nothing while looking like verification. It is recorded instead as
  a dated manual attestation naming the method used — see
  [`ISOLATION_ATTESTATION.md`](ISOLATION_ATTESTATION.md).
- **A determined subprocess is outside deny coverage by design.** That is exactly why
  **placement outside the tree is the primary control** and the deny rules are the second
  layer.

Knowing the limits of your own verification is worth more than claiming past them.

---

## The matching methodology

### What counts as a match

A finding matches an expectation on a strict key: **status + category + scope + target**,
where the target is the document identifier alone for a document-scoped finding and the
document plus line identifier for a line-scoped one. Matching is 1:1 — each finding claims at
most one expectation and vice versa — and contention is broken by canonical serialisation
order, never by position in the findings artifact, so reversing that artifact yields an
identical scorecard.

Line identifiers are assigned explicitly by the dataset, never positional. A `MATCH`-status
entry asserts correctness, so it can neither be a false positive nor satisfy an expectation:
one wrong assertion is counted exactly once.

### The five categories

`PRICE_VARIANCE`, `QTY_UNDER_SHIPMENT`, `QTY_OVER_SHIPMENT`, `QTY_INVOICE_INFLATED`,
`TAX_VARIANCE` — a closed enumeration owned by the harness, because per-category precision
and recall are only well-defined over a fixed vocabulary. An unknown category is a schema
violation and halts the run.

Quantity discrepancies anchor on the **payable quantity**, `min(ordered, received)`, with
received summed across *all* goods receipts for a line. The category names which constraint
bound it. A short shipment billed correctly for what arrived is **not** a discrepancy — a
shipment anomaly with no billing impact is not a finding, and marking it would train an agent
to flag non-issues.

### The materiality threshold

```
threshold = max($0.05, min(2% x basis, $25))
flag when |variance| >= threshold
```

The two thresholds serve different purposes, which is what justifies OR between them. **$25
is materiality** — a discrepancy worth more than the time to chase it is worth the effort,
and it is the only threshold that governs large lines. **2% is a systematic-error signal** —
a proportionally large error on a cheap line indicates wrong contract pricing that will recur,
worth catching at $3 where materiality alone would not justify it. The **$0.05 floor** keeps
rounding noise off the zero-defect control.

They cross at $1,250, so the percentage governs below that point and the $25 cap above. On a
$100,000 line the threshold is $25, not $2,000 — a tolerated $1,999 variance would be a
disqualifying blind spot for a harness built to catch money leaving.

The basis is the **payable extended amount**, never the invoiced one: an inflated invoice
would otherwise enlarge its own denominator and understate its own variance ratio.

> **These are this harness's thresholds and this harness's reasoning.** They are not claimed
> to represent standard corporate practice. Percentage tolerances in the low single digits
> are unremarkable, but that was not verified against a citable standard, so no such claim is
> made.

---

## Reading a scorecard

The scorecard is emitted twice — machine-readable JSON and a human summary — and the summary
names every missed finding and every false flag individually, not just totals.

**An undefined metric is emitted as `null`, never as zero and never omitted.** Zero reads as
failure where the result was in fact perfect, and an omitted key would make the field unstable
across runs. But `null` alone is ambiguous: "not applicable", "not attempted" and "not asked"
all look the same, and a reader who cannot tell them apart will pick the flattering one.

So every scorecard carries a **coverage block** stating which categories the dataset holds
expectations for, which it does not, and how many expectations each has. An unexercised
category is marked inline in the summary, with the consequence spelled out: *their null
metrics mean the data lacks these cases, not that the agent handled them correctly.* The
zero-defect control says outright that it measures over-flagging only and that every recall
figure on it is undefined by construction — otherwise it reads as an agent that recalled
nothing, the exact inversion of what it proves.

---

## Cross-platform behaviour

Identical scorecard content on Windows and on Linux is a central claim here, so it is
**observed rather than argued.** On every push, CI scores the same dataset and findings
artifact on `ubuntu-latest` and `windows-latest` at one pinned Python version, and asserts
that both the scored body and the human summary are byte-identical.

That claim was corroborated hazard by hazard long before it was ever run — shipped output pins
LF, every text read names its encoding, dataset files are exempt from line-ending translation
— and corroborating a mechanism is not observing a result. The first Linux run found a real
defect within minutes of existing.

---

## What this harness does not do

Stated plainly, because a tool that hides its limits is asking to be trusted past them.

- **It does not score reasoning quality.** Judging prose needs an LLM judge: subjective,
  non-reproducible, and itself in need of evaluation. That would poison the deterministic
  verdict this exists to provide. Permanently out of scope, not deferred.
- **It does not run the agent.** The findings payload schema is the port; the agent runs as a
  separate step and writes JSON. That is what makes isolation free rather than fought for.
- **It does not parse documents.** Extraction is the agent's job. Structured invoice data
  comes from an agent-denied index, never from reading a PDF.
- **The key audit is a consistency check, not a proof of correctness.** Generator and auditor
  share an author, so their independence is weak. It catches arithmetic slips, transcription
  errors and post-regeneration drift — not a shared misunderstanding. Its completeness is
  further bounded by the correspondence declared in the key it audits.
- **Durations are comparable only within one machine.** A ledger spanning a laptop and a CI
  runner compares nothing.

---

## Repository layout

```
src/goldset_triad/     the harness: scoring engine, verify, ledger, audit, isolation checks
tests/                 the acceptance suite, mapped criterion by criterion
datasets/dev/          the public dev split, shipped complete with its key
datasets/dev-synthetic/       labelled fixtures for values implausible in the domain
datasets/dev-zero-defect/     the zero-defect control, for over-flagging
specs/                 the specification and the phase build prompts
DECISIONS.md           every fork, the options considered, the choice, and why
```

**[`DECISIONS.md`](DECISIONS.md) is the document to read next** if you want to know why
anything here is the way it is. It records each decision as a fork with its rejected
alternatives, including the ones that turned out wrong and were overturned. Several entries
exist because a later pass found a defect in an earlier one; those are kept rather than
tidied away, because the reasoning is the artifact.
