"""Base class for resource providers."""

from abc import ABC, abstractmethod
from ratatoskr_mcp_server.resource_manager import ResourceData


class ResourceProvider(ABC):
    """Abstract base class for resource providers."""

    @abstractmethod
    async def get_resource(self) -> ResourceData:
        """
        Fetch and return resource data.

        Returns:
            ResourceData containing the resource content or error
        """
        pass
