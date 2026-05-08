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


class TestPrefixCollisionSecurity:
    """前缀碰撞攻击回归测试。

    验证 allowed_root 为 /X/memory/data 时，路径
    ../data-evil/file  (解析为 /X/memory/data-evil/file)
    不会因为 startswith('/X/memory/data') 而绕过沙箱。
    """

    @pytest.mark.asyncio
    async def test_write_rejects_prefix_collision(self, tmp_path):
        """FileWriteTool 必须拒绝写入前缀碰撞的兄弟目录。"""
        from capability.tools.file_write import FileWriteTool

        allowed = tmp_path / "memory" / "data"
        allowed.mkdir(parents=True)
        evil = tmp_path / "memory" / "data-evil"
        evil.mkdir(parents=True)

        tool = FileWriteTool(allowed_root=allowed)
        result = await tool.execute(path="../data-evil/hack.txt", content="pwned")

        assert "error" in result.lower() or "拒绝" in result or "denied" in result.lower()
        assert not (evil / "hack.txt").exists(), "不应在沙箱外创建文件"

    @pytest.mark.asyncio
    async def test_edit_rejects_prefix_collision(self, tmp_path):
        """FileEditTool 必须拒绝编辑前缀碰撞的兄弟目录中的文件。"""
        from capability.tools.file_write import FileWriteTool
        from capability.tools.file_edit import FileEditTool

        allowed = tmp_path / "memory" / "data"
        allowed.mkdir(parents=True)
        evil = tmp_path / "memory" / "data-evil"
        evil.mkdir(parents=True)
        (evil / "existing.txt").write_text("original")

        writer = FileWriteTool(allowed_root=allowed)
        editor = FileEditTool(allowed_root=allowed)
        result = await editor.execute(
            path="../data-evil/existing.txt", old_text="original", new_text="pwned"
        )

        assert "error" in result.lower() or "拒绝" in result or "denied" in result.lower()
        assert (evil / "existing.txt").read_text() == "original", "不应修改沙箱外的文件"
