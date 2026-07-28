# Isolation attestation

This document records **what is checked by code, what is checked by a human, and what
neither can check** about keeping the held-out answer key away from the agent under
evaluation. It is deliberately conservative: the point of a golden-dataset harness is that
its claims survive scrutiny, so anything not actually verified is named as such (D30).

---

## The command: `goldset-triad-check-isolation`

**What it is.** A console script — a small command that runs the two automated isolation
checks. It is not a file you can find by browsing the repository: it is *declared* in
`pyproject.toml` and only comes into existence on your machine when the package is
installed. That is why searching the source tree for it turns up nothing.

```toml
[project.scripts]
goldset-triad-check-isolation = "goldset_triad.check_isolation:main"
```

**How to get it.** Install the package from the repository root. `-e` means *editable*:
the command points back at your working copy, so edits take effect without reinstalling.

**Linux / macOS — bash:**
```bash
cd goldset-triad-harness
python -m pip install -e .
goldset-triad-check-isolation
```

**Windows — PowerShell:**
```powershell
cd goldset-triad-harness
python -m pip install -e .
goldset-triad-check-isolation
```

**If you would rather not install anything**, the same code runs directly from the source
tree. `PYTHONPATH=src` is required, not optional — the package lives under `src/`, so
without it Python cannot find `goldset_triad` at all:

**Linux / macOS — bash:**
```bash
PYTHONPATH=src python -m goldset_triad.check_isolation
```

**Windows — PowerShell:**
```powershell
$env:PYTHONPATH = 'src'; python -m goldset_triad.check_isolation
```

**Exact purpose.** It answers one question — *are the isolation guards configured
correctly?* — and it is honest about being unable to answer a second one, *are they
being enforced?* It runs two checks and prints up to two kinds of advisory note.

| It checks | Meaning |
|---|---|
| **Guard configuration** | The deny rules exist, parse, and name every secret path — the secret directory, the held-out answer key, the held-out invoice index, the three generator files, the discrepancy-design artifact — **and do not name the held-out inputs**, which the agent must be able to read. |
| **Placement** | No secret artifact sits anywhere inside the repository tree, including under directories `.gitignore` hides — **and no scorecard from a non-public split**, since a held-out scorecard names expected findings verbatim and is answer-key content whatever its filename suggests (D93, D104). Checked on the filesystem rather than in the git index, because an untracked file is exactly as readable as a committed one. |

| It also reports (advisory, never changes the exit code) | Meaning |
|---|---|
| `[durability]` | An out-of-tree tier has uncommitted or unpushed work. Not a leak — a risk of losing the tier (D70, D71). |
| `[guard-reach]` | A directory *above* this repository carries its own Claude Code settings that do not cover the secret tier, so a session rooted there does not load these deny rules (D91). |

**Exit codes.** `0` — both checks pass. `1` — a check failed; the failing paths are named.
`2` — the command could not determine what to inspect (for example, run from an installed
copy with no checkout in sight), which it reports as *nothing was checked* rather than as a
failure, because naming a failure that did not occur is worse than silence (D50, D59).

**What it deliberately does not do.** It never opens the answer key, and it never tries to
prove the guards are being enforced. See the method below for why that is impossible from
inside a script.

---

## What is attested manually, and why it cannot be automated

**Harness enforcement of the deny rules.** Deny rules bind **tool calls**. A Python script
runs *beneath* that boundary, so a script that tried to `open()` the guarded file would
succeed every time — and would therefore report failure *identically* whether the guards
were perfect or entirely absent. Such a probe proves nothing while looking like
verification, which is the worst possible outcome for a credibility artifact (D30).

**Method:** open a Claude Code session **rooted at this repository directory** and attempt a
tool-level read of the canary:

- file: `goldset-triad-secret/canary/throwaway.json`
- marker: `CANARY_GTH_9F75AF06_GUARDED_DIR_REACHABLE`

The read must be **refused**, and the marker must never appear. The canary exists for this
purpose: it holds a unique marker and **no answer-key content**, so probing with it cannot
contaminate a session. It is covered only by the secret-*directory* rule and never by a
filename rule, so it exercises the weakest layer.

