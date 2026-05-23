"""
ModuVision FastAPI Backend - Vercel Python Services
Lightweight camera streaming and configuration service
"""

import os
import logging
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global state for camera configurations
camera_store = {
    "cameras": {},
    "current_camera": None,
    "pipelines": {},
    "alert_emails": {}
}

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown logic"""
    logger.info("ModuVision Backend starting...")
    yield
    logger.info("ModuVision Backend shutting down...")

# Initialize the FastAPI app
app = FastAPI(
    title="ModuVision Backend",
    description="Lightweight camera streaming and AI pipeline service",
    version="1.0",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================================
# HEALTH & STATUS ENDPOINTS
# ============================================================================

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "moduvision-backend",
        "version": "1.0"
    }

@app.get("/ready")
async def ready_check():
    """Readiness check"""
    return {
        "status": "ready",
        "cameras": len(camera_store["cameras"]),
        "current": camera_store["current_camera"]
    }

# ============================================================================
# CAMERA ENDPOINTS
# ============================================================================

@app.post("/set-camera")
async def set_camera(request_body: dict = None):
    """Set the active camera"""
    try:
        # Handle both form data and JSON
        if isinstance(request_body, dict):
            camera_id = request_body.get("camera_id")
            url = request_body.get("url")
        else:
            camera_id = request_body.camera_id if hasattr(request_body, 'camera_id') else None
            url = request_body.url if hasattr(request_body, 'url') else None
        
        if not camera_id:
            raise ValueError("camera_id is required")
        
        logger.info(f"Setting camera: {camera_id} -> {url}")
        
        # Store camera configuration
        camera_store["cameras"][camera_id] = {"url": url, "status": "connected"}
        camera_store["current_camera"] = camera_id
        
        return {
            "status": "ok",
            "message": f"Camera {camera_id} configured",
            "camera_id": camera_id,
            "url": url
        }
    except Exception as e:
        logger.error(f"Error setting camera: {str(e)}")
        return JSONResponse(
            {"status": "error", "message": str(e)},
            status_code=400
        )

@app.get("/cameras")
async def get_cameras():
    """Get list of cameras"""
    return {
        "status": "ok",
        "cameras": camera_store["cameras"],
        "current": camera_store["current_camera"]
    }

@app.get("/stream/{camera_id}")
async def stream_camera(camera_id: str):
    """Stream video from camera"""
    try:
        camera = camera_store["cameras"].get(camera_id)
        if not camera or not camera.get("url"):
            return JSONResponse(
                {"status": "error", "message": f"Camera {camera_id} not found or not configured"},
                status_code=404
            )
        
        url = camera["url"]
        logger.info(f"Streaming from {camera_id}: {url}")
        
        async def stream_generator():
            """Generate streaming frames from camera URL"""
            try:
                import urllib.request
                import urllib.error
                
                # Handle both mjpeg streams and regular image URLs
                if "mjpeg" in url.lower() or "/video" in url.lower():
                    # MJPEG stream
                    try:
                        response = urllib.request.urlopen(url, timeout=10)
                        while True:
                            chunk = response.read(4096)
                            if not chunk:
                                break
                            yield chunk
                    except urllib.error.URLError as e:
                        logger.error(f"Stream error: {e}")
                        # Return error frame
                        yield b"--frame\r\nContent-Type: text/plain\r\n\r\nStream unavailable\r\n"
                else:
                    # Static image URL - return as loop
                    import time
                    while True:
                        try:
                            response = urllib.request.urlopen(url, timeout=10)
                            image_data = response.read()
                            yield (
                                b"--frame\r\n"
                                b"Content-Type: image/jpeg\r\n"
                                b"Content-Length: " + str(len(image_data)).encode() + b"\r\n\r\n" +
                                image_data + b"\r\n"
                            )
                            time.sleep(1)  # 1 second between frames
                        except Exception as e:
                            logger.error(f"Error fetching frame: {e}")
                            time.sleep(5)
                            continue
            except Exception as e:
                logger.error(f"Stream generator error: {str(e)}")
                yield b"--frame\r\nContent-Type: text/plain\r\n\r\nStream error\r\n"
        
        return StreamingResponse(
            stream_generator(),
            media_type="multipart/x-mixed-replace; boundary=frame"
        )
    except Exception as e:
        logger.error(f"Error streaming camera: {str(e)}")
        return JSONResponse(
            {"status": "error", "message": str(e)},
            status_code=500
        )

# ============================================================================
# PIPELINE ENDPOINTS
# ============================================================================

@app.post("/set-pipeline")
async def set_pipeline(request_body: dict = None):
    """Set the AI pipeline for processing"""
    try:
        if isinstance(request_body, dict):
            pipeline = request_body.get("pipeline", [])
            camera_id = request_body.get("camera_id", "default")
        else:
            pipeline = request_body.pipeline if hasattr(request_body, 'pipeline') else []
            camera_id = request_body.camera_id if hasattr(request_body, 'camera_id') else "default"
        
        logger.info(f"Setting pipeline for {camera_id}: {pipeline}")
        
        camera_store["pipelines"][camera_id] = pipeline
        
        return {
            "status": "ok",
            "message": "Pipeline updated",
            "camera_id": camera_id,
            "pipeline": pipeline
        }
    except Exception as e:
        logger.error(f"Error setting pipeline: {str(e)}")
        return JSONResponse(
            {"status": "error", "message": str(e)},
            status_code=400
        )

@app.get("/pipeline/{camera_id}")
async def get_pipeline(camera_id: str):
    """Get current pipeline for camera"""
    try:
        pipeline = camera_store["pipelines"].get(camera_id, [])
        logger.info(f"Getting pipeline for {camera_id}")
        
        return {
            "status": "ok",
            "camera_id": camera_id,
            "pipeline": pipeline
        }
    except Exception as e:
        logger.error(f"Error getting pipeline: {str(e)}")
        return JSONResponse(
            {"status": "error", "message": str(e)},
            status_code=500
        )

# ============================================================================
# PARKING MODE ENDPOINTS
# ============================================================================

@app.post("/init-parking")
async def init_parking():
    """Initialize parking detection mode"""
    try:
        logger.info("Initializing parking mode")
        
        # Store parking mode state
        camera_id = camera_store["current_camera"] or "default"
        camera_store["pipelines"][camera_id] = ["Parking Management"]
        
        return {
            "status": "ok",
            "mode": "parking",
            "message": "Parking mode initialized"
        }
    except Exception as e:
        logger.error(f"Error initializing parking: {str(e)}")
        return JSONResponse(
            {"status": "error", "message": str(e)},
            status_code=500
        )

# ============================================================================
# ALERT ENDPOINTS
# ============================================================================

@app.post("/set-alert-email")
async def set_alert_email(request_body: dict = None):
    """Set alert email for notifications"""
    try:
        if isinstance(request_body, dict):
            email = request_body.get("email")
        else:
            email = request_body.email if hasattr(request_body, 'email') else None
        
        camera_id = camera_store["current_camera"] or "default"
        
        logger.info(f"Setting alert email for {camera_id}: {email}")
        camera_store["alert_emails"][camera_id] = email
        
        return {
            "status": "ok",
            "message": f"Alert email set to {email}",
            "email": email
        }
    except Exception as e:
        logger.error(f"Error setting alert email: {str(e)}")
        return JSONResponse(
            {"status": "error", "message": str(e)},
            status_code=400
        )

# ============================================================================
# MODEL ENDPOINTS
# ============================================================================

@app.get("/models")
async def get_models():
    """Get list of available AI models"""
    models = [
        {"name": "YOLOv8n", "type": "detection", "size": "nano"},
        {"name": "YOLOv8s", "type": "detection", "size": "small"},
        {"name": "YOLOv8m", "type": "detection", "size": "medium"},
        {"name": "People Detection", "type": "classification", "description": "Detect people in video"},
        {"name": "Vehicle Detection", "type": "classification", "description": "Detect vehicles"},
        {"name": "Parking Management", "type": "segmentation", "description": "Detect parking spaces"},
        {"name": "Custom Models", "type": "custom", "description": "Upload your own model"}
    ]
    
    return {
        "status": "ok",
        "models": models,
        "count": len(models)
    }

# ============================================================================
# PROJECT ENDPOINTS
# ============================================================================

@app.post("/save-project")
async def save_project(request_body: dict = None):
    """Save project configuration"""
    try:
        if isinstance(request_body, dict):
            project_data = request_body
        else:
            project_data = request_body.__dict__ if hasattr(request_body, '__dict__') else {}
        
        project_id = project_data.get("id")
        logger.info(f"Saving project: {project_id}")
        
        return {
            "status": "ok",
            "message": f"Project {project_id} saved",
            "project": project_data
        }
    except Exception as e:
        logger.error(f"Error saving project: {str(e)}")
        return JSONResponse(
            {"status": "error", "message": str(e)},
            status_code=400
        )

@app.post("/load-project")
async def load_project(request_body: dict = None):
    """Load project configuration"""
    try:
        if isinstance(request_body, dict):
            project_id = request_body.get("project_id")
        else:
            project_id = request_body.project_id if hasattr(request_body, 'project_id') else None
        
        logger.info(f"Loading project: {project_id}")
        
        return {
            "status": "ok",
            "message": f"Project {project_id} loaded",
            "project_id": project_id,
            "cameras": camera_store["cameras"],
            "pipelines": camera_store["pipelines"]
        }
    except Exception as e:
        logger.error(f"Error loading project: {str(e)}")
        return JSONResponse(
            {"status": "error", "message": str(e)},
            status_code=400
        )

# ============================================================================
# STARTUP
# ============================================================================

@app.on_event("startup")
async def startup_event():
    """Initialize on startup"""
    logger.info("ModuVision Backend initialized and ready")

if __name__ == "__main__":
    import uvicorn
    logger.info("Starting ModuVision Backend...")
    uvicorn.run(app, host="0.0.0.0", port=8000)
