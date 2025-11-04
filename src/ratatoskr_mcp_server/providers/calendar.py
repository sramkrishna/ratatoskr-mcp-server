"""Provider for calendar events."""

from datetime import datetime, timedelta
import pytz
from typing import Optional

from ratatoskr_mcp_server.providers.base import ResourceProvider
from ratatoskr_mcp_server.resource_manager import ResourceData
from ratatoskr_mcp_server.utils.calendar import CalendarManager


class CalendarProvider(ResourceProvider):
    """Provides calendar event data from all sources."""

    def __init__(self, timezone: str = "America/Los_Angeles"):
        """Initialize calendar provider.

        Args:
            timezone: Default timezone for events
        """
        self.calendar_mgr = CalendarManager(timezone=timezone)
        self.timezone = pytz.timezone(timezone)

    async def get_resource(self) -> ResourceData:
        """Get upcoming calendar events (next 7 days).

        Returns:
            ResourceData with upcoming events
        """
        try:
            events = self.calendar_mgr.get_upcoming_events(days=7)

            events_data = [event.to_dict() for event in events]

            return ResourceData(
                content={
                    'total_events': len(events),
                    'events': events_data,
                    'calendars': self.calendar_mgr.get_calendar_sources()
                }
            )

        except Exception as e:
            return ResourceData(
                content={},
                error=f'Failed to get calendar events: {str(e)}'
            )

    async def query_events(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        days_ahead: Optional[int] = None,
        calendar_uids: Optional[list] = None
    ) -> ResourceData:
        """Query calendar events with filters.

        Args:
            start_date: Start date (ISO format or 'today', 'yesterday', 'tomorrow')
            end_date: End date (ISO format)
            days_ahead: Number of days ahead to query (alternative to end_date)
            calendar_uids: List of calendar UIDs to filter by

        Returns:
            ResourceData with filtered events
        """
        try:
            now = datetime.now(self.timezone)

            # Parse start_date
            if start_date:
                if start_date.lower() == 'today':
                    start_dt = now.replace(hour=0, minute=0, second=0, microsecond=0)
                elif start_date.lower() == 'yesterday':
                    start_dt = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
                elif start_date.lower() == 'tomorrow':
                    start_dt = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
                else:
                    # Parse ISO format
                    start_dt = datetime.fromisoformat(start_date)
                    if start_dt.tzinfo is None:
                        start_dt = self.timezone.localize(start_dt)
            else:
                start_dt = now

            # Parse end_date
            if end_date:
                end_dt = datetime.fromisoformat(end_date)
                if end_dt.tzinfo is None:
                    end_dt = self.timezone.localize(end_dt)
            elif days_ahead:
                end_dt = start_dt + timedelta(days=days_ahead)
                # Set to end of the last day
                end_dt = end_dt.replace(hour=23, minute=59, second=59)
            else:
                # Default to end of day for single day query
                end_dt = start_dt.replace(hour=23, minute=59, second=59)

            # Query events
            events = self.calendar_mgr.get_events(
                start_date=start_dt,
                end_date=end_dt,
                calendar_uids=calendar_uids
            )

            events_data = [event.to_dict() for event in events]

            return ResourceData(
                content={
                    'query': {
                        'start_date': start_dt.isoformat(),
                        'end_date': end_dt.isoformat(),
                        'calendar_uids': calendar_uids
                    },
                    'total_events': len(events),
                    'events': events_data,
                    'calendars': self.calendar_mgr.get_calendar_sources()
                }
            )

        except Exception as e:
            return ResourceData(
                content={},
                error=f'Failed to query calendar events: {str(e)}'
            )

    async def query_events_with_attendees(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        days_ahead: Optional[int] = None,
        calendar_uids: Optional[list] = None
    ) -> ResourceData:
        """Query calendar events with attendee/participant information.

        Args:
            start_date: Start date (ISO format or 'today', 'yesterday', 'tomorrow')
            end_date: End date (ISO format)
            days_ahead: Number of days ahead to query (alternative to end_date)
            calendar_uids: List of calendar UIDs to filter by

        Returns:
            ResourceData with filtered events including attendee details
        """
        try:
            now = datetime.now(self.timezone)

            # Parse start_date
            if start_date:
                if start_date.lower() == 'today':
                    start_dt = now.replace(hour=0, minute=0, second=0, microsecond=0)
                elif start_date.lower() == 'yesterday':
                    start_dt = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
                elif start_date.lower() == 'tomorrow':
                    start_dt = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
                else:
                    # Parse ISO format
                    start_dt = datetime.fromisoformat(start_date)
                    if start_dt.tzinfo is None:
                        start_dt = self.timezone.localize(start_dt)
            else:
                start_dt = now

            # Parse end_date
            if end_date:
                end_dt = datetime.fromisoformat(end_date)
                if end_dt.tzinfo is None:
                    end_dt = self.timezone.localize(end_dt)
            elif days_ahead:
                end_dt = start_dt + timedelta(days=days_ahead)
                # Set to end of the last day
                end_dt = end_dt.replace(hour=23, minute=59, second=59)
            else:
                # Default to end of day for single day query
                end_dt = start_dt.replace(hour=23, minute=59, second=59)

            # Query events with attendees
            events = self.calendar_mgr.get_events(
                start_date=start_dt,
                end_date=end_dt,
                calendar_uids=calendar_uids,
                include_attendees=True
            )

            events_data = [event.to_dict() for event in events]

            return ResourceData(
                content={
                    'query': {
                        'start_date': start_dt.isoformat(),
                        'end_date': end_dt.isoformat(),
                        'calendar_uids': calendar_uids
                    },
                    'total_events': len(events),
                    'events': events_data,
                    'calendars': self.calendar_mgr.get_calendar_sources()
                }
            )

        except Exception as e:
            return ResourceData(
                content={},
                error=f'Failed to query calendar events with attendees: {str(e)}'
            )

    def close(self) -> None:
        """Clean up resources."""
        pass
