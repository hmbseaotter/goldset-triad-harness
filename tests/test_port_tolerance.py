"""What the port tolerates, and where tolerance stops (D109).

The agent's `findings.json` is also its **production** output. In production it will meet
invoices it cannot adjudicate, and the outcome class for that is deferred (D97). So the
question the agent's design turns on is: can it carry data the harness does not yet read,
without being rejected?

Measured before this was recorded: it can. Unknown fields on a finding, unknown fields inside
`target`, and unknown top-level keys in the artifact are all accepted and ignored. That was
**incidental behaviour** — nothing recorded it, nothing tested it. A later hardening that
rejected unknown fields would have been a reasonable change and would have broken the agent
across a repository boundary, discovered late. So it becomes a guarantee with a check.

**Where tolerance stops, and why the line falls there.** Unknown *values* in a closed
enumeration keep halting. The test is not "is this unexpected?" but **does ignoring it change
what the verdict means?**

* An unrecognised *field* is decoration the harness did not read. Ignoring it changes nothing
  about the findings that were scored.
* An unrecognised `status` such as `ESCALATE` is the agent asserting something about a finding
  that would otherwise be scored. Ignoring it would score the artifact while discarding part
  of its verdict — the agent's author would believe ten invoices were escalated while the
  scorecard reports them as absent findings. That is the confidently-wrong-score failure this
  project exists to prevent, so it halts (E7, E8).

Tolerated is not the same as unremarked. Ignoring input **silently** is its own defect: a
misspelled `reasonning` is a real agent bug, and the scorecard is where its author looks. The
scorecard will therefore report ignored input in an `ignored_input` block — deferred to land
with D97's escalation outcome so one `schema_version` bump serves both (D109). Until then this
suite pins the tolerance so the agent can rely on it.
"""

from __future__ import annotations

import unittest

from goldset_triad.schema import SchemaError, parse_findings_artifact

VALID = {
    "status": "DISCREPANCY",
    "category": "PRICE_VARIANCE",
    "scope": "LINE",
    "target": {"document_id": "INV-2001", "line_id": "2"},
}


def artifact(findings: list[dict], **extra: object) -> dict:
    return {"schema_version": "1", "findings": findings, **extra}


class AdditiveToleranceTests(unittest.TestCase):
    """The guarantee the agent's output design may rely on."""

    def test_an_unknown_field_on_a_finding_is_accepted(self) -> None:
        parsed = parse_findings_artifact(artifact([{**VALID, "escalation_reason": "no PO"}]))
        self.assertEqual(len(parsed), 1)

    def test_an_unknown_field_inside_target_is_accepted(self) -> None:
        finding = {**VALID, "target": {**VALID["target"], "po_hint": "PO-3001?"}}
        parsed = parse_findings_artifact(artifact([finding]))
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0].target.document_id, "INV-2001")

    def test_an_unknown_top_level_key_is_accepted(self) -> None:
        """The shape the agent will actually use: escalations alongside findings, in a sibling
        array the harness ignores until D97 teaches it to read them."""
        parsed = parse_findings_artifact(artifact(
            [dict(VALID)],
            escalations=[{"invoice_id": "INV-9999", "reason": "no resolvable purchase order"}],
        ))
        self.assertEqual(len(parsed), 1)

    def test_tolerance_does_not_alter_what_was_parsed(self) -> None:
        """Ignored means ignored: the parsed findings are identical with and without extras."""
        plain = parse_findings_artifact(artifact([dict(VALID)]))
        decorated = parse_findings_artifact(artifact(
            [{**VALID, "note": "x", "target": {**VALID["target"], "extra": 1}}],
            sidecar={"anything": True},
        ))
        self.assertEqual(plain, decorated)


class ToleranceStopsAtMeaningTests(unittest.TestCase):
    """Where tolerance stops. Each of these would change what the verdict means."""

    def _rejects(self, payload: dict) -> str:
        with self.assertRaises(SchemaError) as ctx:
            parse_findings_artifact(payload)
        return str(ctx.exception)

    def test_an_unknown_status_halts(self) -> None:
        message = self._rejects(artifact([{**VALID, "status": "ESCALATE"}]))
        self.assertIn("closed enumeration", message)
        self.assertIn("ESCALATE", message)

    def test_an_unknown_category_halts(self) -> None:
        message = self._rejects(artifact([{**VALID, "category": "NO_PURCHASE_ORDER"}]))
        self.assertIn("closed enumeration", message)

    def test_an_unknown_scope_halts(self) -> None:
        message = self._rejects(artifact([{**VALID, "scope": "INVOICE"}]))
        self.assertIn("closed enumeration", message)

    def test_an_unsupported_schema_version_halts(self) -> None:
        """A version bump is a shape change, so a future artifact is refused rather than
        half-read — the same reasoning as D66 in the opposite direction."""
        message = self._rejects({"schema_version": "99", "findings": [dict(VALID)]})
        self.assertIn("schema_version", message)

    def test_a_missing_required_field_still_halts(self) -> None:
        """Tolerance is additive only. An absent required field is not decoration."""
        incomplete = {k: v for k, v in VALID.items() if k != "category"}
        message = self._rejects(artifact([incomplete]))
        self.assertIn("category", message)


if __name__ == "__main__":
    unittest.main()
