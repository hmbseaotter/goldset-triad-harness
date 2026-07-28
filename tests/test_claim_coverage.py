"""Every claim an artifact makes is compared by a named check, on every split (D67).

The pattern this exists to end. Four separate decisions were the same defect wearing
different clothes: an artifact declared an authority and nothing compared it.

* D58 — the generator declared the rules the datasets were authored under; nothing
  compared the data to it.
* D59 — `audit_key --help` declared the command name `goldset-triad-audit-key`; nothing
  compared it to what the package provided, so the name did not exist.
* D64a — the held-out manifest declared a `generator_sha256`; nothing compared it, because
  every staleness check iterated the *dev* splits.
* D64b — the guard template declared itself the source of truth and instructed "re-stamp,
  never hand-edit"; nothing compared the stamped copy to it, so the instruction *was* the
  enforcement.

The rule was even written down, in D59: *anything a tool says about itself is a claim, and
every claim gets a check.* It was written and then violated in the same commit — D64a and
D64b are that commit's own unchecked claims. That is the lesson: a rule recorded as prose
is enforced by whoever remembers it, and a second reader will always find the instances the
first one's attention missed. So the rule is machine-checked here instead.

Two halves, and the second is the one that matters:

1. Discovery — every claim-shaped field on disk is registered. Adding a stamp to an
   artifact without registering a check for it fails.
2. **Symmetry** — every registered claim is checked on every split this machine can see,
   held-out included. Partial coverage must name a reason. This is the half that catches
   D64a's shape, which was never an oversight of attention: the loop's universe simply
   excluded the split, and no amount of care inspects a set you did not enumerate.

Reading held-out artifacts here leaks nothing: this compares digests, versions and
threshold text, never answer-key content. When the secret tier is absent the held-out split
drops out of `known_splits()` and the checks narrow to what is present, because D14 requires
the suite to pass from a clone.
"""

from __future__ import annotations

import importlib
import json
import unittest
from dataclasses import dataclass, field

from tests import support
from goldset_triad.dataset import load_dataset

#: Field-name fragments that mark a value as a claim about other state. Anything matching
#: these on disk must be registered. Deliberately name-based: it is the half that works
#: without anyone remembering to declare a new stamp.
CLAIM_NAME_FRAGMENTS = ("sha256", "digest", "generator")


@dataclass(frozen=True)
class Claim:
    """One assertion an artifact makes, and the checks that hold it to account."""

    artifact: str  # "manifest" | "key" | "index" | "policy"
    # Named `field_name`, not `field`: as `field` it shadowed `dataclasses.field` used on the
    # line below, which works at runtime (an annotation-only attribute binds nothing, so the
    # lookup falls through to module scope) and is exactly the kind of accident that stops
    # working after an innocuous edit. pyright flagged it as unbound.
    field_name: str  # the field name, or a policy key
    asserts: str  # what it claims, in words
    checks: tuple[str, ...]  # dotted test paths that compare it
    covers: frozenset[str] = field(default_factory=frozenset)  # empty = every known split
    partial_reason: str = ""  # required when `covers` is narrower than the known splits


REGISTRY: tuple[Claim, ...] = (
    Claim(
        artifact="manifest",
        field_name="generator_sha256",
        asserts="the generator source this split was authored from (D58)",
        checks=(
            "test_generator_staleness.GeneratorStampTests.test_every_shipped_dataset_records_its_generator",
            "test_generator_staleness.GeneratorFreshnessTests.test_stamp_matches_the_current_generator",
            "test_generator_staleness.HeldOutStalenessTests.test_held_out_stamp_matches_the_current_generator",
        ),
    ),
    Claim(
        artifact="manifest",
        field_name="version",
        asserts="the dataset version the scorecard records as provenance",
        checks=("test_scorecard_repro.ScorecardTests.test_records_dataset_identifier_and_version",),
        covers=frozenset({"dev"}),
        partial_reason=(
            "the scorecard test scores one split; the version is copied through verbatim "
            "rather than interpreted, so per-split repetition would exercise the same line"
        ),
    ),
    Claim(
        artifact="key",
        field_name="dataset_version",
        asserts="the version the key was authored for, which must match its manifest",
        checks=("test_claim_coverage.ClaimSymmetryTests.test_key_version_matches_its_manifest",),
    ),
    Claim(
        artifact="policy",
        field_name="materiality_threshold",
        asserts="the floor, cap and rate the shipped rule applies (D53)",
        checks=(
            "test_ground_truth.PolicyTests.test_policy_numbers_match_the_shipping_rule_implementation",
        ),
    ),
    Claim(
        artifact="policy",
        field_name="categories",
        asserts="the closed category enumeration an agent competes against",
        checks=("test_ground_truth.PolicyTests.test_matching_policy_declares_every_rule_the_harness_applies",
            "test_ground_truth.PolicyTests.test_every_published_rule_describes_what_the_code_does"),
    ),
    Claim(
        artifact="policy",
        field_name="dataset_guarantees",
        asserts="what the DATA promises, so an implementer need not guess at a silence (D96)",
        checks=(
            "test_claim_coverage.PublishedGuaranteeTests.test_every_purchase_order_line_has_at_least_one_receipt",
            "test_claim_coverage.PublishedGuaranteeTests.test_every_invoice_line_resolves_to_one_purchase_order_line",
            "test_claim_coverage.PublishedGuaranteeTests.test_the_policy_publishes_both_guarantees",
        ),
    ),
)


