"""Main MCP server implementation for GNOME integration."""

import asyncio
import logging
from typing import Any

from mcp.server import Server
from mcp.server.models import InitializationOptions
from mcp.server.lowlevel.server import NotificationOptions
import mcp.server.stdio
import mcp.types as types

from ratatoskr_mcp_server.resource_manager import ResourceManager, ResourceSerializer
from ratatoskr_mcp_server.providers import (
    GnomeDesktopProvider,
    GnomeExtensionsProvider,
    GnomeFavoriteAppsProvider,
    GnomeKeybindingsProvider,
    DistroInfoProvider,
    AppLaunchStatsProvider,
    ProjectFilesProvider,
    FileStatisticsProvider,
    FileSearchProvider,
    DocumentContentProvider,
    ImageAnalyzerProvider,
    FaceManagerProvider,
)
from ratatoskr_mcp_server.monitors import AppLaunchMonitor, DBusLaunchMonitor, SystemdLaunchMonitor

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ratatoskr-mcp-server")


# Initialize app launch monitor (will be started in main())
app_launch_monitor = None

# Initialize resource manager with providers
resource_manager = ResourceManager({
    "ratatoskr://gnome/desktop": GnomeDesktopProvider(),
    "ratatoskr://gnome/extensions": GnomeExtensionsProvider(),
    "ratatoskr://gnome/favorite-apps": GnomeFavoriteAppsProvider(),
    "ratatoskr://gnome/keybindings": GnomeKeybindingsProvider(),
    "ratatoskr://gnome/app-stats": AppLaunchStatsProvider(),
    "ratatoskr://tracker/project-files": ProjectFilesProvider(),
    "ratatoskr://tracker/file-stats": FileStatisticsProvider(),
    "ratatoskr://distro/osinfo": DistroInfoProvider(),
})

# Initialize file search provider (needs to handle parameters, so not in resource_manager)
file_search_provider = FileSearchProvider()

# Initialize document content provider (needs file_path parameter)
document_content_provider = DocumentContentProvider()

# Initialize image analyzer provider (needs image_path parameter)
image_analyzer_provider = ImageAnalyzerProvider()

# Initialize face manager provider (needs action parameter)
face_manager_provider = FaceManagerProvider()

serializer = ResourceSerializer()
server = Server("ratatoskr-mcp-server")


