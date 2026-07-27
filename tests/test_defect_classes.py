"""Recurring defect classes, each locked by a scanner rather than by attention (D68).

Four classes have each been found, fixed, and then found again in a later sweep. What they
have in common is that the *fix* was applied to an instance while the *class* stayed
unguarded, so the next reader with fresh eyes found the remaining instances. That is a
linear process: it terminates only when someone happens to have looked everywhere.

Each class below gets a scanner, so a new instance fails at the point it is written:

* **Timing waits.** A `time.sleep(1.05)` existed to force a distinct run stamp. D49 made it
  unnecessary; it survived roughly four more sweeps, *while the neighbouring test's docstring
  criticised it in writing*. A comment recording a problem is not a mechanism. The class is at
  zero today, and this pins it there — the cheapest possible moment to lock a class.
* **Absence becoming a number.** The D50 defect: a missing purchase order defaulted to
  zero-rated, so a typo was reported as "apportionment UNSPECIFIED". Scoped deliberately —
  see `NUMERIC_DEFAULTS`.
* **Unanchored patterns.** D65: `Bash(*generate.*)` denied `bash regenerate.sh` and
  `git log --grep=generate.py`, obstructing this project's own workflow verb. Guarded in
  `check_guard_configuration` for deny rules; generalized here to every rule list, so adding
  an `allow` or `ask` list does not reopen it.
* **Guarded-by-ordering.** Two defaults are unreachable only because another validator runs
  first. That is legitimate and load-bearing, so the ordering is asserted rather than assumed.
"""

from __future__ import annotations

import ast
import json
import os
import re
import unittest
from pathlib import Path

from tests import support
from goldset_triad import check_isolation as ci

PACKAGE = support.SRC / "goldset_triad"
TESTS = support.REPO_ROOT / "tests"


# ---------------------------------------------------------------------------
# Class 1 - timing waits
# ---------------------------------------------------------------------------
class NoTimingWaitTests(unittest.TestCase):
    """Zero sleeps, and zero is a deliberate ceiling rather than a coincidence.

    Scoring is deterministic and single-threaded: there is no correct reason to wait. A sleep
    here would mean either a test bending to a real defect (the 1.05s case, which papered over
    scorecard filename collisions until D49 fixed the cause) or a race being tolerated."""

    def test_no_timing_wait_anywhere(self) -> None:
        offenders: list[str] = []
        for directory in (PACKAGE, TESTS):
            for path in sorted(directory.glob("*.py")):
                tree = ast.parse(path.read_text(encoding="utf-8"))
                for node in ast.walk(tree):
                    if not isinstance(node, ast.Call):
                        continue
                    name = (node.func.attr if isinstance(node.func, ast.Attribute)
                            else node.func.id if isinstance(node.func, ast.Name) else None)
                    if name == "sleep":
                        offenders.append(f"{path.name}:{node.lineno}")
        self.assertEqual(
            offenders, [],
            f"timing wait(s) introduced: {offenders}. Scoring is deterministic and "
            f"single-threaded, so a sleep is a symptom: it is either hiding a real defect "
            f"(as the 1.05s wait hid scorecard collisions until D49) or tolerating a race. "
            f"Fix the cause.",
        )


