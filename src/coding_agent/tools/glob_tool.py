from __future__ import annotations

from pathlib import Path
from typing import Any

from coding_agent.tools.base import BaseTool, ToolResult, ToolSpec


class GlobTool(BaseTool):
    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="glob",
            description="Fast file pattern matching. Find files by name patterns like **/*.py or src/**/*.ts. Use this when you need to locate files by extension or name pattern.",
            parameters={
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "The glob pattern to match (e.g. **/*.py, src/**/*.ts)",
                    },
                    "path": {
                        "type": "string",
                        "description": "The directory to search in (defaults to current working directory)",
                    },
                },
                "required": ["pattern"],
            },
        )

    async def execute(self, **kwargs: Any) -> ToolResult:
        pattern = kwargs.get("pattern", "")
        search_path = kwargs.get("path", "")

        base = Path(search_path) if search_path else Path.cwd()
        if not base.exists():
            return ToolResult(success=False, error=f"Directory not found: {search_path or Path.cwd()}")

        try:
            matches = list(base.rglob(pattern))
            if not matches:
                return ToolResult(success=True, output=f"No files matching '{pattern}' found in {base}")

            result = "\n".join(str(m.relative_to(base)) for m in sorted(matches))
            return ToolResult(success=True, output=result)
        except Exception as e:
            return ToolResult(success=False, error=str(e))
