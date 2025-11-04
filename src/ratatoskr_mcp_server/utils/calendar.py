"""Calendar utilities for accessing Evolution Data Server calendars."""

import os
import sqlite3
import subprocess
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from icalendar import Calendar
import pytz


# Evolution Data Server calendar cache location
EDS_CACHE_DIR = os.path.expanduser("~/.cache/evolution/calendar")
EDS_LOCAL_CALENDAR = os.path.expanduser("~/.local/share/evolution/calendar/system/calendar.ics")


class CalendarEvent:
    """Represents a calendar event."""

    def __init__(
        self,
        uid: str,
        summary: str,
        start: Optional[datetime],
        end: Optional[datetime],
        location: Optional[str] = None,
        description: Optional[str] = None,
        calendar_name: Optional[str] = None,
        calendar_uid: Optional[str] = None,
        all_day: bool = False,
        recurring: bool = False,
        attendees: Optional[List[Dict[str, str]]] = None
    ):
        self.uid = uid
        self.summary = summary
        self.start = start
        self.end = end
        self.location = location
        self.description = description
        self.calendar_name = calendar_name
        self.calendar_uid = calendar_uid
        self.all_day = all_day
        self.recurring = recurring
        self.attendees = attendees or []

    def to_dict(self) -> Dict[str, Any]:
        """Convert event to dictionary."""
        return {
            'uid': self.uid,
            'summary': self.summary,
            'start': self.start.isoformat() if self.start else None,
            'end': self.end.isoformat() if self.end else None,
            'location': self.location,
            'description': self.description,
            'calendar_name': self.calendar_name,
            'calendar_uid': self.calendar_uid,
            'all_day': self.all_day,
            'recurring': self.recurring,
            'attendees': self.attendees
        }


