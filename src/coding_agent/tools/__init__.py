from coding_agent.tools.base import ToolResult, ToolSpec, ToolRegistry
from coding_agent.tools.read import ReadTool
from coding_agent.tools.write import WriteTool
from coding_agent.tools.edit import EditTool
from coding_agent.tools.glob_tool import GlobTool
from coding_agent.tools.grep_tool import GrepTool
from coding_agent.tools.bash import BashTool
from coding_agent.tools.web import WebFetchTool

__all__ = [
    "ToolResult",
    "ToolSpec",
    "ToolRegistry",
    "ReadTool",
    "WriteTool",
    "EditTool",
    "GlobTool",
    "GrepTool",
    "BashTool",
    "WebFetchTool",
]


def default_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(ReadTool())
    registry.register(WriteTool())
    registry.register(EditTool())
    registry.register(GlobTool())
    registry.register(GrepTool())
    registry.register(BashTool())
    registry.register(WebFetchTool())
    return registry
