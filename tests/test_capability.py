import pytest
from pathlib import Path
from unittest.mock import AsyncMock
from capability.base import Tool
from capability.runner import ToolRunner
from capability.tools.calculator import CalculatorTool, _safe_eval
from capability.tools.weather import WeatherTool
from capability.tools.file_read import FileReadTool


# ---------------------------------------------------------------------------
# FileReadTool – security fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def scoped_tool(tmp_path):
    """FileReadTool scoped to tmp_path so tests control the allowed root."""
    tool = FileReadTool()
    tool.allowed_root = tmp_path
    return tool


# ---------------------------------------------------------------------------
# Fix 1: Path traversal / symlink / bounded read tests
# ---------------------------------------------------------------------------

class TestFileReadSecurity:
    async def test_path_traversal_rejected(self, scoped_tool, tmp_path):
        """Paths outside the allowed root must be rejected."""
        outside = tmp_path.parent / "evil.txt"
        outside.write_text("secret")
        result = await scoped_tool.execute(path=str(outside))
        assert "Error" in result
        assert "project directory" in result

    async def test_dot_dot_traversal_rejected(self, scoped_tool, tmp_path):
        """Relative .. traversal must be resolved and rejected."""
        result = await scoped_tool.execute(path=str(tmp_path / ".." / ".." / "etc" / "passwd"))
        assert "Error" in result

    async def test_symlink_rejected(self, scoped_tool, tmp_path):
        """Symlinks pointing inside the allowed root must still be rejected."""
        real = tmp_path / "real.txt"
        real.write_text("content")
        link = tmp_path / "link.txt"
        link.symlink_to(real)
        result = await scoped_tool.execute(path=str(link))
        assert "symlinks not allowed" in result

    async def test_normal_read_within_root(self, scoped_tool, tmp_path):
        """Files within the allowed root should still be readable."""
        f = tmp_path / "ok.txt"
        f.write_text("hello world")
        result = await scoped_tool.execute(path=str(f))
        assert "hello world" in result

    async def test_truncation_at_limit(self, scoped_tool, tmp_path):
        """Files exceeding the byte limit should be truncated."""
        f = tmp_path / "big.txt"
        f.write_text("A" * 150_000)
        result = await scoped_tool.execute(path=str(f))
        assert "truncated" in result
        assert len(result) < 150_000


# ---------------------------------------------------------------------------
# Fix 2: Calculator DoS protection tests
# ---------------------------------------------------------------------------

class TestCalculatorDoS:
    def test_deeply_nested_expression(self):
        """Expressions exceeding max depth should raise."""
        # Build "1+(1+(1+...))" nested beyond _MAX_DEPTH
        expr = "1"
        for _ in range(25):
            expr = f"(1+{expr})"
        import ast
        tree = ast.parse(expr, mode="eval")
        with pytest.raises(ValueError, match="deeply nested"):
            _safe_eval(tree)

    def test_too_many_nodes(self):
        """Expressions with too many AST nodes should raise."""
        # Build a balanced binary tree: depth 6 → 127 nodes, max depth 6
        def build_expr(d):
            if d == 0:
                return "1"
            return f"({build_expr(d - 1)}+{build_expr(d - 1)})"

        import ast
        tree = ast.parse(build_expr(6), mode="eval")
        with pytest.raises(ValueError, match="too complex"):
            _safe_eval(tree)

    def test_large_exponent_rejected(self):
        """Exponents larger than 1000 should be rejected."""
        import ast
        tree = ast.parse("2 ** 9999", mode="eval")
        with pytest.raises(ValueError, match="Exponent too large"):
            _safe_eval(tree)

    def test_small_exponent_allowed(self):
        """Small exponents should still work."""
        import ast
        tree = ast.parse("2 ** 10", mode="eval")
        assert _safe_eval(tree) == 1024

    def test_negative_large_exponent_rejected(self):
        """Negative exponents beyond the cap should be rejected."""
        import ast
        tree = ast.parse("2 ** -1001", mode="eval")
        with pytest.raises(ValueError, match="Exponent too large"):
            _safe_eval(tree)


# ---------------------------------------------------------------------------
# Existing tests (kept intact)
# ---------------------------------------------------------------------------

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
    tool.allowed_root = tmp_path
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
