"""Verify mode — recompute a stored scorecard and name what differs (D10, D66, D74).

The outcomes are RANKED, and the ranking is what most of these tests protect. A
difference has several possible causes and they are not equally informative: an
unrecognised schema version, inputs that moved, and numbers that changed on identical
inputs are three different statements about a scorecard, and collapsing them into
"verify failed" is the misdiagnosis pattern this project keeps finding (D50) — aimed at
the one feature whose entire purpose is to say whether a score can be trusted.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tests import support
from goldset_triad.cli import main
from goldset_triad.dataset import DatasetError
from goldset_triad.scorecard import SCORECARD_SCHEMA_VERSION
from goldset_triad.verify import MAX_REPORTED, Outcome, verify


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
        newline="\n",
    )


class VerifyModeTests(unittest.TestCase):
    def _scored(self, td: Path, dataset: str = "dev") -> tuple[Path, Path]:
        """Score ``dataset`` with a perfect findings artifact; return (scorecard, findings)."""
        key = support.read_json(support.key_path(dataset))
        findings = [
            {k: e[k] for k in ("status", "category", "scope", "target")}
            for e in key["expected_findings"]
        ]
        findings_path = td / "findings.json"
        _write_json(findings_path, {"schema_version": "1", "findings": findings})
        out = td / "out"
        rc = main([
            "score", "--dataset", dataset, "--datasets-root", str(support.DATASETS),
            "--findings", str(findings_path), "--out", str(out),
        ])
        self.assertEqual(rc, 0, "the fixture scoring run must succeed")
        cards = sorted(out.glob("*.json"))
        self.assertEqual(len(cards), 1)
        return cards[0], findings_path

    def _verify(self, card: Path, findings: Path, **kwargs: object):
        return verify(
            scorecard_path=card,
            dataset_ref="dev",
            findings_path=findings,
            search_root=support.DATASETS,
            **kwargs,  # type: ignore[arg-type]
        )

    def test_untouched_scorecard_verifies_identical_and_exits_zero(self) -> None:
        with tempfile.TemporaryDirectory() as t:
            td = Path(t)
            card, findings = self._scored(td)
            self.assertEqual(self._verify(card, findings).outcome, Outcome.IDENTICAL)
            rc = main([
                "verify", "--scorecard", str(card), "--dataset", "dev",
                "--datasets-root", str(support.DATASETS), "--findings", str(findings),
            ])
            self.assertEqual(rc, 0)

    def test_altered_numbers_are_detected_and_exit_nonzero(self) -> None:
        """A changed stored number is a SCORING difference, and the report names the
        field rather than handing over two documents to compare."""
        with tempfile.TemporaryDirectory() as t:
            td = Path(t)
            card, findings = self._scored(td)
            doctored = json.loads(card.read_text(encoding="utf-8"))
            doctored["metrics"]["per_category"]["PRICE_VARIANCE"]["true_positives"] = 99
            altered = td / "altered.json"
            _write_json(altered, doctored)

            result = self._verify(altered, findings)
            self.assertEqual(result.outcome, Outcome.SCORE_DIFFERS)
            joined = "\n".join(result.causes)
            self.assertIn("metrics.per_category.PRICE_VARIANCE.true_positives", joined)
            self.assertIn("99", joined)
            rc = main([
                "verify", "--scorecard", str(altered), "--dataset", "dev",
                "--datasets-root", str(support.DATASETS), "--findings", str(findings),
            ])
            self.assertNotEqual(rc, 0)

    def test_unrecognised_schema_version_is_its_own_outcome(self) -> None:
        """D66, recorded before this feature existed. A shape change and a scoring
        difference are indistinguishable once fields are compared, so the version is
        settled first and NOTHING else is compared — the resulting differences must not
        be presented as a scoring discrepancy."""
        with tempfile.TemporaryDirectory() as t:
            td = Path(t)
            card, findings = self._scored(td)
            stale = json.loads(card.read_text(encoding="utf-8"))
            stale["schema_version"] = "1"
            # Change a scored number too. Under a shape mismatch this must NOT surface:
            # if it did, a reader would be sent to audit arithmetic across a schema
            # migration, which is exactly what D66 exists to prevent.
            stale["metrics"]["per_category"]["PRICE_VARIANCE"]["true_positives"] = 42
            old = td / "old_schema.json"
            _write_json(old, stale)

            result = self._verify(old, findings)
            self.assertEqual(result.outcome, Outcome.SCHEMA_UNRECOGNISED)
            joined = "\n".join(result.causes)
            self.assertIn("'1'", joined)
            self.assertIn(SCORECARD_SCHEMA_VERSION, joined)
            self.assertNotIn("PRICE_VARIANCE", joined)
            self.assertNotIn("42", joined)
            rc = main([
                "verify", "--scorecard", str(old), "--dataset", "dev",
                "--datasets-root", str(support.DATASETS), "--findings", str(findings),
            ])
            self.assertNotEqual(rc, 0)

    def test_a_wrong_typed_schema_version_is_unrecognised_not_a_scoring_difference(self) -> None:
        """The same statement as E13, aimed at the coercion that defeated it (D78).

        `str(stored["schema_version"])` stood at the gate, so a scorecard carrying the
        int `2` passed the version check as if it carried `"2"` — and the raw value then
        went on into the body comparison and surfaced as
        `schema_version: stored 2, recomputed '2'` beneath the heading *"the same inputs
        recompute to a different score"*. That is precisely the misdiagnosis D66 recorded
        this feature to prevent, produced by a leniency nobody asked for, in the one
        feature whose whole purpose is to say whether a score can be trusted."""
        with tempfile.TemporaryDirectory() as t:
            td = Path(t)
            card, findings = self._scored(td)
            typed = json.loads(card.read_text(encoding="utf-8"))
            typed["schema_version"] = 2  # an int, where this harness emits the string "2"
            path = td / "int_version.json"
            _write_json(path, typed)

            result = self._verify(path, findings)
            self.assertEqual(result.outcome, Outcome.SCHEMA_UNRECOGNISED)
            joined = "\n".join(result.causes)
            self.assertIn("int", joined)
            self.assertIn("NOT a scoring discrepancy", joined)
            self.assertNotIn("recompute to a different score", joined)

    def test_a_scorecard_declaring_no_schema_version_is_unrecognised_not_compared(self) -> None:
        """Absence is not version "0". A scorecard with no declared shape is a shape
        this harness does not recognise, which is the same outcome and not a scoring
        difference."""
        with tempfile.TemporaryDirectory() as t:
            td = Path(t)
            card, findings = self._scored(td)
            stripped = json.loads(card.read_text(encoding="utf-8"))
            del stripped["schema_version"]
            path = td / "no_version.json"
            _write_json(path, stripped)
            result = self._verify(path, findings)
            self.assertEqual(result.outcome, Outcome.SCHEMA_UNRECOGNISED)
            self.assertIn("no schema_version", "\n".join(result.causes))

    def test_a_fingerprint_mismatch_outranks_a_body_difference(self) -> None:
        """The precedence, asserted rather than assumed (D74).

        Scoring a DIFFERENT findings artifact changes both the fingerprint and the
        numbers, so both causes are live at once and the ranking decides which is
        reported. "You scored different data" and "the numbers are wrong" are different
        findings, and only the second is about scoring — reporting it when the first is
        true sends a reader to audit arithmetic that was never at fault (D50)."""
        with tempfile.TemporaryDirectory() as t:
            td = Path(t)
            card, _findings = self._scored(td)
            other = td / "other.json"
            _write_json(other, {"schema_version": "1", "findings": []})

            result = self._verify(card, other)
            self.assertEqual(result.outcome, Outcome.FINGERPRINT_MISMATCH)
            joined = "\n".join(result.causes)
            self.assertIn("findings artifact", joined)
            # The body differs too -- an empty artifact misses every expectation. It must
            # not be what gets reported.
            self.assertNotIn("metrics.", joined)

    def test_without_a_baseline_the_per_file_limit_is_stated(self) -> None:
        """D74. The scorecard stores only the aggregate inputs digest (D27 chose that
        over a per-file list in every durable record), so on a mismatch verify can name
        that the inputs moved but not which file. It says so, and says what would let it,
        rather than implying a diagnosis it cannot make."""
        with tempfile.TemporaryDirectory() as t:
            td = Path(t)
            copied_manifest = support.copy_dataset("dev", td / "d")
            findings_key = support.read_json(copied_manifest.parent / "dev_answer_key.json")
            findings = td / "f.json"
            _write_json(findings, {
                "schema_version": "1",
                "findings": [
                    {k: e[k] for k in ("status", "category", "scope", "target")}
                    for e in findings_key["expected_findings"]
                ],
            })
            out = td / "out"
            self.assertEqual(0, main([
                "score", "--dataset", str(copied_manifest), "--datasets-root",
                str(support.DATASETS), "--findings", str(findings), "--out", str(out),
            ]))
            card = sorted(out.glob("*.json"))[0]

            po = copied_manifest.parent / "inputs" / "purchase_orders" / "PO-3001.json"
            po.write_bytes(po.read_bytes() + b" ")  # one byte, inside the inputs tree

            result = verify(
                scorecard_path=card, dataset_ref=str(copied_manifest),
                findings_path=findings, search_root=support.DATASETS,
            )
            self.assertEqual(result.outcome, Outcome.FINGERPRINT_MISMATCH)
            joined = "\n".join(result.causes)
            self.assertIn("--baseline-inputs", joined)
            self.assertIn("only the AGGREGATE", joined)

    def test_a_baseline_names_the_divergent_file(self) -> None:
        """Handed the other side, verify delivers the diagnosis D27 described: not that
        the aggregate moved, but which file moved."""
        with tempfile.TemporaryDirectory() as t:
            td = Path(t)
            copied_manifest = support.copy_dataset("dev", td / "d")
            key = support.read_json(copied_manifest.parent / "dev_answer_key.json")
            findings = td / "f.json"
            _write_json(findings, {
                "schema_version": "1",
                "findings": [
                    {k: e[k] for k in ("status", "category", "scope", "target")}
                    for e in key["expected_findings"]
                ],
            })
            out = td / "out"
            self.assertEqual(0, main([
                "score", "--dataset", str(copied_manifest), "--datasets-root",
                str(support.DATASETS), "--findings", str(findings), "--out", str(out),
            ]))
            card = sorted(out.glob("*.json"))[0]

            po = copied_manifest.parent / "inputs" / "purchase_orders" / "PO-3001.json"
            po.write_bytes(po.read_bytes() + b" ")

            result = verify(
                scorecard_path=card, dataset_ref=str(copied_manifest),
                findings_path=findings, search_root=support.DATASETS,
                baseline_inputs=support.DATASETS / "dev" / "inputs",
            )
            self.assertEqual(result.outcome, Outcome.FINGERPRINT_MISMATCH)
            joined = "\n".join(result.causes)
            self.assertIn("purchase_orders/PO-3001.json", joined)
            # Named, not merely listed: the untouched files must not be reported as
            # divergent, or the diagnosis is a directory listing wearing a verdict.
            self.assertNotIn("PO-3002.json", joined)

    def test_naming_a_different_dataset_says_so_in_one_line(self) -> None:
        """The likeliest operator error on a command taking three separate paths (D79).

        The scorecard records the dataset identifier and version, and verify holds both
        before it compares a single digest. It did not look — so pointing verify at the
        wrong split produced three digest mismatches *and* a paragraph advising the
        reader to fetch a pristine inputs directory, sending them to hunt a file that
        never moved. The one-line answer was in hand the whole time, which is what makes
        it the misdiagnosis D50 rules worse than silence."""
        with tempfile.TemporaryDirectory() as t:
            td = Path(t)
            card, findings = self._scored(td)
            result = verify(
                scorecard_path=card, dataset_ref="dev-zero-defect",
                findings_path=findings, search_root=support.DATASETS,
            )
            self.assertEqual(result.outcome, Outcome.DATASET_MISMATCH)
            joined = "\n".join(result.causes)
            self.assertIn("dataset identifier", joined)
            self.assertIn("'dev'", joined)
            self.assertIn("'dev-zero-defect'", joined)
            # None of the downstream noise. A digest of a different dataset differs for
            # a reason that is not tampering, and --baseline-inputs would not help.
            self.assertNotIn("--baseline-inputs", joined)
            self.assertNotIn("sha256", joined)
            self.assertNotIn("AGGREGATE", joined)

    def test_an_absent_fingerprint_is_a_shape_defect_not_a_mismatch(self) -> None:
        """A scorecard that omits a digest is malformed; a scorecard whose digest
        disagrees with the artifact on disk is evidence. `.get()` collapsed the first
        into the second and reported `the scorecard records None` — a scorecard being
        described as holding a value it does not hold (D79). Exit 2, not 1: this is a
        verification that could not happen, not one that failed."""
        with tempfile.TemporaryDirectory() as t:
            td = Path(t)
            card, findings = self._scored(td)
            maimed = json.loads(card.read_text(encoding="utf-8"))
            del maimed["fingerprints"]["answer_key_sha256"]
            path = td / "no_key_digest.json"
            _write_json(path, maimed)

            with self.assertRaises(DatasetError) as caught:
                self._verify(path, findings)
            message = str(caught.exception)
            self.assertIn("answer_key_sha256", message)
            self.assertIn("does not have the shape it claims", message)
            self.assertNotIn("None", message)
            rc = main([
                "verify", "--scorecard", str(path), "--dataset", "dev",
                "--datasets-root", str(support.DATASETS), "--findings", str(findings),
            ])
            self.assertEqual(rc, 2)

    def test_a_baseline_diagnosis_is_bounded(self) -> None:
        """The branch a reader reaches only when something is already wrong is the one
        that printed one line per file (D79). The score-difference list was capped and
        this one was not, so a change across the whole inputs tree produced the diff
        dump this module's docstring promises never to produce."""
        with tempfile.TemporaryDirectory() as t:
            td = Path(t)
            copied_manifest = support.copy_dataset("dev", td / "d")
            key = support.read_json(copied_manifest.parent / "dev_answer_key.json")
            findings = td / "f.json"
            _write_json(findings, {
                "schema_version": "1",
                "findings": [
                    {k: e[k] for k in ("status", "category", "scope", "target")}
                    for e in key["expected_findings"]
                ],
            })
            out = td / "out"
            self.assertEqual(0, main([
                "score", "--dataset", str(copied_manifest), "--datasets-root",
                str(support.DATASETS), "--findings", str(findings), "--out", str(out),
            ]))
            card = sorted(out.glob("*.json"))[0]

            moved = 0
            for path in sorted((copied_manifest.parent / "inputs").rglob("*")):
                if path.is_file():
                    path.write_bytes(path.read_bytes() + b" ")
                    moved += 1
            self.assertGreater(moved, MAX_REPORTED, "the premise: more files than the cap")

            result = verify(
                scorecard_path=card, dataset_ref=str(copied_manifest),
                findings_path=findings, search_root=support.DATASETS,
                baseline_inputs=support.DATASETS / "dev" / "inputs",
            )
            self.assertEqual(result.outcome, Outcome.FINGERPRINT_MISMATCH)
            per_file = [c for c in result.causes if c.startswith("    ")]
            self.assertLessEqual(len(per_file), MAX_REPORTED)
            joined = "\n".join(result.causes)
            # The count is still stated in full: bounding what is printed must not
            # bound what is reported, or the cap becomes its own quiet omission.
            self.assertIn(f"{moved} file(s) diverge", joined)
            self.assertIn("further diverging file(s)", joined)

    def test_an_unreadable_scorecard_is_an_error_not_a_failed_verification(self) -> None:
        """A verification that never happened is not a verification that failed (D50).
        The halt names the cause, and the CLI distinguishes it by exit code."""
        with tempfile.TemporaryDirectory() as t:
            td = Path(t)
            _card, findings = self._scored(td)
            with self.assertRaises(DatasetError):
                self._verify(td / "does_not_exist.json", findings)
            rc = main([
                "verify", "--scorecard", str(td / "does_not_exist.json"), "--dataset",
                "dev", "--datasets-root", str(support.DATASETS), "--findings", str(findings),
            ])
            self.assertEqual(rc, 2, "an error is exit 2; a detected difference is exit 1")


if __name__ == "__main__":
    unittest.main()
