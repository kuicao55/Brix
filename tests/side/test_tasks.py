"""Side tasks 单元测试。"""
from __future__ import annotations

import json

import pytest
from unittest.mock import AsyncMock, MagicMock

from side.base import SideTaskContext


def _make_ctx(llm_response: str = "", **kwargs) -> SideTaskContext:
    """创建测试用 SideTaskContext。"""
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.content = llm_response
    mock_client.chat = AsyncMock(return_value=mock_response)
    return SideTaskContext(
        llm_client=mock_client,
        side_model="test-model",
        config=kwargs.get("config", {}),
        memory=kwargs.get("memory"),
        session_messages=kwargs.get("session_messages", []),
        user_input=kwargs.get("user_input", ""),
        hooks=kwargs.get("hooks"),
    )


# --- SessionTitleTask ---


@pytest.mark.asyncio
async def test_session_title_basic():
    """SessionTitleTask 从对话中提取标题。"""
    from side.tasks.session_title import SessionTitleTask

    task = SessionTitleTask()
    ctx = _make_ctx(
        llm_response='{"title": "Fix login bug"}',
        session_messages=[
            {"role": "user", "content": "登录页面有个 bug"},
            {"role": "assistant", "content": "我来看看"},
            {"role": "user", "content": "点击登录按钮没反应"},
        ],
    )
    result = await task.execute(ctx)
    assert result == "Fix login bug"
    ctx.llm_client.chat.assert_called_once()


@pytest.mark.asyncio
async def test_session_title_empty_messages():
    """SessionTitleTask 无用户消息时返回 None。"""
    from side.tasks.session_title import SessionTitleTask

    task = SessionTitleTask()
    ctx = _make_ctx(session_messages=[])
    result = await task.execute(ctx)
    assert result is None


@pytest.mark.asyncio
async def test_session_title_invalid_json():
    """SessionTitleTask JSON 解析失败时回退到首条用户消息。"""
    from side.tasks.session_title import SessionTitleTask

    task = SessionTitleTask()
    ctx = _make_ctx(
        llm_response="not json",
        session_messages=[{"role": "user", "content": "hi"}],
    )
    result = await task.execute(ctx)
    # 回退：取首条用户消息前 80 字符
    assert result == "hi"


@pytest.mark.asyncio
async def test_session_title_fenced_json():
    """SessionTitleTask 能从 ```json fenced 代码块中提取标题。"""
    from side.tasks.session_title import SessionTitleTask

    task = SessionTitleTask()
    fenced = '```json\n{"title": "Fix auth flow"}\n```'
    ctx = _make_ctx(
        llm_response=fenced,
        session_messages=[{"role": "user", "content": "auth broken"}],
    )
    result = await task.execute(ctx)
    assert result == "Fix auth flow"


@pytest.mark.asyncio
async def test_session_title_prefixed_text():
    """SessionTitleTask 能从带前缀文字的响应中提取标题。"""
    from side.tasks.session_title import SessionTitleTask

    task = SessionTitleTask()
    ctx = _make_ctx(
        llm_response='Here is the title:\n{"title": "Debug CI pipeline"}',
        session_messages=[{"role": "user", "content": "CI broken"}],
    )
    result = await task.execute(ctx)
    assert result == "Debug CI pipeline"


@pytest.mark.asyncio
async def test_session_title_oversized_trimmed():
    """SessionTitleTask 标题超长时截断到 80 字符。"""
    from side.tasks.session_title import SessionTitleTask

    task = SessionTitleTask()
    long_title = "A" * 120
    ctx = _make_ctx(
        llm_response=json.dumps({"title": long_title}),
        session_messages=[{"role": "user", "content": "x"}],
    )
    result = await task.execute(ctx)
    assert result is not None
    assert len(result) <= 80


@pytest.mark.asyncio
async def test_session_title_newlines_collapsed():
    """SessionTitleTask 标题含换行时折叠为单行。"""
    from side.tasks.session_title import SessionTitleTask

    task = SessionTitleTask()
    ctx = _make_ctx(
        llm_response=json.dumps({"title": "Fix\nlogin\nbug"}),
        session_messages=[{"role": "user", "content": "x"}],
    )
    result = await task.execute(ctx)
    assert result is not None
    assert "\n" not in result
    assert "Fix login bug" == result


