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
     "MANUAL: OBSERVED, no longer by-construction (D76). The `cross-platform` job in "
     ".github/workflows/ci.yml scores the dev split on ubuntu-latest and windows-latest at "
     "one pinned Python version and asserts both the scored body and the human summary are "
     "byte-identical; the inputs digest sits inside that body, so a platform difference in "
     "it fails the job. Runs on every push rather than once. Its CONFIGURATION is checked "
     "by test_ci_workflow.CiWorkflowTests.test_the_workflow_compares_scorecards_across_two_platforms; "
     "the result itself can only come from a run, which is why this stays MANUAL."),
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
    ("H58", "[P2] verify mode on an untouched scorecard reports no difference, exits zero",
     "test_verify_mode.VerifyModeTests.test_untouched_scorecard_verifies_identical_and_exits_zero"),
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
    ("E12", "[P2] verify detects altered stored numbers and exits non-zero",
     "test_verify_mode.VerifyModeTests.test_altered_numbers_are_detected_and_exit_nonzero"),
    ("E13", "[P2] an unrecognised scorecard schema version is its own outcome, not a "
            "scoring discrepancy (D66)",
     "test_verify_mode.VerifyModeTests.test_unrecognised_schema_version_is_its_own_outcome"),
    ("E14", "a file that is not valid UTF-8 halts naming the artifact and the byte, on "
            "every read path (D77)",
     "test_read_failures.NonUtf8ReadTests.test_every_dataset_artifact_names_itself_by_role"),
    ("E15", "an absent or wrong-typed findings schema_version is rejected naming the "
            "field, never assumed to be the current one (D78)",
     "test_port_schema.SchemaVersionDeclarationTests.test_an_absent_schema_version_is_rejected_not_assumed"),
    ("E16", "[P2] verify pointed at a different dataset says so in one line and compares "
            "nothing further (D79)",
     "test_verify_mode.VerifyModeTests.test_naming_a_different_dataset_says_so_in_one_line"),
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
    # Held-out tier durability and the three closed gaps (D71).
    ("C68", "both out-of-tree tiers are covered; a clean secret tier is not reported",
     "test_defect_classes.SecretTierDurabilityTests.test_both_out_of_tree_tiers_are_covered"),
    ("C69", "an allow list planted in the deny-only guard is rejected",
     "test_defect_classes.PatternAnchoringTests.test_an_unexpected_permission_list_is_rejected"),
    ("C70", "a document omitting its identifier is named, not misdiagnosed as a phantom reference",
     "test_cross_artifact_validation.DocumentIdentityTests.test_a_purchase_order_omitting_its_number_is_named_not_misdiagnosed"),
    ("C71", "an identifier disagreeing with its filename is rejected",
     "test_cross_artifact_validation.DocumentIdentityTests.test_an_identifier_disagreeing_with_its_filename_is_rejected"),
    ("C72", "[P2] deleting the JSONL ledger and rebuilding it from the scorecard directory "
            "reproduces identical contents",
     "test_run_ledger.RunLedgerTests.test_deleting_and_rebuilding_reproduces_identical_contents"),
    ("C73", "[P2] the CI workflow runs the pyright gate and the full test suite on push",
     "test_ci_workflow.CiWorkflowTests.test_the_workflow_runs_both_gates_on_push"),
    ("C74", "[P2] the same dataset and findings artifact yield identical scorecard content "
            "on Windows and on Linux, outside run_metadata",
     "MANUAL: a RESULT, and results live in runs. The `cross-platform` job in "
     ".github/workflows/ci.yml scores the dev split on both platforms at one pinned Python "
     "version and asserts the scored body and the human summary are byte-identical, on "
     "every push. Binding this to a test that merely reads the workflow would claim more "
     "than the test shows -- D30's rejected reachability probe in new clothes. The "
     "configuration IS checked, by "
     "test_ci_workflow.CiWorkflowTests.test_the_workflow_compares_scorecards_across_two_platforms."),
    ("C75", "[P2] the published README states only what isolation verifies, and never "
            "claims enforcement is verified by an automated probe",
     "test_published_claims.PublishedIsolationClaimTests.test_the_readme_states_only_what_isolation_verifies"),
    ("C76", "an ancestor whose settings do not cover the secret tier is reported, a covering "
            "one is not, and a guard-reach finding never changes the exit code",
     "test_isolation.GuardReachTests.test_an_ancestor_without_secret_coverage_is_reported"),
    ("C77", "no scorecard from a non-dev split is tracked: a held-out scorecard names "
            "expected findings verbatim and is answer-key content",
     "test_repo_shipping.RepositoryShippingTests.test_no_scorecard_from_a_non_dev_split_is_tracked"),
    # Published contract completeness (D96).
    ("C78", "every PO line on every split carries at least one goods receipt, and the policy says so",
     "test_claim_coverage.PublishedGuaranteeTests.test_every_purchase_order_line_has_at_least_one_receipt"),
    ("C79", "every invoice line corresponds one-to-one with a correspondence row, and the policy says so",
     "test_claim_coverage.PublishedGuaranteeTests.test_every_invoice_line_resolves_to_one_purchase_order_line"),
    ("C80", "each split's inputs directory resolves from its manifest and holds documents",
     "test_claim_coverage.PublishedGuaranteeTests.test_the_inputs_directory_resolves_on_every_split"),
    # The scorecard legend (D100).
    ("C81", "every field the scorecard emits is documented in the legend, and no documented "
            "field has stopped being emitted",
     "test_scorecard_legend.ScorecardLegendTests.test_every_emitted_field_is_documented"),
    ("C82", "the summary's TP/FP/FN/P/R and n/a abbreviations are all defined",
     "test_scorecard_legend.ScorecardLegendTests.test_the_summary_abbreviations_are_defined"),
    ("C83", "the legend states the misreading each subtle field invites, not just its name",
     "test_scorecard_legend.ScorecardLegendTests.test_the_subtle_distinctions_are_stated_not_merely_listed"),
    ("C84", "the legend is referenced from both entry documents",
     "test_scorecard_legend.ScorecardLegendTests.test_the_legend_is_referenced_from_the_entry_documents"),
    # Port tolerance and its boundary (D109).
    ("C86", "unknown fields at every level are accepted, and change nothing about what parsed",
     "test_port_tolerance.AdditiveToleranceTests.test_tolerance_does_not_alter_what_was_parsed"),
    ("C87", "an unrecognised enumeration value halts rather than being ignored",
     "test_port_tolerance.ToleranceStopsAtMeaningTests.test_an_unknown_status_halts"),
    # The published surface, bound by execution rather than by reading (D102-D108).
    ("C85", "[P2] every documented block of harness output is reproduced by running the "
            "harness and compared (D102)",
     "test_published_examples.PublishedExampleTests.test_every_registered_example_is_what_the_harness_prints"),
    # The scoring engine's input, swept for the first time since phase 1 (D113, D114).
    ("C88", "two expectations sharing a match key are rejected at load, so the key's "
            "record order cannot reach the scored body (D113)",
     "test_cross_artifact_validation.DuplicateExpectationTests.test_two_expectations_sharing_a_match_key_are_rejected"),
    ("C89", "losing the scorecard-filename race retries and never tracebacks (D114)",
     "test_cli_end_to_end.CliEndToEndTests.test_losing_the_filename_race_retries_instead_of_tracebacking"),
    # The key audit's own arithmetic, swept for the first time (D117).
    ("C90", "the cross-multiplied tax test refuses a negative taxable subtotal rather "
            "than inverting and flagging every invoice (D117)",
     "test_audit_score_parity.TaxDerivationPreconditionTests.test_a_negative_taxable_subtotal_is_refused_rather_than_inverted"),
    ("C91", "every line's `taxable` flag is a present boolean, on both the purchase-order "
            "and the invoice-index side (D117)",
     "test_audit_score_parity.TaxableFlagShippedStateTests.test_every_shipped_line_declares_a_boolean_taxable_flag"),
    # The scorecard-rendering sweep (D118).
    ("C92", "[P2] verify recomputes the human summary too, so a tampered `.txt` beside an "
            "intact scorecard is reported as its own outcome (D118)",
     "test_verify_mode.VerifyModeTests.test_a_tampered_human_summary_is_caught"),
    ("C93", "the per-category table's columns align on every row, at any dataset size",
     "test_scorecard_legend.SummaryAlignmentTests.test_columns_survive_multi_digit_counts"),
]


