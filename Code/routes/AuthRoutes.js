const express = require("express");
const router = express.Router();
const controller = require("../controllers/AuthController");

router.get("/", controller.authentication);

module.exports = router;
