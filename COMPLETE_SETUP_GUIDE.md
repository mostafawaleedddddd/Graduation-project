# ModuVision - Complete Setup Guide

## Overview
Your project has **two components**:
1. **Frontend UI** (Node.js/Express) - Deployed on Vercel ✓
2. **Backend AI Server** (Python/FastAPI) - Needs to run locally on your machine

---

## Part 1: Frontend UI (Already Deployed)

Your UI is live at:
**https://graduation-project-tgra.vercel.app**

### Features Available:
- User authentication (sign up, login)
- Dashboard with camera management
- Model/pipeline selection and drag-drop
- Project management
- Split view for multiple cameras

---

## Part 2: Python Backend Server (Local Setup Required)

The Python backend handles:
- Real-time camera streaming (IP cameras, RTSP, HTTP)
- YOLO object detection models
- Custom AI pipelines
- Alert notifications
- Parking management

### Prerequisites
1. **Python 3.8+** installed
2. **GPU** (NVIDIA with CUDA - recommended for real-time inference)
3. **Git** installed

### Step-by-Step Installation

#### Step 1: Clone Your Repository
```bash
git clone https://github.com/mostafawaleedddddd/Graduation-project.git
cd Graduation-project
```

#### Step 2: Create Python Virtual Environment
```bash
python -m venv venv

# On Windows:
venv\Scripts\activate

# On macOS/Linux:
source venv/bin/activate
```

#### Step 3: Install Python Dependencies
```bash
cd Code/Public/python
pip install -r requirements.txt
```

**Key dependencies:**
- fastapi
- opencv-python
- torch (with CUDA)
- ultralytics (YOLOv8)
- numpy
- requests

#### Step 4: Download YOLO Models
The first run will automatically download required models (~500MB-2GB):
- YOLOv8n (nano)
- YOLOv8m (medium)
- YOLOv8l (large)

#### Step 5: Run the Python Server
```bash
python Server.py
```

Expected output:
```
INFO:     Uvicorn running on http://127.0.0.1:5000
```

The server will listen on `http://localhost:5000`

---

## Part 3: Connecting Frontend to Backend

### Option A: Local Testing (Recommended First)

1. **Start Python Server**
   ```bash
   cd Code/Public/python
   python Server.py
   ```

2. **Start Node.js Server (Local Development)**
   ```bash
   cd Code
   npm install
   npm start
   ```
   Access at `http://localhost:3000`

3. **Frontend will automatically connect** to Python backend at `http://127.0.0.1:5000`

### Option B: Using Deployed Frontend with Local Backend

1. **Start Python Server**
   ```bash
   python Server.py
   ```

2. **Visit deployed UI**
   - Go to https://graduation-project-tgra.vercel.app
   - The frontend will try to connect to your local Python server
   - **Important:** Your Python server must be accessible from the internet or you need to use a tunneling solution

---

## Part 4: IP Camera Setup

### Adding an IP Camera

1. **Get Camera URL**
   - Format: `http://192.168.1.100:8080/video` (HTTP)
   - Format: `rtsp://192.168.1.100:554/stream` (RTSP)
   - Format: `https://192.168.1.100:8443/video` (HTTPS)

2. **In Dashboard:**
   - Click "Add Camera"
   - Select "IP Camera"
   - Paste URL: `https://192.168.100.61:8080/video`
   - Click "Validate"
   - System will test the connection

3. **Select and Stream**
   - Click camera from list
   - Live feed appears in dashboard
   - Ready for AI pipeline processing

---

## Part 5: Using AI Models & Pipelines

### Available Models:
- **YOLOv8 Detection** - Object detection (cars, people, etc.)
- **Parking Management** - Detect empty/occupied spots
- **Person Detection** - Count people, detect individuals
- **Custom Pipelines** - Drag-and-drop model combinations

### Applying Models:

1. **Single Camera Mode:**
   - Select camera from list
   - Drag models to canvas
   - Drop to create pipeline
   - Models process in order: Model1 → Model2 → Display

2. **Split View (Multiple Cameras):**
   - Click "Split View" (4-up or 9-grid)
   - Select different camera for each panel
   - Drag models to each panel
   - Independent processing per camera

3. **Parking Detection:**
   - Click "Parking Mode"
   - Draw parking areas on video
   - Press ESC when done
   - System tracks occupancy

