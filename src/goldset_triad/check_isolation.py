"""Isolation checks — verify what is verifiable; attest the rest (D30).

Harness enforcement of a deny rule binds a tool call, which a subprocess runs
beneath — so a probe that tried to *open* the canary would always succeed and
would report failure whether the guards were perfect or absent, proving nothing.
This module therefore does NOT attempt that. It runs the two checks that ARE
deterministic:

1. **guard-configuration** — the repo's deny rules exist, parse, and cover every
   path in the secret tier (the secret directory, the answer-key filename, the
   generator filenames, the discrepancy-design artifact), while deliberately NOT
   covering the held-out inputs, which the agent must read (the D14 trap).
2. **placement** — no secret artifact exists anywhere inside the repository tree,
   including under ignored directories, since `.gitignore` hides a file from git
   but not from the filesystem.

Harness enforcement itself is attested manually in ``ISOLATION_ATTESTATION.md``.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

# Repo root is two levels up from this file's package: src/goldset_triad/ -> repo.
REPO_ROOT = Path(__file__).resolve().parents[2]
SETTINGS_PATH = REPO_ROOT / ".claude" / "settings.json"

# The secret directory name whose coverage every deny rule set must include, and
# the held-out inputs directory name that must NEVER be covered.
SECRET_DIR_NAME = "goldset-triad-secret"
HELDOUT_INPUTS_DIR_NAME = "goldset-triad-holdout"

# Names that only ever exist on the secret side; finding any inside the repo is a
# placement failure.
#
# These are compared CASE-INSENSITIVELY (see _is_secret_name), which is only safe
# because every name here is genuinely distinct from every public one -- not a case
# variant of it. An earlier design distinguished the held-out key from the public dev
# key by capitalisation alone ('ANSWER_KEY.json' vs 'answer_key.json'). That forced
# this comparison to stay case-sensitive, since case-folding would have flagged the
# legitimate dev keys as secret artifacts -- and a case-sensitive comparison cannot
# see a stray copy that arrives under different casing, which is exactly the leak
# this check exists to catch. Case cannot distinguish names on a case-insensitive
# filesystem, so it must never be load-bearing (D38).
SECRET_ARTIFACT_NAMES = frozenset(
    {
        "holdout_answer_key.json",
        # The held-out invoice index is agent-denied ground truth (D34) -- the extraction
        # answer. While it was named 'invoice_index.json' it collided with the three PUBLIC
        # dev indexes, so it could be listed here at all, and was protected by directory
        # placement alone: uniquely weaker than every other secret artifact (D45).
        "holdout_invoice_index.json",
        "gen_rules.py",
        "generate.py",
        "pdf_invoice.py",
        "discrepancy-plan.md",
    }
)

# Matched on the STEM (text before the first dot), so a compiled or backed-up copy is caught
# too: 'gen_rules.cpython-314.pyc' and 'gen_rules.py.bak' both stem to 'gen_rules'. Bytecode
# matters because a .pyc is decompilable and therefore carries the discrepancy-planting rule
# just as the source does -- __pycache__ exists in the generators directory today (D45).
_SECRET_STEMS = frozenset(n.lower().split(".", 1)[0] for n in SECRET_ARTIFACT_NAMES)


def _is_secret_name(name: str) -> bool:
    """Case-insensitive and extension-insensitive, so a stray copy under any casing or any
    extension is still caught."""
    return name.lower().split(".", 1)[0] in _SECRET_STEMS


SECRET_PATH_SEGMENTS = frozenset({SECRET_DIR_NAME, HELDOUT_INPUTS_DIR_NAME, "_generators"})

# Coverage the guard-configuration check requires, expressed as substrings that at
# least one deny rule must contain.
REQUIRED_COVERAGE = {
    "secret directory": SECRET_DIR_NAME,
    "answer-key filename": "holdout_answer_key.json",
    "invoice-index filename": "holdout_invoice_index.json",
    "generator gen_rules": "gen_rules.",
    "generator generate": "generate.",
    "generator pdf_invoice": "pdf_invoice.",
    "discrepancy-design artifact": "discrepancy-plan.md",
}


@dataclass(frozen=True)
class IsolationResult:
    guard_failures: tuple[str, ...]
    placement_failures: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.guard_failures and not self.placement_failures


def _deny_rules() -> list[str]:
    if not SETTINGS_PATH.is_file():
        raise FileNotFoundError(
            f"guard settings not found at {SETTINGS_PATH}; the deny-guards are unconfigured"
        )
    data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    deny = data.get("permissions", {}).get("deny", [])
    return [str(rule) for rule in deny]


def check_guard_configuration() -> list[str]:
    """Every secret path is covered; the held-out inputs are not (D30, D14)."""
    failures: list[str] = []
    rules = _deny_rules()
    joined = "\n".join(rules)
    for label, needle in REQUIRED_COVERAGE.items():
        if needle not in joined:
            failures.append(f"deny rules do not cover the {label} (no rule mentions '{needle}')")
    # The trap: a rule that covers the held-out INPUTS would silently break
    # evaluation. Assert none does.
    for rule in rules:
        if HELDOUT_INPUTS_DIR_NAME in rule:
            failures.append(
                f"a deny rule covers the held-out INPUTS, which must stay readable: {rule!r}"
            )
    return failures


def check_placement() -> list[str]:
    """No secret artifact exists anywhere in the repo tree, ignored dirs included."""
    failures: list[str] = []
    for dirpath, _dirnames, filenames in os.walk(REPO_ROOT):
        rel = Path(dirpath).relative_to(REPO_ROOT)
        parts = set(rel.parts)
        if parts & SECRET_PATH_SEGMENTS:
            failures.append(f"a secret-tier directory exists inside the repo: {rel}")
        for name in filenames:
            if _is_secret_name(name):
                failures.append(f"a secret artifact exists inside the repo: {rel / name}")
    return failures


def run() -> IsolationResult:
    return IsolationResult(
        guard_failures=tuple(check_guard_configuration()),
        placement_failures=tuple(check_placement()),
    )


def main(argv: list[str] | None = None) -> int:
    try:
        result = run()
    except FileNotFoundError as exc:
        sys.stderr.write(f"isolation check error: {exc}\n")
        return 2
    if result.ok:
        sys.stdout.write(
            "isolation: guard-configuration and placement checks PASS. "
            "Harness enforcement is attested separately (see ISOLATION_ATTESTATION.md); "
            "it is not tested by executing code, because a reachability probe cannot work (D30).\n"
        )
        return 0
    sys.stderr.write("ISOLATION CHECK FAILED:\n")
    for f in result.guard_failures:
        sys.stderr.write(f"  [guard-configuration] {f}\n")
    for f in result.placement_failures:
        sys.stderr.write(f"  [placement] {f}\n")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
