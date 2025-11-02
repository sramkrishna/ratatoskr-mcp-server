# Ratatoskr MCP Server

MCP Server for GNOME integration, providing comprehensive desktop management, AI-powered image analysis, face recognition, and file operations via the Model Context Protocol.

## Features

### Core Desktop Integration
- **GNOME Desktop Information**: Query GNOME Shell version, mode, and settings via D-Bus
- **GNOME Extensions**: List and manage installed GNOME Shell extensions
- **Favorite Apps**: Access and manage pinned applications in the GNOME dash
- **Keybindings**: Query all GNOME keyboard shortcuts and keybindings
- **App Launch Tracking**: Monitor and analyze application usage patterns
- **Distribution Information**: Access OS distribution details

### AI-Powered Features
- **Image Analysis**: Analyze images using local LLaVA vision model (on-device, privacy-preserving)
- **Face Recognition**: Register and identify people in photos using ChromaDB vector database
- **Batch Processing**: Process multiple images simultaneously

### File Management
- **File Search**: Find files by type, size, date, and location using GNOME LocalSearch (TinySPARQL)
- **File Statistics**: Analyze disk usage, find large/old files, get housekeeping suggestions
- **Project Files**: Track recent activity in project directories
- **Document Extraction**: Extract text from PDFs, images, and documents using GNOME extractors
- **File Operations**: Move, copy, trash, rename files and manage directories (all safe operations)

### Privacy & Local Processing
All AI features run completely on-device:
- **Local LLaVA Model**: 4.3GB vision model runs in local container
- **Local Face Database**: ChromaDB stores face embeddings locally at `~/.local/share/ratatoskr-mcp-server/faces_db`
- **No Cloud APIs**: All processing happens on your machine

## Requirements

- Python 3.9 - 3.13 (Python 3.14+ not yet supported due to pydantic-core compatibility)
- GNOME desktop environment (for GNOME-specific features)
- D-Bus session bus
- **For Image Analysis**: Podman (container runtime for LLaVA model)
- **For Face Recognition**: dlib build dependencies (cmake, gcc, g++)

## Installation

### Basic Installation

```bash
python3.13 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### Installing Optional Features

#### Face Recognition Setup

Face recognition requires building dlib, which needs system dependencies:

```bash
# Fedora/RHEL
sudo dnf install cmake gcc gcc-c++ python3-devel

# Ubuntu/Debian
sudo apt install cmake build-essential python3-dev

# Then install Python dependencies
source .venv/bin/activate
pip install chromadb face-recognition pillow setuptools
```

#### Image Analysis Setup

Image analysis uses LLaVA 1.5 7B model running in a Podman container.

**1. Build the container (one-time setup):**
```bash
./scripts/build-llamafile-container.sh
```

**2. Download the vision model (~4.3GB):**
```bash
./scripts/download-vision-model.sh
```

The model is stored at `~/.local/share/ratatoskr-mcp-server/models/llava-v1.5-7b-q4.llamafile`

**Note on Performance:**
- First run: Model loads into memory (~4.3GB RAM usage)
- Subsequent images: Fast inference using loaded model
- The container stays running for efficiency

## Usage

### Running the Server

**Direct execution:**
```bash
source .venv/bin/activate
python src/ratatoskr_mcp_server/server.py
```

**Or use the installed command:**
```bash
ratatoskr-mcp-server
```

### MCP Client Configuration

#### Claude Desktop Configuration

Edit `~/.config/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "ratatoskr": {
      "command": "python",
      "args": ["/path/to/ratatoskr-mcp-server/src/ratatoskr_mcp_server/server.py"],
      "env": {
        "PYTHONPATH": "/path/to/ratatoskr-mcp-server/src"
      }
    }
  }
}
```

#### Generic MCP Client Configuration

```json
{
  "mcpServers": {
    "ratatoskr": {
      "command": "python",
      "args": ["/absolute/path/to/ratatoskr-mcp-server/src/ratatoskr_mcp_server/server.py"]
    }
  }
}
```

### Testing with MCP Inspector

```bash
npx @modelcontextprotocol/inspector python src/ratatoskr_mcp_server/server.py
```

## Available Resources

All resources are read-only and provide JSON data:

- `ratatoskr://gnome/desktop` - GNOME desktop environment information
- `ratatoskr://gnome/extensions` - Installed GNOME Shell extensions
- `ratatoskr://gnome/favorite-apps` - Pinned applications in GNOME dash
- `ratatoskr://gnome/keybindings` - All GNOME keyboard shortcuts
- `ratatoskr://gnome/app-stats` - Application launch statistics and usage patterns
- `ratatoskr://tracker/project-files` - Recent file activity in project directories
- `ratatoskr://tracker/file-stats` - System-wide file statistics and storage analysis
- `ratatoskr://distro/osinfo` - Distribution information

