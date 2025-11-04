"""GNOME notification utilities for Ratatoskr MCP server."""

import logging
from typing import Optional, List
from enum import Enum

try:
    from gi.repository import Gio, GLib
    DBUS_AVAILABLE = True
except ImportError:
    DBUS_AVAILABLE = False

logger = logging.getLogger(__name__)


class NotificationUrgency(Enum):
    """Notification urgency levels."""
    LOW = 0
    NORMAL = 1
    CRITICAL = 2


class NotificationManager:
    """Manager for GNOME desktop notifications via D-Bus."""

    def __init__(self):
        """Initialize notification manager."""
        if not DBUS_AVAILABLE:
            logger.warning("D-Bus not available, notifications will fail")
            self.available = False
            return

        try:
            self.bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
            self.available = True
            logger.info("Notification manager initialized")
        except Exception as e:
            logger.error(f"Failed to connect to D-Bus: {e}")
            self.available = False

    def send_notification(
        self,
        title: str,
        body: str,
        urgency: NotificationUrgency = NotificationUrgency.NORMAL,
        icon: Optional[str] = None,
        actions: Optional[List[tuple]] = None,
        timeout: int = 5000,
        category: Optional[str] = None,
    ) -> dict:
        """Send a GNOME notification via D-Bus.

        Args:
            title: Notification title
            body: Notification body text
            urgency: Urgency level (LOW, NORMAL, CRITICAL)
            icon: Icon name (e.g., 'dialog-information', 'mail-unread')
            actions: List of (action_id, label) tuples
            timeout: Timeout in milliseconds (-1 = default, 0 = never)
            category: Category hint (e.g., 'email', 'im', 'network')

        Returns:
            Dict with success status and notification ID
        """
        if not self.available:
            return {
                "success": False,
                "error": "D-Bus notifications not available"
            }

        try:
            # Build D-Bus method call
            # org.freedesktop.Notifications.Notify
            # (String app_name, UInt32 replaces_id, String app_icon,
            #  String summary, String body, Array actions,
            #  Dict hints, Int32 timeout)

            app_name = "Hugin Agent"
            replaces_id = 0  # 0 = new notification
            app_icon = icon or "dialog-information"
            summary = title

            # Actions format: ["action1", "Label1", "action2", "Label2"]
            action_list = []
            if actions:
                for action_id, label in actions:
                    action_list.extend([action_id, label])

            # Hints dictionary
            hints = {
                "urgency": GLib.Variant('y', urgency.value),
            }
            if category:
                hints["category"] = GLib.Variant('s', category)

            # Make D-Bus call
            result = self.bus.call_sync(
                'org.freedesktop.Notifications',
                '/org/freedesktop/Notifications',
                'org.freedesktop.Notifications',
                'Notify',
                GLib.Variant('(susssasa{sv}i)', (
                    app_name,
                    replaces_id,
                    app_icon,
                    summary,
                    body,
                    action_list,
                    hints,
                    timeout
                )),
                GLib.VariantType('(u)'),
                Gio.DBusCallFlags.NONE,
                -1,
                None
            )

            notification_id = result.unpack()[0]
            logger.info(f"Sent notification: {title} (ID: {notification_id})")

            return {
                "success": True,
                "notification_id": notification_id,
                "title": title,
            }

        except Exception as e:
            logger.error(f"Failed to send notification: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    def send_urgent_notification(self, title: str, body: str, icon: str = "dialog-warning") -> dict:
        """Send a critical/urgent notification that demands attention.

        Args:
            title: Notification title
            body: Notification body
            icon: Icon name

        Returns:
            Dict with success status
        """
        return self.send_notification(
            title=title,
            body=body,
            urgency=NotificationUrgency.CRITICAL,
            icon=icon,
            timeout=0,  # Don't auto-dismiss
        )

    def send_info_notification(self, title: str, body: str, icon: str = "dialog-information") -> dict:
        """Send a normal informational notification.

        Args:
            title: Notification title
            body: Notification body
            icon: Icon name

        Returns:
            Dict with success status
        """
        return self.send_notification(
            title=title,
            body=body,
            urgency=NotificationUrgency.NORMAL,
            icon=icon,
        )

    @classmethod
    def is_available(cls) -> bool:
        """Check if notifications are available."""
        if not DBUS_AVAILABLE:
            return False

        try:
            bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
            # Try to call GetCapabilities to verify service exists
            bus.call_sync(
                'org.freedesktop.Notifications',
                '/org/freedesktop/Notifications',
                'org.freedesktop.Notifications',
                'GetCapabilities',
                None,
                GLib.VariantType('(as)'),
                Gio.DBusCallFlags.NONE,
                1000,  # 1 second timeout
                None
            )
            return True
        except Exception:
            return False


# Common notification icons
class NotificationIcon:
    """Common GNOME notification icons."""
    INFO = "dialog-information"
    WARNING = "dialog-warning"
    ERROR = "dialog-error"
    QUESTION = "dialog-question"

    # Specific icons
    MAIL = "mail-unread"
    CALENDAR = "x-office-calendar"
    DOWNLOAD = "folder-download"
    NETWORK = "network-idle"
    SOFTWARE = "system-software-update"
    ALERT = "dialog-warning"
