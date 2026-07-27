"""Traceability — every [P1] acceptance criterion is bound to a covering test.

An untested eval harness is self-refuting, so the acceptance gate is machine-
checked rather than hand-ticked: each criterion below names either a concrete test
(``module.Class.method``, asserted to exist) or a documented ``MANUAL:``
verification for the few criteria that are generation-side or environment-level
and cannot run inside the in-repo dev-split suite by construction.
"""

from __future__ import annotations

import importlib
import inspect
import re
import unittest
from pathlib import Path

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
    # Sweep fixes (D49-D54). Every entry below answers a criterion added in spec 0.12.0.
    ("C19", "same-second runs each leave their own scorecard",
     "test_cli_end_to_end.CliEndToEndTests.test_same_second_runs_do_not_overwrite_each_other"),
    ("C20", "overwriting a scorecard is refused by the OS, not merely avoided",
     "test_cli_end_to_end.CliEndToEndTests.test_writing_over_an_existing_scorecard_is_refused_by_the_os"),
    ("C21", "both scorecard files are written with pinned LF endings",
     "test_cli_end_to_end.CliEndToEndTests.test_scorecard_files_are_written_with_lf_endings"),
    ("C22", "an expected finding naming an unknown line is rejected at load",
     "test_cross_artifact_validation.ExpectedFindingTargetTests.test_expected_finding_with_unknown_line_is_rejected"),
    ("C23", "an expected finding naming an unknown document is rejected",
     "test_cross_artifact_validation.ExpectedFindingTargetTests.test_expected_finding_with_unknown_document_is_rejected"),
    ("C24", "a phantom purchase order is named, not misdiagnosed as a rate difference",
     "test_cross_artifact_validation.CorrespondenceReferenceTests.test_phantom_purchase_order_is_named_not_misdiagnosed"),
    ("C25", "a phantom purchase-order line is rejected",
     "test_cross_artifact_validation.CorrespondenceReferenceTests.test_phantom_purchase_order_line_is_rejected"),
    ("C26", "an orphan correspondence row is rejected",
     "test_cross_artifact_validation.CorrespondenceReferenceTests.test_orphan_correspondence_row_is_rejected"),
    ("C27", "a correspondence row missing a required field is rejected",
     "test_cross_artifact_validation.CorrespondenceReferenceTests.test_correspondence_row_missing_a_field_is_rejected"),
    ("C28", "an empty correspondence list is rejected, not exempted",
     "test_cross_artifact_validation.CorrespondenceCompletenessTests.test_empty_correspondence_is_not_an_exemption"),
    ("C29", "a missing correspondence entry is rejected naming the line",
     "test_cross_artifact_validation.CorrespondenceCompletenessTests.test_missing_correspondence_entry_is_rejected"),
    ("C30", "differing tax rates across POs on one invoice are rejected",
     "test_cross_artifact_validation.MultiPoTaxRateTests.test_differing_rates_across_pos_is_rejected"),
    ("C31", "an unresolved reference in the audit names its cause, not a key error",
     "test_key_audit.KeyAuditTests.test_unresolved_reference_names_its_cause_not_a_keyerror"),
    ("C32", "the published policy states the thresholds the shipped code applies",
     "test_ground_truth.PolicyTests.test_policy_numbers_match_the_shipping_rule_implementation"),
    ("C33", "shipped keys target only real lines (positive control on D50)",
     "test_cross_artifact_validation.ExpectedFindingTargetTests.test_shipped_keys_target_only_real_lines"),
    ("C34", "a malformed finding names both the finding and the field",
     "test_port_schema.SchemaTests.test_malformed_finding_names_finding_and_field"),
    ("C35", "reported ratios emit at the declared precision",
     "test_scorecard_repro.ScorecardTests.test_ratios_emitted_at_declared_places"),
    # Formalizing the behaviours that lived only in code (D55-D57).
    ("C36", "MATCH cannot satisfy an expectation either, only leave it a miss",
     "test_scoring_engine.ScoringTests.test_match_cannot_satisfy_an_expectation_either"),
    ("C37", "surplus flags on an unexpected key are not duplicate contention",
     "test_scoring_engine.ScoringTests.test_surplus_flags_on_an_unexpected_key_are_not_duplicate_contention"),
    ("C38", "one invoice line mapped twice is rejected",
     "test_cross_artifact_validation.CorrespondenceReferenceTests.test_one_invoice_line_mapped_twice_is_rejected"),
    ("C39", "an exact duplicate correspondence row is rejected",
     "test_cross_artifact_validation.CorrespondenceReferenceTests.test_duplicated_identical_row_is_rejected"),
    ("C40", "the dev split exercises all five categories and both boundary directions",
     "test_key_and_arithmetic.KeyContentTests.test_dataset_coverage_invariants_hold"),
    ("C41", "the zero-defect control declares no expectations but keeps correspondence",
     "test_key_and_arithmetic.KeyContentTests.test_zero_defect_control_declares_no_expectations"),
    # Generator staleness (D58). The generator is out of tree, so nothing here could
    # otherwise notice that a rule changed and the data was never regenerated.
    ("C42", "every shipped dataset's manifest records the generator source that emitted it",
     "test_generator_staleness.GeneratorStampTests.test_every_shipped_dataset_records_its_generator"),
    ("C43", "all splits share one generator stamp, so a partial regeneration is detected",
     "test_generator_staleness.GeneratorStampTests.test_all_datasets_share_one_stamp"),
    ("C44", "the stamp matches the current generator, and skips when it is unreachable",
     "test_generator_staleness.GeneratorFreshnessTests.test_stamp_matches_the_current_generator"),
    ("C45", "the digest provably moves on a source edit and not on bytecode",
     "test_generator_staleness.GeneratorFreshnessTests.test_digest_notices_a_source_change"),
    # Command-line surface (D59).
    ("C46", "every module with a main is declared, resolves, and advertises a real name",
     "test_entry_points.EntryPointTests.test_every_advertised_program_name_is_a_real_command"),
    ("C47", "no checkout found reports that nothing was checked, not an isolation failure",
     "test_isolation.RepoRootResolutionTests.test_no_checkout_anywhere_is_an_error_not_an_isolation_failure"),
    # Coverage disclosure (D60).
    ("C48", "a partially exercised dataset names the categories it cannot measure",
     "test_coverage_reporting.CoverageBlockTests.test_a_partially_exercised_dataset_names_what_it_cannot_measure"),
    ("C49", "the zero-defect control states it measures over-flagging only",
     "test_coverage_reporting.CoverageBlockTests.test_the_zero_defect_control_says_it_measures_no_recall"),
    ("C50", "coverage sits in the scored body; undefined metrics read as n/a while JSON emits null",
     "test_coverage_reporting.CoverageBlockTests.test_coverage_is_in_the_scored_body_not_run_metadata"),
    # Portability and shared validity (D61, D62).
    ("C51", "no text I/O relies on the platform default encoding",
     "test_coverage_reporting.TextIoIsExplicitTests.test_no_call_relies_on_the_platform_default_encoding"),
    ("C52", "every malformation the loader rejects, the audit rejects by name",
     "test_audit_score_parity.ValidityParityTests.test_everything_score_refuses_the_audit_also_refuses_by_name"),
    ("C53", "sharing the loader has not made the audit defer to the key",
     "test_audit_score_parity.ValidityParityTests.test_audit_still_derives_independently"),
    # D63-D66, renumbered from C46-C49: two sessions appended to this list concurrently and
    # both reached for the next four ids, so C46-C49 each named two different criteria. The
    # duplicate-numbering rule was already generalized to "any numbered set" -- but its
    # enforcement reached decision numbers, phase tags and markdown ordered lists, and never
    # these ids, which live in a Python list. CriteriaNumberingTests below closes that.
    ("C54", "the scorecard declares its schema version (needed by [P2] verify)",
     "test_scorecard_repro.ScorecardTests.test_scorecard_declares_its_schema_version"),
    ("C55", "an unanchored generator deny rule is rejected as over-broad",
     "test_isolation.IsolationTests.test_unanchored_generator_rule_is_rejected_as_over_broad"),
    ("C56", "the held-out stamp agrees with the dev splits and the current generator",
     "test_generator_staleness.HeldOutStalenessTests.test_held_out_stamp_agrees_with_the_dev_splits"),
    ("C57", "the stamped guard still matches its source-of-truth template",
     "test_isolation.GuardTemplateDriftTests.test_stamped_guard_matches_the_template"),
    # Claim coverage and defect-class locks (D67, D68).
    ("C58", "an unregistered claim-shaped field fails; a stale registry entry fails too",
     "test_claim_coverage.ClaimDiscoveryTests.test_every_claim_shaped_field_on_disk_is_registered"),
    ("C59", "the split enumeration includes held-out whenever the secret tier is present",
     "test_claim_coverage.ClaimSymmetryTests.test_the_held_out_split_is_in_the_universe_when_present"),
    ("C60", "each key's declared version and identifier match its manifest's, on every split",
     "test_claim_coverage.ClaimSymmetryTests.test_key_version_matches_its_manifest"),
    ("C61", "the published policy is compared to the shipped rule on every known split",
     "test_ground_truth.PolicyTests.test_policy_numbers_match_the_shipping_rule_implementation"),
    ("C62", "no timing wait exists anywhere, and a new one fails",
     "test_defect_classes.NoTimingWaitTests.test_no_timing_wait_anywhere"),
    ("C63", "every numeric absence-default in shipped code carries a justification",
     "test_defect_classes.NumericDefaultTests.test_every_numeric_default_in_shipped_code_is_justified"),
    ("C64", "no rule in any permission list is anchored on a bare stem",
     "test_defect_classes.PatternAnchoringTests.test_no_rule_in_any_list_is_anchored_on_a_bare_stem"),
    ("C65", "reference resolution is asserted to precede the rate check",
     "test_defect_classes.OrderDependencyTests.test_reference_resolution_precedes_the_rate_check"),
    # Secret-tier durability (D70).
    ("C66", "an uncommitted secret tier is reported, and a clean or absent one is not",
     "test_defect_classes.SecretTierDurabilityTests.test_an_uncommitted_change_is_reported"),
    ("C67", "a durability finding never changes the isolation exit code",
     "test_defect_classes.SecretTierDurabilityTests.test_a_durability_warning_never_fails_the_check"),
]


