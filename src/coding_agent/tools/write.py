from __future__ import annotations

from pathlib import Path
from typing import Any

from coding_agent.tools.base import BaseTool, ToolResult, ToolSpec


class WriteTool(BaseTool):
    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="write",
            description="Write content to a file. Creates the file if it doesn't exist. Overwrites existing content. Use this to create new files or completely replace existing ones.",
            parameters={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "The absolute path to the file to write",
                    },
                    "content": {
                        "type": "string",
                        "description": "The content to write to the file",
                    },
                },
                "required": ["file_path", "content"],
            },
        )

    async def execute(self, **kwargs: Any) -> ToolResult:
        file_path = kwargs.get("file_path", "")
        content = kwargs.get("content", "")

        path = Path(file_path)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            return ToolResult(success=True, output=f"Written {len(content)} bytes to {file_path}")
        except Exception as e:
            return ToolResult(success=False, error=str(e))
