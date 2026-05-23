# ModuVision - AI-Powered Video Analysis Platform

A comprehensive solution for real-time video analysis using advanced computer vision and deep learning models.

## Project Structure

```
ModuVision/
├── Code/                     # Node.js Express Application
│   ├── index.js             # Main server entry point
│   ├── package.json         # Node dependencies
│   ├── .env                 # Environment variables
│   ├── controllers/         # Business logic controllers
│   ├── Models/              # Database schemas
│   ├── routes/              # API routes
│   ├── Views/               # EJS templates
│   └── Public/
│       ├── python/          # Python FastAPI server for ML models
│       │   ├── Server.py    # Main Python server
│       │   ├── requirements.txt
│       │   └── [AI Models]  # YOLOv8, fire detection, weapon detection, etc.
│       ├── scripts/         # Frontend JavaScript
│       └── styles/          # CSS files
├── start.sh                 # Combined startup script
├── vercel.json             # Vercel deployment configuration
└── README.md               # This file
```

## Features

- **Real-time Video Processing** - Multi-stream video analysis
- **AI Models Included:**
  - Human Tracking & Re-identification
  - Object Counting
  - Attendance System
  - Security Monitoring
  - Weapon Detection
  - Fire & Smoke Detection
  - Car Parking Detection
  - Heatmap Generation
  - Shelf Gap Detection
  - Color Detection
- **Dynamic NMN** - Advanced module coordination system
- **WebSocket Support** - Live streaming capabilities
- **Multi-camera Support** - Manage multiple video feeds

## Prerequisites

### Required Software
- **Node.js** (v18+) - JavaScript runtime
- **Python** (v3.8+) - AI/ML runtime
- **npm** or **yarn** - Node package manager
- **MongoDB** (optional) - For data persistence

### System Requirements
- GPU recommended for fast inference (CUDA-capable NVIDIA GPU)
- Minimum 8GB RAM
- 10GB+ disk space for models

## Installation

### 1. Install Node.js Dependencies
```bash
cd Code
npm install
```

### 2. Install Python Dependencies
```bash
cd Code/Public/python
pip install -r requirements.txt
```

### 3. Create Environment File
```bash
# In Code/ directory
cat > .env << EOF
MONGO_URI=mongodb://localhost:27017/moduvision
SESSION_SECRET=your-secret-key-here
NODE_ENV=production
PORT=3000
EOF
```

## Running the Application

### Option 1: Using the Startup Script (Recommended)
```bash
./start.sh
```

This will start both servers:
- **Node.js Server**: http://localhost:3000 (API & Web Interface)
- **Python Server**: http://localhost:8000 (AI Models & Video Processing)

### Option 2: Manual Startup

**Terminal 1 - Start Node.js Server:**
```bash
cd Code
node index.js
```
The server will start on `http://localhost:3000`

**Terminal 2 - Start Python Server:**
```bash
cd Code/Public/python
python Server.py
```
The server will start on `http://localhost:8000`

### Option 3: Using npm script (if configured)
```bash
cd Code
npm start
```

## API Endpoints

### Node.js Server (Port 3000)
- `GET /` - Main dashboard
- `GET /user` - User management
- `POST /user/login` - User authentication
- `GET /user/profile` - User profile

### Python Server (Port 8000)
- `GET /video` - MJPEG video stream
- `GET /ws` - WebSocket connection for real-time processing
- `POST /set_pipeline` - Configure AI pipeline
- `POST /set_camera` - Switch camera source
- `GET /nmn_status` - Get NMN processing status

## Deployment to Vercel

### Prerequisites
1. GitHub repository connected
2. Vercel account setup
3. Environment variables configured

### Deployment Steps

1. **Push to GitHub:**
   ```bash
   git add .
   git commit -m "Ready for deployment"
   git push origin main
   ```

2. **Deploy via Vercel CLI:**
   ```bash
   npm install -g vercel
   vercel
   ```

3. **Or Deploy via Vercel Dashboard:**
   - Go to [https://vercel.com/dashboard](https://vercel.com/dashboard)
   - Click "Add New" → "Project"
   - Select your GitHub repository
   - Configure environment variables in Settings
   - Click "Deploy"

### Environment Variables for Vercel
Set these in Vercel project settings:
- `MONGO_URI` - MongoDB connection string
- `SESSION_SECRET` - Session encryption key
- `NODE_ENV` - Set to "production"

## Configuration

### Video Settings
Edit `Code/Public/python/Server.py` to adjust:
- Frame resolution (default: 640x480)
- FPS (default: 20)
- Frame skip rate for performance

### AI Pipeline
Modify pipeline configuration in the web dashboard or via API:
```json
{
  "pipeline": [
    "Tracking",
    "Object Counting",
    "Security",
    "Attendance"
  ]
}
```

## Troubleshooting

### Node Server Won't Start
```bash
# Check if port 3000 is in use
lsof -i :3000

# Kill process using the port
kill -9 <PID>
```

### Python Server Issues
```bash
# Verify Python installation
python --version

# Reinstall requirements
pip install --upgrade pip
pip install -r requirements.txt
```

### MongoDB Connection Error
- Ensure MongoDB is running: `mongod`
- Check connection string in `.env`
- Server will continue running without MongoDB (non-critical)

### GPU/CUDA Issues
- Install CUDA toolkit matching your GPU
- Run: `pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118`

## Development

### File Editing Guidelines
- Edit Python models in `Code/Public/python/`
- Edit Node controllers in `Code/controllers/`
- Edit views in `Code/Views/`
- Do NOT change core directory structure

### Adding New AI Models
1. Place model files in `Code/Public/python/`
2. Create a class with a `process(frame)` method
3. Register in `Server.py` NMN setup
4. Add to pipeline configuration

## Performance Optimization

1. **Enable GPU Acceleration**
   - Ensure CUDA is properly installed
   - Check: `python -c "import torch; print(torch.cuda.is_available())"`

2. **Adjust Frame Skip Rate**
   - Modify `SKIP_N` in `Server.py` (default: 2)
   - Higher = faster but less accurate

3. **Reduce Resolution**
   - Lower camera resolution for faster processing
   - Change in camera_reader_loop()

## Security Notes

- Change `SESSION_SECRET` in production
- Use HTTPS in production deployment
- Secure MongoDB with authentication
- Use environment variables for sensitive data
- Enable CORS only for trusted origins

## Support & Contribution

For issues, feature requests, or contributions:
1. Check existing documentation
2. Review error logs
3. Test in development environment
4. Create detailed bug reports with logs

## License

This project is property of ModuVision. All rights reserved.

---

**Last Updated:** May 23, 2024
**Status:** Production Ready