@pytest.mark.asyncio
async def test_session_title_non_string_field():
    """SessionTitleTask title 字段非字符串时回退。"""
    from side.tasks.session_title import SessionTitleTask

    task = SessionTitleTask()
    ctx = _make_ctx(
        llm_response='{"title": 12345}',
        session_messages=[{"role": "user", "content": "help me"}],
    )
    result = await task.execute(ctx)
    # 非字符串 title 视为无效，回退到首条用户消息
    assert result == "help me"


@pytest.mark.asyncio
async def test_session_title_fallback_long_message():
    """SessionTitleTask 回退时截断首条用户消息到 80 字符。"""
    from side.tasks.session_title import SessionTitleTask

    task = SessionTitleTask()
    long_msg = "请帮我修复一个很长很长的问题" * 20
    ctx = _make_ctx(
        llm_response="totally broken response",
        session_messages=[{"role": "user", "content": long_msg}],
    )
    result = await task.execute(ctx)
    assert result is not None
    assert len(result) <= 80


# --- ToolSummaryTask ---


@pytest.mark.asyncio
async def test_tool_summary_basic():
    """ToolSummaryTask 生成工具调用摘要。"""
    from side.tasks.tool_summary import ToolSummaryTask

    task = ToolSummaryTask()
    ctx = _make_ctx(
        llm_response="Searched in auth/",
        config={
            "_side_task_args": {
                "tool_name": "Grep",
                "tool_input": {"pattern": "auth"},
                "tool_result": "found 3 files",
            },
        },
    )
    result = await task.execute(ctx)
    assert result == "Searched in auth/"


@pytest.mark.asyncio
async def test_tool_summary_empty_args():
    """ToolSummaryTask 无工具信息时仍可执行。"""
    from side.tasks.tool_summary import ToolSummaryTask

    task = ToolSummaryTask()
    ctx = _make_ctx(llm_response="No tools used", config={})
    result = await task.execute(ctx)
    assert result == "No tools used"


@pytest.mark.asyncio
async def test_tool_summary_string_input():
    """ToolSummaryTask tool_input 为字符串时不崩溃。"""
    from side.tasks.tool_summary import ToolSummaryTask

    task = ToolSummaryTask()
    ctx = _make_ctx(
        llm_response="Read file",
        config={
            "_side_task_args": {
                "tool_name": "Read",
                "tool_input": "/path/to/file.py",
                "tool_result": "file contents",
            },
        },
    )
    result = await task.execute(ctx)
    assert result == "Read file"


@pytest.mark.asyncio
async def test_tool_summary_list_input():
    """ToolSummaryTask tool_input 为列表时不崩溃。"""
    from side.tasks.tool_summary import ToolSummaryTask

    task = ToolSummaryTask()
    ctx = _make_ctx(
        llm_response="Processed items",
        config={
            "_side_task_args": {
                "tool_name": "Process",
                "tool_input": ["item1", "item2", "item3"],
                "tool_result": "done",
            },
        },
    )
    result = await task.execute(ctx)
    assert result == "Processed items"


@pytest.mark.asyncio
async def test_tool_summary_scalar_input():
    """ToolSummaryTask tool_input 为标量（int）时不崩溃。"""
    from side.tasks.tool_summary import ToolSummaryTask

    task = ToolSummaryTask()
    ctx = _make_ctx(
        llm_response="Incremented",
        config={
            "_side_task_args": {
                "tool_name": "Counter",
                "tool_input": 42,
                "tool_result": 43,
            },
        },
    )
    result = await task.execute(ctx)
    assert result == "Incremented"


@pytest.mark.asyncio
async def test_tool_summary_none_input():
    """ToolSummaryTask tool_input 为 None 时不崩溃。"""
    from side.tasks.tool_summary import ToolSummaryTask

    task = ToolSummaryTask()
    ctx = _make_ctx(
        llm_response="No input",
        config={
            "_side_task_args": {
                "tool_name": "Ping",
                "tool_input": None,
                "tool_result": "pong",
            },
        },
    )
    result = await task.execute(ctx)
    assert result == "No input"


