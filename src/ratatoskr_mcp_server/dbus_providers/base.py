"""DBus base provider class"""

import dbus
from typing import Any


class DBusProviderBase:
    """Base class to query dbus objects"""

    def __init__(self, bus_name: str, object_path: str):
        self.session_bus = dbus.SessionBus()
        self.proxy = self.session_bus.get_object(bus_name, object_path)
        self.properties_interface = dbus.Interface(
            self.proxy,
            'org.freedesktop.DBus.Properties'
        )

    def get_property(self, interface: str, property_name: str) -> Any:
        """Get a D-Bus property value"""
        try:
            return self.properties_interface.Get(interface, property_name)
        except dbus.DBusException as e:
            raise ValueError(f"Failed to get {property_name}: {e}")

    def set_property(self, interface: str, property_name: str, value: Any) -> None:
        """Set a D-Bus property value"""
        try:
            self.properties_interface.Set(interface, property_name, value)
        except dbus.DBusException as e:
            raise ValueError(f"Failed to set {property_name}: {e}")
