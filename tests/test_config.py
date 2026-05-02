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
    model = registry.get_model_by_id("gpt-4.1-mini")
    assert model is not None
    assert model["id"] == "gpt-4.1-mini"
    assert model["provider"] == "openai"


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
