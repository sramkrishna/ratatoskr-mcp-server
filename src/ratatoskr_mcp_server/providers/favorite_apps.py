"""GNOME favorite/pinned apps provider."""

from ratatoskr_mcp_server.providers.base import ResourceProvider
from ratatoskr_mcp_server.resource_manager import ResourceData
from ratatoskr_mcp_server.utils.gsettings import gsettings_get_list
from ratatoskr_mcp_server.utils.desktop_files import get_app_names


class GnomeFavoriteAppsProvider(ResourceProvider):
    """Provides information about favorite/pinned apps in GNOME."""

    async def get_resource(self) -> ResourceData:
        """
        Get favorite apps (pinned to the dash).

        Returns:
            ResourceData with favorite apps information including:
            - favorite_apps: List of app info with id, name, and found status
            - count: Number of favorite apps
        """
        try:
            # Get favorite-apps from gsettings
            favorite_ids = gsettings_get_list('org.gnome.shell', 'favorite-apps')

            # Convert desktop IDs to human-readable names
            apps_info = get_app_names(favorite_ids)

            return ResourceData(
                content={
                    "favorite_apps": apps_info,
                    "count": len(apps_info)
                }
            )
        except Exception as e:
            return ResourceData(
                content={},
                error=f"Failed to get favorite apps: {str(e)}"
            )
