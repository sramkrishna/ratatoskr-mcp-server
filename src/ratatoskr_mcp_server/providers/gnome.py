"""GNOME-specific desktop environment provider."""

import os
from ratatoskr_mcp_server.providers.base import ResourceProvider
from ratatoskr_mcp_server.resource_manager import ResourceData
from ratatoskr_mcp_server.dbus_providers.gnome_shell import GnomeShellProvider


class GnomeDesktopProvider(ResourceProvider):
    """Provides GNOME-specific desktop environment information."""

    async def get_resource(self) -> ResourceData:
        """
        Get GNOME desktop environment information.

        Returns:
            ResourceData with GNOME-specific information including:
            - desktop_environment: "GNOME"
            - gnome_shell_version: GNOME Shell version from D-Bus
            - gnome_shell_mode: Current shell mode
            - overview_visible: Whether overview is visible
            - desktop_session: Current desktop session
            - xdg_current_desktop: XDG desktop specification
            - is_gnome_session: Always True for this provider
        """
        try:
            # Get environment variables
            desktop_session = os.environ.get('DESKTOP_SESSION', '')
            xdg_current_desktop = os.environ.get('XDG_CURRENT_DESKTOP', '')

            # Get GNOME Shell info via D-Bus
            gnome_info = self._get_gnome_shell_info()

            return ResourceData(
                content={
                    "desktop_environment": "GNOME",
                    "gnome_shell_version": gnome_info.get('version', 'Unknown'),
                    "gnome_shell_mode": gnome_info.get('mode', 'Unknown'),
                    "overview_visible": gnome_info.get('overview_visible', False),
                    "desktop_session": desktop_session,
                    "xdg_current_desktop": xdg_current_desktop,
                    "is_gnome_session": True
                }
            )

        except Exception as e:
            return ResourceData(
                content={},
                error=f"Failed to get GNOME desktop info: {str(e)}"
            )

    def _get_gnome_shell_info(self) -> dict:
        """
        Get GNOME Shell information via D-Bus.

        Returns:
            Dictionary with version, mode, and overview_visible keys
        """
        try:
            shell_provider = GnomeShellProvider()
            return shell_provider.get_all_info()
        except Exception:
            return {
                'version': 'Unknown',
                'mode': 'Unknown',
                'overview_visible': False
            }
