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
import re
import tomllib
import unittest
from pathlib import Path

from tests import support

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


if __name__ == "__main__":
    unittest.main()
