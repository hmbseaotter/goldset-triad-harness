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
        with self.assertRaises(SchemaError):
            _p({"status": "DISCREPANCY", "category": "PRICE_VARIANCE", "scope": "LINE",
                "target": {"document_id": "INV-1", "line_id": "1"}, "confidence": 2})

    def test_valid_match_status_parses_and_is_carried(self) -> None:
        findings = _p({"status": "MATCH", "category": "PRICE_VARIANCE", "scope": "LINE",
                       "target": {"document_id": "INV-1", "line_id": "1"},
                       "confidence": 0.8, "reasoning": "looks right"})
        self.assertEqual(findings[0].status, Status.MATCH)
        self.assertEqual(findings[0].confidence, Decimal("0.8"))

    def test_empty_findings_artifact_is_valid(self) -> None:
        findings = parse_findings_artifact({"schema_version": "1", "findings": []})
        self.assertEqual(findings, ())


if __name__ == "__main__":
    unittest.main()
