"""Multi-backend vision system supporting llamafile, Ollama, and OpenVINO."""

import os
import subprocess
import base64
from pathlib import Path
from typing import Dict, Any, Optional
import requests


# Backend configuration
DEFAULT_BACKEND = os.getenv("VISION_BACKEND", "llamafile")
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OPENVINO_MODEL_PATH = os.getenv("OPENVINO_VISION_MODEL", os.path.expanduser("~/models/qwen2-vl-2b-openvino"))

# Supported formats
SUPPORTED_FORMATS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'}


def _build_command(cmd: list) -> list:
    """Build command with flatpak-spawn if needed."""
    import shutil
    if shutil.which('flatpak-spawn'):
        return ['flatpak-spawn', '--host'] + cmd
    return cmd


class VisionBackend:
    """Base class for vision backends."""

    def analyze_image(self, image_path: str, prompt: str) -> Dict[str, Any]:
        """Analyze an image. Returns dict with success, description, error."""
        raise NotImplementedError


class LlamafileBackend(VisionBackend):
    """Vision analysis using local llamafile in Podman."""

    CONTAINER_IMAGE = "localhost/ratatoskr-llamafile:latest"
    MODELS_DIR = os.path.expanduser("~/.local/share/ratatoskr-mcp-server/models")
    DEFAULT_MODEL = "llava-v1.5-7b-q4.llamafile"

    def check_setup(self) -> Dict[str, Any]:
        """Check if llamafile backend is ready."""
        # Check podman
        try:
            cmd = _build_command(['podman', '--version'])
            result = subprocess.run(cmd, capture_output=True, timeout=5)
            if result.returncode != 0:
                return {'ready': False, 'error': 'Podman not available'}
        except Exception as e:
            return {'ready': False, 'error': f'Podman check failed: {e}'}

        # Check container
        try:
            cmd = _build_command(['podman', 'image', 'exists', self.CONTAINER_IMAGE])
            result = subprocess.run(cmd, capture_output=True, timeout=5)
            if result.returncode != 0:
                return {'ready': False, 'error': 'Container image not found'}
        except Exception as e:
            return {'ready': False, 'error': f'Container check failed: {e}'}

        # Check model
        model_path = os.path.join(self.MODELS_DIR, self.DEFAULT_MODEL)
        if not os.path.exists(model_path):
            return {'ready': False, 'error': 'LLaVA model not found'}

        return {'ready': True}

    def analyze_image(self, image_path: str, prompt: str) -> Dict[str, Any]:
        """Analyze image using llamafile."""
        abs_path = os.path.abspath(os.path.expanduser(image_path))
        ext = Path(abs_path).suffix.lower()

        if not os.path.exists(abs_path):
            return {'success': False, 'error': f'Image not found: {abs_path}'}

        # Check setup
        setup = self.check_setup()
        if not setup['ready']:
            return {'success': False, 'error': setup['error']}

        # Run llamafile in container
        cmd = _build_command([
            'podman', 'run', '--rm',
            '-v', f'{self.MODELS_DIR}:/models:ro,z',
            '-v', f'{abs_path}:/tmp/image{ext}:ro,z',
            '--entrypoint', '/bin/sh',
            self.CONTAINER_IMAGE,
            f'/models/{self.DEFAULT_MODEL}',
            '--image', f'/tmp/image{ext}',
            '--prompt', prompt,
            '--temp', '0.1',
            '-n', '512'
        ])

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if result.returncode == 0:
                description = result.stdout.strip()
                return {
                    'success': True,
                    'description': description,
                    'backend': 'llamafile',
                    'model': self.DEFAULT_MODEL
                }
            else:
                return {'success': False, 'error': f'llamafile failed: {result.stderr}'}
        except subprocess.TimeoutExpired:
            return {'success': False, 'error': 'Analysis timed out'}
        except Exception as e:
            return {'success': False, 'error': f'llamafile error: {e}'}


class OllamaBackend(VisionBackend):
    """Vision analysis using remote Ollama server (GPU-accelerated)."""

    def __init__(self, host: str = None, model: str = "llava:7b"):
        self.host = host or OLLAMA_HOST
        self.model = model

    def check_setup(self) -> Dict[str, Any]:
        """Check if Ollama server is reachable."""
        try:
            response = requests.get(f"{self.host}/api/tags", timeout=5)
            if response.status_code == 200:
                models = response.json().get('models', [])
                model_names = [m['name'] for m in models]
                if self.model in model_names or any(self.model in n for n in model_names):
                    return {'ready': True}
                else:
                    return {
                        'ready': False,
                        'error': f'Model {self.model} not found on Ollama server. Available: {model_names}'
                    }
            else:
                return {'ready': False, 'error': f'Ollama server returned {response.status_code}'}
        except requests.exceptions.ConnectionError:
            return {'ready': False, 'error': f'Cannot connect to Ollama at {self.host}'}
        except Exception as e:
            return {'ready': False, 'error': f'Ollama check failed: {e}'}

    def analyze_image(self, image_path: str, prompt: str) -> Dict[str, Any]:
        """Analyze image using Ollama server."""
        abs_path = os.path.abspath(os.path.expanduser(image_path))

        if not os.path.exists(abs_path):
            return {'success': False, 'error': f'Image not found: {abs_path}'}

        # Check setup
        setup = self.check_setup()
        if not setup['ready']:
            return {'success': False, 'error': setup['error']}

        # Read and encode image
        try:
            with open(abs_path, 'rb') as f:
                image_data = base64.b64encode(f.read()).decode('utf-8')
        except Exception as e:
            return {'success': False, 'error': f'Failed to read image: {e}'}

        # Call Ollama API
        try:
            response = requests.post(
                f"{self.host}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "images": [image_data],
                    "stream": False
                },
                timeout=60
            )

            if response.status_code == 200:
                result = response.json()
                return {
                    'success': True,
                    'description': result['response'],
                    'backend': 'ollama',
                    'model': self.model,
                    'host': self.host
                }
            else:
                return {'success': False, 'error': f'Ollama returned {response.status_code}: {response.text}'}

        except requests.exceptions.Timeout:
            return {'success': False, 'error': 'Ollama request timed out'}
        except Exception as e:
            return {'success': False, 'error': f'Ollama error: {e}'}


