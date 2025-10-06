"""Main MCP server implementation for GNOME integration."""

import asyncio
import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, Optional, Sequence

from mcp.server import Server
from mcp.server.models import InitializationOptions
from mcp.server.lowlevel.server import NotificationOptions
import mcp.server.stdio
import mcp.types as types

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ratatoskr-mcp-server")


# Resource Management Classes

@dataclass
class ResourceData:
    """Container for resource data and metadata."""
    content: Dict[str, Any]
    mime_type: str = "application/json"
    encoding: str = "utf-8"
    error: Optional[str] = None
    
    @property
    def is_error(self) -> bool:
        return self.error is not None


class ResourceProvider(ABC):
    """Abstract base class for resource providers."""
    
    @abstractmethod
    async def get_resource(self) -> ResourceData:
        """Fetch and return resource data."""
        pass


class GnomeDesktopProvider(ResourceProvider):
    """Provides GNOME desktop information."""
    
    async def get_resource(self) -> ResourceData:
        try:
            import os
            from ratatoskr_mcp_server.dbus_providers.gnome_shell import GnomeShellProvider

            # Check environment variable for GNOME session
            desktop_session = os.environ.get('DESKTOP_SESSION', '')
            xdg_current_desktop = os.environ.get('XDG_CURRENT_DESKTOP', '')

            # Try to get GTK version via GI
            gtk_version = "Unknown"
            try:
                import gi
                gi.require_version('Gtk', '3.0')
                from gi.repository import Gtk
                gtk_version = f"{Gtk.get_major_version()}.{Gtk.get_minor_version()}.{Gtk.get_micro_version()}"
            except (ImportError, ValueError):
                # Try GTK 4 if GTK 3 fails
                try:
                    import gi
                    gi.require_version('Gtk', '4.0')
                    from gi.repository import Gtk
                    gtk_version = f"{Gtk.get_major_version()}.{Gtk.get_minor_version()}.{Gtk.get_micro_version()}"
                except (ImportError, ValueError):
                    pass

            # Get GNOME Shell info via D-Bus provider
            gnome_info = {}
            try:
                shell_provider = GnomeShellProvider()
                gnome_info = shell_provider.get_all_info()
            except Exception:
                gnome_info = {
                    'version': 'Unknown',
                    'mode': 'Unknown',
                    'overview_visible': False
                }

            # Determine if running GNOME
            is_gnome = any(x.lower() in ['gnome', 'ubuntu'] for x in [desktop_session, xdg_current_desktop])

            return ResourceData(
                content={
                    "desktop_environment": "GNOME" if is_gnome else xdg_current_desktop or "Unknown",
                    "gnome_shell_version": gnome_info.get('version', 'Unknown'),
                    "gnome_shell_mode": gnome_info.get('mode', 'Unknown'),
                    "overview_visible": gnome_info.get('overview_visible', False),
                    "gtk_version": gtk_version,
                    "desktop_session": desktop_session,
                    "xdg_current_desktop": xdg_current_desktop,
                    "is_gnome_session": is_gnome
                }
            )

        except Exception as e:
            return ResourceData(
                content={},
                error=f"Failed to get GNOME desktop info: {str(e)}"
            )


class DistroInfoProvider(ResourceProvider):
    """Provides distribution information from /etc/os-release."""
    
    async def get_resource(self) -> ResourceData:
        try:
            with open('/etc/os-release', 'r') as f:
                os_info = {}
                for line in f:
                    line = line.strip()
                    if '=' in line and not line.startswith('#'):
                        key, value = line.split('=', 1)
                        os_info[key] = value.strip('"')
                
                return ResourceData(
                    content={
                        "name": os_info.get('NAME', 'Unknown'),
                        "version": os_info.get('VERSION', 'Unknown'),
                        "version_id": os_info.get('VERSION_ID', 'Unknown'),
                        "pretty_name": os_info.get('PRETTY_NAME', 'Unknown'),
                        "id": os_info.get('ID', 'Unknown'),
                        "build_id": os_info.get('BUILD_ID', 'Unknown')
                    }
                )
        except FileNotFoundError:
            return ResourceData(
                content={},
                error="/etc/os-release not found"
            )
        except Exception as e:
            return ResourceData(
                content={},
                error=f"Failed to read OS info: {str(e)}"
            )


