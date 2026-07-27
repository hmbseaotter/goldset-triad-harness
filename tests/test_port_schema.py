"""Findings payload schema v1 — the port (schema-violation criteria)."""

from __future__ import annotations

import json
import unittest
from decimal import Decimal

from tests import support
from goldset_triad.schema import (
    SchemaError,
    Status,
    parse_findings_artifact,
)


def _artifact(finding: dict) -> dict:
    return {"schema_version": "1", "findings": [finding]}


def _p(finding: dict):
    return parse_findings_artifact(json.loads(json.dumps(_artifact(finding)), parse_float=Decimal))


class SchemaTests(unittest.TestCase):
    def test_category_outside_enum_halts_as_schema_violation(self) -> None:
        with self.assertRaises(SchemaError) as ctx:
            _p({"status": "DISCREPANCY", "category": "TAX_ERROR", "scope": "LINE",
                "target": {"document_id": "INV-1", "line_id": "1"}})
        self.assertEqual(ctx.exception.field, "category")

    def test_malformed_finding_names_finding_and_field(self) -> None:
        with self.assertRaises(SchemaError) as ctx:
            _p({"status": "DISCREPANCY", "category": "PRICE_VARIANCE", "scope": "LINE",
                "target": {"document_id": "INV-1"}})  # missing line_id
        self.assertEqual(ctx.exception.finding_index, 0)
        self.assertEqual(ctx.exception.field, "line_id")

    def test_document_scope_absent_line_id_is_malformed(self) -> None:
        with self.assertRaises(SchemaError):
            _p({"status": "DISCREPANCY", "category": "TAX_VARIANCE", "scope": "DOCUMENT",
                "target": {"document_id": "INV-1", "line_id": ""}})

    def test_document_scope_nonsentinel_line_id_is_malformed(self) -> None:
        with self.assertRaises(SchemaError):
            _p({"status": "DISCREPANCY", "category": "TAX_VARIANCE", "scope": "DOCUMENT",
                "target": {"document_id": "INV-1", "line_id": "3"}})

    def test_line_scope_using_sentinel_is_malformed(self) -> None:
        with self.assertRaises(SchemaError):
            _p({"status": "DISCREPANCY", "category": "PRICE_VARIANCE", "scope": "LINE",
                "target": {"document_id": "INV-1", "line_id": "__DOCUMENT__"}})

    def test_confidence_must_be_number_in_unit_interval(self) -> None:
        """Both directions. This was rejection-only, which D68 settled is not enough: a
        check that only ever refuses would pass while refusing *everything*, and the
        accepting half is the one a reader of the published example depends on.

        The valid case goes in as a JSON number and comes back a `Decimal`, because `_p`
        round-trips through JSON with `parse_float=Decimal` — the same path a real artifact
        takes (D77). Asserting the returned type is the point: a `float` arriving here would
        put a float on a path this project keeps free of them."""
        with self.assertRaises(SchemaError):
            _p({"status": "DISCREPANCY", "category": "PRICE_VARIANCE", "scope": "LINE",
                "target": {"document_id": "INV-1", "line_id": "1"}, "confidence": 2})
        accepted = _p({"status": "DISCREPANCY", "category": "PRICE_VARIANCE", "scope": "LINE",
                       "target": {"document_id": "INV-1", "line_id": "1"},
                       "confidence": 0.95})[0]
        self.assertEqual(accepted.confidence, Decimal("0.95"),
                         "a valid confidence must be accepted and carried through")
        self.assertIsInstance(accepted.confidence, Decimal)

    def test_valid_match_status_parses_and_is_carried(self) -> None:
        findings = _p({"status": "MATCH", "category": "PRICE_VARIANCE", "scope": "LINE",
                       "target": {"document_id": "INV-1", "line_id": "1"},
                       "confidence": 0.8, "reasoning": "looks right"})
        self.assertEqual(findings[0].status, Status.MATCH)
        self.assertEqual(findings[0].confidence, Decimal("0.8"))

    def test_empty_findings_artifact_is_valid(self) -> None:
        findings = parse_findings_artifact({"schema_version": "1", "findings": []})
        self.assertEqual(findings, ())


class SchemaVersionDeclarationTests(unittest.TestCase):
    """The port's version is declared, never assumed, and never coerced (D78).

    Two defects lived in one line, `raw.get("schema_version", SCHEMA_VERSION)`:

    * **absence became the current version**, so an artifact declaring nothing was read
      as declaring exactly the value that makes it acceptable — while verify mode, one
      module away, had decided the opposite for the same question about a scorecard
      (D66: absence is not a version). Two opposite answers is one too many;
    * **the comparison did not check the type**, so `{"schema_version": 1}` produced
      *"unsupported schema_version '1'; this harness scores v1"* — a message that reads
      as a contradiction, because an int and a str render identically inside quotes.
    """

    def test_an_absent_schema_version_is_rejected_not_assumed(self) -> None:
        with self.assertRaises(SchemaError) as ctx:
            parse_findings_artifact({"findings": []})
        self.assertEqual(ctx.exception.field, "schema_version")
        self.assertIn("declares no schema_version", str(ctx.exception))
        self.assertIn("will not assume", str(ctx.exception))

    def test_a_wrong_typed_schema_version_names_the_type(self) -> None:
        """The reader is told the artifact declared a number where a string was
        required, rather than left to wonder why v1 is unsupported by a harness that
        scores v1."""
        with self.assertRaises(SchemaError) as ctx:
            parse_findings_artifact({"schema_version": 1, "findings": []})
        self.assertEqual(ctx.exception.field, "schema_version")
        self.assertIn("must be a string, not int", str(ctx.exception))

    def test_an_unsupported_version_is_still_reported_as_unsupported(self) -> None:
        """The converse: a correctly-typed version this harness does not score is a
        different finding from a malformed declaration, and keeps its own message."""
        with self.assertRaises(SchemaError) as ctx:
            parse_findings_artifact({"schema_version": "9", "findings": []})
        self.assertEqual(ctx.exception.field, "schema_version")
        self.assertIn("unsupported schema_version '9'", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
