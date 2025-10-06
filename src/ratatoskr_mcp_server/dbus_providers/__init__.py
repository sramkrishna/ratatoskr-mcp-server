"""DBus providers for querying system services"""

from .base import DBusProviderBase
from .gnome_shell import GnomeShellProvider

__all__ = ["DBusProviderBase", "GnomeShellProvider"]
