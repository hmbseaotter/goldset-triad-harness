"""Console scripts: does every command this package advertises actually exist (D59)?

The gap this closes. `audit_key`'s own ``--help`` introduced itself as
``goldset-triad-audit-key``, and no such command was declared — so a reader who followed
the tool's own instructions got "command not found". The isolation check had no console
script either. Both were invisible for the same reason: every existing test and every
manual run invoked them as ``python -m goldset_triad.<module>``, which works whether or
not an entry point is declared. Nothing exercised the advertised path.

The three checks below run in the opposite direction from each other on purpose:

* module -> declaration: a module with a ``main()`` must be reachable as a command.
* declaration -> module: a declared command must resolve to a real callable, so a typo
  in the manifest is caught here rather than by a user.
* advertised name -> declaration: whatever a parser calls itself in ``--help`` must be a
  command that exists. This is the regression test for the actual defect; the first check
  alone would have passed a package that declared some *other* name for `audit_key`.
"""

from __future__ import annotations

import ast
import importlib
import importlib.util
import os
import re
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

from tests import support

#: Documents that tell a reader how to invoke this package. Both advertised the bare
#: `python -m goldset_triad.<module>` form, which fails on a checkout that has not been
#: installed, because the package lives under `src/` (D85).
INVOCATION_DOCS = ("README.md", "ISOLATION_ATTESTATION.md", "docs/RUNBOOK.md")

PACKAGE_DIR = support.SRC / "goldset_triad"
PYPROJECT = support.REPO_ROOT / "pyproject.toml"


def _console_scripts() -> dict[str, str]:
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    return dict(data.get("project", {}).get("scripts", {}))


