"""Provider for extracting content from documents using LocalSearch extractors."""

from ratatoskr_mcp_server.providers.base import ResourceProvider
from ratatoskr_mcp_server.resource_manager import ResourceData
from ratatoskr_mcp_server.utils.tracker import extract_file_content


class DocumentContentProvider(ResourceProvider):
    """Provides on-demand content extraction from documents."""

    async def get_resource(self, file_path: str) -> ResourceData:
        """
        Extract content and metadata from a document file.

        Args:
            file_path: Path to the file to extract content from

        Returns:
            ResourceData with:
            - success: Whether extraction succeeded
            - file_path: The file path that was extracted
            - filename: Base name of the file
            - metadata: File metadata (format, page count, dimensions, etc.)
            - content: Extracted text content (for PDFs and text files)
            - content_stats: Statistics about the content (word count, character count, etc.)
            - error: Error message if extraction failed
        """
        try:
            if not file_path:
                return ResourceData(
                    content={},
                    error='file_path parameter is required'
                )

            # Extract content using LocalSearch
            result = extract_file_content(file_path)

            if not result['success']:
                return ResourceData(
                    content={'file_path': file_path},
                    error=result.get('error', 'Extraction failed')
                )

            return ResourceData(
                content={
                    'success': True,
                    'file_path': result['file_path'],
                    'filename': result['filename'],
                    'metadata': result.get('metadata', {}),
                    'content': result.get('content'),
                    'content_stats': result.get('content_stats'),
                    'note': 'Content extracted using LocalSearch native extractors. This leverages the same sandboxed extraction system used by GNOME for indexing.'
                }
            )

        except Exception as e:
            return ResourceData(
                content={},
                error=f"Failed to extract document content: {str(e)}"
            )

    def close(self) -> None:
        """Clean up resources."""
        pass
