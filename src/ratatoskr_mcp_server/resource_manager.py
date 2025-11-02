"""Resource management infrastructure for Ratatoskr MCP server."""

import json
from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class ResourceData:
    """Container for resource data and metadata."""
    content: Dict[str, Any]
    mime_type: str = "application/json"
    encoding: str = "utf-8"
    error: Optional[str] = None

    @property
    def is_error(self) -> bool:
        """Check if this resource contains an error."""
        return self.error is not None


class ResourceSerializer:
    """Converts ResourceData objects to wire format."""

    @staticmethod
    def to_json(resource_data: ResourceData) -> str:
        """
        Convert ResourceData to JSON string.

        Args:
            resource_data: Resource data to serialize

        Returns:
            JSON string representation
        """
        if resource_data.is_error:
            return json.dumps({"error": resource_data.error}, indent=2)

        return json.dumps(resource_data.content, indent=2)

    @staticmethod
    def to_dict(resource_data: ResourceData) -> Dict[str, Any]:
        """
        Convert ResourceData to dictionary.

        Args:
            resource_data: Resource data to convert

        Returns:
            Dictionary representation
        """
        if resource_data.is_error:
            return {"error": resource_data.error}

        return resource_data.content


class ResourceManager:
    """Manages URI to resource provider mapping."""

    def __init__(self, providers: Optional[Dict[str, Any]] = None):
        """
        Initialize resource manager.

        Args:
            providers: Dictionary mapping URIs to ResourceProvider instances
        """
        self._providers: Dict[str, Any] = providers or {}

    def register(self, uri: str, provider: Any) -> None:
        """
        Register a resource provider.

        Args:
            uri: Resource URI
            provider: ResourceProvider instance
        """
        self._providers[uri] = provider

    async def get_resource(self, uri: str) -> ResourceData:
        """
        Get resource data for the given URI.

        Args:
            uri: Resource URI to fetch

        Returns:
            ResourceData with content or error
        """
        provider = self._providers.get(uri)
        if not provider:
            return ResourceData(
                content={},
                error=f"Unknown resource: {uri}"
            )

        return await provider.get_resource()

    def list_uris(self) -> list[str]:
        """
        List all available resource URIs.

        Returns:
            List of registered URIs
        """
        return list(self._providers.keys())