# ---------------------------------------------------------------------------
# Class 2 - absence becoming a number
# ---------------------------------------------------------------------------
#: Every site in SHIPPED code where a missing key yields a numeric value, with why it is
#: sound. Keyed by module and expression text, not line number, so ordinary edits do not
#: churn the list while a genuinely new site still fails.
#:
#: Scope is deliberate: **numeric** defaults only. A missing value that becomes a number
#: enters arithmetic and changes a verdict silently, which is what D50 was. A missing value
#: that becomes "" or [] or {} is a structural absence, and the loader has explicit
#: presence checks for the ones that matter (D29 for tax fields, D50/D56 for correspondence
#: rows) which fail loudly instead. Widening this to every container default is possible,
#: but it would trade 8 reviewed justifications for 24 thinner ones.
NUMERIC_DEFAULTS: dict[tuple[str, str], str] = {
    ("audit_key.py", "received.get(key, Decimal(0))"):
        "accumulator seed: `received[key] = received.get(key, 0) + qty` sums receipt lines, "
        "so absence means 'nothing summed yet', not a missing document",
    ("audit_key.py", "inputs.received.get((pon, pln), Decimal(0))"):
        "a purchase-order line with no goods-receipt row genuinely received nothing; zero is "
        "the domain meaning here, and it is what makes QTY_UNDER_SHIPMENT derivable at all",
    ("audit_key.py", "inputs.po_tax.get(pon, Decimal(0))"):
        "unreachable: the shared loader (D62) rejects a correspondence row naming a "
        "non-existent purchase order, and D29 rejects a purchase order with no tax field, so "
        "every key present in the correspondence has an entry",
    ("audit_key.py", "inputs.po_taxable.get(pon, Decimal(0))"):
        "same as po_tax above - reference resolution (D62) and tax-field presence (D29) both "
        "run before the audit derives anything",
    ("audit_key.py", "inputs.inv_tax.get(iid, Decimal(0))"):
        "unreachable: every invoice id reaching here came from a correspondence row whose "
        "invoice line the loader verified against the index (D50)",
    ("audit_key.py", "inputs.inv_taxable.get(iid, Decimal(0))"):
        "unreachable for the same reason as inv_tax: the invoice id came from a "
        "correspondence row whose line the loader verified against the index (D50), and the "
        "index is what supplies the taxable subtotal, so the two are populated together",
    ("dataset.py", "facts.get(reference, (Decimal(0), Decimal(0)))"):
        "unreachable: _validate_correspondence_references runs BEFORE "
        "_validate_multi_po_tax_rates, so a phantom purchase order is named as the typo it is "
        "rather than misdiagnosed as a differing tax rate (D50). The ordering is asserted by "
        "OrderDependencyTests below, not merely commented",
    ("dataset.py", "facts.get(other, (Decimal(0), Decimal(0)))"):
        "unreachable on the same ordering as facts.get(reference): both purchase orders in a "
        "multi-PO comparison come from correspondence rows already resolved against the "
        "inputs, so neither lookup can miss by the time the rate check runs (D50, D62)",
}

_NUMERIC_DEFAULT = (ast.Constant, ast.Call, ast.Tuple)


def _is_numeric_default(node: ast.expr) -> bool:
    """Whether a default evaluates to a number or a tuple of numbers."""
    if isinstance(node, ast.Constant):
        return isinstance(node.value, (int, float)) and not isinstance(node.value, bool)
    if isinstance(node, ast.Call):  # Decimal(0), Decimal("0")
        func = node.func
        name = (func.attr if isinstance(func, ast.Attribute)
                else func.id if isinstance(func, ast.Name) else "")
        return name == "Decimal"
    if isinstance(node, ast.Tuple):
        return bool(node.elts) and all(_is_numeric_default(e) for e in node.elts)
    return False