@pytest.mark.asyncio
async def test_tool_summary_oversized_trimmed():
    """ToolSummaryTask 输出超长时截断到 30 字符。"""
    from side.tasks.tool_summary import ToolSummaryTask

    task = ToolSummaryTask()
    long_output = "This is a very long summary that exceeds the thirty character limit significantly"
    ctx = _make_ctx(
        llm_response=long_output,
        config={
            "_side_task_args": {
                "tool_name": "Grep",
                "tool_input": {"pattern": "auth"},
                "tool_result": "found",
            },
        },
    )
    result = await task.execute(ctx)
    assert result is not None
    assert len(result) <= 30


@pytest.mark.asyncio
async def test_tool_summary_newlines_collapsed():
    """ToolSummaryTask 输出含换行时折叠为单行。"""
    from side.tasks.tool_summary import ToolSummaryTask

    task = ToolSummaryTask()
    ctx = _make_ctx(
        llm_response="Fixed\nbug\nin auth",
        config={
            "_side_task_args": {
                "tool_name": "Edit",
                "tool_input": {"file": "auth.py"},
                "tool_result": "ok",
            },
        },
    )
    result = await task.execute(ctx)
    assert result is not None
    assert "\n" not in result
    assert "Fixed bug in auth" == result


@pytest.mark.asyncio
async def test_tool_summary_non_string_output():
    """ToolSummaryTask 输出非字符串时回退到 None。"""
    from side.tasks.tool_summary import ToolSummaryTask

    task = ToolSummaryTask()
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.content = None
    mock_client.chat = AsyncMock(return_value=mock_response)
    ctx = SideTaskContext(
        llm_client=mock_client,
        side_model="test-model",
        config={
            "_side_task_args": {
                "tool_name": "Grep",
                "tool_input": {"pattern": "auth"},
                "tool_result": "found",
            },
        },
        memory=None,
        session_messages=[],
        user_input="",
        hooks=None,
    )
    result = await task.execute(ctx)
    assert result is None


# --- Secret redaction tests (CQR-2 HIGH) ---


@pytest.mark.asyncio
async def test_tool_summary_redacts_api_key_in_input():
    """ToolSummaryTask 将 tool_input 中的 api_key 红act后再发给 LLM。"""
    from side.tasks.tool_summary import ToolSummaryTask

    task = ToolSummaryTask()
    ctx = _make_ctx(
        llm_response="Called API",
        config={
            "_side_task_args": {
                "tool_name": "Bash",
                "tool_input": {
                    "command": "curl -H 'Authorization: Bearer sk-abc123secrettoken'",
                    "api_key": "sk-proj-SECRETKEY123456789",
                    "token": "ghp_XXXXXXXXXXXXXXXXXXXX",
                    "password": "hunter2",
                },
                "tool_result": "ok",
            },
        },
    )
    # 捕获发给 LLM 的实际 prompt 内容
    captured_messages = []

    async def capture_chat(*args, **kwargs):
        captured_messages.extend(kwargs.get("messages", args[0] if args else []))
        return ctx.llm_client.chat.return_value

    ctx.llm_client.chat = AsyncMock(side_effect=capture_chat)
    await task.execute(ctx)

    # 合并所有 prompt 内容用于断言
    all_text = " ".join(m["content"] for m in captured_messages)
    assert "sk-abc123secrettoken" not in all_text, "Bearer token 应被红act"
    assert "sk-proj-SECRETKEY123456789" not in all_text, "api_key 值应被红act"
    assert "ghp_XXXXXXXXXXXXXXXXXXXX" not in all_text, "token 值应被红act"
    assert "hunter2" not in all_text, "password 值应被红act"
    # 确认工具名和操作类型仍然保留
    assert "Bash" in all_text, "工具名应保留"


