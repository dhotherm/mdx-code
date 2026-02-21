"""Compliance mapping matrix for MDx Code governance."""

# Maps regulatory frameworks to MDx Code features that satisfy them.
# Each framework maps feature names to descriptions of how MDx satisfies the requirement.
COMPLIANCE_MATRIX: dict[str, dict[str, str]] = {
    "SOC2": {
        "audit_trail": "Immutable, chain-hashed audit log of all AI actions (CC6.1, CC7.2)",
        "adversarial_review": "Multi-model code review catches issues single-model misses (CC8.1)",
        "policy_enforcement": "Configurable policies enforce review requirements (CC6.1)",
        "human_approval": "Human-in-the-loop approval for critical changes (CC6.1)",
        "cost_tracking": "Full cost attribution and spending controls (CC6.1)",
        "model_provenance": "Every action records which AI model was used (CC7.2)",
    },
    "EU_AI_Act": {
        "audit_trail": "Article 12 — Transparency and record-keeping",
        "adversarial_review": "Article 9 — Risk management via multi-model validation",
        "policy_enforcement": "Article 9 — Automated risk controls",
        "human_approval": "Article 14 — Human oversight for high-risk AI",
        "cost_tracking": "Article 13 — Transparency of AI system operation",
        "model_provenance": "Article 12 — Logging of AI system actions",
    },
    "OSFI_B13": {
        "audit_trail": "E-21 — Technology risk management audit requirements",
        "adversarial_review": "E-21 — Independent validation of AI outputs",
        "policy_enforcement": "B-13 — Model risk management controls",
        "human_approval": "B-13 — Human judgment in model decisions",
        "cost_tracking": "E-21 — Technology spending oversight",
        "model_provenance": "B-13 — Model inventory and documentation",
    },
    "OCC_2011_12": {
        "audit_trail": "SR 11-7 — Model audit trail requirements",
        "adversarial_review": "SR 11-7 — Effective challenge via independent review",
        "policy_enforcement": "SR 11-7 — Model risk governance framework",
        "human_approval": "SR 11-7 — Human judgment in model risk management",
        "cost_tracking": "SR 11-7 — Resource allocation tracking",
        "model_provenance": "SR 11-7 — Model inventory and lineage tracking",
    },
}


def get_compliance_matrix() -> dict[str, dict[str, str]]:
    """Return the full compliance mapping matrix."""
    return COMPLIANCE_MATRIX
