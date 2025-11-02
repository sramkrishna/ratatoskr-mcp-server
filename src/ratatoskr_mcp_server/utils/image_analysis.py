"""Image analysis using local LLM via containerized llamafile."""

import os
import subprocess
import json
from pathlib import Path
from typing import Dict, Any


# Container and model configuration
CONTAINER_IMAGE = "localhost/ratatoskr-llamafile:latest"
MODELS_DIR = os.path.expanduser("~/.local/share/ratatoskr-mcp-server/models")
DEFAULT_MODEL = "llava-v1.5-7b-q4.llamafile"

# Supported image formats
SUPPORTED_FORMATS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'}


def _build_command(cmd: list) -> list:
    """Build command with flatpak-spawn if we need to access the host."""
    import shutil
    if shutil.which('flatpak-spawn'):
        return ['flatpak-spawn', '--host'] + cmd
    return cmd


def _check_setup() -> Dict[str, Any]:
    """
    Check if the container and model are set up correctly.

    Returns:
        Dict with 'ready' (bool) and 'error' (str) if not ready
    """
    # Check if podman is available
    try:
        cmd = _build_command(['podman', '--version'])
        result = subprocess.run(cmd, capture_output=True, timeout=5)
        if result.returncode != 0:
            return {
                'ready': False,
                'error': 'Podman is not available. Please install podman.'
            }
    except Exception as e:
        return {
            'ready': False,
            'error': f'Failed to check podman: {str(e)}'
        }

    # Check if container image exists
    try:
        cmd = _build_command(['podman', 'image', 'exists', CONTAINER_IMAGE])
        result = subprocess.run(cmd, capture_output=True, timeout=5)
        if result.returncode != 0:
            return {
                'ready': False,
                'error': f'Container image not found. Please run: ./scripts/build-llamafile-container.sh'
            }
    except Exception as e:
        return {
            'ready': False,
            'error': f'Failed to check container image: {str(e)}'
        }

    # Check if model exists
    model_path = os.path.join(MODELS_DIR, DEFAULT_MODEL)
    if not os.path.exists(model_path):
        return {
            'ready': False,
            'error': f'Vision model not found. Please run: ./scripts/download-vision-model.sh'
        }

    return {'ready': True}


def analyze_image(
    image_path: str,
    prompt: str = None,
    write_metadata: bool = True,
    model: str = None
) -> Dict[str, Any]:
    """
    Analyze an image using a local vision LLM.

    Args:
        image_path: Path to the image file to analyze
        prompt: Custom prompt for the analysis (uses default if None)
        write_metadata: Whether to write the description to image metadata
        model: Model filename to use (uses default if None)

    Returns:
        Dict with:
        - success: Whether analysis succeeded
        - image_path: The analyzed image path
        - description: Generated description
        - metadata_written: Whether metadata was written
        - error: Error message if failed
    """
    try:
        # Expand and validate path
        abs_path = os.path.abspath(os.path.expanduser(image_path))

        if not os.path.exists(abs_path):
            return {
                'success': False,
                'image_path': image_path,
                'error': f'Image file not found: {abs_path}'
            }

        # Check file extension
        ext = Path(abs_path).suffix.lower()
        if ext not in SUPPORTED_FORMATS:
            return {
                'success': False,
                'image_path': abs_path,
                'error': f'Unsupported image format: {ext}. Supported: {", ".join(SUPPORTED_FORMATS)}'
            }

        # Check setup
        setup_check = _check_setup()
        if not setup_check['ready']:
            return {
                'success': False,
                'image_path': abs_path,
                'error': setup_check['error']
            }

        # Use default model if not specified
        model_file = model or DEFAULT_MODEL
        model_path = os.path.join(MODELS_DIR, model_file)

        # Default prompt optimized for metadata and search
        if prompt is None:
            prompt = (
                "Describe this image in detail for accessibility and search purposes. "
                "Include: main subjects, actions, setting, colors, mood, and any text visible. "
                "Be concise but thorough."
            )

        # Build podman command to run llamafile
        # Run the llamafile directly (it's self-contained with model and projector)
        # Use :z for SELinux relabeling to allow container access
        cmd = _build_command([
            'podman', 'run', '--rm',
            '-v', f'{MODELS_DIR}:/models:ro,z',
            '-v', f'{abs_path}:/tmp/image{ext}:ro,z',
            '--entrypoint', '/bin/sh',
            CONTAINER_IMAGE,
            f'/models/{model_file}',  # Run llamafile directly
            '--image', f'/tmp/image{ext}',
            '--temp', '0',  # Deterministic output
            '-ngl', '35',   # GPU layers (if available)
            '-p', prompt
        ])

        # Run the analysis (this can take 10-60 seconds)
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120  # 2 minute timeout
        )

        if result.returncode != 0:
            return {
                'success': False,
                'image_path': abs_path,
                'error': f'Analysis failed: {result.stderr}'
            }

        # Extract description from output
        description = result.stdout.strip()

        if not description:
            return {
                'success': False,
                'image_path': abs_path,
                'error': 'No description generated'
            }

        response = {
            'success': True,
            'image_path': abs_path,
            'description': description,
            'metadata_written': False
        }

        # Optionally write to metadata
        if write_metadata:
            metadata_result = _write_image_metadata(abs_path, description)
            response['metadata_written'] = metadata_result['success']
            if not metadata_result['success']:
                response['metadata_warning'] = metadata_result.get('error')

        return response

    except subprocess.TimeoutExpired:
        return {
            'success': False,
            'image_path': abs_path,
            'error': 'Analysis timed out (>2 minutes). Try a smaller model or simpler image.'
        }
    except Exception as e:
        return {
            'success': False,
            'image_path': image_path,
            'error': f'Analysis failed: {str(e)}'
        }


