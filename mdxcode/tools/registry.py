"""
Tool Registry

Tools are how the AI takes action in the real world.
Read files. Write files. Run commands. Search code.

The registry manages tool definitions and execution.
It's the bridge between what the AI wants to do and what actually happens.

Each tool is simple:
- A name
- A description (for the AI to understand when to use it)
- An input schema (what parameters it takes)
- An execute function (what it actually does)
"""

import asyncio
import json
import subprocess
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


class Tool:
    """A single tool that the AI can use."""
    
    def __init__(
        self,
        name: str,
        description: str,
        input_schema: dict,
        execute_fn: Callable,
    ):
        self.name = name
        self.description = description
        self.input_schema = input_schema
        self.execute_fn = execute_fn
    
    async def execute(self, **kwargs) -> str:
        """Execute the tool with given inputs."""
        if asyncio.iscoroutinefunction(self.execute_fn):
            return await self.execute_fn(**kwargs)
        return self.execute_fn(**kwargs)
    
    def to_api_format(self) -> dict:
        """Convert to Anthropic API tool format."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }


class ToolRegistry:
    """
    Registry of all available tools.
    
    Tools get registered at startup, then the registry
    handles routing execution requests to the right tool.
    """
    
    def __init__(self):
        self.tools: Dict[str, Tool] = {}
        self._register_default_tools()
    
    def register(self, tool: Tool):
        """Register a tool."""
        self.tools[tool.name] = tool
    
    async def execute(self, tool_name: str, tool_input: dict) -> str:
        """Execute a tool by name."""
        if tool_name not in self.tools:
            return f"ERROR: Unknown tool '{tool_name}'"
        
        tool = self.tools[tool_name]
        try:
            return await tool.execute(**tool_input)
        except Exception as e:
            return f"ERROR: {str(e)}"
    
    def get_definitions(self) -> List[dict]:
        """Get all tool definitions in API format."""
        return [tool.to_api_format() for tool in self.tools.values()]
    
    def _register_default_tools(self):
        """Register the default set of tools."""
        # File tools
        self.register(Tool(
            name="read_file",
            description="Read the contents of a file. Use this to understand existing code before making changes.",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the file to read"
                    }
                },
                "required": ["path"]
            },
            execute_fn=_read_file,
        ))
        
        self.register(Tool(
            name="write_file",
            description="Write content to a file. Creates the file if it doesn't exist, overwrites if it does.",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the file to write"
                    },
                    "content": {
                        "type": "string",
                        "description": "Content to write to the file"
                    }
                },
                "required": ["path", "content"]
            },
            execute_fn=_write_file,
        ))
        
        self.register(Tool(
            name="edit_file",
            description="Make a precise edit to a file by replacing a unique string. The old_str must appear exactly once in the file.",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the file to edit"
                    },
                    "old_str": {
                        "type": "string",
                        "description": "The exact string to find and replace (must be unique in the file)"
                    },
                    "new_str": {
                        "type": "string",
                        "description": "The string to replace it with"
                    }
                },
                "required": ["path", "old_str", "new_str"]
            },
            execute_fn=_edit_file,
        ))
        
        # Shell tools
        self.register(Tool(
            name="run_bash",
            description="Run a bash command and return the output. Use for running tests, linting, building, etc.",
            input_schema={
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The bash command to run"
                    },
                    "working_dir": {
                        "type": "string",
                        "description": "Working directory for the command (optional)"
                    }
                },
                "required": ["command"]
            },
            execute_fn=_run_bash,
        ))
        
        # Search tools
        self.register(Tool(
            name="glob",
            description="Find files matching a glob pattern. Use to discover files in the codebase.",
            input_schema={
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Glob pattern (e.g., '**/*.py', 'src/**/*.ts')"
                    },
                    "path": {
                        "type": "string",
                        "description": "Base path to search from (default: current directory)"
                    }
                },
                "required": ["pattern"]
            },
            execute_fn=_glob,
        ))
        
        self.register(Tool(
            name="grep",
            description="Search for a pattern in files. Use to find where something is defined or used.",
            input_schema={
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Regex pattern to search for"
                    },
                    "path": {
                        "type": "string",
                        "description": "File or directory to search in"
                    },
                    "include": {
                        "type": "string",
                        "description": "File pattern to include (e.g., '*.py')"
                    }
                },
                "required": ["pattern"]
            },
            execute_fn=_grep,
        ))
        
        self.register(Tool(
            name="list_directory",
            description="List contents of a directory. Use to understand project structure.",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the directory (default: current directory)"
                    },
                    "recursive": {
                        "type": "boolean",
                        "description": "Whether to list recursively (default: false)"
                    }
                },
                "required": []
            },
            execute_fn=_list_directory,
        ))


# Tool implementations
# These are the actual functions that do the work.

def _read_file(path: str) -> str:
    """Read a file and return its contents."""
    try:
        file_path = Path(path)
        if not file_path.exists():
            return f"ERROR: File not found: {path}"
        if not file_path.is_file():
            return f"ERROR: Not a file: {path}"
        
        content = file_path.read_text()
        return content
    except Exception as e:
        return f"ERROR: {str(e)}"


def _write_file(path: str, content: str) -> str:
    """Write content to a file."""
    try:
        file_path = Path(path)
        
        # Create parent directories if needed
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        file_path.write_text(content)
        return f"Successfully wrote {len(content)} characters to {path}"
    except Exception as e:
        return f"ERROR: {str(e)}"


def _edit_file(path: str, old_str: str, new_str: str) -> str:
    """Make a precise edit to a file."""
    try:
        file_path = Path(path)
        if not file_path.exists():
            return f"ERROR: File not found: {path}"
        
        content = file_path.read_text()
        
        # Check that old_str is unique
        count = content.count(old_str)
        if count == 0:
            return f"ERROR: String not found in file. Make sure you're using the exact string."
        if count > 1:
            return f"ERROR: String found {count} times. It must be unique. Include more context."
        
        # Make the replacement
        new_content = content.replace(old_str, new_str, 1)
        file_path.write_text(new_content)
        
        return f"Successfully edited {path}"
    except Exception as e:
        return f"ERROR: {str(e)}"


def _run_bash(command: str, working_dir: Optional[str] = None) -> str:
    """Run a bash command."""
    try:
        cwd = Path(working_dir) if working_dir else None
        
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=120,  # 2 minute timeout
            cwd=cwd,
        )
        
        output = result.stdout + result.stderr
        
        if result.returncode != 0:
            return f"Command exited with code {result.returncode}\n{output}"
        
        return output if output else "(no output)"
    except subprocess.TimeoutExpired:
        return "ERROR: Command timed out after 120 seconds"
    except Exception as e:
        return f"ERROR: {str(e)}"


def _glob(pattern: str, path: Optional[str] = None) -> str:
    """Find files matching a glob pattern."""
    try:
        base_path = Path(path) if path else Path.cwd()
        
        matches = list(base_path.glob(pattern))
        
        if not matches:
            return f"No files found matching '{pattern}'"
        
        # Limit results to avoid overwhelming output
        if len(matches) > 100:
            matches = matches[:100]
            result = "\n".join(str(m) for m in matches)
            return f"{result}\n\n(showing first 100 of {len(matches)} matches)"
        
        return "\n".join(str(m) for m in matches)
    except Exception as e:
        return f"ERROR: {str(e)}"


def _grep(pattern: str, path: Optional[str] = None, include: Optional[str] = None) -> str:
    """Search for a pattern in files."""
    try:
        search_path = path or "."
        
        # Build grep command
        cmd = ["grep", "-rn", "--color=never"]
        
        if include:
            cmd.extend(["--include", include])
        
        cmd.extend([pattern, search_path])
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
        )
        
        output = result.stdout
        
        if not output:
            return f"No matches found for '{pattern}'"
        
        # Limit output
        lines = output.split("\n")
        if len(lines) > 50:
            output = "\n".join(lines[:50])
            return f"{output}\n\n(showing first 50 of {len(lines)} matches)"
        
        return output
    except subprocess.TimeoutExpired:
        return "ERROR: Search timed out"
    except Exception as e:
        return f"ERROR: {str(e)}"


def _list_directory(path: Optional[str] = None, recursive: bool = False) -> str:
    """List directory contents."""
    try:
        dir_path = Path(path) if path else Path.cwd()
        
        if not dir_path.exists():
            return f"ERROR: Directory not found: {path}"
        if not dir_path.is_dir():
            return f"ERROR: Not a directory: {path}"
        
        if recursive:
            items = list(dir_path.rglob("*"))
            # Limit and filter
            items = [i for i in items if not any(p.startswith(".") for p in i.parts)][:100]
        else:
            items = list(dir_path.iterdir())
        
        # Format output
        lines = []
        for item in sorted(items):
            prefix = "📁 " if item.is_dir() else "📄 "
            rel_path = item.relative_to(dir_path) if recursive else item.name
            lines.append(f"{prefix}{rel_path}")
        
        return "\n".join(lines) if lines else "(empty directory)"
    except Exception as e:
        return f"ERROR: {str(e)}"


def get_tool_definitions() -> List[dict]:
    """Get tool definitions for API calls. Convenience function."""
    registry = ToolRegistry()
    return registry.get_definitions()


# Package exports
__all__ = [
    "Tool",
    "ToolRegistry",
    "get_tool_definitions",
]
