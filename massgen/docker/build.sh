#!/bin/bash
# Build script for MassGen Docker runtime image

set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Default values
IMAGE_NAME="massgen/mcp-runtime"
TAG="latest"
DOCKERFILE="massgen/docker/Dockerfile"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -t|--tag)
            TAG="$2"
            shift 2
            ;;
        -n|--name)
            IMAGE_NAME="$2"
            shift 2
            ;;
        -h|--help)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  -t, --tag TAG       Image tag (default: latest)"
            echo "  -n, --name NAME     Image name (default: massgen/mcp-runtime)"
            echo "  -h, --help          Show this help message"
            echo ""
            echo "Examples:"
            echo "  $0                                    # Build with default settings"
            echo "  $0 -t v1.0.0                          # Build with specific tag"
            echo "  $0 -n custom-runtime -t dev           # Custom name and tag"
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            echo "Use -h or --help for usage information"
            exit 1
            ;;
    esac
done

# Check if Docker is available
if ! command -v docker &> /dev/null; then
    echo -e "${RED}Error: Docker is not installed or not in PATH${NC}"
    echo "Please install Docker: https://docs.docker.com/get-docker/"
    exit 1
fi

# Check if Docker daemon is running
if ! docker info &> /dev/null; then
    echo -e "${RED}Error: Docker daemon is not running${NC}"
    echo "Please start Docker and try again"
    exit 1
fi

echo -e "${BLUE}Building MassGen Docker runtime image...${NC}"
echo -e "${BLUE}Image: ${IMAGE_NAME}:${TAG}${NC}"
echo ""

# Build the image
docker build \
    -t "${IMAGE_NAME}:${TAG}" \
    -f "${DOCKERFILE}" \
    .

echo ""
echo -e "${GREEN}✓ Build successful!${NC}"
echo ""
echo -e "${BLUE}Image details:${NC}"
docker images "${IMAGE_NAME}:${TAG}" --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}\t{{.CreatedAt}}"

echo ""
echo -e "${BLUE}To use this image:${NC}"
echo -e "1. Set command_line_execution_mode: \"docker\" in your config"
echo -e "2. (Optional) Set command_line_docker_image: \"${IMAGE_NAME}:${TAG}\""
echo ""
echo -e "${BLUE}Test the image:${NC}"
echo -e "  docker run --rm ${IMAGE_NAME}:${TAG} python --version"
echo -e "  docker run --rm ${IMAGE_NAME}:${TAG} node --version"
