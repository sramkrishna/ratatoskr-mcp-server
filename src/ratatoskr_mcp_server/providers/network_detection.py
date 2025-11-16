"""Provider for network detection and environment awareness."""

from ratatoskr_mcp_server.providers.base import ResourceProvider
from ratatoskr_mcp_server.resource_manager import ResourceData
from ratatoskr_mcp_server.utils.vision_auto_backend import (
    get_current_ssid,
    get_current_subnet,
    can_reach_host,
    auto_select_backend
)
import os


class NetworkDetectionProvider(ResourceProvider):
    """Provides network detection and recommended backend selection."""

    async def get_resource(self) -> ResourceData:
        """
        Detect current network environment and recommend backends.

        Returns:
            ResourceData with network info and backend recommendations
        """
        try:
            # Gather network info
            current_ssid = get_current_ssid()
            current_subnet = get_current_subnet()

            # Get home network config
            home_subnet = os.getenv("HOME_SUBNET")
            home_sentinel_host = os.getenv("HOME_SENTINEL_HOST")
            home_ssid = os.getenv("HOME_WIFI_SSID")
            ollama_host_env = os.getenv("OLLAMA_HOST", "nvidia-machine")
            ollama_host = ollama_host_env.replace("http://", "").split(":")[0]

            # Check network status
            on_home_network = False
            network_checks = []

            if home_subnet and current_subnet:
                subnet_match = (current_subnet == home_subnet)
                network_checks.append({
                    'check': 'subnet',
                    'expected': home_subnet,
                    'actual': current_subnet,
                    'match': subnet_match
                })

                if subnet_match and home_sentinel_host:
                    sentinel_reachable = can_reach_host(home_sentinel_host, port=22, timeout=0.5)
                    network_checks.append({
                        'check': 'sentinel_host',
                        'host': home_sentinel_host,
                        'reachable': sentinel_reachable
                    })
                    on_home_network = sentinel_reachable
                elif subnet_match:
                    on_home_network = True
            elif home_ssid and current_ssid:
                ssid_match = (current_ssid == home_ssid)
                network_checks.append({
                    'check': 'ssid',
                    'expected': home_ssid,
                    'actual': current_ssid,
                    'match': ssid_match
                })
                on_home_network = ssid_match

            # Check available backends
            ollama_reachable = can_reach_host(ollama_host, port=11434, timeout=1.0) if on_home_network else False

            openvino_model = os.getenv("OPENVINO_VISION_MODEL", os.path.expanduser("~/models/qwen2-vl-2b-openvino"))
            openvino_available = os.path.exists(openvino_model)

            # Get recommended backend
            backend_selection = auto_select_backend(
                home_subnet=home_subnet,
                home_sentinel_host=home_sentinel_host,
                home_ssid=home_ssid,
                ollama_host=ollama_host
            )

            return ResourceData(
                content={
                    'network': {
                        'current_ssid': current_ssid,
                        'current_subnet': current_subnet,
                        'on_home_network': on_home_network,
                        'checks': network_checks
                    },
                    'backends': {
                        'ollama': {
                            'host': ollama_host,
                            'reachable': ollama_reachable,
                            'available': ollama_reachable
                        },
                        'openvino': {
                            'model_path': openvino_model,
                            'available': openvino_available
                        },
                        'llamafile': {
                            'available': True  # Always available as fallback
                        }
                    },
                    'recommended_backend': backend_selection['backend'],
                    'recommendation_reason': backend_selection['reason'],
                    'recommendation_details': backend_selection.get('details', {})
                }
            )

        except Exception as e:
            return ResourceData(
                content={},
                error=f"Network detection failed: {str(e)}"
            )

    def close(self) -> None:
        """Clean up resources."""
        pass
