"""Provider for on-demand image analysis using multi-backend vision system."""

from ratatoskr_mcp_server.providers.base import ResourceProvider
from ratatoskr_mcp_server.resource_manager import ResourceData
from ratatoskr_mcp_server.utils.vision_backends import analyze_image_multi_backend
from ratatoskr_mcp_server.utils.vision_auto_backend import auto_select_backend


class ImageAnalyzerProvider(ResourceProvider):
    """Provides on-demand image analysis using configurable vision backends."""

    async def get_resource(
        self,
        image_path: str = None,
        image_paths: list = None,
        prompt: str = None,
        write_metadata: bool = True,
        backend: str = None,
        ollama_host: str = None,
        home_ssid: str = None,
        auto: bool = True
    ) -> ResourceData:
        """
        Analyze image(s) using multi-backend vision system.

        Args:
            image_path: Single image path to analyze
            image_paths: Multiple image paths for batch analysis
            prompt: Custom analysis prompt (optional)
            write_metadata: Whether to write description to image metadata
            backend: Vision backend: 'ollama', 'openvino', or 'llamafile'
                     If None and auto=True, auto-selects based on network
            ollama_host: Ollama server URL (e.g., 'http://nvidia-machine:11434')
            home_ssid: Home WiFi SSID for auto-detection
            auto: Auto-select backend based on network (default: True)

        Returns:
            ResourceData with analysis results and backend info
        """
        try:
            # Auto-select backend if requested
            if backend is None and auto:
                selection = auto_select_backend(
                    home_ssid=home_ssid,
                    ollama_host=ollama_host or "nvidia-machine"
                )
                backend = selection['backend']
                auto_reason = selection['reason']
            else:
                auto_reason = f"Manually selected backend: {backend or 'llamafile'}"

            # Single image analysis
            if image_path:
                result = analyze_image_multi_backend(
                    image_path=image_path,
                    prompt=prompt,
                    backend=backend,
                    ollama_host=ollama_host
                )

                if not result['success']:
                    return ResourceData(
                        content={'image_path': image_path, 'backend_attempted': backend},
                        error=result.get('error', 'Analysis failed')
                    )

                return ResourceData(
                    content={
                        'success': True,
                        'image_path': image_path,
                        'description': result['description'],
                        'backend': result.get('backend'),
                        'backend_selection': auto_reason,
                        'model': result.get('model', result.get('model_path', 'unknown')),
                        'note': f"Analyzed using {result.get('backend')} backend. {auto_reason}"
                    }
                )

            # Batch image analysis
            elif image_paths:
                analyzed = []
                failed = []

                for img_path in image_paths:
                    result = analyze_image_multi_backend(
                        image_path=img_path,
                        prompt=prompt,
                        backend=backend,
                        ollama_host=ollama_host
                    )

                    if result['success']:
                        analyzed.append({
                            'image_path': img_path,
                            'description': result['description'],
                            'backend': result.get('backend')
                        })
                    else:
                        failed.append({
                            'image_path': img_path,
                            'error': result.get('error')
                        })

                return ResourceData(
                    content={
                        'success': True,
                        'analyzed': analyzed,
                        'failed': failed,
                        'total_analyzed': len(analyzed),
                        'total_failed': len(failed),
                        'backend': backend,
                        'backend_selection': auto_reason,
                        'note': f"Batch analysis using {backend} backend. {auto_reason}"
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
