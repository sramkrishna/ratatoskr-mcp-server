"""Provider for on-demand image analysis using local vision LLM."""

from ratatoskr_mcp_server.providers.base import ResourceProvider
from ratatoskr_mcp_server.resource_manager import ResourceData
from ratatoskr_mcp_server.utils.image_analysis import analyze_image, analyze_images_batch


class ImageAnalyzerProvider(ResourceProvider):
    """Provides on-demand image analysis using local vision model."""

    async def get_resource(
        self,
        image_path: str = None,
        image_paths: list = None,
        prompt: str = None,
        write_metadata: bool = True,
        model: str = None
    ) -> ResourceData:
        """
        Analyze image(s) using a local vision LLM.

        Args:
            image_path: Single image path to analyze
            image_paths: Multiple image paths for batch analysis
            prompt: Custom analysis prompt (optional)
            write_metadata: Whether to write description to image metadata
            model: Model filename to use (optional)

        Returns:
            ResourceData with analysis results
        """
        try:
            # Single image analysis
            if image_path:
                result = analyze_image(
                    image_path=image_path,
                    prompt=prompt,
                    write_metadata=write_metadata,
                    model=model
                )

                if not result['success']:
                    return ResourceData(
                        content={'image_path': image_path},
                        error=result.get('error', 'Analysis failed')
                    )

                return ResourceData(
                    content={
                        'success': True,
                        'image_path': result['image_path'],
                        'description': result['description'],
                        'metadata_written': result.get('metadata_written', False),
                        'note': 'Image analyzed using local vision LLM. Description written to metadata and indexed by LocalSearch for search.'
                    }
                )

            # Batch image analysis
            elif image_paths:
                result = analyze_images_batch(
                    image_paths=image_paths,
                    prompt=prompt,
                    write_metadata=write_metadata,
                    model=model
                )

                if not result['success']:
                    return ResourceData(
                        content={},
                        error=result.get('error', 'Batch analysis failed')
                    )

                return ResourceData(
                    content={
                        'success': True,
                        'analyzed': result['analyzed'],
                        'failed': result.get('failed', []),
                        'total_analyzed': result['total_analyzed'],
                        'total_failed': result['total_failed'],
                        'note': 'Images analyzed using local vision LLM. Descriptions written to metadata and indexed by LocalSearch.'
                    }
                )

            else:
                return ResourceData(
                    content={},
                    error='Either image_path or image_paths parameter is required'
                )

        except Exception as e:
            return ResourceData(
                content={},
                error=f"Image analysis failed: {str(e)}"
            )

    def close(self) -> None:
        """Clean up resources."""
        pass
