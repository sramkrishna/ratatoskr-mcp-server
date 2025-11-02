"""Monitor for tracking application launches via GNOME Shell application state."""

import logging
import threading
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, Optional

from ratatoskr_mcp_server.utils.app_launch_db import AppLaunchDB
from ratatoskr_mcp_server.utils.desktop_files import get_app_names

logger = logging.getLogger(__name__)


class AppLaunchMonitor:
    """Monitor for tracking application launches."""

    def __init__(self, db_path: Optional[str] = None, poll_interval: float = 2.0):
        """
        Initialize the app launch monitor.

        Args:
            db_path: Path to SQLite database. If None, uses default location.
            poll_interval: How often to check for app state changes (seconds)
        """
        self.db = AppLaunchDB(db_path)
        self.poll_interval = poll_interval
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._last_seen: Dict[str, int] = {}  # app_id -> last_seen_timestamp
        self._lock = threading.Lock()

        # Path to GNOME Shell's application state file
        self.app_state_path = Path.home() / '.local' / 'share' / 'gnome-shell' / 'application_state'

    def _parse_application_state(self) -> Dict[str, int]:
        """
        Parse GNOME Shell's application_state file.

        Returns:
            Dictionary mapping app_id to last_seen timestamp
        """
        result = {}

        if not self.app_state_path.exists():
            return result

        try:
            tree = ET.parse(self.app_state_path)
            root = tree.getroot()

            for app in root.findall('.//application'):
                app_id = app.get('id')
                last_seen = app.get('last-seen')

                if app_id and last_seen:
                    result[app_id] = int(last_seen)

        except Exception as e:
            logger.debug(f"Failed to parse application state: {e}")

        return result

    def _monitor_loop(self) -> None:
        """Main monitoring loop that runs in a background thread."""
        logger.info("App launch monitor started")

        # Initialize with current application state
        self._last_seen = self._parse_application_state()
        logger.info(f"Monitoring {len(self._last_seen)} applications")

        while self._running:
            try:
                # Get current application state
                current_state = self._parse_application_state()

                # Find apps that were launched (last_seen timestamp changed)
                newly_launched = []

                for app_id, last_seen in current_state.items():
                    if app_id not in self._last_seen:
                        # New app we haven't seen before - record it
                        newly_launched.append(app_id)
                    elif last_seen > self._last_seen[app_id]:
                        # App was launched again (timestamp updated)
                        newly_launched.append(app_id)

                if newly_launched:
                    # Get human-readable names and record launches
                    app_info = get_app_names(newly_launched)

                    for info in app_info:
                        app_id = info['id']
                        app_name = info['name']

                        # Record to database
                        self.db.record_launch(app_id, app_name)
                        logger.info(f"Recorded launch: {app_name} ({app_id})")

                # Update our tracking state
                with self._lock:
                    self._last_seen = current_state

            except Exception as e:
                logger.error(f"Error in monitor loop: {e}")

            # Sleep until next poll
            time.sleep(self.poll_interval)

        logger.info("App launch monitor stopped")

    def start(self) -> None:
        """Start monitoring app launches in a background thread."""
        if self._running:
            logger.warning("Monitor already running")
            return

        if not self.app_state_path.exists():
            logger.warning(f"Application state file not found: {self.app_state_path}")
            logger.warning("App launch monitoring may not work correctly")

        self._running = True
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()
        logger.info("App launch monitor starting...")

    def stop(self) -> None:
        """Stop monitoring app launches."""
        if not self._running:
            return

        logger.info("Stopping app launch monitor...")
        self._running = False

        if self._thread:
            self._thread.join(timeout=5.0)
            self._thread = None

    def is_running(self) -> bool:
        """Check if the monitor is currently running."""
        return self._running

    def get_stats(self):
        """Get launch statistics from the database."""
        return self.db.get_stats()

    def get_top_apps(self, limit: int = 10):
        """Get most frequently launched apps."""
        return self.db.get_top_apps(limit)

    def get_recent_launches(self, limit: int = 10):
        """Get most recent app launches."""
        return self.db.get_recent_launches(limit)

    def import_gnome_history(self) -> int:
        """
        Import historical app usage from GNOME's application_state file.

        This uses the last-seen timestamps and scores to estimate historical usage.
        Apps with higher scores are assumed to have been launched more frequently.
        We estimate launch counts based on GNOME's score.

        Returns:
            Number of historical launches imported
        """
        if not self.app_state_path.exists():
            logger.warning("Application state file not found")
            return 0

        try:
            tree = ET.parse(self.app_state_path)
            root = tree.getroot()

            imported_count = 0
            app_data = []

            # Collect all apps with their scores and timestamps
            for app in root.findall('.//application'):
                app_id = app.get('id')
                last_seen = app.get('last-seen')
                score = app.get('score')

                if app_id and last_seen:
                    app_data.append({
                        'id': app_id,
                        'last_seen': int(last_seen),
                        'score': float(score) if score else 0.0
                    })

            # Get human-readable names
            app_ids = [app['id'] for app in app_data]
            app_names = get_app_names(app_ids)
            name_map = {info['id']: info['name'] for info in app_names}

            # Import based on score (higher score = more launches in the past)
            # We estimate launch counts from the score
            for app in app_data:
                app_id = app['id']
                app_name = name_map.get(app_id, app_id)
                score = app['score']

                # Only import apps that have been actually used (score > 0)
                if score > 0:
                    # Estimate launch count from score
                    # GNOME's score is a weighted average of frequency and recency
                    # Higher score = more frequent use
                    # Use a logarithmic scale to avoid over-counting
                    # Score 1-10: 1 launch, 10-100: 2-10 launches, 100-1000: 10-30, etc.
                    import math
                    estimated_launches = max(1, min(200, int(math.log10(score + 1) * 20)))

                    # Record estimated historical launches
                    for _ in range(estimated_launches):
                        self.db.record_launch(app_id, app_name)
                        imported_count += 1

                    logger.debug(f"Imported {estimated_launches} launches for {app_name} (score: {score:.1f})")

            logger.info(f"Imported {imported_count} historical app usage entries from GNOME")
            return imported_count

        except Exception as e:
            logger.error(f"Failed to import GNOME history: {e}")
            return 0

    def get_gnome_app_scores(self) -> list[dict]:
        """
        Get GNOME's native app usage scores for comparison.

        Returns:
            List of dicts with app_id, name, score, and last_seen (ISO 8601 format with timezone)
        """
        if not self.app_state_path.exists():
            return []

        try:
            from datetime import datetime
            import time

            tree = ET.parse(self.app_state_path)
            root = tree.getroot()

            app_data = []

            for app in root.findall('.//application'):
                app_id = app.get('id')
                last_seen = app.get('last-seen')
                score = app.get('score')

                if app_id and last_seen:
                    timestamp = int(last_seen)
                    # Convert to local datetime with timezone info
                    dt = datetime.fromtimestamp(timestamp)

                    # Get timezone offset
                    if time.daylight and time.localtime(timestamp).tm_isdst:
                        tz_offset_seconds = -time.altzone
                    else:
                        tz_offset_seconds = -time.timezone

                    tz_hours = tz_offset_seconds // 3600
                    tz_minutes = abs(tz_offset_seconds % 3600) // 60
                    tz_str = f"{tz_hours:+03d}:{tz_minutes:02d}"

                    # Format as ISO 8601 with timezone
                    last_seen_iso = f"{dt.strftime('%Y-%m-%dT%H:%M:%S')}{tz_str}"

                    app_data.append({
                        'id': app_id,
                        'last_seen_timestamp': timestamp,
                        'last_seen': last_seen_iso,
                        'score': float(score) if score else 0.0
                    })

            # Get names
            app_ids = [app['id'] for app in app_data]
            app_names = get_app_names(app_ids)
            name_map = {info['id']: info['name'] for info in app_names}

            # Add names and sort by score
            result = []
            for app in app_data:
                result.append({
                    'app_id': app['id'],
                    'name': name_map.get(app['id'], app['id']),
                    'score': app['score'],
                    'last_seen': app['last_seen'],
                    'last_seen_timestamp': app['last_seen_timestamp']
                })

            # Sort by score descending
            result.sort(key=lambda x: x['score'], reverse=True)

            return result

        except Exception as e:
            logger.error(f"Failed to get GNOME app scores: {e}")
            return []

    def close(self) -> None:
        """Clean up resources."""
        self.stop()
        self.db.close()
