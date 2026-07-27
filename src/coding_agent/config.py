from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class AgentConfig:
    llm_provider: str = os.getenv("CODING_AGENT_PROVIDER", "openai")
    llm_model: str = os.getenv("CODING_AGENT_MODEL", "gpt-4o")
    llm_api_key: str = os.getenv("CODING_AGENT_API_KEY", "")
    llm_base_url: str | None = os.getenv("CODING_AGENT_BASE_URL", None)
    max_tool_calls: int = int(os.getenv("CODING_AGENT_MAX_TOOL_CALLS", "25"))
    max_tool_rounds: int = int(os.getenv("CODING_AGENT_MAX_TOOL_ROUNDS", "10"))
    workspace: Path = Path(os.getenv("CODING_AGENT_WORKSPACE", Path.cwd()))
    verbose: bool = os.getenv("CODING_AGENT_VERBOSE", "0") == "1"
    system_prompt: str = field(default_factory=lambda: _default_system_prompt())


SYSTEM_PROMPT = """You are an AI coding assistant. You help users with software engineering tasks by:

1. Exploring and reading codebases to understand them
2. Answering questions about code
3. Writing, editing, and refactoring code
4. Running commands and tests
5. Searching for files and content

You have access to a set of tools. For each task, you should:
1. Think about what needs to be done
2. Use the appropriate tools
3. Observe the results
4. Continue until the task is complete

Always follow best practices:
- Understand the code before making changes
- Match existing code style and conventions
- Use existing libraries and patterns
- Verify your work when possible
- Be concise and direct in your responses

When you need to clarify requirements, ask the user."""


def _default_system_prompt() -> str:
    return SYSTEM_PROMPT
