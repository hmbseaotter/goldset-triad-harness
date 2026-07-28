"""Every field the scorecard emits is documented in the legend (D100).

The gap this closes. A scorecard has 40-odd fields and several whose obvious reading is the
wrong one: `false_positive_rate` is per *invoice* not per finding; `precision: null` and
`precision: "0.0000"` are different verdicts; the three false-positive counters are not
alternatives; `missed[].reasoning` is the answer key's note, not the agent's. Before this,
that knowledge existed as inline comments inside an illustrative JSON block in the README —
readable, but not usable as a reference by someone looking at their own scorecard, and
invisible to anyone who did not know to look.

Why it needs a check rather than just a document. The coverage block was added to the
scorecard by D60 and the README's example was updated by hand. Nothing connected the two, so
the next field added would silently go undocumented — the shape of defect D59 named: a claim
(here, "the legend describes the scorecard") that nothing compares against reality.

Field NAMES are checked rather than dotted paths. A path check would fail on cosmetic
restructuring of the document and pass a field documented under the wrong parent; a name
check is stable and still catches the thing that matters, which is a field nobody wrote down.
Names must appear in backticks, so prose that happens to use the word does not satisfy it.
"""

from __future__ import annotations

import json
import re
import tempfile
import unittest
from pathlib import Path

from tests import support
from goldset_triad import scorecard as sc
from goldset_triad.dataset import load_dataset
from goldset_triad.scoring import score

LEGEND = support.REPO_ROOT / "docs" / "SCORECARD.md"

#: Names that are values or identifiers rather than fields, so the legend need not define them
#: as fields. Category names are published in `matching_policy.json`; the rest are enum values.
NOT_FIELDS = frozenset({
    "PRICE_VARIANCE", "QTY_UNDER_SHIPMENT", "QTY_OVER_SHIPMENT", "QTY_INVOICE_INFLATED",
    "TAX_VARIANCE",
})


def _field_names(obj: object) -> set[str]:
    """Every mapping key anywhere in the structure, at any depth."""
    found: set[str] = set()
    if isinstance(obj, dict):
        for key, value in obj.items():
            found.add(str(key))
            found |= _field_names(value)
    elif isinstance(obj, list):
        for item in obj:
            found |= _field_names(item)
    return found


def _scorecard_with_every_branch() -> dict:
    """A scorecard exercising misses AND false flags, so both element shapes appear.

    Built from the dev split with a deliberately imperfect submission: one correct finding, one
    aimed at a line that does not exist. An all-correct submission would leave `false_flags`
    empty and its `reason` field undocumented-but-unchecked — the check would then pass by
    never having seen the field, which is the vacuous pass this project keeps finding."""
    loaded = load_dataset("dev", support.DATASETS)
    expected = loaded.answer_key.expected_findings
    submitted = (
        expected[0],
        support.line(expected[0].category, expected[0].target.document_id, "999-NO-SUCH-LINE"),
    )
    result = score(expected, submitted, loaded.invoice_index.inventory)
    provenance = sc.Provenance("dev", loaded.manifest.version, "f" * 64,
                               loaded.answer_key.sha256, loaded.invoice_index.sha256,
                               loaded.inputs_aggregate_sha256)
    return sc.build_scorecard(result, provenance, sc.RunMetadata("2026-07-28T00:00:00Z", 1, 2, 3))


