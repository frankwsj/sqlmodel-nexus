"""Multi-application manager for MCP support."""

from __future__ import annotations

from typing import TYPE_CHECKING

from nexusx.handler import GraphQLHandler
from nexusx.mcp.builders.type_tracer import TypeTracer
from nexusx.mcp.managers.app_resources import AppResources
from nexusx.mcp.types.app_config import AppConfig

if TYPE_CHECKING:
    pass


class MultiAppManager:
    """Manages multiple GraphQL applications in a single MCP server.

    This class is responsible for:
    - Initializing and storing resources for each application
    - Routing tool calls to the correct application
    - Providing app discovery functionality
    """

    def __init__(self, apps: list[AppConfig]):
        """Initialize the multi-app manager.

        Args:
            apps: List of application configurations

        Example:
            ```python
            apps = [
                {"name": "blog", "base": BlogBaseEntity, "description": "Blog API"},
                {"name": "shop", "base": ShopBaseEntity, "description": "Shop API"}
            ]
            manager = MultiAppManager(apps)
            ```
        """
        validated_apps = self._validate_apps(apps)
        self.apps: dict[str, AppResources] = {}
        self.aliases: dict[str, str] = {}

        for app_config in validated_apps:
            resources = self._create_app_resources(app_config)
            app_name = app_config["name"]
            self.apps[app_name] = resources
            for alias in app_config.get("aliases", []):
                self.aliases[alias] = app_name

    @staticmethod
    def _validate_apps(apps: list[AppConfig]) -> list[AppConfig]:
        """Validate app configs and normalize aliases."""
        if not apps:
            raise ValueError("At least one app configuration is required")

        seen_names: set[str] = set()
        seen_aliases: set[str] = set()
        validated_apps: list[AppConfig] = []

        for index, app_config in enumerate(apps):
            if "name" not in app_config or not app_config["name"]:
                raise ValueError(f"App config at index {index} is missing required field 'name'")
            if "base" not in app_config or app_config["base"] is None:
                app_label = app_config.get("name", f"index {index}")
                raise ValueError(
                    f"App '{app_label}' is missing required field 'base'"
                )

            app_name = app_config["name"]
            if app_name in seen_names:
                raise ValueError(f"Duplicate app name '{app_name}' is not allowed")
            seen_names.add(app_name)

            aliases = app_config.get("aliases", [])
            if aliases is None:
                aliases = []
            if not isinstance(aliases, list):
                raise ValueError(f"App '{app_name}' aliases must be a list of strings")

            normalized_aliases: list[str] = []
            for alias in aliases:
                if not isinstance(alias, str) or not alias:
                    raise ValueError(
                        f"App '{app_name}' aliases must contain only non-empty strings"
                    )
                if alias == app_name:
                    raise ValueError(f"App '{app_name}' alias '{alias}' duplicates its name")
                if alias in seen_names or alias in seen_aliases:
                    raise ValueError(f"Alias '{alias}' is already used by another app")
                seen_aliases.add(alias)
                normalized_aliases.append(alias)

            validated_app: AppConfig = dict(app_config)
            validated_app["aliases"] = normalized_aliases
            validated_apps.append(validated_app)

        return validated_apps


    def _create_app_resources(self, config: AppConfig) -> AppResources:
        """Create resources for a single application.

        Args:
            config: Application configuration

        Returns:
            AppResources instance with handler, tracer, and SDL generator
        """
        # Create GraphQL handler for this app
        handler = GraphQLHandler(
            base=config["base"],
            session_factory=config.get("session_factory"),
            query_description=config.get("query_description"),
            mutation_description=config.get("mutation_description"),
        )

        # Create type tracer for progressive disclosure
        introspection_data = handler.get_introspection_data()
        entity_names = {e.__name__ for e in handler.entities}
        tracer = TypeTracer(introspection_data, entity_names)

        # Create AppResources container
        return AppResources(
            name=config["name"],
            description=config.get("description", ""),
            handler=handler,
            tracer=tracer,
            sdl_generator=handler.get_sdl_generator(),
        )

    def get_app(self, name: str) -> AppResources:
        """Get resources for a specific application.

        Args:
            name: Application name (required)

        Returns:
            AppResources for the specified application

        Raises:
            ValueError: If application name is not found

        Example:
            ```python
            app = manager.get_app("blog")
            queries = app.tracer.list_operation_fields("Query")
            ```
        """
        if name in self.apps:
            return self.apps[name]

        if name in self.aliases:
            return self.apps[self.aliases[name]]

        available = list(self.apps.keys())
        if self.aliases:
            available += [f"alias:{alias}" for alias in self.aliases]
        raise ValueError(
            f"App '{name}' not found. Available apps: {available}"
        )

    def list_apps(self) -> list[str]:
        """List all available application names.

        Returns:
            List of application names

        Example:
            ```python
            app_names = manager.list_apps()
            # ["blog", "shop"]
            ```
        """
        return list(self.apps.keys())