class NumericDefaultTests(unittest.TestCase):
    def test_every_numeric_default_in_shipped_code_is_justified(self) -> None:
        unjustified: list[str] = []
        for path in sorted(PACKAGE.glob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not (isinstance(node, ast.Call)
                        and isinstance(node.func, ast.Attribute)
                        and node.func.attr == "get"
                        and len(node.args) == 2):
                    continue
                if not _is_numeric_default(node.args[1]):
                    continue
                expr = ast.unparse(node)
                if (path.name, expr) not in NUMERIC_DEFAULTS:
                    unjustified.append(f"{path.name}:{node.lineno} {expr}")
        self.assertEqual(
            unjustified, [],
            f"{len(unjustified)} site(s) turn a missing key into a number with no recorded "
            f"justification: {unjustified}. Either the absence is genuinely zero in the "
            f"domain, or a prior check makes it unreachable, or it is the D50 defect - a "
            f"typo scored as data. Add an entry to NUMERIC_DEFAULTS saying which.",
        )

    def test_no_justification_outlives_its_site(self) -> None:
        """A justification for code that no longer exists is a claim about nothing."""
        present: set[tuple[str, str]] = set()
        for path in sorted(PACKAGE.glob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                        and node.func.attr == "get" and len(node.args) == 2
                        and _is_numeric_default(node.args[1])):
                    present.add((path.name, ast.unparse(node)))
        stale = sorted(f"{m}: {e}" for m, e in set(NUMERIC_DEFAULTS) - present)
        self.assertEqual(stale, [], f"NUMERIC_DEFAULTS justifies absent site(s): {stale}")

    def test_every_justification_says_something(self) -> None:
        for (module, expr), reason in NUMERIC_DEFAULTS.items():
            with self.subTest(site=f"{module}:{expr}"):
                self.assertGreater(
                    len(reason.strip()), 40,
                    f"the justification for {module}:{expr} is too thin to review",
                )


# ---------------------------------------------------------------------------
# Class 3 - unanchored patterns, across every rule list
# ---------------------------------------------------------------------------
class PatternAnchoringTests(unittest.TestCase):
    """D65 generalized. A bare `*<stem>.` matches the stem inside ordinary words, so
    `Bash(*generate.*)` denied `bash regenerate.sh` — obstructing the project's own workflow
    verb. `check_guard_configuration` rejects that shape in the deny list; these assert the
    property over EVERY rule list, so introducing an `allow` or `ask` list cannot reopen it."""

    #: Whole filenames are distinctive enough to stand alone; a stem is not.
    _WHOLE_NAME_OK = re.compile(r"\*[\w.-]+\.(json|md)\*")
    _BARE_STEM = re.compile(r"\(\*[A-Za-z0-9_]+\.")

    def _rule_lists(self):
        paths = [("stamped", support.REPO_ROOT / ".claude" / "settings.json")]
        secret = support.find_secret_dir()
        if secret is not None:
            template = secret / "_guard-template.settings.json"
            if template.is_file():
                paths.append(("template", template))
        for label, path in paths:
            data = json.loads(path.read_text(encoding="utf-8"))
            for list_name, rules in data.get("permissions", {}).items():
                yield label, list_name, [str(r) for r in rules]

    def test_no_rule_in_any_list_is_anchored_on_a_bare_stem(self) -> None:
        offenders: list[str] = []
        for label, list_name, rules in self._rule_lists():
            for rule in rules:
                if self._WHOLE_NAME_OK.search(rule):
                    continue
                if self._BARE_STEM.search(rule):
                    offenders.append(f"{label}/{list_name}: {rule}")
        self.assertEqual(
            offenders, [],
            f"rule(s) anchored on a bare stem: {offenders}. The stem matches inside ordinary "
            f"words, so the rule obstructs unrelated commands - and a guard that blocks "
            f"routine work is one people switch off (D65). Anchor on a separator or a space.",
        )

    def test_at_least_one_rule_list_was_examined(self) -> None:
        """Guard against the scan passing because it found nothing to scan."""
        examined = list(self._rule_lists())
        self.assertTrue(examined, "no permission rule list was found to check")
        self.assertIn("deny", {ln for _l, ln, _r in examined})

    def test_an_unexpected_permission_list_is_rejected(self) -> None:
        """The guard file's SHAPE, which nothing asserted before (D71).

        Anchoring was checked across whatever lists happened to exist and coverage read `deny`,
        so a new list would have been half-examined. An `allow` list is the case that matters: it
        grants reach in the file whose entire purpose is to withhold it."""
        import json
        import tempfile
        from unittest import mock

        shipped = json.loads(
            (support.REPO_ROOT / ".claude" / "settings.json").read_text(encoding="utf-8")
        )
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / ".claude").mkdir()
            tampered = dict(shipped)
            tampered["permissions"] = dict(shipped["permissions"])
            tampered["permissions"]["allow"] = ["Read(**/holdout_answer_key.json)"]
            (root / ".claude" / "settings.json").write_text(
                json.dumps(tampered, indent=2), encoding="utf-8", newline="\n"
            )
            failures = ci.check_guard_configuration(root)
        self.assertTrue(
            any("unexpected permission list" in f and "allow" in f for f in failures),
            f"an allow list in the deny-only guard went unreported: {failures}",
        )

    def test_the_shipped_guard_declares_only_the_expected_lists(self) -> None:
        """Positive control: the rule does not fire on the file as shipped."""
        failures = ci.check_guard_configuration()
        self.assertFalse(
            any("unexpected permission list" in f for f in failures),
            f"the shipped guard tripped its own shape check: {failures}",
        )

    def test_the_shipped_check_rejects_the_historical_bad_pattern(self) -> None:
        """The scan above reads files; this confirms the SHIPPED check still rejects the
        shape, so the guarantee does not depend on this test file existing."""
        from unittest import mock

        bad = ["Read(**/goldset-triad-secret/**)", "Read(**/holdout_answer_key.json)",
               "Read(**/holdout_invoice_index.json)", "Read(**/gen_rules.*)",
               "Read(**/generate.*)", "Read(**/pdf_invoice.*)",
               "Read(**/discrepancy-plan.md)", "Bash(*generate.*)"]
        with mock.patch.object(ci, "_deny_rules", return_value=bad):
            failures = ci.check_guard_configuration()
        self.assertTrue(
            any("generate." in f for f in failures),
            f"the shipped guard-config check no longer rejects a bare-stem rule: {failures}",
        )


