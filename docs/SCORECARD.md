# Reading a scorecard, field by field

A scorecard is the harness's durable verdict on one findings artifact. This is the reference for
every field it emits: what the value is, and — where a field invites a wrong reading — what that
wrong reading would be.

Two files are written per run, sharing a stem:

| File | For |
|---|---|
| `scorecard-<dataset>-<stamp>.json` | machines, and recomputation |
| `scorecard-<dataset>-<stamp>.txt` | people; names every miss and false flag individually |

Both are written with pinned LF endings so the bytes match on every platform (D49). A run in the
same second as another gets a distinct name rather than overwriting it (D49).

---

## The human summary, and its abbreviations

The `.txt` file is the same verdict in a form you can read at a glance. Its abbreviations appear
nowhere else, so they are defined here.

```
Scorecard - dataset dev @ 1.0.0
============================================================
Workload: 4 invoice(s), 3 finding(s) submitted
Overall precision: 1.0000   recall: 0.3333
False positives: 0  (rate 0.0000 per invoice)
Duplicate-contention flags: 0   Non-existent-target flags: 0   MATCH assertions: 0

Per-category (precision / recall):
  PRICE_VARIANCE         TP 3  FP 0  FN 1   P 1.0000  R 0.7500
  QTY_UNDER_SHIPMENT     TP 0  FP 0  FN 1   P n/a     R 0.0000
  TAX_VARIANCE           TP 0  FP 0  FN 0   P n/a     R n/a      [not exercised by this dataset]

COVERAGE: this dataset exercises all 5 categories (9 expected finding(s)).

Missed findings (6):
  - PRICE_VARIANCE on INV-2002 line 3
False flags: none
```

| Abbreviation | Full name | JSON field | What it counts |
|---|---|---|---|
| `TP` | true positives | `true_positives` | Flags the agent submitted that matched an expectation. **Right answers.** |
| `FP` | false positives | `false_positives` | Flags the agent submitted that no expectation justified. **Wrong alarms.** |
| `FN` | false negatives | `false_negatives` | Expectations the agent did not produce. **Things it should have caught and did not.** |
| `P` | precision | `precision` | `TP ÷ (TP + FP)` — of what it flagged, how much was right. Answers *"can I trust its alarms?"* |
| `R` | recall | `recall` | `TP ÷ (TP + FN)` — of what was there, how much it found. Answers *"will it miss things?"* |
| `n/a` | undefined | `null` | The metric has no value, because its denominator is zero. **Not zero — see below.** |

**Precision and recall trade against each other, which is why both are reported per category.**
An agent that flags everything scores perfect recall and terrible precision. An agent that flags
only what it is certain of scores the reverse. Neither is good, and a single overall number hides
which failure you have — a category-level view shows whether the agent is blind to tax variance
or merely noisy about prices.

There is no F-score. Combining the two into one number would discard exactly the distinction the
per-category table exists to show, and the zero-defect control is scored on
`false_positive_rate` instead, because over-flagging a clean dataset is the failure a blended
score conceals.

`n/a` in the summary is `null` in the JSON. A row reading `TP 0 FP 0 FN 0 P n/a R n/a` with
`[not exercised by this dataset]` means the dataset asked nothing here — **not** that the agent
answered everything correctly.

---

## Top-level blocks

| Field | Type | Meaning |
|---|---|---|
| `schema_version` | string | The shape of the **scored body**. Raised whenever that shape changes, so a consumer can tell a schema migration from a scoring difference (D60, D66). Currently `"2"`. |
| `dataset` | object | Which dataset produced this verdict. |
| `fingerprints` | object | Four digests that make the verdict recomputable without trusting it. |
| `workload` | object | How much was scored, and how much was submitted. |
| `coverage` | object | What the dataset **can and cannot measure**. |
| `metrics` | object | The verdict itself. |
| `missed` | array | Every expectation the agent did not produce. |
| `false_flags` | array | Every flag the agent produced that no expectation justified. |
| `run_metadata` | object | Exactly the non-deterministic fields, and nothing else. |

