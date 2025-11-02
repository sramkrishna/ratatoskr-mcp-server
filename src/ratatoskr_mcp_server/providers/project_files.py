"""Provider for project file activity from TinySPARQL."""

from pathlib import Path
from collections import defaultdict
from typing import Optional

from ratatoskr_mcp_server.providers.base import ResourceProvider
from ratatoskr_mcp_server.resource_manager import ResourceData
from ratatoskr_mcp_server.utils.tracker import (
    get_recent_files,
    get_file_type_stats,
    get_recent_documents,
    get_recent_images,
    get_recent_media,
    is_tracker_available
)


class ProjectFilesProvider(ResourceProvider):
    """Provides file activity information for project directories."""

    def __init__(self, project_paths: Optional[list[str]] = None):
        """
        Initialize the provider.

        Args:
            project_paths: List of project directory paths to track.
                          If None, uses a default set of common project locations.
        """
        if project_paths is None:
            # Default project locations
            home = Path.home()
            project_paths = [
                str(home / 'Projects'),
                str(home / 'Developer'),
                str(home / 'Code'),
                str(home / 'workspace'),
            ]

        # Filter to only existing directories
        self.project_paths = [
            path for path in project_paths
            if Path(path).exists() and Path(path).is_dir()
        ]

    async def get_resource(self) -> ResourceData:
        """
        Get file activity information from TinySPARQL.

        Returns:
            ResourceData with:
            - tracker_available: Whether TinySPARQL is running
            - projects: List of project directories with file activity (directory-organized view)
              For each project:
              - path: Project directory path
              - recent_files: Recently modified files (last 7 days)
              - file_type_summary: Count of files by type
              - total_recent_files: Total count of recent files
            - recent_by_type: Files organized by type (type-organized view)
              - documents: Recent PDFs, text files, office documents
              - images: Recent image files (PNG, JPG, etc.)
              - media: Recent audio and video files
        """
        try:
            # Check if Tracker is available
            if not is_tracker_available():
                return ResourceData(
                    content={
                        'tracker_available': False,
                        'note': 'TinySPARQL is not available or not running. File activity tracking requires TinySPARQL (GNOME LocalSearch) to be enabled.'
                    }
                )

            projects_data = []

            for project_path in self.project_paths:
                # Get recent files for this project
                recent_files = get_recent_files(project_path, days=7, limit=50)

                if not recent_files:
                    # Skip projects with no recent activity
                    continue

                # Get file type statistics
                file_type_stats = get_file_type_stats(project_path, days=7)

                # Organize files by subdirectory for better context
                files_by_dir = defaultdict(list)
                for file_info in recent_files:
                    file_path = Path(file_info.get('path', ''))
                    parent = file_path.parent

                    # Get relative path from project root
                    try:
                        rel_parent = parent.relative_to(project_path)
                        dir_key = str(rel_parent) if str(rel_parent) != '.' else '(root)'
                    except ValueError:
                        dir_key = str(parent)

                    files_by_dir[dir_key].append({
                        'filename': file_info['filename'],
                        'path': file_info.get('path', ''),
                        'modified': file_info.get('modified_timestamp', ''),
                        'type': file_info.get('mime_type', 'unknown')
                    })

                # Convert mime types to more readable categories
                type_categories = self._categorize_file_types(file_type_stats)

                project_info = {
                    'path': project_path,
                    'name': Path(project_path).name,
                    'total_recent_files': len(recent_files),
                    'file_type_summary': type_categories,
                    'files_by_directory': dict(files_by_dir),
                    'note': 'Files modified in the last 7 days'
                }

                projects_data.append(project_info)

            # Get type-specific file activity across all project directories
            # Query each project directory for type-specific files
            all_documents = []
            all_images = []
            all_media = {'audio': [], 'video': []}

            for project_path in self.project_paths:
                # Get documents from this project
                docs = get_recent_documents(directory=project_path, days=7, limit=20)
                all_documents.extend(docs)

                # Get images from this project
                images = get_recent_images(directory=project_path, days=7, limit=20)
                all_images.extend(images)

                # Get media from this project
                media = get_recent_media(directory=project_path, days=7, limit=20)
                all_media['audio'].extend(media.get('audio', []))
                all_media['video'].extend(media.get('video', []))

            # Sort by modification time (most recent first)
            all_documents.sort(key=lambda x: x.get('modified', ''), reverse=True)
            all_images.sort(key=lambda x: x.get('modified', ''), reverse=True)
            all_media['audio'].sort(key=lambda x: x.get('modified', ''), reverse=True)
            all_media['video'].sort(key=lambda x: x.get('modified', ''), reverse=True)

            # Limit to top results
            all_documents = all_documents[:30]
            all_images = all_images[:30]
            all_media['audio'] = all_media['audio'][:20]
            all_media['video'] = all_media['video'][:20]

            return ResourceData(
                content={
                    'tracker_available': True,
                    'projects_tracked': len(self.project_paths),
                    'projects_with_activity': len(projects_data),
                    'projects': projects_data,
                    'recent_by_type': {
                        'documents': {
                            'files': all_documents,
                            'count': len(all_documents),
                            'note': 'PDFs, text files, office documents modified in last 7 days'
                        },
                        'images': {
                            'files': all_images,
                            'count': len(all_images),
                            'note': 'Image files (PNG, JPG, etc.) modified in last 7 days'
                        },
                        'media': {
                            'audio': all_media['audio'],
                            'video': all_media['video'],
                            'audio_count': len(all_media['audio']),
                            'video_count': len(all_media['video']),
                            'note': 'Audio and video files modified in last 7 days'
                        }
                    },
                    'note': 'File activity from TinySPARQL (GNOME LocalSearch) indexer. Provides both project-based and type-based views of recent file activity (last 7 days).'
                }
            )

        except Exception as e:
            return ResourceData(
                content={},
                error=f"Failed to get project file activity: {str(e)}"
            )

    def _categorize_file_types(self, mime_stats: dict[str, int]) -> dict[str, int]:
        """
        Convert MIME types to readable categories.

        Args:
            mime_stats: Dictionary of MIME type to count

        Returns:
            Dictionary of category to count
        """
        categories = defaultdict(int)

        for mime_type, count in mime_stats.items():
            category = self._get_category(mime_type)
            categories[category] += count

        return dict(categories)

    def _get_category(self, mime_type: str) -> str:
        """
        Get a readable category for a MIME type.

        Args:
            mime_type: MIME type string

        Returns:
            Category name
        """
        if not mime_type or mime_type == 'unknown':
            return 'other'

        # Programming languages
        if any(lang in mime_type for lang in ['python', 'javascript', 'typescript', 'rust', 'go', 'java', 'c++', 'c-source']):
            return 'code'

        # Text and documents
        if mime_type.startswith('text/'):
            if 'markdown' in mime_type or 'x-rst' in mime_type:
                return 'documentation'
            if 'json' in mime_type or 'yaml' in mime_type or 'toml' in mime_type or 'xml' in mime_type:
                return 'configuration'
            return 'text'

        # Application types
        if mime_type.startswith('application/'):
            if 'json' in mime_type:
                return 'configuration'
            if 'sql' in mime_type or 'database' in mime_type:
                return 'database'
            if 'pdf' in mime_type:
                return 'document'
            if 'zip' in mime_type or 'tar' in mime_type or 'gzip' in mime_type:
                return 'archive'
            return 'application'

        # Images
        if mime_type.startswith('image/'):
            return 'image'

        # Audio/Video
        if mime_type.startswith('audio/') or mime_type.startswith('video/'):
            return 'media'

        return 'other'

    def close(self) -> None:
        """Clean up resources."""
        pass
