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

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Final

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


# The generator stems whose Bash patterns must stay anchored (D65). Derived from the
# artifact names above so a new generator file cannot be added here and forgotten there.
GENERATOR_STEMS: Final = tuple(
    sorted(n.split(".", 1)[0] for n in SECRET_ARTIFACT_NAMES if n.endswith(".py"))
)

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


def looks_like_checkout(path: Path) -> bool:
    """Whether ``path`` is a harness source checkout (D59).

    Deliberately does NOT test for ``.claude/settings.json``: a missing settings file is a
    genuine isolation failure this tool must report, so using its presence to decide
    whether to look here at all would convert that failure into a silent redirect."""
    return (path / "pyproject.toml").is_file() and (path / "src" / "goldset_triad").is_dir()


def _deny_rules(root: Path) -> list[str]:
    settings_path = root / ".claude" / "settings.json"
    if not settings_path.is_file():
        raise FileNotFoundError(
            f"guard settings not found at {settings_path}; the deny-guards are unconfigured"
        )
    data = json.loads(settings_path.read_text(encoding="utf-8"))
    deny = data.get("permissions", {}).get("deny", [])
    return [str(rule) for rule in deny]


def check_guard_configuration(root: Path | None = None) -> list[str]:
    """Every secret path is covered; the held-out inputs are not (D30, D14)."""
    failures: list[str] = []
    rules = _deny_rules(REPO_ROOT if root is None else root)
    joined = "\n".join(rules)
    for label, needle in REQUIRED_COVERAGE.items():
        if needle not in joined:
            failures.append(f"deny rules do not cover the {label} (no rule mentions '{needle}')")
    # Over-breadth is its own failure class, not a milder version of under-coverage
    # (D65). An unanchored generator pattern such as `Bash(*generate.*)` matches the
    # substring inside ordinary words -- `bash regenerate.sh`,
    # `npm run pregenerate.build`, `git log --grep=generate.py` -- and "regenerate" is
    # this project's own workflow verb. Such a rule leaks nothing; it obstructs, and a
    # guard that obstructs routine work is one people switch off. Each generator stem
    # must therefore be anchored on a separator or a space, never left bare.
    for rule in rules:
        if not rule.startswith("Bash("):
            continue
        pattern = rule[len("Bash("):-1]
        for stem in GENERATOR_STEMS:
            bare = f"*{stem}."
            if pattern.startswith(bare):
                failures.append(
                    f"deny rule {rule!r} is unanchored: '{bare}*' also matches the stem "
                    f"inside ordinary words (regenerate., pregenerate.), obstructing "
                    f"routine commands. Anchor it on a separator or a space."
                )

    # The trap: a rule that covers the held-out INPUTS would silently break
    # evaluation. Assert none does.
    for rule in rules:
        if HELDOUT_INPUTS_DIR_NAME in rule:
            failures.append(
                f"a deny rule covers the held-out INPUTS, which must stay readable: {rule!r}"
            )
    return failures


def check_placement(root: Path | None = None) -> list[str]:
    """No secret artifact exists anywhere in the repo tree, ignored dirs included."""
    failures: list[str] = []
    base = REPO_ROOT if root is None else root
    for dirpath, _dirnames, filenames in os.walk(base):
        rel = Path(dirpath).relative_to(base)
        parts = set(rel.parts)
        if parts & SECRET_PATH_SEGMENTS:
            failures.append(f"a secret-tier directory exists inside the repo: {rel}")
        for name in filenames:
            if _is_secret_name(name):
                failures.append(f"a secret artifact exists inside the repo: {rel / name}")
    return failures


def run(root: Path | None = None) -> IsolationResult:
    return IsolationResult(
        guard_failures=tuple(check_guard_configuration(root)),
        placement_failures=tuple(check_placement(root)),
    )


def main(argv: list[str] | None = None) -> int:
    # This took no arguments and silently ignored the ones it was handed, which was
    # harmless while it ran only as `python -m ...`. Declaring it a console script (D59)
    # makes that visible: an advertised command that treats `--help` as a request to run
    # the check is a command that lies about itself. Parsing nothing is still parsing --
    # it rejects a typo instead of ignoring it.
    parser = argparse.ArgumentParser(
        prog="goldset-triad-check-isolation",
        description=(
            "Verify the repository's isolation guards: that the deny rules cover every "
            "secret path without covering the held-out inputs, and that no secret "
            "artifact sits inside the repository tree. Exits non-zero on any failure."
        ),
        epilog=(
            "Harness enforcement of the deny rules is attested in "
            "ISOLATION_ATTESTATION.md, not tested by executing code (D30)."
        ),
    )
    parser.add_argument(
        "--repo-root",
        help="the checkout to inspect; defaults to this package's own checkout, or the "
             "current directory when the package is installed rather than run in place",
    )
    args = parser.parse_args(argv)

    # Which tree to inspect. This module used to derive it solely from __file__, which is
    # correct only when running from a source tree. Once D59 made it an installed command,
    # __file__ pointed into site-packages and the tool reported "the deny-guards are
    # unconfigured" -- naming an isolation failure when the truth was that it had been
    # handed nowhere to look. Misdiagnosis is the failure mode D50 ruled worse than silence.
    if args.repo_root is not None:
        root = Path(args.repo_root).resolve()
        if not root.is_dir():
            sys.stderr.write(f"isolation check error: --repo-root {root} is not a directory\n")
            return 2
    elif looks_like_checkout(REPO_ROOT):
        root = REPO_ROOT
    elif looks_like_checkout(Path.cwd()):
        root = Path.cwd()
    else:
        sys.stderr.write(
            "isolation check error: this command inspects a harness checkout, and none was "
            f"found. It is running from an installed copy at {Path(__file__).parent}, and "
            f"the current directory ({Path.cwd()}) is not a checkout either. Run it from "
            "inside the repository, or pass --repo-root. This is NOT an isolation failure: "
            "nothing has been checked.\n"
        )
        return 2

    try:
        result = run(root)
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