## Available Tools

### Desktop Information
- `get_desktop_info` - Get GNOME desktop information
- `get_distro_info` - Get Linux distribution details
- `get_gnome_extensions` - List installed GNOME extensions
- `get_favorite_apps` - Get pinned applications
- `get_keybindings` - Get all keyboard shortcuts
- `get_app_launch_stats` - Get application usage statistics

### File Discovery & Analysis
- `get_project_files` - Get recent file activity in project directories
- `get_file_statistics` - Get storage analysis and housekeeping suggestions
- `search_files` - Search files by type, size, date, and location
- `extract_document_content` - Extract text from PDFs, images, and documents

### File Operations (Safe)
- `move_files` - Move files to a directory (max 50 files)
- `copy_files` - Copy files to a directory (max 100 files)
- `trash_files` - Move files to trash/recycle bin (SAFE - max 10 files)
- `rename_file` - Rename a single file
- `create_directory` - Create a new directory
- `remove_directory` - Remove an empty directory

### AI-Powered Tools

#### Image Analysis
- `analyze_image` - Analyze a single image and write description to metadata
  - Uses local LLaVA 1.5 7B vision model
  - Writes to EXIF/XMP metadata for LocalSearch indexing
  - Custom prompts supported

- `analyze_images_batch` - Analyze multiple images (max 10)
  - Batch processing for efficiency
  - Same features as single image analysis

#### Face Recognition
- `manage_faces` - Register and identify people in photos
  - **Actions:**
    - `register` - Add a person's face (requires single face in image)
    - `identify` - Find registered people in an image
    - `list` - Show all registered people
    - `remove` - Delete a person from database
  - **Parameters:**
    - `action` (required): Action to perform
    - `person_name`: Name of person (for register/remove)
    - `image_path`: Path to image file
    - `replace_existing`: Replace existing faces (default: false)
    - `confidence_threshold`: Match threshold 0.0-1.0 (default: 0.6)

## Example Usage

### Face Recognition Workflow

```python
# 1. Register family members
manage_faces(
    action="register",
    person_name="Mom",
    image_path="/home/user/photos/mom_portrait.jpg"
)

manage_faces(
    action="register",
    person_name="Dad",
    image_path="/home/user/photos/dad_portrait.jpg"
)

# 2. Identify people in a group photo
manage_faces(
    action="identify",
    image_path="/home/user/photos/family_reunion.jpg",
    confidence_threshold=0.6
)

# 3. List all registered people
manage_faces(action="list")

# 4. Remove a person
manage_faces(action="remove", person_name="Mom")
```

### Image Analysis Workflow

```python
# Analyze a single image with custom prompt
analyze_image(
    image_path="/home/user/photos/vacation.jpg",
    prompt="Describe this vacation photo in detail, including location, activities, and people",
    write_metadata=True
)

# Batch analyze multiple images
analyze_images_batch(
    image_paths=[
        "/home/user/photos/photo1.jpg",
        "/home/user/photos/photo2.jpg",
        "/home/user/photos/photo3.jpg"
    ],
    write_metadata=True
)
```

### File Management Workflow

```python
# Find large old PDFs for cleanup
search_files(
    file_type="pdf",
    min_size_mb=10,
    max_modified_date="2024-01-01",
    directory="~/Downloads"
)

# Get storage analysis
get_file_statistics()

# Move files to organize
move_files(
    file_paths=["/home/user/Downloads/document.pdf"],
    destination="/home/user/Documents/Archive",
    overwrite=False
)
```

## Data Storage Locations

