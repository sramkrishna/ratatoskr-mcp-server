"""Systemd-based app launch monitor for Flatpak applications."""

import logging
import re
import subprocess
import threading
import time
from typing import Optional

from ratatoskr_mcp_server.utils.app_launch_db import AppLaunchDB
from ratatoskr_mcp_server.utils.desktop_files import get_app_names

logger = logging.getLogger(__name__)


class SystemdLaunchMonitor:
    """Monitor Flatpak app launches via systemd D-Bus signals."""

    def __init__(self, db_path: Optional[str] = None, startup_grace_period: float = 5.0):
        """
        Initialize the systemd launch monitor.

        Args:
            db_path: Path to SQLite database. If None, uses default location.
            startup_grace_period: Seconds to wait after starting before recording launches (default: 5.0)
        """
        self.db = AppLaunchDB(db_path)
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._startup_grace_period = startup_grace_period
        self._start_time: Optional[float] = None

    def _unescape_systemd_unit_name(self, name: str) -> str:
        """
        Unescape systemd unit name encoding.

        Systemd escapes special characters as \\xNN where NN is hex.
        gdbus outputs them with double backslashes: \\\\xNN
        Example: \\\\x2d → -

        Args:
            name: Escaped systemd unit name part

        Returns:
            Unescaped string
        """
        def replace_hex(match):
            hex_code = match.group(1)
            return chr(int(hex_code, 16))

        # Replace all \\xNN sequences (double backslash from gdbus output)
        # Pattern uses 4 backslashes in raw string to match 2 literal backslashes
        return re.sub(r'\\\\x([0-9a-fA-F]{2})', replace_hex, name)

    def _should_record_app(self, desktop_id: str) -> bool:
        """
        Check if an app should be recorded (filter background services).

        Args:
            desktop_id: Desktop file ID (e.g., 'org.gnome.NautilusPreviewer.desktop')

        Returns:
            True if the app should be recorded, False otherwise
        """
        # Remove .desktop suffix for checking
        app_id = desktop_id.replace('.desktop', '')

        # Skip background service suffixes
        background_suffixes = [
            '.SearchProvider',
            '.Api',  # Background API services (e.g., PikaBackup.Api)
            'Previewer',  # NautilusPreviewer
            'Daemon',
            '.Monitor',
        ]

        for suffix in background_suffixes:
            if app_id.endswith(suffix):
                return False

        return True

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

    def _extract_app_id_from_unit(self, unit_name: str) -> Optional[str]:
        """
        Extract Flatpak app ID from systemd unit name.

        Args:
            unit_name: Unit name (e.g., 'app-flatpak-io.github.alainm23.planify-1732779298.scope')

        Returns:
            App ID with .desktop suffix (e.g., 'io.github.alainm23.planify.desktop')
            or None if not a Flatpak app unit
        """
        # Pattern: app-flatpak-{APP_ID}-{RANDOM}.scope
        match = re.match(r'app-flatpak-(.+)-\d+\.scope$', unit_name)
        if match:
            app_id = match.group(1)
            # Unescape systemd unit name encoding
            app_id = self._unescape_systemd_unit_name(app_id)
            return f"{app_id}.desktop"
        return None

    def _monitor_loop(self) -> None:
        """
        Main monitoring loop using gdbus monitor.

        Watches for systemd UnitNew signals for Flatpak app launches.
        """
        logger.info("Systemd Flatpak launch monitor started")

        try:
            # Build command to monitor systemd signals
            from ratatoskr_mcp_server.utils.gsettings import _build_command

            cmd = _build_command([
                'gdbus',
                'monitor',
                '--session',
                '--dest', 'org.freedesktop.systemd1',
                '--object-path', '/org/freedesktop/systemd1'
            ])

            # Start gdbus monitor process
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1
            )

            while self._running and process.poll() is None:
                line = process.stdout.readline()
                if not line:
                    continue

                line = line.strip()

                # Look for UnitNew signals
                # Format: /org/freedesktop/systemd1: org.freedesktop.systemd1.Manager.UnitNew ('app-flatpak-...', ...)
                if 'org.freedesktop.systemd1.Manager.UnitNew' in line:
                    # Extract unit name from the signal
                    # The unit name is in single quotes after UnitNew
                    match = re.search(r"UnitNew \('([^']+)'", line)
                    if match:
                        unit_name = match.group(1)
                        self._handle_unit_new(unit_name)

            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()

        except Exception as e:
            logger.error(f"Systemd monitor error: {e}")

        logger.info("Systemd Flatpak launch monitor stopped")

    def _handle_unit_new(self, unit_name: str) -> None:
        """
        Handle a systemd UnitNew signal.

        Args:
            unit_name: Systemd unit name (e.g., 'app-flatpak-io.github.alainm23.planify-123.scope')
        """
        # Only process Flatpak app units
        if not unit_name.startswith('app-flatpak-'):
            return

        # Skip during startup grace period to avoid recording already-running apps
        if self._start_time and (time.time() - self._start_time) < self._startup_grace_period:
            logger.debug(f"Ignoring unit during startup grace period: {unit_name}")
            return

        logger.info(f"Systemd unit started: {unit_name}")

        # Extract app ID
        desktop_id = self._extract_app_id_from_unit(unit_name)

        if desktop_id:
            # Filter out background services (same as D-Bus monitor)
            if not self._should_record_app(desktop_id):
                logger.debug(f"Skipped background service: {desktop_id}")
                return

            # Get human-readable name
            app_info = get_app_names([desktop_id])
            app_name = app_info[0]['name'] if app_info and app_info[0]['found'] else desktop_id

            # Check if this app has a search provider
            has_search_provider = self._has_search_provider(desktop_id)
            search_provider_note = " (has search provider - may include background activations)" if has_search_provider else ""

            # Record the launch (with deduplication)
            recorded = self.db.record_launch(desktop_id, app_name)
            if recorded:
                logger.info(f"Recorded Flatpak launch: {app_name} ({desktop_id}){search_provider_note}")
            else:
                logger.debug(f"Skipped duplicate Flatpak launch: {app_name} ({desktop_id})")
        else:
            logger.debug(f"Could not extract app ID from unit: {unit_name}")

    def start(self) -> None:
        """Start monitoring systemd signals in a background thread."""
        if self._running:
            logger.warning("Systemd monitor already running")
            return

        self._start_time = time.time()
        self._running = True
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()
        logger.info(f"Systemd Flatpak launch monitor starting (grace period: {self._startup_grace_period}s)...")

    def stop(self) -> None:
        """Stop monitoring systemd signals."""
        if not self._running:
            return

        logger.info("Stopping systemd Flatpak launch monitor...")
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
