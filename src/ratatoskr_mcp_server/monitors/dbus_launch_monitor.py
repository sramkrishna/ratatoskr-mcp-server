"""D-Bus based app launch monitor using NameOwnerChanged signals."""

import logging
import subprocess
import threading
import time
import json
from typing import Optional, Dict, Set
from pathlib import Path

from ratatoskr_mcp_server.utils.app_launch_db import AppLaunchDB
from ratatoskr_mcp_server.utils.desktop_files import get_app_names

logger = logging.getLogger(__name__)


class DBusLaunchMonitor:
    """Monitor app launches via D-Bus NameOwnerChanged signals."""

    def __init__(self, db_path: Optional[str] = None, startup_grace_period: float = 5.0):
        """
        Initialize the D-Bus launch monitor.

        Args:
            db_path: Path to SQLite database. If None, uses default location.
            startup_grace_period: Seconds to wait after starting before recording launches (default: 5.0)
        """
        self.db = AppLaunchDB(db_path)
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._known_names: Set[str] = set()
        self._startup_grace_period = startup_grace_period
        self._start_time: Optional[float] = None

        # Cache for D-Bus name to desktop ID mapping
        self._name_to_desktop_id: Dict[str, str] = {}
        self._build_name_mapping()

    def _build_name_mapping(self) -> None:
        """
        Build mapping from D-Bus names to desktop IDs.

        Common patterns:
        - org.gnome.Nautilus → org.gnome.Nautilus.desktop
        - org.mozilla.firefox → org.mozilla.firefox.desktop
        """
        # Get all known desktop apps from GNOME state
        app_state_path = Path.home() / '.local' / 'share' / 'gnome-shell' / 'application_state'

        if app_state_path.exists():
            try:
                import xml.etree.ElementTree as ET
                tree = ET.parse(app_state_path)
                root = tree.getroot()

                # Build reverse mapping
                for app in root.findall('.//application'):
                    app_id = app.get('id')
                    if app_id:
                        # Remove .desktop suffix to get potential D-Bus name
                        if app_id.endswith('.desktop'):
                            dbus_name = app_id[:-8]  # Remove .desktop
                            self._name_to_desktop_id[dbus_name] = app_id

                            # Also try lowercase variants
                            self._name_to_desktop_id[dbus_name.lower()] = app_id

                logger.debug(f"Built mapping for {len(self._name_to_desktop_id)} D-Bus names")
            except Exception as e:
                logger.warning(f"Failed to build D-Bus name mapping: {e}")

    def _has_search_provider(self, desktop_id: str) -> bool:
        """
        Check if an app has a search provider (may launch in background).

        Args:
            desktop_id: Desktop file ID

        Returns:
            True if the app has a known search provider
        """
        # Remove .desktop suffix for checking
        app_id = desktop_id.replace('.desktop', '')

        # Apps known to have search providers that may launch in background
        apps_with_search_providers = [
            'org.gnome.Characters',
            'org.gnome.Calculator',
            'org.gnome.clocks',
            'org.gnome.Contacts',
            'org.gnome.Calendar',
            'org.gnome.Weather',
        ]

        return app_id in apps_with_search_providers

    def _get_desktop_id_from_dbus_name(self, dbus_name: str) -> Optional[str]:
        """
        Try to determine desktop ID from D-Bus name.

        Args:
            dbus_name: D-Bus service name (e.g., 'org.gnome.Nautilus')

        Returns:
            Desktop ID if found, None otherwise
        """
        # Try direct lookup
        if dbus_name in self._name_to_desktop_id:
            return self._name_to_desktop_id[dbus_name]

        # Try with .desktop suffix
        potential_id = f"{dbus_name}.desktop"
        if potential_id in self._name_to_desktop_id.values():
            return potential_id

        # Try common patterns
        if dbus_name.startswith('org.gnome.'):
            return f"{dbus_name}.desktop"

        if dbus_name.startswith('org.mozilla.'):
            return f"{dbus_name}.desktop"

        return None

    def _is_app_service(self, name: str) -> bool:
        """
        Check if a D-Bus name represents an application.

        Args:
            name: D-Bus service name

        Returns:
            True if this looks like an app service
        """
        # Skip system services
        if name.startswith(':'):  # Unique names
            return False

        if name.startswith('org.freedesktop.'):
            return False

        if name.startswith('org.gtk.'):
            return False

        # Skip background service suffixes (search providers, previewers, APIs, daemons, etc.)
        background_suffixes = [
            '.SearchProvider',
            '.Api',  # Background API services (e.g., PikaBackup.Api)
            'Previewer',  # NautilusPreviewer
            'Daemon',
            '.Monitor',
        ]
        if any(name.endswith(suffix) for suffix in background_suffixes):
            return False

        # Include GNOME apps and other well-known prefixes
        app_prefixes = [
            'org.gnome.',
            'org.mozilla.',
            'com.slack.',
            'com.discordapp.',
            'org.chromium.',
            'com.google.',
            'io.github.',
            'com.github.',
            'org.kde.',
        ]

        return any(name.startswith(prefix) for prefix in app_prefixes)

    def _monitor_loop(self) -> None:
        """
        Main monitoring loop using dbus-monitor.

        Uses dbus-monitor command to watch NameOwnerChanged signals.
        """
        logger.info("D-Bus launch monitor started")

        try:
            # Build command to monitor NameOwnerChanged
            from ratatoskr_mcp_server.utils.gsettings import _build_command

            cmd = _build_command([
                'dbus-monitor',
                '--session',
                "type='signal',sender='org.freedesktop.DBus',interface='org.freedesktop.DBus',member='NameOwnerChanged'"
            ])

            # Start dbus-monitor process
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1
            )

            current_signal = {}

            while self._running and process.poll() is None:
                line = process.stdout.readline()
                if not line:
                    continue

                line = line.strip()

                # Parse dbus-monitor output
                if 'member=NameOwnerChanged' in line:
                    current_signal = {}
                elif line.startswith('string "'):
                    # Extract the string value
                    value = line[8:-1]  # Remove 'string "' and '"'

                    if 'name' not in current_signal:
                        current_signal['name'] = value
                    elif 'old_owner' not in current_signal:
                        current_signal['old_owner'] = value
                    elif 'new_owner' not in current_signal:
                        current_signal['new_owner'] = value

                        # We have a complete signal - process it
                        self._handle_name_owner_changed(
                            current_signal['name'],
                            current_signal['old_owner'],
                            current_signal['new_owner']
                        )
                        current_signal = {}

            process.terminate()
            process.wait(timeout=5)

        except Exception as e:
            logger.error(f"D-Bus monitor error: {e}")

        logger.info("D-Bus launch monitor stopped")

    def _handle_name_owner_changed(self, name: str, old_owner: str, new_owner: str) -> None:
        """
        Handle a NameOwnerChanged signal.

        Args:
            name: Service name
            old_owner: Previous owner (empty if new service)
            new_owner: New owner (empty if service exited)
        """
        # Check if this is an app service
        if not self._is_app_service(name):
            return

        # App launched (claimed a name)
        if not old_owner and new_owner:
            # Skip during startup grace period to avoid recording already-running apps
            if self._start_time and (time.time() - self._start_time) < self._startup_grace_period:
                logger.debug(f"Ignoring D-Bus service during startup grace period: {name}")
                return

            logger.info(f"D-Bus service started: {name}")

            # Try to get desktop ID
            desktop_id = self._get_desktop_id_from_dbus_name(name)

            if desktop_id:
                # Get human-readable name
                app_info = get_app_names([desktop_id])
                app_name = app_info[0]['name'] if app_info and app_info[0]['found'] else name

                # Check if this app has a search provider
                has_search_provider = self._has_search_provider(desktop_id)
                search_provider_note = " (has search provider - may include background activations)" if has_search_provider else ""

                # Record the launch (with deduplication)
                recorded = self.db.record_launch(desktop_id, app_name)
                if recorded:
                    logger.info(f"Recorded launch: {app_name} ({desktop_id}){search_provider_note}")
                else:
                    logger.debug(f"Skipped duplicate launch: {app_name} ({desktop_id})")
            else:
                logger.debug(f"Could not map D-Bus name to desktop ID: {name}")

        # App exited (released a name)
        elif old_owner and not new_owner:
            logger.debug(f"D-Bus service stopped: {name}")
            # Future: Could track exit events and duration

    def start(self) -> None:
        """Start monitoring D-Bus signals in a background thread."""
        if self._running:
            logger.warning("D-Bus monitor already running")
            return

        self._start_time = time.time()
        self._running = True
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()
        logger.info(f"D-Bus launch monitor starting (grace period: {self._startup_grace_period}s)...")

    def stop(self) -> None:
        """Stop monitoring D-Bus signals."""
        if not self._running:
            return

        logger.info("Stopping D-Bus launch monitor...")
        self._running = False

        if self._thread:
            self._thread.join(timeout=5.0)
            self._thread = None

    def is_running(self) -> bool:
        """Check if the monitor is currently running."""
        return self._running

    def close(self) -> None:
        """Clean up resources."""
        self.stop()
        self.db.close()
