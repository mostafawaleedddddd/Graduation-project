const express = require("express");
const path = require("path");
const session = require('express-session');
const app = express();
app.use(express.json());
app.use(express.urlencoded({ extended: true }));

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

// Connect to MongoDB with error handling
mongoose.connect(process.env.MONGO_URI)
  .catch(err => {
    console.warn("⚠️  MongoDB connection warning (non-critical):", err.message);
    console.log("ℹ️  Server will run without database, but database features won't work");
  });

// Routes (MATCH CASE EXACTLY)
app.use("/", require("./routes/MainRoutes"));
// app.use("/auth", require("./routes/AuthRoutes"));
app.use("/user", require("./routes/UserRoutes"));

// Server
const PORT = 3000;
app.listen(PORT, () => {
  console.log(`ModuVision running on http://localhost:${PORT}`);
});
