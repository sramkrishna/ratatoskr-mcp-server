#!/usr/bin/env python3
"""
Test client to query GNOME Shell version via D-Bus.
This verifies that our D-Bus implementation works correctly.
"""

import sys
import os
import json
from typing import Dict, Any, Optional


def test_dbus_gnome_query() -> Dict[str, Any]:
    """Test querying GNOME Shell via D-Bus directly."""
    print("Testing D-Bus GNOME Shell query...")

    try:
        import dbus
        session_bus = dbus.SessionBus()
        shell_proxy = session_bus.get_object('org.gnome.Shell', '/org/gnome/Shell')
        # Use the Properties interface to get properties
        properties_interface = dbus.Interface(shell_proxy, 'org.freedesktop.DBus.Properties')

        # Get GNOME Shell version
        gnome_version = properties_interface.Get('org.gnome.Shell', 'ShellVersion')

        # Get additional properties if available
        try:
            mode = properties_interface.Get('org.gnome.Shell', 'Mode')
        except:
            mode = "Unknown"

        try:
            overview_visible = properties_interface.Get('org.gnome.Shell', 'OverviewVisible')
        except:
            overview_visible = None

        return {
            "status": "success",
            "gnome_shell_version": str(gnome_version),
            "mode": str(mode),
            "overview_visible": overview_visible,
            "method": "dbus"
        }

    except ImportError:
        return {
            "status": "error",
            "error": "dbus-python not available",
            "method": "dbus"
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "method": "dbus"
        }


def test_environment_info() -> Dict[str, Any]:
    """Test environment variable detection."""
    print("Testing environment variable detection...")

    return {
        "desktop_session": os.environ.get('DESKTOP_SESSION', 'Not set'),
        "xdg_current_desktop": os.environ.get('XDG_CURRENT_DESKTOP', 'Not set'),
        "xdg_session_desktop": os.environ.get('XDG_SESSION_DESKTOP', 'Not set'),
        "session_manager": os.environ.get('SESSION_MANAGER', 'Not set'),
        "gdmsession": os.environ.get('GDMSESSION', 'Not set'),
    }


def test_gtk_info() -> Dict[str, Any]:
    """Test GTK version detection."""
    print("Testing GTK version detection...")

    try:
        import gi
        gi.require_version('Gtk', '3.0')
        from gi.repository import Gtk

        return {
            "status": "success",
            "gtk_major": Gtk.get_major_version(),
            "gtk_minor": Gtk.get_minor_version(),
            "gtk_micro": Gtk.get_micro_version(),
            "gtk_version": f"{Gtk.get_major_version()}.{Gtk.get_minor_version()}.{Gtk.get_micro_version()}",
            "toolkit": "GTK 3"
        }
    except Exception as e:
        try:
            import gi
            gi.require_version('Gtk', '4.0')
            from gi.repository import Gtk

            return {
                "status": "success",
                "gtk_major": Gtk.get_major_version(),
                "gtk_minor": Gtk.get_minor_version(),
                "gtk_micro": Gtk.get_micro_version(),
                "gtk_version": f"{Gtk.get_major_version()}.{Gtk.get_minor_version()}.{Gtk.get_micro_version()}",
                "toolkit": "GTK 4"
            }
        except Exception as e2:
            return {
                "status": "error",
                "error": f"GTK 3: {str(e)}, GTK 4: {str(e2)}"
            }


def test_mcp_server_resource() -> Dict[str, Any]:
    """Test our MCP server's GNOME resource provider."""
    print("Testing MCP server resource provider...")

    try:
        # Import our server components
        sys.path.insert(0, '/var/home/sri/Projects/ratatoskr-mcp-server/src')
        from ratatoskr_mcp_server.server import GnomeDesktopProvider

        import asyncio

        async def test_provider():
            provider = GnomeDesktopProvider()
            resource_data = await provider.get_resource()

            if resource_data.is_error:
                return {
                    "status": "error",
                    "error": resource_data.error
                }
            else:
                return {
                    "status": "success",
                    "data": resource_data.content,
                    "mime_type": resource_data.mime_type
                }

        return asyncio.run(test_provider())

    except Exception as e:
        return {
            "status": "error",
            "error": str(e)
        }


def main():
    """Run all tests and display results."""
    print("=" * 60)
    print("GNOME Shell D-Bus Test Client")
    print("=" * 60)

    tests = [
        ("D-Bus GNOME Query", test_dbus_gnome_query),
        ("Environment Variables", test_environment_info),
        ("GTK Version", test_gtk_info),
        ("MCP Server Resource", test_mcp_server_resource)
    ]

    results = {}

    for test_name, test_func in tests:
        print(f"\n{test_name}:")
        print("-" * 40)
        try:
            result = test_func()
            results[test_name] = result
            print(json.dumps(result, indent=2))
        except Exception as e:
            error_result = {"status": "error", "error": str(e)}
            results[test_name] = error_result
            print(json.dumps(error_result, indent=2))

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    for test_name, result in results.items():
        status = result.get('status', 'unknown')
        if status == 'success':
            print(f"✓ {test_name}: SUCCESS")
        else:
            print(f"✗ {test_name}: FAILED - {result.get('error', 'Unknown error')}")

    # Check if running in GNOME
    env_result = results.get("Environment Variables", {})
    desktop = env_result.get("xdg_current_desktop", "").lower()
    session = env_result.get("desktop_session", "").lower()

    print(f"\nDetected Desktop Environment:")
    if "gnome" in desktop or "gnome" in session:
        print("✓ GNOME detected")
    else:
        print(f"⚠ Non-GNOME environment detected: {desktop}")


if __name__ == "__main__":
    main()