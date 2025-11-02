"""Provider for app launch statistics."""

from typing import Optional
from pathlib import Path
from ratatoskr_mcp_server.providers.base import ResourceProvider
from ratatoskr_mcp_server.resource_manager import ResourceData
from ratatoskr_mcp_server.utils.app_launch_db import AppLaunchDB
from ratatoskr_mcp_server.monitors import AppLaunchMonitor


class AppLaunchStatsProvider(ResourceProvider):
    """Provides statistics about application launches."""

    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize the provider.

        Args:
            db_path: Path to the database. If None, uses default location.
        """
        self.db = AppLaunchDB(db_path)
        self.monitor = AppLaunchMonitor(db_path)

    async def get_resource(self) -> ResourceData:
        """
        Get app launch statistics and usage information.

        Returns:
            ResourceData with:
            - tracked_launches: Actual tracked app launches (accurate but may be limited)
              - overall_stats: Total launches, unique apps, date range
              - top_apps: Most frequently launched apps (top 20)
              - recent_launches: Most recent launches (last 20)
            - gnome_usage_patterns: GNOME's native usage scores (historical context)
              - Note: These are usage scores, NOT launch counts
              - High score = frequently/recently used, NOT necessarily launched often
        """
        try:
            # Get actual tracked launch statistics
            overall_stats = self.db.get_stats()
            top_apps = self.db.get_top_apps(limit=20)
            recent_launches = self.db.get_recent_launches(limit=20)

            # Get GNOME's usage scores for context (separate from launch tracking)
            gnome_scores = self.monitor.get_gnome_app_scores()[:20]

            return ResourceData(
                content={
                    'tracked_launches': {
                        'overall_stats': overall_stats,
                        'top_apps': top_apps,
                        'recent_launches': recent_launches,
                        'note': 'These are actual tracked app launches. Includes both user-initiated launches and automated/scheduled activity (e.g., backup apps running scheduled tasks). Data collection started when tracking began.'
                    },
                    'gnome_usage_patterns': {
                        'apps': gnome_scores,
                        'note': 'GNOME usage scores indicate frequency and recency of USE, not launch count. High score means the app is frequently/recently active.'
                    }
                }
            )

        except Exception as e:
            return ResourceData(
                content={},
                error=f"Failed to get app launch statistics: {str(e)}"
            )

    def close(self) -> None:
        """Clean up database connection."""
        self.monitor.close()
        self.db.close()
