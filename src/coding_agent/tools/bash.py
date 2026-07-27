from __future__ import annotations

import asyncio
import platform
from typing import Any

from coding_agent.tools.base import BaseTool, ToolResult, ToolSpec


class BashTool(BaseTool):
    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="bash",
            description="Execute a shell command. Use this to run code, build projects, run tests, install packages, etc. The command runs in the specified working directory or the current directory.",
            parameters={
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The command to execute",
                    },
                    "workdir": {
                        "type": "string",
                        "description": "The working directory to run the command in",
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Timeout in milliseconds (default 120000)",
                    },
                },
                "required": ["command"],
            },
        )

    async def execute(self, **kwargs: Any) -> ToolResult:
        command = kwargs.get("command", "")
        workdir = kwargs.get("workdir")
        timeout = kwargs.get("timeout", 120000)

        if not command:
            return ToolResult(success=False, error="No command provided")

        try:
            is_windows = platform.system() == "Windows"
            shell_cmd = command

            if is_windows:
                proc = await asyncio.create_subprocess_shell(
                    shell_cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=workdir,
                )
            else:
                proc = await asyncio.create_subprocess_shell(
                    shell_cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=workdir,
                )

            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=timeout / 1000
                )
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                return ToolResult(
                    success=False,
                    error=f"Command timed out after {timeout}ms",
                )

            output = ""
            if stdout:
                output += stdout.decode("utf-8", errors="replace")
            if stderr:
                if output:
                    output += "\n"
                output += stderr.decode("utf-8", errors="replace")

            if proc.returncode != 0:
                return ToolResult(
                    success=False,
                    error=f"Exit code {proc.returncode}\n{output}",
                )

            if not output:
                output = "(command completed with no output)"

            max_output = 10000
            if len(output) > max_output:
                output = output[:max_output] + f"\n... (output truncated at {max_output} chars)"

            return ToolResult(success=True, output=output)
        except Exception as e:
            return ToolResult(success=False, error=str(e))
