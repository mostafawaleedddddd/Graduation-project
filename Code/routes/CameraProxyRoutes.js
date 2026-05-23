const express = require("express");
const router = express.Router();
const axios = require("axios");

// Python server base URL (runs locally on port 8000)
const PYTHON_SERVER = process.env.PYTHON_SERVER_URL || "http://localhost:8000";

/**
 * GET /camera-proxy/stream/:cameraId
 * Streams video from the Python server to the client
 */
router.get("/stream/:cameraId", async (req, res) => {
  try {
    const { cameraId } = req.params;
    const url = `${PYTHON_SERVER}/stream/${cameraId}`;

    console.log(`[Camera Proxy] Streaming from: ${url}`);

    const response = await axios.get(url, {
      responseType: "stream",
      timeout: 30000,
    });

    // Set proper MJPEG headers
    res.setHeader("Content-Type", response.headers["content-type"]);
    res.setHeader("Cache-Control", "no-cache");
    res.setHeader("Connection", "keep-alive");

    response.data.pipe(res);

    response.data.on("error", (err) => {
      console.error(`[Camera Proxy] Stream error: ${err.message}`);
      res.status(500).json({ error: "Stream error" });
    });

    req.on("close", () => {
      response.data.destroy();
    });
  } catch (error) {
    console.error(`[Camera Proxy] Error: ${error.message}`);
    res.status(500).json({ error: error.message });
  }
});

/**
 * POST /camera-proxy/set-camera
 * Set the active camera source for the Python server
 */
router.post("/set-camera", async (req, res) => {
  try {
    const { source } = req.body;

    if (!source) {
      return res.status(400).json({ error: "Camera source is required" });
    }

    const response = await axios.post(`${PYTHON_SERVER}/set_camera`, { source });

    res.json(response.data);
  } catch (error) {
    console.error(`[Camera Proxy] Set camera error: ${error.message}`);
    res.status(500).json({ error: error.message });
  }
});

/**
 * POST /camera-proxy/set-pipeline
 * Set the AI pipeline (Tracking, Attendance, Security, etc.)
 */
router.post("/set-pipeline", async (req, res) => {
  try {
    const { pipeline } = req.body;

    if (!pipeline || !Array.isArray(pipeline)) {
      return res.status(400).json({ error: "Pipeline array is required" });
    }

    const response = await axios.post(`${PYTHON_SERVER}/set_pipeline`, { 
      pipeline,
      camera_id: req.body.camera_id || "default"
    });

    res.json(response.data);
  } catch (error) {
    console.error(`[Camera Proxy] Set pipeline error: ${error.message}`);
    res.status(500).json({ error: error.message });
  }
});

/**
 * GET /camera-proxy/status
 * Get the status of the Python server
 */
router.get("/status", async (req, res) => {
  try {
    const response = await axios.get(`${PYTHON_SERVER}/status`);
    res.json(response.data);
  } catch (error) {
    console.log(`[Camera Proxy] Python server not responding: ${error.message}`);
    res.status(503).json({ 
      error: "Python server not available",
      message: "Make sure Server.py is running on port 8000"
    });
  }
});

/**
 * WebSocket proxy for real-time camera streaming
 */
router.get("/ws/:cameraId", (req, res) => {
  res.status(400).json({ 
    error: "WebSocket not supported via HTTP GET. Use WebSocket connection directly to Python server." 
  });
});

module.exports = router;
