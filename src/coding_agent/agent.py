from __future__ import annotations

import json
from typing import Any

from coding_agent.config import AgentConfig
from coding_agent.llm import LLMMessage, create_provider
from coding_agent.llm.base import LLMProvider
from coding_agent.tools import ToolRegistry, default_registry


class Agent:
    def __init__(
        self,
        config: AgentConfig | None = None,
        provider: LLMProvider | None = None,
        registry: ToolRegistry | None = None,
    ):
        self.config = config or AgentConfig()
        self.provider = provider or create_provider(self.config)
        self.registry = registry or default_registry()
        self.messages: list[LLMMessage] = []
        self._round = 0

    async def run(self, query: str, stream: bool = False) -> str:
        self.messages = [
            LLMMessage(role="system", content=self.config.system_prompt),
            LLMMessage(role="user", content=query),
        ]
        self._round = 0

        while self._round < self.config.max_tool_rounds:
            self._round += 1
            tools = self.registry.to_openai_tools()

            response = self.provider.chat(
                messages=self.messages,
                tools=tools,
                temperature=0.0,
            )

            if response.tool_calls:
                if stream:
                    print()

                self.messages.append(
                    LLMMessage(
                        role="assistant",
                        content=response.content,
                        tool_calls=response.tool_calls,
                    )
                )

                for tc in response.tool_calls:
                    tool_name = tc["function"]["name"]
                    try:
                        args = json.loads(tc["function"]["arguments"])
                    except json.JSONDecodeError:
                        args = {}

                    tool = self.registry.get(tool_name)
                    if tool is None:
                        result_msg = f"Error: unknown tool '{tool_name}'"
                    else:
                        try:
                            result = await tool.execute(**args)
                            result_msg = result.output if result.success else f"Error: {result.error}"
                        except Exception as e:
                            result_msg = f"Error executing {tool_name}: {e}"

                    self.messages.append(
                        LLMMessage(
                            role="tool",
                            content=result_msg,
                            tool_call_id=tc["id"],
                            name=tool_name,
                        )
                    )

                    if stream:
                        status = "success" if "Error" not in result_msg else "error"
                        print(f"  \u2514\u2500 {tool_name}: {status}")
            else:
                return response.content or ""

        return "Agent stopped: reached maximum tool call rounds."

    def reset(self):
        self.messages = []
        self._round = 0

    @property
    def history(self) -> list[dict[str, Any]]:
        return [
            {
                "role": m.role,
                "content": m.content,
                "tool_calls": m.tool_calls,
            }
            for m in self.messages
        ]
