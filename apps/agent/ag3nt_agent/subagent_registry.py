"""Dynamic subagent registry for AG3NT.

This module provides a registry-based approach to subagent management, enabling:
- Runtime registration/unregistration of subagents
- Plugin-based subagent addition
- User-defined subagents via YAML/JSON config files
- Persistence to ~/.ag3nt/subagents/
- Event callbacks for UI updates

This replaces the static SUBAGENT_REGISTRY with a dynamic, extensible system.
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Literal

import yaml

if TYPE_CHECKING:
    from ag3nt_agent.subagent_configs import SubagentConfig

logger = logging.getLogger(__name__)

# Source types for subagent registration
SubagentSource = Literal["builtin", "plugin", "user"]


class SubagentRegistry:
    """Dynamic registry for subagent configurations.

    This is a singleton class that manages all subagent configurations.
    Subagents can come from three sources:
    - builtin: The 8 predefined subagents (RESEARCHER, CODER, etc.)
    - plugin: Subagents registered by plugins
    - user: Custom subagents defined by the user

    Thread-safe for concurrent access.
    """

    _instance: SubagentRegistry | None = None
    _lock = threading.Lock()

    def __new__(cls) -> SubagentRegistry:
        """Ensure only one instance exists (singleton pattern)."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        """Initialize the registry (only runs once due to singleton)."""
        if getattr(self, "_initialized", False):
            return

        self._registry: dict[str, tuple[SubagentConfig, SubagentSource]] = {}
        self._callbacks: list[Callable[[str, str, SubagentSource], None]] = []
        self._registry_lock = threading.RLock()
        self._initialized = True

        # Load builtin subagents
        self._load_builtins()

        logger.info("SubagentRegistry initialized with %d builtin subagents",
                    len(self.list_by_source("builtin")))

    @classmethod
    def get_instance(cls) -> SubagentRegistry:
        """Get the singleton instance.

        Returns:
            The SubagentRegistry singleton instance.
        """
        return cls()

    @classmethod
    def reset_instance(cls) -> None:
        """Reset the singleton instance (for testing only)."""
        with cls._lock:
            cls._instance = None

    def _load_builtins(self) -> None:
        """Load the 8 builtin subagent configurations."""
        from ag3nt_agent.subagent_configs import BUILTIN_SUBAGENTS

        for name, config in BUILTIN_SUBAGENTS.items():
            self._registry[name] = (config, "builtin")

    def register(
        self,
        config: SubagentConfig,
        source: SubagentSource = "user",
        overwrite: bool = False,
    ) -> bool:
        """Register a subagent configuration.

        Args:
            config: The SubagentConfig to register.
            source: Where this subagent comes from (builtin, plugin, user).
            overwrite: If True, overwrite existing subagent with same name.

        Returns:
            True if registered successfully, False if name exists and overwrite=False.
        """
        with self._registry_lock:
            name = config.name.lower()

            if name in self._registry and not overwrite:
                logger.warning("Subagent '%s' already exists, use overwrite=True to replace", name)
                return False

            existing_source = self._registry.get(name, (None, None))[1]
            if existing_source == "builtin" and source != "builtin":
                logger.warning("Cannot overwrite builtin subagent '%s'", name)
                return False

            self._registry[name] = (config, source)
            logger.info("Registered subagent '%s' from source '%s'", name, source)

            # Notify callbacks
            self._notify_callbacks("register", name, source)
            return True

    def unregister(self, name: str) -> bool:
        """Unregister a subagent by name.

        Note: Builtin subagents cannot be unregistered.

        Args:
            name: The subagent name to unregister.

        Returns:
            True if unregistered, False if not found or is builtin.
        """
        with self._registry_lock:
            name = name.lower()

            if name not in self._registry:
                logger.warning("Subagent '%s' not found", name)
                return False

            config, source = self._registry[name]
            if source == "builtin":
                logger.warning("Cannot unregister builtin subagent '%s'", name)
                return False

            del self._registry[name]
            logger.info("Unregistered subagent '%s'", name)

            # Notify callbacks
            self._notify_callbacks("unregister", name, source)
            return True

    def get(self, name: str) -> SubagentConfig | None:
        """Get a subagent configuration by name.

        Args:
            name: The subagent name to retrieve.

        Returns:
            The SubagentConfig if found, None otherwise.
        """
        with self._registry_lock:
            name = name.lower()
            entry = self._registry.get(name)
            return entry[0] if entry else None

    def get_with_source(self, name: str) -> tuple[SubagentConfig, SubagentSource] | None:
        """Get a subagent configuration and its source.

        Args:
            name: The subagent name to retrieve.

        Returns:
            Tuple of (config, source) if found, None otherwise.
        """
        with self._registry_lock:
            name = name.lower()
            return self._registry.get(name)

    def get_source(self, name: str) -> SubagentSource | None:
        """Get the source of a subagent.

        Args:
            name: The subagent name to look up.

        Returns:
            The source (builtin, plugin, user) if found, None otherwise.
        """
        with self._registry_lock:
            entry = self._registry.get(name.lower())
            return entry[1] if entry else None

    def list_all(self) -> list[SubagentConfig]:
        """List all registered subagents.

        Returns:
            List of all SubagentConfig instances.
        """
        with self._registry_lock:
            return [config for config, _ in self._registry.values()]

    def list_by_source(self, source: SubagentSource) -> list[SubagentConfig]:
        """List subagents from a specific source.

        Args:
            source: The source to filter by (builtin, plugin, user).

        Returns:
            List of SubagentConfig instances from that source.
        """
        with self._registry_lock:
            return [config for config, src in self._registry.values() if src == source]

    def list_names(self) -> list[str]:
        """List all registered subagent names.

        Returns:
            List of subagent names.
        """
        with self._registry_lock:
            return list(self._registry.keys())

    def on_change(self, callback: Callable[[str, str, SubagentSource], None]) -> None:
        """Register a callback for registry changes.

        The callback receives (event_type, subagent_name, source) where:
        - event_type: "register" or "unregister"
        - subagent_name: The name of the affected subagent
        - source: The source of the subagent

        Args:
            callback: Function to call on registry changes.
        """
        self._callbacks.append(callback)
        logger.debug("Registered change callback, total: %d", len(self._callbacks))

    def remove_callback(self, callback: Callable[[str, str, SubagentSource], None]) -> bool:
        """Remove a previously registered callback.

        Args:
            callback: The callback to remove.

        Returns:
            True if removed, False if not found.
        """
        try:
            self._callbacks.remove(callback)
            return True
        except ValueError:
            return False

    def _notify_callbacks(self, event_type: str, name: str, source: SubagentSource) -> None:
        """Notify all registered callbacks of a change.

        Args:
            event_type: The type of event (register, unregister).
            name: The subagent name.
            source: The subagent source.
        """
        for callback in self._callbacks:
            try:
                callback(event_type, name, source)
            except Exception as e:
                logger.error("Callback error: %s", e)

    def load_from_file(self, path: Path, source: SubagentSource = "user") -> int:
        """Load subagent configs from a YAML or JSON file.

        The file should contain a list of subagent configurations or a dict
        mapping names to configurations.

        Args:
            path: Path to the YAML/JSON file.
            source: Source to assign to loaded subagents.

        Returns:
            Number of subagents loaded.
        """
        from ag3nt_agent.subagent_configs import SubagentConfig

        if not path.exists():
            logger.warning("Config file not found: %s", path)
            return 0

        try:
            with open(path, "r", encoding="utf-8") as f:
                if path.suffix.lower() in (".yaml", ".yml"):
                    data = yaml.safe_load(f)
                else:
                    data = json.load(f)
        except Exception as e:
            logger.error("Failed to load config file %s: %s", path, e)
            return 0

        loaded = 0
        configs = data if isinstance(data, list) else data.get("subagents", [])

        for item in configs:
            try:
                config = SubagentConfig(**item)
                if self.register(config, source=source):
                    loaded += 1
            except Exception as e:
                logger.error("Failed to parse subagent config: %s", e)

        logger.info("Loaded %d subagents from %s", loaded, path)
        return loaded

    def save_to_file(self, path: Path, source: SubagentSource = "user") -> int:
        """Save subagents from a specific source to a YAML file.

        Args:
            path: Path to save the YAML file.
            source: Source to filter by (only save subagents from this source).

        Returns:
            Number of subagents saved.
        """
        from dataclasses import asdict

        configs = self.list_by_source(source)
        if not configs:
            logger.info("No subagents to save for source '%s'", source)
            return 0

        # Convert to dicts for serialization
        data = {"subagents": [asdict(c) for c in configs]}

        # Ensure parent directory exists
        path.parent.mkdir(parents=True, exist_ok=True)

        try:
            with open(path, "w", encoding="utf-8") as f:
                yaml.dump(data, f, default_flow_style=False, sort_keys=False)
            logger.info("Saved %d subagents to %s", len(configs), path)
            return len(configs)
        except Exception as e:
            logger.error("Failed to save config file %s: %s", path, e)
            return 0

    def save_single_config(self, config: SubagentConfig, user_data_path: Path) -> bool:
        """Save a single subagent config to a YAML file.

        Saves to ~/.ag3nt/subagents/{name}.yaml

        Args:
            config: The subagent configuration to save.
            user_data_path: The user data directory path (e.g., ~/.ag3nt).

        Returns:
            True if saved successfully, False otherwise.
        """
        from dataclasses import asdict

        subagents_dir = user_data_path / "subagents"
        subagents_dir.mkdir(parents=True, exist_ok=True)

        file_path = subagents_dir / f"{config.name.lower()}.yaml"

        try:
            import yaml
            data = {"subagents": [asdict(config)]}
            with open(file_path, "w", encoding="utf-8") as f:
                yaml.dump(data, default_flow_style=False, sort_keys=False, stream=f)
            logger.info("Saved subagent config to %s", file_path)
            return True
        except Exception as e:
            logger.error("Failed to save config file %s: %s", file_path, e)
            return False

    def load_user_configs(self, user_data_path: Path | None = None) -> int:
        """Load user-defined subagents from the default location.

        Loads from ~/.ag3nt/subagents/*.yaml and *.json files.

        Args:
            user_data_path: Override the user data directory path.

        Returns:
            Total number of subagents loaded.
        """
        if user_data_path is None:
            user_data_path = Path.home() / ".ag3nt"

        subagents_dir = user_data_path / "subagents"
        if not subagents_dir.exists():
            subagents_dir.mkdir(parents=True, exist_ok=True)
            return 0

        loaded = 0
        for pattern in ("*.yaml", "*.yml", "*.json"):
            for config_file in subagents_dir.glob(pattern):
                loaded += self.load_from_file(config_file, source="user")

        return loaded

    def to_dict(self) -> dict[str, dict]:
        """Export registry as a dictionary for API responses.

        Returns:
            Dict mapping names to {config: ..., source: ...}.
        """
        from dataclasses import asdict

        with self._registry_lock:
            return {
                name: {
                    "config": asdict(config),
                    "source": source,
                }
                for name, (config, source) in self._registry.items()
            }


# Convenience functions for backward compatibility
def get_subagent_config(name: str) -> SubagentConfig:
    """Get a subagent configuration by name.

    This is a convenience function for backward compatibility.
    Prefer using SubagentRegistry.get_instance().get() directly.

    Args:
        name: The subagent type name.

    Returns:
        The SubagentConfig for the requested type.

    Raises:
        ValueError: If the subagent type is not found.
    """
    config = SubagentRegistry.get_instance().get(name)
    if config is None:
        available = SubagentRegistry.get_instance().list_names()
        raise ValueError(f"Unknown subagent: {name}. Available: {available}")
    return config


def list_subagent_types() -> list[str]:
    """List all available subagent types.

    This is a convenience function for backward compatibility.
    Prefer using SubagentRegistry.get_instance().list_names() directly.

    Returns:
        List of subagent type names.
    """
    return SubagentRegistry.get_instance().list_names()