def _artifact_path(split: support.Split, artifact: str):
    return {"manifest": split.manifest, "key": split.key,
            "index": split.index, "policy": split.policy}[artifact]


def _resolve(dotted: str):
    module_name, cls_name, method_name = dotted.split(".")
    module = importlib.import_module(f"tests.{module_name}")
    return getattr(getattr(module, cls_name), method_name)


class ClaimDiscoveryTests(unittest.TestCase):
    """Half one: nothing claim-shaped sits on disk unregistered."""

    def test_every_claim_shaped_field_on_disk_is_registered(self) -> None:
        registered = {(c.artifact, c.field_name) for c in REGISTRY}
        unregistered: list[str] = []
        for split in support.known_splits():
            for artifact in ("manifest", "key", "index", "policy"):
                path = _artifact_path(split, artifact)
                if not path.is_file():
                    continue
                obj = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(obj, dict):
                    continue
                for name in obj:
                    low = name.lower()
                    if not any(frag in low for frag in CLAIM_NAME_FRAGMENTS):
                        continue
                    if (artifact, name) not in registered:
                        unregistered.append(f"{split.name}/{path.name}:{name}")
        self.assertEqual(
            unregistered, [],
            f"claim-shaped field(s) with no registered check: {unregistered}. Register each "
            f"in REGISTRY naming the check that compares it, or the artifact declares an "
            f"authority nothing holds it to (D67).",
        )

    def test_registry_has_no_stale_entries(self) -> None:
        """A registry entry for a field that no longer exists is a check guarding nothing.

        The register must not itself go stale — it would otherwise report coverage of an
        artifact that has moved on, which is the failure mode it exists to prevent."""
        splits = support.known_splits()
        missing: list[str] = []
        for claim in REGISTRY:
            seen = False
            for split in splits:
                path = _artifact_path(split, claim.artifact)
                if not path.is_file():
                    continue
                obj = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(obj, dict) and claim.field_name in obj:
                    seen = True
                    break
            if not seen:
                missing.append(f"{claim.artifact}.{claim.field_name}")
        self.assertEqual(
            missing, [],
            f"REGISTRY names field(s) that exist on no split: {missing}; the claim was "
            f"removed or renamed and its entry outlived it",
        )

    def test_every_registered_check_resolves(self) -> None:
        unresolved: list[str] = []
        for claim in REGISTRY:
            for dotted in claim.checks:
                try:
                    _resolve(dotted)
                except (ImportError, AttributeError, ValueError):
                    unresolved.append(f"{claim.artifact}.{claim.field_name} -> {dotted}")
        self.assertEqual(unresolved, [], f"registered check(s) do not exist: {unresolved}")

    def test_partial_coverage_states_a_reason(self) -> None:
        """Narrowing coverage is allowed; narrowing it silently is not."""
        for claim in REGISTRY:
            if claim.covers:
                self.assertTrue(
                    claim.partial_reason.strip(),
                    f"{claim.artifact}.{claim.field_name} covers only {sorted(claim.covers)} "
                    f"with no reason given",
                )


class ClaimSymmetryTests(unittest.TestCase):
    """Half two: every claim is checked on every split, held-out included (the D64a rule)."""

    def test_every_claim_is_checked_on_every_known_split(self) -> None:
        known = {s.name for s in support.known_splits()}
        gaps: list[str] = []
        for claim in REGISTRY:
            if claim.covers:
                continue  # declared partial, with a reason asserted above
            for split in sorted(known):
                path = _artifact_path(
                    next(s for s in support.known_splits() if s.name == split), claim.artifact
                )
                if not path.is_file():
                    continue
                obj = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(obj, dict) and claim.field_name not in obj:
                    gaps.append(f"{split}: {claim.artifact}.{claim.field_name} absent")
        self.assertEqual(
            gaps, [],
            f"a claim is registered as covering every split but is missing from some: "
            f"{gaps}",
        )

    def test_the_held_out_split_is_in_the_universe_when_present(self) -> None:
        """The premise of everything above. If the secret tier is here, held-out must be
        enumerated -- otherwise every symmetry assertion narrows to the dev splits and
        passes for the same reason D64a passed."""
        secret = support.find_secret_dir()
        names = {s.name for s in support.known_splits()}
        if secret is None:
            self.skipTest("no secret tier on this machine; held-out is out of reach (D14)")
        self.assertIn(
            "held-out", names,
            f"the secret tier is present at {secret} but known_splits() returned only "
            f"{sorted(names)}; split-level checks would silently skip the split whose "
            f"numbers carry the most weight",
        )

    def test_key_version_matches_its_manifest(self) -> None:
        """The key declares a dataset_version; the manifest declares one too. Nothing
        compared them, so a key authored for one version could be scored as another."""
        for split in support.known_splits():
            with self.subTest(split=split.name):
                manifest = json.loads(split.manifest.read_text(encoding="utf-8"))
                key = json.loads(split.key.read_text(encoding="utf-8"))
                self.assertEqual(
                    str(key["dataset_version"]), str(manifest["version"]),
                    f"{split.name}: the answer key says version "
                    f"{key['dataset_version']!r} and the manifest says "
                    f"{manifest['version']!r}",
                )
                self.assertEqual(
                    str(key["dataset_identifier"]), str(manifest["identifier"]),
                    f"{split.name}: key and manifest disagree about the identifier",
                )