@pytest.mark.asyncio
async def test_tool_summary_redacts_secrets_in_result():
    """ToolSummaryTask 将 tool_result 中的凭证模式红act。"""
    from side.tasks.tool_summary import ToolSummaryTask

    task = ToolSummaryTask()
    ctx = _make_ctx(
        llm_response="Fetched data",
        config={
            "_side_task_args": {
                "tool_name": "Bash",
                "tool_input": {"command": "curl https://api.example.com"},
                "tool_result": (
                    "HTTP 200\n"
                    "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.abc\n"
                    "X-Api-Key: secret-key-value-12345\n"
                    '{"access_token": "ya29.secretvalue", "status": "ok"}'
                ),
            },
        },
    )
    captured_messages = []

    async def capture_chat(*args, **kwargs):
        captured_messages.extend(kwargs.get("messages", args[0] if args else []))
        return ctx.llm_client.chat.return_value

    ctx.llm_client.chat = AsyncMock(side_effect=capture_chat)
    await task.execute(ctx)

    all_text = " ".join(m["content"] for m in captured_messages)
    assert "eyJhbGciOiJIUzI1NiJ9" not in all_text, "JWT token 应被红act"
    assert "secret-key-value-12345" not in all_text, "X-Api-Key 值应被红act"
    assert "ya29.secretvalue" not in all_text, "access_token 值应被红act"
    # 非敏感内容应保留
    assert "HTTP 200" in all_text or "200" in all_text, "非敏感状态码应保留"


@pytest.mark.asyncio
async def test_tool_summary_redacts_nested_dict_secrets():
    """ToolSummaryTask 红act嵌套字典中的凭证字段。"""
    from side.tasks.tool_summary import ToolSummaryTask

    task = ToolSummaryTask()
    ctx = _make_ctx(
        llm_response="Updated config",
        config={
            "_side_task_args": {
                "tool_name": "Write",
                "tool_input": {
                    "file_path": "config.yaml",
                    "content": "db_password: supersecret\napi_token: tok_abc123",
                },
                "tool_result": "written",
            },
        },
    )
    captured_messages = []

    async def capture_chat(*args, **kwargs):
        captured_messages.extend(kwargs.get("messages", args[0] if args else []))
        return ctx.llm_client.chat.return_value

    ctx.llm_client.chat = AsyncMock(side_effect=capture_chat)
    await task.execute(ctx)

    all_text = " ".join(m["content"] for m in captured_messages)
    # dict 键名含有 secret 类关键字时值应被红act
    # 但 content 字段内的自由文本（如写入文件的内容）需要更精细处理；
    # 至少顶层敏感键名的值必须被红act
    assert "supersecret" not in all_text, "db_password 值应被红act"
    assert "tok_abc123" not in all_text, "api_token 值应被红act"


@pytest.mark.asyncio
async def test_tool_summary_preserves_non_sensitive_fields():
    """ToolSummaryTask 非敏感字段应保留原样。"""
    from side.tasks.tool_summary import ToolSummaryTask

    task = ToolSummaryTask()
    ctx = _make_ctx(
        llm_response="Searched files",
        config={
            "_side_task_args": {
                "tool_name": "Grep",
                "tool_input": {"pattern": "def main", "path": "/src"},
                "tool_result": "Found 5 matches in 3 files",
            },
        },
    )
    captured_messages = []

    async def capture_chat(*args, **kwargs):
        captured_messages.extend(kwargs.get("messages", args[0] if args else []))
        return ctx.llm_client.chat.return_value

    ctx.llm_client.chat = AsyncMock(side_effect=capture_chat)
    await task.execute(ctx)

    all_text = " ".join(m["content"] for m in captured_messages)
    assert "def main" in all_text, "非敏感搜索 pattern 应保留"
    assert "/src" in all_text, "非敏感路径应保留"
    assert "Found 5 matches" in all_text, "非敏感 result 应保留"


# --- Control character / escape sequence tests (CQR-2 MEDIUM) ---


# --- CQR-3: Pattern-based key redaction tests ---


@pytest.mark.asyncio
async def test_tool_summary_redacts_db_password_key():
    """db_password 等组合键名应被红act（模式匹配而非精确匹配）。"""
    from side.tasks.tool_summary import ToolSummaryTask

    task = ToolSummaryTask()
    ctx = _make_ctx(
        llm_response="Updated config",
        config={
            "_side_task_args": {
                "tool_name": "Write",
                "tool_input": {
                    "file_path": "config.yaml",
                    "db_password": "supersecret123",
                    "apiToken": "tok_live_abc",
                    "auth_header": "Bearer xyz",
                    "github_token": "ghp_FAKE00000000000000000000000000000000",
                    "secret_key": "my_secret_value",
                },
                "tool_result": "written",
            },
        },
    )
    captured_messages = []

    async def capture_chat(*args, **kwargs):
        captured_messages.extend(kwargs.get("messages", args[0] if args else []))
        return ctx.llm_client.chat.return_value

    ctx.llm_client.chat = AsyncMock(side_effect=capture_chat)
    await task.execute(ctx)

    all_text = " ".join(m["content"] for m in captured_messages)
    assert "supersecret123" not in all_text, "db_password 值应被红act"
    assert "tok_live_abc" not in all_text, "apiToken 值应被红act"
    assert "my_secret_value" not in all_text, "secret_key 值应被红act"


