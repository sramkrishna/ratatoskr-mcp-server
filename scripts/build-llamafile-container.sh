#!/bin/bash
# Build the llamafile container image for local image analysis
#
# Usage: ./scripts/build-llamafile-container.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
CONTAINERFILE="$PROJECT_DIR/containers/llamafile.containerfile"

IMAGE_NAME="localhost/ratatoskr-llamafile"
IMAGE_TAG="latest"

# Detect if we need to use flatpak-spawn to access host podman
if command -v flatpak-spawn &> /dev/null; then
    PODMAN_CMD=(flatpak-spawn --host podman)
else
    PODMAN_CMD=(podman)
fi

echo "========================================"
echo "Building Llamafile Container Image"
echo "========================================"
echo ""
echo "Image: $IMAGE_NAME:$IMAGE_TAG"
echo "Containerfile: $CONTAINERFILE"
echo ""

# Check if podman is available
if ! "${PODMAN_CMD[@]}" --version &> /dev/null; then
    echo "ERROR: podman is not installed or not in PATH"
    echo "Please install podman to build the container"
    exit 1
fi

# Build the container
echo "Building container image..."
"${PODMAN_CMD[@]}" build \
    -t "$IMAGE_NAME:$IMAGE_TAG" \
    -f "$CONTAINERFILE" \
    "$PROJECT_DIR"

echo ""
echo "✓ Container image built successfully!"
echo ""
echo "Image details:"
"${PODMAN_CMD[@]}" images "$IMAGE_NAME:$IMAGE_TAG"

echo ""
echo "Next steps:"
echo "1. Download a vision model using: ./scripts/download-vision-model.sh"
echo "2. Test the container with: ./scripts/test-llamafile-container.sh"
echo ""