All data is stored locally in `~/.local/share/ratatoskr-mcp-server/`:

- `app_launches.db` - SQLite database for app launch tracking
- `faces_db/` - ChromaDB vector database for face recognition
- `models/` - AI models (llava-v1.5-7b-q4.llamafile, ~4.3GB)

## Development

### Project Structure

```
src/ratatoskr_mcp_server/
├── server.py                 # Main MCP server
├── resource_manager.py       # Resource management system
├── providers/                # Data providers
│   ├── base.py              # Base provider class
│   ├── gnome.py             # GNOME desktop provider
│   ├── extensions.py        # GNOME extensions provider
│   ├── favorite_apps.py     # Favorite apps provider
│   ├── keybindings.py       # Keybindings provider
│   ├── distro.py            # Distribution info provider
│   ├── app_stats.py         # App launch statistics
│   ├── project_files.py     # Project file activity
│   ├── file_stats.py        # File statistics provider
│   ├── file_search.py       # File search provider
│   ├── document_content.py  # Document extraction provider
│   ├── image_analyzer.py    # Image analysis with LLaVA
│   └── face_manager.py      # Face recognition provider
├── monitors/                 # Background monitors
│   ├── app_launch.py        # GNOME usage tracking
│   ├── dbus_launch_monitor.py    # Native app monitoring
│   └── systemd_launch_monitor.py # Flatpak app monitoring
└── utils/                    # Utilities
    ├── gsettings.py         # GSettings wrapper
    ├── tinysparql.py        # TinySPARQL/Tracker queries
    ├── app_launch_db.py     # App launch database
    ├── file_operations.py   # Safe file operations
    ├── face_database.py     # Face recognition database
    └── llamafile.py         # LLaVA vision model interface
```

### Running Tests

```bash
source .venv/bin/activate
pip install -e ".[dev]"
pytest tests/
```

### Adding New Providers

1. Create a new provider class inheriting from `ResourceProvider`
2. Implement the `get_resource()` method
3. Register in `resource_manager` in `server.py`
4. Add corresponding resource URI and tool definition

## Troubleshooting

### Face Recognition Issues

**Error: "No module named 'pkg_resources'"**
```bash
pip install setuptools
```

**Error: "ModuleNotFoundError: No module named 'chromadb'"**
```bash
pip install chromadb face-recognition pillow setuptools
```

**dlib build fails:**
- Ensure cmake and C++ compiler are installed
- On Fedora: `sudo dnf install cmake gcc gcc-c++ python3-devel`
- On Ubuntu: `sudo apt install cmake build-essential python3-dev`

### Image Analysis Issues

**Container not found:**
```bash
./scripts/build-llamafile-container.sh
```

**Model not found:**
```bash
./scripts/download-vision-model.sh
```

**SELinux permission errors:**
The scripts automatically handle SELinux with the `:z` flag for volume mounts.

### General Issues

**D-Bus errors:**
- Ensure running on host system, not in container
- Check GNOME Shell is running: `pgrep -a gnome-shell`

**Import errors:**
- Ensure virtual environment is activated: `source .venv/bin/activate`
- Reinstall: `pip install -e .`

## Performance Notes

### Image Analysis
- First image: 10-30 seconds (model loading)
- Subsequent images: 2-5 seconds per image
- Memory usage: ~4.3GB while container is running
- Container persists between calls for efficiency

### Face Recognition
- Registration: 1-3 seconds per face
- Identification: 2-5 seconds per image
- Scales well with multiple faces registered
- ChromaDB uses efficient vector similarity search

## Privacy & Security

- All AI processing happens locally on your machine
- No data sent to external APIs or cloud services
- Face database stored locally with no telemetry
- File operations restricted to user directories only
- Trash operations are reversible (no permanent deletion)
- Maximum file limits prevent accidental mass operations

## License

MIT

## Credits

- Uses [LLaVA 1.5 7B](https://llava-vl.github.io/) for vision AI
- Uses [ChromaDB](https://www.trychroma.com/) for vector similarity search
- Uses [face_recognition](https://github.com/ageitgey/face_recognition) library
- Integrates with GNOME LocalSearch (TinySPARQL) for file indexing