@pytest.mark.asyncio
async def test_tool_summary_redacts_basic_auth_header():
    """Authorization: Basic <credential> 整行应被红act（含多 token 值）。"""
    from side.tasks.tool_summary import ToolSummaryTask

    task = ToolSummaryTask()
    ctx = _make_ctx(
        llm_response="Fetched data",
        config={
            "_side_task_args": {
                "tool_name": "Bash",
                "tool_input": {"command": "curl https://api.example.com"},
                "tool_result": (
                    "HTTP 200\n"
                    "Authorization: Basic dXNlcjpwYXNz\n"
                    "X-Api-Key: secret-long-key-value-here\n"
                    "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.abc\n"
                ),
            },
        },
    )
    captured_messages = []

    async def capture_chat(*args, **kwargs):
        captured_messages.extend(kwargs.get("messages", args[0] if args else []))
        return ctx.llm_client.chat.return_value

    ctx.llm_client.chat = AsyncMock(side_effect=capture_chat)
    await task.execute(ctx)

    all_text = " ".join(m["content"] for m in captured_messages)
    assert "dXNlcjpwYXNz" not in all_text, "Basic auth credential 应被红act"
    assert "secret-long-key-value-here" not in all_text, "X-Api-Key 完整值应被红act"


# --- CQR-3: sanitize tests ---


def test_sanitize_summary_strips_ansi_escapes():
    """_sanitize_summary 应剥离 ANSI 转义序列。"""
    from side.tasks.tool_summary import _sanitize_summary

    # 常见 ANSI 颜色码
    payload = "\x1b[31mRed Error\x1b[0m in auth"
    result = _sanitize_summary(payload)
    assert result is not None
    assert "\x1b" not in result, "ANSI ESC 字符应被剥离"
    assert "[" not in result or "Red" not in result, "ANSI 控制序列内容应被剥离"
    # 清理后应保留可读文本
    assert "Error" in result or "auth" in result


def test_sanitize_summary_strips_csi_sequences():
    """_sanitize_summary 应剥离 CSI (Control Sequence Introducer) 序列。"""
    from side.tasks.tool_summary import _sanitize_summary

    # 光标移动、清屏等 CSI 序列
    payload = "\x1b[2J\x1b[1;1HDone\x1b[?25l"
    result = _sanitize_summary(payload)
    assert result is not None
    assert "\x1b" not in result
    assert "Done" in result


def test_sanitize_summary_strips_control_chars():
    """_sanitize_summary 应剥离 NUL、BEL、BS 等控制字符。"""
    from side.tasks.tool_summary import _sanitize_summary

    payload = "\x00\x07\x08Result\x1b[0m"
    result = _sanitize_summary(payload)
    assert result is not None
    assert "\x00" not in result
    assert "\x07" not in result
    assert "\x08" not in result
    assert "\x1b" not in result
    assert "Result" in result


def test_sanitize_title_strips_ansi_escapes():
    """_sanitize_title 应剥离 ANSI 转义序列。"""
    from side.tasks.session_title import _sanitize_title

    payload = "\x1b[1m\x1b[34mFix login bug\x1b[0m"
    result = _sanitize_title(payload)
    assert result is not None
    assert "\x1b" not in result
    assert "Fix login bug" in result


def test_sanitize_title_strips_csi_sequences():
    """_sanitize_title 应剥离 CSI 序列。"""
    from side.tasks.session_title import _sanitize_title

    payload = "\x1b[32mAuth flow\x1b[0m\x1b[2K"
    result = _sanitize_title(payload)
    assert result is not None
    assert "\x1b" not in result
    assert "Auth flow" in result


