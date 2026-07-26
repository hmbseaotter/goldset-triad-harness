"""Repository composition — what must ship, and what must never.

Every other check in this suite reads the **filesystem**. That is a blind spot: a
file can be present on disk, pass every placement and isolation check, and still
be silently excluded from the repository by an ignore rule — so a fresh clone
lacks it and cannot run. That is not hypothetical. A `.gitignore` pattern of
`ANSWER_KEY*`, written to keep the held-out key out, also matched
`datasets/*/answer_key.json` under `core.ignorecase` and would have dropped all
three PUBLIC dev keys from the commit. The dev split is required to ship complete
(inputs *and* key), and the full acceptance suite is required to pass from the
repository alone — both would have been false, while every filesystem-based test
kept passing.

These tests therefore assert over the **git index and ignore rules**, not the
working tree, and they generalise beyond the keys: nothing in the shipping trees
may be ignored, no partly-tracked tree may have a stray untracked file, and no
secret artifact may be tracked.

`--no-index` is load-bearing on the ignore check. By default `git check-ignore`
consults the index and will not report an already-tracked path as ignored, so the
check would pass vacuously the moment the file was committed — reporting health
precisely when the damage was already done.

Scope note: these tests target *silent* exclusion. A file simply not yet `git
add`-ed is loud — `git status` shows it, and a CI checkout contains only committed
files — so asserting "every on-disk file is tracked" would fail on ordinary
in-progress work and train readers to ignore the signal. An ignore rule is the
silent case, and that is what is asserted here.
"""

from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from tests import support

# Trees whose every file must reach a fresh clone. `src` and `tests` so the suite
# can run at all; `datasets` because the dev split must ship complete.
SHIPPING_TREES = ("src", "tests", "datasets")

# Individual files outside those trees that must also be tracked. `.claude/` is not
# listed wholesale because `settings.local.json` in it is user-local and correctly
# ignored — only the stamped guard file must ship.
REQUIRED_TRACKED_FILES = (
    ".claude/settings.json",
    ".gitattributes",
    ".gitignore",
    "pyproject.toml",
    "pyrightconfig.json",
    "ISOLATION_ATTESTATION.md",
    "DECISIONS.md",
)

# Build artifacts that legitimately never ship.
_EXCLUDED_DIR_PARTS = frozenset({"__pycache__", ".pytest_cache", ".venv", "node_modules"})
_EXCLUDED_SUFFIXES = (".pyc", ".pyo")

# Mirrors the placement check's set, but asserted over the git index rather than the
# filesystem — a `git add -f` leak is invisible to a filesystem walk of a clean tree.
_SECRET_NAME_FRAGMENTS = (
    "holdout_answer_key",
    "gen_rules.py",
    "generate.py",
    "pdf_invoice.py",
    "discrepancy-plan",
)
_SECRET_PATH_FRAGMENTS = ("goldset-triad-secret", "goldset-triad-holdout", "_generators")


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=support.REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def _is_git_work_tree() -> bool:
    result = _git("rev-parse", "--is-inside-work-tree")
    return result.returncode == 0 and result.stdout.strip() == "true"


def _tracked_files() -> set[str]:
    result = _git("ls-files")
    return {line.strip() for line in result.stdout.splitlines() if line.strip()}


def _shipping_files_on_disk() -> list[str]:
    """Every file under the shipping trees, as repo-relative POSIX paths."""
    found: list[str] = []
    for tree in SHIPPING_TREES:
        root = support.REPO_ROOT / tree
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            rel = path.relative_to(support.REPO_ROOT)
            if _EXCLUDED_DIR_PARTS & set(rel.parts):
                continue
            if path.suffix in _EXCLUDED_SUFFIXES:
                continue
            found.append(rel.as_posix())
    return sorted(found)


def ignored_paths(candidates: list[str], extra_excludes: str | None = None) -> list[str]:
    """Which of ``candidates`` the ignore rules would exclude.

    ``--no-index`` is essential: without it git skips paths already in the index,
    so a tracked-but-matched file is reported as fine and the check is useless
    exactly where it matters.

    ``-z`` with byte-mode I/O is also essential, and for a reason this project has
    already been bitten by once: in text mode ``subprocess`` translates ``\\n`` to
    the platform line ending when writing stdin, so on Windows git would receive
    each path with a trailing CR and check a filename that does not exist —
    yielding false negatives against exact-name rules. NUL separation removes the
    newline question entirely and also sidesteps git's quoting of unusual paths.

    ``extra_excludes`` injects an additional ignore file, used by the suite to
    prove the check actually fires on a known-bad pattern."""
    if not candidates:
        return []
    cmd = ["git"]
    if extra_excludes is not None:
        cmd += ["-c", f"core.excludesFile={extra_excludes}"]
    cmd += ["check-ignore", "--no-index", "-z", "--stdin"]
    result = subprocess.run(
        cmd,
        cwd=support.REPO_ROOT,
        input=b"\0".join(c.encode("utf-8") for c in candidates),
        capture_output=True,
        check=False,
    )
    # exit 0 => at least one match, 1 => none matched, >1 => error
    if result.returncode > 1:
        raise RuntimeError(f"git check-ignore failed: {result.stderr.decode(errors='replace').strip()}")
    return [p.decode("utf-8") for p in result.stdout.split(b"\0") if p]


