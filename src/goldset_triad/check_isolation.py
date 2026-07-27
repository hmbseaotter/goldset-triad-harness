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
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from .jsonio import DatasetError, read_json_object

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


def check_guard_reach(root: Path | None = None) -> list[str]:
    """Do this repository's deny rules actually bind the session you are running in? (D91)

    They bind a session **rooted here**. Claude Code loads its permission settings from
    the session's own root, so a session opened at an ancestor directory — a workspace
    folder holding several projects, which is an ordinary way to work — loads *that*
    directory's settings and never sees these rules at all.

    Found by re-running the attestation: a tool-level read of the canary, which the
    dated record says was refused, **succeeded**, because the session was rooted one
    level above this repository. The rules had not failed to match; they had never been
    loaded. The same absence explains a generator invocation that ran unrefused (D90).

    Advisory, and deliberately so (D70's reasoning): where you open your editor is not a
    property of this repository, and a check that failed the build over it would be
    reporting your working habits as a security defect. But it is reported *when isolation
    is checked*, which is exactly when you are about to rely on the guards.

    Placement remains the primary control throughout (D14, D30) — the held-out split is
    outside this tree whatever settings are loaded. This warns about the second layer."""
    warnings: list[str] = []
    base = REPO_ROOT if root is None else root
    for ancestor in base.parents:
        for name in ("settings.json", "settings.local.json"):
            candidate = ancestor / ".claude" / name
            if not candidate.is_file():
                continue
            try:
                data = read_json_object(candidate, f"Claude Code settings at {candidate}")
            except DatasetError:
                # An ancestor's settings being unreadable or malformed is not this
                # repository's business to halt over -- it is somebody else's workspace
                # file. Routed through the shared reader all the same (D77): the lock is
                # that ONE function reads text, not that every caller reacts alike.
                continue
            permissions = data.get("permissions")
            deny = permissions.get("deny", []) if isinstance(permissions, dict) else []
            covers = any(SECRET_DIR_NAME in str(rule) for rule in deny)
            if not covers:
                warnings.append(
                    f"{candidate} carries Claude Code settings that do NOT cover the "
                    f"secret tier ({len(deny)} deny rule(s)). A session rooted at "
                    f"{ancestor} loads those instead of this repository's, so the "
                    f"deny-guards are not in force there. Placement outside the tree "
                    f"still is (D14); this is the second layer only (D91)."
                )
    return warnings


@dataclass(frozen=True)
class IsolationResult:
    guard_failures: tuple[str, ...]
    placement_failures: tuple[str, ...]
    #: Advisory (D70). Kept out of `ok` on purpose: an uncommitted secret tier is a
    #: durability risk, not an isolation breach — nothing has leaked and nothing is
    #: mis-guarded. Failing the command for it would make a routine editing session look
    #: like a security finding, which is how a guard earns being ignored.
    durability_warnings: tuple[str, ...] = ()
    #: Advisory for the same reason (D91): whether these rules are the ones a session
    #: actually loaded depends on where that session was opened, which is not a property
    #: of this repository. Reported, never fatal — and placement, the primary control,
    #: is unaffected either way.
    reach_warnings: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.guard_failures and not self.placement_failures


def looks_like_checkout(path: Path) -> bool:
    """Whether ``path`` is a harness source checkout (D59).

    Deliberately does NOT test for ``.claude/settings.json``: a missing settings file is a
    genuine isolation failure this tool must report, so using its presence to decide
    whether to look here at all would convert that failure into a silent redirect."""
    return (path / "pyproject.toml").is_file() and (path / "src" / "goldset_triad").is_dir()


#: The stamped guard is a deny-only artifact. Anything else appearing under `permissions` is a
#: change to what the guard file DOES, and must be a deliberate edit to the source-of-truth
#: template rather than something that arrived unnoticed (D71). An `allow` list is the case that
#: matters: it would grant reach in the same file whose entire purpose is to withhold it, and
#: nothing was asserting the file's shape at all.
EXPECTED_PERMISSION_LISTS: Final = frozenset({"deny"})