# Tests that support the suite without standing for an acceptance criterion of their
# own: positive controls, self-verifications of another guard, and internal invariants.
# Listing one here is a deliberate act, which is the point — see
# ``test_every_test_method_is_mapped_or_explicitly_exempt``.
EXEMPT_TESTS: frozenset[str] = frozenset({
    # Verify mode's internal invariants (D74). The three [P2] criteria it must satisfy are
    # mapped above as H58, E12 and E13. These four protect decisions the spec does not
    # state as criteria but which decide whether verify's report is trustworthy: the
    # OUTCOME PRECEDENCE, without which "you scored different data" is reported as "the
    # numbers are wrong" (D50); absence of a schema version treated as unrecognised rather
    # than as version zero; and the two halves of D74's honest account of what a
    # per-file diagnosis can say when the scorecard stores only an aggregate (D27).
    "test_verify_mode.VerifyModeTests.test_a_fingerprint_mismatch_outranks_a_body_difference",
    "test_verify_mode.VerifyModeTests.test_a_scorecard_declaring_no_schema_version_is_unrecognised_not_compared",
    "test_verify_mode.VerifyModeTests.test_without_a_baseline_the_per_file_limit_is_stated",
    "test_verify_mode.VerifyModeTests.test_a_baseline_names_the_divergent_file",
    "test_verify_mode.VerifyModeTests.test_an_unreadable_scorecard_is_an_error_not_a_failed_verification",
    # The ledger's internal invariants (D75). Its one [P2] criterion is mapped above as C72.
    # These protect what that guarantee rests on: the RUN ORDER, which is not the obvious
    # one because the D49 collision ordinal sorts lexicographically in a filename; the rule
    # that every field be recoverable from the directory, without which a rebuild cannot
    # reproduce anything; the append-failure policy, which is the one place besides D9's
    # performance breach where a warning coexists with exit zero; and refusing to guess a
    # run position for a file that is not a scorecard.
    "test_run_ledger.RunLedgerTests.test_run_order_survives_the_collision_ordinal",
    "test_run_ledger.RunLedgerTests.test_every_ledger_field_comes_from_the_scorecard",
    "test_run_ledger.RunLedgerTests.test_an_unwritable_ledger_warns_and_the_run_still_exits_zero",
    "test_run_ledger.RunLedgerTests.test_a_foreign_json_file_is_named_rather_than_silently_skipped",
    # D83: the reservation path skips what it cannot parse while the ledger still refuses
    # it. An internal invariant about which subsystem a failure may reach, not a criterion.
    "test_run_ledger.RunLedgerTests.test_a_neighbour_this_harness_did_not_emit_does_not_block_scoring",
    # The README's other published claims (D84). C75 maps the isolation claim, which is the
    # one D30 states as a requirement. These four bind the rest: the materiality numbers to
    # the shipped constants (D53's pattern, applied to prose rather than to a policy file);
    # the absence of an industry-norm claim (D16); that every command named is one that
    # exists (D59's rule, wider audience); and that each is given for both shells. The last
    # test is the flattener's own premise -- a phrase scan on a wrapped document
    # under-reports (D55), which is how the industry-norm disclaimer was written and
    # matched nothing.
    "test_published_claims.PublishedIsolationClaimTests.test_the_readme_threshold_matches_the_shipped_rule",
    "test_published_claims.PublishedIsolationClaimTests.test_the_readme_does_not_claim_the_thresholds_are_an_industry_norm",
    "test_published_claims.PublishedCommandTests.test_every_command_the_readme_names_is_one_that_exists",
    "test_published_claims.PublishedCommandTests.test_every_documented_command_is_given_for_both_shells",
    "test_published_claims.WrappedPhraseScanTests.test_a_wrapped_phrase_is_found_after_flattening_and_not_before",
    # --- the phase-completion sweep (D85-D89) ---------------------------------------
    # An advertised invocation is EXECUTED, not read (D85). C46 already carries D59's
    # criterion for a program name that must exist; these cover the invocation one layer
    # out -- the documents told a reader to run a command that failed on an uninstalled
    # checkout, and only running it could have shown that.
    "test_entry_points.AdvertisedInvocationTests.test_the_documented_module_invocation_runs",
    "test_entry_points.AdvertisedInvocationTests.test_the_bare_invocation_really_does_fail",
    "test_entry_points.AdvertisedInvocationTests.test_every_document_that_advertises_the_module_form_states_the_path",
    # E10 now tests the case it names -- a present but undecodable key (D86). Absence is a
    # different finding and keeps its own test rather than being lost with the rebinding.
    "test_dataset_loading.DatasetLoadingTests.test_absent_answer_key_halts",
    # The assert lock (D88). `python -O` strips asserts; D62 ruled on one site and left
    # seven. Same registry-plus-census shape as the numeric defaults it sits beside.
    "test_defect_classes.ShippedAssertTests.test_every_assert_in_shipped_code_is_justified",
    "test_defect_classes.ShippedAssertTests.test_no_justification_outlives_its_site",
    "test_defect_classes.ShippedAssertTests.test_every_justification_says_something",
    "test_defect_classes.ShippedAssertTests.test_every_shipped_assert_is_type_narrowing",
    "test_defect_classes.ShippedAssertTests.test_the_scan_finds_the_asserts_that_exist",
    # U4 observed under a randomised string hash rather than held by construction (D89).
    "test_scorecard_repro.HashSeedDeterminismTests.test_the_scored_body_is_identical_under_different_hash_seeds",
    # The build prompt is the third copy of the criteria list, now bound to it (D87).
    "test_traceability.TraceabilityTests.test_the_build_prompt_gate_lists_every_phase_two_criterion",
    # Whether this repository's deny rules are the ones a session loaded (D91). Advisory
    # by construction -- where an editor is opened is not a property of the repository --
    # so it answers to no criterion, but it is the finding that explains why a canary read
    # succeeded when the dated attestation says it was refused.
    "test_isolation.GuardReachTests.test_an_ancestor_that_does_cover_the_secret_tier_is_not_reported",
    # D93: the premise for the held-out-scorecard check -- it must classify a held-out
    # filename as a leak and a dev one as fine, or it is a scan nobody has shown to look.
    "test_repo_shipping.RepositoryShippingTests.test_the_scorecard_check_would_catch_a_held_out_card",
    # D94: a leading byte-order mark is accepted, and a clean file is unaffected. Widening
    # what the reader TOLERATES, not what the harness treats as the same input -- the second
    # test scores end to end, because the reader in isolation is not the path a user takes.
    "test_read_failures.OneReaderTests.test_a_leading_byte_order_mark_is_accepted",
    "test_read_failures.OneReaderTests.test_a_bom_artifact_scores_end_to_end",
    # D95: a fenced block's language tag is invisible once the page is rendered, so every
    # shell block carries a visible label saying which shell it is for. This project gives
    # every command twice, once per shell, which makes that the one thing a reader of the
    # published page cannot afford to guess.
    "test_published_claims.ShellLabelTests.test_every_shell_block_carries_a_visible_label",
    "test_published_claims.ShellLabelTests.test_the_scan_would_notice_an_unlabelled_block",
    "test_isolation.GuardReachTests.test_a_reach_warning_never_changes_the_exit_code",
    # D80. Every one of these protects C72 — "delete the ledger, rebuild it, get the same
    # file" — against a condition its own test could not reach. C72 scores ONE split, so
    # its ordinals never tie; the tie needed two identifiers in one second, and it made
    # the rebuild order filesystem-dependent, so the guarantee would have failed on Linux
    # and held on the machine it was written on. The rest are the boundary the ordering
    # rests on: a residual tie halts, a null in a load-bearing field is refused, a null
    # in a metric that D40 defines as nullable is carried, and a mistyped directory is
    # named rather than answered with an empty ledger.
    "test_run_ledger.RunLedgerTests.test_three_splits_in_one_second_keep_their_run_order",
    "test_run_ledger.RunLedgerTests.test_a_hand_placed_duplicate_run_position_halts",
    "test_run_ledger.RunLedgerTests.test_a_null_run_timestamp_is_rejected_not_carried",
    "test_run_ledger.RunLedgerTests.test_a_null_ratio_is_carried_through",
    "test_run_ledger.RunLedgerTests.test_a_missing_scorecard_directory_is_named_not_answered_with_nothing",
    # The workflow's configuration checks (D76). C73 maps the "both gates run" criterion
    # here; these two check claims the workflow makes that no criterion states -- that the
    # cross-platform comparison names TWO platforms rather than silently comparing a run to
    # itself, and that the skip count is asserted rather than eyeballed.
    "test_ci_workflow.CiWorkflowTests.test_the_workflow_compares_scorecards_across_two_platforms",
    "test_ci_workflow.CiWorkflowTests.test_the_suite_skip_count_is_asserted_rather_than_eyeballed",
    # The two claims the workflow made that nothing held it to (D81): that the number of
    # tests which ran is checked against something real rather than a typed-in floor, and
    # that the line-ending step can actually fail. Both were configuration the workflow
    # described itself as having; neither was true.
    "test_ci_workflow.CiWorkflowTests.test_the_test_count_is_derived_rather_than_hand_maintained",
    "test_ci_workflow.CiWorkflowTests.test_the_line_ending_check_can_fail",
    # D79's two reporting invariants. E16 carries the dataset-identity criterion; these
    # protect the two properties a report has to have to be worth reading: that an
    # ABSENT field is reported as a defect in the scorecard rather than as a value it
    # disagrees about, and that no cause list is unbounded. Neither is a criterion the
    # spec states, and both decide whether verify's output is a diagnosis or a dump.
    "test_verify_mode.VerifyModeTests.test_an_absent_fingerprint_is_a_shape_defect_not_a_mismatch",
    "test_verify_mode.VerifyModeTests.test_a_baseline_diagnosis_is_bounded",
    # D78's other two halves. E15 carries the criterion on an ABSENT declaration; these
    # are the same rule on a wrong-typed one, on both sides of the project. The verify
    # entry is deliberately not a second criterion: E13 already says an unrecognised
    # schema version is its own outcome, and a scorecard whose version field is not even
    # a string is unrecognised. What it adds is the reason E13 was silently violated —
    # a `str()` at the gate that made the check pass and then let the raw value surface
    # below as a scoring difference.
    "test_verify_mode.VerifyModeTests.test_a_wrong_typed_schema_version_is_unrecognised_not_a_scoring_difference",
    "test_port_schema.SchemaVersionDeclarationTests.test_a_wrong_typed_schema_version_names_the_type",
    "test_port_schema.SchemaVersionDeclarationTests.test_an_unsupported_version_is_still_reported_as_unsupported",
    # The shared reader's other read paths and its lock (D77). E14 carries the criterion
    # on the dataset-side artifacts; these are the same statement on the two runtime
    # artifacts, the three-causes-apart distinction, and — the one that matters — the AST
    # lock that stops a sixth reader arriving with its own subset of guards. Asserting
    # today's call sites is a snapshot; asserting that only one function reads text is
    # what makes the class stay closed (D68's shape, applied to a read).
    "test_read_failures.NonUtf8ReadTests.test_a_non_utf8_findings_artifact_halts_naming_it",
    "test_read_failures.NonUtf8ReadTests.test_a_non_utf8_scorecard_halts_rather_than_failing_verification",
    "test_read_failures.NonUtf8ReadTests.test_the_three_read_failures_are_reported_apart",
    "test_read_failures.OneReaderTests.test_only_the_shared_reader_reads_text",
    "test_read_failures.OneReaderTests.test_the_scan_would_notice_a_stray_read",
    "test_read_failures.OneReaderTests.test_the_findings_artifact_has_one_loader",
    "test_read_failures.WriteDestinationTests.test_a_ledger_destination_that_cannot_be_written_is_named",
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
    "test_traceability.TraceabilityTests.test_spec_p2_criterion_count_is_unchanged",
    # The numbering guards check this file's own list, so they answer to no criterion.
    "test_traceability.CriteriaNumberingTests.test_no_criterion_id_is_used_twice",
    "test_traceability.CriteriaNumberingTests.test_the_numeric_ids_are_contiguous",
    "test_traceability.CriteriaNumberingTests.test_the_happy_path_and_edge_ids_are_also_unique",
    # Converses and premises for the D67/D68 locks; each names the criterion it supports.
    "test_claim_coverage.ClaimDiscoveryTests.test_registry_has_no_stale_entries",
    "test_claim_coverage.PublishedGuaranteeTests.test_the_policy_publishes_both_guarantees",
    # Premise and converse for the legend checks.
    "test_scorecard_legend.ScorecardLegendTests.test_the_fixture_exercises_both_element_shapes",
    "test_scorecard_legend.ScorecardLegendTests.test_the_legend_documents_no_field_that_is_not_emitted",
    # The remaining tolerance cases; C86/C87 name one of each direction.
    "test_port_tolerance.AdditiveToleranceTests.test_an_unknown_field_on_a_finding_is_accepted",
    "test_port_tolerance.AdditiveToleranceTests.test_an_unknown_field_inside_target_is_accepted",
    "test_port_tolerance.AdditiveToleranceTests.test_an_unknown_top_level_key_is_accepted",
    "test_port_tolerance.ToleranceStopsAtMeaningTests.test_an_unknown_category_halts",
    "test_port_tolerance.ToleranceStopsAtMeaningTests.test_an_unknown_scope_halts",
    "test_port_tolerance.ToleranceStopsAtMeaningTests.test_an_unsupported_schema_version_halts",
    "test_port_tolerance.ToleranceStopsAtMeaningTests.test_a_missing_required_field_still_halts",
    "test_claim_coverage.ClaimDiscoveryTests.test_every_registered_check_resolves",
    "test_claim_coverage.ClaimDiscoveryTests.test_partial_coverage_states_a_reason",
    "test_claim_coverage.ClaimSymmetryTests.test_every_claim_is_checked_on_every_known_split",
    "test_defect_classes.NumericDefaultTests.test_no_justification_outlives_its_site",
    "test_defect_classes.NumericDefaultTests.test_every_justification_says_something",
    # D82's two additions to the same lock: a default belonging to no named bucket fails
    # rather than being skipped, and the buckets are asserted to partition a non-trivial
    # total so the scan cannot go quiet. C63 carries the criterion; these keep its
    # universe honest, which is the half that was missing.
    "test_defect_classes.NumericDefaultTests.test_no_default_escapes_classification",
    "test_defect_classes.NumericDefaultTests.test_the_classification_covers_every_site_and_the_buckets_are_populated",
    # The third direction of the traceability map (D82): an exemption naming a test that
    # no longer exists is a claim about nothing.
    "test_traceability.TraceabilityTests.test_no_exemption_outlives_its_test",
    # The published-surface sweep (D102-D108). C85 carries D102's criterion; everything
    # here is a mechanism whose rule the project had already stated and whose universe was
    # narrower than that rule — so none of them is a new promise, which is why none gets a
    # criterion of its own.
    #
    # D102's other three: the completeness half (an output-shaped block bound to no run),
    # the registry's own premise, and the proof that a deleted row is caught — which is the
    # direction the legend actually drifted.
    "test_published_examples.PublishedExampleTests.test_every_output_shaped_block_is_registered",
    "test_published_examples.PublishedExampleTests.test_the_registry_is_not_empty_and_every_document_is_read",
    "test_published_examples.PublishedExampleTests.test_a_doctored_example_is_caught",
    # D103: the advisory says what it observed, and the document consuming it does not
    # conclude more than the advisory can support. Bound together because the failure was
    # the pair, not either half.
    "test_isolation.GuardReachTests.test_the_advisory_states_a_condition_rather_than_judging_this_session",
    "test_isolation.GuardReachTests.test_the_attestation_does_not_gate_on_the_advisory",
    # D104: the contamination axis of D93's rule, plus the positive control that a
    # legitimate dev scorecard is left alone.
    "test_isolation.IsolationTests.test_placement_fails_on_an_untracked_held_out_scorecard",
    "test_isolation.IsolationTests.test_placement_leaves_dev_scorecards_alone",
    # D105: the document registry asserted covered in both directions, and the automation
    # claim with the fact it rests on.
    "test_published_claims.DocumentRegistryTests.test_every_markdown_document_is_classified",
    "test_published_claims.DocumentRegistryTests.test_no_classified_document_has_gone_missing",
    "test_published_claims.AutomationClaimTests.test_no_published_document_claims_a_commit_hook",
    "test_published_claims.AutomationClaimTests.test_the_repository_really_has_no_commit_hook_running_these",
    # D106: prose restating a status, bound to the status.
    "test_traceability.TraceabilityTests.test_no_document_says_a_built_artifact_is_unbuilt",
    "test_traceability.TraceabilityTests.test_the_build_prompt_states_the_gate_size_it_actually_has",
    # D107: the boundary between the tolerant read and the intolerant hash, in both
    # directions, because tolerating a BOM on a source digest and tolerating one on a
    # dataset fingerprint are opposite requirements.
    "test_generator_staleness.GeneratorFreshnessTests.test_a_byte_order_mark_does_not_move_the_digest",
    "test_generator_staleness.GeneratorFreshnessTests.test_a_byte_order_mark_does_move_a_dataset_artifact_fingerprint",
    # D108: the sweep marker's own trigger, which was prose for eighteen decisions.
    "test_traceability.TraceabilityTests.test_the_sweep_marker_has_not_fallen_behind_its_own_trigger",
    # D109's guarantee, published where its audience reads it. C86 and C87 carry the
    # behaviour; these carry the *publication* of it — the D53 move, which is a different
    # claim from the behaviour being correct and failed separately for the thresholds once.
    "test_published_claims.PublishedPortGuaranteeTests.test_the_readme_publishes_the_additive_tolerance_guarantee",
    "test_published_claims.PublishedPortGuaranteeTests.test_the_published_guarantee_matches_the_shipped_parser",
    # The `[P3]` criterion checksum, which had no counterpart while `[P1]` and `[P2]` did.
    "test_traceability.TraceabilityTests.test_spec_p3_criterion_count_is_unchanged",
    # The scoring-input sweep (D113–D116). C88 and C89 carry the two criteria; these are
    # the controls and the converses around them.
    #
    # D113: the shipped keys are already clean, which is what makes this a lock at zero
    # (D68) rather than a repair — and two DIFFERENT categories on one line stay legal,
    # because H28 requires exactly that and a check forbidding it would break the dev split.
    "test_cross_artifact_validation.DuplicateExpectationTests.test_the_shipped_keys_declare_no_duplicate_expectation",
    "test_cross_artifact_validation.DuplicateExpectationTests.test_distinct_expectations_on_the_same_line_are_still_allowed",
    # D114: the retry terminates. A bounded retry that never gives up is a hang wearing a
    # fix's clothes, so exhausting it is a named halt.
    "test_cli_end_to_end.CliEndToEndTests.test_exhausting_the_retries_is_a_named_halt",
    # D115: the publishable splits are discovered, so a new split needs no code edit —
    # which is the property a literal could not have.
    "test_isolation.IsolationTests.test_a_newly_added_split_is_publishable_without_editing_code",
    # D116: the project's other stamped marker, which D108's mechanism did not reach.
    "test_traceability.TraceabilityTests.test_the_negative_space_section_is_stamped_current",
    # D118's controls. C92 and C93 carry the criteria; these are the boundaries around
    # them: a correct pair must still read `identical` AND say the summary was compared
    # (otherwise "checked and matched" is indistinguishable from "not checked"); an absent
    # `.txt` is not a difference, since the JSON is the durable record and keeping only it
    # is legitimate; today's shipped data must align too, not just the `[P3]`-scale
    # fixture; and the document-scope branch is chosen by enum identity, not by a string.
    "test_verify_mode.VerifyModeTests.test_an_untouched_pair_still_verifies_identical",
    "test_verify_mode.VerifyModeTests.test_an_absent_summary_is_not_a_failure",
    "test_scorecard_legend.SummaryAlignmentTests.test_columns_align_across_every_row_of_a_real_run",
    "test_scorecard_legend.SummaryAlignmentTests.test_a_document_scoped_miss_is_labelled_by_enum_not_by_string",
    # D117's controls. C90 and C91 carry the criteria; these are the surrounding cases —
    # a zero-variance invoice must not flag (which is what the inversion broke), a material
    # variance must still flag (so the guard cannot be met by never flagging), and D28's
    # zero-subtotal boundary must be untouched by the new negative guard.
    "test_audit_score_parity.TaxDerivationPreconditionTests.test_a_zero_variance_invoice_does_not_flag",
    "test_audit_score_parity.TaxDerivationPreconditionTests.test_a_material_variance_still_flags",
    "test_audit_score_parity.TaxDerivationPreconditionTests.test_the_zero_subtotal_case_is_untouched",
    # D112: the same binding as D102's, applied to what the harness prints when something
    # goes WRONG. C85 carries the criterion for published output as a whole; these three
    # are its failure-message half — the registered message provoked and compared, the
    # completeness scan over the declared scope, and the premise that a rewording is
    # caught. Verified by mutation against the shipped message, not only on a fixture.
    "test_published_examples.PublishedFailureMessageTests.test_every_quoted_failure_message_is_what_the_code_emits",
    "test_published_examples.PublishedFailureMessageTests.test_every_failure_shaped_block_is_registered",
    "test_published_examples.PublishedFailureMessageTests.test_a_reworded_message_is_caught",
    "test_defect_classes.PatternAnchoringTests.test_at_least_one_rule_list_was_examined",
    "test_defect_classes.PatternAnchoringTests.test_the_shipped_check_rejects_the_historical_bad_pattern",
    "test_defect_classes.SecretTierDurabilityTests.test_a_clean_tier_reports_nothing",
    "test_defect_classes.SecretTierDurabilityTests.test_an_untracked_file_is_reported",
    "test_defect_classes.SecretTierDurabilityTests.test_an_absent_tier_reports_nothing",
    "test_defect_classes.PatternAnchoringTests.test_the_shipped_guard_declares_only_the_expected_lists",
    "test_cross_artifact_validation.DocumentIdentityTests.test_a_goods_receipt_omitting_its_number_is_rejected",
    "test_cross_artifact_validation.DocumentIdentityTests.test_every_shipped_document_carries_a_matching_identifier",
})

