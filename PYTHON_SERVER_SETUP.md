# ModuVision - Python Server Setup

## Overview

ModuVision consists of two parts:
1. **Node.js/Express Backend** - UI and data management (runs on port 3000)
2. **Python FastAPI Server** - Camera streaming and AI models (runs on port 8000)

The Python server handles:
- Camera streaming (RTSP, HTTP, IP cameras)
- YOLOv8 object detection and tracking
- Attendance tracking
- Security monitoring
- Fire/Smoke detection
- Weapon detection
- Parking management
- Heatmap generation
- And more...

## Prerequisites

### System Requirements
- Python 3.8+
- Node.js 16+
- CUDA 11.8+ (for GPU acceleration - optional but recommended)
- 4GB+ RAM (8GB+ recommended for AI models)

### Python Dependencies

Install required Python packages:

```bash
cd Code/Public/python
pip install -r requirements.txt
```

If `requirements.txt` doesn't exist, install these manually:

```bash
pip install fastapi uvicorn opencv-python ultralytics torch torchvision matplotlib pillow python-multipart numpy scipy
```

### Download YOLOv8 Models

The application uses YOLOv8 models. They will be downloaded automatically on first run, but you can pre-download them:

```bash
python -c "from ultralytics import YOLO; YOLO('yolov8s.pt')"
python -c "from ultralytics import YOLO; YOLO('yolov8n.pt')"
```

## Running the Application

### Method 1: Manual Start (Development)

**Terminal 1 - Start Node.js Server:**
```bash
cd Code
npm install
npm start
# or: node index.js
```

The UI will be available at: `http://localhost:3000`

**Terminal 2 - Start Python Server:**
```bash
cd Code/Public/python
python Server.py
```

The Python server will be available at: `http://localhost:8000`

### Method 2: Automated Start (Production-like)

The application can auto-start both servers. Make sure your `package.json` has:

```json
{
  "scripts": {
    "start": "node start-all.js"
  }
}
```

## Verification

### Check if servers are running:

**Python Server Status:**
```bash
curl http://localhost:8000/status
```

Expected response:
```json
{
  "status": "ok",
  "camera_source": "default",
  "pipeline": []
}
```

**Node.js Server:**
Visit `http://localhost:3000` in your browser

## Usage Flow

1. **Login** to ModuVision at `http://localhost:3000`
2. **Add a Camera** via the dashboard:
   - Click "Add Camera"
   - Enter camera name and URL (examples below)
   - Click "Add"
3. **Select a Camera** from the dropdown
4. **Drag AI Models** onto the canvas (Object Counting, Tracking, etc.)
5. **Apply Pipeline** to start processing
6. **Watch Live Stream** of the camera with AI detections

## Supported Camera URLs

### IP Cameras (HTTP/HTTPS):
```
http://192.168.1.100:8080/video
https://192.168.1.100:8443/stream
https://192.168.1.100:8080/video
```

### RTSP Streams:
```
rtsp://192.168.1.100:554/live
rtsp://username:password@camera.example.com/stream
```

### Local Webcam:
```
0 (or 1, 2, etc. for multiple cameras)
```

### YouTube/RTMP:
```
https://www.youtube.com/watch?v=VIDEO_ID
rtmp://server.com/live/stream
```

## Troubleshooting

### Python Server Not Starting
- Check Python version: `python --version` (should be 3.8+)
- Check CUDA availability: `nvidia-smi` (if GPU-enabled)
- Verify port 8000 is not in use: `lsof -i :8000`
- Check logs in Server.py output

### Camera Connection Issues
- Verify camera URL is correct and accessible
- Check firewall/network settings
- Try accessing camera URL directly in browser
- Ensure camera supports the protocol (HTTP, RTSP)

### Slow Performance
- Reduce frame size in Server.py
- Skip heavy models (use frame skipping)
- Enable GPU: Make sure CUDA is properly installed
- Reduce FPS setting

### Out of Memory
- Reduce number of concurrent models
- Lower video resolution
- Increase skip frames for heavy models

### Models Taking Too Long to Load
- First run downloads YOLOv8 models (~100MB)
- This is normal, subsequent runs will be faster
- Ensure internet connection for initial download

## API Endpoints

### Camera Management
- `POST /camera-proxy/set-camera` - Set active camera
- `GET /camera-proxy/stream/:cameraId` - Get video stream (MJPEG)
- `GET /camera-proxy/status` - Get server status

### Pipeline Management
- `POST /camera-proxy/set-pipeline` - Set AI pipeline

### Database Management
- `POST /user/addCamera` - Store camera in database
- `GET /user/getCameras` - Fetch user's cameras
- `DELETE /camera/:name` - Delete camera from database

## Configuration

### Modify Server Settings

Edit `Code/Public/python/Server.py`:

```python
# Frame skip for heavy models
SKIP_N = 2  # Process every 2nd frame

# Camera settings
CAP_PROP_FPS = 30
CAP_PROP_FRAME_WIDTH = 640
CAP_PROP_FRAME_HEIGHT = 480

# Worker threads
num_workers = 4
```

### Environment Variables

Create `.env` file in `Code/` directory:

```env
MONGO_URI=mongodb+srv://user:password@cluster.mongodb.net/moduvision
SESSION_SECRET=your-secret-key-here
PYTHON_SERVER_URL=http://localhost:8000
NODE_ENV=development
```

## Performance Tips

1. **Use GPU** - Install CUDA for 10-20x faster inference
2. **Lower Resolution** - 640x480 is faster than 1920x1080
3. **Frame Skipping** - Heavy models skip frames automatically
4. **Pipeline Order** - Put lightweight models first
5. **Connection Quality** - Good network reduces latency

## Advanced: Running on Different Machines

**Python server on machine A, Node.js on machine B:**

Set environment variable on Node.js machine:
```bash
export PYTHON_SERVER_URL=http://MACHINE_A_IP:8000
npm start
```

## Support

For issues:
1. Check server logs (Terminal output)
2. Verify network connectivity
3. Ensure all dependencies installed
4. Check camera URL accessibility
5. Review firewall settings

---

**Happy Streaming! 🎥**