class RepositoryShippingTests(unittest.TestCase):
    def setUp(self) -> None:
        if not _is_git_work_tree():
            self.skipTest("not a git work tree; repository-composition checks do not apply")

    def test_no_shipping_file_is_excluded_by_an_ignore_rule(self) -> None:
        """The general form of the bug that nearly shipped: an ignore pattern
        matching something the repository must contain."""
        excluded = ignored_paths(_shipping_files_on_disk())
        self.assertEqual(
            excluded,
            [],
            "these files must ship but an ignore rule excludes them "
            f"(a fresh clone would lack them): {excluded}",
        )

    def test_required_files_are_tracked_and_not_ignored(self) -> None:
        tracked = _tracked_files()
        missing = [f for f in REQUIRED_TRACKED_FILES if f not in tracked]
        self.assertEqual(missing, [], f"required files are not tracked: {missing}")
        excluded = ignored_paths(list(REQUIRED_TRACKED_FILES))
        self.assertEqual(excluded, [], f"required files are ignored: {excluded}")

    def test_the_check_actually_fires_on_a_known_bad_pattern(self) -> None:
        """Self-verification: prove the mechanism detects the bug it exists for.

        A guard that cannot fail is worth nothing, and this one has a specific way
        of rotting into a vacuous pass (dropping `--no-index`, or mangling the paths
        it feeds git, both of which happened while writing it). So the suite injects
        the historical pattern through a temporary excludes file — the repository's
        own `.gitignore` is untouched — and asserts the dev keys are caught."""
        with tempfile.TemporaryDirectory() as td:
            excludes = Path(td) / "extra.gitignore"
            # The pattern that nearly shipped. Under core.ignorecase this matches
            # dev_answer_key.json as surely as it matched answer_key.json.
            excludes.write_text("*ANSWER_KEY*\n", encoding="utf-8", newline="\n")
            caught = ignored_paths(_shipping_files_on_disk(), extra_excludes=str(excludes))
        key_hits = sorted(p for p in caught if p.endswith("dev_answer_key.json"))
        self.assertEqual(
            len(key_hits), 3,
            "the ignore check failed to detect the historical bug pattern; "
            f"expected all three dev keys, got {key_hits}",
        )
        # And the paths must come back clean -- no stray CR from newline translation.
        for path in caught:
            self.assertNotIn("\r", path, f"path mangled by newline translation: {path!r}")
            self.assertNotIn("\\", path, f"path came back quoted/escaped: {path!r}")

    def test_no_secret_artifact_is_tracked(self) -> None:
        """The dual check, over the index rather than the filesystem: a secret
        artifact force-added into git would not be caught by a placement walk of an
        otherwise clean tree."""
        leaks = []
        for path in sorted(_tracked_files()):
            lowered = path.lower()
            if any(frag in lowered for frag in _SECRET_NAME_FRAGMENTS):
                leaks.append(path)
            elif any(frag in lowered for frag in _SECRET_PATH_FRAGMENTS):
                leaks.append(path)
        self.assertEqual(leaks, [], f"secret artifacts are tracked in git: {leaks}")

    def test_the_dev_split_ships_complete(self) -> None:
        """The concrete requirement the general rules exist to protect: every dev
        split ships its inputs AND its key, so the suite runs from the repo alone."""
        tracked = _tracked_files()
        for dataset in ("dev", "dev-synthetic", "dev-zero-defect"):
            base = f"datasets/{dataset}"
            for required in ("manifest.json", "dev_answer_key.json",
                             "invoice_index.json", "matching_policy.json"):
                self.assertIn(
                    f"{base}/{required}", tracked,
                    f"{base}/{required} must ship with the dev split",
                )
            inputs = [f for f in tracked if f.startswith(f"{base}/inputs/")]
            self.assertTrue(inputs, f"{base}/inputs/ ships no files")


if __name__ == "__main__":
    unittest.main()
