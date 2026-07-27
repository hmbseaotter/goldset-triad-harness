# Isolation attestation

**Method:** deny-guards in this repo's `.claude/settings.json`, enforced by Claude
Code at the tool-call layer, plus placement of the entire held-out split outside
the repository tree.

**What is verified automatically** (run `goldset-triad-check-isolation`, or `python -m goldset_triad.check_isolation` from a source checkout — D59 declared the console script so the advertised command exists; both routes run the same checks):

- **Guard-configuration check** — the deny rules exist, parse, and cover every path
  in the secret tier (the secret directory, the held-out answer-key filename, the
  three generator filenames, the discrepancy-design artifact), while deliberately
  NOT covering the held-out inputs directory, which the agent-under-test must read.
- **Placement check** — no secret artifact exists at any path inside the repository
  tree, including under ignored directories.

**What is attested manually** — harness enforcement of the deny rules. This is NOT
tested by executing code: deny rules bind tool calls, while a subprocess runs
beneath that boundary, so a reachability probe would report failure unconditionally
and prove nothing (D30). The correct test is to open a Claude Code session **rooted
in this repository** and attempt a tool-level read of the canary
(`goldset-triad-secret/canary/throwaway.json`, marker
`CANARY_GTH_9F75AF06_GUARDED_DIR_REACHABLE`); the read must be refused.

| Item | Status |
|---|---|
| Guard-configuration check passes | **PASS** — `python -m goldset_triad.check_isolation` (run with `PYTHONPATH=src`, package not installed), 2026-07-26. |
| Placement check passes | **PASS** — same run, 2026-07-26. |
| Tool-level read of the canary is refused (repo-rooted session) | **VERIFIED 2026-07-26** — a Claude Code session rooted at the repository directory attempted a tool-level Read of `goldset-triad-secret/canary/throwaway.json`; the call was refused at the tool-call layer (`File is in a directory that is denied by your permission settings`) with no content returned, so the `CANARY_GTH_9F75AF06_GUARDED_DIR_REACHABLE` marker never surfaced. |
| Tool-level read of a held-out input succeeds (repo-rooted session) — positive control that the guards do not over-block | **VERIFIED 2026-07-26** — from the same repo-rooted session, a tool-level Read of `goldset-triad-holdout/inputs/purchase_orders/PO-7001.json` succeeded, confirming the deny rules leave the held-out inputs directory readable by the agent-under-test. |

**Honest limits of this claim** (D30): placement and guard configuration are
checked automatically; harness enforcement is attested, not code-tested; and a
determined subprocess is outside deny coverage by design — which is exactly why
placement outside the tree is the primary control.

- **Attestation date:** 2026-07-26 (automated guard-configuration and placement
  checks run and PASS; harness-enforcement half now verified from a repo-rooted
  session — canary read refused at the tool-call layer, no content returned).