# Checksum over the spec's [P1] acceptance criteria, in the tradition the 0.10.2 sweep
# established when a SHALL count caught nine silently duplicated requirements. The map
# below is a parallel list, so nothing otherwise notices a criterion added to the spec
# with no entry here. Raising this number is the deliberate act that forces the entry.
EXPECTED_SPEC_P1_CRITERIA = 137

# The same checksum for `[P2]`, added when phase 2 began producing criteria of its own.
# It was missing for the same reason D64a's gap existed and D69's after it: the rule
# ("a criterion cannot arrive uncovered") was right, and its enforcement reached only the
# phase the mechanism had been written during. A `[P2]` criterion could have been added
# to the spec with no map entry and nothing would have said so — which is precisely how
# D66's criterion went missing from the spec for two versions while its requirement sat
# in the `optional feature` block.
#
# All seven are mapped. The note that stood here — "not every entry is mapped yet, the
# ledger, CI-workflow and cross-platform criteria are mapped as their items land" —
# described a debt that was paid two commits later and then went on describing it, which
# is the same stale-restatement class the 0.22.0 sweep removed three instances of.
EXPECTED_SPEC_P2_CRITERIA = 10

# The same checksum for `[P3]`, which had none while its criteria went from two to seven.
#
# D74's reasoning for adding the `[P2]` checksum applies here word for word: *the rule was
# right and its enforcement reached only the phase the mechanism was written during.* That
# was the fourth instance of the shape when D74 wrote it; this is the same mechanism, one
# phase further on, and D110 had just made `[P3]` the phase carrying the most criteria
# nothing guarded — five of its seven arrived in a single change.
#
# `[P3]` is UNBUILT, so these criteria bind to no tests and nothing else would notice one
# being dropped. That is precisely why the count matters: a criterion deleted from an
# unbuilt phase leaves no failing test behind, so the checksum is the only thing standing
# between a design commitment and its quiet disappearance before anyone builds it.
#
# `[P4]` and `[P5]` deliberately have no checksum: they carry no criteria and no
# requirements, and D110 records that emptiness as a deferral with a trigger. A checksum of
# zero would assert the deferral is permanent.
EXPECTED_SPEC_P3_CRITERIA = 7


