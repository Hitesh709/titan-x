from __future__ import annotations

from pathlib import Path
from typing import Any

from coding_agent.tools.base import BaseTool, ToolResult, ToolSpec


class EditTool(BaseTool):
    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="edit",
            description="Edit a file by replacing exact text. Use this for surgical changes to existing files without rewriting the entire file. The edit will fail if old_string is not found or matches multiple times.",
            parameters={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "The absolute path to the file to edit",
                    },
                    "old_string": {
                        "type": "string",
                        "description": "The exact text to find and replace",
                    },
                    "new_string": {
                        "type": "string",
                        "description": "The text to replace it with",
                    },
                },
                "required": ["file_path", "old_string", "new_string"],
            },
        )

    async def execute(self, **kwargs: Any) -> ToolResult:
        file_path = kwargs.get("file_path", "")
        old_string = kwargs.get("old_string", "")
        new_string = kwargs.get("new_string", "")

        path = Path(file_path)
        if not path.exists():
            return ToolResult(success=False, error=f"File not found: {file_path}")

        try:
            content = path.read_text(encoding="utf-8")
            count = content.count(old_string)

            if count == 0:
                return ToolResult(
                    success=False,
                    error=f"old_string not found in {file_path}",
                )
            if count > 1:
                return ToolResult(
                    success=False,
                    error=f"Found {count} matches for old_string. Provide more context to make it unique.",
                )

            new_content = content.replace(old_string, new_string, 1)
            path.write_text(new_content, encoding="utf-8")
            return ToolResult(success=True, output=f"Edited {file_path}")
        except Exception as e:
            return ToolResult(success=False, error=str(e))
