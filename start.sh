#!/bin/bash

# ModuVision Startup Script
# This script starts both the Node.js server and Python server

echo "=========================================="
echo "🚀 ModuVision - Starting All Services..."
echo "=========================================="

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Start Node.js Server
echo -e "${BLUE}📱 Starting Node.js Server on port 3000...${NC}"
cd Code
node index.js &
NODE_PID=$!
echo -e "${GREEN}✓ Node.js Server started (PID: $NODE_PID)${NC}"

# Wait a moment for Node to start
sleep 2

# Start Python Server
echo -e "${BLUE}🐍 Starting Python FastAPI Server on port 8000...${NC}"
cd Public/python
python Server.py &
PYTHON_PID=$!
echo -e "${GREEN}✓ Python Server started (PID: $PYTHON_PID)${NC}"

echo ""
echo "=========================================="
echo "✅ All Services Started!"
echo "=========================================="
echo "Node.js API:    http://localhost:3000"
echo "Python API:     http://localhost:8000"
echo "WebSocket:      ws://localhost:8000/ws"
echo "Video Stream:   http://localhost:8000/video"
echo "=========================================="
echo ""
echo "Press Ctrl+C to stop all services"
echo ""

# Wait for both processes
wait $NODE_PID $PYTHON_PID
