#!/bin/bash
set -e

echo "Building ftp-web-preview from local source..."

# Build with kaniko (if available) or docker
cd /home/node/.openclaw/workspace/ftp-web-preview

# Option 1: If docker is available
if command -v docker &> /dev/null; then
    docker build -t 192.168.68.95:31443/ai-apps/ftp-web-preview:local-fixed .
    docker push 192.168.68.95:31443/ai-apps/ftp-web-preview:local-fixed
fi

echo "Build complete!"