class OpenVINOBackend(VisionBackend):
    """Vision analysis using local OpenVINO (NPU-accelerated)."""

    def __init__(self, model_path: str = None):
        self.model_path = model_path or OPENVINO_MODEL_PATH
        self._model = None
        self._pipe = None

    def check_setup(self) -> Dict[str, Any]:
        """Check if OpenVINO model is available."""
        if not os.path.exists(self.model_path):
            return {
                'ready': False,
                'error': f'OpenVINO model not found at {self.model_path}'
            }

        # Check if optimum-intel is installed
        try:
            import optimum.intel
            return {'ready': True}
        except ImportError:
            return {
                'ready': False,
                'error': 'optimum-intel not installed. Run: pip install optimum[openvino]'
            }

    def _load_model(self):
        """Lazy load the OpenVINO model."""
        if self._pipe is not None:
            return

        try:
            from optimum.intel.openvino import OVModelForVisualCausalLM
            from transformers import AutoProcessor

            self._model = OVModelForVisualCausalLM.from_pretrained(
                self.model_path,
                device="NPU"  # or "GPU" or "CPU"
            )
            self._pipe = AutoProcessor.from_pretrained(self.model_path)
        except Exception as e:
            raise RuntimeError(f"Failed to load OpenVINO model: {e}")

    def analyze_image(self, image_path: str, prompt: str) -> Dict[str, Any]:
        """Analyze image using OpenVINO."""
        abs_path = os.path.abspath(os.path.expanduser(image_path))

        if not os.path.exists(abs_path):
            return {'success': False, 'error': f'Image not found: {abs_path}'}

        # Check setup
        setup = self.check_setup()
        if not setup['ready']:
            return {'success': False, 'error': setup['error']}

        try:
            from PIL import Image

            # Load model if needed
            self._load_model()

            # Load and process image
            image = Image.open(abs_path)

            # Process with vision model
            inputs = self._pipe(text=prompt, images=image, return_tensors="pt")
            outputs = self._model.generate(**inputs, max_new_tokens=512)
            description = self._pipe.decode(outputs[0], skip_special_tokens=True)

            return {
                'success': True,
                'description': description,
                'backend': 'openvino',
                'model_path': self.model_path,
                'device': 'NPU'
            }

        except Exception as e:
            return {'success': False, 'error': f'OpenVINO error: {e}'}


# Backend registry
BACKENDS = {
    'llamafile': LlamafileBackend,
    'ollama': OllamaBackend,
    'openvino': OpenVINOBackend,
}


def get_backend(backend_name: str = None, **kwargs) -> VisionBackend:
    """
    Get a vision backend instance.

    Args:
        backend_name: 'llamafile', 'ollama', or 'openvino'
        **kwargs: Backend-specific arguments (e.g., ollama_host, model_path)

    Returns:
        VisionBackend instance
    """
    backend_name = backend_name or DEFAULT_BACKEND

    if backend_name not in BACKENDS:
        raise ValueError(f"Unknown backend: {backend_name}. Available: {list(BACKENDS.keys())}")

    backend_class = BACKENDS[backend_name]

    # Pass backend-specific kwargs
    if backend_name == 'ollama':
        return backend_class(host=kwargs.get('ollama_host'), model=kwargs.get('ollama_model', 'llava:7b'))
    elif backend_name == 'openvino':
        return backend_class(model_path=kwargs.get('openvino_model_path'))
    else:
        return backend_class()


def analyze_image_multi_backend(
    image_path: str,
    prompt: str = None,
    backend: str = None,
    **backend_kwargs
) -> Dict[str, Any]:
    """
    Analyze an image using specified backend.

    Args:
        image_path: Path to image file
        prompt: Analysis prompt
        backend: 'llamafile', 'ollama', or 'openvino' (defaults to env or 'llamafile')
        **backend_kwargs: Backend-specific arguments

    Returns:
        Dict with success, description, backend info, or error
    """
    if prompt is None:
        prompt = (
            "Describe this image in detail for accessibility and search purposes. "
            "Include: main subjects, actions, setting, colors, mood, and any text visible. "
            "Be concise but thorough."
        )

    try:
        vision_backend = get_backend(backend, **backend_kwargs)
        result = vision_backend.analyze_image(image_path, prompt)
        return result
    except Exception as e:
        return {
            'success': False,
            'error': f'Backend initialization failed: {e}'
        }