# Tests that support the suite without standing for an acceptance criterion of their
# own: positive controls, self-verifications of another guard, and internal invariants.
# Listing one here is a deliberate act, which is the point — see
# ``test_every_test_method_is_mapped_or_explicitly_exempt``.
EXEMPT_TESTS: frozenset[str] = frozenset({
    # Positive controls: the converse of a criterion, proving a guard does not over-fire.
    "test_cross_artifact_validation.MultiPoTaxRateTests.test_equal_rates_across_pos_is_allowed",
    "test_cross_artifact_validation.MultiPoTaxRateTests.test_shipped_datasets_have_no_multi_po_invoice",
    "test_cross_artifact_validation.CorrespondenceCompletenessTests.test_every_shipped_dataset_is_complete",
    "test_cross_artifact_validation.CorrespondenceReferenceTests.test_shipped_datasets_map_each_line_exactly_once",
    "test_isolation.IsolationTests.test_placement_passes_on_clean_tree",
    "test_key_audit.KeyAuditTests.test_shipped_dev_key_is_consistent",
    "test_dataset_loading.DatasetLoadingTests.test_inputs_digest_stable_on_recompute",
    "test_dataset_loading.DatasetLoadingTests.test_no_input_file_modified_by_a_load",
    "test_dataset_loading.DatasetLoadingTests.test_resolves_by_identifier_and_by_path",
    "test_key_and_arithmetic.KeyContentTests.test_exempt_po_correct_zero_tax_has_no_finding",
    "test_key_and_arithmetic.KeyContentTests.test_dev_has_exempt_po_and_the_two_boundary_bases_plausibly",
    "test_key_and_arithmetic.ShippedTaxRuleTests.test_threshold_shape",
    "test_port_schema.SchemaTests.test_empty_findings_artifact_is_valid",
    "test_port_schema.SchemaTests.test_valid_match_status_parses_and_is_carried",
    "test_port_schema.SchemaTests.test_confidence_must_be_number_in_unit_interval",
    "test_port_schema.SchemaTests.test_document_scope_nonsentinel_line_id_is_malformed",
    "test_port_schema.SchemaTests.test_line_scope_using_sentinel_is_malformed",
    "test_scoring_engine.ScoringTests.test_zero_defect_empty_artifact_precision_and_recall_null",
    "test_cli_end_to_end.CliEndToEndTests.test_happy_path_emits_scorecard_and_exits_zero",
    "test_cli_end_to_end.CliEndToEndTests.test_missing_dataset_halts_nonzero",
    "test_ground_truth.SuiteHygieneTests.test_suite_data_root_is_in_repo",
    "test_ground_truth.TruthSourceTests.test_index_absent_from_agent_readable_inputs",
    "test_ground_truth.RoundingTests.test_ratio_rounds_half_up_not_banker",
    "test_isolation.IsolationTests.test_no_shipped_check_claims_to_test_enforcement_by_code",
    "test_constraints_scan.ConstraintScanTests.test_loader_reads_no_invoice_pdf",
    # Supporting halves of criteria mapped above: each is the second direction of a check
    # whose primary assertion carries the criterion (D64, D65).
    "test_generator_staleness.HeldOutStalenessTests.test_held_out_manifest_records_its_generator",
    "test_generator_staleness.HeldOutStalenessTests.test_held_out_stamp_matches_the_current_generator",
    "test_isolation.GuardTemplateDriftTests.test_rule_order_matches_too",
    "test_isolation.IsolationTests.test_shipped_rules_deny_the_generator_but_allow_innocent_words",
    # The other two directions of the D59 entry-point check, and the remaining branches
    # of root resolution. C46 and C47 each name one direction; these are the converses,
    # which is the same relationship the positive controls above have to their criteria.
    "test_entry_points.EntryPointTests.test_every_module_with_a_main_is_reachable_as_a_command",
    "test_entry_points.EntryPointTests.test_every_declared_command_resolves",
    "test_isolation.RepoRootResolutionTests.test_falls_back_to_the_current_directory_when_installed",
    "test_isolation.RepoRootResolutionTests.test_explicit_repo_root_wins",
    "test_isolation.RepoRootResolutionTests.test_a_nonexistent_repo_root_is_named",
    "test_isolation.RepoRootResolutionTests.test_settings_presence_does_not_decide_where_to_look",
    # Positive controls and converses for the D60 coverage block.
    "test_coverage_reporting.CoverageBlockTests.test_a_fully_exercised_dataset_reports_every_category",
    "test_coverage_reporting.CoverageBlockTests.test_expected_finding_count_matches_the_key",
    "test_coverage_reporting.UndefinedMetricDisplayTests.test_undefined_metrics_read_as_na_not_python_none",
    "test_coverage_reporting.UndefinedMetricDisplayTests.test_json_still_emits_null_not_the_display_string",
    "test_coverage_reporting.TextIoIsExplicitTests.test_the_scan_fires_on_a_bare_call",
    "test_audit_score_parity.ValidityParityTests.test_the_shipped_splits_pass_both_doors",
    # Guards that verify another guard rather than a criterion.
    "test_repo_shipping.RepositoryShippingTests.test_required_files_are_tracked_and_not_ignored",
    "test_repo_shipping.RepositoryShippingTests.test_the_secret_vocabulary_is_not_duplicated_here",
    "test_traceability.TraceabilityTests.test_every_criterion_has_coverage",
    "test_traceability.TraceabilityTests.test_every_named_test_resolves",
    "test_traceability.TraceabilityTests.test_coverage_summary",
    "test_traceability.TraceabilityTests.test_every_test_method_is_mapped_or_explicitly_exempt",
    "test_traceability.TraceabilityTests.test_spec_p1_criterion_count_is_unchanged",
    # The numbering guards check this file's own list, so they answer to no criterion.
    "test_traceability.CriteriaNumberingTests.test_no_criterion_id_is_used_twice",
    "test_traceability.CriteriaNumberingTests.test_the_numeric_ids_are_contiguous",
    "test_traceability.CriteriaNumberingTests.test_the_happy_path_and_edge_ids_are_also_unique",
    # Converses and premises for the D67/D68 locks; each names the criterion it supports.
    "test_claim_coverage.ClaimDiscoveryTests.test_registry_has_no_stale_entries",
    "test_claim_coverage.ClaimDiscoveryTests.test_every_registered_check_resolves",
    "test_claim_coverage.ClaimDiscoveryTests.test_partial_coverage_states_a_reason",
    "test_claim_coverage.ClaimSymmetryTests.test_every_claim_is_checked_on_every_known_split",
    "test_defect_classes.NumericDefaultTests.test_no_justification_outlives_its_site",
    "test_defect_classes.NumericDefaultTests.test_every_justification_says_something",
    "test_defect_classes.PatternAnchoringTests.test_at_least_one_rule_list_was_examined",
    "test_defect_classes.PatternAnchoringTests.test_the_shipped_check_rejects_the_historical_bad_pattern",
    "test_defect_classes.SecretTierDurabilityTests.test_a_clean_tier_reports_nothing",
    "test_defect_classes.SecretTierDurabilityTests.test_an_untracked_file_is_reported",
    "test_defect_classes.SecretTierDurabilityTests.test_an_absent_tier_reports_nothing",
})

