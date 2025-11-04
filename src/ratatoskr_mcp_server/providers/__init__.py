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
# from .face_manager import FaceManagerProvider  # Disabled - requires face_recognition
from .calendar import CalendarProvider
from .planify import PlanifyProvider
from .email import EmailProvider
# from .muninn import MuninnProvider  # Disabled - Muninn is a separate MCP server

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
    # "FaceManagerProvider",  # Disabled - requires face_recognition
    "CalendarProvider",
    "PlanifyProvider",
    "EmailProvider",
    # "MuninnProvider",  # Disabled - Muninn is a separate MCP server
]
