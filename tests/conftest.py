import pytest
from config.loader import load_config


@pytest.fixture
def config():
    return load_config()
