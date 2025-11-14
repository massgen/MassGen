#!/bin/bash
# Enable VNC viewer for Docker container to visualize Claude Computer Use actions

CONTAINER_NAME="${1:-cua-container}"
VNC_PORT="${2:-5900}"

echo "Enabling VNC viewer for container: $CONTAINER_NAME"
echo "VNC will be available on port: $VNC_PORT"

# Check if container exists and is running
if ! docker ps | grep -q "$CONTAINER_NAME"; then
    echo "❌ Container $CONTAINER_NAME is not running!"
    echo "Start it with: docker start $CONTAINER_NAME"
    exit 1
fi

# Start x11vnc inside the container
echo "Starting x11vnc server..."
docker exec -d "$CONTAINER_NAME" bash -c "x11vnc -display :99 -forever -shared -rfbport 5900 -nopw"

# Wait a moment for VNC to start
sleep 2

# Get the container's IP address
CONTAINER_IP=$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' "$CONTAINER_NAME")

echo ""
echo "✅ VNC server started successfully!"
echo ""
echo "To view the desktop:"
echo "  1. Install a VNC viewer (e.g., TigerVNC, RealVNC, or TightVNC)"
echo "  2. Connect to: $CONTAINER_IP:5900"
echo ""
echo "Or use SSH tunnel from remote machine:"
echo "  ssh -L $VNC_PORT:$CONTAINER_IP:5900 $(whoami)@$(hostname)"
echo "  Then connect to: localhost:$VNC_PORT"
echo ""
echo "To stop VNC:"
echo "  docker exec $CONTAINER_NAME pkill x11vnc"
echo ""
