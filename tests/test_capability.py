import pytest
from unittest.mock import AsyncMock
from capability.base import Tool
from capability.runner import ToolRunner
from capability.tools.calculator import CalculatorTool
from capability.tools.weather import WeatherTool
from capability.tools.file_read import FileReadTool


def test_tool_base_interface():
    tool = CalculatorTool()
    assert tool.name == "calculator"
    assert isinstance(tool.description, str)
    assert isinstance(tool.input_schema, dict)


@pytest.mark.asyncio
async def test_calculator():
    tool = CalculatorTool()
    result = await tool.execute(expression="2 + 3")
    assert "5" in result


@pytest.mark.asyncio
async def test_weather_mock():
    tool = WeatherTool()
    result = await tool.execute(city="Tokyo")
    assert isinstance(result, str)
    assert len(result) > 0


@pytest.mark.asyncio
async def test_file_read(tmp_path):
    test_file = tmp_path / "test.txt"
    test_file.write_text("hello world")
    tool = FileReadTool()
    result = await tool.execute(path=str(test_file))
    assert "hello world" in result


def test_tool_runner_register():
    runner = ToolRunner()
    tool = CalculatorTool()
    runner.register(tool)
    assert "calculator" in [t.name for t in runner._tools.values()]


def test_tool_runner_get_schemas():
    runner = ToolRunner()
    runner.register(CalculatorTool())
    runner.register(WeatherTool())
    schemas = runner.get_tool_schemas()
    assert len(schemas) == 2
    assert all(s["type"] == "function" for s in schemas)


@pytest.mark.asyncio
async def test_tool_runner_run():
    runner = ToolRunner()
    runner.register(CalculatorTool())
    result = await runner.run("calculator", {"expression": "10 * 5"})
    assert "50" in result