class ResourceManager:
    """Manages URI to resource provider mapping."""
    
    def __init__(self):
        self._providers: Dict[str, ResourceProvider] = {
            "ratatoskr://gnome/desktop": GnomeDesktopProvider(),
            "ratatoskr://distro/osinfo": DistroInfoProvider(),
        }
    
    async def get_resource(self, uri: str) -> ResourceData:
        """Get resource data for the given URI."""
        provider = self._providers.get(uri)
        if not provider:
            return ResourceData(
                content={},
                error=f"Unknown resource: {uri}"
            )
        
        return await provider.get_resource()
    
    def list_uris(self) -> list[str]:
        """List all available resource URIs."""
        return list(self._providers.keys())


class ResourceSerializer:
    """Converts ResourceData objects to wire format."""
    
    @staticmethod
    def to_json(resource_data: ResourceData) -> str:
        """Convert ResourceData to JSON string."""
        if resource_data.is_error:
            return json.dumps({"error": resource_data.error}, indent=2)
        
        return json.dumps(resource_data.content, indent=2)
    
    @staticmethod
    def to_dict(resource_data: ResourceData) -> Dict[str, Any]:
        """Convert ResourceData to dictionary."""
        if resource_data.is_error:
            return {"error": resource_data.error}
        
        return resource_data.content


# Initialize resource manager
resource_manager = ResourceManager()
serializer = ResourceSerializer()

server = Server("ratatoskr-mcp-server")


@server.list_resources()
async def handle_list_resources() -> list[types.Resource]:
    """List available resources."""
    return [
        types.Resource(
            uri="ratatoskr://gnome/desktop",
            name="GNOME Desktop Environment",
            description="Access to GNOME desktop settings and information",
            mimeType="application/json",
        ),
        types.Resource(
            uri="ratatoskr://distro/osinfo",
            name="Distribution Info",
            description="Display the version of the distro you are running",
            mimeType="application/json",
        )
    ]


@server.read_resource()
async def handle_read_resource(uri: types.AnyUrl) -> str:
    """Read a resource using the resource management system."""
    resource_data = await resource_manager.get_resource(str(uri))
    
    if resource_data.is_error:
        raise ValueError(resource_data.error)
    
    return serializer.to_json(resource_data)


@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    """List available GNOME tools."""
    return [
        types.Tool(
            name="get_desktop_info",
            description="Get information about the GNOME desktop environment",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": [],
            },
        ),
    ]


@server.call_tool()
async def handle_call_tool(
    name: str, arguments: dict[str, Any] | None
) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    """Handle tool calls for GNOME operations."""
    if name == "get_desktop_info":
        # Use the resource provider to get desktop info
        resource_data = await resource_manager.get_resource("ratatoskr://gnome/desktop")

        if resource_data.is_error:
            return [
                types.TextContent(
                    type="text",
                    text=f"Error: {resource_data.error}",
                )
            ]

        return [
            types.TextContent(
                type="text",
                text=serializer.to_json(resource_data),
            )
        ]
    else:
        raise ValueError(f"Unknown tool: {name}")


async def main() -> None:
    """Run the MCP server."""
    options = InitializationOptions(
        server_name="ratatoskr-mcp-server",
        server_version="0.1.0",
        capabilities=server.get_capabilities(
            notification_options=NotificationOptions(),
            experimental_capabilities={},
        ),
    )
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, options)


def cli_main() -> None:
    """CLI entry point for the MCP server."""
    asyncio.run(main())


if __name__ == "__main__":
    cli_main()
