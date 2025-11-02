"""Provider for searching files using TinySPARQL."""

from pathlib import Path
from ratatoskr_mcp_server.providers.base import ResourceProvider
from ratatoskr_mcp_server.resource_manager import ResourceData
from ratatoskr_mcp_server.utils.tracker import search_files, is_tracker_available


class FileSearchProvider(ResourceProvider):
    """Provides file search functionality via TinySPARQL."""

    def __init__(self):
        """Initialize the file search provider."""
        self._last_search_params = None

    async def get_resource(self, **kwargs) -> ResourceData:
        """
        Search for files using TinySPARQL.

        Parameters from kwargs:
            file_type: Type of file to search for ('pdf', 'image', 'video', etc.)
            directory: Directory to search in
            min_size_mb: Minimum file size in MB
            max_size_mb: Maximum file size in MB
            min_modified_date: Minimum modification date (YYYY-MM-DD)
            max_modified_date: Maximum modification date (YYYY-MM-DD)
            limit: Maximum number of results (default: 100)

        Returns:
            ResourceData with:
            - tracker_available: Whether TinySPARQL is running
            - search_params: Parameters used for search
            - results: List of matching files
            - count: Number of files found
        """
        try:
            # Check if Tracker is available
            if not is_tracker_available():
                return ResourceData(
                    content={
                        'tracker_available': False,
                        'note': 'TinySPARQL is not available or not running. File search requires TinySPARQL (GNOME LocalSearch) to be enabled.'
                    }
                )

            # Extract search parameters
            file_type = kwargs.get('file_type')
            directory = kwargs.get('directory')
            min_size_mb = kwargs.get('min_size_mb')
            max_size_mb = kwargs.get('max_size_mb')
            min_modified_date = kwargs.get('min_modified_date')
            max_modified_date = kwargs.get('max_modified_date')
            limit = kwargs.get('limit', 100)

            # Expand ~ in directory path if present
            if directory:
                directory = str(Path(directory).expanduser())

            # Store search params for reference
            search_params = {
                'file_type': file_type,
                'directory': directory,
                'min_size_mb': min_size_mb,
                'max_size_mb': max_size_mb,
                'min_modified_date': min_modified_date,
                'max_modified_date': max_modified_date,
                'limit': limit,
            }

            # Perform search
            results = search_files(
                file_type=file_type,
                directory=directory,
                min_size_mb=min_size_mb,
                max_size_mb=max_size_mb,
                min_modified_date=min_modified_date,
                max_modified_date=max_modified_date,
                limit=limit
            )

            # Group results by directory for better organization
            by_directory = {}
            for file_info in results:
                dir_path = str(Path(file_info['path']).parent)
                if dir_path not in by_directory:
                    by_directory[dir_path] = []
                by_directory[dir_path].append(file_info)

            # Calculate total size
            total_size_bytes = sum(f['size_bytes'] for f in results)
            total_size_mb = round(total_size_bytes / (1024 * 1024), 2)

            # Generate helpful summary
            summary = {
                'total_files': len(results),
                'total_size_mb': total_size_mb,
                'directories_found': len(by_directory),
                'truncated': len(results) >= limit,
            }

            return ResourceData(
                content={
                    'tracker_available': True,
                    'search_params': search_params,
                    'summary': summary,
                    'results': results,
                    'results_by_directory': by_directory,
                    'note': 'File search results from TinySPARQL (GNOME LocalSearch). Use this to identify file locations for organization and cleanup.'
                }
            )

        except Exception as e:
            return ResourceData(
                content={},
                error=f"Failed to search files: {str(e)}"
            )

    def close(self) -> None:
        """Clean up resources."""
        pass