# ---------------------------------------------------------------------------
# Class 4 - correctness that depends on call order
# ---------------------------------------------------------------------------
class OrderDependencyTests(unittest.TestCase):
    """Where one validator's correctness depends on another running first, assert the order.

    Two `facts.get(..., (Decimal(0), Decimal(0)))` defaults in `_validate_multi_po_tax_rates`
    are unreachable only because `_validate_correspondence_references` runs before them. That
    dependency is documented at the call site and is genuinely load-bearing: swapping the two
    calls resurrects D50's misdiagnosis, reporting a phantom purchase order as a differing tax
    rate. One existing test happens to catch that swap; this states the dependency directly, so
    it is protected on purpose rather than by luck."""

    def test_reference_resolution_precedes_the_rate_check(self) -> None:
        source = (PACKAGE / "dataset.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        loader = next(
            n for n in ast.walk(tree)
            if isinstance(n, ast.FunctionDef) and n.name == "load_dataset"
        )
        called: list[str] = []
        for node in ast.walk(loader):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id.startswith("_validate"):
                    called.append(node.func.id)
        for earlier, later, why in (
            ("_validate_correspondence_references", "_validate_multi_po_tax_rates",
             "else a phantom purchase order is misdiagnosed as a differing tax rate (D50)"),
        ):
            with self.subTest(pair=f"{earlier} before {later}"):
                self.assertIn(earlier, called)
                self.assertIn(later, called)
                self.assertLess(
                    called.index(earlier), called.index(later),
                    f"{earlier} must run before {later}: {why}. Current order: {called}",
                )