---

## Part 6: Troubleshooting

### Camera Stream Not Showing
**Problem:** "Camera idle" message, no video
**Solution:**
1. Verify camera URL is correct
2. Check camera is accessible from your network
3. Ensure Python server is running (`python Server.py`)
4. Check firewall settings

### Python Server Not Starting
**Error:** `ModuleNotFoundError: No module named 'fastapi'`
**Solution:**
```bash
pip install -r requirements.txt
```

**Error:** CUDA/GPU issues
**Solution:**
- Install NVIDIA CUDA Toolkit
- Install PyTorch with CUDA support:
  ```bash
  pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118
  ```

### Models Not Processing
**Problem:** Models loaded but no output
**Solution:**
1. Check Python server logs for errors
2. Ensure GPU has memory (nvidia-smi to check)
3. Restart Python server
4. Try CPU-only mode (slower):
   ```bash
   # In Server.py, change device to 'cpu'
   ```

### Database Connection Error
**Problem:** "Failed to connect to MongoDB"
**Solution:**
1. Ensure MongoDB URI is set in environment variables
2. Verify MongoDB server is running
3. Check connection string format

---

## Part 7: Running on Cloud (Advanced)

### Option 1: Run Python Backend on Cloud VM
- Deploy Python server to AWS EC2, Google Cloud, or DigitalOcean
- Update environment variables with cloud server URL
- Frontend will connect to remote Python server

### Option 2: Docker Deployment
```bash
docker build -t moduvision-backend .
docker run -p 5000:5000 moduvision-backend
```

### Option 3: Ngrok Tunneling (Development)
```bash
pip install ngrok
ngrok http 5000
```
Use the generated URL in frontend configuration

---

## Part 8: Environment Variables

Create `.env` file in project root:

```
# MongoDB
MONGO_URI=mongodb+srv://username:password@cluster.mongodb.net/moduvision

# Camera Settings
DEFAULT_CAMERA_URL=http://192.168.1.100:8080/video
CAMERA_TIMEOUT=30

# AI Settings
YOLO_CONFIDENCE=0.5
YOLO_DEVICE=gpu  # or 'cpu'

# Server
PYTHON_SERVER_PORT=5000
NODE_SERVER_PORT=3000
```

---

## Part 9: Quick Start Checklist

- [ ] Python 3.8+ installed
- [ ] Virtual environment created and activated
- [ ] Dependencies installed: `pip install -r requirements.txt`
- [ ] MongoDB URI configured (if using database)
- [ ] YOLO models downloaded (~2GB)
- [ ] Python server running: `python Server.py`
- [ ] Frontend deployed at: https://graduation-project-tgra.vercel.app
- [ ] IP camera URL ready and tested
- [ ] Python server accessible from frontend
- [ ] First camera added successfully

---

## Part 10: Support & Documentation

### Key Files:
- `/Code/Public/python/Server.py` - FastAPI backend
- `/Code/Public/scripts/Dashboard.js` - Frontend logic
- `/Code/routes/CameraProxyRoutes.js` - API bridge
- `/Code/index.js` - Express server

### API Endpoints:
- `POST /camera-proxy/set-camera` - Select camera
- `GET /camera-proxy/stream/{camera_id}` - Video stream
- `POST /camera-proxy/set-pipeline` - Apply models
- `POST /camera-proxy/init-parking` - Parking mode
- `POST /camera-proxy/set-alert-email` - Alert settings

---

## Testing the Full System

### Local Testing (Recommended):
1. Start Python server: `python Server.py`
2. Start Node server: `npm start`
3. Visit `http://localhost:3000`
4. Login with test account
5. Add IP camera
6. Apply models

### Production Testing:
1. Start Python server locally
2. Visit https://graduation-project-tgra.vercel.app
3. Login
4. Add camera (must be accessible from internet)
5. Test streaming and models

---

## Next Steps

1. **Get Python server running locally** - This is the critical step
2. **Test with local camera feed or IP camera**
3. **Verify all models process correctly**
4. **Deploy Python server to cloud** (optional)
5. **Configure alert emails and notifications**

---

**Support:** For issues, check logs in:
- Node.js: `npm start` console output
- Python: `python Server.py` console output
- Browser: Developer console (F12)

Good luck! Your ModuVision system is now ready to use.