A positive control belongs with it: a tool-level read of a held-out *input* must **succeed**,
confirming the guards have not over-blocked the files the agent under test needs (D14, D65).

### How to run it — the exact procedure

**Step 1 — open a session rooted at this repository.** This is the part that matters. From a
terminal:

**Windows — PowerShell:**
```powershell
cd D:\Claude_Stuff\Claude_Desktop_Code_Projects\goldset-triad-harness
claude
```

**Linux / macOS — bash:**
```bash
cd ~/goldset-triad-harness
claude
```

Do **not** start from a parent folder. `cd`-ing afterwards does not help: the session root is
fixed when it launches, and the deny rules are loaded from that root.

**Step 2 — confirm the automated half first**, so a failure below is unambiguous:

**Windows — PowerShell:**
```powershell
goldset-triad-check-isolation
```

**Linux / macOS — bash:**
```bash
goldset-triad-check-isolation
```

Expect `guard-configuration and placement checks PASS`.

A `[guard-reach]` line may also appear. **It is not a verdict on your session** and it is not
a reason to stop. The command is a Python script reading the filesystem: it can see that some
ancestor directory carries its own Claude Code settings, and it cannot see where your session
was rooted. On this machine that ancestor exists and is *meant* to (D91), so the line is
permanent — it says only *"if a session were rooted there, these rules would not be loaded in
it"*.

This document previously told you to treat that line as proof of a mis-rooted session and to
stop until it cleared. It never clears, so the instruction could not be followed; it was
reading a conditional statement as an observation about the reader (D103). **What actually
establishes your session's root is step 1** — you opened it here — and step 3's outcome, which
is the only thing that can distinguish rules-loaded from rules-absent.

**Step 3 — the negative test.** In the Claude Code session, paste one of these — the path is
the only difference, and every other command in this document is given for both platforms, so
this one is too (D103):

> **Windows:** Read the file `D:\Claude_Stuff\goldset-triad-secret\canary\throwaway.json` and
> tell me exactly what happened — whether the read succeeded or was refused, and quote any
> error.

> **Linux / macOS:** Read the file `~/goldset-triad-secret/canary/throwaway.json` and tell me
> exactly what happened — whether the read succeeded or was refused, and quote any error.

| Result | Meaning |
|---|---|
| Refused, e.g. *"File is in a directory that is denied by your permission settings"*, no content shown | **PASS** — record it |
| Any content returned, or the marker `CANARY_GTH_9F75AF06_GUARDED_DIR_REACHABLE` appears | **FAIL** — the guards are not binding |

**Step 4 — the positive control.** In the same session:

> **Windows:** Read the file
> `D:\Claude_Stuff\goldset-triad-holdout\inputs\purchase_orders\PO-7001.json` and tell me
> whether it succeeded.

> **Linux / macOS:** Read the file
> `~/goldset-triad-holdout/inputs/purchase_orders/PO-7001.json` and tell me whether it
> succeeded.

This one **must succeed**. A refusal here means the guards over-block and evaluation is
broken, which is the D14 trap — as much a failure as a leak, in the opposite direction.

**Step 5 — record it.** Add a dated entry to the attestation log below with both outcomes,
the session's root directory, and the exact refusal text. Reading the canary is safe: it holds
a unique marker and no answer-key content, which is the entire reason it exists.

> **The session's root directory is load-bearing, and this was not always written down.**
> Claude Code loads permission settings from the session's own root. A session opened at a
> parent folder — a workspace holding several projects — loads *that* folder's settings, and
> the rules in `goldset-triad-harness/.claude/settings.json` are never read. The guards then
> do not apply, whatever they contain. `goldset-triad-check-isolation` reports which ancestor
> directories carry their own settings, so you can see *which* roots would miss these rules —
> but it cannot tell you where your own session was opened, so it can never confirm that you
> got step 1 right. Only step 3 can (D103).

---

## Attestation log

Newest first. Superseded entries are kept, because the record of what was believed and when
is part of what makes the claim auditable.

### 2026-07-28 (session rooted at the SECRET tier) — mirror guard **reads PASS, writes UNPROBED**

