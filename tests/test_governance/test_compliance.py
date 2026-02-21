"""Tests for the compliance mapping matrix."""

from mdxcode.governance.compliance import COMPLIANCE_MATRIX, get_compliance_matrix


EXPECTED_FRAMEWORKS = {"SOC2", "EU_AI_Act", "OSFI_B13", "OCC_2011_12"}
EXPECTED_FEATURES = {
    "audit_trail",
    "adversarial_review",
    "policy_enforcement",
    "human_approval",
    "cost_tracking",
    "model_provenance",
}


class TestComplianceMatrix:
    """Tests for compliance matrix completeness."""

    def test_all_frameworks_present(self):
        matrix = get_compliance_matrix()
        assert set(matrix.keys()) == EXPECTED_FRAMEWORKS

    def test_all_features_present_in_each_framework(self):
        matrix = get_compliance_matrix()
        for framework, features in matrix.items():
            assert set(features.keys()) == EXPECTED_FEATURES, (
                f"Framework {framework} missing features: "
                f"{EXPECTED_FEATURES - set(features.keys())}"
            )

    def test_all_values_are_nonempty_strings(self):
        matrix = get_compliance_matrix()
        for framework, features in matrix.items():
            for feature, description in features.items():
                assert isinstance(description, str), (
                    f"{framework}.{feature} should be a string"
                )
                assert len(description) > 0, (
                    f"{framework}.{feature} should not be empty"
                )

    def test_returns_same_reference(self):
        """get_compliance_matrix() returns the module-level constant."""
        assert get_compliance_matrix() is COMPLIANCE_MATRIX
