"""
Agent Loop - The Heart of MDx Code

Here's the thing most people don't realize about Claude Code:
the core architecture is embarrassingly simple.

    while task_not_complete:
        response = ask_llm(conversation)
        if response.wants_tool:
            result = execute_tool(response.tool)
            conversation.append(result)
        if response.done:
            break

That's it. AI thinks → acts → observes → repeats.
Everything else is just tooling and governance wrapped around this loop.

This file implements that loop with the governance and polish
that makes it production-ready for regulated environments.
"""

import json
from typing import Optional

from rich.console import Console
from rich.live import Live
from rich.spinner import Spinner
from rich.panel import Panel
from rich.syntax import Syntax
from rich.markdown import Markdown

from mdxcode.core.session import Session
from mdxcode.governance.audit import AuditLogger
from mdxcode.governance.permissions import check_permission, PermissionResult
from mdxcode.models.router import ModelRouter
from mdxcode.tools.registry import ToolRegistry, get_tool_definitions


class AgentLoop:
    """
    The main agent loop.
    
    This is where the magic happens. Give it a task, watch it work.
    It'll read files, write code, run tests, iterate until done.
    
    But unlike raw Claude Code, this one:
    - Respects your governance rules
    - Logs everything for audit
    - Can switch models on the fly
    - Understands your regulatory profile
    """
    
    def __init__(
        self,
        session: Session,
        router: ModelRouter,
        audit: AuditLogger,
        console: Console,
    ):
        self.session = session
        self.router = router
        self.audit = audit
        self.console = console
        self.tools = ToolRegistry()
        self.messages = []
        self.max_iterations = 50  # Safety limit. Infinite loops are bad.
    
    async def run(self, task: str) -> str:
        """
        Run the agent loop on a task.
        
        This is the simple loop that powers everything:
        1. Send conversation to LLM
        2. If LLM wants to use a tool → check permissions → execute → add result
        3. If LLM is done → return the result
        4. Repeat
        
        The complexity isn't in the loop. It's in everything we wrap around it.
        """
        # Build the system prompt with context
        system_prompt = self._build_system_prompt()
        
        # Start the conversation
        self.messages = [{"role": "user", "content": task}]
        
        self.console.print(f"\n[bold cyan]Task:[/bold cyan] {task}\n")
        self.console.print("[dim]─" * 60 + "[/dim]\n")
        
        iteration = 0
        
        while iteration < self.max_iterations:
            iteration += 1
            
            # Show thinking indicator
            with Live(Spinner("dots", text="Thinking..."), console=self.console, transient=True):
                response = await self.router.complete(
                    messages=self.messages,
                    system=system_prompt,
                    tools=get_tool_definitions(),
                )
            
            # Check if we're done
            if response.stop_reason == "end_turn":
                final_response = self._extract_text(response)
                self._show_response(final_response)
                self.audit.log_completion(final_response)
                return final_response
            
            # Process tool uses
            if response.stop_reason == "tool_use":
                # Add assistant response to history
                self.messages.append({
                    "role": "assistant",
                    "content": response.content
                })
                
                tool_results = []
                
                for block in response.content:
                    if block.type == "tool_use":
                        result = await self._handle_tool_use(block)
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result,
                        })
                
                # Add tool results to conversation
                self.messages.append({
                    "role": "user",
                    "content": tool_results
                })
        
        # If we hit max iterations, something's wrong
        self.console.print("[yellow]⚠ Max iterations reached. Stopping.[/yellow]")
        self.audit.log_warning("max_iterations_reached")
        return "Task incomplete: max iterations reached"
    
    async def _handle_tool_use(self, block) -> str:
        """
        Handle a tool use request from the LLM.
        
        This is where governance happens:
        1. Check if the tool use is allowed
        2. If not, ask for permission or block
        3. If yes, execute and return result
        4. Log everything either way
        """
        tool_name = block.name
        tool_input = block.input
        
        # Show what the agent wants to do
        self._show_tool_use(tool_name, tool_input)
        
        # Check permissions based on regulatory profile
        permission = check_permission(
            tool_name=tool_name,
            tool_input=tool_input,
            profile=self.session.profile,
            context=self.session.context,
        )
        
        if permission.status == "blocked":
            # This action is not allowed. Period.
            self._show_blocked(tool_name, permission.reason)
            self.audit.log_tool_blocked(tool_name, tool_input, permission.reason)
            return f"BLOCKED: {permission.reason}"
        
        if permission.status == "requires_approval":
            # Need human approval
            approved = self._ask_approval(tool_name, tool_input, permission.reason)
            if not approved:
                self._show_denied(tool_name)
                self.audit.log_tool_denied(tool_name, tool_input, "user_denied")
                return "DENIED: User declined to approve this action"
        
        # Execute the tool
        if self.session.dry_run:
            result = f"[DRY RUN] Would execute {tool_name}"
            self._show_dry_run(tool_name)
        else:
            try:
                result = await self.tools.execute(tool_name, tool_input)
                self._show_tool_result(tool_name, result)
            except Exception as e:
                result = f"ERROR: {str(e)}"
                self._show_tool_error(tool_name, str(e))
        
        # Log the action
        self.audit.log_tool_use(
            tool_name=tool_name,
            tool_input=tool_input,
            result=result,
            approved_by="auto" if permission.status == "allowed" else "user",
        )
        
        return result
    
    def _build_system_prompt(self) -> str:
        """
        Build the system prompt with context.
        
        This is where MDXCODE.md gets injected into the conversation.
        The AI reads your project's conventions before touching anything.
        """
        base_prompt = """You are MDx Code, an AI-native engineering companion.

You help developers build, debug, and maintain code. You have access to tools
that let you read files, write files, run commands, and search codebases.

Your approach:
1. Understand the task fully before acting
2. Read relevant files to understand context
3. Make changes incrementally, testing as you go
4. Explain what you're doing and why

You are running in a regulated environment. Respect the governance rules.
If an action is blocked, explain why and suggest alternatives.
"""
        
        # Add MDXCODE.md context if available
        if self.session.context:
            ctx = self.session.context
            base_prompt += f"""

## Project Context (from MDXCODE.md)

Project: {ctx.project_name or 'Unknown'}
Domain: {ctx.domain or 'Unknown'}
Regulatory Profile: {ctx.regulatory_profile or 'standard'}

### Conventions
{ctx.conventions or 'No specific conventions defined.'}

### Compliance Requirements
{ctx.compliance or 'Standard compliance requirements apply.'}

### Guardrails
{ctx.guardrails or 'Standard guardrails apply.'}

### Known Issues
{ctx.known_issues or 'None documented.'}
"""
        
        # Add regulatory profile context
        base_prompt += f"""

## Regulatory Profile: {self.session.profile}

You are operating under the '{self.session.profile}' regulatory profile.
This affects what actions require approval and what actions are blocked.
Always respect these constraints - they exist for good reasons.
"""
        
        return base_prompt
    
    def _extract_text(self, response) -> str:
        """Extract text content from response."""
        for block in response.content:
            if hasattr(block, "text"):
                return block.text
        return ""
    
    def _show_response(self, text: str):
        """Show the final response."""
        self.console.print("\n[dim]─" * 60 + "[/dim]")
        self.console.print(Markdown(text))
    
    def _show_tool_use(self, tool_name: str, tool_input: dict):
        """Show what tool is being used."""
        input_str = json.dumps(tool_input, indent=2)
        if len(input_str) > 200:
            input_str = input_str[:200] + "..."
        
        self.console.print(f"\n[bold blue]🔧 {tool_name}[/bold blue]")
        self.console.print(f"[dim]{input_str}[/dim]")
    
    def _show_tool_result(self, tool_name: str, result: str):
        """Show the result of a tool execution."""
        # Truncate long results for display
        display_result = result if len(result) < 500 else result[:500] + "...\n[dim](truncated)[/dim]"
        self.console.print(f"[green]   → Done[/green]")
        if self.session.verbose:
            self.console.print(f"[dim]{display_result}[/dim]")
    
    def _show_tool_error(self, tool_name: str, error: str):
        """Show a tool execution error."""
        self.console.print(f"[red]   ✗ Error: {error}[/red]")
    
    def _show_blocked(self, tool_name: str, reason: str):
        """Show that an action was blocked."""
        self.console.print(f"[red]   ⛔ BLOCKED: {reason}[/red]")
    
    def _show_denied(self, tool_name: str):
        """Show that an action was denied by user."""
        self.console.print(f"[yellow]   ✗ Denied by user[/yellow]")
    
    def _show_dry_run(self, tool_name: str):
        """Show dry run indicator."""
        self.console.print(f"[yellow]   → [DRY RUN] Would execute[/yellow]")
    
    def _ask_approval(self, tool_name: str, tool_input: dict, reason: str) -> bool:
        """Ask user for approval."""
        self.console.print(f"\n[yellow]⚠ This action requires approval:[/yellow]")
        self.console.print(f"[dim]   Reason: {reason}[/dim]")
        
        response = self.console.input("[bold]Approve? [y/N][/bold] ")
        return response.lower() in ("y", "yes")
