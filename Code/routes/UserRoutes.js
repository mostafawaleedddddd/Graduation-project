const express = require("express");
var bodyParser = require('body-parser');
const UserSchema=require('../Models/user');
const projectController = require('../controllers/projectController');
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
router.get('/',(req,res)=>{res.render('Dashboard',{user: (req.session.user === undefined ? "" : req.session.user)})});
router.post('/projectsCreate', projectController.createProject);
router.get('/Getprojects', projectController.getUserProjects);
router.get('/projects/:projectId', projectController.getProjectById);
router.delete('/projects/:projectId', projectController.deleteProject);
module.exports = router;