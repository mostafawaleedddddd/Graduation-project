const express = require("express");
const router = express.Router();
const controller = require("../controllers/MainController");
const UserSchema=require('../Models/user');
const user = require("../controllers/userController");


router.get("/", controller.home);
router.get("/login", controller.login);
router.get("/signup", controller.signup);
router.get("/auth", controller.login);
router.get('/successful-login', (req, res) => {
  res.render('Successful_login');
});

router.post('/checkUser',user.checkCredentials);
router.post('/addUser',user.addUser);
router.post('/login',user.login);


module.exports = router;
