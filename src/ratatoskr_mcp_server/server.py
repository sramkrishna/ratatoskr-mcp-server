"""Main MCP server implementation for GNOME integration."""

import asyncio
import logging
from typing import Any

from mcp.server import Server
from mcp.server.models import InitializationOptions
from mcp.server.lowlevel.server import NotificationOptions
import mcp.server.stdio
import mcp.types as types

from ratatoskr_mcp_server.resource_manager import ResourceManager, ResourceSerializer, ResourceData
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
    NetworkDetectionProvider,
    # FaceManagerProvider,  # Disabled - requires face_recognition
    CalendarProvider,
    PlanifyProvider,
    EmailProvider,
    # MuninnProvider,  # Disabled - Muninn is a separate MCP server
)
from ratatoskr_mcp_server.monitors import AppLaunchMonitor, DBusLaunchMonitor, SystemdLaunchMonitor
from ratatoskr_mcp_server.utils.planify import PlanifyManager
from ratatoskr_mcp_server.utils.notifications import NotificationManager, NotificationUrgency
from ratatoskr_mcp_server.utils.xdg_helpers import compose_email, create_calendar_event
from ratatoskr_mcp_server.utils.evolution_contacts import EvolutionContactsManager
from ratatoskr_mcp_server.utils.contact_communication_analysis import ContactCommunicationAnalyzer
from ratatoskr_mcp_server.utils.sent_email_analysis import SentEmailAnalyzer

# Configure logging with support for LOG_LEVEL environment variable
import os
log_level_str = os.getenv("LOG_LEVEL", "INFO").upper()
log_level = getattr(logging, log_level_str, logging.INFO)

# Configure logging to file if LOG_FILE is set, otherwise use stderr
log_file = os.getenv("LOG_FILE")
if log_file:
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        filename=log_file,
        filemode='a'
    )
else:
    logging.basicConfig(level=log_level)

logger = logging.getLogger("ratatoskr_mcp_server")


# Initialize app launch monitor (will be started in main())
app_launch_monitor = None

# Check if Planify is available
PLANIFY_AVAILABLE = PlanifyManager.is_available()
if PLANIFY_AVAILABLE:
    logger.info("Planify detected - enabling task management features")
else:
    logger.info("Planify not found - task management features disabled")

# Initialize resource manager with providers
resources = {
    "ratatoskr://gnome/desktop": GnomeDesktopProvider(),
    "ratatoskr://gnome/extensions": GnomeExtensionsProvider(),
    "ratatoskr://gnome/favorite-apps": GnomeFavoriteAppsProvider(),
    "ratatoskr://gnome/keybindings": GnomeKeybindingsProvider(),
    "ratatoskr://gnome/app-stats": AppLaunchStatsProvider(),
    "ratatoskr://tracker/project-files": ProjectFilesProvider(),
    "ratatoskr://tracker/file-stats": FileStatisticsProvider(),
    "ratatoskr://distro/osinfo": DistroInfoProvider(),
    "ratatoskr://system/network": NetworkDetectionProvider(),
    "ratatoskr://calendar/events": CalendarProvider(),
}

# Add Planify resource if available
if PLANIFY_AVAILABLE:
    resources["ratatoskr://planify/tasks"] = PlanifyProvider()

resource_manager = ResourceManager(resources)

# Initialize file search provider (needs to handle parameters, so not in resource_manager)
file_search_provider = FileSearchProvider()

# Initialize document content provider (needs file_path parameter)
document_content_provider = DocumentContentProvider()

# Initialize image analyzer provider (needs image_path parameter)
image_analyzer_provider = ImageAnalyzerProvider()

# Initialize face manager provider (needs action parameter)
# face_manager_provider = FaceManagerProvider()  # Disabled - requires face_recognition

# Initialize calendar provider (needs query parameters)
calendar_provider = CalendarProvider()

# Initialize Planify provider if available
if PLANIFY_AVAILABLE:
    planify_provider = PlanifyProvider()
else:
    planify_provider = None

# Initialize email provider
email_provider = EmailProvider()

# Initialize contacts manager
try:
    contacts_manager = EvolutionContactsManager()
    CONTACTS_AVAILABLE = True
    logger.info("Evolution contacts detected - enabling contact search features")
except Exception as e:
    contacts_manager = None
    CONTACTS_AVAILABLE = False
    logger.info(f"Evolution contacts not available: {e}")

# Initialize contact communication analyzer
try:
    communication_analyzer = ContactCommunicationAnalyzer()
    COMM_ANALYSIS_AVAILABLE = True
    logger.info("Contact communication analyzer initialized")
except Exception as e:
    communication_analyzer = None
    COMM_ANALYSIS_AVAILABLE = False
    logger.info(f"Contact communication analyzer not available: {e}")

# Initialize sent email analyzer
try:
    sent_email_analyzer = SentEmailAnalyzer()
    SENT_EMAIL_ANALYSIS_AVAILABLE = True
    logger.info("Sent email analyzer initialized")
except Exception as e:
    sent_email_analyzer = None
    SENT_EMAIL_ANALYSIS_AVAILABLE = False
    logger.info(f"Sent email analyzer not available: {e}")

# Initialize Muninn memory provider
# muninn_provider = MuninnProvider()  # Disabled - Muninn is a separate MCP server
# Create a dummy provider that's never available
class DummyMuninnProvider:
    available = False
muninn_provider = DummyMuninnProvider()

# Initialize notification manager
notification_manager = NotificationManager()

serializer = ResourceSerializer()
server = Server("ratatoskr-mcp-server")


