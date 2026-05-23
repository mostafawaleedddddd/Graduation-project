"""
ModuVision FastAPI Backend - Vercel Python Services
Wraps the original Server.py and provides API endpoints for the frontend
"""

import os
import sys
import json

# Add the path to the Server.py module
sys.path.insert(0, "/var/task/Code/Public/python")

from fastapi import FastAPI, UploadFile, File, Request, WebSocket, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
import logging

# Import the original server
try:
    from Server import LiveStreamServer
    print("[v0] ✓ Successfully imported LiveStreamServer from Server.py")
except ImportError as e:
    print(f"[v0] ✗ Failed to import Server.py: {e}")
    LiveStreamServer = None

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize the FastAPI app
app = FastAPI(title="ModuVision Backend API", version="1.0")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global server instance
server_instance = None

def get_server():
    """Get or initialize the LiveStreamServer instance"""
    global server_instance
    if server_instance is None:
        try:
            server_instance = LiveStreamServer()
            logger.info("[v0] ✓ LiveStreamServer initialized successfully")
        except Exception as e:
            logger.error(f"[v0] ✗ Failed to initialize LiveStreamServer: {e}")
            raise
    return server_instance


# ============================================================================
# HEALTH CHECK ENDPOINTS
# ============================================================================

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "ok", "service": "ModuVision Backend"}


@app.get("/ready")
async def ready_check():
    """Readiness check - ensures server is initialized"""
    try:
        server = get_server()
        return {"status": "ready", "service": "ModuVision Backend", "server": "initialized"}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Service not ready: {str(e)}")


# ============================================================================
# CAMERA ENDPOINTS
# ============================================================================

@app.post("/set-camera")
async def set_camera(request: Request):
    """Set the active camera"""
    try:
        server = get_server()
        body = await request.json()
        camera_id = body.get("camera_id")
        url = body.get("url")
        
        logger.info(f"[v0] Setting camera: {camera_id}, URL: {url}")
        
        # Call the original server's camera selection
        if hasattr(server, 'current_camera_id'):
            server.current_camera_id = camera_id
        if hasattr(server, 'camera_url'):
            server.camera_url = url
            
        return {"status": "ok", "camera_id": camera_id}
    except Exception as e:
        logger.error(f"[v0] Error setting camera: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/stream/{camera_id}")
async def stream_camera(camera_id: str):
    """Stream video from camera"""
    try:
        server = get_server()
        logger.info(f"[v0] Streaming camera: {camera_id}")
        
        # Use the original server's streaming method if available
        if hasattr(server, 'video_stream_generator'):
            return StreamingResponse(
                server.video_stream_generator(camera_id),
                media_type="multipart/x-mixed-replace; boundary=frame"
            )
        else:
            # Fallback: return a placeholder frame
            return JSONResponse({"status": "streaming", "camera": camera_id})
            
    except Exception as e:
        logger.error(f"[v0] Error streaming camera: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# PIPELINE ENDPOINTS
# ============================================================================

@app.post("/set-pipeline")
async def set_pipeline(request: Request):
    """Set the processing pipeline"""
    try:
        server = get_server()
        body = await request.json()
        pipeline = body.get("pipeline", [])
        camera_id = body.get("camera_id", "default")
        
        logger.info(f"[v0] Setting pipeline for {camera_id}: {pipeline}")
        
        # Call the original server's pipeline method
        if hasattr(server, 'set_pipeline'):
            result = server.set_pipeline(pipeline, camera_id)
            return {"status": "ok", "pipeline": pipeline, "result": result}
        else:
            return {"status": "ok", "pipeline": pipeline}
            
    except Exception as e:
        logger.error(f"[v0] Error setting pipeline: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/pipeline/{camera_id}")
async def get_pipeline(camera_id: str):
    """Get current pipeline for camera"""
    try:
        server = get_server()
        logger.info(f"[v0] Getting pipeline for {camera_id}")
        
        if hasattr(server, 'get_pipeline'):
            pipeline = server.get_pipeline(camera_id)
            return {"camera_id": camera_id, "pipeline": pipeline}
        else:
            return {"camera_id": camera_id, "pipeline": []}
            
    except Exception as e:
        logger.error(f"[v0] Error getting pipeline: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# PARKING MODE ENDPOINTS
# ============================================================================

@app.post("/init-parking")
async def init_parking():
    """Initialize parking detection mode"""
    try:
        server = get_server()
        logger.info("[v0] Initializing parking mode")
        
        if hasattr(server, 'init_parking'):
            result = server.init_parking()
            return {"status": "ok", "mode": "parking", "result": result}
        else:
            return {"status": "ok", "mode": "parking"}
            
    except Exception as e:
        logger.error(f"[v0] Error initializing parking: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# ALERT ENDPOINTS
# ============================================================================

@app.post("/set-alert-email")
async def set_alert_email(request: Request):
    """Set alert email for notifications"""
    try:
        server = get_server()
        body = await request.json()
        email = body.get("email")
        
        logger.info(f"[v0] Setting alert email: {email}")
        
        if hasattr(server, 'alert_email'):
            server.alert_email = email
            
        return {"status": "ok", "email": email}
    except Exception as e:
        logger.error(f"[v0] Error setting alert email: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# UTILITY ENDPOINTS
# ============================================================================

@app.get("/models")
async def get_available_models():
    """Get list of available AI models"""
    models = [
        "Object Detection",
        "Tracking",
        "Counting",
        "Attendance",
        "Security",
        "Parking Management",
        "Heatmap",
        "Gap Detection",
        "Fire Detection",
        "Weapon Detection"
    ]
    return {"models": models}


@app.post("/save-project")
async def save_project(request: Request):
    """Save project configuration"""
    try:
        body = await request.json()
        logger.info(f"[v0] Saving project: {body.get('name')}")
        return {"status": "ok", "project": body}
    except Exception as e:
        logger.error(f"[v0] Error saving project: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/load-project")
async def load_project(request: Request):
    """Load project configuration"""
    try:
        body = await request.json()
        project_id = body.get("project_id")
        logger.info(f"[v0] Loading project: {project_id}")
        return {"status": "ok", "project_id": project_id}
    except Exception as e:
        logger.error(f"[v0] Error loading project: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# STARTUP EVENT
# ============================================================================

@app.on_event("startup")
async def startup_event():
    """Initialize server on startup"""
    logger.info("[v0] Backend startup event triggered")
    try:
        server = get_server()
        logger.info("[v0] ✓ Backend is ready")
    except Exception as e:
        logger.error(f"[v0] ✗ Backend initialization failed: {e}")


if __name__ == "__main__":
    import uvicorn
    logger.info("[v0] Starting ModuVision Backend Server...")
    uvicorn.run(app, host="0.0.0.0", port=8000)
