const express = require("express");
const path = require("path");
const app = express();
app.use(express.json());
app.use(express.urlencoded({ extended: true }));
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
app.use("/auth", require("./routes/AuthRoutes"));

// Server
const PORT = 3000;
app.listen(PORT, () => {
  console.log(`ModuVision running on http://localhost:${PORT}`);
});