@server.list_resources()
async def handle_list_resources() -> list[types.Resource]:
    """List all available resources."""
    return [
        types.Resource(
            uri="ratatoskr://gnome/desktop",
            name="GNOME Desktop Environment",
            description="Access to GNOME desktop settings and information",
            mimeType="application/json",
        ),
        types.Resource(
            uri="ratatoskr://gnome/extensions",
            name="GNOME Desktop Extensions",
            description="Information about GNOME extensions",
            mimeType="application/json",
        ),
        types.Resource(
            uri="ratatoskr://gnome/favorite-apps",
            name="GNOME Favorite Apps",
            description="Favorite/pinned apps on the GNOME dash",
            mimeType="application/json",
        ),
        types.Resource(
            uri="ratatoskr://gnome/keybindings",
            name="GNOME Keybindings",
            description="GNOME keyboard shortcuts and keybindings",
            mimeType="application/json",
        ),
        types.Resource(
            uri="ratatoskr://gnome/app-stats",
            name="App Launch Statistics",
            description="Statistics about application launches (frequency, recent launches)",
            mimeType="application/json",
        ),
        types.Resource(
            uri="ratatoskr://tracker/project-files",
            name="Project File Activity",
            description="Recent file activity in project directories from TinySPARQL (GNOME LocalSearch)",
            mimeType="application/json",
        ),
        types.Resource(
            uri="ratatoskr://tracker/file-stats",
            name="File Statistics & Storage Analysis",
            description="System-wide file statistics, largest files, old files, and housekeeping suggestions from TinySPARQL",
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
        types.Tool(
            name="get_distro_info",
            description="Get information about the Linux distribution (name, version, ID, etc.)",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": [],
            },
        ),
        types.Tool(
            name="get_gnome_extensions",
            description="Get information about installed GNOME extensions (enabled, disabled, counts)",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": [],
            },
        ),
        types.Tool(
            name="get_favorite_apps",
            description="Get favorite/pinned apps from the GNOME dash with human-readable names",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": [],
            },
        ),
        types.Tool(
            name="get_keybindings",
            description="Get all GNOME keyboard shortcuts and keybindings from all schemas",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": [],
            },
        ),
        types.Tool(
            name="get_app_launch_stats",
            description="Get statistics about application launches including frequency, top apps, and recent launches",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": [],
            },
        ),
        types.Tool(
            name="get_project_files",
            description="Get recent file activity in project directories from TinySPARQL (files modified in last 7 days)",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": [],
            },
        ),
        types.Tool(
            name="get_file_statistics",
            description="Get system-wide file statistics, storage analysis, and housekeeping suggestions from TinySPARQL",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": [],
            },
        ),
        types.Tool(
            name="search_files",
            description="Search for files by type, location, size, and modification date using TinySPARQL. Useful for finding files to organize or clean up.",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_type": {
                        "type": "string",
                        "description": "Type of files to search for: 'pdf', 'image', 'video', 'audio', 'document', 'spreadsheet', 'presentation', 'archive', 'iso'",
                    },
                    "directory": {
                        "type": "string",
                        "description": "Directory path to search in (e.g., '/home/user/Downloads' or '~/Downloads'). If not specified, searches all indexed directories.",
                    },
                    "min_size_mb": {
                        "type": "number",
                        "description": "Minimum file size in megabytes",
                    },
                    "max_size_mb": {
                        "type": "number",
                        "description": "Maximum file size in megabytes",
                    },
                    "min_modified_date": {
                        "type": "string",
                        "description": "Minimum modification date in YYYY-MM-DD format (e.g., '2025-10-01')",
                    },
                    "max_modified_date": {
                        "type": "string",
                        "description": "Maximum modification date in YYYY-MM-DD format (e.g., '2025-10-31')",
                    },
                    "limit": {
                        "type": "number",
                        "description": "Maximum number of results to return (default: 100)",
                    },
                },
                "required": [],
            },
        ),
        types.Tool(
            name="extract_document_content",
            description="Extract text content and metadata from a document file (PDF, image, text file, etc.) using LocalSearch native extractors. This leverages the same sandboxed extraction system used by GNOME for indexing.",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Absolute path to the file to extract content from (e.g., '/home/user/Documents/report.pdf' or '~/Downloads/presentation.pdf')",
                    },
                },
                "required": ["file_path"],
            },
        ),
        types.Tool(
            name="analyze_image",
            description="Analyze an image using a local vision LLM to generate a detailed description. The description is written to the image's EXIF/XMP metadata and indexed by LocalSearch, making it searchable. Uses on-device AI for privacy. Requires: container built (./scripts/build-llamafile-container.sh) and model downloaded (./scripts/download-vision-model.sh).",
            inputSchema={
                "type": "object",
                "properties": {
                    "image_path": {
                        "type": "string",
                        "description": "Path to the image file to analyze (supports .jpg, .jpeg, .png, .gif, .bmp, .webp)",
                    },
                    "prompt": {
                        "type": "string",
                        "description": "Optional custom prompt for analysis (uses default accessibility-focused prompt if not provided)",
                    },
                    "write_metadata": {
                        "type": "boolean",
                        "description": "Whether to write the description to image metadata (default: true)",
                    },
                },
                "required": ["image_path"],
            },
        ),
        types.Tool(
            name="analyze_images_batch",
            description="Analyze multiple images in batch using a local vision LLM. Generates descriptions for each image and writes them to EXIF/XMP metadata. Uses on-device AI for privacy. Maximum 10 images per batch.",
            inputSchema={
                "type": "object",
                "properties": {
                    "image_paths": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of image file paths to analyze (maximum 10)",
                    },
                    "prompt": {
                        "type": "string",
                        "description": "Optional custom prompt for analysis (applies to all images)",
                    },
                    "write_metadata": {
                        "type": "boolean",
                        "description": "Whether to write descriptions to image metadata (default: true)",
                    },
                },
                "required": ["image_paths"],
            },
        ),
        types.Tool(
            name="move_files",
            description="Move files to a destination directory. Maximum 50 files per operation. Only operates on user directories (no system files). Files can be moved for organization purposes.",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_paths": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of file paths to move (maximum 50 files)",
                    },
                    "destination": {
                        "type": "string",
                        "description": "Destination directory path",
                    },
                    "overwrite": {
                        "type": "boolean",
                        "description": "Whether to overwrite existing files at destination (default: false)",
                    },
                },
                "required": ["file_paths", "destination"],
            },
        ),
        types.Tool(
            name="copy_files",
            description="Copy files to a destination directory. Maximum 100 files per operation. Only operates on user directories (no system files). Useful for backing up or duplicating files.",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_paths": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of file paths to copy (maximum 100 files)",
                    },
                    "destination": {
                        "type": "string",
                        "description": "Destination directory path",
                    },
                    "overwrite": {
                        "type": "boolean",
                        "description": "Whether to overwrite existing files at destination (default: false)",
                    },
                },
                "required": ["file_paths", "destination"],
            },
        ),
        types.Tool(
            name="trash_files",
            description="Move files to the trash/recycle bin (SAFE deletion - files can be restored). Maximum 10 files per operation. Does NOT permanently delete files. Only operates on user directories.",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_paths": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of file paths to move to trash (maximum 10 files)",
                    },
                },
                "required": ["file_paths"],
            },
        ),
        types.Tool(
            name="rename_file",
            description="Rename a single file. Only operates on user directories (no system files). The file stays in the same directory with a new name.",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to the file to rename",
                    },
                    "new_name": {
                        "type": "string",
                        "description": "New filename (just the name, not a full path)",
                    },
                },
                "required": ["file_path", "new_name"],
            },
        ),
        types.Tool(
            name="create_directory",
            description="Create a new directory. Only operates on user directories (no system files). Can optionally create parent directories if they don't exist.",
            inputSchema={
                "type": "object",
                "properties": {
                    "directory_path": {
                        "type": "string",
                        "description": "Path to the directory to create",
                    },
                    "parents": {
                        "type": "boolean",
                        "description": "If true, create parent directories as needed (like mkdir -p). Default: false",
                    },
                },
                "required": ["directory_path"],
            },
        ),
        types.Tool(
            name="remove_directory",
            description="Remove an empty directory (SAFE deletion - directory must be empty). Only operates on user directories (no system files). For non-empty directories, move files to trash first.",
            inputSchema={
                "type": "object",
                "properties": {
                    "directory_path": {
                        "type": "string",
                        "description": "Path to the directory to remove (must be empty)",
                    },
                },
                "required": ["directory_path"],
            },
        ),
        types.Tool(
            name="manage_faces",
            description="Manage face registration and recognition using local ChromaDB. Register family members and identify them in photos. Uses on-device AI for privacy. Actions: register (add person), identify (find people in image), list (show registered people), remove (delete person).",
            inputSchema={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "description": "Action to perform: 'register' (add new person), 'identify' (find people in image), 'list' (show all registered people), 'remove' (delete person)",
                        "enum": ["register", "identify", "list", "remove"],
                    },
                    "person_name": {
                        "type": "string",
                        "description": "Name of the person (required for 'register' and 'remove' actions)",
                    },
                    "image_path": {
                        "type": "string",
                        "description": "Path to image file (required for 'register' and 'identify' actions). For registration, image must contain exactly one face.",
                    },
                    "replace_existing": {
                        "type": "boolean",
                        "description": "Whether to replace existing face registrations for this person (default: false). Only used with 'register' action.",
                    },
                    "confidence_threshold": {
                        "type": "number",
                        "description": "Similarity threshold for face identification, 0.0-1.0 (default: 0.6). Lower values are more strict. Only used with 'identify' action.",
                    },
                },
                "required": ["action"],
            },
        ),
    ]