def test_sanitize_title_strips_control_chars():
    """_sanitize_title 应剥离控制字符。"""
    from side.tasks.session_title import _sanitize_title

    payload = "\x00\x07Title\x08\x1b[0m"
    result = _sanitize_title(payload)
    assert result is not None
    assert "\x00" not in result
    assert "\x07" not in result
    assert "\x08" not in result
    assert "\x1b" not in result
    assert "Title" in result


def test_sanitize_summary_all_escapes_only():
    """_sanitize_summary 处理纯 ANSI 序列无可读文本的情况。"""
    from side.tasks.tool_summary import _sanitize_summary

    payload = "\x1b[31m\x1b[1m\x1b[0m"
    result = _sanitize_summary(payload)
    # 纯控制序列清理后为空或 None
    assert result is None


def test_sanitize_title_all_escapes_only():
    """_sanitize_title 处理纯 ANSI 序列无可读文本的情况。"""
    from side.tasks.session_title import _sanitize_title

    payload = "\x1b[31m\x1b[1m\x1b[0m"
    result = _sanitize_title(payload)
    assert result is None


# --- CQR-4: Expanded header redaction tests ---


def test_redact_tool_result_cookie_header():
    """Cookie header 值应被红act。"""
    from side.tasks.tool_summary import _redact_tool_result

    result = _redact_tool_result(
        "HTTP 200\n"
        "Cookie: session_id=abc123; token=xyz789\n"
        "Content-Type: application/json"
    )
    assert "abc123" not in result, "Cookie 值应被红act"
    assert "xyz789" not in result, "Cookie token 值应被红act"
    assert "HTTP 200" in result, "非敏感内容应保留"


def test_redact_tool_result_set_cookie_header():
    """Set-Cookie header 值应被红act。"""
    from side.tasks.tool_summary import _redact_tool_result

    result = _redact_tool_result(
        "HTTP 200\n"
        "Set-Cookie: session=secret_session_value; HttpOnly\n"
        "Content-Type: text/html"
    )
    assert "secret_session_value" not in result, "Set-Cookie 值应被红act"
    assert "HTTP 200" in result, "非敏感内容应保留"


def test_redact_tool_result_proxy_authorization_header():
    """Proxy-Authorization header 值应被红act。"""
    from side.tasks.tool_summary import _redact_tool_result

    result = _redact_tool_result(
        "HTTP 200\n"
        "Proxy-Authorization: Basic dXNlcjpwYXNz\n"
        "Content-Length: 42"
    )
    assert "dXNlcjpwYXNz" not in result, "Proxy-Authorization 值应被红act"
    assert "HTTP 200" in result, "非敏感内容应保留"


def test_redact_tool_result_x_auth_token_header():
    """X-Auth-Token header 值应被红act。"""
    from side.tasks.tool_summary import _redact_tool_result

    result = _redact_tool_result(
        "HTTP 200\n"
        "X-Auth-Token: my-secret-auth-token-value\n"
        "X-Request-Id: req-123"
    )
    assert "my-secret-auth-token-value" not in result, "X-Auth-Token 值应被红act"
    assert "req-123" in result, "非敏感 header 应保留"


def test_redact_tool_result_generic_token_header_fallback():
    """header 名含 token/secret/key/auth 的未知 header 应被 fallback 红act。"""
    from side.tasks.tool_summary import _redact_tool_result

    result = _redact_tool_result(
        "HTTP 200\n"
        "X-Custom-Auth: bearer_custom_value_here\n"
        "X-Some-Token: another_secret_token\n"
        "X-My-Key: my_api_key_value\n"
        "X-Secret-Header: super_secret_stuff\n"
        "Content-Type: application/json"
    )
    assert "bearer_custom_value_here" not in result, "X-Custom-Auth 值应被红act"
    assert "another_secret_token" not in result, "X-Some-Token 值应被红act"
    assert "my_api_key_value" not in result, "X-My-Key 值应被红act"
    assert "super_secret_stuff" not in result, "X-Secret-Header 值应被红act"
    assert "application/json" in result, "Content-Type 非敏感应保留"


