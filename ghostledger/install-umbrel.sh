#!/bin/bash
# GhostLedger Umbrel Installation Helper
# ========================================
# This script automates the installation of GhostLedger on Umbrel
# by building the Docker image locally on your Umbrel device.

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}================================${NC}"
echo -e "${GREEN}GhostLedger Umbrel Installer${NC}"
echo -e "${GREEN}================================${NC}"
echo ""

# Check if running on Umbrel
if [ ! -d "$HOME/umbrel" ] && [ ! -d "$HOME/umbrel-ghosts" ]; then
    echo -e "${RED}Error: This doesn't appear to be an Umbrel device.${NC}"
    echo "Expected to find ~/umbrel or ~/umbrel-ghosts directory."
    exit 1
fi

# Determine Umbrel installation directory
if [ -d "$HOME/umbrel" ]; then
    UMBREL_ROOT="$HOME/umbrel"
elif [ -d "$HOME/umbrel-ghosts" ]; then
    UMBREL_ROOT="$HOME/umbrel-ghosts"
fi

echo -e "${YELLOW}Detected Umbrel installation at: $UMBREL_ROOT${NC}"
echo ""

# Set installation paths
APP_DIR="$UMBREL_ROOT/app-data/ghostledger"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Step 1: Create app directory
echo -e "${YELLOW}[1/5] Creating app directory...${NC}"
mkdir -p "$APP_DIR"
echo -e "${GREEN}✓ Created $APP_DIR${NC}"
echo ""

# Step 2: Copy app files
echo -e "${YELLOW}[2/5] Copying application files...${NC}"
cp -r "$SCRIPT_DIR"/* "$APP_DIR/"
echo -e "${GREEN}✓ Files copied${NC}"
echo ""

# Step 3: Build Docker image
echo -e "${YELLOW}[3/5] Building Docker image (this may take 5-10 minutes)...${NC}"
cd "$APP_DIR"
docker build -t ghostledger:local .
echo -e "${GREEN}✓ Image built successfully${NC}"
echo ""

# Step 4: Start the app
echo -e "${YELLOW}[4/5] Starting GhostLedger...${NC}"
docker-compose up -d
echo -e "${GREEN}✓ App started${NC}"
echo ""

# Step 5: Verify installation
echo -e "${YELLOW}[5/5] Verifying installation...${NC}"
sleep 3
if docker-compose ps | grep -q "Up"; then
    echo -e "${GREEN}✓ GhostLedger is running!${NC}"
    echo ""
    echo -e "${GREEN}================================${NC}"
    echo -e "${GREEN}Installation Complete!${NC}"
    echo -e "${GREEN}================================${NC}"
    echo ""
    echo -e "Access GhostLedger at:"
    echo -e "${GREEN}http://$(hostname -I | awk '{print $1}'):8501${NC}"
    echo ""
    echo "To view logs:"
    echo "  docker-compose logs -f"
    echo ""
    echo "To stop:"
    echo "  docker-compose down"
    echo ""
    echo "To restart:"
    echo "  docker-compose restart"
else
    echo -e "${RED}✗ Something went wrong. Check logs:${NC}"
    echo "  docker-compose logs"
    exit 1
fi
