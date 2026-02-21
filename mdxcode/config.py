"""Configuration management for MDx Code."""

from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field


MDX_DIR = Path.home() / ".mdx"
CONFIG_PATH = MDX_DIR / "config.yaml"

DEFAULT_CONFIG = {
    "version": "2.0",
    "default_backend": "auto",
    "routing_strategy": "balanced",
    "audit": {
        "enabled": True,
        "directory": str(MDX_DIR / "audit"),
        "chain_hashing": True,
    },
    "display": {
        "show_footer": True,
        "show_routing_reason": True,
        "verbose": False,
    },
}


class AuditConfig(BaseModel):
    """Audit trail configuration."""

    enabled: bool = True
    directory: str = str(MDX_DIR / "audit")
    chain_hashing: bool = True


class DisplayConfig(BaseModel):
    """Display configuration."""

    show_footer: bool = True
    show_routing_reason: bool = True
    verbose: bool = False
    sound: bool = True  # Terminal bell on task completion


class MdxConfig(BaseModel):
    """Top-level MDx Code configuration."""

    version: str = "2.0"
    default_backend: str = Field(
        default="auto", pattern=r"^(auto|claude|codex|gemini|opencode)$"
    )
    routing_strategy: str = Field(
        default="balanced", pattern=r"^(balanced|cost_optimized|quality_first)$"
    )
    audit: AuditConfig = Field(default_factory=AuditConfig)
    display: DisplayConfig = Field(default_factory=DisplayConfig)


def ensure_mdx_dir() -> Path:
    """Ensure ~/.mdx/ directory exists."""
    MDX_DIR.mkdir(parents=True, exist_ok=True)
    return MDX_DIR


def load_config(path: Optional[Path] = None) -> MdxConfig:
    """Load config from file, creating with defaults if it doesn't exist."""
    config_path = path or CONFIG_PATH

    if config_path.exists():
        raw = yaml.safe_load(config_path.read_text()) or {}
        return MdxConfig(**raw)

    # First run — create default config
    ensure_mdx_dir()
    config = MdxConfig()
    save_config(config, config_path)
    return config


def save_config(config: MdxConfig, path: Optional[Path] = None) -> None:
    """Save config to YAML file."""
    config_path = path or CONFIG_PATH
    config_path.parent.mkdir(parents=True, exist_ok=True)
    data = config.model_dump()
    config_path.write_text(yaml.dump(data, default_flow_style=False, sort_keys=False))