def _permission_lists(root: Path) -> dict[str, list[str]]:
    settings_path = root / ".claude" / "settings.json"
    if not settings_path.is_file():
        raise FileNotFoundError(
            f"guard settings not found at {settings_path}; the deny-guards are unconfigured"
        )
    # The shared reader (D77). This site guarded nothing: a settings file that was not
    # valid JSON, or not UTF-8, produced a traceback from the guard checker -- the one
    # command whose whole job is to report on configuration it was pointed at.
    data = read_json_object(settings_path, "guard settings")
    permissions = data.get("permissions", {})
    if not isinstance(permissions, dict):
        return {}
    return {str(k): [str(r) for r in v] for k, v in permissions.items() if isinstance(v, list)}


def _deny_rules(root: Path) -> list[str]:
    return _permission_lists(root).get("deny", [])


def check_guard_configuration(root: Path | None = None) -> list[str]:
    """Every secret path is covered; the held-out inputs are not (D30, D14)."""
    failures: list[str] = []
    base = REPO_ROOT if root is None else root
    # Rules still come through `_deny_rules`, which is the seam the suite substitutes to test
    # this function against hand-built rule sets. Routing them through `_permission_lists`
    # instead silently bypassed those substitutions, so three tests began asserting against the
    # real shipped rules while appearing to test their own fixtures -- green, and measuring
    # something else entirely.
    rules = _deny_rules(base)
    joined = "\n".join(rules)
    # The file's SHAPE, which nothing asserted (D71). Pattern anchoring was checked across
    # whatever lists happened to exist, and the coverage rules read `deny` -- so a new list
    # would have been half-examined. An `allow` list is the case that matters, because it grants
    # reach in the file whose whole purpose is to withhold it.
    try:
        unexpected = sorted(set(_permission_lists(base)) - EXPECTED_PERMISSION_LISTS)
    except FileNotFoundError:
        unexpected = []  # absence is reported by the rules read above, not twice
    if unexpected:
        failures.append(
            f"the stamped guard declares unexpected permission list(s): {unexpected}. This file "
            f"is deny-only by design; add the list to the source-of-truth template deliberately "
            f"and update EXPECTED_PERMISSION_LISTS, or remove it (D71)"
        )
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


SECRET_ENV_VAR = "GOLDSET_TRIAD_SECRET_DIR"
CONVENTIONAL_SECRET_DIR = REPO_ROOT.parents[1] / "goldset-triad-secret"
HOLDOUT_ENV_VAR = "GOLDSET_TRIAD_HOLDOUT_DIR"
CONVENTIONAL_HOLDOUT_DIR = REPO_ROOT.parents[1] / HELDOUT_INPUTS_DIR_NAME


def find_secret_dir() -> Path | None:
    """The secret tier's root, or None when this machine does not have it."""
    override = os.environ.get(SECRET_ENV_VAR)
    if override:
        candidate = Path(override)
        return candidate if candidate.is_dir() else None
    return CONVENTIONAL_SECRET_DIR if CONVENTIONAL_SECRET_DIR.is_dir() else None


def find_holdout_dir() -> Path | None:
    """The held-out INPUTS tier's root, or None when absent (D71).

    A separate tier from the secret one, with a genuinely different access rule: the agent
    under test MUST be able to read these inputs, so no deny rule may cover them (D14) — while
    the world must not, because these inputs plus the deliberately-published matching policy
    (D53) are enough to derive the answer key mechanically. Readable-by-the-agent and
    publishable are different properties, and only the first applies here."""
    override = os.environ.get(HOLDOUT_ENV_VAR)
    if override:
        candidate = Path(override)
        return candidate if candidate.is_dir() else None
    return CONVENTIONAL_HOLDOUT_DIR if CONVENTIONAL_HOLDOUT_DIR.is_dir() else None


