import os
import tempfile

import pytest
from config.loader import load_config
from config.model_registry import ModelRegistry


def test_load_config_returns_dict():
    config = load_config()
    assert isinstance(config, dict)
    assert "providers" in config
    assert "models" in config


def test_model_registry_get_by_id():
    config = load_config()
    registry = ModelRegistry(config)
    default = registry.get_default_model()
    assert default is not None
    model = registry.get_model_by_id(default["id"])
    assert model is not None
    assert model["id"] == default["id"]
    assert "provider" in model


def test_model_registry_get_default():
    config = load_config()
    registry = ModelRegistry(config)
    default = registry.get_default_model()
    assert default is not None
    assert default["default"] is True


def test_model_registry_get_by_purpose():
    config = load_config()
    registry = ModelRegistry(config)
    models = registry.get_models_by_purpose("coding")
    assert len(models) > 0
    assert all("coding" in m["purpose"] for m in models)


def test_model_registry_get_fallback():
    config = load_config()
    registry = ModelRegistry(config)
    fallback = registry.get_fallback_model()
    assert fallback is not None


# --- Edge-case tests for config layer fixes ---


def test_load_config_nonexistent_path_raises():
    """load_config with a path that does not exist should raise FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        load_config(path="/tmp/does_not_exist_brix_test.yaml")


def test_load_config_empty_yaml_returns_empty_dict():
    """load_config on an empty YAML file should return {} instead of None."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write("")  # empty file
        tmp_path = f.name
    try:
        result = load_config(path=tmp_path)
        assert result == {}
    finally:
        os.unlink(tmp_path)


def test_model_registry_malformed_missing_id():
    """ModelRegistry should not crash when a model entry is missing the 'id' key."""
    config = {
        "models": [
            {"provider": "openai", "purpose": ["coding"]},  # no "id"
            {"id": "valid-model", "provider": "openai", "purpose": ["coding"]},
        ],
        "routing": {"default_model": "valid-model"},
    }
    registry = ModelRegistry(config)
    # Searching for a real model should still work
    found = registry.get_model_by_id("valid-model")
    assert found is not None
    assert found["id"] == "valid-model"
    # Searching for a missing id should not crash, just return None
    assert registry.get_model_by_id("nonexistent") is None


def test_model_registry_routing_references_missing_model():
    """When routing references a model id that does not exist, get_default/get_fallback return None."""
    config = {
        "models": [
            {"id": "only-model", "provider": "openai", "purpose": ["coding"]},
        ],
        "routing": {
            "default_model": "ghost-model",
            "fallback_model": "ghost-model",
        },
    }
    registry = ModelRegistry(config)
    assert registry.get_default_model() is None
    assert registry.get_fallback_model() is None


# --- Layered config tests ---


def test_layered_config_merge(tmp_path):
    """ConfigLoader should merge global -> project -> local layers."""
    from config.loader import ConfigLoader

    global_dir = tmp_path / "global"
    global_dir.mkdir()
    (global_dir / "config.yaml").write_text(
        "model: gpt-4\ndebug: false\nretry:\n  max_retries: 3"
    )

    project_dir = tmp_path / "project" / ".brix"
    project_dir.mkdir(parents=True)
    (project_dir / "settings.yaml").write_text(
        "model: claude-sonnet\nlogging: true"
    )

    local_dir = tmp_path / "project" / ".brix"
    (local_dir / "settings.local.yaml").write_text(
        "debug: true\napi_key: secret"
    )

    loader = ConfigLoader(
        global_path=global_dir / "config.yaml",
        project_path=project_dir / "settings.yaml",
        local_path=local_dir / "settings.local.yaml",
    )
    config = loader.load()

    # Local overrides project overrides global
    assert config["model"] == "claude-sonnet"  # project overrides global
    assert config["debug"] is True  # local overrides global
    assert config["logging"] is True  # project-only key preserved
    assert config["api_key"] == "secret"  # local-only key preserved
    assert config["retry"]["max_retries"] == 3  # global nested key preserved


def test_layered_config_missing_layers(tmp_path):
    """Missing layers should be silently skipped."""
    from config.loader import ConfigLoader

    global_dir = tmp_path / "global"
    global_dir.mkdir()
    (global_dir / "config.yaml").write_text("model: gpt-4")

    loader = ConfigLoader(
        global_path=global_dir / "config.yaml",
        project_path=tmp_path / "nonexistent" / "settings.yaml",
        local_path=tmp_path / "nonexistent" / "settings.local.yaml",
    )
    config = loader.load()
    assert config["model"] == "gpt-4"


def test_layered_config_backward_compat(tmp_path):
    """If no .brix/ dir exists, fall back to config/settings.yaml."""
    from config.loader import ConfigLoader

    # Simulate the old single-file config
    old_config = tmp_path / "config" / "settings.yaml"
    old_config.parent.mkdir(parents=True)
    old_config.write_text("model: old-model\nengine: state_machine")

    loader = ConfigLoader(
        global_path=tmp_path / "nonexistent_global.yaml",
        project_path=None,  # no .brix/settings.yaml
        local_path=None,  # no .brix/settings.local.yaml
        fallback_path=old_config,
    )
    config = loader.load()
    assert config["model"] == "old-model"


def test_layered_config_fallback_with_global(tmp_path):
    """Fallback should merge on top of global when no project path given."""
    from config.loader import ConfigLoader

    global_dir = tmp_path / "global"
    global_dir.mkdir()
    (global_dir / "config.yaml").write_text("model: gpt-4\ndebug: false")

    old_config = tmp_path / "config" / "settings.yaml"
    old_config.parent.mkdir(parents=True)
    old_config.write_text("model: old-model\nengine: state_machine")

    loader = ConfigLoader(
        global_path=global_dir / "config.yaml",
        project_path=None,  # no .brix/settings.yaml
        local_path=None,
        fallback_path=old_config,
    )
    config = loader.load()
    # Fallback should override global's model
    assert config["model"] == "old-model"
    assert config["engine"] == "state_machine"
    # Global's debug should be preserved
    assert config["debug"] is False


def test_banner_contains_model_info(capsys):
    """Banner should display model and version info."""
    from cli.banner import show_banner

    show_banner(model="test-model", version="0.1.0", cwd="/test/dir")
    captured = capsys.readouterr()
    assert "BRIX" in captured.out or "Brix" in captured.out or "brix" in captured.out.lower()
    assert "test-model" in captured.out
