# Llamafile Vision Model Container
# This container provides a local LLM with vision capabilities for image analysis

FROM fedora:40

# Install dependencies
RUN dnf install -y \
    curl \
    ca-certificates \
    && dnf clean all

# Download llamafile binary
# Using the latest stable release
RUN curl -L -o /usr/local/bin/llamafile \
    https://github.com/Mozilla-Ocho/llamafile/releases/download/0.8.13/llamafile-0.8.13 \
    && chmod +x /usr/local/bin/llamafile

# Create directory for models
RUN mkdir -p /models

# Set working directory
WORKDIR /workspace

# Create wrapper script to run llamafile with sh (for APE compatibility)
RUN echo '#!/bin/sh' > /usr/local/bin/run-llamafile && \
    echo 'exec sh /usr/local/bin/llamafile "$@"' >> /usr/local/bin/run-llamafile && \
    chmod +x /usr/local/bin/run-llamafile

# Default entrypoint - uses sh to run llamafile for compatibility
ENTRYPOINT ["/usr/local/bin/run-llamafile"]

# Labels for metadata
LABEL org.opencontainers.image.title="Llamafile Vision"
LABEL org.opencontainers.image.description="Local LLM with vision capabilities for image analysis"
LABEL org.opencontainers.image.source="https://github.com/Mozilla-Ocho/llamafile"
LABEL maintainer="Ratatoskr MCP Server"