def _git_durability(tier: Path, label: str) -> list[str]:
    """Uncommitted changes and unpushed commits in one tier, as advisory findings."""
    if not (tier / ".git").exists():
        return []  # not a git repo: nothing to be stale about
    try:
        # `-b` adds the branch line, which carries [ahead N]. Committed is not the same as
        # safe: a commit that was never pushed dies with the disk exactly as an uncommitted
        # edit does, and this whole check exists for the single-disk risk.
        result = subprocess.run(
            ["git", "-C", str(tier), "status", "--porcelain", "-b"],
            capture_output=True, text=True, timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return []  # git unavailable is not an isolation finding
    if result.returncode != 0:
        return []
    lines = [ln.rstrip() for ln in result.stdout.splitlines() if ln.strip()]
    branch = lines[0] if lines and lines[0].startswith("##") else ""
    dirty = [ln.strip() for ln in lines[1:]]

    warnings: list[str] = []
    if dirty:
        warnings.append(
            f"the {label} at {tier} has {len(dirty)} uncommitted change(s): "
            f"{', '.join(dirty[:4])}{'' if len(dirty) <= 4 else ', ...'}. Every isolation check "
            f"reads the WORKING tree, so these pass while being one disk failure from lost."
        )
    ahead = re.search(r"\[ahead (\d+)", branch)
    if ahead:
        warnings.append(
            f"the {label} at {tier} is {ahead.group(1)} commit(s) ahead of its remote. "
            f"Committed is not the same as safe: an unpushed commit dies with the disk too."
        )
    return warnings


def check_secret_tier_durability() -> list[str]:
    """Is each out-of-tree tier's *committed* state current? (D70, extended by D71)

    Every other check reads a tier's WORKING tree — the stamped guard against the template on
    disk (D64b), each manifest's digest (D58, D63). None of them looks at what is committed, so
    a tier's git state was itself a claim nothing compared.

    Found by observation, not by theory: the guard template and the held-out manifest sat
    uncommitted while the harness side of the same two decisions was already pushed. The
    template is the **source of truth** the repo's `.claude/settings.json` is stamped from, so a
    disk failure at that moment would have lost the anchored rules and left a restored template
    *behind* the stamped copy that claims to derive from it — reversing which one is
    authoritative. Losing the held-out re-stamp would have made every held-out scorecard
    unverifiable. Closing that single-disk risk is the entire reason those repositories exist.

    Both out-of-tree tiers are covered (D71). The held-out INPUTS tier was the last one with no
    durability story at all, and losing it is the worse outcome of the two: a scorecard embeds an
    aggregate digest of exactly those bytes (D27), so without the bytes there is nothing left to
    recompute against and every held-out result becomes permanently unverifiable.

    Advisory, and deliberately not a test: a failing test here would fire during any normal
    editing session on either tier, and a check that cries wolf while you work is one you learn
    to ignore (D65's lesson about guards people switch off). Reported when isolation is checked —
    which is when you are about to rely on the guards."""
    warnings: list[str] = []
    for finder, label in ((find_secret_dir, "secret tier"),
                          (find_holdout_dir, "held-out inputs tier")):
        tier = finder()
        if tier is not None:
            warnings.extend(_git_durability(tier, label))
    return warnings


def run(root: Path | None = None) -> IsolationResult:
    return IsolationResult(
        guard_failures=tuple(check_guard_configuration(root)),
        placement_failures=tuple(check_placement(root)),
        durability_warnings=tuple(check_secret_tier_durability()),
        reach_warnings=tuple(check_guard_reach(root)),
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
    # Advisory findings print either way, and never change the exit code (D70, D91).
    for w in result.durability_warnings:
        sys.stdout.write(f"  [durability] {w}\n")
    for w in result.reach_warnings:
        sys.stdout.write(f"  [guard-reach] {w}\n")
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