def _write_image_metadata(image_path: str, description: str) -> Dict[str, Any]:
    """
    Write the description to image EXIF/XMP metadata using exiftool.

    Args:
        image_path: Path to the image file
        description: Description to write

    Returns:
        Dict with success status
    """
    try:
        # Use exiftool to write metadata
        # Write to multiple fields for maximum compatibility
        cmd = _build_command([
            'exiftool',
            '-overwrite_original',
            f'-Description={description}',
            f'-ImageDescription={description}',
            f'-XMP:Description={description}',
            f'-Caption-Abstract={description}',
            image_path
        ])

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10
        )

        if result.returncode != 0:
            return {
                'success': False,
                'error': f'Failed to write metadata: {result.stderr}'
            }

        # Trigger LocalSearch to re-index the file
        _trigger_reindex(image_path)

        return {'success': True}

    except Exception as e:
        return {
            'success': False,
            'error': f'Failed to write metadata: {str(e)}'
        }


def _trigger_reindex(file_path: str) -> None:
    """
    Trigger LocalSearch to re-index a file.

    This is optional - LocalSearch will eventually pick up the changes,
    but this makes them immediately searchable.
    """
    try:
        cmd = _build_command(['localsearch', 'index', '--file', file_path])
        subprocess.run(cmd, capture_output=True, timeout=10)
    except Exception:
        # Silently fail - reindexing will happen eventually anyway
        pass


def analyze_images_batch(
    image_paths: list,
    prompt: str = None,
    write_metadata: bool = True,
    model: str = None,
    max_batch: int = 10
) -> Dict[str, Any]:
    """
    Analyze multiple images in batch.

    Args:
        image_paths: List of image file paths
        prompt: Custom prompt for analysis
        write_metadata: Whether to write descriptions to metadata
        model: Model filename to use
        max_batch: Maximum number of images to process

    Returns:
        Dict with:
        - success: Overall success status
        - analyzed: List of successfully analyzed images
        - failed: List of failed images with errors
        - total_analyzed: Count of successful analyses
        - total_failed: Count of failures
    """
    if len(image_paths) > max_batch:
        return {
            'success': False,
            'error': f'Batch size ({len(image_paths)}) exceeds maximum ({max_batch})'
        }

    analyzed = []
    failed = []

    for image_path in image_paths:
        result = analyze_image(image_path, prompt, write_metadata, model)

        if result['success']:
            analyzed.append(result)
        else:
            failed.append({
                'image_path': result.get('image_path', image_path),
                'error': result.get('error')
            })

    return {
        'success': len(analyzed) > 0,
        'analyzed': analyzed,
        'failed': failed,
        'total_analyzed': len(analyzed),
        'total_failed': len(failed)
    }
