"""Helpers for xdg-open integration (email, calendar)."""

import os
import subprocess
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Optional, List
from urllib.parse import quote

try:
    from gi.repository import Gio, GLib
    DBUS_AVAILABLE = True
except ImportError:
    DBUS_AVAILABLE = False


def open_file_manager_at(file_path: str) -> bool:
    """
    Open file manager showing the specified file using D-Bus.

    Args:
        file_path: Absolute path to file to show

    Returns:
        True if successful, False otherwise
    """
    if not DBUS_AVAILABLE:
        return False

    try:
        # Use org.freedesktop.FileManager1 D-Bus interface
        # This is the standard interface for file managers
        connection = Gio.bus_get_sync(Gio.BusType.SESSION, None)

        file_manager = Gio.DBusProxy.new_sync(
            connection,
            Gio.DBusProxyFlags.NONE,
            None,
            'org.freedesktop.FileManager1',
            '/org/freedesktop/FileManager1',
            'org.freedesktop.FileManager1',
            None
        )

        # ShowItems method takes a list of file URIs and a startup ID
        file_uri = f"file://{file_path}"
        file_manager.call_sync(
            'ShowItems',
            GLib.Variant('(ass)', ([file_uri], '')),
            Gio.DBusCallFlags.NONE,
            -1,
            None
        )

        return True
    except Exception as e:
        # Fallback to subprocess if D-Bus fails
        try:
            subprocess.Popen(
                ['nautilus', '--select', file_path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True
            )
            return True
        except:
            return False

# Default video call URL from environment (Google Meet, Zoom, Jitsi, Teams, etc.)
DEFAULT_VIDEO_CALL_URL = os.getenv("DEFAULT_VIDEO_CALL_URL")


def compose_email(
    to: str,
    subject: str = "",
    body: str = "",
    cc: Optional[str] = None,
    bcc: Optional[str] = None,
    attachments: Optional[List[str]] = None
) -> dict:
    """Open email composer with pre-filled fields and optional attachments.

    If more than 5 files are attached, they will be automatically zipped into a single archive.

    Args:
        to: Recipient email address
        subject: Email subject
        body: Email body text
        cc: CC recipients (comma-separated)
        bcc: BCC recipients (comma-separated)
        attachments: List of file paths to attach (absolute paths)

    Returns:
        Dictionary with 'success' boolean and optional 'error' message.
    """
    zip_file_path = None

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

        # Handle attachments
        files_to_attach = []
        zipped = False

        if attachments:
            # Validate all files first
            validated_paths = []
            for attachment_path in attachments:
                # Convert to absolute path
                abs_path = os.path.abspath(os.path.expanduser(attachment_path))

                # Check if file exists
                if not os.path.exists(abs_path):
                    return {"success": False, "error": f"Attachment not found: {attachment_path}"}

                # Check if it's a file (not a directory)
                if not os.path.isfile(abs_path):
                    return {"success": False, "error": f"Attachment is not a file: {attachment_path}"}

                validated_paths.append(abs_path)

            # If more than 5 attachments, create a zip file
            if len(validated_paths) > 5:
                # Create human-readable zip filename
                # Use email subject if provided, otherwise use a friendly default
                if subject:
                    # Sanitize subject for filename (remove/replace invalid chars)
                    safe_subject = "".join(c if c.isalnum() or c in (' ', '-', '_') else '_' for c in subject)
                    # Limit length and strip whitespace
                    safe_subject = safe_subject[:50].strip().replace(' ', '_')
                    zip_filename = f"{safe_subject}.zip"
                else:
                    # Friendly default based on file types
                    extensions = set(os.path.splitext(p)[1].lower() for p in validated_paths)
                    if all(ext in {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'} for ext in extensions):
                        zip_filename = "photos.zip"
                    elif all(ext in {'.pdf', '.doc', '.docx', '.txt', '.odt'} for ext in extensions):
                        zip_filename = "documents.zip"
                    else:
                        zip_filename = "email_attachments.zip"

                zip_file_path = os.path.join(tempfile.gettempdir(), zip_filename)

                # Use ZIP_DEFLATED for maximum compatibility across all platforms
                # This is the standard DEFLATE algorithm, supported by:
                # - Windows 10/11 built-in zip support
                # - macOS built-in Archive Utility
                # - Linux unzip utilities
                # - All major archive tools (7-Zip, WinRAR, etc.)
                with zipfile.ZipFile(zip_file_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    for file_path in validated_paths:
                        # Add file to zip with just its basename (not full path)
                        zipf.write(file_path, arcname=os.path.basename(file_path))

                files_to_attach = [zip_file_path]
                zipped = True
            else:
                files_to_attach = validated_paths

            # NOTE: We DON'T add attach= parameters to mailto URLs because:
            # 1. Not part of RFC 6068 (mailto: standard)
            # 2. Evolution doesn't reliably support it
            # 3. Causes multiple composer windows to open
            # Instead, we return the attachment paths for the user to manually attach

        if params:
            mailto_parts.append("?" + "&".join(params))

        mailto_url = "".join(mailto_parts)

        # Try Evolution directly first (more reliable than xdg-open)
        try:
            result = subprocess.run(
                ['evolution', mailto_url],
                capture_output=True,
                text=True,
                timeout=10,
                start_new_session=True  # Detach from parent process
            )
        except FileNotFoundError:
            # Evolution not found, try xdg-open as fallback
            result = subprocess.run(
                ['xdg-open', mailto_url],
                capture_output=True,
                text=True,
                timeout=10
            )

        # Evolution/xdg-open launches in background and may return non-zero
        # This is normal behavior, treat as success
        response = {"success": True}

        # Return attachment info for manual attachment
        if attachments:
            if zipped:
                response["attachments_to_add"] = [zip_file_path]
                response["zipped"] = True
                response["zip_file"] = zip_file_path
                response["original_file_count"] = len(attachments)
                response["note"] = f"Composer opened. Please manually attach: {zip_file_path} (contains {len(attachments)} files)"

                # Open Nautilus showing the zip file for easy drag & drop
                if open_file_manager_at(zip_file_path):
                    response["nautilus_opened"] = True
            else:
                response["attachments_to_add"] = files_to_attach
                response["note"] = f"Composer opened. Please manually attach {len(files_to_attach)} file(s)"

                # Open Nautilus showing the attachment file(s)
                if len(files_to_attach) == 1:
                    # Single file - select it in Nautilus
                    if open_file_manager_at(files_to_attach[0]):
                        response["nautilus_opened"] = True
                else:
                    # Multiple files - show first file (Nautilus will show directory)
                    if open_file_manager_at(files_to_attach[0]):
                        response["nautilus_opened"] = True

        # Add debug info if there was stderr but we're treating it as success
        if result.returncode != 0 and result.stderr:
            response["debug_info"] = f"xdg-open returned {result.returncode}, stderr: {result.stderr}"

        return response

    except subprocess.TimeoutExpired:
        # Clean up zip file on failure
        if zip_file_path and os.path.exists(zip_file_path):
            os.unlink(zip_file_path)
        return {"success": False, "error": "Email composer timed out"}
    except FileNotFoundError as e:
        # Clean up zip file on failure
        if zip_file_path and os.path.exists(zip_file_path):
            os.unlink(zip_file_path)
        return {"success": False, "error": f"Command not found: {e}"}
    except Exception as e:
        # Clean up zip file on failure
        if zip_file_path and os.path.exists(zip_file_path):
            os.unlink(zip_file_path)
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
            # Regular events use DATETIME format (YYYYMMDDTHHMMSSZ in UTC)
            # Parse the datetime with timezone info
            start_dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
            end_dt = datetime.fromisoformat(end_time.replace('Z', '+00:00'))

            # Convert to UTC before formatting with Z suffix (which means UTC)
            from datetime import timezone
            # If naive (no timezone), assume local time
            if start_dt.tzinfo is None:
                start_dt = start_dt.astimezone()  # Adds local timezone
            if end_dt.tzinfo is None:
                end_dt = end_dt.astimezone()  # Adds local timezone

            start_utc = start_dt.astimezone(timezone.utc)
            end_utc = end_dt.astimezone(timezone.utc)

            dtstart = f"DTSTART:{start_utc.strftime('%Y%m%dT%H%M%S')}Z"
            dtend = f"DTEND:{end_utc.strftime('%Y%m%dT%H%M%S')}Z"

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

        # Handle video call URL - put it in location field for better calendar integration
        if video_call_url:
            # Use video URL as location (Zoom, Google Meet, etc.)
            location = video_call_url
            # Also add to description if there's already a description
            if description:
                video_note = f"\\n\\nVideo call: {video_call_url}"
                description += video_note

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