> **Heading corrected the same day (D122).** It read *"mirror guard **PASS**"*. Every probe below is a
> **read**. The guard's other half — writes into the published repository, which D120 itself calls *the only
> genuine leak route in a generator review* — was never attempted, so the unqualified PASS covered the easy
> half and claimed the hard one. Worse, half of that write rule was **inert**: each pattern was written both
> as `Edit(` and as `Write(`, and only `Edit(` is matched by file permission checks. The route was closed
> throughout because the pair contained the binding verb, but nothing here established that, and this entry
> asserted it. **Owed:** from a session rooted at the secret tier, attempt an edit to any file under
> `D:\Claude_Stuff\Claude_Desktop_Code_Projects\goldset-triad-harness` and record the refusal verbatim.

The first entry recording a session rooted at `goldset-triad-secret` rather than here. It is
in this log because it is an isolation result, and it tests the guard D120 added — the one
that did not exist until that decision, leaving a session at that root able to read the
held-out answer key and write into this repository.

| Probe | Result |
|---|---|
| `held-out/holdout_answer_key.json` | **Refused.** Verbatim: `File is in a directory that is denied by your permission settings.` |
| `design/discrepancy-plan.md` | **Refused.** Same message. |
| `_generators/gen_rules.py` | **Readable**, which is the point — reviewing it is what that root is for, and a guard that blocked it would make the review impossible (D65). |

**Why this entry matters more than a routine pass.** D120's checks read the guard *file*
from this side and confirm its rules cover the right paths. They cannot confirm the rules
**bind** — the same configuration-versus-enforcement distinction this whole document exists
to keep honest (D30). This is the secret-side counterpart of the canary test, and until it
was run the mirror guard was configuration nobody had seen work.

**And that argument is exactly why the missing write probe matters.** Having made the case
that reading a rule is not seeing it work, this entry then generalised from three reads to
the whole guard. The write direction has no canary — there is nothing to leave on disk that
a refused write would reveal — so it can only be attested by attempting one. Until that is
done, the row is absent from the table above rather than assumed into it (D122).

**Scope of the session that produced it.** It read `_generators/` and, read-only, this
repository's published `datasets/dev/matching_policy.json`. It did not open `held-out/`,
`worked-example/` or `design/`, and wrote nothing outside the private root. Its report was
written under an output contract requiring findings as *properties* — anything not already
present in `matching_policy.json` was not to appear — and the findings it carried back are
recorded in **D121**.

### 2026-07-27 (later, session rooted at this repository) — **PASS, all routes**

Run by the author from a Claude Code session rooted at
`D:\Claude_Stuff\Claude_Desktop_Code_Projects\goldset-triad-harness`, after the entry below
showed that a parent-rooted session loads none of these rules.

| Item | Result |
|---|---|
| Guard-configuration check | **PASS** |
| Placement check | **PASS** |
| **Tool-level read of the canary is refused** — the negative test D30 prescribes | **PASS — refused.** The marker `CANARY_GTH_9F75AF06_GUARDED_DIR_REACHABLE` did not surface. |
| **Tool-level read of a held-out input succeeds** — the positive control | **PASS — succeeded.** `goldset-triad-holdout\inputs\purchase_orders\PO-7001.json` read normally, so the guards do not over-block the files the agent under test needs (D14, D65). |

**Four further routes to the answer key itself, all refused** — broader than the method
requires, and volunteered by the author:

| Route | Target | Result |
|---|---|---|
| `Read` | `D:\Claude_Stuff\goldset-triad-secret\holdout_answer_key.json` | denied |
| `Read` | `…\goldset-triad-harness\goldset-triad-secret\holdout_answer_key.json` | denied |
| `Bash cat` | `D:/Claude_Stuff/goldset-triad-secret/holdout_answer_key.json` | denied |
| `Glob` | `**/holdout_answer_key.json` | no files found |

No key content was obtained by any route.

**Why the canary is the load-bearing one, and why those four do not replace it.** The answer
key is covered **three ways** — two directory rules and an unscoped filename rule — so a
refusal there cannot say *which* layer fired; the filename rule alone would produce it. The
canary carries **no filename rule at all** and is covered by the directory rule only, which
is why D17 placed it that way: it is the one file that isolates the weakest layer. Refusing
it proves the directory rule binds, and everything else in the tier rests on that.

