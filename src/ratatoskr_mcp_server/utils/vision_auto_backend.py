"""Auto-detect vision backend based on network/environment."""

import os
import socket
import ipaddress
from typing import Optional

try:
    from gi.repository import Gio, GLib
    DBUS_AVAILABLE = True
except ImportError:
    DBUS_AVAILABLE = False


def get_current_ssid() -> Optional[str]:
    """Get current WiFi SSID via D-Bus."""
    if not DBUS_AVAILABLE:
        return None

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

        # Get primary connection
        primary_connection_path = nm_proxy.get_cached_property('PrimaryConnection')
        if not primary_connection_path:
            return None

        primary_path = primary_connection_path.unpack()
        if not primary_path or primary_path == '/':
            return None

        # Get the active connection
        active_conn_proxy = Gio.DBusProxy.new_sync(
            connection,
            Gio.DBusProxyFlags.NONE,
            None,
            'org.freedesktop.NetworkManager',
            primary_path,
            'org.freedesktop.NetworkManager.Connection.Active',
            None
        )

        # Check if it's a WiFi connection
        conn_type = active_conn_proxy.get_cached_property('Type')
        if not conn_type or conn_type.unpack() != '802-11-wireless':
            return None

        # Get the specific device path
        devices = active_conn_proxy.get_cached_property('Devices')
        if not devices:
            return None

        device_paths = devices.unpack()
        if not device_paths:
            return None

        device_path = device_paths[0]

        # Get WiFi device proxy
        wifi_device_proxy = Gio.DBusProxy.new_sync(
            connection,
            Gio.DBusProxyFlags.NONE,
            None,
            'org.freedesktop.NetworkManager',
            device_path,
            'org.freedesktop.NetworkManager.Device.Wireless',
            None
        )

        # Get active access point
        active_ap_path = wifi_device_proxy.get_cached_property('ActiveAccessPoint')
        if not active_ap_path:
            return None

        ap_path = active_ap_path.unpack()
        if not ap_path or ap_path == '/':
            return None

        # Get access point proxy
        ap_proxy = Gio.DBusProxy.new_sync(
            connection,
            Gio.DBusProxyFlags.NONE,
            None,
            'org.freedesktop.NetworkManager',
            ap_path,
            'org.freedesktop.NetworkManager.AccessPoint',
            None
        )

        # Get SSID (returns bytes)
        ssid_variant = ap_proxy.get_cached_property('Ssid')
        if not ssid_variant:
            return None

        ssid_bytes = ssid_variant.unpack()
        if not ssid_bytes:
            return None

        # Convert bytes to string
        return bytes(ssid_bytes).decode('utf-8', errors='ignore')

    except Exception as e:
        # Silently fail and return None
        return None


