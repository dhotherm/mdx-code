"""Governance MCP server — policy checking via MCP protocol."""

from pathlib import Path
from typing import Optional

from mcp.server.fastmcp import FastMCP

from mdxcode.governance.policy_engine import (
    PolicyFile,
    PolicyResult,
    evaluate_policies,
    load_policy_file,
)

mcp = FastMCP("mdx-governance")


@mcp.tool()
def check_policy(files: list[str], policy_path: str = "") -> dict:
    """Check files against MDx governance policies.

    Evaluates a list of file paths against the active .mdxpolicy file.
    Returns whether review/approval is required and which policies matched.

    Args:
        files: List of file paths to check (e.g. ["src/auth/login.py"]).
        policy_path: Optional path to .mdxpolicy file. Defaults to auto-discovery.
    """
    try:
        path = Path(policy_path) if policy_path else None
        policy_file = load_policy_file(path)
        if policy_file is None:
            return {"error": "No .mdxpolicy file found. Run 'mdx policy init' to create one."}

        result = evaluate_policies(policy_file, files)
        return result.model_dump()
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def list_policies(policy_path: str = "") -> dict:
    """List all active governance policies and defaults.

    Returns the full policy configuration from the .mdxpolicy file,
    including all policy rules and default settings.

    Args:
        policy_path: Optional path to .mdxpolicy file. Defaults to auto-discovery.
    """
    try:
        path = Path(policy_path) if policy_path else None
        policy_file = load_policy_file(path)
        if policy_file is None:
            return {"error": "No .mdxpolicy file found. Run 'mdx policy init' to create one."}

        policies = []
        for p in policy_file.policies:
            policies.append({
                "name": p.name,
                "description": p.description,
                "paths": p.paths,
                "severity": p.severity,
                "requires": {
                    "adversarial_review": p.requires.adversarial_review,
                    "min_reviewers": p.requires.min_reviewers,
                    "human_approval": p.requires.human_approval,
                },
            })

        return {
            "version": policy_file.version,
            "policies": policies,
            "defaults": {
                "adversarial_review": policy_file.defaults.adversarial_review,
                "human_approval": policy_file.defaults.human_approval,
                "severity": policy_file.defaults.severity,
            },
        }
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def evaluate_commit(staged_files: list[str], policy_path: str = "") -> dict:
    """Evaluate staged files for commit readiness against policies.

    Checks if a set of staged files can be committed based on active
    governance policies. Returns commit decision with blocking policies.

    Args:
        staged_files: List of staged file paths to evaluate.
        policy_path: Optional path to .mdxpolicy file. Defaults to auto-discovery.
    """
    try:
        path = Path(policy_path) if policy_path else None
        policy_file = load_policy_file(path)
        if policy_file is None:
            return {
                "can_commit": True,
                "blocking_policies": [],
                "actions_required": [],
                "note": "No .mdxpolicy file found — no policies to enforce.",
            }

        result = evaluate_policies(policy_file, staged_files)

        actions_required = []
        if result.requires_review:
            actions_required.append("Run adversarial review: mdx review --staged")
        if result.requires_approval:
            actions_required.append("Obtain human approval before committing")
        if result.min_reviewers > 1:
            actions_required.append(f"Ensure at least {result.min_reviewers} reviewers")

        can_commit = not result.requires_review and not result.requires_approval

        return {
            "can_commit": can_commit,
            "blocking_policies": result.matching_policies,
            "actions_required": actions_required,
            "requires_review": result.requires_review,
            "requires_approval": result.requires_approval,
            "min_reviewers": result.min_reviewers,
        }
    except Exception as e:
        return {"error": str(e)}


def main():
    """Run the governance MCP server."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
