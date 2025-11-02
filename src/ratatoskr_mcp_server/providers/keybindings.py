"""GNOME keybindings provider."""

import subprocess
from typing import List, Dict, Any
from ratatoskr_mcp_server.providers.base import ResourceProvider
from ratatoskr_mcp_server.resource_manager import ResourceData
from ratatoskr_mcp_server.utils.gsettings import gsettings_get_all, gsettings_get_with_path, _build_command


class GnomeKeybindingsProvider(ResourceProvider):
    """Provides information about GNOME keyboard shortcuts."""

    # Potential GNOME keybinding schemas (will check which exist)
    POTENTIAL_KEYBINDING_SCHEMAS = [
        'org.gnome.shell.keybindings',
        'org.gnome.desktop.wm.keybindings',
        'org.gnome.mutter.keybindings',
        'org.gnome.mutter.wayland.keybindings',
        'org.gnome.settings-daemon.plugins.media-keys',
    ]

    def _is_hardware_only_binding(self, value: str) -> bool:
        """
        Check if a keybinding value contains only hardware keys (XF86*) without modifiers.

        Args:
            value: GSettings value string (e.g., "['XF86Battery']" or "['<Super>1']")

        Returns:
            True if it's only hardware keys without user-assignable shortcuts
        """
        # Check if all items in the array are XF86* keys without < modifiers
        # Hardware-only: ['XF86Battery']
        # User shortcut: ['<Super>1'], ['<Alt>F4']
        # Mixed: ['XF86AudioRaiseVolume', '<Super>Up']

        # If it contains < character, it has modifiers - keep it
        if '<' in value:
            return False

        # If it contains XF86, it's a hardware key
        if 'XF86' in value:
            return True

        return False

    def _get_available_schemas(self) -> list[str]:
        """
        Get list of keybinding schemas that actually exist on the system.

        Returns:
            List of available schema names
        """
        available = []

        # Get all installed schemas
        try:
            cmd = _build_command(['gsettings', 'list-schemas'])
            output = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True
            ).stdout

            installed_schemas = set(output.strip().split('\n'))

            # Check which of our keybinding schemas are installed
            for schema in self.POTENTIAL_KEYBINDING_SCHEMAS:
                if schema in installed_schemas:
                    available.append(schema)

        except subprocess.CalledProcessError:
            pass

        return available

    def _expand_custom_keybindings(self, paths_str: str) -> List[Dict[str, str]]:
        """
        Expand custom keybinding paths to their full details.

        Args:
            paths_str: String containing array of paths like "['path1/', 'path2/']"

        Returns:
            List of dicts with 'name', 'binding', and 'command' for each custom keybinding
        """
        # Parse the array string to extract paths
        # Example: "['/org/gnome/.../custom0/', '/org/gnome/.../custom1/']"
        paths_str = paths_str.strip()
        if not paths_str.startswith('[') or not paths_str.endswith(']'):
            return []

        # Remove brackets and split by comma
        paths_str = paths_str[1:-1]
        if not paths_str.strip():
            return []

        # Split and clean paths
        paths = []
        for part in paths_str.split(','):
            part = part.strip().strip("'\"")
            if part:
                paths.append(part)

        # Query each custom keybinding
        custom_bindings = []
        schema = 'org.gnome.settings-daemon.plugins.media-keys.custom-keybinding'

        for path in paths:
            try:
                name = gsettings_get_with_path(schema, path, 'name')
                binding = gsettings_get_with_path(schema, path, 'binding')
                command = gsettings_get_with_path(schema, path, 'command')

                custom_bindings.append({
                    'name': name,
                    'binding': binding,
                    'command': command,
                })
            except subprocess.CalledProcessError:
                # If we can't read this custom binding, skip it
                continue

        return custom_bindings

    async def get_resource(self) -> ResourceData:
        """
        Get all GNOME keybindings from available schemas.

        Returns:
            ResourceData with keybindings organized by schema including:
            - available_schemas: List of schemas that were found
            - <schema_name>: Keybindings for each schema
            - total_count: Total number of keybindings
        """
        try:
            # Discover which schemas are available
            available_schemas = self._get_available_schemas()

            if not available_schemas:
                return ResourceData(
                    content={
                        'available_schemas': [],
                        'total_count': 0,
                        'message': 'No keybinding schemas found on this system'
                    }
                )

            all_keybindings = {
                'available_schemas': available_schemas
            }
            total_count = 0

            # Query each available schema
            for schema in available_schemas:
                try:
                    bindings = gsettings_get_all(schema)

                    # Filter out empty, disabled, or unmapped keybindings
                    filtered_bindings = {}
                    for key, value in bindings.items():
                        if not value:
                            continue

                        # Special handling for custom-keybindings
                        if key == 'custom-keybindings' and value.startswith('['):
                            # Expand custom keybindings to show their details
                            custom_bindings = self._expand_custom_keybindings(value)
                            if custom_bindings:
                                filtered_bindings['custom_keybindings'] = custom_bindings
                            continue

                        # Skip empty arrays
                        if value in ['@as []', "['']", '[]', 'disabled']:
                            continue

                        # Skip values that don't look like keybindings
                        # Valid keybindings are usually arrays like ['<Super>1'] or strings
                        if not value.startswith('[') and not value.startswith("'"):
                            continue

                        # Skip hardware-only keybindings (XF86* without modifiers)
                        # These are like ['XF86Battery'] - just hardware key names
                        # We want shortcuts like ['<Super>1'], ['<Alt>F4'], etc.
                        # Check if it's ONLY XF86 keys without any modifier keys
                        if self._is_hardware_only_binding(value):
                            continue

                        filtered_bindings[key] = value

                    # Store with a descriptive name that won't collide
                    # org.gnome.shell.keybindings → shell_keybindings
                    # org.gnome.desktop.wm.keybindings → desktop_wm_keybindings
                    # org.gnome.mutter.keybindings → mutter_keybindings
                    parts = schema.split('.')
                    if len(parts) >= 3:
                        # Take last 2-3 parts to make it unique
                        if len(parts) > 3:
                            schema_name = '_'.join(parts[-2:]).replace('-', '_')
                        else:
                            schema_name = parts[-1].replace('-', '_')
                    else:
                        schema_name = schema.replace('.', '_').replace('-', '_')

                    all_keybindings[schema_name] = filtered_bindings

                    # Count keybindings, including custom ones
                    for key, value in filtered_bindings.items():
                        if key == 'custom_keybindings' and isinstance(value, list):
                            total_count += len(value)
                        else:
                            total_count += 1

                except Exception as e:
                    # If a schema fails, store error but continue
                    schema_name = schema.split('.')[-1].replace('-', '_')
                    all_keybindings[schema_name] = {'error': str(e)}

            all_keybindings['total_count'] = total_count

            return ResourceData(content=all_keybindings)

        except Exception as e:
            return ResourceData(
                content={},
                error=f"Failed to get keybindings: {str(e)}"
            )