def can_reach_host(host: str, port: int = 11434, timeout: float = 1.0) -> bool:
    """Check if a host is reachable."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except:
        return False


def get_current_subnet() -> Optional[str]:
    """Get current IP subnet (e.g., '10.0.0.0/24') via D-Bus."""
    if not DBUS_AVAILABLE:
        return None

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

        # Get primary connection
        primary_connection_path = nm_proxy.get_cached_property('PrimaryConnection')
        if not primary_connection_path:
            return None

        primary_path = primary_connection_path.unpack()
        if not primary_path or primary_path == '/':
            return None

        # Get the active connection
        active_conn_proxy = Gio.DBusProxy.new_sync(
            connection,
            Gio.DBusProxyFlags.NONE,
            None,
            'org.freedesktop.NetworkManager',
            primary_path,
            'org.freedesktop.NetworkManager.Connection.Active',
            None
        )

        # Get IP4Config path
        ip4_config_path = active_conn_proxy.get_cached_property('Ip4Config')
        if not ip4_config_path:
            return None

        ip4_path = ip4_config_path.unpack()
        if not ip4_path or ip4_path == '/':
            return None

        # Get IP4Config proxy
        ip4_proxy = Gio.DBusProxy.new_sync(
            connection,
            Gio.DBusProxyFlags.NONE,
            None,
            'org.freedesktop.NetworkManager',
            ip4_path,
            'org.freedesktop.NetworkManager.IP4Config',
            None
        )

        # Get address data
        address_data = ip4_proxy.get_cached_property('AddressData')
        if not address_data:
            return None

        addresses = address_data.unpack()
        if not addresses:
            return None

        # Get first address
        first_addr = addresses[0]
        if 'address' not in first_addr or 'prefix' not in first_addr:
            return None

        ip_str = first_addr['address']
        prefix = first_addr['prefix']

        # Create network from IP and prefix
        interface = ipaddress.IPv4Interface(f"{ip_str}/{prefix}")
        network = interface.network

        return str(network)  # e.g., "10.0.0.0/24"

    except Exception as e:
        # Silently fail and return None
        return None


def auto_select_backend(
    home_subnet: str = None,
    home_sentinel_host: str = None,
    home_ssid: str = None,
    ollama_host: str = "nvidia-machine",
    ollama_port: int = 11434
) -> dict:
    """
    Automatically select the best vision backend based on environment.

    Priority:
    1. If on home network and Ollama reachable → use 'ollama' (fastest, GPU)
    2. If OpenVINO available → use 'openvino' (fast, local NPU)
    3. Fallback → use 'llamafile' (slow, always works)

    Args:
        home_subnet: Home network subnet (e.g., '10.0.0.0/24')
        home_sentinel_host: Sentinel host that must be reachable at home (e.g., 'lothlorien')
        home_ssid: Home WiFi SSID (optional, less reliable than subnet)
        ollama_host: Hostname/IP of machine running Ollama
        ollama_port: Port Ollama is listening on (default: 11434)

    Returns:
        Dict with:
        - backend: 'ollama', 'openvino', or 'llamafile'
        - reason: Why this backend was selected
        - details: Additional info
    """
    # Get environment config
    home_subnet = home_subnet or os.getenv("HOME_SUBNET")
    home_sentinel_host = home_sentinel_host or os.getenv("HOME_SENTINEL_HOST")
    home_ssid = home_ssid or os.getenv("HOME_WIFI_SSID")
    ollama_host = os.getenv("OLLAMA_HOST", ollama_host).replace("http://", "").split(":")[0]

    # Gather current environment info via D-Bus
    current_ssid = get_current_ssid()
    current_subnet = get_current_subnet()

    # Determine if we're at home (need BOTH checks to pass for safety)
    checks = []
    on_home_network = False

    if home_subnet and current_subnet:
        subnet_match = (current_subnet == home_subnet)
        checks.append(f"subnet: {current_subnet} {'==' if subnet_match else '!='} {home_subnet}")
        if subnet_match:
            # Check for sentinel host if configured
            if home_sentinel_host:
                sentinel_reachable = can_reach_host(home_sentinel_host, port=22, timeout=0.5)  # Try SSH port
                checks.append(f"sentinel '{home_sentinel_host}': {'reachable' if sentinel_reachable else 'not reachable'}")
                on_home_network = sentinel_reachable
            else:
                # No sentinel configured, subnet match is enough
                on_home_network = True
    elif home_ssid and current_ssid:
        # Fallback to SSID check if subnet not configured
        ssid_match = (current_ssid == home_ssid)
        checks.append(f"ssid: '{current_ssid}' {'==' if ssid_match else '!='} '{home_ssid}'")
        on_home_network = ssid_match

    check_details = ', '.join(checks) if checks else 'no home network checks configured'

    # Try Ollama first (if on home network)
    if on_home_network:
        if can_reach_host(ollama_host, ollama_port, timeout=1.0):
            return {
                'backend': 'ollama',
                'reason': f'At home ({check_details}), Ollama server reachable',
                'details': {
                    'ssid': current_ssid,
                    'ollama_host': ollama_host,
                    'expected_speed': 'fastest (GPU-accelerated)'
                }
            }
        else:
            reason = f"On home network but Ollama not reachable at {ollama_host}:{ollama_port}"
    else:
        reason = f"Not on home network (connected to '{current_ssid}', home is '{home_ssid}')"

    # Check if OpenVINO is available
    openvino_model = os.getenv("OPENVINO_VISION_MODEL", os.path.expanduser("~/models/qwen2-vl-2b-openvino"))
    if os.path.exists(openvino_model):
        try:
            import optimum.intel
            return {
                'backend': 'openvino',
                'reason': f'{reason}, using local OpenVINO',
                'details': {
                    'ssid': current_ssid,
                    'model_path': openvino_model,
                    'expected_speed': 'fast (NPU-accelerated)'
                }
            }
        except ImportError:
            pass

    # Fallback to llamafile
    return {
        'backend': 'llamafile',
        'reason': f'{reason}, fallback to llamafile',
        'details': {
            'ssid': current_ssid,
            'expected_speed': 'slow (CPU-only)'
        }
    }


# Example usage
if __name__ == "__main__":
    import json

    # Configure your home network
    selection = auto_select_backend(
        home_ssid="YourHomeWiFiName",  # Replace with your actual SSID
        ollama_host="192.168.1.100"     # Replace with your Nvidia machine IP/hostname
    )

    print(json.dumps(selection, indent=2))
