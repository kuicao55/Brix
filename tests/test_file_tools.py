"""FileWriteTool 和 FileEditTool 测试。"""
import pytest
from pathlib import Path


class TestFileWriteTool:
    """FileWriteTool 安全性和功能测试。"""

    @pytest.mark.asyncio
    async def test_write_creates_file(self, tmp_path):
        from capability.tools.file_write import FileWriteTool
        tool = FileWriteTool(allowed_root=tmp_path)
        result = await tool.execute(path="test.md", content="# Hello")
        assert "success" in result.lower() or "写入" in result
        assert (tmp_path / "test.md").read_text() == "# Hello"

    @pytest.mark.asyncio
    async def test_write_rejects_path_traversal(self, tmp_path):
        from capability.tools.file_write import FileWriteTool
        tool = FileWriteTool(allowed_root=tmp_path)
        result = await tool.execute(path="../escape.txt", content="bad")
        assert "error" in result.lower() or "拒绝" in result or "denied" in result.lower()
        assert not (tmp_path.parent / "escape.txt").exists()

    @pytest.mark.asyncio
    async def test_write_rejects_absolute_path(self, tmp_path):
        from capability.tools.file_write import FileWriteTool
        tool = FileWriteTool(allowed_root=tmp_path)
        result = await tool.execute(path="/etc/passwd", content="bad")
        assert "error" in result.lower() or "拒绝" in result or "denied" in result.lower()

    @pytest.mark.asyncio
    async def test_write_creates_parent_dirs(self, tmp_path):
        from capability.tools.file_write import FileWriteTool
        tool = FileWriteTool(allowed_root=tmp_path)
        result = await tool.execute(path="sub/dir/file.md", content="nested")
        assert (tmp_path / "sub" / "dir" / "file.md").read_text() == "nested"

    @pytest.mark.asyncio
    async def test_write_overwrites_existing(self, tmp_path):
        from capability.tools.file_write import FileWriteTool
        tool = FileWriteTool(allowed_root=tmp_path)
        await tool.execute(path="file.md", content="v1")
        await tool.execute(path="file.md", content="v2")
        assert (tmp_path / "file.md").read_text() == "v2"


class TestFileEditTool:
    """FileEditTool 安全性和功能测试。"""

    @pytest.mark.asyncio
    async def test_edit_replaces_text(self, tmp_path):
        from capability.tools.file_write import FileWriteTool
        from capability.tools.file_edit import FileEditTool
        writer = FileWriteTool(allowed_root=tmp_path)
        editor = FileEditTool(allowed_root=tmp_path)
        await writer.execute(path="user.md", content="Name: Alice\nRole: Dev")
        result = await editor.execute(
            path="user.md", old_text="Alice", new_text="Bob"
        )
        assert (tmp_path / "user.md").read_text() == "Name: Bob\nRole: Dev"

    @pytest.mark.asyncio
    async def test_edit_rejects_path_traversal(self, tmp_path):
        from capability.tools.file_edit import FileEditTool
        editor = FileEditTool(allowed_root=tmp_path)
        result = await editor.execute(path="../escape.txt", old_text="a", new_text="b")
        assert "error" in result.lower() or "拒绝" in result or "denied" in result.lower()

    @pytest.mark.asyncio
    async def test_edit_fails_when_old_text_not_found(self, tmp_path):
        from capability.tools.file_write import FileWriteTool
        from capability.tools.file_edit import FileEditTool
        writer = FileWriteTool(allowed_root=tmp_path)
        editor = FileEditTool(allowed_root=tmp_path)
        await writer.execute(path="file.md", content="hello world")
        result = await editor.execute(path="file.md", old_text="NOTFOUND", new_text="x")
        assert "error" in result.lower() or "not found" in result.lower() or "未找到" in result

    @pytest.mark.asyncio
    async def test_edit_fails_when_multiple_matches(self, tmp_path):
        from capability.tools.file_write import FileWriteTool
        from capability.tools.file_edit import FileEditTool
        writer = FileWriteTool(allowed_root=tmp_path)
        editor = FileEditTool(allowed_root=tmp_path)
        await writer.execute(path="file.md", content="foo bar foo")
        result = await editor.execute(path="file.md", old_text="foo", new_text="baz")
        assert "error" in result.lower() or "multiple" in result.lower() or "多个" in result

    @pytest.mark.asyncio
    async def test_edit_file_not_found(self, tmp_path):
        from capability.tools.file_edit import FileEditTool
        editor = FileEditTool(allowed_root=tmp_path)
        result = await editor.execute(path="nonexistent.md", old_text="a", new_text="b")
        assert "error" in result.lower() or "not found" in result.lower() or "不存在" in result
