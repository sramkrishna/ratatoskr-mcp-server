"""WiFi network scanning via NetworkManager D-Bus."""

import time
from typing import List, Dict, Optional

try:
    from gi.repository import Gio, GLib
    DBUS_AVAILABLE = True
except ImportError:
    DBUS_AVAILABLE = False


def scan_wifi_networks(
    rescan: bool = True,
    filter_pattern: str = None,
    min_signal_strength: int = 0
) -> Dict:
    """
    Scan for available WiFi networks.

    Args:
        rescan: Whether to trigger a new scan (default: True)
        filter_pattern: Optional pattern to filter SSIDs (case-insensitive)
        min_signal_strength: Minimum signal strength (0-100, default: 0)

    Returns:
        Dict with:
        - success: bool
        - networks: List of network dicts (sorted by signal strength)
        - current_ssid: Currently connected SSID (if any)
        - error: Error message (if failed)
    """
    if not DBUS_AVAILABLE:
        return {
            'success': False,
            'error': 'D-Bus/GLib not available'
        }

    try:
        # Connect to NetworkManager via D-Bus
        connection = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)

        # Get NetworkManager proxy
        nm_proxy = Gio.DBusProxy.new_sync(
            connection,
            Gio.DBusProxyFlags.NONE,
            None,
            'org.freedesktop.NetworkManager',
            '/org/freedesktop/NetworkManager',
            'org.freedesktop.NetworkManager',
            None
        )

        # Get all devices
        devices_variant = nm_proxy.get_cached_property('Devices')
        if not devices_variant:
            return {
                'success': False,
                'error': 'No network devices found'
            }

        device_paths = devices_variant.unpack()

        # Find WiFi device
        wifi_device_path = None
        for device_path in device_paths:
            device_proxy = Gio.DBusProxy.new_sync(
                connection,
                Gio.DBusProxyFlags.NONE,
                None,
                'org.freedesktop.NetworkManager',
                device_path,
                'org.freedesktop.NetworkManager.Device',
                None
            )

            device_type = device_proxy.get_cached_property('DeviceType')
            if device_type and device_type.unpack() == 2:  # 2 = NM_DEVICE_TYPE_WIFI
                wifi_device_path = device_path
                break

        if not wifi_device_path:
            return {
                'success': False,
                'error': 'No WiFi device found'
            }

        # Get WiFi device proxy
        wifi_device_proxy = Gio.DBusProxy.new_sync(
            connection,
            Gio.DBusProxyFlags.NONE,
            None,
            'org.freedesktop.NetworkManager',
            wifi_device_path,
            'org.freedesktop.NetworkManager.Device.Wireless',
            None
        )

        # Trigger scan if requested
        if rescan:
            try:
                wifi_device_proxy.call_sync(
                    'RequestScan',
                    GLib.Variant('(a{sv})', ({},)),
                    Gio.DBusCallFlags.NONE,
                    5000,  # 5 second timeout
                    None
                )
                # Give scan time to complete
                time.sleep(2)
            except Exception as e:
                # Scan might fail if one is already in progress, that's ok
                pass

        # Get access points
        access_points_variant = wifi_device_proxy.get_cached_property('AccessPoints')
        if not access_points_variant:
            return {
                'success': True,
                'networks': [],
                'current_ssid': None
            }

        ap_paths = access_points_variant.unpack()

        # Get currently connected SSID
        current_ssid = None
        active_ap_variant = wifi_device_proxy.get_cached_property('ActiveAccessPoint')
        if active_ap_variant:
            active_ap_path = active_ap_variant.unpack()
            if active_ap_path and active_ap_path != '/':
                try:
                    active_ap_proxy = Gio.DBusProxy.new_sync(
                        connection,
                        Gio.DBusProxyFlags.NONE,
                        None,
                        'org.freedesktop.NetworkManager',
                        active_ap_path,
                        'org.freedesktop.NetworkManager.AccessPoint',
                        None
                    )
                    ssid_variant = active_ap_proxy.get_cached_property('Ssid')
                    if ssid_variant:
                        ssid_bytes = ssid_variant.unpack()
                        if ssid_bytes:
                            current_ssid = bytes(ssid_bytes).decode('utf-8', errors='ignore')
                except:
                    pass

        # Parse access points
        networks = []
        seen_ssids = set()  # De-duplicate by SSID

        for ap_path in ap_paths:
            try:
                ap_proxy = Gio.DBusProxy.new_sync(
                    connection,
                    Gio.DBusProxyFlags.NONE,
                    None,
                    'org.freedesktop.NetworkManager',
                    ap_path,
                    'org.freedesktop.NetworkManager.AccessPoint',
                    None
                )

                # Get SSID
                ssid_variant = ap_proxy.get_cached_property('Ssid')
                if not ssid_variant:
                    continue

                ssid_bytes = ssid_variant.unpack()
                if not ssid_bytes:
                    continue

                ssid = bytes(ssid_bytes).decode('utf-8', errors='ignore')

                # Skip if already seen (take strongest signal for each SSID)
                if ssid in seen_ssids:
                    continue

                # Apply filters
                if filter_pattern and filter_pattern.lower() not in ssid.lower():
                    continue

                # Get signal strength (0-100)
                strength_variant = ap_proxy.get_cached_property('Strength')
                strength = strength_variant.unpack() if strength_variant else 0

                if strength < min_signal_strength:
                    continue

                # Get security flags
                flags_variant = ap_proxy.get_cached_property('Flags')
                wpa_flags_variant = ap_proxy.get_cached_property('WpaFlags')
                rsn_flags_variant = ap_proxy.get_cached_property('RsnFlags')

                flags = flags_variant.unpack() if flags_variant else 0
                wpa_flags = wpa_flags_variant.unpack() if wpa_flags_variant else 0
                rsn_flags = rsn_flags_variant.unpack() if rsn_flags_variant else 0

                # Determine security type
                if rsn_flags != 0:
                    security = 'WPA2/WPA3'
                elif wpa_flags != 0:
                    security = 'WPA'
                elif flags & 0x1:  # NM_802_11_AP_FLAGS_PRIVACY
                    security = 'WEP'
                else:
                    security = 'Open'

                # Get frequency
                frequency_variant = ap_proxy.get_cached_property('Frequency')
                frequency = frequency_variant.unpack() if frequency_variant else 0

                # Determine band (2.4 GHz vs 5 GHz)
                if frequency >= 5000:
                    band = '5 GHz'
                elif frequency >= 2400:
                    band = '2.4 GHz'
                else:
                    band = 'Unknown'

                networks.append({
                    'ssid': ssid,
                    'signal_strength': strength,
                    'security': security,
                    'frequency': frequency,
                    'band': band,
                    'connected': ssid == current_ssid
                })

                seen_ssids.add(ssid)

            except Exception as e:
                # Skip this AP if there's an error
                continue

        # Sort by signal strength (strongest first)
        networks.sort(key=lambda x: x['signal_strength'], reverse=True)

        return {
            'success': True,
            'networks': networks,
            'current_ssid': current_ssid,
            'total_networks': len(networks)
        }

    except Exception as e:
        return {
            'success': False,
            'error': f'Network scan failed: {str(e)}'
        }


def get_signal_quality_description(strength: int) -> str:
    """Convert signal strength (0-100) to human-readable description."""
    if strength >= 80:
        return 'Excellent'
    elif strength >= 60:
        return 'Good'
    elif strength >= 40:
        return 'Fair'
    elif strength >= 20:
        return 'Weak'
    else:
        return 'Very Weak'