class CalendarManager:
    """Manages access to all calendar sources."""

    def __init__(self, timezone: str = "America/Los_Angeles"):
        """Initialize calendar manager.

        Args:
            timezone: Default timezone for events
        """
        self.timezone = pytz.timezone(timezone)
        self._calendar_sources = None

    def get_calendar_sources(self) -> Dict[str, str]:
        """Get map of calendar UID to display name from Evolution Data Server.

        Returns:
            Dict mapping calendar UID to display name
        """
        if self._calendar_sources is not None:
            return self._calendar_sources

        sources = {}

        # Local calendar
        sources['system-calendar'] = 'Personal'

        try:
            # Query Evolution Data Server for calendar sources via D-Bus
            result = subprocess.run(
                [
                    'gdbus', 'call', '--session',
                    '--dest', 'org.gnome.evolution.dataserver.Sources5',
                    '--object-path', '/org/gnome/evolution/dataserver/SourceManager',
                    '--method', 'org.freedesktop.DBus.ObjectManager.GetManagedObjects'
                ],
                capture_output=True,
                text=True,
                timeout=5
            )

            if result.returncode == 0:
                # Parse the D-Bus response to extract calendar names
                # This is a simple parser - we look for DisplayName and UID fields
                output = result.stdout

                # Extract calendar sources
                import re
                uid_pattern = r"'UID':\s*<'([^']+)'>"
                display_pattern = r"'DisplayName':\s*<'([^']+)'>"
                calendar_pattern = r"'org\.gnome\.evolution\.dataserver\.Source\.Calendar':"

                # Find all UIDs and DisplayNames
                lines = output.split('\n')
                current_uid = None
                current_name = None
                is_calendar = False

                for i, line in enumerate(lines):
                    if "'org.gnome.evolution.dataserver.Source':" in line:
                        # Look for UID in next few lines
                        for j in range(i, min(i + 10, len(lines))):
                            uid_match = re.search(uid_pattern, lines[j])
                            if uid_match:
                                current_uid = uid_match.group(1)
                                break

                        # Look for DisplayName in Data field (it's in the config string)
                        for j in range(i, min(i + 20, len(lines))):
                            if 'DisplayName=' in lines[j]:
                                # Extract DisplayName from config
                                display_match = re.search(r'DisplayName=([^\n\\]+)', lines[j])
                                if display_match:
                                    current_name = display_match.group(1).strip()
                                    break

                    # Check if this source is a calendar
                    if "'Calendar']:" in line or "'org.gnome.evolution.dataserver.Source.Calendar':" in line:
                        is_calendar = True

                    # When we hit a new source, save the previous one if it was a calendar
                    if "'/org/gnome/evolution/dataserver/SourceManager/Source_" in line:
                        if current_uid and current_name and is_calendar and current_uid != 'system-calendar':
                            sources[current_uid] = current_name
                        current_uid = None
                        current_name = None
                        is_calendar = False

                # Save the last one
                if current_uid and current_name and is_calendar and current_uid != 'system-calendar':
                    sources[current_uid] = current_name

        except Exception as e:
            print(f"Warning: Could not query Evolution Data Server: {e}")

        # Add any calendar UIDs we find in cache that aren't in sources
        if os.path.exists(EDS_CACHE_DIR):
            for entry in os.listdir(EDS_CACHE_DIR):
                cache_path = os.path.join(EDS_CACHE_DIR, entry, 'cache.db')
                if os.path.isfile(cache_path) and entry not in sources:
                    sources[entry] = f"Calendar ({entry[:8]})"

        self._calendar_sources = sources
        return sources

    def _parse_eds_datetime(self, dt_str: str) -> Optional[datetime]:
        """Parse Evolution Data Server datetime format (YYYYMMDDHHMMSS).

        Evolution stores times in UTC, so we parse them as UTC and convert to local timezone.

        Args:
            dt_str: Datetime string in EDS format (UTC)

        Returns:
            Datetime object in local timezone or None
        """
        if not dt_str:
            return None

        try:
            # Remove timezone suffix if present
            dt_str = dt_str.split('Z')[0]

            if len(dt_str) == 8:
                # Date only (all-day event) - use local timezone
                dt = datetime.strptime(dt_str, '%Y%m%d')
                return self.timezone.localize(dt)
            elif len(dt_str) >= 14:
                # Date and time - stored in UTC, convert to local timezone
                dt = datetime.strptime(dt_str[:14], '%Y%m%d%H%M%S')
                # Treat as UTC
                import pytz
                dt_utc = pytz.UTC.localize(dt)
                # Convert to local timezone
                return dt_utc.astimezone(self.timezone)
            else:
                return None

        except Exception:
            return None

    def _extract_attendees(self, component) -> List[Dict[str, str]]:
        """Extract attendee information from an iCalendar component.

        Args:
            component: iCalendar VEVENT component

        Returns:
            List of attendee dictionaries with email, name, role, and status
        """
        attendees = []
        attendee_list = component.get('attendee', [])
        if not isinstance(attendee_list, list):
            attendee_list = [attendee_list]

        for attendee in attendee_list:
            attendee_info = {}

            # Extract email from the attendee value (format: mailto:email@example.com)
            if attendee:
                email = str(attendee)
                if email.startswith('mailto:'):
                    attendee_info['email'] = email[7:]  # Remove 'mailto:' prefix
                else:
                    attendee_info['email'] = email

                # Extract parameters (CN, ROLE, PARTSTAT)
                if hasattr(attendee, 'params'):
                    if 'CN' in attendee.params:
                        attendee_info['name'] = str(attendee.params['CN'])
                    if 'ROLE' in attendee.params:
                        attendee_info['role'] = str(attendee.params['ROLE'])
                    if 'PARTSTAT' in attendee.params:
                        attendee_info['status'] = str(attendee.params['PARTSTAT'])

                if attendee_info:
                    attendees.append(attendee_info)

        return attendees

    def _query_local_calendar(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        include_attendees: bool = False
    ) -> List[CalendarEvent]:
        """Query events from local ICS calendar.

        Args:
            start_date: Filter events starting after this date
            end_date: Filter events ending before this date
            include_attendees: Whether to extract attendee information

        Returns:
            List of calendar events
        """
        events = []

        if not os.path.exists(EDS_LOCAL_CALENDAR):
            return events

        try:
            with open(EDS_LOCAL_CALENDAR, 'rb') as f:
                cal = Calendar.from_ical(f.read())

            for component in cal.walk('VEVENT'):
                summary = str(component.get('summary', 'Untitled'))
                uid = str(component.get('uid', ''))
                location = str(component.get('location', '')) if component.get('location') else None
                description = str(component.get('description', '')) if component.get('description') else None

                # Parse start time
                dtstart = component.get('dtstart')
                start_dt = None
                all_day = False

                if dtstart:
                    if hasattr(dtstart.dt, 'hour'):
                        # DateTime
                        start_dt = dtstart.dt
                        if start_dt.tzinfo is None:
                            start_dt = self.timezone.localize(start_dt)
                        start_dt = start_dt.astimezone(self.timezone)
                    else:
                        # Date only (all-day event)
                        start_dt = datetime.combine(dtstart.dt, datetime.min.time())
                        start_dt = self.timezone.localize(start_dt)
                        all_day = True

                # Parse end time
                dtend = component.get('dtend')
                end_dt = None

                if dtend:
                    if hasattr(dtend.dt, 'hour'):
                        end_dt = dtend.dt
                        if end_dt.tzinfo is None:
                            end_dt = self.timezone.localize(end_dt)
                        end_dt = end_dt.astimezone(self.timezone)
                    else:
                        end_dt = datetime.combine(dtend.dt, datetime.min.time())
                        end_dt = self.timezone.localize(end_dt)

                # Filter by date range
                if start_date and end_dt and end_dt < start_date:
                    continue
                if end_date and start_dt and start_dt > end_date:
                    continue

                # Check if recurring
                recurring = component.get('rrule') is not None

                # Parse attendees if requested
                attendees = self._extract_attendees(component) if include_attendees else []

                events.append(CalendarEvent(
                    uid=uid,
                    summary=summary,
                    start=start_dt,
                    end=end_dt,
                    location=location,
                    description=description,
                    calendar_name='Personal',
                    calendar_uid='system-calendar',
                    all_day=all_day,
                    recurring=recurring,
                    attendees=attendees
                ))

        except Exception as e:
            print(f"Error reading local calendar: {e}")

        return events

    def _query_eds_cache(
        self,
        cache_uid: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        include_attendees: bool = False
    ) -> List[CalendarEvent]:
        """Query events from an Evolution Data Server cache database.

        Args:
            cache_uid: Calendar UID
            start_date: Filter events starting after this date
            end_date: Filter events ending before this date
            include_attendees: Whether to extract attendee information

        Returns:
            List of calendar events
        """
        events = []
        cache_path = os.path.join(EDS_CACHE_DIR, cache_uid, 'cache.db')

        if not os.path.exists(cache_path):
            return events

        try:
            conn = sqlite3.connect(cache_path)
            cursor = conn.cursor()

            # Build query - include ECacheOBJ for recurring event expansion
            # We need to fetch recurring events separately to expand them

            # First, get non-recurring events with date filter
            query_non_recurring = "SELECT ECacheUID, summary, occur_start, occur_end, location, description, has_recurrences, ECacheOBJ FROM ECacheObjects WHERE has_recurrences = 0"
            params_non_recurring = []

            if start_date and end_date:
                start_str = start_date.strftime('%Y%m%d%H%M%S')
                end_str = end_date.strftime('%Y%m%d%H%M%S')
                query_non_recurring += " AND occur_start >= ? AND occur_start <= ?"
                params_non_recurring.extend([start_str, end_str])
            elif start_date:
                start_str = start_date.strftime('%Y%m%d%H%M%S')
                query_non_recurring += " AND occur_start >= ?"
                params_non_recurring.append(start_str)
            elif end_date:
                end_str = end_date.strftime('%Y%m%d%H%M%S')
                query_non_recurring += " AND occur_start <= ?"
                params_non_recurring.append(end_str)

            # Execute query for non-recurring events
            cursor.execute(query_non_recurring, params_non_recurring)
            non_recurring_rows = cursor.fetchall()

            # Get recurring events separately (we need to expand these)
            query_recurring = "SELECT ECacheUID, summary, occur_start, occur_end, location, description, has_recurrences, ECacheOBJ FROM ECacheObjects WHERE has_recurrences = 1"
            cursor.execute(query_recurring)
            recurring_rows = cursor.fetchall()

            all_rows = non_recurring_rows + recurring_rows

            sources = self.get_calendar_sources()
            calendar_name = sources.get(cache_uid, f'Calendar ({cache_uid[:8]})')

            for row in all_rows:
                uid, summary, occur_start, occur_end, location, description, has_recurrences, ecache_obj = row

                # If this is a recurring event, parse the VEVENT and expand occurrences
                if has_recurrences and ecache_obj and start_date and end_date:
                    try:
                        # Parse the VEVENT from ECacheOBJ
                        cal = Calendar.from_ical(ecache_obj)
                        for component in cal.walk('VEVENT'):
                            # Get the recurrence rule
                            dtstart = component.get('dtstart')
                            dtend = component.get('dtend')
                            rrule = component.get('rrule')

                            if not dtstart or not rrule:
                                continue

                            # Parse start/end times
                            if hasattr(dtstart.dt, 'hour'):
                                event_start = dtstart.dt
                                all_day = False
                            else:
                                event_start = datetime.combine(dtstart.dt, datetime.min.time())
                                all_day = True

                            # Ensure timezone awareness
                            if event_start.tzinfo is None:
                                event_start = self.timezone.localize(event_start)
                            else:
                                event_start = event_start.astimezone(self.timezone)

                            # Calculate duration
                            if dtend:
                                if hasattr(dtend.dt, 'hour'):
                                    event_end = dtend.dt
                                else:
                                    event_end = datetime.combine(dtend.dt, datetime.min.time())

                                if event_end.tzinfo is None:
                                    event_end = self.timezone.localize(event_end)
                                else:
                                    event_end = event_end.astimezone(self.timezone)

                                duration = event_end - event_start
                            else:
                                duration = timedelta(hours=1)
                                event_end = None

                            # Expand recurrences using rrule
                            from dateutil import rrule as du_rrule

                            # Build rrule from the iCal RRULE
                            rrule_str = rrule.to_ical().decode('utf-8')
                            rule = du_rrule.rrulestr(rrule_str, dtstart=event_start)

                            # Get occurrences within our date range
                            occurrences = rule.between(start_date, end_date, inc=True)

                            # Extract attendees once for all occurrences (if requested)
                            attendees = self._extract_attendees(component) if include_attendees else []

                            # Create event for each occurrence
                            for occurrence in occurrences:
                                occurrence_end = occurrence + duration if event_end else None

                                events.append(CalendarEvent(
                                    uid=uid or '',
                                    summary=summary or component.get('summary', 'Untitled'),
                                    start=occurrence,
                                    end=occurrence_end,
                                    location=location or str(component.get('location', '')) if component.get('location') else None,
                                    description=description or str(component.get('description', '')) if component.get('description') else None,
                                    calendar_name=calendar_name,
                                    calendar_uid=cache_uid,
                                    all_day=all_day,
                                    recurring=True,
                                    attendees=attendees
                                ))
                    except Exception as e:
                        print(f"Error expanding recurring event {uid}: {e}")
                        # Fall back to single occurrence
                        start_dt = self._parse_eds_datetime(occur_start)
                        end_dt = self._parse_eds_datetime(occur_end) if occur_end else None
                        all_day = occur_start and len(occur_start) == 8

                        # Try to extract attendees from ecache_obj (if requested)
                        attendees = []
                        if include_attendees and ecache_obj:
                            try:
                                cal = Calendar.from_ical(ecache_obj)
                                for comp in cal.walk('VEVENT'):
                                    attendees = self._extract_attendees(comp)
                                    break
                            except Exception:
                                pass

                        # Only include if within date range
                        if start_date and end_date and start_dt:
                            if start_dt >= start_date and start_dt <= end_date:
                                events.append(CalendarEvent(
                                    uid=uid or '',
                                    summary=summary or 'Untitled',
                                    start=start_dt,
                                    end=end_dt,
                                    location=location,
                                    description=description,
                                    calendar_name=calendar_name,
                                    calendar_uid=cache_uid,
                                    all_day=all_day,
                                    recurring=True,
                                    attendees=attendees
                                ))
                else:
                    # Non-recurring event - already filtered by SQL query
                    start_dt = self._parse_eds_datetime(occur_start)
                    end_dt = self._parse_eds_datetime(occur_end) if occur_end else None
                    all_day = occur_start and len(occur_start) == 8

                    # Try to extract attendees from ecache_obj (if requested)
                    attendees = []
                    if include_attendees and ecache_obj:
                        try:
                            cal = Calendar.from_ical(ecache_obj)
                            for comp in cal.walk('VEVENT'):
                                attendees = self._extract_attendees(comp)
                                break
                        except Exception:
                            pass

                    events.append(CalendarEvent(
                        uid=uid or '',
                        summary=summary or 'Untitled',
                        start=start_dt,
                        end=end_dt,
                        location=location,
                        description=description,
                        calendar_name=calendar_name,
                        calendar_uid=cache_uid,
                        all_day=all_day,
                        recurring=False,
                        attendees=attendees
                    ))

            conn.close()

        except Exception as e:
            print(f"Error reading cache {cache_uid}: {e}")

        return events

    def get_events(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        calendar_uids: Optional[List[str]] = None,
        include_attendees: bool = False
    ) -> List[CalendarEvent]:
        """Get calendar events from all sources.

        Args:
            start_date: Filter events starting after this date
            end_date: Filter events ending before this date
            calendar_uids: Optional list of calendar UIDs to filter by
            include_attendees: Whether to extract attendee information

        Returns:
            List of calendar events sorted by start time
        """
        all_events = []

        # Query local calendar
        if not calendar_uids or 'system-calendar' in calendar_uids:
            all_events.extend(self._query_local_calendar(start_date, end_date, include_attendees))

        # Query Evolution Data Server caches
        if os.path.exists(EDS_CACHE_DIR):
            for entry in os.listdir(EDS_CACHE_DIR):
                if entry == 'trash':
                    continue

                if calendar_uids and entry not in calendar_uids:
                    continue

                all_events.extend(self._query_eds_cache(entry, start_date, end_date, include_attendees))

        # Sort by start time
        all_events.sort(key=lambda e: e.start if e.start else datetime.max.replace(tzinfo=self.timezone))

        return all_events

    def get_events_for_date(self, date: datetime) -> List[CalendarEvent]:
        """Get all events for a specific date.

        Args:
            date: Date to query

        Returns:
            List of events on that date
        """
        start = self.timezone.localize(datetime.combine(date.date(), datetime.min.time()))
        end = self.timezone.localize(datetime.combine(date.date(), datetime.max.time()))

        return self.get_events(start_date=start, end_date=end)

    def get_upcoming_events(self, days: int = 7) -> List[CalendarEvent]:
        """Get upcoming events for the next N days.

        Args:
            days: Number of days to look ahead

        Returns:
            List of upcoming events
        """
        now = datetime.now(self.timezone)
        end = now + timedelta(days=days)

        return self.get_events(start_date=now, end_date=end)