class ScorecardLegendTests(unittest.TestCase):
    def setUp(self) -> None:
        self.card = _scorecard_with_every_branch()
        self.text = LEGEND.read_text(encoding="utf-8")
        # Backticked names, with each dotted segment counted separately: `target.document_id`
        # documents both `target` and `document_id`, and requiring a second standalone mention
        # of each would push the document toward listing names twice for a checker's benefit.
        self.documented = {
            segment
            for quoted in re.findall(r"`([A-Za-z_][A-Za-z0-9_.]*)`", self.text)
            for segment in quoted.split(".")
            if segment
        }
        # Emphasis markers sit inside the phrases below in the rendered prose, so the search
        # normalizes them away rather than the prose being written around the checker.
        self.prose = re.sub(r"[*_]+", "", self.text).lower()

    def test_the_fixture_exercises_both_element_shapes(self) -> None:
        """The premise: if neither array is populated, the element fields go unchecked."""
        self.assertTrue(self.card["missed"], "fixture produced no missed findings")
        self.assertTrue(self.card["false_flags"], "fixture produced no false flags")
        self.assertIn("reason", self.card["false_flags"][0],
                      "a false flag should carry the reason it was counted against the agent")

    def test_every_emitted_field_is_documented(self) -> None:
        emitted = _field_names(self.card) - NOT_FIELDS
        undocumented = sorted(emitted - self.documented)
        self.assertEqual(
            undocumented, [],
            f"{len(undocumented)} scorecard field(s) are emitted but absent from "
            f"docs/SCORECARD.md: {undocumented}. Document each in backticks, or a reader "
            f"meets a field with no stated meaning (D100).",
        )

    def test_the_legend_documents_no_field_that_is_not_emitted(self) -> None:
        """The converse. A legend describing a field the scorecard no longer emits sends a
        reader looking for something that is not there — and is how a document goes stale
        while still looking maintained."""
        emitted = _field_names(self.card) | {"reason"}
        # Only names that look like scorecard fields are candidates; the document legitimately
        # mentions modules, commands and constants in backticks too.
        candidates = {
            name for name in self.documented
            if re.fullmatch(r"[a-z][a-z0-9_]*", name) and "_" in name
        }
        stale = sorted(candidates - emitted - {
            # Referenced deliberately, and not scorecard fields.
            "parse_float", "matching_policy", "invoice_count",
        })
        self.assertEqual(
            stale, [],
            f"docs/SCORECARD.md documents field name(s) the scorecard does not emit: "
            f"{stale}. Either the field was removed and the legend outlived it, or the name "
            f"is a typo a reader will search for in vain.",
        )

    def test_the_subtle_distinctions_are_stated_not_merely_listed(self) -> None:
        """A table of names would satisfy the checks above while leaving the misreadings
        intact. These are the four this project has actually had to explain."""
        for needle, what in (
            ("per invoice", "false_positive_rate's denominator"),
            ("different verdicts", "null versus 0.0000 precision"),
            ("not alternatives", "the three false-positive counters"),
            ("answer key's own note", "missed[].reasoning being key content"),
        ):
            with self.subTest(distinction=what):
                self.assertIn(
                    needle, self.prose,
                    f"the legend lists the fields but does not state {what}",
                )

    def test_the_summary_abbreviations_are_defined(self) -> None:
        """The `.txt` summary uses TP/FP/FN/P/R and `n/a`, defined in no other document.

        They are the first thing a reader meets and the easiest to guess wrong — `P` and `R`
        are not obvious, and `n/a` is not zero. Every abbreviation the summary actually emits
        must be defined, so the set is taken from the emitted text rather than a hand list."""
        loaded = load_dataset("dev", support.DATASETS)
        summary = sc.human_summary(self.card, score(
            loaded.answer_key.expected_findings,
            (loaded.answer_key.expected_findings[0],),
            loaded.invoice_index.inventory,
        ))
        emitted_abbrevs = {
            token for token in re.findall(r"\b(TP|FP|FN|P|R|n/a)\b", summary)
        }
        self.assertTrue(emitted_abbrevs, "the summary emitted no abbreviations to check")
        undefined = sorted(a for a in emitted_abbrevs if f"`{a}`" not in self.text)
        self.assertEqual(
            undefined, [],
            f"the summary uses abbreviation(s) the legend never defines: {undefined}. A reader "
            f"meeting `P` and `R` for the first time has no way to know which is which.",
        )
        for term in ("true positives", "false positives", "false negatives", "precision",
                     "recall"):
            with self.subTest(term=term):
                self.assertIn(term, self.prose, f"{term!r} is not spelled out in the legend")

    def test_the_legend_is_referenced_from_the_entry_documents(self) -> None:
        """A reference document nobody is pointed at is a document nobody reads (D92)."""
        for name in ("README.md", "docs/RUNBOOK.md"):
            with self.subTest(document=name):
                body = (support.REPO_ROOT / name).read_text(encoding="utf-8")
                self.assertIn(
                    "SCORECARD.md", body,
                    f"{name} does not point at the scorecard legend",
                )


if __name__ == "__main__":
    unittest.main()
