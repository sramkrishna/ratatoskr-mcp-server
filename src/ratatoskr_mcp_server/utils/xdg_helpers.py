"""Helpers for xdg-open integration (email, calendar)."""

import os
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import quote

# Default video call URL from environment (Google Meet, Zoom, Jitsi, Teams, etc.)
DEFAULT_VIDEO_CALL_URL = os.getenv("DEFAULT_VIDEO_CALL_URL")


def compose_email(
    to: str,
    subject: str = "",
    body: str = "",
    cc: Optional[str] = None,
    bcc: Optional[str] = None
) -> dict:
    """Open email composer with pre-filled fields using xdg-open.

    Args:
        to: Recipient email address
        subject: Email subject
        body: Email body text
        cc: CC recipients (comma-separated)
        bcc: BCC recipients (comma-separated)

    Returns:
        Dictionary with 'success' boolean and optional 'error' message.
    """
    try:
        # Build mailto URL
        mailto_parts = [f"mailto:{to}"]
        params = []

        if subject:
            params.append(f"subject={quote(subject)}")
        if body:
            params.append(f"body={quote(body)}")
        if cc:
            params.append(f"cc={quote(cc)}")
        if bcc:
            params.append(f"bcc={quote(bcc)}")

        if params:
            mailto_parts.append("?" + "&".join(params))

        mailto_url = "".join(mailto_parts)

        # Open with xdg-open
        result = subprocess.run(
            ['xdg-open', mailto_url],
            capture_output=True,
            text=True,
            timeout=10
        )

        if result.returncode == 0:
            return {"success": True}
        else:
            return {"success": False, "error": f"xdg-open failed: {result.stderr}"}

    except subprocess.TimeoutExpired:
        return {"success": False, "error": "xdg-open timed out"}
    except FileNotFoundError:
        return {"success": False, "error": "xdg-open not found"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def create_calendar_event(
    title: str,
    start_time: str,
    end_time: str,
    description: str = "",
    location: str = "",
    all_day: bool = False,
    video_call_url: Optional[str] = None
) -> dict:
    """Create calendar event by opening .ics file with xdg-open.

    Args:
        title: Event title/summary
        start_time: Start time (ISO format: YYYY-MM-DDTHH:MM:SS or YYYY-MM-DD for all-day)
        end_time: End time (same format as start_time)
        description: Event description
        location: Event location
        all_day: Whether this is an all-day event
        video_call_url: If provided, adds this video call URL to the event (Google Meet, Zoom, Jitsi, Teams, etc.).
                       Only added when explicitly provided - not added automatically.

    Returns:
        Dictionary with 'success' boolean and optional 'error' message.
    """
    try:
        # Note: We don't automatically use DEFAULT_VIDEO_CALL_URL here
        # The LLM can read that env var and decide when to use it based on context

        # Parse and format times
        if all_day:
            # All-day events use DATE format (YYYYMMDD)
            start_dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
            end_dt = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
            dtstart = f"DTSTART;VALUE=DATE:{start_dt.strftime('%Y%m%d')}"
            dtend = f"DTEND;VALUE=DATE:{end_dt.strftime('%Y%m%d')}"
        else:
            # Regular events use DATETIME format (YYYYMMDDTHHMMSSZ)
            start_dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
            end_dt = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
            dtstart = f"DTSTART:{start_dt.strftime('%Y%m%dT%H%M%S')}Z"
            dtend = f"DTEND:{end_dt.strftime('%Y%m%dT%H%M%S')}Z"

        # Generate unique ID
        uid = f"{start_dt.strftime('%Y%m%d%H%M%S')}-{hash(title) % 10000}@ratatoskr"

        # Build iCalendar content
        ics_lines = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//Ratatoskr MCP Server//NONSGML v1.0//EN",
            "BEGIN:VEVENT",
            f"UID:{uid}",
            f"DTSTAMP:{datetime.utcnow().strftime('%Y%m%dT%H%M%S')}Z",
            dtstart,
            dtend,
            f"SUMMARY:{title}",
        ]

        # Add video call URL if specified
        if video_call_url:
            # Add video call link to description
            video_note = f"\\n\\nVideo call: {video_call_url}"
            if description:
                description += video_note
            else:
                description = f"Virtual meeting{video_note}"

        if description:
            # Escape special characters and handle line folding for long descriptions
            desc_escaped = description.replace('\\', '\\\\').replace(',', '\\,').replace(';', '\\;').replace('\n', '\\n')
            ics_lines.append(f"DESCRIPTION:{desc_escaped}")

        if location:
            loc_escaped = location.replace('\\', '\\\\').replace(',', '\\,').replace(';', '\\;')
            ics_lines.append(f"LOCATION:{loc_escaped}")

        # Add conference data for video call
        if video_call_url:
            # Add standard CONFERENCE property (RFC 7986) with the video call URL
            ics_lines.append(f"CONFERENCE;VALUE=URI;FEATURE=VIDEO:{video_call_url}")

        ics_lines.extend([
            "END:VEVENT",
            "END:VCALENDAR"
        ])

        ics_content = "\r\n".join(ics_lines)

        # Write to temporary file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.ics', delete=False) as f:
            f.write(ics_content)
            temp_path = f.name

        # Open with xdg-open
        result = subprocess.run(
            ['xdg-open', temp_path],
            capture_output=True,
            text=True,
            timeout=10
        )

        if result.returncode == 0:
            return {
                "success": True,
                "ics_path": temp_path,
                "note": "Calendar application opened. Temporary .ics file will be cleaned up later."
            }
        else:
            # Clean up temp file on failure
            Path(temp_path).unlink(missing_ok=True)
            return {"success": False, "error": f"xdg-open failed: {result.stderr}"}

    except ValueError as e:
        return {"success": False, "error": f"Invalid date/time format: {e}"}
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "xdg-open timed out"}
    except FileNotFoundError:
        return {"success": False, "error": "xdg-open not found"}
    except Exception as e:
        return {"success": False, "error": str(e)}
