"""Resource providers for Ratatoskr MCP server."""

from .base import ResourceProvider
from .desktop import DesktopEnvironmentProvider
from .gnome import GnomeDesktopProvider
from .extensions import GnomeExtensionsProvider
from .favorite_apps import GnomeFavoriteAppsProvider
from .keybindings import GnomeKeybindingsProvider
from .distro import DistroInfoProvider
from .app_stats import AppLaunchStatsProvider
from .project_files import ProjectFilesProvider
from .file_stats import FileStatisticsProvider
from .file_search import FileSearchProvider
from .document_content import DocumentContentProvider
from .image_analyzer import ImageAnalyzerProvider
from .face_manager import FaceManagerProvider

__all__ = [
    "ResourceProvider",
    "DesktopEnvironmentProvider",
    "GnomeDesktopProvider",
    "GnomeExtensionsProvider",
    "GnomeFavoriteAppsProvider",
    "GnomeKeybindingsProvider",
    "DistroInfoProvider",
    "AppLaunchStatsProvider",
    "ProjectFilesProvider",
    "FileStatisticsProvider",
    "FileSearchProvider",
    "DocumentContentProvider",
    "ImageAnalyzerProvider",
    "FaceManagerProvider",
]
