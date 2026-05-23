const { spawn } = require('child_process');
const path = require('path');

/**
 * Start the Python FastAPI server for camera streaming and AI models
 * This runs locally on port 8000
 */
function startPythonServer() {
  const pythonPath = process.env.PYTHON_PATH || 'python3';
  const serverPath = path.join(__dirname, 'Public', 'python', 'Server.py');

  console.log('[Services] Starting Python FastAPI server...');
  
  const pythonProcess = spawn(pythonPath, [serverPath], {
    cwd: path.join(__dirname, 'Public', 'python'),
    stdio: 'inherit',
    env: {
      ...process.env,
      PYTHONUNBUFFERED: '1',
    },
  });

  pythonProcess.on('error', (error) => {
    console.error('[Services] Failed to start Python server:', error.message);
  });

  pythonProcess.on('close', (code) => {
    console.log(`[Services] Python server exited with code ${code}`);
  });

  return pythonProcess;
}

module.exports = { startPythonServer };