# Checksum over the spec's [P1] acceptance criteria, in the tradition the 0.10.2 sweep
# established when a SHALL count caught nine silently duplicated requirements. The map
# below is a parallel list, so nothing otherwise notices a criterion added to the spec
# with no entry here. Raising this number is the deliberate act that forces the entry.
EXPECTED_SPEC_P1_CRITERIA = 119


def _spec_p1_criteria() -> list[str]:
    spec = (Path(__file__).resolve().parents[1] / "specs" / "goldset-triad-harness.md").read_text(
        encoding="utf-8"
    )
    acceptance = spec.split("## acceptance criteria", 1)[1].split("\n---", 1)[0]
    return re.findall(r"^- \[ \] \[P1\] (.+)$", acceptance, re.M)


def _all_test_methods() -> set[str]:
    found: set[str] = set()
    tests_dir = Path(__file__).resolve().parent
    for path in sorted(tests_dir.glob("test_*.py")):
        module = importlib.import_module(f"tests.{path.stem}")
        for name, obj in vars(module).items():
            if inspect.isclass(obj) and issubclass(obj, unittest.TestCase):
                for attr in dir(obj):
                    if attr.startswith("test_"):
                        found.add(f"{path.stem}.{name}.{attr}")
    return found


class CriteriaNumberingTests(unittest.TestCase):
    """These ids are a numbered set, and numbered sets must be unique and contiguous (D69).

    Found live: two sessions appended to CRITERIA concurrently, both took the next four ids,
    and C46-C49 each named two unrelated criteria. Every reference to them was ambiguous, and
    nothing noticed — the linter enforces this rule for decision numbers, phase tags and
    markdown ordered lists, and the generalization to "any numbered set" stopped at the edge of
    the file it could parse. A python list was outside its reach and therefore outside the rule
    in practice, though not in principle.

    The check lives here, with the list, for the reason the subject-index check lives with the
    index: the tool that owns a derivation owns its check. A second implementation in the linter
    would need to parse Python to find these, and would drift."""

    def _ids(self) -> list[str]:
        return [c[0] for c in CRITERIA]

    def test_no_criterion_id_is_used_twice(self) -> None:
        counts: dict[str, int] = {}
        for cid in self._ids():
            counts[cid] = counts.get(cid, 0) + 1
        dupes = sorted(f"{cid} (x{n})" for cid, n in counts.items() if n > 1)
        self.assertEqual(
            dupes, [],
            f"criterion id(s) used more than once: {dupes}. Every citation of them is "
            f"ambiguous. Renumber the later entries; never reuse an id (D69).",
        )

    def test_the_numeric_ids_are_contiguous(self) -> None:
        """A gap usually means an entry was deleted and its criterion silently dropped.

        Suffixed ids (C25a/C25b) are counted once, by their number, since a deliberate split of
        one criterion is not a gap."""
        numbers = sorted({
            int(m.group(1)) for cid in self._ids()
            if (m := re.match(r"^C(\d+)[a-z]?$", cid))
        })
        expected = list(range(numbers[0], numbers[-1] + 1))
        missing = sorted(set(expected) - set(numbers))
        self.assertEqual(
            missing, [],
            f"gap(s) in the criterion sequence: {[f'C{n}' for n in missing]} - an entry was "
            f"probably removed, taking its criterion with it",
        )

    def test_the_happy_path_and_edge_ids_are_also_unique(self) -> None:
        """The H and E series are numbered sets too, and were never checked either."""
        for prefix in ("H", "E"):
            with self.subTest(series=prefix):
                ids = [c for c in self._ids() if re.match(rf"^{prefix}\d", c)]
                counts: dict[str, int] = {}
                for cid in ids:
                    counts[cid] = counts.get(cid, 0) + 1
                self.assertEqual(
                    sorted(c for c, n in counts.items() if n > 1), [],
                    f"duplicate id(s) in the {prefix} series",
                )


