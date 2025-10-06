"""GNOME Shell D-Bus provider"""

import logging
from typing import Dict, Any
from .base import DBusProviderBase

logger = logging.getLogger(__name__)


class GnomeShellProvider(DBusProviderBase):
    """D-Bus provider for GNOME Shell"""

    def __init__(self):
        try:
            super().__init__('org.gnome.Shell', '/org/gnome/Shell')
        except Exception as e:
            logger.error(f"Failed to connect to GNOME Shell D-Bus: {e}")
            raise

    def get_shell_version(self) -> str:
        """Get GNOME Shell version"""
        try:
            return str(self.get_property('org.gnome.Shell', 'ShellVersion'))
        except Exception:
            return "Unknown"

    def get_mode(self) -> str:
        """Get GNOME Shell mode"""
        try:
            return str(self.get_property('org.gnome.Shell', 'Mode'))
        except Exception:
            return "Unknown"

    def get_overview_visible(self) -> bool:
        """Get overview visibility state"""
        try:
            return bool(self.get_property('org.gnome.Shell', 'OverviewVisible'))
        except Exception:
            return False

    def get_all_info(self) -> Dict[str, Any]:
        """Get all GNOME Shell information"""
        return {
            'version': self.get_shell_version(),
            'mode': self.get_mode(),
            'overview_visible': self.get_overview_visible()
        }
