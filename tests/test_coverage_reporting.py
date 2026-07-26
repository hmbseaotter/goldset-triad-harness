"""Coverage reporting: does the scorecard say what the dataset could not measure (D60)?

The gap this closes. Per-category metrics are emitted for all five categories always, so a
dataset that exercises only some of them produces rows of zeros with `null` precision and
recall. D25 fixed `null` as "undefined", which is correct — but *undefined because the data
holds no such case* and *undefined because nothing was submitted* look identical, and the
held-out split at `[P1]` exercises two of five. Three categories therefore come back null on
every held-out run, and null on a category the agent was never asked about reads as a clean
sheet.

Nothing here needed new computation: every expectation is either matched or missed, so
`tp + fn` already WAS the expectation count. The defect was that the scorecard declined to
say so and left a reader to derive it.

The zero-defect control is the extreme of the same case: it declares no expectations at all
(D57), so every category is unexercised and every recall figure is undefined by
construction. A scorecard that did not say so would present the control as an agent that
recalled nothing — the exact inversion of what the control proves.
"""

from __future__ import annotations

import unittest

from tests import support
from goldset_triad import scorecard as sc
from goldset_triad.dataset import load_dataset
from goldset_triad.schema import Category
from goldset_triad.scoring import score

RUN = sc.RunMetadata("2026-07-26T10:00:00Z", 1, 2, 3)


def _card(dataset: str, *, perfect: bool = True):
    loaded = load_dataset(dataset, support.DATASETS)
    agent = support.perfect_artifact(dataset) if perfect else ()
    result = score(loaded.answer_key.expected_findings, agent, loaded.invoice_index.inventory)
    provenance = sc.Provenance(dataset, loaded.manifest.version, "f" * 64,
                              loaded.answer_key.sha256, loaded.invoice_index.sha256,
                              loaded.inputs_aggregate_sha256)
    return sc.build_scorecard(result, provenance, RUN), result


class CoverageBlockTests(unittest.TestCase):
    def test_a_fully_exercised_dataset_reports_every_category(self) -> None:
        card, _ = _card("dev")
        coverage = card["coverage"]
        self.assertEqual(coverage["categories_not_exercised"], [])
        self.assertEqual(len(coverage["categories_exercised"]), len(list(Category)))
        self.assertEqual(coverage["categories_total"], len(list(Category)))
        self.assertTrue(coverage["measures_recall"])

    def test_expected_finding_count_matches_the_key(self) -> None:
        loaded = load_dataset("dev", support.DATASETS)
        card, _ = _card("dev")
        self.assertEqual(
            card["coverage"]["expected_finding_count"],
            len(loaded.answer_key.expected_findings),
        )

    def test_a_partially_exercised_dataset_names_what_it_cannot_measure(self) -> None:
        """The held-out shape, reproduced in repo: a key holding two categories.

        Built by scoring the dev split against a key trimmed to two categories, because the
        held-out split itself is unreadable from CI by design (D14). The property under test
        is the scorecard's arithmetic, not the held-out data."""
        loaded = load_dataset("dev", support.DATASETS)
        kept = tuple(
            f for f in loaded.answer_key.expected_findings
            if f.category in (Category.PRICE_VARIANCE, Category.QTY_UNDER_SHIPMENT)
        )
        self.assertTrue(kept, "fixture drift: dev holds neither category")
        result = score(kept, kept, loaded.invoice_index.inventory)
        provenance = sc.Provenance("dev", loaded.manifest.version, "f" * 64,
                                  loaded.answer_key.sha256, loaded.invoice_index.sha256,
                                  loaded.inputs_aggregate_sha256)
        card = sc.build_scorecard(result, provenance, RUN)

        coverage = card["coverage"]
        self.assertEqual(
            sorted(coverage["categories_exercised"]),
            sorted(["PRICE_VARIANCE", "QTY_UNDER_SHIPMENT"]),
        )
        self.assertEqual(len(coverage["categories_not_exercised"]), 3)
        self.assertTrue(coverage["measures_recall"])

        # The three unmeasured categories must be null AND flagged as unexercised. Null
        # alone is what a reader misreads.
        for name in coverage["categories_not_exercised"]:
            row = card["metrics"]["per_category"][name]
            self.assertIsNone(row["recall"])
            self.assertEqual(row["expected_count"], 0)
            self.assertFalse(row["exercised_by_dataset"])

        summary = sc.human_summary(card, result)
        self.assertIn("2 of 5 categories", summary)
        for name in coverage["categories_not_exercised"]:
            self.assertIn(name, summary.split("COVERAGE:", 1)[1])
        self.assertIn("NOT that the agent handled them correctly", summary)

    def test_the_zero_defect_control_says_it_measures_no_recall(self) -> None:
        card, result = _card("dev-zero-defect")
        coverage = card["coverage"]
        self.assertEqual(coverage["categories_exercised"], [])
        self.assertEqual(coverage["expected_finding_count"], 0)
        self.assertFalse(coverage["measures_recall"])
        summary = sc.human_summary(card, result)
        self.assertIn("measures over-flagging only", summary)
        self.assertIn("undefined by construction", summary)

    def test_coverage_is_in_the_scored_body_not_run_metadata(self) -> None:
        """It is a property of the answer key, so it must survive into the bytes that two
        runs are required to match — and must not sit in the envelope reserved for
        non-deterministic fields."""
        card, _ = _card("dev")
        self.assertIn("coverage", card)
        self.assertNotIn("coverage", card["run_metadata"])
        self.assertIn('"coverage"', sc.deterministic_body(card))