**Everything except `run_metadata` is the scored body.** Two runs on the same dataset and the same
findings artifact produce byte-identical scored bodies (D18). That is why `run_metadata` is
segregated rather than sprinkled: the byte comparison excludes precisely one block, and it is
obvious which.

---

## `dataset`

| Field | Type | Meaning |
|---|---|---|
| `identifier` | string | The dataset's own name, e.g. `dev`, `held-out`. |
| `version` | string | The dataset version, copied from its manifest verbatim. |

---

## `fingerprints`

All four are SHA-256 hex digests. Their purpose is **verify-by-recompute**: a scorecard never has
to be trusted, because anyone holding the same inputs can recompute these and compare (D10).

| Field | Digest over | Changes when |
|---|---|---|
| `findings_artifact_sha256` | the submitted findings file, raw bytes | the agent's submission differs in any byte |
| `answer_key_sha256` | the answer key, raw bytes | the expectations were edited |
| `invoice_index_sha256` | the structured invoice index, raw bytes | the ground-truth line inventory changed |
| `inputs_aggregate_sha256` | **all input documents together** — purchase orders, goods receipts, invoice PDFs | any input document changed by one byte |

The aggregate digest is defined so two machines agree: paths relative and forward-slashed, sorted
byte-wise, each file's raw bytes hashed, then the path/digest pairs hashed in that order (D27). On
a mismatch the harness recomputes **per-file** digests and reports which files diverged, so
diagnostic depth is computed on demand rather than stored in every scorecard.

---

## `workload`

| Field | Type | Meaning |
|---|---|---|
| `invoice_count` | integer | Invoices in the dataset — **not** invoices the agent commented on. It is the denominator of `false_positive_rate`. |
| `finding_count` | integer | Findings the agent **submitted**. Not the number that were correct. |

---

## `coverage`

Present because `null` is ambiguous. "Not applicable", "not attempted" and "not asked" all look
identical as `null`, and a reader who cannot tell them apart picks the flattering one (D60).

| Field | Type | Meaning |
|---|---|---|
| `categories_total` | integer | Categories in the closed enumeration. |
| `categories_exercised` | array | Categories this dataset holds at least one expectation for. |
| `categories_not_exercised` | array | Categories it holds none for. **Their `null` metrics mean the data lacks these cases, not that the agent handled them correctly.** |
| `expected_finding_count` | integer | Total expectations in the answer key. |
| `measures_recall` | boolean | `false` when the key declares no expectations at all — the zero-defect control. It measures over-flagging only, and every recall figure on it is undefined **by construction**, not by omission. |

> **The misreading this block exists to prevent.** A held-out run showing three categories at
> `null` looks like a flawless agent. It usually means the dataset never asked.

---

## `metrics`

| Field | Type | Meaning |
|---|---|---|
| `overall.precision` | string or `null` | Of the flags submitted, the share that were right. `null` when the agent submitted no flags at all. |
| `overall.recall` | string or `null` | Of the expectations held, the share the agent found. `null` when the key holds none. |
| `false_positive_count` | integer | Flags no expectation justified. |
| `false_positive_rate` | string | **Per invoice, not per finding** — `false_positive_count ÷ invoice_count`. The zero-defect control is scored on this: over-flagging a clean dataset is the failure a recall-only view hides. |
| `duplicate_contention_count` | integer | Flags that lost a contest for the *same* expectation. See below. |
| `nonexistent_target_count` | integer | Flags naming an invoice or line that does not exist. See below. |
| `match_status_count` | integer | `MATCH` assertions submitted. **Not** false positives (D13). |
| `per_category` | object | One entry per category in the enumeration — always all of them, never only the exercised ones, so the key set is stable across datasets. |

Ratios are emitted as **strings**, quantized to four decimal places with `ROUND_HALF_UP`. Strings
because a float cannot represent `0.6667` exactly and byte-identity is required (D37). Read them
back with `parse_float=Decimal` if you intend to compute with them.

### The three false-positive counters are not alternatives

`false_positive_count` is the total. The other two are **diagnostics that partition part of it**,
and they mean different things about the agent:

- **`duplicate_contention_count`** — two or more flags contended for one expectation. Exactly one
  is credited as a true positive; the rest are false positives *and* counted here, because an
  agent emitting duplicates has a defect that an undifferentiated total would conceal (D26).
- **`nonexistent_target_count`** — a flag named a target absent from the dataset. That is a
  different defect: not a wrong judgement about a real line, but a reference to nothing.

Flags that merely share a match key for which the key holds **no** expectation are ordinary false
positives and are *not* counted as contention — contention means contending *for* an expectation,
and inflating the diagnostic would obscure what it exists to reveal (D55).

### `per_category.<CATEGORY>`

| Field | Type | Meaning |
|---|---|---|
| `true_positives` | integer | Flags matching an expectation. |
| `false_positives` | integer | Flags in this category with no matching expectation. |
| `false_negatives` | integer | Expectations in this category the agent did not produce. |
| `precision` | string or `null` | `null` when `true_positives + false_positives` is zero — the agent flagged nothing here. |
| `recall` | string or `null` | `null` when `true_positives + false_negatives` is zero — the dataset asked nothing here. |
| `expected_count` | integer | Expectations the key holds in this category. Equals `true_positives + false_negatives`. |
| `exercised_by_dataset` | boolean | `false` when `expected_count` is zero. The summary marks these rows inline. |

> **`precision: null` and `precision: "0.0000"` are different verdicts.** `null` means the agent
> submitted nothing in this category. `"0.0000"` means it submitted flags and every one was wrong.
> Zero read as failure where the result was undefined is the misreading D25 exists to stop.

---

## `missed` and `false_flags`

Both are arrays of finding-shaped objects, so a reader can see *what* was missed rather than only
how many.

| Field | Type | Meaning |
|---|---|---|
| `status` | string | `DISCREPANCY` or `MATCH`. |
| `category` | string | One of the five in the enumeration. |
| `scope` | string | `LINE` or `DOCUMENT`. |
| `target.document_id` | string | The **invoice** identifier — always the invoice, never the purchase order (D22). |
| `target.line_id` | string | The invoice line, or the sentinel `__DOCUMENT__` when `scope` is `DOCUMENT`. |
| `confidence` | number or `null` | Carried through if the agent supplied it. Not used in scoring at `[P1]`. |
| `reasoning` | string or `null` | Free text. On a **`missed`** entry this is the *answer key's* own note, not the agent's. |
| `reason` | string | **`false_flags` only** — why the flag was counted against the agent, e.g. a nonexistent target or lost contention. |

> **`missed[].reasoning` is answer-key content.** It states what the key expected and why. A
> scorecard from the **held-out** split therefore discloses expectations verbatim and must not be
> committed to this repository or the holdout repository — write it to the secret tier or outside
> all three (D93).

---

## `run_metadata`

| Field | Type | Meaning |
|---|---|---|
| `run_timestamp` | string | UTC ISO-8601, `Z`-suffixed, second precision (D6). |
| `load_ms` | integer | Milliseconds spent loading and validating the dataset. |
| `score_ms` | integer | Milliseconds spent scoring. |
| `total_ms` | integer | Milliseconds for the run. |

This block holds **exactly** the non-deterministic fields. Nothing here affects the verdict, and
excluding it makes two runs on the same inputs byte-identical. Elapsed time is reported, never
judged: exceeding a performance target warns and still exits zero, because how long scoring took
does not change whether it was right.

---

## What a scorecard deliberately does not contain

- **No judgement made at runtime.** Every expectation was loaded from the answer key; nothing was
  derived, inferred or asked of a model while scoring (D9).
- **No calibration verdict.** `confidence` is carried, not scored — a deferred addition.
- **No statement that the key is correct.** The key-audit command checks the key against an
  independent derivation, and reports *consistency*, not correctness — the generator and the
  auditor share an author, so agreement is evidence, not proof (D35).
- **No "cannot adjudicate" outcome.** An agent that correctly declines to decide — an invoice with
  no resolvable purchase order, a missing goods receipt — has no vocabulary for it and scores as
  having missed a finding. The datasets currently guarantee those cases absent (D96); the outcome
  class is scheduled (D97).
