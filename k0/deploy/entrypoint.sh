#!/bin/sh
# K0 Kernel Entrypoint Script
# Ensures correct permissions for mounted volumes before starting the application

set -e

# Fix permissions on /data directory (mounted from host)
# This is necessary because Docker on Windows doesn't preserve Linux ownership
if [ -d /data ]; then
    echo "Fixing permissions on /data directory..."
    # Note: This runs as k0user (non-root), so we can only fix permissions if we run as root first
    # The Dockerfile will need to be modified to run this as root, then switch to k0user
    chmod -R u+rwX /data 2>/dev/null || echo "Warning: Could not fix /data permissions (may need root)"
fi

# Start the kernel
exec "$@"
