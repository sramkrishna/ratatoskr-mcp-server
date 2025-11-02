"""Utilities for parsing .desktop files."""

import os
from pathlib import Path
from typing import Optional, List


# Standard locations for .desktop files
DESKTOP_FILE_PATHS = [
    Path.home() / ".local/share/applications",           # User apps
    Path("/usr/share/applications"),                      # System apps
    Path("/usr/local/share/applications"),                # Local apps
    Path("/var/lib/flatpak/exports/share/applications"),  # Flatpak apps (system)
    Path.home() / ".local/share/flatpak/exports/share/applications",  # Flatpak apps (user)
]


def find_desktop_file(desktop_id: str) -> Optional[Path]:
    """
    Find a .desktop file by its ID.

    Args:
        desktop_id: Desktop file ID (e.g., 'org.mozilla.firefox.desktop')

    Returns:
        Path to the desktop file if found, None otherwise
    """
    for search_path in DESKTOP_FILE_PATHS:
        if not search_path.exists():
            continue

        desktop_file = search_path / desktop_id
        if desktop_file.exists():
            return desktop_file

    return None


def parse_desktop_file(desktop_file: Path) -> dict:
    """
    Parse a .desktop file and extract key information.

    Args:
        desktop_file: Path to the .desktop file

    Returns:
        Dictionary with desktop entry fields
    """
    data = {
        'name': None,
        'generic_name': None,
        'comment': None,
        'icon': None,
        'exec': None,
        'categories': [],
    }

    try:
        with open(desktop_file, 'r', encoding='utf-8') as f:
            in_desktop_entry = False

            for line in f:
                line = line.strip()

                # Check for [Desktop Entry] section
                if line == '[Desktop Entry]':
                    in_desktop_entry = True
                    continue
                elif line.startswith('[') and line.endswith(']'):
                    # Entering a different section
                    in_desktop_entry = False
                    continue

                # Only parse lines in [Desktop Entry] section
                if not in_desktop_entry or not line or line.startswith('#'):
                    continue

                # Parse key=value
                if '=' in line:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip()

                    if key == 'Name':
                        data['name'] = value
                    elif key == 'GenericName':
                        data['generic_name'] = value
                    elif key == 'Comment':
                        data['comment'] = value
                    elif key == 'Icon':
                        data['icon'] = value
                    elif key == 'Exec':
                        data['exec'] = value
                    elif key == 'Categories':
                        data['categories'] = [cat.strip() for cat in value.split(';') if cat.strip()]

    except Exception:
        pass

    return data


def get_app_name(desktop_id: str) -> str:
    """
    Get the human-readable name for a desktop application.

    Args:
        desktop_id: Desktop file ID (e.g., 'org.mozilla.firefox.desktop')

    Returns:
        Human-readable app name, or the desktop_id if parsing fails
    """
    # Find the desktop file
    desktop_file = find_desktop_file(desktop_id)
    if not desktop_file:
        # Fallback: try to extract a reasonable name from the ID
        return _fallback_name_from_id(desktop_id)

    # Parse the desktop file
    data = parse_desktop_file(desktop_file)

    # Return the name, or fallback
    if data['name']:
        return data['name']

    return _fallback_name_from_id(desktop_id)


def get_app_names(desktop_ids: List[str]) -> List[dict]:
    """
    Get human-readable names for multiple desktop applications.

    Args:
        desktop_ids: List of desktop file IDs

    Returns:
        List of dictionaries with 'id', 'name', and 'found' keys
    """
    results = []

    for desktop_id in desktop_ids:
        desktop_file = find_desktop_file(desktop_id)
        found = desktop_file is not None

        if found:
            data = parse_desktop_file(desktop_file)
            name = data['name'] or _fallback_name_from_id(desktop_id)
        else:
            name = _fallback_name_from_id(desktop_id)

        results.append({
            'id': desktop_id,
            'name': name,
            'found': found
        })

    return results


def _fallback_name_from_id(desktop_id: str) -> str:
    """
    Extract a reasonable name from a desktop ID when the file can't be found.

    Args:
        desktop_id: Desktop file ID

    Returns:
        Best-effort human-readable name
    """
    # Remove .desktop suffix
    name = desktop_id.replace('.desktop', '')

    # For reverse domain names like org.mozilla.firefox, take the last part
    if '.' in name:
        parts = name.split('.')
        # Take the last part and capitalize it
        name = parts[-1].capitalize()

    return name
