"""Tests for configuration management."""

import pytest
import yaml
from pathlib import Path

from mdxcode.config import MdxConfig, load_config, save_config


@pytest.fixture
def tmp_config(tmp_path):
    """Provide a temporary config file path."""
    return tmp_path / "config.yaml"


class TestMdxConfig:
    """Tests for the MdxConfig model."""

    def test_defaults(self):
        config = MdxConfig()
        assert config.version == "2.0"
        assert config.default_backend == "auto"
        assert config.routing_strategy == "balanced"
        assert config.audit.enabled is True
        assert config.audit.chain_hashing is True
        assert config.display.show_footer is True
        assert config.display.verbose is False

    def test_valid_backends(self):
        for backend in ("auto", "claude", "codex", "gemini"):
            config = MdxConfig(default_backend=backend)
            assert config.default_backend == backend

    def test_invalid_backend_rejected(self):
        with pytest.raises(Exception):
            MdxConfig(default_backend="invalid_backend")

    def test_valid_strategies(self):
        for strategy in ("balanced", "cost_optimized", "quality_first"):
            config = MdxConfig(routing_strategy=strategy)
            assert config.routing_strategy == strategy

    def test_invalid_strategy_rejected(self):
        with pytest.raises(Exception):
            MdxConfig(routing_strategy="fastest")


class TestLoadConfig:
    """Tests for loading configuration."""

    def test_creates_default_on_first_run(self, tmp_config):
        config = load_config(tmp_config)
        assert config.default_backend == "auto"
        assert tmp_config.exists()

    def test_loads_existing_config(self, tmp_config):
        data = {
            "version": "2.0",
            "default_backend": "claude",
            "routing_strategy": "quality_first",
            "audit": {"enabled": False, "directory": "/tmp/audit", "chain_hashing": False},
            "display": {"show_footer": False, "show_routing_reason": False, "verbose": True},
        }
        tmp_config.parent.mkdir(parents=True, exist_ok=True)
        tmp_config.write_text(yaml.dump(data))

        config = load_config(tmp_config)
        assert config.default_backend == "claude"
        assert config.routing_strategy == "quality_first"
        assert config.audit.enabled is False
        assert config.display.verbose is True

    def test_partial_config_uses_defaults(self, tmp_config):
        tmp_config.parent.mkdir(parents=True, exist_ok=True)
        tmp_config.write_text(yaml.dump({"default_backend": "gemini"}))

        config = load_config(tmp_config)
        assert config.default_backend == "gemini"
        assert config.audit.enabled is True  # default
        assert config.display.show_footer is True  # default


class TestSaveConfig:
    """Tests for saving configuration."""

    def test_roundtrip(self, tmp_config):
        original = MdxConfig(default_backend="claude", routing_strategy="cost_optimized")
        save_config(original, tmp_config)

        loaded = load_config(tmp_config)
        assert loaded.default_backend == "claude"
        assert loaded.routing_strategy == "cost_optimized"

    def test_creates_parent_dirs(self, tmp_path):
        nested_path = tmp_path / "a" / "b" / "config.yaml"
        config = MdxConfig()
        save_config(config, nested_path)
        assert nested_path.exists()
