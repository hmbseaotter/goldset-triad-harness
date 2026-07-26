"""Constraint validation — the scans that back the credibility claims.

These assert, by parsing the source, the properties a reviewer would otherwise
have to take on trust: no float on a monetary path, no division inside a flagging
decision, the scoring engine importing only the standard library, no network or
model client anywhere, no PDF/parsing library, no domain rule in the scorer, and
no forbidden terminology anywhere in the repository.
"""

from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path

from tests import support

PKG = support.SRC / "goldset_triad"
SHIPPED_MODULES = sorted(PKG.glob("*.py"))

_FORBIDDEN_IMPORTS = {
    "socket", "ssl", "http", "urllib", "ftplib", "smtplib", "telnetlib",
    "requests", "httpx", "aiohttp", "urllib3",
    "anthropic", "openai", "cohere", "google",
    "reportlab", "pypdf", "PyPDF2", "fitz", "pdfminer",
}


def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _imported_roots(tree: ast.Module) -> set[str]:
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                roots.add(a.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                roots.add(node.module.split(".")[0])
    return roots


class ConstraintScanTests(unittest.TestCase):
    def test_no_float_on_any_monetary_path(self) -> None:
        offenders: list[str] = []
        for path in SHIPPED_MODULES:
            for node in ast.walk(_tree(path)):
                if isinstance(node, ast.Name) and node.id == "float":
                    offenders.append(f"{path.name}:{node.lineno}")
        self.assertEqual(offenders, [], f"float used in shipped code: {offenders}")

    def test_no_division_inside_a_flagging_decision(self) -> None:
        # The flagging decisions that ship are in audit_key's rule functions.
        tree = _tree(PKG / "audit_key.py")
        rule_fns = {"_threshold", "_material", "_payable", "_derive_line", "_derive_tax"}
        offenders: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name in rule_fns:
                for inner in ast.walk(node):
                    if isinstance(inner, ast.BinOp) and isinstance(inner.op, (ast.Div, ast.FloorDiv)):
                        offenders.append(f"{node.name}:{inner.lineno}")
        self.assertEqual(offenders, [], f"division in a flagging decision: {offenders}")

    def test_scoring_engine_imports_only_standard_library(self) -> None:
        stdlib = set(sys.stdlib_module_names)
        allowed = stdlib | {"goldset_triad"}
        offenders: list[str] = []
        for path in SHIPPED_MODULES:
            for root in _imported_roots(_tree(path)):
                if root not in allowed:
                    offenders.append(f"{path.name}: {root}")
        self.assertEqual(offenders, [], f"non-stdlib import in shipped code: {offenders}")

    def test_no_network_or_model_or_pdf_import_anywhere(self) -> None:
        offenders: list[str] = []
        for path in SHIPPED_MODULES:
            roots = _imported_roots(_tree(path))
            for bad in roots & _FORBIDDEN_IMPORTS:
                offenders.append(f"{path.name}: {bad}")
        self.assertEqual(offenders, [], f"forbidden import: {offenders}")

    def test_scoring_module_implements_no_domain_rule(self) -> None:
        # Faithful to the intent: the scorer imports no rule implementation and
        # carries no materiality constant in code. (A prose token scan would wrongly
        # flag the docstring, which explains what the module deliberately does NOT do.)
        tree = _tree(PKG / "scoring.py")
        roots = _imported_roots(tree)
        self.assertNotIn("gen_rules", roots)
        self.assertNotIn("audit_key", roots)
        threshold_literals = {"0.02", "0.05", "25"}
        found: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant):
                value = node.value
                if isinstance(value, str) and value in threshold_literals:
                    found.append(value)
                elif isinstance(value, (int, float)) and not isinstance(value, bool):
                    if str(value) in threshold_literals:
                        found.append(str(value))
        self.assertEqual(found, [], f"scoring.py carries a materiality constant: {found}")

    def test_forbidden_strings_absent_from_the_authored_work(self) -> None:
        # The clean-room rule forbids BLEED of the practice app's terminology into
        # the work. The strings may appear only where they are named to be forbidden
        # or searched for: the requirement documents (which state the rule) and this
        # scan itself. Everywhere else must be clean.
        forbidden = ("reconciliation agent", "iTradeNetwork")
        allow_rel = {
            "DECISIONS.md",
            "specs/goldset-triad-harness.md",
            "specs/goldset-triad-harness.build-prompt.md",
            "tests/test_constraints_scan.py",
        }
        hits: list[str] = []
        for path in support.REPO_ROOT.rglob("*"):
            if not path.is_file() or ".git" in path.parts:
                continue
            rel = path.relative_to(support.REPO_ROOT).as_posix()
            if rel in allow_rel:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            for term in forbidden:
                if term in text:
                    hits.append(f"{rel}: {term}")
        self.assertEqual(hits, [], f"forbidden terminology bled into the work: {hits}")

    def test_loader_reads_no_invoice_pdf(self) -> None:
        # The scorer never parses an invoice document: nothing in the shipped code
        # opens a .pdf.
        for path in SHIPPED_MODULES:
            src = path.read_text(encoding="utf-8")
            self.assertNotIn(".pdf", src, f"{path.name} references a .pdf path")


if __name__ == "__main__":
    unittest.main()