@server.list_resources()
async def handle_list_resources() -> list[types.Resource]:
    """List all available resources."""
    resources_list = [
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
        ),
        types.Resource(
            uri="ratatoskr://system/network",
            name="Network Detection & Backend Selection",
            description="Detect current network environment (WiFi SSID, subnet), determine if on home network, check available vision backends (Ollama/GPU, OpenVINO/NPU, llamafile/CPU), and recommend optimal backend for current location",
            mimeType="application/json",
        ),
        types.Resource(
            uri="ratatoskr://calendar/events",
            name="Calendar Events",
            description="Upcoming calendar events from all configured calendars (local and online)",
            mimeType="application/json",
        ),
    ]

    # Add Planify resource if available
    if PLANIFY_AVAILABLE:
        resources_list.append(
            types.Resource(
                uri="ratatoskr://planify/tasks",
                name="Planify Tasks",
                description="Tasks and to-dos from Planify task manager (if installed)",
                mimeType="application/json",
            )
        )

    return resources_list


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
    tools_list = [
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
            name="detect_network",
            description="Detect current network environment and get recommended vision backend. Returns: network info (WiFi SSID, subnet, home network status), available backends (Ollama/GPU, OpenVINO/NPU, llamafile/CPU), and recommended backend for current location. Use this to understand which backend will be used for vision tasks or to help debug backend selection issues.",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": [],
            },
        ),
        types.Tool(
            name="scan_wifi_networks",
            description="Scan for available WiFi networks and show signal strength, security, and frequency. SUPER USEFUL when you're in a place with many SSIDs (coffee shop, airport, hotel, conference) and need to find the right network. Shows signal strength (so you can pick the strongest), security type (WPA2, WPA, Open), and band (2.4 GHz vs 5 GHz). Can filter by name pattern and minimum signal strength.",
            inputSchema={
                "type": "object",
                "properties": {
                    "rescan": {
                        "type": "boolean",
                        "description": "Whether to trigger a new scan before listing networks (default: true). Set to false to just show cached results.",
                    },
                    "filter_pattern": {
                        "type": "string",
                        "description": "Optional pattern to filter SSIDs (case-insensitive). E.g., 'hotel' to find hotel networks, 'guest' for guest networks.",
                    },
                    "min_signal_strength": {
                        "type": "number",
                        "description": "Minimum signal strength (0-100, default: 0). E.g., 50 to only show networks with decent signal.",
                    },
                },
                "required": [],
            },
        ),
        types.Tool(
            name="convert_markdown_to_pdf",
            description="Convert markdown file(s) to PDF using pandoc. Perfect for emailing markdown documents - PDFs render properly in all webmail clients (Gmail, Outlook, etc.) and on all platforms (Windows, macOS, Linux). Supports metadata (title, author) and handles single or multiple files. Requires pandoc to be installed.",
            inputSchema={
                "type": "object",
                "properties": {
                    "markdown_path": {
                        "type": "string",
                        "description": "Path to markdown file to convert (for single file conversion)",
                    },
                    "markdown_paths": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of markdown file paths to convert (for batch conversion)",
                    },
                    "output_path": {
                        "type": "string",
                        "description": "Optional output PDF path (for single file). Defaults to same directory/name as markdown with .pdf extension.",
                    },
                    "output_dir": {
                        "type": "string",
                        "description": "Optional output directory for batch conversion. Defaults to same directory as each markdown file.",
                    },
                    "title": {
                        "type": "string",
                        "description": "Optional document title for PDF metadata",
                    },
                    "author": {
                        "type": "string",
                        "description": "Optional author name for PDF metadata",
                    },
                },
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
            description="Analyze an image using multi-backend vision system (automatically selects best backend based on network). Auto-selection: At home → Ollama (GPU, fastest ~50-150 tok/s), Traveling → OpenVINO (NPU ~20-50 tok/s), Fallback → llamafile (CPU ~2-5 tok/s). The description is written to the image's EXIF/XMP metadata and indexed by LocalSearch, making it searchable. Uses on-device AI for privacy. Set 'backend' parameter to override auto-selection.",
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
                    "backend": {
                        "type": "string",
                        "enum": ["ollama", "openvino", "llamafile"],
                        "description": "Optional: Force specific backend ('ollama', 'openvino', or 'llamafile'). If not specified, automatically selects based on network/availability.",
                    },
                    "ollama_host": {
                        "type": "string",
                        "description": "Optional: Override Ollama server host (e.g., 'http://192.168.1.100:11434')",
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
            description="Analyze multiple images in batch using multi-backend vision system (automatically selects best backend based on network). Auto-selection: At home → Ollama (GPU, fastest ~50-150 tok/s), Traveling → OpenVINO (NPU ~20-50 tok/s), Fallback → llamafile (CPU ~2-5 tok/s). Generates descriptions for each image and writes them to EXIF/XMP metadata. Uses on-device AI for privacy. Maximum 10 images per batch.",
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
                    "backend": {
                        "type": "string",
                        "enum": ["ollama", "openvino", "llamafile"],
                        "description": "Optional: Force specific backend ('ollama', 'openvino', or 'llamafile'). If not specified, automatically selects based on network/availability.",
                    },
                    "ollama_host": {
                        "type": "string",
                        "description": "Optional: Override Ollama server host (e.g., 'http://192.168.1.100:11434')",
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
        types.Tool(
            name="query_calendar_events",
            description="Query calendar events from all configured calendars. Returns event times, titles, locations, descriptions - but NOT attendee/participant info. DO NOT USE this tool if the query mentions specific people (names, emails) or asks WHO attended meetings. Use query_calendar_events_with_attendees instead for any people-related queries. Supports date ranges like 'yesterday', 'today', 'tomorrow', or ISO dates. IMPORTANT: Use start_date parameter, not 'date'. Example: For today's events, use {\"start_date\": \"today\"}.",
            inputSchema={
                "type": "object",
                "properties": {
                    "start_date": {
                        "type": "string",
                        "description": "Start date for query (REQUIRED parameter name is 'start_date', not 'date'!). Can be 'yesterday', 'today', 'tomorrow', or ISO format (YYYY-MM-DD). For queries like 'past week' or 'last month', calculate the actual date in ISO format (e.g., for 'past week' use date from 7 days ago). If not specified, defaults to now (which may miss past events today).",
                    },
                    "end_date": {
                        "type": "string",
                        "description": "End date for query in ISO format (YYYY-MM-DD). For queries like 'past week', set this to today's date. If not specified, end of start_date is used.",
                    },
                    "days_ahead": {
                        "type": "number",
                        "description": "Number of days ahead to query from start_date (alternative to end_date). NOTE: Use negative values for looking back in time is NOT supported - use explicit start_date and end_date instead. Default is 0 (just the start date).",
                    },
                    "calendar_uids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional list of calendar UIDs to filter by. If not provided, queries all calendars.",
                    },
                },
                "required": [],
            },
        ),
        types.Tool(
            name="query_calendar_events_with_attendees",
            description="Query calendar events WITH full attendee/participant lists. REQUIRED when the query mentions ANY person's name or asks about WHO attended. Examples that REQUIRE this tool: 'meetings with Alison', 'who attended the standup', 'meetings that has john in it', 'show me Sarah's meetings last week'. Returns email, name, role, and RSVP status for each attendee. IMPORTANT: This tool returns ALL events with their attendee lists - you must then filter the results yourself to find events where a specific person attended by checking the 'attendees' array in each event.",
            inputSchema={
                "type": "object",
                "properties": {
                    "start_date": {
                        "type": "string",
                        "description": "Start date for query. Can be 'yesterday', 'today', 'tomorrow', or ISO format (YYYY-MM-DD). For queries like 'past week' or 'last month', calculate the actual date in ISO format (e.g., for 'past week' use date from 7 days ago). If not specified, defaults to now.",
                    },
                    "end_date": {
                        "type": "string",
                        "description": "End date for query in ISO format (YYYY-MM-DD). For queries like 'past week', set this to today's date. If not specified, end of start_date is used.",
                    },
                    "days_ahead": {
                        "type": "number",
                        "description": "Number of days ahead to query from start_date (alternative to end_date). NOTE: Use negative values for looking back in time is NOT supported - use explicit start_date and end_date instead. Default is 0 (just the start date).",
                    },
                    "calendar_uids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional list of calendar UIDs to filter by. If not provided, queries all calendars.",
                    },
                },
                "required": [],
            },
        ),
    ]

    # Add Planify tools if available
    if PLANIFY_AVAILABLE:
        tools_list.extend([
            types.Tool(
                name="query_planify_tasks",
                description="Query tasks from Planify task manager. Supports filtering by completion status, project, priority, and due dates. CRITICAL RULES: (1) When user asks for 'upcoming tasks', 'todos', or 'things to do', ALWAYS use completed=false to exclude finished tasks. (2) When user asks for 'today's tasks' or 'this week', DO NOT use due_date parameter - query with completed=false (no date filter) to get ALL uncompleted tasks, then filter by date in your response. (3) The due_date parameter is ONLY for exact date matching (e.g., 'tasks due on Nov 15'). (4) 'Upcoming' means future or current dates - use hugin_get_current_date to check today's date, then exclude tasks with past due dates from your response.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "completed": {
                            "type": "boolean",
                            "description": "Filter by completion status. IMPORTANT: When user asks for 'upcoming tasks', 'todos', 'things to do', or 'what do I need to work on', you MUST use completed=false to exclude finished tasks! If true, returns only completed tasks. If false, returns only incomplete/active tasks. If omitted, returns both completed and incomplete (rarely useful).",
                        },
                        "project_id": {
                            "type": "string",
                            "description": "Filter tasks by project ID. Use get_planify_projects to get available project IDs.",
                        },
                        "priority": {
                            "type": "number",
                            "description": "Filter by priority level: 1 (low), 2 (medium), 3 (high), 4 (urgent).",
                        },
                        "has_due_date": {
                            "type": "boolean",
                            "description": "Filter by due date presence. If true, returns ONLY tasks with due dates. If false, returns ONLY tasks without due dates. If omitted, returns both. Example use case: To get tasks without due dates, use has_due_date=false.",
                        },
                        "due_date": {
                            "type": "string",
                            "description": "Filter tasks by EXACT due date match in ISO format (YYYY-MM-DD). Only use this when user asks for tasks due on a SPECIFIC date (e.g., 'tasks due on November 15th'). DO NOT use this for queries like 'today's tasks' or 'todos today' - those should use completed=false with no due_date filter to show all uncompleted tasks including overdue ones.",
                        },
                        "limit": {
                            "type": "number",
                            "description": "Maximum number of tasks to return (default: 50).",
                        },
                    },
                    "required": [],
                },
            ),
            types.Tool(
                name="get_planify_projects",
                description="Get all available projects from Planify task manager. Use this to get project IDs for filtering tasks.",
                inputSchema={
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            ),
        ])

    # Add email tools if available
    if email_provider.available:
        tools_list.extend([
            types.Tool(
                name="get_email_accounts",
                description="Get list of email accounts configured in Evolution. Returns account_id, email_address, and email_count for each account. CRITICAL: Always call this FIRST before query_emails. Map user queries to accounts: 'gmail'→email ending '@gmail.com', 'hotmail'→'@hotmail.com', 'work'→account with most emails. DO NOT default to first account! Match the email address from this list to the user's request, then use that account's account_id in query_emails. Example: User asks 'gmail emails'→call this→find 'sriram.ramkrishna@gmail.com'→use its account_id in query_emails.",
                inputSchema={
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            ),
            types.Tool(
                name="get_email_folders",
                description="Get list of folders for a specific email account.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "account_name": {
                            "type": "string",
                            "description": "Email account name (e.g., 'imap.gmail.com'). Use get_email_accounts to see available accounts.",
                        },
                    },
                    "required": ["account_name"],
                },
            ),
            types.Tool(
                name="query_emails",
                description="Query emails from Evolution. FAST: Uses SQLite indexes for instant searches across 190,000+ emails. Searches last 7 days by default. Supports filtering by sender, recipient, subject, date. No timeout needed - queries are <1ms! NOTE: Queries email metadata (subject, sender, date) from SQLite database. Evolution should be running for best results - it caches email bodies when accessing IMAP accounts. IMPORTANT FOR SENT MAIL: When user asks 'who did I email' or 'emails I sent', you MUST: (1) call get_email_accounts to get the user's email address, (2) set sender parameter to that email address to filter by sent emails. Evolution does NOT have separate folder filtering - use sender/recipient to distinguish sent vs received.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "account_name": {
                            "type": "string",
                            "description": "Account ID hash (NOT email address!) from get_email_accounts. CRITICAL: When user mentions 'gmail', 'hotmail', or any email address, you MUST call get_email_accounts FIRST to see available accounts, match the user's request to the correct email_address, then use that account's account_id here. DO NOT pass email addresses - only pass the account_id hash (e.g., '6f004791b4e0c36040e307bb52bca86f88fe723e'). If not specified, searches all accounts (slower).",
                        },
                        "folder_names": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "DEPRECATED: Evolution stores all emails in one database table regardless of folder. Use 'sender' and 'recipient' parameters instead to filter sent vs received emails. This parameter is kept for backward compatibility but has no effect.",
                        },
                        "days_back": {
                            "type": "number",
                            "description": "Number of days to look back from today. Default: 7. Can search years of email instantly thanks to SQLite indexing.",
                        },
                        "sender": {
                            "type": "string",
                            "description": "Filter by sender email address (e.g., 'nikshi@gmail.com'). Case-insensitive partial match. CRITICAL FOR SENT MAIL: When user asks 'who did I email' or 'emails I sent', set this to the user's email address (from get_email_accounts) to find sent emails.",
                        },
                        "recipient": {
                            "type": "string",
                            "description": "Filter by recipient email address (in To or CC). Case-insensitive partial match. Use this for 'emails to X' queries.",
                        },
                        "subject_contains": {
                            "type": "string",
                            "description": "Filter by text in subject line. Case-insensitive partial match.",
                        },
                        "has_attachments": {
                            "type": "boolean",
                            "description": "Only return emails with attachments (default: false).",
                        },
                        "limit": {
                            "type": "number",
                            "description": "Maximum number of emails to return (default: 100).",
                        },
                    },
                    "required": [],
                },
            ),
            types.Tool(
                name="get_email_content",
                description="Get full content of a specific email including body text/HTML. Use this after query_emails to read email bodies. IMPORTANT: Evolution only caches email bodies for IMAP accounts when you access them. If email body is not cached, you'll get an error asking to open the email in Evolution first. For best results, ensure Evolution is running.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "account_id": {
                            "type": "string",
                            "description": "Account ID from query_emails result.",
                        },
                        "folder": {
                            "type": "string",
                            "description": "Folder name from query_emails result (e.g., 'INBOX').",
                        },
                        "uid": {
                            "type": "string",
                            "description": "Email UID from query_emails result.",
                        },
                    },
                    "required": ["account_id", "folder", "uid"],
                },
            ),
            types.Tool(
                name="find_ical_emails",
                description="Find emails with iCalendar (.ics) attachments. Useful for finding meeting invitations and calendar-related emails to add context to appointments.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "account_name": {
                            "type": "string",
                            "description": "Email account name (e.g., 'imap.gmail.com'). Required.",
                        },
                        "folder_names": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of folder names to search (e.g., ['INBOX', 'Sent Mail']). If not specified, defaults to INBOX and Sent Mail only for performance.",
                        },
                        "days_back": {
                            "type": "number",
                            "description": "Number of days to look back from today. Default: 7 (30s timeout). Use 30 for one month (60s timeout).",
                        },
                        "limit": {
                            "type": "number",
                            "description": "Maximum number of emails to return (default: 50).",
                        },
                    },
                    "required": ["account_name"],
                },
            ),
        ])

    # Add Muninn memory tools if available
    if muninn_provider.available:
        tools_list.extend([
            types.Tool(
                name="muninn_remember",
                description="Store a memory/context about an email conversation. Use this to save discussion summaries, decisions made, action items, or any context about emails for future recall.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "email_message_id": {
                            "type": "string",
                            "description": "Email Message-ID from the email metadata.",
                        },
                        "email_subject": {
                            "type": "string",
                            "description": "Email subject line.",
                        },
                        "email_sender": {
                            "type": "string",
                            "description": "Email sender.",
                        },
                        "email_date": {
                            "type": "string",
                            "description": "Email date (ISO format).",
                        },
                        "context": {
                            "type": "string",
                            "description": "The conversation context, summary, or discussion notes about this email.",
                        },
                        "tags": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Optional tags for categorization (e.g., ['work', 'urgent', 'follow-up']).",
                        },
                        "notes": {
                            "type": "string",
                            "description": "Optional additional notes.",
                        },
                    },
                    "required": ["email_message_id", "email_subject", "email_sender", "email_date", "context"],
                },
            ),
            types.Tool(
                name="muninn_recall",
                description="Recall stored memories about email(s). Retrieve past discussion context about specific emails or browse recent memories.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "email_message_id": {
                            "type": "string",
                            "description": "Optional: Specific email Message-ID to recall memories for.",
                        },
                        "limit": {
                            "type": "number",
                            "description": "Maximum number of memories to return (default: 10).",
                        },
                    },
                    "required": [],
                },
            ),
            types.Tool(
                name="muninn_search",
                description="Semantically search through email memories. Find past discussions by topic, keyword, or context even if exact words don't match.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query (e.g., 'discussions about the Filigran opportunity', 'meetings with John').",
                        },
                        "limit": {
                            "type": "number",
                            "description": "Maximum number of results (default: 10).",
                        },
                        "sender": {
                            "type": "string",
                            "description": "Optional: Filter by sender email address.",
                        },
                        "tags": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Optional: Filter by tags.",
                        },
                    },
                    "required": ["query"],
                },
            ),
            types.Tool(
                name="muninn_update",
                description="Update an existing email memory with new context, tags, or notes.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "memory_id": {
                            "type": "string",
                            "description": "Memory ID to update (from muninn_recall or muninn_search results).",
                        },
                        "context": {
                            "type": "string",
                            "description": "Optional: New context to replace existing.",
                        },
                        "tags": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Optional: New tags to replace existing.",
                        },
                        "notes": {
                            "type": "string",
                            "description": "Optional: New notes to replace existing.",
                        },
                    },
                    "required": ["memory_id"],
                },
            ),
            types.Tool(
                name="muninn_forget",
                description="Delete a memory. Use with caution - this cannot be undone.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "memory_id": {
                            "type": "string",
                            "description": "Memory ID to delete.",
                        },
                    },
                    "required": ["memory_id"],
                },
            ),
            types.Tool(
                name="muninn_stats",
                description="Get statistics about stored memories (total count, unique senders, tags, etc.).",
                inputSchema={
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            ),
        ])

    # Notification tools (always available)
    tools_list.extend([
        types.Tool(
            name="send_notification",
            description="Send a GNOME desktop notification. Use this to alert the user about important events, reminders, or status updates. Examples: new CalGator events, task deadlines approaching, system alerts, completed background operations.",
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Notification title (short, attention-grabbing)",
                    },
                    "body": {
                        "type": "string",
                        "description": "Notification body text (detailed message)",
                    },
                    "urgency": {
                        "type": "string",
                        "enum": ["low", "normal", "critical"],
                        "description": "Urgency level: 'low' for FYI, 'normal' for info, 'critical' for urgent alerts that need immediate attention",
                    },
                    "icon": {
                        "type": "string",
                        "description": "Icon name (e.g., 'dialog-information', 'mail-unread', 'x-office-calendar', 'dialog-warning'). See NotificationIcon class for common icons.",
                    },
                    "category": {
                        "type": "string",
                        "description": "Category hint for grouping (e.g., 'email', 'calendar', 'network', 'im')",
                    },
                },
                "required": ["title", "body"],
            },
        ),
        types.Tool(
            name="send_urgent_notification",
            description="Send a CRITICAL notification that won't auto-dismiss. Use for urgent alerts that demand immediate user attention (e.g., deadlines in < 1 hour, critical system issues, important calendar events starting soon). This will stay on screen until user dismisses it.",
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Urgent notification title",
                    },
                    "body": {
                        "type": "string",
                        "description": "Detailed urgent message",
                    },
                },
                "required": ["title", "body"],
            },
        ),
        types.Tool(
            name="add_todo",
            description="Open Planify quick-add dialog to create a new todo/task. Use this when the user wants to add a reminder, task, or todo item. The dialog will appear on screen for the user to fill in details.",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": [],
            },
        ),
        types.Tool(
            name="compose_email",
            description="Open Evolution email composer with pre-filled content. Provides file paths that the user should manually attach (automated attachment via mailto: URLs is unreliable). SMART FEATURE: If more than 5 files are provided, they will be automatically zipped into a single archive - then user just needs to attach the one zip file. Perfect for sending documents, images, or any files.",
            inputSchema={
                "type": "object",
                "properties": {
                    "to": {
                        "type": "string",
                        "description": "Recipient email address",
                    },
                    "subject": {
                        "type": "string",
                        "description": "Email subject line",
                    },
                    "body": {
                        "type": "string",
                        "description": "Email body content",
                    },
                    "cc": {
                        "type": "string",
                        "description": "CC recipients (comma-separated, optional)",
                    },
                    "bcc": {
                        "type": "string",
                        "description": "BCC recipients (comma-separated, optional)",
                    },
                    "attachments": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of file paths to attach (absolute paths). Files will be validated before opening composer. If more than 5 files, they will be automatically zipped. Example: ['/home/user/Documents/report.pdf', '/home/user/Pictures/chart.png']",
                    },
                },
                "required": ["to"],
            },
        ),
        types.Tool(
            name="create_calendar_event",
            description="Create a calendar event by opening GNOME Calendar with pre-filled event details. The user can review and save. Use this when the user wants to schedule an event or meeting. Supports adding Google Meet conference links.",
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Event title/summary",
                    },
                    "start_time": {
                        "type": "string",
                        "description": "Start time in ISO format (YYYY-MM-DDTHH:MM:SS or YYYY-MM-DD for all-day events)",
                    },
                    "end_time": {
                        "type": "string",
                        "description": "End time in ISO format (same format as start_time)",
                    },
                    "description": {
                        "type": "string",
                        "description": "Event description/notes (optional)",
                    },
                    "location": {
                        "type": "string",
                        "description": "Event location (optional)",
                    },
                    "all_day": {
                        "type": "boolean",
                        "description": "Whether this is an all-day event (default: false)",
                    },
                    "video_call_url": {
                        "type": "string",
                        "description": "Video conferencing URL for the event (Zoom, Google Meet, Jitsi, Teams, etc.). IMPORTANT: When creating events with video calls, ALWAYS use this parameter - it will automatically populate the location field with a clickable link. Do NOT put URLs in the location parameter manually. If the event has a video call link (from email, user request, etc.), extract it and pass it here.",
                    },
                },
                "required": ["title", "start_time", "end_time"],
            },
        ),
        types.Tool(
            name="query_contacts",
            description="Search Evolution contacts by name, email, or organization. Returns contact details including emails, phones, and notes.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "General search query (searches name, email, organization)",
                    },
                    "email": {
                        "type": "string",
                        "description": "Search by specific email address (partial match, optional)",
                    },
                    "name": {
                        "type": "string",
                        "description": "Search by name (partial match, optional)",
                    },
                    "limit": {
                        "type": "number",
                        "description": "Maximum contacts to return (default: 50)",
                    },
                },
                "required": [],
            },
        ),
        types.Tool(
            name="analyze_contact_communications",
            description="Analyze email communication patterns with contacts efficiently. In ONE QUERY, analyzes all contacts against email history to find: who you've emailed in a time period, most active contacts, communication frequency. Perfect for questions like 'How many contacts have I emailed in the past year?' or 'Who is my most active contact in the past 4 months?' This is much faster than querying each contact individually.",
            inputSchema={
                "type": "object",
                "properties": {
                    "my_email_addresses": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Your email addresses to analyze (e.g., ['sri@ramkrishna.me', 'sriram.ramkrishna@gmail.com'])",
                    },
                    "days_back": {
                        "type": "number",
                        "description": "How many days back to analyze (default: 365 for 1 year)",
                    },
                    "recent_days": {
                        "type": "number",
                        "description": "Optional: analyze most active contacts in recent period (e.g., 120 for 4 months)",
                    },
                },
                "required": ["my_email_addresses"],
            },
        ),
        types.Tool(
            name="analyze_sent_emails",
            description="Analyze who you've sent emails to by directly scanning your Sent folders. This works WITHOUT requiring a contact list - it discovers all recipients from your actual email history. Returns statistics about who you email most frequently, when you last emailed them, and identifies your most active correspondents. Perfect for questions like 'Who have I sent the most emails to in the past year?' or 'Who is my most active correspondent in the past 4 months?' Works even if your contacts don't have email addresses stored.",
            inputSchema={
                "type": "object",
                "properties": {
                    "my_email_addresses": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Your email addresses to analyze (e.g., ['sri@ramkrishna.me', 'sriram.ramkrishna@gmail.com'])",
                    },
                    "days_back": {
                        "type": "number",
                        "description": "How many days back to analyze (default: 365 for 1 year)",
                    },
                    "recent_days": {
                        "type": "number",
                        "description": "Optional: analyze most active recipients in recent period (e.g., 120 for 4 months)",
                    },
                },
                "required": ["my_email_addresses"],
            },
        ),
    ])

    return tools_list


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
    # Disabled - requires face_recognition
    # if name == "manage_faces":
    #     args = arguments or {}
    #
    #     # Call the face manager provider with parameters
    #     resource_data = await face_manager_provider.get_resource(**args)
    #
    #     if resource_data.is_error:
    #         return [
    #             types.TextContent(
    #                 type="text",
    #                 text=f"Error: {resource_data.error}",
    #             )
    #         ]
    #
    #     return [
    #         types.TextContent(
    #             type="text",
    #             text=serializer.to_json(resource_data),
    #         )
    #     ]

    if name == "query_calendar_events":
        args = arguments or {}

        # Call the calendar provider with parameters
        resource_data = await calendar_provider.query_events(
            start_date=args.get('start_date'),
            end_date=args.get('end_date'),
            days_ahead=args.get('days_ahead'),
            calendar_uids=args.get('calendar_uids')
        )

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

    if name == "query_calendar_events_with_attendees":
        args = arguments or {}

        # Call the calendar provider with attendees parameter
        resource_data = await calendar_provider.query_events_with_attendees(
            start_date=args.get('start_date'),
            end_date=args.get('end_date'),
            days_ahead=args.get('days_ahead'),
            calendar_uids=args.get('calendar_uids')
        )

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

    # Handle Planify tools
    if name == "query_planify_tasks":
        if not PLANIFY_AVAILABLE:
            return [
                types.TextContent(
                    type="text",
                    text="Error: Planify is not installed or not available",
                )
            ]

        args = arguments or {}

        # Call the Planify provider with parameters
        resource_data = await planify_provider.query_tasks(
            completed=args.get('completed'),
            project_id=args.get('project_id'),
            priority=args.get('priority'),
            has_due_date=args.get('has_due_date'),
            due_date=args.get('due_date'),
            limit=args.get('limit')
        )

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

    if name == "get_planify_projects":
        if not PLANIFY_AVAILABLE:
            return [
                types.TextContent(
                    type="text",
                    text="Error: Planify is not installed or not available",
                )
            ]

        # Call the Planify provider to get projects
        resource_data = await planify_provider.get_projects()

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

    # Handle email tools
    if name == "get_email_accounts":
        if not email_provider.available:
            return [
                types.TextContent(
                    type="text",
                    text="Error: Evolution is not available or not configured",
                )
            ]

        resource_data = email_provider.get_accounts()

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

    if name == "get_email_folders":
        if not email_provider.available:
            return [
                types.TextContent(
                    type="text",
                    text="Error: Evolution is not available or not configured",
                )
            ]

        args = arguments or {}
        account_name = args.get('account_name')

        if not account_name:
            return [
                types.TextContent(
                    type="text",
                    text="Error: account_name parameter is required",
                )
            ]

        resource_data = email_provider.get_folders(account_name)

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

    if name == "query_emails":
        if not email_provider.available:
            return [
                types.TextContent(
                    type="text",
                    text="Error: Evolution is not available or not configured",
                )
            ]

        args = arguments or {}

        resource_data = await email_provider.query_emails(
            account_name=args.get('account_name'),
            folder_names=args.get('folder_names'),
            days_back=args.get('days_back', 30),
            has_attachments=args.get('has_attachments', False),
            sender=args.get('sender'),
            recipient=args.get('recipient'),
            subject_contains=args.get('subject_contains'),
            limit=args.get('limit', 100)
        )

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

    if name == "get_email_content":
        if not email_provider.available:
            return [
                types.TextContent(
                    type="text",
                    text="Error: Evolution is not available or not configured",
                )
            ]

        args = arguments or {}

        resource_data = await email_provider.get_email_content(
            account_id=args.get('account_id'),
            folder=args.get('folder'),
            uid=args.get('uid')
        )

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

    if name == "find_ical_emails":
        if not email_provider.available:
            return [
                types.TextContent(
                    type="text",
                    text="Error: Evolution is not available or not configured",
                )
            ]

        args = arguments or {}

        resource_data = await email_provider.find_ical_emails(
            account_name=args.get('account_name'),
            folder_names=args.get('folder_names'),
            days_back=args.get('days_back', 30),
            limit=args.get('limit', 50)
        )

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

    # Handle Muninn memory tools
    if name == "muninn_remember":
        if not muninn_provider.available:
            return [
                types.TextContent(
                    type="text",
                    text="Error: Muninn memory system is not available",
                )
            ]

        args = arguments or {}

        resource_data = await muninn_provider.remember(
            email_message_id=args.get('email_message_id'),
            email_subject=args.get('email_subject'),
            email_sender=args.get('email_sender'),
            email_date=args.get('email_date'),
            context=args.get('context'),
            tags=args.get('tags'),
            notes=args.get('notes')
        )

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

    if name == "muninn_recall":
        if not muninn_provider.available:
            return [
                types.TextContent(
                    type="text",
                    text="Error: Muninn memory system is not available",
                )
            ]

        args = arguments or {}

        resource_data = await muninn_provider.recall(
            email_message_id=args.get('email_message_id'),
            limit=args.get('limit', 10)
        )

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

    if name == "muninn_search":
        if not muninn_provider.available:
            return [
                types.TextContent(
                    type="text",
                    text="Error: Muninn memory system is not available",
                )
            ]

        args = arguments or {}

        resource_data = await muninn_provider.search_memories(
            query=args.get('query'),
            limit=args.get('limit', 10),
            sender=args.get('sender'),
            tags=args.get('tags')
        )

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

    if name == "muninn_update":
        if not muninn_provider.available:
            return [
                types.TextContent(
                    type="text",
                    text="Error: Muninn memory system is not available",
                )
            ]

        args = arguments or {}

        resource_data = await muninn_provider.update_memory(
            memory_id=args.get('memory_id'),
            context=args.get('context'),
            tags=args.get('tags'),
            notes=args.get('notes')
        )

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

    if name == "muninn_forget":
        if not muninn_provider.available:
            return [
                types.TextContent(
                    type="text",
                    text="Error: Muninn memory system is not available",
                )
            ]

        args = arguments or {}

        resource_data = await muninn_provider.forget_memory(
            memory_id=args.get('memory_id')
        )

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

    if name == "muninn_stats":
        if not muninn_provider.available:
            return [
                types.TextContent(
                    type="text",
                    text="Error: Muninn memory system is not available",
                )
            ]

        resource_data = await muninn_provider.get_stats()

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

    # Handle notification tools
    if name == "send_notification":
        args = arguments or {}
        title = args.get('title', 'Notification')
        body = args.get('body', '')
        urgency_str = args.get('urgency', 'normal')
        icon = args.get('icon', 'dialog-information')
        category = args.get('category')

        # Map urgency string to enum
        urgency_map = {
            'low': NotificationUrgency.LOW,
            'normal': NotificationUrgency.NORMAL,
            'critical': NotificationUrgency.CRITICAL,
        }
        urgency = urgency_map.get(urgency_str, NotificationUrgency.NORMAL)

        result = notification_manager.send_notification(
            title=title,
            body=body,
            urgency=urgency,
            icon=icon,
            category=category,
        )

        return [
            types.TextContent(
                type="text",
                text=serializer.to_json({'content': result}),
            )
        ]

    if name == "add_todo":
        result = PlanifyManager.quick_add()

        if result['success']:
            return [
                types.TextContent(
                    type="text",
                    text=serializer.to_json({'content': "Todo dialog opened. User will fill in the details."}),
                )
            ]
        else:
            return [
                types.TextContent(
                    type="text",
                    text=serializer.to_json({'content': f"Error opening todo dialog: {result['error']}"}),
                )
            ]

    if name == "compose_email":
        args = arguments or {}
        to = args.get('to', '')
        subject = args.get('subject', '')
        body = args.get('body', '')
        cc = args.get('cc')
        bcc = args.get('bcc')
        attachments = args.get('attachments')

        result = compose_email(to=to, subject=subject, body=body, cc=cc, bcc=bcc, attachments=attachments)

        if result['success']:
            msg = f"✅ Email composer opened for {to}"

            # Show attachment info clearly
            if result.get('attachments_to_add'):
                attachment_list = result['attachments_to_add']
                if result.get('zipped'):
                    msg += f"\n\n📎 ATTACHMENTS - Please manually attach this file:"
                    msg += f"\n  {attachment_list[0]}"
                    msg += f"\n  (Contains {result['original_file_count']} files)"
                else:
                    msg += f"\n\n📎 ATTACHMENTS - Please manually attach {len(attachment_list)} file(s):"
                    for att_path in attachment_list:
                        msg += f"\n  • {att_path}"

            # Add debug info if present
            if result.get('debug_info'):
                msg += f"\n\n🔍 Debug: {result['debug_info']}"

            return [
                types.TextContent(
                    type="text",
                    text=serializer.to_json({'content': msg}),
                )
            ]
        else:
            return [
                types.TextContent(
                    type="text",
                    text=serializer.to_json({'content': f"Error opening email composer: {result['error']}"}),
                )
            ]

    if name == "create_calendar_event":
        args = arguments or {}
        title = args.get('title', '')
        start_time = args.get('start_time', '')
        end_time = args.get('end_time', '')
        description = args.get('description', '')
        location = args.get('location', '')
        all_day = args.get('all_day', False)
        video_call_url = args.get('video_call_url')

        result = create_calendar_event(
            title=title,
            start_time=start_time,
            end_time=end_time,
            description=description,
            location=location,
            all_day=all_day,
            video_call_url=video_call_url
        )

        if result['success']:
            return [
                types.TextContent(
                    type="text",
                    text=serializer.to_json({'content': f"Calendar event '{title}' created and opened in GNOME Calendar"}),
                )
            ]
        else:
            return [
                types.TextContent(
                    type="text",
                    text=serializer.to_json({'content': f"Error creating calendar event: {result['error']}"}),
                )
            ]

    if name == "query_contacts":
        if not CONTACTS_AVAILABLE or contacts_manager is None:
            return [
                types.TextContent(
                    type="text",
                    text=serializer.to_json({'content': 'Evolution contacts not available'}),
                )
            ]

        args = arguments or {}
        query = args.get('query')
        email = args.get('email')
        name_query = args.get('name')
        limit = args.get('limit', 50)

        try:
            contacts = contacts_manager.search_contacts(
                query=query,
                email=email,
                name=name_query,
                limit=limit
            )

            return [
                types.TextContent(
                    type="text",
                    text=serializer.to_json({
                        'content': {
                            'contacts': contacts,
                            'count': len(contacts)
                        }
                    }),
                )
            ]
        except Exception as e:
            return [
                types.TextContent(
                    type="text",
                    text=serializer.to_json({'content': f'Error querying contacts: {str(e)}'}),
                )
            ]

    if name == "analyze_contact_communications":
        if not COMM_ANALYSIS_AVAILABLE or communication_analyzer is None:
            return [
                types.TextContent(
                    type="text",
                    text=serializer.to_json({'content': 'Contact communication analyzer not available'}),
                )
            ]

        args = arguments or {}
        my_email_addresses = args.get('my_email_addresses', [])
        days_back = args.get('days_back', 365)
        recent_days = args.get('recent_days')

        if not my_email_addresses:
            return [
                types.TextContent(
                    type="text",
                    text=serializer.to_json({'content': 'Error: my_email_addresses is required'}),
                )
            ]

        try:
            analysis = communication_analyzer.analyze_contact_emails(
                my_email_addresses=my_email_addresses,
                days_back=days_back,
                recent_days=recent_days
            )

            return [
                types.TextContent(
                    type="text",
                    text=serializer.to_json({'content': analysis}),
                )
            ]
        except Exception as e:
            import traceback
            return [
                types.TextContent(
                    type="text",
                    text=serializer.to_json({'content': f'Error analyzing communications: {str(e)}\n{traceback.format_exc()}'}),
                )
            ]

    if name == "analyze_sent_emails":
        if not SENT_EMAIL_ANALYSIS_AVAILABLE or sent_email_analyzer is None:
            resource_data = ResourceData(content={'content': 'Sent email analyzer not available'})
            return [
                types.TextContent(
                    type="text",
                    text=serializer.to_json(resource_data),
                )
            ]

        args = arguments or {}
        my_email_addresses = args.get('my_email_addresses', [])
        days_back = args.get('days_back', 365)
        recent_days = args.get('recent_days')

        if not my_email_addresses:
            resource_data = ResourceData(content={'content': 'Error: my_email_addresses is required'})
            return [
                types.TextContent(
                    type="text",
                    text=serializer.to_json(resource_data),
                )
            ]

        try:
            analysis = sent_email_analyzer.analyze_sent_emails(
                my_email_addresses=my_email_addresses,
                days_back=days_back,
                recent_days=recent_days
            )

            resource_data = ResourceData(content={'content': analysis})
            return [
                types.TextContent(
                    type="text",
                    text=serializer.to_json(resource_data),
                )
            ]
        except Exception as e:
            import traceback
            resource_data = ResourceData(content={'content': f'Error analyzing sent emails: {str(e)}\n{traceback.format_exc()}'})
            return [
                types.TextContent(
                    type="text",
                    text=serializer.to_json(resource_data),
                )
            ]

    if name == "send_urgent_notification":
        args = arguments or {}
        title = args.get('title', 'Urgent Notification')
        body = args.get('body', '')

        result = notification_manager.send_urgent_notification(
            title=title,
            body=body,
        )

        return [
            types.TextContent(
                type="text",
                text=serializer.to_json({'content': result}),
            )
        ]

    # Handle network scanning tool
    if name == "scan_wifi_networks":
        from ratatoskr_mcp_server.utils.network_scanner import scan_wifi_networks

        args = arguments or {}
        result = scan_wifi_networks(
            rescan=args.get('rescan', True),
            filter_pattern=args.get('filter_pattern'),
            min_signal_strength=args.get('min_signal_strength', 0)
        )

        return [
            types.TextContent(
                type="text",
                text=serializer.to_json({'content': result}),
            )
        ]

    # Handle markdown to PDF conversion
    if name == "convert_markdown_to_pdf":
        from ratatoskr_mcp_server.utils.markdown_converter import (
            convert_markdown_to_pdf,
            convert_multiple_markdown_to_pdf
        )

        args = arguments or {}
        markdown_path = args.get('markdown_path')
        markdown_paths = args.get('markdown_paths')

        # Single file conversion
        if markdown_path:
            result = convert_markdown_to_pdf(
                markdown_path=markdown_path,
                output_path=args.get('output_path'),
                title=args.get('title'),
                author=args.get('author'),
                temporary=args.get('temporary', False)
            )
        # Batch conversion
        elif markdown_paths:
            result = convert_multiple_markdown_to_pdf(
                markdown_paths=markdown_paths,
                output_dir=args.get('output_dir'),
                title=args.get('title'),
                author=args.get('author'),
                temporary=args.get('temporary', False)
            )
        else:
            result = {
                'success': False,
                'error': 'Either markdown_path or markdown_paths is required'
            }

        return [
            types.TextContent(
                type="text",
                text=serializer.to_json({'content': result}),
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
        "detect_network": "ratatoskr://system/network",
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
