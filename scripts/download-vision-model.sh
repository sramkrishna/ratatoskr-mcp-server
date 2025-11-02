#!/bin/bash
# Download a vision-capable LLM model for image analysis
#
# Usage: ./scripts/download-vision-model.sh [model-name]
#
# Available models:
#   llava-1.5-7b-q4  - LLaVA 1.5 7B quantized (recommended, ~4GB)
#   llava-1.6-34b-q4 - LLaVA 1.6 34B quantized (better quality, ~19GB)

set -euo pipefail

MODELS_DIR="${HOME}/.local/share/ratatoskr-mcp-server/models"
DEFAULT_MODEL="llava-1.5-7b-q4"
MODEL="${1:-$DEFAULT_MODEL}"

echo "========================================"
echo "Downloading Vision Model"
echo "========================================"
echo ""
echo "Model: $MODEL"
echo "Destination: $MODELS_DIR"
echo ""

# Create models directory
mkdir -p "$MODELS_DIR"

case "$MODEL" in
    llava-1.5-7b-q4)
        MODEL_FILE="llava-v1.5-7b-q4.llamafile"
        MODEL_URL="https://huggingface.co/jartine/llava-v1.5-7B-GGUF/resolve/main/llava-v1.5-7b-q4.llamafile"
        MODEL_SIZE="~4GB"
        ;;
    llava-1.6-34b-q4)
        MODEL_FILE="llava-v1.6-34b-q4.llamafile"
        MODEL_URL="https://huggingface.co/jartine/llava-v1.6-34B-GGUF/resolve/main/llava-v1.6-34b-q4.llamafile"
        MODEL_SIZE="~19GB"
        ;;
    *)
        echo "ERROR: Unknown model: $MODEL"
        echo ""
        echo "Available models:"
        echo "  llava-1.5-7b-q4  - LLaVA 1.5 7B quantized (recommended, ~4GB)"
        echo "  llava-1.6-34b-q4 - LLaVA 1.6 34B quantized (better quality, ~19GB)"
        exit 1
        ;;
esac

MODEL_PATH="$MODELS_DIR/$MODEL_FILE"

# Check if model already exists
if [ -f "$MODEL_PATH" ]; then
    echo "Model already exists at: $MODEL_PATH"
    echo ""
    read -p "Re-download? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Skipping download."
        exit 0
    fi
    rm -f "$MODEL_PATH"
fi

echo "Downloading $MODEL_FILE ($MODEL_SIZE)..."
echo "This may take a while depending on your internet connection."
echo ""

# Download with curl, showing progress
curl -L --progress-bar -o "$MODEL_PATH" "$MODEL_URL"

# Make executable
chmod +x "$MODEL_PATH"

echo ""
echo "✓ Model downloaded successfully!"
echo ""
echo "Model location: $MODEL_PATH"
echo "Size: $(du -h "$MODEL_PATH" | cut -f1)"
echo ""
echo "Next steps:"
echo "1. Test the model with: ./scripts/test-llamafile-container.sh"
echo "2. Run image analysis via MCP tools"
echo ""
