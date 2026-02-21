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
    max_cost_per_task: Optional[float] = None
    daily_budget: Optional[float] = None
    first_run_complete: bool = False
    task_count: int = 0


class ProjectConfig(BaseModel):
    """Project-level configuration (from .mdx.yaml in repo root)."""

    preferred_backend: Optional[str] = None
    strategy: Optional[str] = None
    max_cost_per_task: Optional[float] = None
    daily_budget: Optional[float] = None


def ensure_mdx_dir() -> Path:
    """Ensure ~/.mdx/ directory exists."""
    MDX_DIR.mkdir(parents=True, exist_ok=True)
    return MDX_DIR


# Module-level cache — avoids re-parsing YAML + Pydantic on every call
_cached_config: Optional[MdxConfig] = None


def load_config(path: Optional[Path] = None) -> MdxConfig:
    """Load config from file, creating with defaults if it doesn't exist.

    Cached for the process lifetime when using the default path.
    """
    global _cached_config
    if path is None and _cached_config is not None:
        return _cached_config

    config_path = path or CONFIG_PATH

    if config_path.exists():
        raw = yaml.safe_load(config_path.read_text()) or {}
        config = MdxConfig(**raw)
    else:
        # First run — create default config
        ensure_mdx_dir()
        config = MdxConfig()
        save_config(config, config_path)

    if path is None:
        _cached_config = config
    return config


def save_config(config: MdxConfig, path: Optional[Path] = None) -> None:
    """Save config to YAML file. Also updates the cache."""
    global _cached_config
    config_path = path or CONFIG_PATH
    config_path.parent.mkdir(parents=True, exist_ok=True)
    data = config.model_dump()
    config_path.write_text(yaml.dump(data, default_flow_style=False, sort_keys=False))
    if path is None:
        _cached_config = config


def load_project_config() -> Optional[ProjectConfig]:
    """Load project-level config from .mdx.yaml in current or parent dirs."""
    cwd = Path.cwd()
    for directory in [cwd, *cwd.parents]:
        config_file = directory / ".mdx.yaml"
        if config_file.exists():
            try:
                raw = yaml.safe_load(config_file.read_text()) or {}
                return ProjectConfig(**raw)
            except Exception:
                return None
        # Stop at git root
        if (directory / ".git").exists():
            break
    return None