@server.call_tool()
async def handle_call_tool(
    name: str, arguments: dict[str, Any] | None
) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    """Handle tool calls for GNOME operations."""

    # Handle search_files separately as it takes parameters
    if name == "search_files":
        # Get arguments with defaults
        args = arguments or {}

        # Call the file search provider with parameters
        resource_data = await file_search_provider.get_resource(**args)

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

    # Handle extract_document_content separately as it takes parameters
    if name == "extract_document_content":
        # Get file_path argument
        args = arguments or {}
        file_path = args.get('file_path')

        if not file_path:
            return [
                types.TextContent(
                    type="text",
                    text="Error: file_path parameter is required",
                )
            ]

        # Call the document content provider with file_path
        resource_data = await document_content_provider.get_resource(file_path=file_path)

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

    # Handle image analysis tools
    if name in ["analyze_image", "analyze_images_batch"]:
        args = arguments or {}

        # Call the image analyzer provider with parameters
        resource_data = await image_analyzer_provider.get_resource(**args)

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

    # Handle face management tool
    if name == "manage_faces":
        args = arguments or {}

        # Call the face manager provider with parameters
        resource_data = await face_manager_provider.get_resource(**args)

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

    # Handle file operation tools
    if name in ["move_files", "copy_files", "trash_files", "rename_file", "create_directory", "remove_directory"]:
        from ratatoskr_mcp_server.utils import file_operations
        import json

        args = arguments or {}

        if name == "move_files":
            file_paths = args.get('file_paths', [])
            destination = args.get('destination')
            overwrite = args.get('overwrite', False)

            if not file_paths or not destination:
                return [types.TextContent(type="text", text="Error: file_paths and destination are required")]

            result = file_operations.move_files(file_paths, destination, overwrite)
            return [types.TextContent(type="text", text=json.dumps(result, indent=2))]

        elif name == "copy_files":
            file_paths = args.get('file_paths', [])
            destination = args.get('destination')
            overwrite = args.get('overwrite', False)

            if not file_paths or not destination:
                return [types.TextContent(type="text", text="Error: file_paths and destination are required")]

            result = file_operations.copy_files(file_paths, destination, overwrite)
            return [types.TextContent(type="text", text=json.dumps(result, indent=2))]

        elif name == "trash_files":
            file_paths = args.get('file_paths', [])

            if not file_paths:
                return [types.TextContent(type="text", text="Error: file_paths is required")]

            result = file_operations.trash_files(file_paths)
            return [types.TextContent(type="text", text=json.dumps(result, indent=2))]

        elif name == "rename_file":
            file_path = args.get('file_path')
            new_name = args.get('new_name')

            if not file_path or not new_name:
                return [types.TextContent(type="text", text="Error: file_path and new_name are required")]

            result = file_operations.rename_file(file_path, new_name)
            return [types.TextContent(type="text", text=json.dumps(result, indent=2))]

        elif name == "create_directory":
            directory_path = args.get('directory_path')
            parents = args.get('parents', False)

            if not directory_path:
                return [types.TextContent(type="text", text="Error: directory_path is required")]

            result = file_operations.create_directory(directory_path, parents)
            return [types.TextContent(type="text", text=json.dumps(result, indent=2))]

        elif name == "remove_directory":
            directory_path = args.get('directory_path')

            if not directory_path:
                return [types.TextContent(type="text", text="Error: directory_path is required")]

            result = file_operations.remove_directory(directory_path)
            return [types.TextContent(type="text", text=json.dumps(result, indent=2))]

    # Map tool names to resource URIs
    tool_to_uri = {
        "get_desktop_info": "ratatoskr://gnome/desktop",
        "get_distro_info": "ratatoskr://distro/osinfo",
        "get_gnome_extensions": "ratatoskr://gnome/extensions",
        "get_favorite_apps": "ratatoskr://gnome/favorite-apps",
        "get_keybindings": "ratatoskr://gnome/keybindings",
        "get_app_launch_stats": "ratatoskr://gnome/app-stats",
        "get_project_files": "ratatoskr://tracker/project-files",
        "get_file_statistics": "ratatoskr://tracker/file-stats",
    }

    uri = tool_to_uri.get(name)
    if not uri:
        raise ValueError(f"Unknown tool: {name}")

    # Get resource data
    resource_data = await resource_manager.get_resource(uri)

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