def test_redact_tool_result_all_new_headers_together():
    """多个敏感 header 同时出现时应全部被红act。"""
    from side.tasks.tool_summary import _redact_tool_result

    result = _redact_tool_result(
        "HTTP 200\n"
        "Cookie: sid=abc123\n"
        "Set-Cookie: token=xyz789; Path=/\n"
        "Proxy-Authorization: Bearer proxy_secret\n"
        "X-Auth-Token: auth_token_value\n"
        "X-Api-Key: api_key_12345\n"
        "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.abc\n"
        "Content-Type: application/json"
    )
    assert "abc123" not in result, "Cookie 应被红act"
    assert "xyz789" not in result, "Set-Cookie 应被红act"
    assert "proxy_secret" not in result, "Proxy-Authorization 应被红act"
    assert "auth_token_value" not in result, "X-Auth-Token 应被红act"
    assert "api_key_12345" not in result, "X-Api-Key 应被红act"
    assert "eyJhbGciOiJIUzI1NiJ9" not in result, "Authorization JWT 应被红act"
    assert "application/json" in result, "Content-Type 非敏感应保留"


# --- CQR-5: Structured tool_result secret redaction ---


def test_redact_tool_result_dict_with_api_key():
    """_redact_tool_result 对 dict 类型的 tool_result 应递归红act api_key。"""
    from side.tasks.tool_summary import _redact_tool_result

    result = _redact_tool_result({
        "status": "ok",
        "api_key": "sk-proj-SECRETKEY123456789",
        "data": {"count": 42},
    })
    assert "sk-proj-SECRETKEY123456789" not in result, "api_key 值应被红act"
    assert "ok" in result, "非敏感字段应保留"
    assert "42" in result, "嵌套非敏感值应保留"


def test_redact_tool_result_dict_with_private_key():
    """_redact_tool_result 对 dict 类型的 tool_result 应递归红act private_key。"""
    from side.tasks.tool_summary import _redact_tool_result

    result = _redact_tool_result({
        "file": "id_rsa",
        "private_key": "-----BEGIN RSA PRIVATE KEY-----\nMIIE...",
        "comment": "generated key",
    })
    assert "MIIE..." not in result, "private_key 值应被红act"
    assert "id_rsa" in result, "非敏感字段应保留"


def test_redact_tool_result_dict_with_auth_token():
    """_redact_tool_result 对 dict 类型的 tool_result 应递归红act auth_token。"""
    from side.tasks.tool_summary import _redact_tool_result

    result = _redact_tool_result({
        "user": "admin",
        "auth_token": "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.abc",
        "expires": 3600,
    })
    assert "eyJhbGciOiJIUzI1NiJ9" not in result, "auth_token JWT 应被红act"
    assert "admin" in result, "非敏感字段应保留"
    assert "3600" in result, "非敏感字段应保留"


def test_redact_tool_result_nested_dict_secrets():
    """_redact_tool_result 对嵌套 dict 中的敏感键应递归红act。"""
    from side.tasks.tool_summary import _redact_tool_result

    result = _redact_tool_result({
        "config": {
            "db_password": "supersecret123",
            "host": "localhost",
        },
        "token": "tok_live_abc123",
        "status": "ok",
    })
    assert "supersecret123" not in result, "嵌套 db_password 应被红act"
    assert "tok_live_abc123" not in result, "顶层 token 应被红act"
    assert "localhost" in result, "非敏感嵌套字段应保留"
    assert "ok" in result, "非敏感顶层字段应保留"


def test_redact_tool_result_list_of_dicts():
    """_redact_tool_result 对 list[dict] 类型的 tool_result 应递归红act。"""
    from side.tasks.tool_summary import _redact_tool_result

    result = _redact_tool_result([
        {"name": "user1", "secret": "s3cret_value"},
        {"name": "user2", "api_key": "sk-abc123def456"},
    ])
    assert "s3cret_value" not in result, "list 中 dict 的 secret 应被红act"
    assert "sk-abc123def456" not in result, "list 中 dict 的 api_key 应被红act"
    assert "user1" in result, "非敏感字段应保留"
    assert "user2" in result, "非敏感字段应保留"


def test_redact_tool_result_string_still_works():
    """_redact_tool_result 对字符串类型的 tool_result 仍应正常红act。"""
    from side.tasks.tool_summary import _redact_tool_result

    result = _redact_tool_result(
        "Authorization: Bearer sk-abc123secrettoken\n"
        "X-Api-Key: my-api-key-value\n"
        "HTTP 200"
    )
    assert "sk-abc123secrettoken" not in result, "Bearer token 应被红act"
    assert "my-api-key-value" not in result, "X-Api-Key 值应被红act"
    assert "HTTP 200" in result, "非敏感内容应保留"