def _modules_with_main() -> set[str]:
    """Module names defining a top-level ``main``, read with ast rather than by import.

    A `main` nested in a class or assigned conditionally is not an entry point, and a
    substring match on the text would count both. The parse is also why this notices a
    new command-line module the day it is written."""
    found: set[str] = set()
    for path in sorted(PACKAGE_DIR.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:  # top level only
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "main":
                found.add(path.stem)
    return found


class EntryPointTests(unittest.TestCase):
    def test_every_module_with_a_main_is_reachable_as_a_command(self) -> None:
        declared_targets = {
            target.split(":", 1)[0].split(".")[-1] for target in _console_scripts().values()
        }
        missing = sorted(_modules_with_main() - declared_targets)
        self.assertEqual(
            missing, [],
            f"module(s) define main() with no console script: {missing}. Add an entry to "
            f"[project.scripts] in pyproject.toml, or the command exists only as "
            f"`python -m goldset_triad.<module>` while its --help may advertise otherwise "
            f"(D59).",
        )

    def test_every_declared_command_resolves(self) -> None:
        for command, target in sorted(_console_scripts().items()):
            module_path, _, attribute = target.partition(":")
            with self.subTest(command=command):
                self.assertTrue(attribute, f"{command} names no callable in {target!r}")
                module = importlib.import_module(module_path)
                function = getattr(module, attribute, None)
                self.assertTrue(
                    callable(function),
                    f"{command} points at {target}, which is not a callable",
                )

    def test_every_advertised_program_name_is_a_real_command(self) -> None:
        """The defect itself: a parser naming a command that was never declared."""
        commands = set(_console_scripts())
        for path in sorted(PACKAGE_DIR.glob("*.py")):
            source = path.read_text(encoding="utf-8")
            for advertised in re.findall(r"""prog=["']([^"']+)["']""", source):
                with self.subTest(module=path.name, prog=advertised):
                    self.assertIn(
                        advertised, commands,
                        f"{path.name} advertises itself as {advertised!r} in --help, but "
                        f"no such console script is declared, so following the tool's own "
                        f"instructions fails (D59)",
                    )


class AdvertisedInvocationTests(unittest.TestCase):
    """An invocation a document advertises is RUN here, not merely read (D85).

    D59's rule is that anything a tool says about itself is a claim needing a check, and
    its original instance was a `prog=` name for a command that did not exist. This is the
    same defect one layer out: two documents told a reader to run
    `python -m goldset_triad.<module>` without installing, and that fails with
    `ModuleNotFoundError` because the package lives under `src/`.

    It survived for D59's exact reason. Every test reaches the package through
    `tests/support.py`, which inserts `src` into `sys.path`, and every manual run used an
    installed console script — so the advertised route was the one path nobody took. The
    only check that could have caught it is one that actually executes it, in a subprocess
    that does not inherit the suite's own path fixing."""

    def _run(self, pythonpath: str | None) -> subprocess.CompletedProcess[str]:
        env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
        if pythonpath is not None:
            env["PYTHONPATH"] = pythonpath
        return subprocess.run(
            [sys.executable, "-m", "goldset_triad.check_isolation", "--help"],
            cwd=support.REPO_ROOT, env=env, capture_output=True, text=True, timeout=120,
        )

    def test_the_documented_module_invocation_runs(self) -> None:
        """`PYTHONPATH=src python -m goldset_triad.<module>` — the form both documents now
        give — executed rather than pattern-matched."""
        result = self._run("src")
        self.assertEqual(
            result.returncode, 0,
            f"the invocation the documents advertise failed:\n{result.stderr}",
        )
        self.assertIn("usage: goldset-triad-check-isolation", result.stdout)

    def _is_genuinely_installed(self) -> bool:
        """Whether the package resolves from OUTSIDE this checkout's `src`.

        Asked in a clean subprocess run from elsewhere, because asking it in-process
        answers the wrong question: `tests/support.py` inserts `src` into `sys.path` at
        import, so `find_spec` succeeds here whether or not anything is installed. That is
        the very path fixing which hid D85, and it would have made this premise test skip
        itself for a reason that had nothing to do with an install."""
        with tempfile.TemporaryDirectory() as elsewhere:
            probe = subprocess.run(
                [sys.executable, "-c",
                 "import importlib.util,sys;"
                 "sys.exit(0 if importlib.util.find_spec('goldset_triad') else 1)"],
                cwd=elsewhere,
                env={k: v for k, v in os.environ.items() if k != "PYTHONPATH"},
                capture_output=True, text=True, timeout=120,
            )
        return probe.returncode == 0

    def test_the_bare_invocation_really_does_fail(self) -> None:
        """The premise. Documenting `PYTHONPATH=src` is only worth doing if omitting it
        genuinely breaks, and a check that has only ever seen the working case has not been
        shown to look (D73)."""
        if self._is_genuinely_installed():
            self.skipTest(
                "goldset_triad is installed in this interpreter, so the bare form "
                "legitimately works and there is nothing here to prove"
            )
        result = self._run(None)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("No module named", result.stderr)

    def test_every_document_that_advertises_the_module_form_states_the_path(self) -> None:
        """Neither document may advertise the bare form again.

        Checked per line, and a line carrying the `<module>` placeholder is exempt: that is
        prose *describing* the invocation form, not a line anybody types. A concrete line —
        one naming a real module — is a command, and a command that fails on an
        uninstalled checkout is D59's defect however carefully the surrounding prose is
        worded."""
        for name in INVOCATION_DOCS:
            path = support.REPO_ROOT / name
            with self.subTest(document=name):
                self.assertTrue(path.is_file(), f"{name} is missing")
                runnable = [
                    line for line in path.read_text(encoding="utf-8").splitlines()
                    if "python -m goldset_triad" in line and "<module>" not in line
                ]
                self.assertTrue(
                    runnable, f"{name} shows no concrete module invocation to check"
                )
                for line in runnable:
                    self.assertIn(
                        "PYTHONPATH", line,
                        f"{name} shows `{line.strip()[:60]}...` with no PYTHONPATH, which "
                        f"fails with ModuleNotFoundError on an uninstalled checkout (D85)",
                    )


if __name__ == "__main__":
    unittest.main()
