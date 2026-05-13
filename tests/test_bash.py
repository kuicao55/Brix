"""Tests for BashTool."""

from __future__ import annotations

import asyncio

import pytest

from capability.tools.bash import BashTool


@pytest.fixture
def bash_tool():
    return BashTool()


def test_name(bash_tool):
    assert bash_tool.name == "bash"


def test_description(bash_tool):
    assert "command" in bash_tool.description.lower()


def test_input_schema(bash_tool):
    schema = bash_tool.input_schema
    assert schema["type"] == "object"
    assert "command" in schema["properties"]
    assert "command" in schema["required"]


@pytest.mark.asyncio
async def test_echo_command(bash_tool):
    result = await bash_tool.execute(command="echo hello")
    assert "hello" in result


@pytest.mark.asyncio
async def test_stderr_capture(bash_tool):
    result = await bash_tool.execute(command="echo error >&2")
    assert "[stderr]" in result
    assert "error" in result


@pytest.mark.asyncio
async def test_empty_command(bash_tool):
    result = await bash_tool.execute(command="")
    assert "Error" in result


@pytest.mark.asyncio
async def test_timeout(bash_tool):
    result = await bash_tool.execute(command="sleep 10", timeout=1)
    assert "timed out" in result


@pytest.mark.asyncio
async def test_output_truncation(bash_tool):
    # Generate output larger than 100KB
    result = await bash_tool.execute(command="python3 -c \"print('x' * 200000)\"")
    assert "truncated" in result


@pytest.mark.asyncio
async def test_no_output(bash_tool):
    result = await bash_tool.execute(command="true")
    assert "(no output)" in result


@pytest.mark.asyncio
async def test_multiline_output(bash_tool):
    result = await bash_tool.execute(command="printf 'line1\nline2\nline3'")
    assert "line1" in result
    assert "line2" in result
    assert "line3" in result
