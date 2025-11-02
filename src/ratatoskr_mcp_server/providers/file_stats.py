"""Provider for system-wide file statistics from TinySPARQL."""

from ratatoskr_mcp_server.providers.base import ResourceProvider
from ratatoskr_mcp_server.resource_manager import ResourceData
from ratatoskr_mcp_server.utils.tracker import (
    get_file_statistics_by_extension,
    get_largest_files,
    get_old_files,
    is_tracker_available
)


class FileStatisticsProvider(ResourceProvider):
    """Provides system-wide file statistics and storage analysis."""

    async def get_resource(self) -> ResourceData:
        """
        Get system-wide file statistics from TinySPARQL.

        Returns:
            ResourceData with:
            - tracker_available: Whether TinySPARQL is running
            - file_types: Statistics by file type (PDFs, images, videos, etc.)
            - largest_files: Top 20 largest files
            - old_files: Files not modified in over 1 year
            - housekeeping_suggestions: Recommendations for cleanup
        """
        try:
            # Check if Tracker is available
            if not is_tracker_available():
                return ResourceData(
                    content={
                        'tracker_available': False,
                        'note': 'TinySPARQL is not available or not running. File statistics require TinySPARQL (GNOME LocalSearch) to be enabled.'
                    }
                )

            # Get file statistics by type
            file_stats = get_file_statistics_by_extension()

            # Get largest files
            largest_files = get_largest_files(limit=20)

            # Get old files (not modified in 1 year)
            old_files = get_old_files(days=365, limit=30)

            # Calculate total storage usage
            total_indexed_size_bytes = sum(
                stats['total_size_bytes']
                for stats in file_stats.values()
                if 'total_size_bytes' in stats
            )
            total_indexed_size_gb = round(total_indexed_size_bytes / (1024 * 1024 * 1024), 2)

            # Generate housekeeping suggestions
            suggestions = []

            # Suggest cleaning up old files
            if old_files:
                total_old_size = sum(f['size_bytes'] for f in old_files)
                total_old_size_mb = round(total_old_size / (1024 * 1024), 2)
                suggestions.append({
                    'type': 'old_files',
                    'description': f'Found {len(old_files)} files not modified in over 1 year',
                    'potential_space_savings_mb': total_old_size_mb,
                    'action': 'Review and consider archiving or deleting old files'
                })

            # Suggest reviewing large files
            if largest_files:
                very_large_files = [f for f in largest_files if f['size_bytes'] > 1024 * 1024 * 1024]  # > 1GB
                if very_large_files:
                    suggestions.append({
                        'type': 'large_files',
                        'description': f'Found {len(very_large_files)} files larger than 1GB',
                        'largest_file': very_large_files[0]['filename'] if very_large_files else None,
                        'largest_file_size_gb': very_large_files[0]['size_gb'] if very_large_files else None,
                        'action': 'Review large files to identify candidates for compression or archival'
                    })

            # Suggest cleaning up disk images if many exist
            if 'iso_images' in file_stats and file_stats['iso_images']['count'] > 5:
                iso_stats = file_stats['iso_images']
                suggestions.append({
                    'type': 'disk_images',
                    'description': f'Found {iso_stats["count"]} ISO/disk image files',
                    'total_size_gb': iso_stats['total_size_gb'],
                    'action': 'Consider removing old ISO files that are no longer needed'
                })

            # Build summary statistics
            summary = {
                'total_indexed_size_gb': total_indexed_size_gb,
                'total_pdfs': file_stats.get('pdfs', {}).get('count', 0),
                'total_images': file_stats.get('images', {}).get('count', 0),
                'total_videos': file_stats.get('videos', {}).get('count', 0),
                'total_archives': file_stats.get('archives', {}).get('count', 0),
            }

            return ResourceData(
                content={
                    'tracker_available': True,
                    'summary': summary,
                    'file_types': file_stats,
                    'largest_files': largest_files,
                    'old_files': {
                        'files': old_files,
                        'count': len(old_files),
                        'note': 'Files not modified in over 1 year (showing up to 30)'
                    },
                    'housekeeping_suggestions': suggestions,
                    'note': 'File statistics from TinySPARQL (GNOME LocalSearch) indexer. Use this data to identify storage optimization opportunities.'
                }
            )

        except Exception as e:
            return ResourceData(
                content={},
                error=f"Failed to get file statistics: {str(e)}"
            )

    def close(self) -> None:
        """Clean up resources."""
        pass
