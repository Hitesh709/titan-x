from __future__ import annotations

from pathlib import Path
from typing import Any

from coding_agent.tools.base import BaseTool, ToolResult, ToolSpec


class ReadTool(BaseTool):
    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="read",
            description="Read the contents of a file. Use this when you need to inspect the contents of an existing file. Returns the file content with line numbers.",
            parameters={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "The absolute path to the file to read",
                    },
                    "offset": {
                        "type": "integer",
                        "description": "The line number to start reading from (1-indexed)",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of lines to read",
                    },
                },
                "required": ["file_path"],
            },
        )

    async def execute(self, **kwargs: Any) -> ToolResult:
        file_path = kwargs.get("file_path", "")
        offset = kwargs.get("offset")
        limit = kwargs.get("limit")

        path = Path(file_path)
        if not path.exists():
            return ToolResult(success=False, error=f"File not found: {file_path}")
        if not path.is_file():
            return ToolResult(success=False, error=f"Not a file: {file_path}")

        try:
            content = path.read_text(encoding="utf-8")
            lines = content.splitlines(keepends=True)

            start = (offset - 1) if offset and offset > 0 else 0
            if limit:
                lines = lines[start : start + limit]
            else:
                lines = lines[start:]

            result = ""
            for i, line in enumerate(lines, start=start + 1 if offset else 1):
                result += f"{i}: {line}"
                if not line.endswith("\n"):
                    result += "\n"

            if not result:
                result = "(empty file)"

            return ToolResult(success=True, output=result)
        except Exception as e:
            return ToolResult(success=False, error=str(e))
