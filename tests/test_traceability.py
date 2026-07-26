"""Traceability — every [P1] acceptance criterion is bound to a covering test.

An untested eval harness is self-refuting, so the acceptance gate is machine-
checked rather than hand-ticked: each criterion below names either a concrete test
(``module.Class.method``, asserted to exist) or a documented ``MANUAL:``
verification for the few criteria that are generation-side or environment-level
and cannot run inside the in-repo dev-split suite by construction.
"""

from __future__ import annotations

import importlib
import unittest

# (criterion id, short description, coverage). Coverage is a dotted test path under
# the ``tests`` package, or a string beginning "MANUAL:" with the reason.
CRITERIA: list[tuple[str, str, str]] = [
    # --- happy path ---
    ("H1", "perfect findings score P/R 1.0 in every category",
     "test_scoring_engine.ScoringTests.test_perfect_findings_score_precision_and_recall_one"),
    ("H2", "scorecard emitted as parseable JSON and human summary",
     "test_scorecard_repro.ScorecardTests.test_json_parses_and_summary_emitted"),
    ("H3", "scorecard records dataset id and version",
     "test_scorecard_repro.ScorecardTests.test_records_dataset_identifier_and_version"),
    ("H4", "scorecard embeds four fingerprints",
     "test_scorecard_repro.ScorecardTests.test_embeds_four_fingerprints"),
    ("H5", "editing the invoice index changes its fingerprint",
     "test_ground_truth.TruthSourceTests.test_index_fingerprint_changes_when_index_edited"),
    ("H6", "regenerating dev PDFs from the seed is byte-identical",
     "MANUAL: generation-side (the generator is out-of-repo by design, D14); confirmed "
     "byte-identical across regenerations during the build."),
    ("H7", "no PDF/parser importable from the scoring engine; reads no document",
     "test_constraints_scan.ConstraintScanTests.test_loader_reads_no_invoice_pdf"),
    ("H8", "invoice index absent from agent-readable inputs",
     "test_ground_truth.TruthSourceTests.test_index_absent_from_agent_readable_inputs"),
    ("H9", "scoring engine implements no domain rule",
     "test_constraints_scan.ConstraintScanTests.test_scoring_module_implements_no_domain_rule"),
    ("H10", "the key, not the inputs, is what the scorer treats as truth",
     "test_ground_truth.TruthSourceTests.test_key_is_truth_not_inputs"),
    ("H11", "audit reports divergence on a corrupt key, none on the shipped key",
     "test_key_audit.KeyAuditTests.test_corrupted_key_reports_divergence_naming_the_finding"),
    ("H12", "key-audit not invoked by any scoring path",
     "test_key_audit.KeyAuditTests.test_audit_not_imported_by_any_scoring_module"),
    ("H13", "every generator rule appears in the published policy",
     "test_ground_truth.PolicyTests.test_matching_policy_publishes_every_rule"),
    ("H14", "generation emits doc+index from one record with parse-back",
     "MANUAL: generation-side (D36); the generator renders each PDF, reads it back and "
     "asserts it matches the index — run during the build, parse-back passed."),
    ("H15", "editing one input byte changes the aggregate inputs digest",
     "test_dataset_loading.DatasetLoadingTests.test_inputs_digest_changes_when_one_byte_edited"),
    ("H16", "a digest mismatch reports which files diverged",
     "test_dataset_loading.DatasetLoadingTests.test_per_file_digest_locates_the_changed_file"),
    ("H17", "aggregate inputs digest identical on Windows and Linux",
     "MANUAL: cross-platform ([P2] scope); the algorithm normalizes paths to forward "
     "slashes over raw bytes and .gitattributes disables line-ending conversion, so it is "
     "platform-independent by construction; determinism is asserted by "
     "test_dataset_loading.DatasetLoadingTests.test_inputs_digest_stable_on_recompute."),
    ("H18", "zero-defect empty artifact: FP 0, rate 0, precision null",
     "test_scoring_engine.ScoringTests.test_zero_defect_empty_artifact_precision_and_recall_null"),
    ("H19", "tax overcharge scores as document-scoped TP; line-scoped does not match",
     "test_scoring_engine.ScoringTests.test_line_and_document_findings_do_not_match_each_other"),
    ("H20", "goods-receipt under-shipment scores as a true positive",
     "test_key_and_arithmetic.KeyContentTests.test_all_five_categories_present_with_correct_scope"),
    ("H21", "goods-receipt over-shipment scores as a true positive",
     "test_key_and_arithmetic.KeyContentTests.test_all_five_categories_present_with_correct_scope"),
    ("H22", "run_metadata holds only run stamp and three durations",
     "test_scorecard_repro.ScorecardTests.test_run_metadata_holds_only_timestamp_and_three_durations"),
    ("H23", "counts in the scored body; altering either changes the bytes",
     "test_scorecard_repro.ScorecardTests.test_counts_in_scored_body_and_alter_changes_bytes"),
    ("H24", "three quantity categories each score; short shipment billed right = no finding",
     "test_key_and_arithmetic.KeyContentTests.test_short_shipment_billed_correctly_has_no_finding"),
    ("H25a", "cent-aligned boundary: $10.00 flags, $9.99 does not",
     "test_key_and_arithmetic.KeyContentTests.test_cent_aligned_boundary_flag_and_no_flag"),
    ("H25b", "non-aligned boundary: $6.67 flags, $6.66 does not",
     "test_key_and_arithmetic.KeyContentTests.test_nonaligned_boundary_flag_and_no_flag"),
    ("H26", "display rounding never alters a flagging decision",
     "test_ground_truth.RoundingTests.test_no_quantize_in_a_flagging_decision"),
    ("H27", "$26 variance on a $100,000 line flags (the $25 cap governs)",
     "test_key_and_arithmetic.KeyContentTests.test_hundred_thousand_line_twenty_six_dollar_variance_flags"),
    ("H28", "both-wrong line yields one price and one quantity finding",
     "test_key_and_arithmetic.KeyContentTests.test_both_wrong_line_yields_price_and_quantity"),
    ("H29", "one-unit overbill below materiality: no finding; above: finding",
     "test_key_and_arithmetic.KeyContentTests.test_cheap_one_unit_overbill_below_materiality_no_finding"),
    ("H30", "inputs and key in different locations load from the manifest",
     "test_dataset_loading.DatasetLoadingTests.test_manifest_names_three_artifacts_separately"),
    ("H31", "TAX_VARIANCE document-scoped, single finding, not per-line",
     "test_key_and_arithmetic.KeyContentTests.test_all_five_categories_present_with_correct_scope"),
    ("H32", "document-scoped finding with absent line id is malformed",
     "test_port_schema.SchemaTests.test_document_scope_absent_line_id_is_malformed"),
    ("H33", "line-scoped and document-scoped findings do not match each other",
     "test_scoring_engine.ScoringTests.test_line_and_document_findings_do_not_match_each_other"),
    ("H34", "two-percent term uses the payable extended amount",
     "test_ground_truth.PayableBasisTests.test_two_percent_uses_payable_extended_not_ordered"),
    ("H35", "tax assessed against the invoice's taxable subtotal",
     "test_key_and_arithmetic.KeyContentTests.test_price_error_on_taxable_line_yields_no_tax_finding"),
    ("H36", "correspondence in the key, absent from the inputs",
     "test_ground_truth.TruthSourceTests.test_correspondence_in_key_absent_from_inputs"),
    ("H37", "reordering invoice lines changes no id and no finding",
     "test_dataset_loading.DatasetLoadingTests.test_reordering_invoice_index_lines_changes_no_target"),
    ("H38", "zero-defect precision null (empty) vs 0.0 (spurious flags)",
     "test_scoring_engine.ScoringTests.test_zero_defect_with_flags_precision_zero_recall_null"),
    ("H39", "zero-defect recall null in both cases",
     "test_scoring_engine.ScoringTests.test_zero_defect_empty_artifact_precision_and_recall_null"),
    ("H40", "every undefined metric emitted as null, never zero or omitted",
     "test_scorecard_repro.ScorecardTests.test_undefined_metrics_emitted_as_null_never_zero_or_omitted"),
    ("H41", "price error on a taxable line yields one PRICE_VARIANCE, no TAX_VARIANCE",
     "test_key_and_arithmetic.KeyContentTests.test_price_error_on_taxable_line_yields_no_tax_finding"),
    ("H42", "duplicate contention counted distinctly; byte-identical on swap",
     "test_scoring_engine.ScoringTests.test_contention_one_tp_one_fp_and_order_reversal_identical"),
    ("H43", "display rounding is ROUND_HALF_UP, not banker's",
     "test_ground_truth.RoundingTests.test_ratio_rounds_half_up_not_banker"),
    ("H44", "non-terminating tax rate: same verdict under two precisions",
     "test_key_and_arithmetic.ShippedTaxRuleTests.test_nonterminating_rate_same_verdict_under_two_precisions"),
    ("H45", "tax on a zero taxable subtotal flags at >= $0.05",
     "test_key_and_arithmetic.ShippedTaxRuleTests.test_zero_taxable_flags_at_five_cents"),
    ("H46", "fully exempt PO with correct zero tax: no finding",
     "test_key_and_arithmetic.ShippedTaxRuleTests.test_exempt_with_zero_tax_is_clean"),
    ("H47", "zero taxable subtotal does not annihilate the invoiced tax",
     "test_key_and_arithmetic.ShippedTaxRuleTests.test_zero_taxable_does_not_annihilate_invoiced_tax"),
    ("H48", "PO with zero taxable subtotal and non-zero tax rejected, named",
     "test_dataset_loading.DatasetLoadingTests.test_zero_taxable_subtotal_with_nonzero_tax_rejected"),
    ("H49", "PO/invoice with absent tax field rejected",
     "test_dataset_loading.DatasetLoadingTests.test_absent_tax_field_rejected"),
    ("H50", "received quantity summed across receipts; single-receipt key differs",
     "test_ground_truth.ReceiptSummingTests.test_received_quantity_is_summed_and_single_receipt_would_differ"),
    ("H51", "goods receipts are separate documents, not co-located in the PO",
     "test_ground_truth.TruthSourceTests.test_goods_receipts_are_separate_documents_not_in_po"),
    ("H52", "dev has exempt PO + $500 + $333.33; $100k only synthetic",
     "test_key_and_arithmetic.KeyContentTests.test_hundred_thousand_only_in_synthetic"),
    ("H53", "synthetic fixture labelled, loads through the same loader",
     "test_key_and_arithmetic.KeyContentTests.test_synthetic_labelled_and_loads_through_same_loader"),
    ("H54", "no division reachable from a flagging decision",
     "test_constraints_scan.ConstraintScanTests.test_no_division_inside_a_flagging_decision"),
    ("H55", "reported ratios at declared places; byte-identical across precisions",
     "test_scorecard_repro.ScorecardTests.test_cross_precision_byte_identical"),
    ("H56", "every run_metadata field non-deterministic (excluding it -> identical)",
     "test_scorecard_repro.ScorecardTests.test_excluding_run_metadata_makes_two_runs_byte_identical"),
    ("H57", "summary names each miss and each false flag individually",
     "test_scorecard_repro.ScorecardTests.test_summary_names_each_miss_and_false_flag"),
    # --- edge cases ---
    ("E1", "omitting one finding reduces that category's recall by 1/count",
     "test_scoring_engine.ScoringTests.test_omitting_one_finding_reduces_recall_by_one_over_count"),
    ("E2", "adding one spurious finding lowers precision",
     "test_scoring_engine.ScoringTests.test_spurious_finding_is_false_positive_and_lowers_precision"),
    ("E3", "two contending findings: one TP one FP, reverse identical",
     "test_scoring_engine.ScoringTests.test_contention_one_tp_one_fp_and_order_reversal_identical"),
    ("E4", "wrong TargetLine is both a false negative and a false positive",
     "test_scoring_engine.ScoringTests.test_wrong_targetline_is_both_false_negative_and_false_positive"),
    ("E5", "non-existent target is a false positive labelled distinctly",
     "test_scoring_engine.ScoringTests.test_nonexistent_target_is_false_positive_labelled"),
    ("E6", "MATCH status is not a false positive",
     "test_scoring_engine.ScoringTests.test_match_status_is_not_a_false_positive"),
    ("E7", "malformed findings artifact halts, names finding+field, no scorecard",
     "test_cli_end_to_end.CliEndToEndTests.test_malformed_findings_halts_nonzero_and_writes_nothing"),
    ("E8", "category outside the enumeration halts as a schema violation",
     "test_port_schema.SchemaTests.test_category_outside_enum_halts_as_schema_violation"),
    ("E9", "missing/unreadable dataset halts, names it, no partial score",
     "test_dataset_loading.DatasetLoadingTests.test_missing_dataset_halts_naming_it"),
    ("E10", "unreadable answer key halts rather than passing",
     "test_dataset_loading.DatasetLoadingTests.test_unreadable_answer_key_halts"),
    ("E11", "timestamp lacking Z/second precision rejected as malformed",
     "test_dataset_loading.DatasetLoadingTests.test_timestamp_without_z_is_rejected"),
    # --- constraint validation ---
    ("C1", "same inputs scored twice: byte-identical apart from run_metadata",
     "test_cli_end_to_end.CliEndToEndTests.test_two_runs_byte_identical_apart_from_run_metadata"),
    ("C2", "pyright reports zero errors",
     "MANUAL: type gate run separately as `npx pyright` (dev tool, not a runtime import)."),
    ("C3", "scoring engine imports only the standard library",
     "test_constraints_scan.ConstraintScanTests.test_scoring_engine_imports_only_standard_library"),
    ("C4", "no float on any monetary code path",
     "test_constraints_scan.ConstraintScanTests.test_no_float_on_any_monetary_path"),
    ("C5", "no networking or model-client import in the scoring path",
     "test_constraints_scan.ConstraintScanTests.test_no_network_or_model_or_pdf_import_anywhere"),
    ("C6", "guard-configuration + placement checks (canary reframed by D30)",
     "test_isolation.IsolationTests.test_guard_configuration_passes_on_shipped_settings"),
    ("C7", "guard-config fails naming an uncovered secret path",
     "test_isolation.IsolationTests.test_guard_configuration_fails_naming_uncovered_secret_path"),
    ("C8", "placement fails when a secret artifact is planted (incl. ignored dirs)",
     "test_isolation.IsolationTests.test_placement_fails_when_secret_artifact_planted"),
    ("C9", "no shipped check tests enforcement by code; attestation dated + method",
     "test_isolation.IsolationTests.test_attestation_record_exists_with_date_and_method"),
    ("C10", "repository contains no held-out artifact at any path",
     "test_isolation.IsolationTests.test_repository_contains_no_heldout_artifact"),
    ("C11", "agent can read held-out inputs but not the key (both halves, config)",
     "test_isolation.IsolationTests.test_guard_configuration_rejects_covering_holdout_inputs"),
    ("C12", "the full suite passes on the dev split alone, no out-of-tree path",
     "test_ground_truth.SuiteHygieneTests.test_no_test_loads_data_from_an_out_of_tree_path"),
    ("C13", "zero occurrences of the forbidden terminology in the work",
     "test_constraints_scan.ConstraintScanTests.test_forbidden_strings_absent_from_the_authored_work"),
    ("C14", "no input or key file modified by a run (hashes before/after)",
     "test_cli_end_to_end.CliEndToEndTests.test_run_does_not_modify_any_input_file"),
    # Repository composition. Added after a near-miss: every check above reads the
    # filesystem, where a file excluded from git is still plainly present, so an
    # ignore rule could silently drop the public dev keys while the whole suite
    # stayed green. These assert over the git index and ignore rules instead.
    ("C15", "the dev split ships complete in git - inputs and key both tracked",
     "test_repo_shipping.RepositoryShippingTests.test_the_dev_split_ships_complete"),
    ("C16", "no ignore rule excludes a file that must ship",
     "test_repo_shipping.RepositoryShippingTests.test_no_shipping_file_is_excluded_by_an_ignore_rule"),
    ("C17", "no secret artifact is tracked in the git index",
     "test_repo_shipping.RepositoryShippingTests.test_no_secret_artifact_is_tracked"),
    ("C18", "the shipping check provably fires on the historical bad pattern",
     "test_repo_shipping.RepositoryShippingTests.test_the_check_actually_fires_on_a_known_bad_pattern"),
]


class TraceabilityTests(unittest.TestCase):
    def test_every_criterion_has_coverage(self) -> None:
        for cid, desc, coverage in CRITERIA:
            self.assertTrue(coverage, f"{cid} ({desc}) has no coverage")

    def test_every_named_test_resolves(self) -> None:
        unresolved: list[str] = []
        for cid, _desc, coverage in CRITERIA:
            if coverage.startswith("MANUAL:"):
                continue
            module_name, cls_name, method_name = coverage.split(".")
            try:
                module = importlib.import_module(f"tests.{module_name}")
                cls = getattr(module, cls_name)
                getattr(cls, method_name)
            except (ImportError, AttributeError):
                unresolved.append(f"{cid}: {coverage}")
        self.assertEqual(unresolved, [], f"criteria bound to missing tests: {unresolved}")

    def test_coverage_summary(self) -> None:
        automated = [c for c in CRITERIA if not c[2].startswith("MANUAL:")]
        manual = [c for c in CRITERIA if c[2].startswith("MANUAL:")]
        # A visible summary; also guards against an empty map.
        self.assertGreaterEqual(len(automated), 60)
        self.assertLessEqual(len(manual), 5)


if __name__ == "__main__":
    unittest.main()