*(The `Glob` line is the placement check passing rather than a guard result: from a session
rooted here, glob searches this tree, where the key correctly does not exist.)*

**What this pair of entries establishes together.** Two runs, the same day, the same machine,
the same rules on disk, **opposite results** — differing only in the directory the session was
opened from. That is D91 demonstrated rather than argued: the deny rules bind, and they bind
**only** a session rooted at this repository. The enforcement half of this attestation is
sound, and it is sound conditionally.

---

### 2026-07-27 (earlier, session rooted one level above) — enforcement half **FAILED in this configuration**

| Item | Result |
|---|---|
| Guard-configuration check | **PASS** — `PYTHONPATH=src python -m goldset_triad.check_isolation`, package not installed. |
| Placement check | **PASS** — same run. |
| Tool-level read of the canary is refused | **FAILED — the read succeeded.** The marker `CANARY_GTH_9F75AF06_GUARDED_DIR_REACHABLE` surfaced in the session's context. |
| Cause | The session was rooted at `D:\Claude_Stuff\Claude_Desktop_Code_Projects`, **one directory above this repository**. That directory's `.claude/settings.local.json` carries an `allow` list and **zero deny rules**, so this repository's deny-guards were never loaded. The rules did not fail to match; they were not in force. |
| Related | The same absence explains a generator invocation earlier the same day that ran without being refused (D90), which had been recorded as an open question. |
| Contamination | **None.** The canary holds no answer-key content by design, which is the entire reason it exists. No answer key, generator source or design artifact was read. |
| Standing | Placement — the **primary** control (D14, D30) — was unaffected throughout: the whole held-out split remains outside this tree. The **second** layer was absent for the duration of that session. |

**Action:** a `[guard-reach]` advisory now reports this condition whenever isolation is
checked (D91). Re-attestation from a correctly-rooted session was required before the
enforcement half could be claimed again — **done, and passing, in the entry above.**

### 2026-07-26 — enforcement half verified *(superseded by the entry above)*

| Item | Result |
|---|---|
| Guard-configuration check | **PASS** — `PYTHONPATH=src python -m goldset_triad.check_isolation`, package not installed. |
| Placement check | **PASS** — same run. |
| Tool-level read of the canary is refused | **VERIFIED** — a Claude Code session rooted at the repository directory attempted a tool-level Read of `goldset-triad-secret/canary/throwaway.json`; the call was refused at the tool-call layer (`File is in a directory that is denied by your permission settings`) with no content returned, so the marker never surfaced. |
| Tool-level read of a held-out input succeeds — positive control | **VERIFIED** — from the same session, a Read of `goldset-triad-holdout/inputs/purchase_orders/PO-7001.json` succeeded, confirming the deny rules leave the held-out inputs readable. |

This entry is **not withdrawn**: it remains the evidence that the rules *do* bind when
loaded. What the 2026-07-27 entry adds is that whether they are loaded depends on where the
session was opened — a precondition this document did not previously state.

---

## Honest limits of the whole claim (D30)

- Placement and guard configuration are **checked automatically**, by the test suite — which
  CI runs **on every push**, and which you can run locally at any time. This line named the
  commit rather than the push until D105; no commit hook runs these checks, and overstating
  by one step is exactly what this document exists not to do.
- Harness enforcement is **attested by a human**, never code-tested, for the reason above.
- A determined subprocess is **outside deny coverage by design** — which is exactly why
  placement outside the repository tree is the primary control and the deny rules are the
  second layer.
- The deny rules bind only a session rooted at this repository (D91). This is not a
  hypothesis: the two entries above are the same rules, the same machine and the same day,
  passing from one root and absent from another.

**Standing status as of 2026-07-27:** both automated checks PASS; the enforcement half is
**attested PASS from a repository-rooted session**, including the canary negative test and
the held-out-input positive control. It is *not* claimed for sessions rooted elsewhere, and
`goldset-triad-check-isolation` prints a `[guard-reach]` line when that is the case.
