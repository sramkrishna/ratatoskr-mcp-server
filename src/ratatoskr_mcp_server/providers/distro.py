"""Distribution information resource provider."""

from ratatoskr_mcp_server.providers.base import ResourceProvider
from ratatoskr_mcp_server.resource_manager import ResourceData


class DistroInfoProvider(ResourceProvider):
    """Provides Linux distribution information from /etc/os-release."""

    async def get_resource(self) -> ResourceData:
        """
        Get Linux distribution information.

        Returns:
            ResourceData with distribution information including:
            - name: Distribution name
            - version: Distribution version
            - version_id: Distribution version ID
            - pretty_name: Pretty formatted distribution name
            - id: Distribution ID
            - build_id: Distribution build ID (if available)
        """
        try:
            with open('/etc/os-release', 'r') as f:
                os_info = {}
                for line in f:
                    line = line.strip()
                    if '=' in line and not line.startswith('#'):
                        key, value = line.split('=', 1)
                        os_info[key] = value.strip('"')

                return ResourceData(
                    content={
                        "name": os_info.get('NAME', 'Unknown'),
                        "version": os_info.get('VERSION', 'Unknown'),
                        "version_id": os_info.get('VERSION_ID', 'Unknown'),
                        "pretty_name": os_info.get('PRETTY_NAME', 'Unknown'),
                        "id": os_info.get('ID', 'Unknown'),
                        "build_id": os_info.get('BUILD_ID', 'Unknown')
                    }
                )
        except FileNotFoundError:
            return ResourceData(
                content={},
                error="/etc/os-release not found"
            )
        except Exception as e:
            return ResourceData(
                content={},
                error=f"Failed to read OS info: {str(e)}"
            )
