"""Bash command execution tool."""

from __future__ import annotations

import asyncio

from capability.base import Tool

_MAX_OUTPUT_BYTES = 100_000  # 100 KB limit, consistent with FileReadTool
_DEFAULT_TIMEOUT = 30  # seconds


class BashTool(Tool):
    """Execute shell commands asynchronously."""

    @property
    def name(self) -> str:
        return "bash"

    @property
    def description(self) -> str:
        return "Execute a shell command and return its output."

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The shell command to execute",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Timeout in seconds (default: 30)",
                    "default": 30,
                },
            },
            "required": ["command"],
        }

    async def execute(self, **params) -> str:
        command = params.get("command", "")
        if not command:
            return "Error: command is required"

        timeout = params.get("timeout", _DEFAULT_TIMEOUT)
        if not isinstance(timeout, (int, float)) or timeout <= 0:
            timeout = _DEFAULT_TIMEOUT

        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    proc.communicate(), timeout=timeout
                )
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                return f"Error: command timed out after {timeout}s"

            stdout = stdout_bytes.decode("utf-8", errors="replace") if stdout_bytes else ""
            stderr = stderr_bytes.decode("utf-8", errors="replace") if stderr_bytes else ""

            parts = []
            if stdout:
                parts.append(stdout)
            if stderr:
                parts.append(f"[stderr]\n{stderr}")
            output = "\n".join(parts) if parts else "(no output)"

            # Truncate if too long
            if len(output) > _MAX_OUTPUT_BYTES:
                output = output[:_MAX_OUTPUT_BYTES] + "\n... (truncated)"

            return output

        except Exception as exc:
            return f"Error executing command: {exc}"
