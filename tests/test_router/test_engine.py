"""Tests for task categorization engine."""

import pytest

from mdxcode.router.engine import TaskCategory, categorize_task


class TestCategorizeTask:
    """Test keyword-based task categorization."""

    # --- code_generation ---

    def test_create_feature(self):
        result = categorize_task("Create a new user preferences page")
        assert result.category == "code_generation"

    def test_build_component(self):
        result = categorize_task("Build a React component for the dashboard")
        assert result.category == "code_generation"

    def test_implement_feature(self):
        result = categorize_task("Implement OAuth2 login flow")
        assert result.category == "code_generation"

    def test_add_endpoint(self):
        result = categorize_task("Add endpoint for user profile updates")
        assert result.category == "code_generation"

    def test_generate_scaffold(self):
        result = categorize_task("Generate a REST API scaffold")
        assert result.category == "code_generation"

    # --- test_writing ---

    def test_write_tests(self):
        result = categorize_task("Write tests for the auth module")
        assert result.category == "test_writing"

    def test_add_test_coverage(self):
        result = categorize_task("Add test coverage for payment processing")
        assert result.category == "test_writing"

    def test_unit_test(self):
        result = categorize_task("Write unit test for the UserService class")
        assert result.category == "test_writing"

    def test_pytest_spec(self):
        result = categorize_task("Create pytest spec for validation logic")
        assert result.category == "test_writing"

    def test_integration_tests(self):
        result = categorize_task("Add integration tests for the API")
        assert result.category == "test_writing"

    # --- code_review ---

    def test_review_code(self):
        result = categorize_task("Review src/ for code quality issues")
        assert result.category == "code_review"

    def test_audit_code(self):
        result = categorize_task("Audit the authentication module")
        assert result.category == "code_review"

    def test_check_code(self):
        result = categorize_task("Check the database layer for issues")
        assert result.category == "code_review"

    # --- debugging ---

    def test_fix_bug(self):
        result = categorize_task("Fix the login timeout bug")
        assert result.category == "debugging"

    def test_error_message(self):
        result = categorize_task("The API returns error on POST /users, it's broken")
        assert result.category == "debugging"

    def test_broken_feature(self):
        result = categorize_task("The search feature is broken after the update")
        assert result.category == "debugging"

    def test_failing_test(self):
        # "failing" is a debugging keyword, but "test" is test_writing
        # debugging should win because "failing" + "error" are strong debugging signals
        result = categorize_task("Fix the failing test that throws an error")
        assert result.category == "debugging"

    # --- refactoring ---

    def test_refactor_module(self):
        result = categorize_task("Refactor the payment module")
        assert result.category == "refactoring"

    def test_clean_up(self):
        result = categorize_task("Clean up the legacy API handlers")
        assert result.category == "refactoring"

    def test_optimize_performance(self):
        result = categorize_task("Optimize the database query performance")
        assert result.category == "refactoring"

    def test_simplify_code(self):
        result = categorize_task("Simplify the request handling logic")
        assert result.category == "refactoring"

    # --- documentation ---

    def test_add_docs(self):
        result = categorize_task("Add documentation for the API")
        assert result.category == "documentation"

    def test_write_readme(self):
        result = categorize_task("Write a README for the project")
        assert result.category == "documentation"

    def test_add_docstrings(self):
        result = categorize_task("Add docstrings to all public methods")
        assert result.category == "documentation"

    # --- security ---

    def test_security_scan(self):
        result = categorize_task("Scan for SQL injection vulnerabilities")
        assert result.category == "security"

    def test_owasp_check(self):
        result = categorize_task("Check for OWASP top 10 vulnerabilities")
        assert result.category == "security"

    def test_xss_vulnerability(self):
        result = categorize_task("Find XSS vulnerabilities in the frontend")
        assert result.category == "security"

    def test_security_audit(self):
        result = categorize_task("Perform a security audit on the codebase")
        assert result.category == "security"

    # --- general (fallback) ---

    def test_vague_request(self):
        result = categorize_task("Help me with this code")
        assert result.category == "general"

    def test_empty_string(self):
        result = categorize_task("")
        assert result.category == "general"

    def test_random_text(self):
        result = categorize_task("The quick brown fox jumps over the lazy dog")
        assert result.category == "general"

    # --- confidence ---

    def test_high_confidence_multiple_keywords(self):
        result = categorize_task("Write unit tests and add test coverage for assertions")
        assert result.category == "test_writing"
        assert result.confidence > 0.5

    def test_general_has_moderate_confidence(self):
        result = categorize_task("Do something with the app")
        assert result.category == "general"
        assert result.confidence == 0.5

    def test_confidence_in_range(self):
        """All confidence scores should be between 0 and 1."""
        tasks = [
            "Fix the bug", "Write tests", "Review code",
            "Create a feature", "Refactor module", "Add docs",
            "Security scan", "Help me",
        ]
        for task in tasks:
            result = categorize_task(task)
            assert 0.0 <= result.confidence <= 1.0, f"Task '{task}': {result.confidence}"

    # --- edge cases ---

    def test_case_insensitive(self):
        result = categorize_task("REFACTOR THE DATABASE LAYER")
        assert result.category == "refactoring"

    def test_mixed_signals_strongest_wins(self):
        """When keywords from multiple categories appear, the strongest match wins."""
        result = categorize_task("Fix the security vulnerability in authentication")
        # "security" + "vulnerability" + "authentication" are all security keywords
        assert result.category == "security"
