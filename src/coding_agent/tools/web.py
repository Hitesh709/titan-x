from __future__ import annotations

from typing import Any

import httpx

from coding_agent.tools.base import BaseTool, ToolResult, ToolSpec


class WebFetchTool(BaseTool):
    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="web_fetch",
            description="Fetch content from a URL. Use this to retrieve web content, API responses, or documentation from the internet.",
            parameters={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The URL to fetch content from",
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Timeout in seconds (default 30)",
                    },
                },
                "required": ["url"],
            },
        )

    async def execute(self, **kwargs: Any) -> ToolResult:
        url = kwargs.get("url", "")
        timeout = kwargs.get("timeout", 30)

        if not url:
            return ToolResult(success=False, error="No URL provided")

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get(url, follow_redirects=True)
                response.raise_for_status()

                content_type = response.headers.get("content-type", "")
                if "text" in content_type or "json" in content_type or "html" in content_type:
                    text = response.text
                else:
                    text = f"[Binary content: {content_type}, {len(response.content)} bytes]"

                max_output = 10000
                if len(text) > max_output:
                    text = text[:max_output] + f"\n... (content truncated at {max_output} chars)"

                return ToolResult(
                    success=True,
                    output=text,
                )
        except httpx.HTTPStatusError as e:
            return ToolResult(success=False, error=f"HTTP {e.response.status_code}: {e.response.text[:500]}")
        except httpx.RequestError as e:
            return ToolResult(success=False, error=f"Request failed: {e}")
        except Exception as e:
            return ToolResult(success=False, error=str(e))