async def main() -> None:
    """Run the MCP server."""
    global app_launch_monitor

    dbus_monitor = None
    systemd_monitor = None

    # Initialize the app launch monitors
    try:
        # Keep AppLaunchMonitor for GNOME scores, but don't start it
        app_launch_monitor = AppLaunchMonitor()

        # Check database status
        from ratatoskr_mcp_server.utils.app_launch_db import AppLaunchDB
        db = AppLaunchDB()
        stats = db.get_stats()
        db.close()

        logger.info(f"App launch tracking initialized ({stats['total_launches']} launches tracked)")

        # Start D-Bus monitor for native GNOME apps
        dbus_monitor = DBusLaunchMonitor()
        dbus_monitor.start()
        logger.info("D-Bus NameOwnerChanged monitoring started - tracking native app launches")

        # Start systemd monitor for Flatpak apps
        systemd_monitor = SystemdLaunchMonitor()
        systemd_monitor.start()
        logger.info("Systemd UnitNew monitoring started - tracking Flatpak app launches")

    except Exception as e:
        logger.warning(f"Could not start app launch monitors: {e}")
        app_launch_monitor = None
        dbus_monitor = None
        systemd_monitor = None

    try:
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
    finally:
        # Stop the monitors when server shuts down
        if dbus_monitor:
            logger.info("Stopping D-Bus launch monitor...")
            dbus_monitor.stop()
            logger.info("D-Bus launch monitor stopped")

        if systemd_monitor:
            logger.info("Stopping systemd launch monitor...")
            systemd_monitor.stop()
            logger.info("Systemd launch monitor stopped")

        if app_launch_monitor:
            app_launch_monitor.close()


def cli_main() -> None:
    """CLI entry point for the MCP server."""
    asyncio.run(main())


if __name__ == "__main__":
    cli_main()
