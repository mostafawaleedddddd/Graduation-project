const express = require("express");
const router = express.Router();
const controller = require("../controllers/MainController");
const UserSchema=require('../Models/user');
const user = require("../controllers/userController");
router.get("/", controller.home);
router.post('/addUser',user.addUser);
router.post('/login',user.login);
module.exports = router;