class SecretTierDurabilityTests(unittest.TestCase):
    """The tier's COMMITTED state is a claim too, and nothing compared it (D70).

    Every other check reads the secret tier's working tree. Found by observation: the guard
    template and the held-out manifest sat uncommitted while the harness side of the same two
    decisions was already pushed. The template is the source of truth the repo's settings are
    stamped from, so a disk failure there would have left a restored template *behind* the
    stamped copy claiming to derive from it — inverting which one is authoritative.

    Advisory rather than a failing test, on purpose: this would otherwise fire during any
    normal editing session on the secret side, and a check that cries wolf while you work is
    one you learn to switch off (D65). It reports when isolation is checked, which is when you
    are about to rely on the guards.

    Exercised against a throwaway git repo via the env override, never the real tier."""

    def _fake_tier(self, td: str, name: str = "secret"):
        import subprocess

        tier = Path(td) / name
        tier.mkdir()
        run = lambda *a: subprocess.run(["git", "-C", str(tier), *a], capture_output=True)
        subprocess.run(["git", "init", "-q", str(tier)], capture_output=True)
        run("config", "user.email", "t@t")
        run("config", "user.name", "t")
        (tier / "_guard-template.settings.json").write_text("{}", encoding="utf-8", newline="\n")
        run("add", "-A")
        run("commit", "-qm", "init")
        return tier

    def _isolate(self, secret: Path | str, holdout: Path | str):
        """Point BOTH tier overrides somewhere controlled.

        These tests originally set only the secret override, and passed — because the function
        looked at one tier. Extending it to the held-out tier (D71) made the real one leak into
        every result. Under-isolated tests are indistinguishable from correct ones until the
        code reaches past what they pinned, so both are pinned now."""
        from unittest import mock

        return mock.patch.dict(
            os.environ,
            {ci.SECRET_ENV_VAR: str(secret), ci.HOLDOUT_ENV_VAR: str(holdout)},
        )

    def test_a_clean_tier_reports_nothing(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            tier = self._fake_tier(td)
            with self._isolate(tier, Path(td) / "no-holdout"):
                self.assertEqual(ci.check_secret_tier_durability(), [])

    def test_an_uncommitted_change_is_reported(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            tier = self._fake_tier(td)
            (tier / "_guard-template.settings.json").write_text(
                '{"edited": true}', encoding="utf-8", newline="\n"
            )
            with self._isolate(tier, Path(td) / "no-holdout"):
                warnings = ci.check_secret_tier_durability()
        self.assertTrue(warnings)
        self.assertIn("uncommitted", warnings[0])
        self.assertIn("_guard-template.settings.json", warnings[0])

    def test_an_untracked_file_is_reported(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            tier = self._fake_tier(td)
            (tier / "stray.json").write_text("{}", encoding="utf-8", newline="\n")
            with self._isolate(tier, Path(td) / "no-holdout"):
                warnings = ci.check_secret_tier_durability()
        self.assertTrue(any("stray.json" in w for w in warnings))

    def test_an_absent_tier_reports_nothing(self) -> None:
        """D14: no out-of-tree tier on this machine is the normal case for a clone."""
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            with self._isolate(Path(td) / "nope", Path(td) / "also-nope"):
                self.assertEqual(ci.check_secret_tier_durability(), [])

    def test_both_out_of_tree_tiers_are_covered(self) -> None:
        """The held-out inputs tier was the last with no durability story (D71).

        Losing it is the worse of the two outcomes: a scorecard embeds an aggregate digest of
        exactly those bytes (D27), so without the bytes there is nothing left to recompute
        against and every held-out result becomes permanently unverifiable."""
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            secret = self._fake_tier(td, "secret")
            holdout = self._fake_tier(td, "holdout")
            (holdout / "inputs.json").write_text("{}", encoding="utf-8", newline="\n")
            with self._isolate(secret, holdout):
                warnings = ci.check_secret_tier_durability()
        self.assertTrue(
            any("held-out inputs tier" in w for w in warnings),
            f"the held-out tier's uncommitted state went unreported: {warnings}",
        )
        self.assertFalse(
            any("secret tier" in w for w in warnings),
            "the clean secret tier should not have been reported",
        )

    def test_a_durability_warning_never_fails_the_check(self) -> None:
        """The property that keeps this from becoming noise: advisory means advisory."""
        result = ci.IsolationResult(
            guard_failures=(), placement_failures=(),
            durability_warnings=("the tier has uncommitted changes",),
        )
        self.assertTrue(result.ok, "a durability warning must not make isolation fail")


if __name__ == "__main__":
    unittest.main()
