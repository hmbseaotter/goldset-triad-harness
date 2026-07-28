# Runbook — how to actually use this thing

Written for someone who has never seen this project. Every command is given for **Windows
(PowerShell)** and **Linux/macOS (bash)**. If you only ever read one section, read
[§1](#1-first-ten-minutes-prove-it-works) — it proves the tool works on your machine before
you try anything real.

**Conventions used throughout**

- *"From the repo root"* means the folder containing `pyproject.toml`.
- Lines beginning `#` are comments, not commands.
- `>` output shown after a command is what you should expect to see.

> ### ⚠ Read this before you start: launch AI agents from the harness folder
>
> The deny-guards that keep the answer key out of an agent's reach live in
> `goldset-triad-harness/.claude/settings.json`. An agent session loads its permission
> settings from **its own root directory**, so a session opened at a parent folder — a
> workspace holding several projects — never reads them, and the guards do not bind.
>
> **Windows — PowerShell:**
> ```powershell
> cd D:\Claude_Stuff\Claude_Desktop_Code_Projects\goldset-triad-harness
> claude
> ```
>
> **Linux / macOS — bash:**
> ```bash
> cd ~/goldset-triad-harness
> claude
> ```
>
> `cd`-ing after launch does not help — the root is fixed when the session starts. Placement
> of the held-out split outside this tree is the **primary** control and holds regardless;
> this is the second layer. Run `goldset-triad-check-isolation` (§2.5) if in doubt: a
> `[guard-reach]` line means the guards are not in force (D91).

---

## 0. Which repository is which

There are **three**, and mixing them up is the one mistake that matters.

| Repository | Where | Holds | The one rule |
|---|---|---|---|
| **goldset-triad-harness** | `D:\Claude_Stuff\Claude_Desktop_Code_Projects\goldset-triad-harness` | The scorer, the tests, and the **public dev split** | Safe to publish. This is the portfolio artifact. |
| **goldset-triad-holdout** | `D:\Claude_Stuff\goldset-triad-holdout` | The held-out **inputs** the agent reads | **Never publish.** The agent may read these; the world may not. |
| **goldset-triad-secret** | `D:\Claude_Stuff\goldset-triad-secret` | The held-out **answer key**, the generators, the discrepancy design | **Never publish, never copy into the harness repo.** |

**Why the holdout inputs cannot be published even though the agent reads them.** The
matching policy is published deliberately, so an agent can compete against rules it can
read. Those inputs *plus* that policy are enough to derive the answer key mechanically —
which is exactly what the audit command does. *Readable by the agent* and *publishable* are
different properties, and only the first applies.

---

## 1. First ten minutes: prove it works

Nothing here touches the held-out data. You are running the public dev split.

### 1.1 Check your prerequisites

You need **Python 3.11 or newer**. Nothing else — the scorer has zero runtime dependencies.

**Windows — PowerShell:**
```powershell
python --version
```

**Linux / macOS — bash:**
```bash
python3 --version
```

> If Windows opens the Microsoft Store instead of printing a version, Python is not
> installed. Get it from python.org and tick **"Add python.exe to PATH"** during setup.

On Linux, substitute `python3` for `python` in every command below if plain `python` is not
on your system.

### 1.2 Install the harness

`-e` means *editable*: the commands point back at your working copy, so edits take effect
without reinstalling.

**Windows — PowerShell:**
```powershell
cd D:\Claude_Stuff\Claude_Desktop_Code_Projects\goldset-triad-harness
python -m pip install -e .
```

**Linux / macOS — bash:**
```bash
cd ~/goldset-triad-harness
python3 -m pip install -e .
```

This creates three commands: `goldset-triad`, `goldset-triad-audit-key` and
`goldset-triad-check-isolation`.

> **Prefer not to install?** Every command also runs from source, but you must put `src` on
> the import path, because the package lives there. See [§5.1](#51-modulenotfounderror-no-module-named-goldset_triad).

### 1.3 Score something

The repository ships a worked example you can copy — see
[README → *A worked example*](../README.md#a-worked-example-what-you-give-it-and-what-you-get-back).
Save it as `findings.json`, then:

**Windows — PowerShell:**
```powershell
goldset-triad score --dataset dev --findings .\findings.json --out .\scorecards
```

**Linux / macOS — bash:**
```bash
goldset-triad score --dataset dev --findings ./findings.json --out ./scorecards
```

You should see a summary printed, ending with the path of the scorecard it wrote.

**To read what it says, keep [docs/SCORECARD.md](SCORECARD.md) open beside it.** That is the
field-by-field reference: what `TP`, `FP`, `FN`, `P` and `R` stand for, what each JSON field
means, and — for the handful whose obvious reading is the wrong one — what the wrong reading
would be. Two worth knowing before you draw any conclusion: `false_positive_rate` is per
*invoice*, not per finding; and `P n/a` is not the same as `P 0.0000` — the first means the
agent flagged nothing in that category, the second means everything it flagged was wrong.

### 1.4 Confirm the harness is honest about itself

Re-score the same inputs and check the result can be reproduced:

**Windows — PowerShell:**
```powershell
goldset-triad verify --scorecard .\scorecards\<the-file-it-just-wrote>.json `
  --dataset dev --findings .\findings.json
```

**Linux / macOS — bash:**
```bash
goldset-triad verify --scorecard ./scorecards/<the-file-it-just-wrote>.json \
  --dataset dev --findings ./findings.json
```

> `verify: identical - recomputed from the same inputs and every scored field matches...`

That is the whole point of the tool: **a scorecard never has to be trusted, because it can
be recomputed.**

---

## 2. Everyday tasks

### 2.1 Score an agent's findings

**Windows — PowerShell:**
```powershell
goldset-triad score --dataset dev --findings .\findings.json --out .\scorecards
```

**Linux / macOS — bash:**
```bash
goldset-triad score --dataset dev --findings ./findings.json --out ./scorecards
```

`--dataset` takes either a **name** (`dev`, `dev-synthetic`, `dev-zero-defect`) or a **path
to a `manifest.json`**, which is how you reach the held-out split:

**Windows — PowerShell:**
```powershell
goldset-triad score --dataset D:\Claude_Stuff\goldset-triad-secret\held-out\manifest.json `
  --findings .\findings.json --out .\scorecards
```

**Linux / macOS — bash:**
```bash
goldset-triad score --dataset ~/goldset-triad-secret/held-out/manifest.json \
  --findings ./findings.json --out ./scorecards
```

### 2.2 Verify a stored scorecard

**Windows — PowerShell:**
```powershell
goldset-triad verify --scorecard .\scorecards\scorecard-dev-20260727T090320Z.json `
  --dataset dev --findings .\findings.json
```

**Linux / macOS — bash:**
```bash
goldset-triad verify --scorecard ./scorecards/scorecard-dev-20260727T090320Z.json \
  --dataset dev --findings ./findings.json
```

You must name the dataset and findings again: a scorecard records *fingerprints*, not paths.
A digest confirms identity; it cannot locate a file.

**What the answers mean** — verify reports the **first** applicable outcome and stops:

| Outcome | What happened | What to do |
|---|---|---|
| `identical` | Everything matches. | Nothing. |
| `dataset-mismatch` | You pointed it at a different split. | Re-run with the identifier it prints. |
| `schema-unrecognised` | The scorecard was written by a different version. | Re-score to get a comparable card. Not a scoring problem. |
| `fingerprint-mismatch` | The inputs moved since the score. | Find what changed — add `--baseline-inputs` (below). |
| `score-differs` | Same inputs, different numbers. | This is the real one. Investigate. |

To find *which* input file changed, give it a clean copy to compare against:

**Windows — PowerShell:**
```powershell
goldset-triad verify --scorecard .\scorecards\<file>.json --dataset dev `
  --findings .\findings.json --baseline-inputs .\datasets\dev\inputs
```

**Linux / macOS — bash:**
```bash
goldset-triad verify --scorecard ./scorecards/<file>.json --dataset dev \
  --findings ./findings.json --baseline-inputs ./datasets/dev/inputs
```

### 2.3 Rebuild the run ledger

The ledger (`run-ledger.jsonl`) is a convenience log of every run. It is derived, so deleting
it loses nothing:

**Windows — PowerShell:**
```powershell
goldset-triad rebuild-ledger --out .\scorecards
```

**Linux / macOS — bash:**
```bash
goldset-triad rebuild-ledger --out ./scorecards
```

### 2.4 Check an answer key against an independent derivation

**Windows — PowerShell:**
```powershell
goldset-triad-audit-key --dataset dev
```

**Linux / macOS — bash:**
```bash
goldset-triad-audit-key --dataset dev
```

> `key audit: consistent - every declared finding is independently derivable...`

This is a **consistency check, not a proof of correctness** — the generator and the auditor
share an author, so it catches arithmetic slips and drift, not a shared misunderstanding.

### 2.5 Check the isolation guards

**Windows — PowerShell:**
```powershell
goldset-triad-check-isolation
```

**Linux / macOS — bash:**
```bash
goldset-triad-check-isolation
```

See [`ISOLATION_ATTESTATION.md`](../ISOLATION_ATTESTATION.md) for what it does and does not
prove.

Two things it reports are worth knowing before you meet them:

- A **`[guard-reach]`** line is advisory and never changes the exit code. It says some folder
  *above* this one carries its own Claude Code settings, so a session rooted **there** would
  not load these deny rules. It is not a statement about the session you are in (D103).
- A **`[placement]` failure naming a scorecard** is a real failure, exit 1, and it means a
  held-out scorecard is sitting in this tree. §5.8 has the fix.

### 2.6 The held-out workflow, end to end

This is the run that actually measures an agent. Everything above used the public dev split,
where you can see the answers; here you cannot, which is the entire point.

> ### ⚠ A held-out scorecard must never be committed to this repository
>
> Scorecards are normally the durable record and **are** committed — but that rule was
> written for the dev split. A held-out scorecard is different: its `missed` array names
> every expectation the agent failed to find, with the category, the invoice, the line, and
> the generator's own note (`"seeded TAX_VARIANCE on INV-2003"`). **That is answer-key
> content.** Even with zero misses, the `coverage` block reveals which categories the key
> exercises and how many expectations it holds.
>
> Write held-out scorecards **outside this repository**, and keep them there (D93).

#### Step 1 — your agent reads the held-out inputs and writes findings

The agent reads `D:\Claude_Stuff\goldset-triad-holdout\inputs\`. It never sees the key. Its
output is an ordinary `findings.json`, exactly the shape shown in the
[README's worked example](../README.md#what-you-give-it--the-findings-artifact).

#### Step 2 — score it, writing the scorecard outside the repo

**Windows — PowerShell:**
```powershell
goldset-triad score `
  --dataset D:\Claude_Stuff\goldset-triad-secret\held-out\manifest.json `
  --findings D:\Claude_Stuff\agent-runs\findings.json `
  --out D:\Claude_Stuff\agent-runs\scorecards
```

**Linux / macOS — bash:**
```bash
goldset-triad score \
  --dataset ~/goldset-triad-secret/held-out/manifest.json \
  --findings ~/agent-runs/findings.json \
  --out ~/agent-runs/scorecards
```

Note `--out`: it points **outside** the harness repository, so no held-out scorecard is ever
written here in the first place — which is stronger than not committing one, because a file
sitting untracked in this tree is still readable by whatever agent works in it.

**If you forget it, the harness tells you — afterwards, not at the time.** The score still
runs and the scorecard is still written; it is `goldset-triad-check-isolation` that then
fails, and the test suite with it. See §5.8 for the exact message and what to do.

#### Step 3 — read a thin-coverage scorecard

The held-out split is small, so most categories hold no expectations at all. The scorecard
says so rather than leaving you to infer it. Below is the **same shape**, produced from the
public `dev-synthetic` split so it can be printed here safely:

```text
Per-category (precision / recall):
  PRICE_VARIANCE         TP 0  FP 0  FN 1   P n/a  R 0.0000
  QTY_UNDER_SHIPMENT     TP 0  FP 0  FN 0   P n/a  R n/a   [not exercised by this dataset]
  QTY_OVER_SHIPMENT      TP 0  FP 0  FN 0   P n/a  R n/a   [not exercised by this dataset]
  QTY_INVOICE_INFLATED   TP 0  FP 0  FN 0   P n/a  R n/a   [not exercised by this dataset]
  TAX_VARIANCE           TP 0  FP 0  FN 0   P n/a  R n/a   [not exercised by this dataset]

COVERAGE: this dataset exercises 1 of 5 categories (1 expected finding(s)). NOT measured: QTY_UNDER_SHIPMENT, QTY_OVER_SHIPMENT, QTY_INVOICE_INFLATED, TAX_VARIANCE. Their null metrics mean the data lacks these cases, NOT that the agent handled them correctly.
```

The `COVERAGE:` line really is one long line; your terminal wraps it where its width falls. It
was shown here hand-wrapped at three lines until D102 compared this block against a real run.

Reproduce that yourself with:

**Windows — PowerShell:**
```powershell
# `-Encoding ascii` avoids a byte-order mark. A BOM is accepted anyway (§5.6, D94),
# but it changes the file's bytes and so its fingerprint -- keep it out on purpose.
'{"schema_version":"1","findings":[]}' | Out-File -Encoding ascii empty.json
goldset-triad score --dataset dev-synthetic --findings .\empty.json --out .\scorecards
```

**Linux / macOS — bash:**
```bash
echo '{"schema_version":"1","findings":[]}' > empty.json
goldset-triad score --dataset dev-synthetic --findings ./empty.json --out ./scorecards
```

**How to read it.** Four rows show `P n/a  R n/a  [not exercised]`. That is **not** a perfect
score in those categories — it means the dataset never asked. A row of `n/a` and a row of
`1.0000` look equally clean at a glance and mean opposite things, which is why the harness
spells out the consequence in words rather than trusting you to notice.

#### Step 4 — verify the result later

Held-out numbers are the ones that carry weight, so they are the ones most worth being able
to re-derive:

**Windows — PowerShell:**
```powershell
goldset-triad verify `
  --scorecard D:\Claude_Stuff\agent-runs\scorecards\<file>.json `
  --dataset D:\Claude_Stuff\goldset-triad-secret\held-out\manifest.json `
  --findings D:\Claude_Stuff\agent-runs\findings.json
```

**Linux / macOS — bash:**
```bash
goldset-triad verify \
  --scorecard ~/agent-runs/scorecards/<file>.json \
  --dataset ~/goldset-triad-secret/held-out/manifest.json \
  --findings ~/agent-runs/findings.json
```

This is why losing the holdout inputs is unrecoverable: the scorecard embeds a digest of
exactly those bytes, and without them there is nothing left to recompute against.

### 2.7 Run the test suite

**Windows — PowerShell:**
```powershell
python -m unittest discover -s tests -t .
```

**Linux / macOS — bash:**
```bash
python3 -m unittest discover -s tests -t .
```

Some tests **skip** when the secret tier is not on your machine. That is by design, not a
failure.

---

## 3. Regenerating the datasets

**Read this whole section before running anything.** The generator **overwrites dataset
files** in all three repositories.

### 3.1 When you need to

Only when a **rule** changed — a threshold, a category, the shape of a document. Editing a
dataset file by hand is never the answer: the generator is the source of truth, and the next
run silently reverts hand edits.

### 3.2 Before you run it

Make sure every repository is committed and clean, so the regeneration is a reviewable diff
and you can undo it:

**Windows — PowerShell:**
```powershell
git -C D:\Claude_Stuff\Claude_Desktop_Code_Projects\goldset-triad-harness status --short
git -C D:\Claude_Stuff\goldset-triad-holdout status --short
git -C D:\Claude_Stuff\goldset-triad-secret status --short
```

**Linux / macOS — bash:**
```bash
git -C ~/goldset-triad-harness status --short
git -C ~/goldset-triad-holdout status --short
git -C ~/goldset-triad-secret status --short
```

**All three must print nothing.** If any shows changes, commit or stash them first — an
empty output is what makes step 3.4 meaningful.

### 3.3 Run it

**Windows — PowerShell:**
```powershell
cd D:\Claude_Stuff\goldset-triad-secret\_generators
python generate.py
```

**Linux / macOS — bash:**
```bash
cd ~/goldset-triad-secret/_generators
python3 generate.py
```

> ```
> emitted dev: 9 expected finding(s), 4 invoice(s)
> emitted dev-synthetic: 1 expected finding(s), 1 invoice(s)
> emitted dev-zero-defect: 0 expected finding(s), 1 invoice(s)
> emitted held-out: 2 expected finding(s), 1 invoice(s)
> ```

### 3.4 Check what changed

**Windows — PowerShell:**
```powershell
git -C D:\Claude_Stuff\Claude_Desktop_Code_Projects\goldset-triad-harness status --short
```

**Linux / macOS — bash:**
```bash
git -C ~/goldset-triad-harness status --short
```

- **Nothing listed** → generation is reproducible and no rule changed. This is the expected
  result when you have changed nothing, and it is worth running occasionally just to confirm
  it still holds.
- **Files listed** → review the diff before committing. If you did not change a rule, a diff
  means something is wrong: generation is supposed to be byte-for-byte repeatable from the
  same seed.

### 3.5 Afterwards

Re-run the audit and the suite, then commit all three repositories:

**Windows — PowerShell:**
```powershell
cd D:\Claude_Stuff\Claude_Desktop_Code_Projects\goldset-triad-harness
goldset-triad-audit-key --dataset dev
python -m unittest discover -s tests -t .
```

**Linux / macOS — bash:**
```bash
cd ~/goldset-triad-harness
goldset-triad-audit-key --dataset dev
python3 -m unittest discover -s tests -t .
```

---

## 4. The other two repositories

### 4.1 goldset-triad-holdout — the held-out inputs

Documents the agent under evaluation reads: purchase orders, goods receipts, invoice PDFs.
**There is nothing to run here.** You point the harness at the held-out manifest (§2.1); the
files themselves are just read.

Keep it committed, for one specific reason: a scorecard embeds a digest of *exactly these
bytes*, so if you lose them, every held-out result becomes permanently unverifiable.

**Windows — PowerShell:**
```powershell
git -C D:\Claude_Stuff\goldset-triad-holdout add -A; git -C D:\Claude_Stuff\goldset-triad-holdout commit -m "..."
```

**Linux / macOS — bash:**
```bash
git -C ~/goldset-triad-holdout add -A && git -C ~/goldset-triad-holdout commit -m "..."
```

### 4.2 goldset-triad-secret — the answer key and generators

| Folder | What it is |
|---|---|
| `held-out/` | The held-out answer key, invoice index and manifest |
| `_generators/` | `generate.py`, `gen_rules.py`, `pdf_invoice.py` — how the data is made |
| `design/` | The discrepancy plan: where errors were deliberately placed |
| `canary/` | A decoy file used by the isolation attestation |
| `_guard-template.settings.json` | The **source of truth** for the deny rules |

**If you edit the guard template, re-stamp it into the harness repo.** The harness's
`.claude/settings.json` is a *copy*; the template is authoritative, and a check compares
them.

The only thing you *run* here is the generator (§3).

---

## 5. Troubleshooting — the errors you will actually see

### 5.1 `ModuleNotFoundError: No module named 'goldset_triad'`

You are running from source without installing. The package lives under `src/`, which is not
on Python's path by default. Either install it (§1.2) or set the path:

**Windows — PowerShell:**
```powershell
$env:PYTHONPATH = 'src'; python -m goldset_triad.check_isolation
```

**Linux / macOS — bash:**
```bash
PYTHONPATH=src python3 -m goldset_triad.check_isolation
```

### 5.2 `confidence, when present, must be a number between 0 and 1`

In **findings.json**, confidence is a JSON **number**, not a string:

```jsonc
"confidence": 0.95     // correct
"confidence": "0.95"   // rejected
```

(Confusingly, the *scorecard* emits numbers as strings — deliberately, so the output bytes
are exact. Input and output differ here on purpose.)

### 5.3 `dataset 'xyz' not found (looked for manifest at ...)`

`--dataset` takes a name found under `datasets/`, or a full path to a `manifest.json`. The
message prints exactly where it looked.

### 5.4 `error: ... is not UTF-8 text`

You pointed the harness at something that is not a text file — a PDF or a zip, usually a
wrong path. It names the file and the byte offset.

### 5.5 A halt with no scorecard written

By design. Any integrity failure stops the run and writes nothing: a distorted score is worse
than no score. The message names the specific cause.

### 5.6 A byte-order mark in your JSON — no longer a problem

**A leading UTF-8 BOM is accepted** (D94). Windows tooling adds one freely — `Out-File
-Encoding utf8` on PowerShell 5.1 does it despite the name, and so does Notepad's "UTF-8" —
and the harness reads with `utf-8-sig`, which strips a BOM when present and changes nothing
when it is not.

This is listed because earlier versions rejected it with
`findings artifact is not valid JSON: ... (Unexpected UTF-8 BOM)`. If you see that message,
you are on a build from before this change; either update, or write the file without a BOM:

**Windows — PowerShell:**
```powershell
'{"schema_version":"1","findings":[]}' | Out-File -Encoding ascii empty.json
[IO.File]::WriteAllText("$PWD\empty.json", '{"schema_version":"1","findings":[]}')
```

**Linux / macOS — bash:**
```bash
echo '{"schema_version":"1","findings":[]}' > empty.json
```

Note that a BOM'd file and a clean one are genuinely **different bytes**, so they fingerprint
differently in a scorecard. That is correct and deliberate: what widened is what the harness
*accepts*, not what it treats as the same input.

### 5.7 Tests "skipped"

Expected when the secret tier is absent — those tests need out-of-tree data. A clone without
it still passes the full suite.

### 5.8 `[placement] a scorecard from the 'held-out' split exists inside the repo`

The most likely way to meet this is scoring the held-out split with `--out` left at its
default, so the scorecard landed in `scorecards/` here instead of outside the repo (§2.6).

`goldset-triad-check-isolation` exits **1** and prints:

```text
ISOLATION CHECK FAILED:
  [placement] a scorecard from the 'held-out' split exists inside the repo: scorecards\scorecard-held-out-20260728T000000Z.json. It names expected findings verbatim, so it is answer-key content wearing a results file's name (D93). Re-run with --out pointing outside this repository, and delete this copy
```

**The test suite goes red at the same time** — three tests, including one about repository-root
resolution whose subject looks unrelated. If you are staring at a puzzling suite failure, run
the isolation check first: it names the cause in one line.

**The fix**, in order:

1. **Delete the scorecard from this tree.** It is answer-key content, and being untracked does
   not help — a file merely ignored or untracked is still on disk and still readable by an
   agent working here, which is the whole reason this is checked on the filesystem rather than
   in the git index (D104).
2. **Re-run the score with `--out` pointing outside the repository** (§2.6, Step 2). Nothing is
   lost: scoring is deterministic, so the same inputs produce the same scorecard.
3. **If you already committed it**, deleting the file is not enough — treat the held-out key as
   compromised and regenerate the split (§6, rule 6). It is in history.

This fires on *presence*, not on tracking, and only for splits whose keys are not public. Dev,
dev-synthetic and dev-zero-defect scorecards belong here and are left alone.

---

## 6. Safety rules

1. **Never copy anything from `goldset-triad-secret` into the harness repository.** Not the
   key, not the generators, not the design notes. `.gitignore` is not protection: it hides a
   file from git, not from the filesystem or from a reading agent.
2. **Never publish `goldset-triad-holdout`.** Its inputs plus the published policy are enough
   to derive the key.
3. **Never hand-edit a dataset file.** Change the generator and regenerate (§3).
4. **Never delete a scorecard.** They are the durable record. The harness itself cannot
   overwrite one — it creates files exclusively, so the operating system refuses.
5. **Never let a held-out scorecard exist inside this repository** — not committed, and not
   sitting untracked either. Its `missed` array names expectations verbatim — category,
   invoice, line, and the generator's own note — so it is answer-key content wearing a results
   file's name, and an untracked file is exactly as readable to an agent working here as a
   committed one. Point `--out` outside the repo (§2.6). The isolation check enforces this on
   the filesystem and fails if one appears (§5.8, D104).
6. **If a key ever lands in public git history, treat it as permanently compromised.**
   Rewriting history does not reliably remove it; regenerate the held-out split instead.

---

## 7. Where files land

| Thing | Default location | Committed? |
|---|---|---|
| Scorecards from a **dev** split | `scorecards/` (or `--out`) | **Yes** — the durable record |
| Scorecards from the **held-out** split | wherever `--out` points, **outside this repo** | **Never here** — they contain answer-key content (§2.6, D93) |
| Run ledger (`run-ledger.jsonl`) | beside the scorecards | No — derived, gitignored |
| Dev split | `datasets/dev/` | Yes — public by design |
| Held-out answer key | `goldset-triad-secret/held-out/` | Yes, in *that* repo only |

Two runs in the same second do not collide: the second gets an ordinal suffix
(`...-2.json`), and no scorecard is ever overwritten.
