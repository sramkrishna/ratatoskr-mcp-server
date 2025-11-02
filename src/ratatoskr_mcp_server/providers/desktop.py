"""Generic desktop environment detection and information provider."""

import os
from ratatoskr_mcp_server.providers.base import ResourceProvider
from ratatoskr_mcp_server.resource_manager import ResourceData


class DesktopEnvironmentProvider(ResourceProvider):
    """
    Detects and provides information about the current desktop environment.

    This is a generic provider that detects which DE is running and
    provides basic information. For DE-specific details, use the
    specific providers (GnomeDesktopProvider, etc.).
    """

    async def get_resource(self) -> ResourceData:
        """
        Detect and return basic desktop environment information.

        Returns:
            ResourceData with generic desktop information including:
            - desktop_environment: Name of detected DE
            - desktop_session: DESKTOP_SESSION environment variable
            - xdg_current_desktop: XDG_CURRENT_DESKTOP environment variable
            - xdg_session_type: Session type (wayland, x11, etc.)
        """
        try:
            desktop_session = os.environ.get('DESKTOP_SESSION', '')
            xdg_current_desktop = os.environ.get('XDG_CURRENT_DESKTOP', '')
            xdg_session_type = os.environ.get('XDG_SESSION_TYPE', '')

            # Detect desktop environment
            detected_de = self._detect_desktop_environment(
                desktop_session,
                xdg_current_desktop
            )

            return ResourceData(
                content={
                    "desktop_environment": detected_de,
                    "desktop_session": desktop_session,
                    "xdg_current_desktop": xdg_current_desktop,
                    "xdg_session_type": xdg_session_type,
                }
            )

        except Exception as e:
            return ResourceData(
                content={},
                error=f"Failed to detect desktop environment: {str(e)}"
            )

    def _detect_desktop_environment(
        self,
        desktop_session: str,
        xdg_current_desktop: str
    ) -> str:
        """
        Detect desktop environment from environment variables.

        Args:
            desktop_session: DESKTOP_SESSION value
            xdg_current_desktop: XDG_CURRENT_DESKTOP value

        Returns:
            Detected desktop environment name
        """
        # Check XDG_CURRENT_DESKTOP first (more reliable)
        xdg_lower = xdg_current_desktop.lower()
        session_lower = desktop_session.lower()

        # GNOME
        if 'gnome' in xdg_lower or 'gnome' in session_lower:
            return 'GNOME'
        if 'ubuntu' in xdg_lower:  # Ubuntu uses GNOME
            return 'GNOME'

        # KDE Plasma
        if 'kde' in xdg_lower or 'plasma' in session_lower:
            return 'KDE'

        # XFCE
        if 'xfce' in xdg_lower or 'xfce' in session_lower:
            return 'XFCE'

        # Cinnamon
        if 'cinnamon' in xdg_lower or 'cinnamon' in session_lower:
            return 'Cinnamon'

        # MATE
        if 'mate' in xdg_lower or 'mate' in session_lower:
            return 'MATE'

        # Budgie
        if 'budgie' in xdg_lower or 'budgie' in session_lower:
            return 'Budgie'

        # Fallback
        if xdg_current_desktop:
            return xdg_current_desktop
        if desktop_session:
            return desktop_session

        return 'Unknown'
