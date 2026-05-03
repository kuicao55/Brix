"""Tests for the CLI display formatting (Task 5).

TDD: These tests are written BEFORE the implementation.
Step 2 (RED): all should fail with ModuleNotFoundError.
Step 4 (GREEN): all should pass after implementation.
"""

import pytest
from cli.display import format_response


def test_format_response_plain():
    result = format_response("Hello world")
    assert "Hello world" in result


def test_format_response_code_block():
    result = format_response("Here is code:\n```python\nprint('hi')\n```")
    assert "print" in result