def _spec_criteria(tag: str) -> list[str]:
    """Every criterion carrying ``tag``, ticked or not (D82).

    The pattern was `^- \\[ \\] \\[{tag}\\]` — an unticked box, literally. So the moment
    anyone ticked one off, the count dropped and the guard failed with *"the spec now has
    5 [P2] criteria but this map expects 6 ... Add the missing entries"*, telling a reader
    that a criterion had been deleted when it had been satisfied. A checklist whose guard
    breaks when you use it as a checklist is a guard that misdiagnoses, which is the
    class this whole file exists to close."""
    spec = (Path(__file__).resolve().parents[1] / "specs" / "goldset-triad-harness.md").read_text(
        encoding="utf-8"
    )
    acceptance = spec.split("## acceptance criteria", 1)[1].split("\n---", 1)[0]
    return re.findall(rf"^- \[[ xX]\] \[{tag}\] (.+)$", acceptance, re.M)


def _spec_p1_criteria() -> list[str]:
    return _spec_criteria("P1")


def all_test_methods() -> set[str]:
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

    def test_spec_p2_criterion_count_is_unchanged(self) -> None:
        """The same guard for `[P2]`, which it did not previously reach (D74).

        The rule — a criterion cannot arrive uncovered — was correct and its enforcement
        stopped at the phase the mechanism was written during. That is the shape D64a,
        D69 and D73 each turned out to be, and it was not hypothetical here: D66's
        criterion was absent from the spec for two versions while its requirement sat in
        the `optional feature` block, and nothing in this file could have said so."""
        actual = len(_spec_criteria("P2"))
        self.assertEqual(
            actual, EXPECTED_SPEC_P2_CRITERIA,
            f"the spec now has {actual} [P2] acceptance criteria but this map expects "
            f"{EXPECTED_SPEC_P2_CRITERIA}. Add the missing entries to CRITERIA and raise "
            f"EXPECTED_SPEC_P2_CRITERIA, so a new criterion cannot arrive uncovered.",
        )

    def test_the_build_prompt_gate_lists_every_phase_two_criterion(self) -> None:
        """The THIRD copy of the criteria list, bound at last (D87).

        `EXPECTED_SPEC_P2_CRITERIA` binds the spec to this map. Nothing bound either to the
        build prompt — which opens its gate with the words *"Every `[P2]` criterion in the
        spec"* and, when this was written, enumerated six of eight. It had silently fallen
        behind twice: once when the sweep added the dataset-mismatch criterion, once when
        the README criterion arrived.

        That document matters more than its obscurity suggests: it is what a fresh build
        session actually reads, and the 0.10.3 sweep found six of its eight defects there
        for exactly that reason. Counted rather than compared line by line, because the
        prompt legitimately paraphrases — what must not drift is how many gates there are."""
        prompt = (Path(__file__).resolve().parents[1] / "specs"
                  / "goldset-triad-harness.p2.build-prompt.md").read_text(encoding="utf-8")
        gate = prompt.split("## Phase-2 acceptance gate", 1)[1].split("\n## ", 1)[0]
        listed = len(re.findall(r"(?m)^- \[ \] ", gate))
        self.assertEqual(
            listed, EXPECTED_SPEC_P2_CRITERIA,
            f"the phase-2 build prompt's gate lists {listed} item(s) but the spec has "
            f"{EXPECTED_SPEC_P2_CRITERIA} [P2] criteria. Its gate says 'Every [P2] "
            f"criterion in the spec', so a builder working from it would stop short.",
        )

    def test_every_test_method_is_mapped_or_explicitly_exempt(self) -> None:
        """test -> map. The map was one-directional: it caught a criterion with no test,
        never a test with no criterion, so five cross-artifact tests sat unmapped (D54)."""
        mapped = {c[2] for c in CRITERIA if not c[2].startswith("MANUAL:")}
        unaccounted = sorted(all_test_methods() - mapped - EXEMPT_TESTS)
        self.assertEqual(
            unaccounted, [],
            f"{len(unaccounted)} test(s) are neither mapped to a criterion nor exempt: "
            f"{unaccounted}. Map each to the criterion it verifies, or add it to "
            f"EXEMPT_TESTS with a reason.",
        )

    def test_the_sweep_marker_has_not_fallen_behind_its_own_trigger(self) -> None:
        """The marker is a mechanism now, not a note (D108).

        The spec's sweep marker states its own trigger — *"~8–10 decisions since the stamp
        above"* — and ends *"Update this line whenever a sweep completes, or it stops
        meaning anything."* Nothing checked it. Eleven decisions had accrued past the stamp
        when this was written, which is the marker's own overdue condition, silently.

        That is D67's thesis turned on the project's own process: a rule recorded as prose
        is enforced by whoever remembers it. The trigger is deliberately change-based rather
        than calendar-based, and a change-based trigger is exactly the kind a machine can
        evaluate — there was never a reason for this one to be manual.

        The ceiling is the *upper* end of the stated range, so a sweep coming due reads as
        a reminder rather than a failure, and only overshooting it fails."""
        root = Path(__file__).resolve().parents[1]
        spec = (root / "specs" / "goldset-triad-harness.md").read_text(encoding="utf-8")
        decisions = (root / "DECISIONS.md").read_text(encoding="utf-8")

        stamped = re.search(r"\*\*Last swept:[^@]*@[^@]*@\s*D(\d+)\*\*", spec)
        self.assertIsNotNone(
            stamped, "the spec's sweep marker no longer states the decision it was taken at"
        )
        assert stamped is not None  # for the type checker; the assertion above is the gate
        swept_at = int(stamped.group(1))

        numbers = sorted(int(n) for n in re.findall(r"(?m)^## D(\d+)", decisions))
        self.assertTrue(numbers, "no decisions found; this check would pass vacuously")
        latest = numbers[-1]
        accrued = len([n for n in numbers if n > swept_at])

        self.assertLessEqual(
            accrued, 10,
            f"{accrued} decisions (D{swept_at + 1}–D{latest}) have accrued since the last "
            f"sweep at D{swept_at}, past the 8–10 trigger the marker states. Run a sweep "
            f"and update the marker, or the marker stops meaning anything — which is what "
            f"it says about itself (D108).",
        )

    def test_the_negative_space_section_is_stamped_current(self) -> None:
        """The project's *other* stamped marker, which D108's check could not see (D116).

        D108 mechanised the spec's sweep marker and stopped there. `DECISIONS.md` carries a
        second one — `## Not checked — as of <version> @ D<n>` — whose whole purpose is to
        tell the next reader how current the gap list is, and it drifted four decisions
        behind while the mechanism written to stop exactly this drift looked elsewhere.
        D108's universe was *the marker I was fixing*; the rule was *stamped markers go
        stale*.

        The tolerance is the same 10 the sweep trigger uses, and for the same reason: this
        list is the sweep's own output, so the two go stale together and a single threshold
        keeps them in step."""
        root = Path(__file__).resolve().parents[1]
        decisions = (root / "DECISIONS.md").read_text(encoding="utf-8")

        stamped = re.search(r"^## Not checked — as of \S+ @ D(\d+)", decisions, re.M)
        self.assertIsNotNone(
            stamped,
            "DECISIONS.md's negative-space section no longer carries a `as of <version> @ "
            "D<n>` stamp, so nothing says how current its gap list is",
        )
        assert stamped is not None  # for the type checker; the assertion above is the gate
        stamped_at = int(stamped.group(1))

        numbers = sorted(int(n) for n in re.findall(r"(?m)^## D(\d+)", decisions))
        self.assertTrue(numbers, "no decisions found; this check would pass vacuously")
        accrued = len([n for n in numbers if n > stamped_at])
        self.assertLessEqual(
            accrued, 10,
            f"the negative-space list is stamped at D{stamped_at} and {accrued} decisions "
            f"(D{stamped_at + 1}–D{numbers[-1]}) have landed since. A gap list that is not "
            f"current is worse than none: the next reader takes it as the state of things "
            f"(D111). Add this pass's entry and restamp the heading (D116).",
        )

    def test_no_document_says_a_built_artifact_is_unbuilt(self) -> None:
        """Prose *about* the criteria, bound at last (D106).

        D87 bound the build prompt's gate to the criterion count and its check counts
        checkboxes. The same file's summary block went on saying *"4 of 5 — not built: item
        4, the README"* after the README shipped, and *"all six items in the gate"* after
        D87 itself corrected that gate to eight, twelve lines below, in the same commit. A
        mechanism that reads a list does not see the sentence describing the list.

        Deliberately narrow: this checks the one class that has actually gone wrong — a
        document asserting an artifact does not exist while it does. Prose cannot be
        machine-checked in general, and pretending otherwise would be the overstatement
        this project keeps finding in its own checks."""
        deliverables = {
            "README and methodology write-up": Path(__file__).resolve().parents[1] / "README.md",
        }
        documents = [
            Path(__file__).resolve().parents[1] / name
            for name in ("specs/goldset-triad-harness.p2.build-prompt.md",
                         "specs/goldset-triad-harness.md")
        ]
        contradictions: list[str] = []
        for name, artifact in deliverables.items():
            if not artifact.is_file():
                continue
            for document in documents:
                flat = re.sub(r"\s+", " ", document.read_text(encoding="utf-8"))
                for match in re.finditer(rf"[Nn]ot built:[^.]*{re.escape(name)}", flat):
                    contradictions.append(
                        f"{document.name}: {flat[match.start():match.end()][:90]!r} "
                        f"— but {artifact.name} exists"
                    )
        self.assertEqual(
            contradictions, [],
            f"{len(contradictions)} document(s) say a deliverable is unbuilt while its "
            f"artifact is on disk: {contradictions}. Update the prose, not just the list "
            f"beside it (D106).",
        )

    def test_the_build_prompt_states_the_gate_size_it_actually_has(self) -> None:
        """The second half of the same drift: a sentence counting the gate.

        `all six items in the phase-2 acceptance gate` outlived the gate becoming eight.
        Any spelled-out or numeric count the prompt gives for its own gate must match the
        checkboxes it contains — the count is derived from the file, never restated."""
        prompt_path = (Path(__file__).resolve().parents[1] / "specs"
                       / "goldset-triad-harness.p2.build-prompt.md")
        prompt = prompt_path.read_text(encoding="utf-8")
        gate = prompt.split("## Phase-2 acceptance gate", 1)[1].split("\n## ", 1)[0]
        actual = len(re.findall(r"(?m)^- \[ \] ", gate))
        words = {"two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
                 "eight": 8, "nine": 9, "ten": 10}
        flat = re.sub(r"\s+", " ", prompt)
        wrong: list[str] = []
        for match in re.finditer(
            r"\b(\d+|two|three|four|five|six|seven|eight|nine|ten)\b\s+items?\s+in\s+the\s+"
            r"phase-2 acceptance gate", flat, re.I,
        ):
            token = match.group(1).lower()
            stated = int(token) if token.isdigit() else words[token]
            if stated != actual:
                wrong.append(f"{match.group(0)!r} but the gate lists {actual}")
        self.assertEqual(
            wrong, [],
            f"the build prompt miscounts its own gate: {wrong}. Say 'every item' rather "
            f"than a number, or keep the number derived (D106).",
        )

    def test_spec_p3_criterion_count_is_unchanged(self) -> None:
        """The same guard for `[P3]`, which did not have one (D74's shape, one phase on).

        `[P3]` is the next phase and is unbuilt, so its criteria bind to no tests: dropping
        one breaks nothing and shows up nowhere. D110 found its phase block had accumulated
        four design commitments that appeared in no requirement, and fixing that took its
        criteria from two to seven — the largest body of criteria in the spec with nothing
        counting them."""
        actual = len(_spec_criteria("P3"))
        self.assertEqual(
            actual, EXPECTED_SPEC_P3_CRITERIA,
            f"the spec now has {actual} [P3] acceptance criteria but this map expects "
            f"{EXPECTED_SPEC_P3_CRITERIA}. Raise EXPECTED_SPEC_P3_CRITERIA deliberately "
            f"when adding one, so a criterion for an unbuilt phase cannot vanish without "
            f"a failing test — there is no covering test to miss it.",
        )

    def test_no_exemption_outlives_its_test(self) -> None:
        """map -> tests, the third direction (D82).

        `EXEMPT_TESTS` is a parallel list with no staleness check, so deleting or renaming
        a test left its exemption behind forever — and an exemption for a test that does
        not exist is a claim about nothing, which is exactly what
        `test_registry_has_no_stale_entries` exists to prevent for the claims registry one
        file away. The two lists are the same shape; only one of them was guarded."""
        stale = sorted(EXEMPT_TESTS - all_test_methods())
        self.assertEqual(
            stale, [],
            f"{len(stale)} exemption(s) name a test that no longer exists: {stale}. Each "
            f"was a deliberate statement that some test answers to no criterion; with the "
            f"test gone the statement is about nothing. Remove them.",
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
        # Raised 5 -> 6 by D76, deliberately and with a reason, because a ceiling nudged
        # upward whenever it binds is not a ceiling. The sixth is C74, cross-platform
        # byte-identity: it is a RESULT produced by running on two operating systems, which
        # a single-platform unit suite cannot produce however it is written. Every other
        # MANUAL entry is generation-side (H6, H14), environment-level (C2) or the same
        # cross-platform observation (H17). None of the six is a criterion that *could*
        # have been automated here and was not.
        self.assertLessEqual(len(manual), 6)


if __name__ == "__main__":
    unittest.main()