class UndefinedMetricDisplayTests(unittest.TestCase):
    """`null` is right for JSON (D25) and wrong when interpolated into human text."""

    def test_undefined_metrics_read_as_na_not_python_none(self) -> None:
        card, result = _card("dev-zero-defect")
        summary = sc.human_summary(card, result)
        self.assertNotIn("None", summary)
        self.assertIn("n/a", summary)

    def test_json_still_emits_null_not_the_display_string(self) -> None:
        """The display form must not leak back into the machine-readable record."""
        card, _ = _card("dev-zero-defect")
        row = card["metrics"]["per_category"]["TAX_VARIANCE"]
        self.assertIsNone(row["precision"])
        self.assertIsNone(row["recall"])
        self.assertNotIn("n/a", sc.serialize(card))


class TextIoIsExplicitTests(unittest.TestCase):
    """No text read or write anywhere relies on the platform default (D61).

    Discovered by being bitten: `Path.read_text()` with no encoding decodes with the
    platform default — cp1252 here — so a source file containing a byte sequence cp1252
    leaves undefined raises `UnicodeDecodeError` on Windows and passes on Linux. Several
    suites scan source and spec files this way, and every non-ASCII character this project
    writes freely (em dashes, curly quotes) is a candidate trigger. `write_text` without a
    pinned newline is the same family as D49's line-ending finding.

    Scanned with ast rather than by substring so a call is judged by its actual keyword
    arguments, not by whether the word "encoding" happens to appear on the same line."""

    _TEXT_IO = {"read_text", "write_text", "open"}

    def test_no_call_relies_on_the_platform_default_encoding(self) -> None:
        import ast

        offenders: list[str] = []
        for path in sorted((support.REPO_ROOT / "tests").glob("*.py")) + sorted(
            (support.SRC / "goldset_triad").glob("*.py")
        ):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                name = node.func.attr if isinstance(node.func, ast.Attribute) else (
                    node.func.id if isinstance(node.func, ast.Name) else None
                )
                if name not in self._TEXT_IO:
                    continue
                keywords = {kw.arg for kw in node.keywords}
                if "encoding" in keywords:
                    continue
                # Binary mode takes no encoding, so `open(p, "rb")` is not an offender.
                mode = next(
                    (a.value for a in node.args
                     if isinstance(a, ast.Constant) and isinstance(a.value, str)),
                    "",
                )
                if name == "open" and "b" in mode:
                    continue
                offenders.append(f"{path.name}:{node.lineno} {name}()")

        self.assertEqual(
            offenders, [],
            f"{len(offenders)} text I/O call(s) rely on the platform default encoding, "
            f"which makes the suite platform-dependent: {offenders}. Pass "
            f'encoding="utf-8" (and newline="\\n" when writing).',
        )

    def test_the_scan_fires_on_a_bare_call(self) -> None:
        """A scan that has only ever found nothing has not been shown to look."""
        import ast

        tree = ast.parse("from pathlib import Path\nPath('x').read_text()\n")
        bare = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in self._TEXT_IO
            and "encoding" not in {kw.arg for kw in node.keywords}
        ]
        self.assertEqual(len(bare), 1)


if __name__ == "__main__":
    unittest.main()