class PublishedGuaranteeTests(unittest.TestCase):
    """The policy's `dataset_guarantees` are measured, not asserted in prose (D96).

    `payable_quantity` published how to SUM goods receipts and never what an empty set means.
    An implementer reading it could take zero (yielding QTY_UNDER_SHIPMENT) or "cannot
    compute" (yielding an escalation). The key is authored on the first reading, so the second
    — the better business answer — would score as a false negative for a convention nobody
    published. That is D53's own concern: an agent judged against a rule it was never told.

    Unreachable today, which is why the fix is to publish the *guarantee* rather than invent a
    convention: the empty-receipt case does not occur, so nobody has to handle it. It becomes
    live the moment `[P3]` authors a purchase-order line with no receipt — at which point the
    guarantee fails here, loudly, and the P4 outcome class is what makes the case expressible.

    Published without a check, the guarantee would itself be an unchecked claim (D67)."""

    def _po_and_receipt_lines(self, split: support.Split):
        po_lines: set[tuple[str, str]] = set()
        for path in sorted((split.inputs / "purchase_orders").glob("*.json")):
            po = json.loads(path.read_text(encoding="utf-8"))
            for line in po["lines"]:
                po_lines.add((str(po["po_number"]), str(line["line_no"])))
        received: set[tuple[str, str]] = set()
        for path in sorted((split.inputs / "goods_receipts").glob("*.json")):
            receipt = json.loads(path.read_text(encoding="utf-8"))
            for line in receipt["lines"]:
                received.add((str(receipt["po_number"]), str(line["po_line_no"])))
        return po_lines, received

    def test_the_inputs_directory_resolves_on_every_split(self) -> None:
        """The premise. Assuming `<root>/inputs` reports held-out as empty rather than
        missing, which is a vacuous pass — so the resolution is asserted before it is used."""
        for split in support.known_splits():
            with self.subTest(split=split.name):
                self.assertTrue(
                    split.inputs.is_dir(),
                    f"{split.name}: inputs_dir does not resolve to {split.inputs}",
                )
                self.assertTrue(
                    any(split.inputs.rglob("*.json")),
                    f"{split.name}: inputs resolve but hold no documents, so any loop over "
                    f"them would pass by checking nothing",
                )

    def test_every_purchase_order_line_has_at_least_one_receipt(self) -> None:
        for split in support.known_splits():
            with self.subTest(split=split.name):
                po_lines, received = self._po_and_receipt_lines(split)
                self.assertTrue(po_lines, f"{split.name}: no purchase-order lines found")
                uncovered = sorted(po_lines - received)
                self.assertEqual(
                    uncovered, [],
                    f"{split.name}: purchase-order line(s) with no goods receipt: "
                    f"{uncovered}. The published policy guarantees this cannot happen, so "
                    f"either the guarantee is now false and must be withdrawn, or the data is "
                    f"wrong. If [P3] is deliberately introducing the case, that needs the "
                    f"'cannot adjudicate' outcome class first (D96).",
                )

    def test_every_invoice_line_resolves_to_one_purchase_order_line(self) -> None:
        """The second guarantee. Enforced at load by D48/D50/D56; asserted here because the
        policy now PUBLISHES it, and a published guarantee needs its own check."""
        for split in support.known_splits():
            with self.subTest(split=split.name):
                loaded = load_dataset(str(split.manifest), support.DATASETS)
                counts: dict[tuple[str, str], int] = {}
                for entry in loaded.answer_key.correspondence:
                    key = (str(entry["invoice_id"]), str(entry["invoice_line_id"]))
                    counts[key] = counts.get(key, 0) + 1
                targets = loaded.invoice_index.inventory.line_targets
                self.assertEqual(
                    sorted(set(counts) ^ set(targets)), [],
                    f"{split.name}: invoice lines and correspondence rows do not correspond "
                    f"one-to-one",
                )
                self.assertEqual(
                    [k for k, n in counts.items() if n != 1], [],
                    f"{split.name}: an invoice line maps to more than one PO line",
                )

    def test_the_policy_publishes_both_guarantees(self) -> None:
        """And the text is present on every split, not just `dev` (D67's enumeration)."""
        for split in support.known_splits():
            with self.subTest(split=split.name):
                policy = json.loads(split.policy.read_text(encoding="utf-8"))
                stated = str(policy.get("dataset_guarantees", ""))
                self.assertIn("at least one goods receipt", stated)
                self.assertIn("exactly one", stated)


if __name__ == "__main__":
    unittest.main()
