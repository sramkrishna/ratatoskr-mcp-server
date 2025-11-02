"""GSettings utilities for querying GNOME configuration."""

import subprocess
from typing import List, Dict, Any


def is_in_container() -> bool:
    """
    Detect if running inside a container (toolbox/distrobox).

    Returns:
        True if running in a container, False otherwise.
    """
    try:
        subprocess.run(
            ['which', 'flatpak-spawn'],
            capture_output=True,
            check=True
        )
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def _build_command(base_cmd: List[str]) -> List[str]:
    """
    Build command with container detection.

    Args:
        base_cmd: Base command to execute

    Returns:
        Command with flatpak-spawn prepended if in container
    """
    if is_in_container():
        return ['flatpak-spawn', '--host'] + base_cmd
    return base_cmd


def gsettings_get_list(schema: str, key: str) -> List[str]:
    """
    Query a GSettings list value, handling container environments.

    Args:
        schema: GSettings schema (e.g., 'org.gnome.shell')
        key: GSettings key (e.g., 'enabled-extensions')

    Returns:
        List of string values from GSettings

    Raises:
        subprocess.CalledProcessError: If gsettings command fails
    """
    cmd = _build_command(['gsettings', 'get', schema, key])

    # Execute command
    output = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=True
    ).stdout

    # Parse GSettings list output: ['item1', 'item2'] -> ['item1', 'item2']
    # Remove brackets, quotes, spaces and split by comma
    result = output[1:-2].replace("'", "").replace(" ", "").split(",")

    # Filter out empty strings
    return [item for item in result if item]


def gsettings_get_string(schema: str, key: str) -> str:
    """
    Query a GSettings string value.

    Args:
        schema: GSettings schema
        key: GSettings key

    Returns:
        String value from GSettings

    Raises:
        subprocess.CalledProcessError: If gsettings command fails
    """
    cmd = _build_command(['gsettings', 'get', schema, key])

    output = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=True
    ).stdout.strip()

    # Remove surrounding quotes if present
    if output.startswith("'") and output.endswith("'"):
        output = output[1:-1]

    return output


def gsettings_list_keys(schema: str) -> List[str]:
    """
    List all keys in a GSettings schema.

    Args:
        schema: GSettings schema

    Returns:
        List of key names

    Raises:
        subprocess.CalledProcessError: If gsettings command fails
    """
    cmd = _build_command(['gsettings', 'list-keys', schema])

    output = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=True
    ).stdout

    # Split by newlines and filter empty
    return [line.strip() for line in output.split('\n') if line.strip()]


def gsettings_get_all(schema: str) -> Dict[str, Any]:
    """
    Get all key-value pairs from a GSettings schema.

    Args:
        schema: GSettings schema

    Returns:
        Dictionary mapping keys to their values

    Raises:
        subprocess.CalledProcessError: If gsettings command fails
    """
    keys = gsettings_list_keys(schema)
    result = {}

    for key in keys:
        try:
            cmd = _build_command(['gsettings', 'get', schema, key])
            output = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True
            ).stdout.strip()

            # Store the raw value
            result[key] = output
        except subprocess.CalledProcessError:
            # If we can't get a key, skip it
            result[key] = None

    return result


def gsettings_get_with_path(schema: str, path: str, key: str) -> str:
    """
    Query a GSettings value from a relocatable schema with a specific path.

    Args:
        schema: GSettings schema (e.g., 'org.gnome.settings-daemon.plugins.media-keys.custom-keybinding')
        path: Path for the relocatable schema (e.g., '/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/custom0/')
        key: GSettings key (e.g., 'binding', 'command', 'name')

    Returns:
        String value from GSettings

    Raises:
        subprocess.CalledProcessError: If gsettings command fails
    """
    # For relocatable schemas, use --schemadir with the path in the schema:path format
    cmd = _build_command(['gsettings', 'get', f'{schema}:{path}', key])

    output = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=True
    ).stdout.strip()

    # Remove surrounding quotes if present
    if output.startswith("'") and output.endswith("'"):
        output = output[1:-1]

    return output
