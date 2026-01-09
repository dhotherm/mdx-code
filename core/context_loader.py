"""
Context Loader - Reading MDXCODE.md

This is one of the most powerful ideas in MDx Code:
every project gets a context file that the AI reads before touching anything.

Think of MDXCODE.md as institutional knowledge that travels with the code.
It tells the AI:
- What this project is about
- What commands to run
- What conventions to follow
- What compliance rules apply
- What guardrails to respect

Different domains, different rules. Health has HIPAA. Wealth has IIROC.
The context file captures all of that.
"""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class MDXCodeContext:
    """
    Parsed context from MDXCODE.md.
    
    This gets injected into the system prompt so the AI
    understands your project before making any changes.
    """
    
    # Project basics
    project_name: Optional[str] = None
    domain: Optional[str] = None
    team: Optional[str] = None
    owner: Optional[str] = None
    
    # Regulatory
    regulatory_profile: Optional[str] = None
    
    # Content sections
    quick_commands: Optional[str] = None
    architecture: Optional[str] = None
    conventions: Optional[str] = None
    compliance: Optional[str] = None
    guardrails: Optional[str] = None
    known_issues: Optional[str] = None
    context_files: Optional[str] = None
    
    # Raw content for anything we didn't parse
    raw_content: Optional[str] = None


def load_mdxcode_context(path: Optional[Path] = None) -> Optional[MDXCodeContext]:
    """
    Load and parse MDXCODE.md from the current directory or specified path.
    
    Returns None if no MDXCODE.md found. That's fine - it's optional.
    But when it exists, it's powerful.
    """
    if path is None:
        path = Path.cwd() / "MDXCODE.md"
    
    if not path.exists():
        return None
    
    content = path.read_text()
    return parse_mdxcode(content)


def parse_mdxcode(content: str) -> MDXCodeContext:
    """
    Parse MDXCODE.md content into structured context.
    
    The format is markdown, so we parse it section by section.
    Flexible enough to handle variations, strict enough to be useful.
    """
    ctx = MDXCodeContext(raw_content=content)
    
    # Extract project metadata from the Project section
    project_match = re.search(
        r'##\s*Project.*?(?=##|\Z)',
        content,
        re.DOTALL | re.IGNORECASE
    )
    if project_match:
        project_section = project_match.group()
        
        # Parse key-value pairs
        name_match = re.search(r'\*\*Name:\*\*\s*(.+)', project_section)
        if name_match:
            ctx.project_name = name_match.group(1).strip()
        
        domain_match = re.search(r'\*\*Domain:\*\*\s*(.+)', project_section)
        if domain_match:
            ctx.domain = domain_match.group(1).strip()
        
        team_match = re.search(r'\*\*Team:\*\*\s*(.+)', project_section)
        if team_match:
            ctx.team = team_match.group(1).strip()
        
        owner_match = re.search(r'\*\*Owner:\*\*\s*(.+)', project_section)
        if owner_match:
            ctx.owner = owner_match.group(1).strip()
    
    # Extract each section
    ctx.quick_commands = _extract_section(content, "Quick Commands")
    ctx.architecture = _extract_section(content, "Architecture")
    ctx.conventions = _extract_section(content, "Conventions")
    ctx.compliance = _extract_section(content, "Compliance")
    ctx.guardrails = _extract_section(content, "Guardrails")
    ctx.known_issues = _extract_section(content, "Known Issues")
    ctx.context_files = _extract_section(content, "Context Files")
    
    # Try to infer regulatory profile from domain or explicit setting
    profile_match = re.search(r'regulatory_profile:\s*(\w+)', content, re.IGNORECASE)
    if profile_match:
        ctx.regulatory_profile = profile_match.group(1).strip()
    elif ctx.domain:
        # Infer from domain
        domain_lower = ctx.domain.lower()
        if domain_lower in ("health", "healthcare"):
            ctx.regulatory_profile = "healthcare"
        elif domain_lower in ("wealth", "protection", "financial"):
            ctx.regulatory_profile = "financial_services"
        else:
            ctx.regulatory_profile = "standard"
    
    return ctx


def _extract_section(content: str, section_name: str) -> Optional[str]:
    """Extract a section by header name."""
    # Match ## Section Name followed by content until next ## or end
    pattern = rf'##\s*{re.escape(section_name)}.*?\n(.*?)(?=\n##|\Z)'
    match = re.search(pattern, content, re.DOTALL | re.IGNORECASE)
    
    if match:
        return match.group(1).strip()
    return None


def create_starter_mdxcode(path: Path):
    """
    Create a starter MDXCODE.md file.
    
    This gives people a template to customize.
    Good defaults, clear structure, easy to extend.
    """
    starter = '''# MDXCODE.md

## Project
- **Name:** [Your Project Name]
- **Domain:** [Health | Wealth | Protection | Platform | Other]
- **Team:** [Your Team Name]
- **Owner:** [@your.name]

## Quick Commands
| Command | Description |
|---------|-------------|
| `make test` | Run all tests |
| `make lint` | Run linters |
| `make build` | Build the project |

## Architecture
- `src/` → Source code
- `tests/` → Test files
- `docs/` → Documentation

## Conventions
<!-- Add your team's coding conventions here -->
- Use meaningful variable names
- Write tests for new functionality
- Keep functions small and focused

## Compliance
<!-- Add compliance requirements here -->
- Standard security practices apply
- No hardcoded credentials
- Log access to sensitive data

## Guardrails
<!-- Things MDx Code should NOT do automatically -->
- ❌ Never commit directly to main
- ❌ Never modify production configs
- ⚠️ Schema changes require approval

## Known Issues
<!-- Current bugs, tech debt, gotchas -->
- None documented yet

## Context Files
<!-- Other files MDx Code should read for context -->
- `README.md`
- `docs/ARCHITECTURE.md`
'''
    
    path.write_text(starter)


# Package exports
__all__ = [
    "MDXCodeContext",
    "load_mdxcode_context",
    "parse_mdxcode",
    "create_starter_mdxcode",
]
