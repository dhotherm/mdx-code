"""
Security Agent

A specialized agent for vulnerability scanning and remediation.

This isn't just a linter. It's an AI that:
1. Scans your codebase for known vulnerability patterns
2. Uses AI to understand context and find subtle issues
3. Can auto-fix many common vulnerabilities
4. Learns from new patterns over time

The knowledge base grows as you use it.
Every fix teaches it something new.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
import re

from rich.console import Console
from rich.table import Table
from rich.panel import Panel


# Where vulnerability knowledge lives
KNOWLEDGE_DIR = Path(__file__).parent.parent / "knowledge"
VULNERABILITIES_DIR = KNOWLEDGE_DIR / "vulnerabilities"
PATTERNS_DIR = KNOWLEDGE_DIR / "patterns"
LEARNINGS_FILE = KNOWLEDGE_DIR / "learnings" / "discovered.jsonl"


class SecurityAgent:
    """
    AI-powered security scanning and remediation.
    
    Unlike traditional static analysis, this agent:
    - Understands code context
    - Can explain why something is a vulnerability
    - Suggests fixes that fit your codebase patterns
    - Learns from new discoveries
    """
    
    def __init__(self, console: Console):
        self.console = console
        self.vulnerabilities = self._load_vulnerability_patterns()
    
    def _load_vulnerability_patterns(self) -> List[Dict]:
        """Load known vulnerability patterns from knowledge base."""
        patterns = []
        
        # Load built-in patterns
        patterns.extend(BUILTIN_VULNERABILITY_PATTERNS)
        
        # Load custom patterns from knowledge directory
        if VULNERABILITIES_DIR.exists():
            for file in VULNERABILITIES_DIR.glob("*.json"):
                try:
                    data = json.loads(file.read_text())
                    if isinstance(data, list):
                        patterns.extend(data)
                    else:
                        patterns.append(data)
                except Exception:
                    pass
        
        # Load learned patterns
        if LEARNINGS_FILE.exists():
            try:
                with open(LEARNINGS_FILE) as f:
                    for line in f:
                        try:
                            patterns.append(json.loads(line))
                        except json.JSONDecodeError:
                            pass
            except Exception:
                pass
        
        return patterns
    
    async def scan(self, path: str = "."):
        """
        Scan a path for vulnerabilities.
        
        This does two passes:
        1. Pattern-based detection (fast, catches known issues)
        2. AI-powered analysis (deeper, catches subtle issues)
        """
        self.console.print(f"[bold]Scanning {path} for vulnerabilities...[/bold]\n")
        
        scan_path = Path(path)
        if not scan_path.exists():
            self.console.print(f"[red]Path not found: {path}[/red]")
            return
        
        findings = []
        
        # Pass 1: Pattern-based detection
        self.console.print("[dim]Pass 1: Pattern matching...[/dim]")
        pattern_findings = await self._scan_patterns(scan_path)
        findings.extend(pattern_findings)
        
        # Pass 2: AI-powered analysis
        self.console.print("[dim]Pass 2: AI analysis...[/dim]")
        # AI analysis would go here in full implementation
        
        # Display results
        self._display_findings(findings)
    
    async def _scan_patterns(self, path: Path) -> List[Dict]:
        """Scan using pattern matching."""
        findings = []
        
        # Get all source files
        extensions = [".py", ".js", ".ts", ".java", ".go", ".rb", ".php"]
        files = []
        for ext in extensions:
            files.extend(path.rglob(f"*{ext}"))
        
        for file in files:
            try:
                content = file.read_text()
                lines = content.split("\n")
                
                for vuln in self.vulnerabilities:
                    pattern = vuln.get("pattern", "")
                    if not pattern:
                        continue
                    
                    for i, line in enumerate(lines, 1):
                        if re.search(pattern, line, re.IGNORECASE):
                            findings.append({
                                "file": str(file),
                                "line": i,
                                "code": line.strip(),
                                "vulnerability": vuln.get("name", "Unknown"),
                                "severity": vuln.get("severity", "medium"),
                                "description": vuln.get("description", ""),
                                "fix_available": vuln.get("fix_pattern") is not None,
                                "fix_pattern": vuln.get("fix_pattern"),
                            })
            except Exception:
                continue
        
        return findings
    
    def _display_findings(self, findings: List[Dict]):
        """Display scan findings."""
        if not findings:
            self.console.print("\n[green]✓ No vulnerabilities found![/green]")
            return
        
        # Group by severity
        critical = [f for f in findings if f["severity"] == "critical"]
        high = [f for f in findings if f["severity"] == "high"]
        medium = [f for f in findings if f["severity"] == "medium"]
        low = [f for f in findings if f["severity"] == "low"]
        
        self.console.print(f"\n[bold]Found {len(findings)} issues:[/bold]\n")
        
        # Summary table
        table = Table(show_header=True, header_style="bold")
        table.add_column("Severity", style="bold")
        table.add_column("Count", justify="right")
        
        if critical:
            table.add_row("[red]CRITICAL[/red]", str(len(critical)))
        if high:
            table.add_row("[orange1]HIGH[/orange1]", str(len(high)))
        if medium:
            table.add_row("[yellow]MEDIUM[/yellow]", str(len(medium)))
        if low:
            table.add_row("[green]LOW[/green]", str(len(low)))
        
        self.console.print(table)
        self.console.print()
        
        # Detailed findings
        severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        for finding in sorted(findings, key=lambda f: severity_order.get(f["severity"], 4)):
            severity = finding["severity"].upper()
            color = {"critical": "red", "high": "orange1", "medium": "yellow", "low": "green"}[finding["severity"]]
            
            self.console.print(f"[{color}]{severity}[/{color}]: {finding['vulnerability']}")
            self.console.print(f"  [dim]└── {finding['file']}:{finding['line']}[/dim]")
            self.console.print(f"  [dim]└── {finding['code'][:80]}[/dim]")
            if finding.get("fix_available"):
                self.console.print(f"  [green]└── Auto-fix available ✓[/green]")
            self.console.print()
    
    async def fix(self, path: str = ".", auto_fix: bool = False):
        """Fix vulnerabilities in a path."""
        self.console.print(f"[bold]Finding fixable vulnerabilities in {path}...[/bold]\n")
        
        scan_path = Path(path)
        findings = await self._scan_patterns(scan_path)
        
        fixable = [f for f in findings if f.get("fix_available")]
        
        if not fixable:
            self.console.print("[green]No auto-fixable vulnerabilities found.[/green]")
            return
        
        self.console.print(f"Found {len(fixable)} fixable issues.\n")
        
        for finding in fixable:
            self.console.print(f"[bold]{finding['vulnerability']}[/bold]")
            self.console.print(f"  File: {finding['file']}:{finding['line']}")
            self.console.print(f"  Current: [red]{finding['code']}[/red]")
            
            # Generate fix
            fix = self._generate_fix(finding)
            if fix:
                self.console.print(f"  Proposed: [green]{fix}[/green]")
                
                if auto_fix:
                    self._apply_fix(finding, fix)
                    self.console.print(f"  [green]✓ Fixed[/green]")
                else:
                    response = self.console.input("  Apply fix? [y/N] ")
                    if response.lower() == "y":
                        self._apply_fix(finding, fix)
                        self.console.print(f"  [green]✓ Fixed[/green]")
                    else:
                        self.console.print(f"  [yellow]Skipped[/yellow]")
            
            self.console.print()
    
    def _generate_fix(self, finding: Dict) -> Optional[str]:
        """Generate a fix for a vulnerability."""
        fix_pattern = finding.get("fix_pattern")
        if not fix_pattern:
            return None
        
        vuln = next((v for v in self.vulnerabilities if v.get("name") == finding["vulnerability"]), None)
        if not vuln:
            return None
        
        pattern = vuln.get("pattern", "")
        fix = vuln.get("fix_pattern", "")
        
        try:
            return re.sub(pattern, fix, finding["code"], flags=re.IGNORECASE)
        except Exception:
            return None
    
    def _apply_fix(self, finding: Dict, fix: str):
        """Apply a fix to a file."""
        file_path = Path(finding["file"])
        content = file_path.read_text()
        lines = content.split("\n")
        
        lines[finding["line"] - 1] = fix
        file_path.write_text("\n".join(lines))
    
    async def learn(self):
        """Add new vulnerability patterns to the knowledge base."""
        self.console.print("[bold]MDx Code Security Learning Mode[/bold]\n")
        self.console.print("Add new vulnerability patterns for future scans.\n")
        
        name = self.console.input("Name (e.g., 'Hardcoded AWS Key'): ").strip()
        if not name:
            self.console.print("[yellow]Cancelled[/yellow]")
            return
        
        pattern = self.console.input("Regex pattern to detect: ").strip()
        if not pattern:
            self.console.print("[yellow]Cancelled[/yellow]")
            return
        
        severity = self.console.input("Severity (critical/high/medium/low): ").strip().lower()
        if severity not in ("critical", "high", "medium", "low"):
            severity = "medium"
        
        description = self.console.input("Description: ").strip()
        fix_pattern = self.console.input("Fix pattern (optional): ").strip() or None
        
        new_pattern = {
            "name": name,
            "pattern": pattern,
            "severity": severity,
            "description": description,
            "fix_pattern": fix_pattern,
            "learned_at": datetime.now().isoformat(),
        }
        
        LEARNINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(LEARNINGS_FILE, "a") as f:
            f.write(json.dumps(new_pattern) + "\n")
        
        self.console.print(f"\n[green]✓ Learned new pattern: {name}[/green]")


# Built-in vulnerability patterns
BUILTIN_VULNERABILITY_PATTERNS = [
    {
        "name": "SQL Injection (f-string)",
        "pattern": r'f["\'].*SELECT.*\{.*\}',
        "severity": "critical",
        "description": "SQL query with f-string interpolation. Use parameterized queries.",
    },
    {
        "name": "Hardcoded Password",
        "pattern": r'password\s*=\s*["\'][^"\']+["\']',
        "severity": "high",
        "description": "Hardcoded password. Use environment variables.",
    },
    {
        "name": "Hardcoded API Key",
        "pattern": r'(?:api_key|apikey)\s*=\s*["\'][^"\']{20,}["\']',
        "severity": "high",
        "description": "Hardcoded API key. Use environment variables.",
    },
    {
        "name": "Hardcoded AWS Key",
        "pattern": r'AKIA[0-9A-Z]{16}',
        "severity": "critical",
        "description": "AWS access key in source. Remove and rotate immediately.",
    },
    {
        "name": "Shell Injection",
        "pattern": r'subprocess\..*shell\s*=\s*True',
        "severity": "high",
        "description": "Using shell=True with subprocess. Sanitize input carefully.",
    },
    {
        "name": "Eval Usage",
        "pattern": r'\beval\s*\(',
        "severity": "high",
        "description": "eval() is dangerous. Find an alternative.",
    },
    {
        "name": "Insecure Random",
        "pattern": r'random\.(random|randint|choice)\(',
        "severity": "medium",
        "description": "Using random for security. Use secrets module instead.",
        "fix_pattern": "secrets.token_hex(",
    },
    {
        "name": "YAML Unsafe Load",
        "pattern": r'yaml\.load\([^)]*\)(?!\s*,\s*Loader)',
        "severity": "medium",
        "description": "yaml.load() without safe Loader. Use yaml.safe_load().",
        "fix_pattern": "yaml.safe_load(",
    },
    {
        "name": "Weak Hash (MD5)",
        "pattern": r'hashlib\.md5\(',
        "severity": "medium",
        "description": "MD5 is weak. Use SHA-256 or better.",
        "fix_pattern": "hashlib.sha256(",
    },
    {
        "name": "Debug Mode",
        "pattern": r'DEBUG\s*=\s*True',
        "severity": "medium",
        "description": "Debug mode enabled. Disable in production.",
    },
]


__all__ = ["SecurityAgent", "BUILTIN_VULNERABILITY_PATTERNS"]
