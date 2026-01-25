const express = require("express");
var bodyParser = require('body-parser');
const UserSchema=require('../Models/user');
const router = express.Router();
router.use(bodyParser.json());
const user = require("../controllers/userController");
router.use((req, res, next) => {
    if (req.session.user !== undefined && req.session.user != null && req.session.role === 'User') {
        next();
    }
    else {
        res.render('Error', { message: 'You don\'t have an authority to access this page',user: (req.session.user === undefined ? "" : req.session.user) })
    }
});
router.get('/user/login',(req,res)=>{res.render('Dashboard',{user: (req.session.user === undefined ? "" : req.session.user)})});
module.exports = router;