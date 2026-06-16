const express = require("express");
const path = require("path");
const { spawn } = require("child_process");
const session = require('express-session');
const app = express();
app.use(express.json());
app.use(express.urlencoded({ extended: true }));

// Start the Python backend Server.py alongside the Node app.
const pythonExecutable = process.env.PYTHON || 'python';
const pythonScript = path.resolve(__dirname, 'Public', 'python', 'Server.py');
const pythonProcess = spawn(pythonExecutable, [pythonScript], {
  cwd: path.dirname(pythonScript),
  stdio: ['ignore', 'inherit', 'inherit'],
});

pythonProcess.on('error', err => {
  console.error('Failed to start Server.py:', err);
});

pythonProcess.on('exit', (code, signal) => {
  console.log(`Server.py exited with code=${code} signal=${signal}`);
});

const shutdown = () => {
  if (!pythonProcess.killed) {
    pythonProcess.kill();
  }
  process.exit();
};

process.on('SIGINT', shutdown);
process.on('SIGTERM', shutdown);
process.on('exit', shutdown);

app.use(
  session({
    secret: process.env.SESSION_SECRET || "moduvision-secret",
    resave: false,
    saveUninitialized: false,
    cookie: { secure: false } // true only with HTTPS
  })
);
// View engine
app.set("view engine", "ejs");
app.set("views", path.join(__dirname, "views"));

// Static files
app.use(express.static(path.join(__dirname, "public")));
//database connection
const mongoose = require("mongoose");
require('dotenv').config();
mongoose.connect(process.env.MONGO_URI);

// Routes (MATCH CASE EXACTLY)
app.use("/", require("./routes/MainRoutes"));
// app.use("/auth", require("./routes/AuthRoutes"));
app.use("/user", require("./routes/UserRoutes"));

// Server
const PORT = 3000;
app.listen(PORT, () => {
  console.log(`ModuVision running on http://localhost:${PORT}`);
});
