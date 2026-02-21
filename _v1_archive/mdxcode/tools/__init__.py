"""
MDx Code Tools

The tools that let the AI take action:
- File tools: read, write, edit
- Shell tools: run bash commands
- Search tools: glob, grep, list

Each tool is simple. The power is in how the AI chains them together.
"""

from mdxcode.tools.registry import Tool, ToolRegistry, get_tool_definitions

__all__ = [
    "Tool",
    "ToolRegistry",
    "get_tool_definitions",
]
