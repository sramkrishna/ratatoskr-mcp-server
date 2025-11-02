"""SQLite database for tracking app launch statistics."""

import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from contextlib import contextmanager


class AppLaunchDB:
    """Database for tracking application launch statistics."""

    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize the app launch database.

        Args:
            db_path: Path to SQLite database file. If None, uses default location.
        """
        if db_path is None:
            # Store in XDG_DATA_HOME or ~/.local/share
            data_home = Path.home() / '.local' / 'share' / 'ratatoskr-mcp-server'
            data_home.mkdir(parents=True, exist_ok=True)
            db_path = str(data_home / 'app_launches.db')

        self.db_path = db_path
        self._local = threading.local()
        self._initialize_db()

    def _get_connection(self) -> sqlite3.Connection:
        """Get a thread-local database connection."""
        if not hasattr(self._local, 'connection'):
            self._local.connection = sqlite3.connect(self.db_path)
            self._local.connection.row_factory = sqlite3.Row
        return self._local.connection

    @contextmanager
    def _transaction(self):
        """Context manager for database transactions."""
        conn = self._get_connection()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def _initialize_db(self) -> None:
        """Initialize the database schema."""
        with self._transaction() as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS app_launches (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    app_id TEXT NOT NULL,
                    app_name TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # Create index for faster queries
            conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_app_id
                ON app_launches(app_id)
            ''')

            conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_timestamp
                ON app_launches(timestamp)
            ''')

    def record_launch(self, app_id: str, app_name: Optional[str] = None, dedupe_window_seconds: int = 2) -> bool:
        """
        Record an app launch with deduplication.

        Args:
            app_id: Application ID (e.g., 'org.mozilla.firefox.desktop')
            app_name: Human-readable app name (optional)
            dedupe_window_seconds: Skip recording if same app was launched within this many seconds (default: 2)

        Returns:
            True if launch was recorded, False if it was a duplicate
        """
        with self._transaction() as conn:
            # Check for recent launch of the same app
            cursor = conn.execute(
                '''
                SELECT timestamp FROM app_launches
                WHERE app_id = ?
                ORDER BY timestamp DESC
                LIMIT 1
                ''',
                (app_id,)
            )
            row = cursor.fetchone()

            if row:
                # Parse the last timestamp and check if it's within the dedupe window
                last_timestamp = datetime.strptime(row['timestamp'], '%Y-%m-%d %H:%M:%S')
                now = datetime.utcnow()
                time_diff = (now - last_timestamp).total_seconds()

                if time_diff < dedupe_window_seconds:
                    # Too soon - skip this duplicate launch
                    return False

            # Record the launch
            conn.execute(
                'INSERT INTO app_launches (app_id, app_name) VALUES (?, ?)',
                (app_id, app_name)
            )
            return True

    def get_launch_count(self, app_id: str) -> int:
        """
        Get total launch count for an app.

        Args:
            app_id: Application ID

        Returns:
            Number of times the app was launched
        """
        conn = self._get_connection()
        cursor = conn.execute(
            'SELECT COUNT(*) as count FROM app_launches WHERE app_id = ?',
            (app_id,)
        )
        row = cursor.fetchone()
        return row['count'] if row else 0

    def get_all_launch_counts(self) -> List[Dict[str, any]]:
        """
        Get launch counts for all apps, sorted by most launched.

        Returns:
            List of dicts with app_id, app_name, launch_count, and last_launched (local time with timezone)
        """
        import time
        import calendar

        conn = self._get_connection()
        cursor = conn.execute('''
            SELECT
                app_id,
                app_name,
                COUNT(*) as launch_count,
                MAX(timestamp) as last_launched
            FROM app_launches
            GROUP BY app_id
            ORDER BY launch_count DESC
        ''')

        results = []
        for row in cursor.fetchall():
            timestamp_str = row['last_launched']

            try:
                # Parse UTC timestamp and convert to local time with timezone
                dt_utc = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
                unix_timestamp = calendar.timegm(dt_utc.timetuple())
                dt_local = datetime.fromtimestamp(unix_timestamp)

                # Get timezone offset
                if time.daylight and time.localtime(unix_timestamp).tm_isdst:
                    tz_offset_seconds = -time.altzone
                else:
                    tz_offset_seconds = -time.timezone

                tz_hours = tz_offset_seconds // 3600
                tz_minutes = abs(tz_offset_seconds % 3600) // 60
                tz_str = f"{tz_hours:+03d}:{tz_minutes:02d}"

                last_launched_with_tz = f"{dt_local.strftime('%Y-%m-%dT%H:%M:%S')}{tz_str}"
            except Exception:
                last_launched_with_tz = timestamp_str

            results.append({
                'app_id': row['app_id'],
                'app_name': row['app_name'] or row['app_id'],
                'launch_count': row['launch_count'],
                'last_launched': last_launched_with_tz
            })

        return results

    def get_recent_launches(self, limit: int = 10) -> List[Dict[str, any]]:
        """
        Get most recent app launches.

        Args:
            limit: Maximum number of launches to return

        Returns:
            List of recent launches with app_id, app_name, and timestamp (local time with timezone)
        """
        import time

        conn = self._get_connection()
        cursor = conn.execute('''
            SELECT app_id, app_name, timestamp
            FROM app_launches
            ORDER BY timestamp DESC
            LIMIT ?
        ''', (limit,))

        results = []
        for row in cursor.fetchall():
            # SQLite CURRENT_TIMESTAMP stores UTC time
            # Parse it and convert to local time with timezone
            timestamp_str = row['timestamp']

            try:
                # Parse the UTC timestamp
                dt_utc = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')

                # Convert to Unix timestamp (treating as UTC)
                import calendar
                unix_timestamp = calendar.timegm(dt_utc.timetuple())

                # Convert to local time
                dt_local = datetime.fromtimestamp(unix_timestamp)

                # Get timezone offset
                if time.daylight and time.localtime(unix_timestamp).tm_isdst:
                    tz_offset_seconds = -time.altzone
                else:
                    tz_offset_seconds = -time.timezone

                tz_hours = tz_offset_seconds // 3600
                tz_minutes = abs(tz_offset_seconds % 3600) // 60
                tz_str = f"{tz_hours:+03d}:{tz_minutes:02d}"

                # Format as ISO 8601 with timezone
                timestamp_with_tz = f"{dt_local.strftime('%Y-%m-%dT%H:%M:%S')}{tz_str}"

            except Exception:
                # Fallback to original timestamp if parsing fails
                timestamp_with_tz = timestamp_str

            results.append({
                'app_id': row['app_id'],
                'app_name': row['app_name'] or row['app_id'],
                'timestamp': timestamp_with_tz
            })

        return results

    def get_top_apps(self, limit: int = 10) -> List[Dict[str, any]]:
        """
        Get most frequently launched apps.

        Args:
            limit: Maximum number of apps to return

        Returns:
            List of top apps with launch counts
        """
        all_counts = self.get_all_launch_counts()
        return all_counts[:limit]

    def get_stats(self) -> Dict[str, any]:
        """
        Get overall statistics.

        Returns:
            Dictionary with total launches, unique apps, first/last launch (local time with timezone)
        """
        import time
        import calendar

        conn = self._get_connection()

        # Total launches
        cursor = conn.execute('SELECT COUNT(*) as count FROM app_launches')
        total_launches = cursor.fetchone()['count']

        # Unique apps
        cursor = conn.execute('SELECT COUNT(DISTINCT app_id) as count FROM app_launches')
        unique_apps = cursor.fetchone()['count']

        # First and last launch
        cursor = conn.execute('SELECT MIN(timestamp) as first, MAX(timestamp) as last FROM app_launches')
        row = cursor.fetchone()

        def convert_timestamp(timestamp_str):
            if not timestamp_str:
                return None
            try:
                dt_utc = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
                unix_timestamp = calendar.timegm(dt_utc.timetuple())
                dt_local = datetime.fromtimestamp(unix_timestamp)

                if time.daylight and time.localtime(unix_timestamp).tm_isdst:
                    tz_offset_seconds = -time.altzone
                else:
                    tz_offset_seconds = -time.timezone

                tz_hours = tz_offset_seconds // 3600
                tz_minutes = abs(tz_offset_seconds % 3600) // 60
                tz_str = f"{tz_hours:+03d}:{tz_minutes:02d}"

                return f"{dt_local.strftime('%Y-%m-%dT%H:%M:%S')}{tz_str}"
            except Exception:
                return timestamp_str

        return {
            'total_launches': total_launches,
            'unique_apps': unique_apps,
            'first_launch': convert_timestamp(row['first']),
            'last_launch': convert_timestamp(row['last'])
        }

    def clear_all_data(self) -> None:
        """Clear all launch data from the database."""
        with self._transaction() as conn:
            conn.execute('DELETE FROM app_launches')

    def close(self) -> None:
        """Close the database connection."""
        if hasattr(self._local, 'connection'):
            self._local.connection.close()
            del self._local.connection
