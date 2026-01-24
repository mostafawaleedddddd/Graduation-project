const express = require("express");
const path = require("path");

const app = express();

// View engine
app.set("view engine", "ejs");
app.set("views", path.join(__dirname, "views"));

// Static files
app.use(express.static(path.join(__dirname, "public")));

// Routes (MATCH CASE EXACTLY)
app.use("/", require("./routes/MainRoutes"));
app.use("/auth", require("./routes/AuthRoutes"));

// Server
const PORT = 3000;
app.listen(PORT, () => {
  console.log(`ModuVision running on http://localhost:${PORT}`);
});