# --- CQR-6: URL/query param credential redaction ---


def test_redact_value_url_query_api_key():
    """URL 查询参数中的 api_key 应被红act。"""
    from side.tasks.tool_summary import _redact_value

    result = _redact_value("https://api.example.com/data?api_key=sk-secret12345&foo=bar")
    assert "sk-secret12345" not in result, "URL 中的 api_key 值应被红act"
    assert "api.example.com" in result, "非敏感 URL 部分应保留"
    assert "foo=bar" in result, "非敏感查询参数应保留"


def test_redact_value_url_query_access_token():
    """URL 查询参数中的 access_token 应被红act。"""
    from side.tasks.tool_summary import _redact_value

    result = _redact_value("https://api.example.com/callback?access_token=ya29.secretvalue&state=xyz")
    assert "ya29.secretvalue" not in result, "URL 中的 access_token 值应被红act"
    assert "state=xyz" in result, "非敏感查询参数应保留"


def test_redact_value_url_query_client_secret():
    """URL 查询参数中的 client_secret 应被红act。"""
    from side.tasks.tool_summary import _redact_value

    result = _redact_value("https://oauth.example.com/token?client_id=abc&client_secret=super_secret_val")
    assert "super_secret_val" not in result, "URL 中的 client_secret 值应被红act"
    assert "client_id=abc" in result, "client_id 非敏感应保留"


def test_redact_value_url_query_session_id():
    """URL 查询参数中的 session_id 应被红act。"""
    from side.tasks.tool_summary import _redact_value

    result = _redact_value("https://app.example.com/page?session_id=sess_abcdef123456&tab=home")
    assert "sess_abcdef123456" not in result, "URL 中的 session_id 值应被红act"
    assert "tab=home" in result, "非敏感查询参数应保留"


def test_redact_value_url_multiple_credentials():
    """URL 同时含多个凭证参数时应全部被红act。"""
    from side.tasks.tool_summary import _redact_value

    result = _redact_value("https://api.example.com?api_key=xxx&access_token=yyy&normal=ok")
    assert "xxx" not in result, "api_key 值应被红act"
    assert "yyy" not in result, "access_token 值应被红act"
    assert "normal=ok" in result, "非敏感参数应保留"


def test_redact_tool_result_url_in_dict_value():
    """tool_result dict 中 url 字段含查询参数凭证时应被红act。"""
    from side.tasks.tool_summary import _redact_tool_result

    result = _redact_tool_result({
        "url": "https://api.example.com/data?api_key=sk-secret12345&access_token=tok_live_abc",
        "status": 200,
    })
    assert "sk-secret12345" not in result, "url 中的 api_key 应被红act"
    assert "tok_live_abc" not in result, "url 中的 access_token 应被红act"
    assert "200" in result, "非敏感字段应保留"


@pytest.mark.asyncio
async def test_tool_summary_redacts_url_credentials_in_input():
    """ToolSummaryTask 将 tool_input 中 url 字段的查询参数凭证红act后再发给 LLM。"""
    from side.tasks.tool_summary import ToolSummaryTask

    task = ToolSummaryTask()
    ctx = _make_ctx(
        llm_response="Fetched data",
        config={
            "_side_task_args": {
                "tool_name": "Bash",
                "tool_input": {
                    "command": "curl 'https://api.example.com/data?api_key=sk-secret12345&access_token=yyy'",
                },
                "tool_result": "ok",
            },
        },
    )
    captured_messages = []

    async def capture_chat(*args, **kwargs):
        captured_messages.extend(kwargs.get("messages", args[0] if args else []))
        return ctx.llm_client.chat.return_value

    ctx.llm_client.chat = AsyncMock(side_effect=capture_chat)
    await task.execute(ctx)

    all_text = " ".join(m["content"] for m in captured_messages)
    assert "sk-secret12345" not in all_text, "URL 中的 api_key 值应被红act"
    assert "api.example.com" in all_text, "非敏感 URL 部分应保留"
