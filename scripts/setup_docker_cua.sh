#!/bin/bash
# Setup script for Docker-based computer use environment

echo "Setting up Docker container for computer use..."

# Create a clean build directory
BUILD_DIR=$(mktemp -d)
echo "Using build directory: $BUILD_DIR"

# Create Dockerfile
cat > $BUILD_DIR/Dockerfile << 'EOF'
FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

# Install desktop environment and tools
RUN apt-get update && apt-get install -y \
    xvfb \
    x11vnc \
    xfce4 \
    xfce4-terminal \
    firefox \
    scrot \
    xdotool \
    imagemagick \
    && rm -rf /var/lib/apt/lists/*

# Set up X11
ENV DISPLAY=:99

# Start script
RUN echo '#!/bin/bash' > /start.sh && \
    echo 'Xvfb :99 -screen 0 1280x800x24 &' >> /start.sh && \
    echo 'sleep 2' >> /start.sh && \
    echo 'xfce4-session &' >> /start.sh && \
    echo 'tail -f /dev/null' >> /start.sh && \
    chmod +x /start.sh

CMD ["/start.sh"]
EOF

# Build the Docker image
echo "Building Docker image..."
docker build -t cua-ubuntu $BUILD_DIR

if [ $? -ne 0 ]; then
    echo "❌ Docker build failed!"
    rm -rf $BUILD_DIR
    exit 1
fi

# Remove existing container if it exists
if docker ps -a | grep -q cua-container; then
    echo "Removing existing container..."
    docker rm -f cua-container
fi

# Run the container
echo "Starting container..."
docker run -d --name cua-container cua-ubuntu

if [ $? -ne 0 ]; then
    echo "❌ Failed to start container!"
    rm -rf $BUILD_DIR
    exit 1
fi

# Wait for container to be ready
sleep 3

# Test the container
echo "Testing container..."
docker exec -e DISPLAY=:99 cua-container xdotool getmouselocation

if [ $? -eq 0 ]; then
    echo "✅ Docker container setup complete!"
    echo "You can now use the Docker example configuration."
else
    echo "❌ Container setup failed. Please check Docker logs:"
    echo "docker logs cua-container"
fi

# Cleanup
echo "Cleaning up build directory..."
rm -rf $BUILD_DIR
