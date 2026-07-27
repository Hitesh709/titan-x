from __future__ import annotations

from typing import Any

from anthropic import Anthropic

from coding_agent.llm.base import LLMMessage, LLMProvider, LLMResponse


class AnthropicProvider(LLMProvider):
    def __init__(
        self,
        api_key: str,
        model: str = "claude-sonnet-4-20250514",
        base_url: str | None = None,
    ):
        self.model = model
        kwargs = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        self.client = Anthropic(**kwargs)
        self._cache: dict[str, Any] = {}

    def chat(
        self,
        messages: list[LLMMessage],
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        system_msg = None
        api_messages = []
        for m in messages:
            if m.role == "system":
                system_msg = m.content
            elif m.role == "tool":
                api_messages.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": m.tool_call_id,
                                "content": m.content or "",
                            }
                        ],
                    }
                )
            else:
                content: list[dict[str, Any]] = []
                if m.content:
                    content.append({"type": "text", "text": m.content})
                if m.tool_calls:
                    for tc in m.tool_calls:
                        content.append(
                            {
                                "type": "tool_use",
                                "id": tc["id"],
                                "name": tc["function"]["name"],
                                "input": _parse_json(tc["function"]["arguments"]),
                            }
                        )
                if m.role == "assistant" and content:
                    api_messages.append({"role": "assistant", "content": content})
                elif m.role in ("user", "assistant"):
                    api_messages.append({"role": m.role, "content": m.content or ""})

        api_kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": api_messages,
            "temperature": temperature,
            "max_tokens": max_tokens or 8192,
        }
        if system_msg:
            api_kwargs["system"] = system_msg
        if tools:
            api_kwargs["tools"] = [_convert_tool(t) for t in tools]
        if tool_choice:
            api_kwargs["tool_choice"] = {"type": "tool", "name": tool_choice}

        response = self.client.messages.create(**api_kwargs)

        content = None
        tool_calls = None
        for block in response.content:
            if block.type == "text":
                content = block.text
            elif block.type == "tool_use":
                if tool_calls is None:
                    tool_calls = []
                tool_calls.append(
                    {
                        "id": block.id,
                        "type": "function",
                        "function": {
                            "name": block.name,
                            "arguments": _dump_json(block.input),
                        },
                    }
                )

        usage = None
        if response.usage:
            usage = {
                "prompt_tokens": response.usage.input_tokens,
                "completion_tokens": response.usage.output_tokens,
                "total_tokens": response.usage.input_tokens + response.usage.output_tokens,
            }

        return LLMResponse(content=content, tool_calls=tool_calls, usage=usage)


def _convert_tool(t: dict) -> dict:
    return {
        "name": t["function"]["name"],
        "description": t["function"]["description"],
        "input_schema": t["function"]["parameters"],
    }


def _parse_json(s: str) -> Any:
    import json
    return json.loads(s)


def _dump_json(o: Any) -> str:
    import json
    return json.dumps(o)
