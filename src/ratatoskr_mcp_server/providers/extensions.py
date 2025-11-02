"""GNOME Extensions resource provider."""

from ratatoskr_mcp_server.providers.base import ResourceProvider
from ratatoskr_mcp_server.resource_manager import ResourceData
from ratatoskr_mcp_server.utils.gsettings import gsettings_get_list


class GnomeExtensionsProvider(ResourceProvider):
    """Fetch information about installed GNOME extensions."""

    async def get_resource(self) -> ResourceData:
        """
        Get information about GNOME Shell extensions.

        Returns:
            ResourceData with extension information including:
            - enabled_extensions: List of enabled extension UUIDs
            - disabled_extensions: List of disabled extension UUIDs
            - all_installed_extensions: Combined list of all extensions
            - enabled_extensions_count: Number of enabled extensions
            - disabled_extensions_count: Number of disabled extensions
            - total_installed_extensions: Total number of extensions
        """
        try:
            # Query gsettings for extension lists
            enabled_extensions = gsettings_get_list('org.gnome.shell', 'enabled-extensions')
            disabled_extensions = gsettings_get_list('org.gnome.shell', 'disabled-extensions')

            # Calculate counts
            num_enabled = len(enabled_extensions)
            num_disabled = len(disabled_extensions)
            num_total = num_enabled + num_disabled

            # Combine all extensions
            all_extensions = enabled_extensions + disabled_extensions

            return ResourceData(
                content={
                    "enabled_extensions": enabled_extensions,
                    "disabled_extensions": disabled_extensions,
                    "all_installed_extensions": all_extensions,
                    "enabled_extensions_count": num_enabled,
                    "disabled_extensions_count": num_disabled,
                    "total_installed_extensions": num_total,
                }
            )
        except Exception as e:
            return ResourceData(
                content={},
                error=f"Failed to get extensions: {str(e)}"
            )
