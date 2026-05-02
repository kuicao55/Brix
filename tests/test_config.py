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
