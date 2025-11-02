"""Utility functions for Ratatoskr."""

from .gsettings import is_in_container, gsettings_get_list
from .desktop_files import get_app_name, get_app_names, parse_desktop_file

__all__ = [
    "is_in_container",
    "gsettings_get_list",
    "get_app_name",
    "get_app_names",
    "parse_desktop_file",
]