class TraceabilityTests(unittest.TestCase):
    def test_every_criterion_has_coverage(self) -> None:
        for cid, desc, coverage in CRITERIA:
            self.assertTrue(coverage, f"{cid} ({desc}) has no coverage")

    def test_spec_p1_criterion_count_is_unchanged(self) -> None:
        """spec -> map. Without this the map can silently fall behind the spec (D54)."""
        actual = len(_spec_p1_criteria())
        self.assertEqual(
            actual, EXPECTED_SPEC_P1_CRITERIA,
            f"the spec now has {actual} [P1] acceptance criteria but this map expects "
            f"{EXPECTED_SPEC_P1_CRITERIA}. Add the missing entries to CRITERIA and raise "
            f"EXPECTED_SPEC_P1_CRITERIA, so a new criterion cannot arrive uncovered.",
        )

    def test_every_test_method_is_mapped_or_explicitly_exempt(self) -> None:
        """test -> map. The map was one-directional: it caught a criterion with no test,
        never a test with no criterion, so five cross-artifact tests sat unmapped (D54)."""
        mapped = {c[2] for c in CRITERIA if not c[2].startswith("MANUAL:")}
        unaccounted = sorted(_all_test_methods() - mapped - EXEMPT_TESTS)
        self.assertEqual(
            unaccounted, [],
            f"{len(unaccounted)} test(s) are neither mapped to a criterion nor exempt: "
            f"{unaccounted}. Map each to the criterion it verifies, or add it to "
            f"EXEMPT_TESTS with a reason.",
        )

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
