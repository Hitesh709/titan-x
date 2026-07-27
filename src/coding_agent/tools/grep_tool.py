from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from coding_agent.tools.base import BaseTool, ToolResult, ToolSpec


class GrepTool(BaseTool):
    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="grep",
            description="Search file contents using regular expressions. Use this when you need to find files containing specific patterns, function definitions, variable references, etc.",
            parameters={
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "The regex pattern to search for",
                    },
                    "path": {
                        "type": "string",
                        "description": "The directory to search in (defaults to current working directory)",
                    },
                    "include": {
                        "type": "string",
                        "description": "File glob pattern to filter (e.g. *.py, *.{ts,tsx})",
                    },
                    "max_matches": {
                        "type": "integer",
                        "description": "Maximum number of matches to return (default 50)",
                    },
                },
                "required": ["pattern"],
            },
        )

    async def execute(self, **kwargs: Any) -> ToolResult:
        pattern = kwargs.get("pattern", "")
        search_path = kwargs.get("path", "")
        include = kwargs.get("include")
        max_matches = kwargs.get("max_matches", 50)

        base = Path(search_path) if search_path else Path.cwd()
        if not base.exists():
            return ToolResult(success=False, error=f"Directory not found: {search_path or Path.cwd()}")

        try:
            regex = re.compile(pattern)
        except re.error as e:
            return ToolResult(success=False, error=f"Invalid regex: {e}")

        matches = []
        try:
            files = list(base.rglob("*")) if not include else list(base.rglob(include))
            for file_path in sorted(files):
                if not file_path.is_file():
                    continue
                try:
                    content = file_path.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    continue

                for i, line in enumerate(content.splitlines(), 1):
                    if regex.search(line):
                        rel = file_path.relative_to(base)
                        matches.append(f"{rel}:{i}: {line.strip()}")
                        if len(matches) >= max_matches:
                            break
                if len(matches) >= max_matches:
                    break
        except Exception as e:
            return ToolResult(success=False, error=str(e))

        if not matches:
            return ToolResult(success=True, output=f"No matches found for '{pattern}' in {base}")

        result = "\n".join(matches)
        if len(matches) >= max_matches:
            result += f"\n... (showing first {max_matches} matches)"

        return ToolResult(success=True, output=result)
