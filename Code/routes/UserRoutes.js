const express = require("express");
var bodyParser = require('body-parser');
const UserSchema = require('../Models/user');
const projectController = require('../controllers/projectController');
const attendanceController = require('../controllers/attendanceController');
const router = express.Router();
router.use(bodyParser.json());
const user = require("../controllers/userController");

router.use((req, res, next) => {
    if (req.session.user !== undefined && req.session.user != null && req.session.role === 'User') {
        next();
    }
    else {
        res.render('Error', { message: 'You don\'t have an authority to access this page', user: (req.session.user === undefined ? "" : req.session.user) });
    }
});

router.get('/', (req, res) => {
    res.render('Dashboard', { user: (req.session.user === undefined ? "" : req.session.user) });
});

/* ─── PROJECT ROUTES ─── */
router.post('/projectsCreate', projectController.createProject);
router.get('/Getprojects', projectController.getUserProjects);
router.get('/projects/:projectId', projectController.getProjectById);
router.delete('/projects/:projectId', projectController.deleteProject);

/* ─── CAMERA ROUTES ─── */
router.post('/addCamera', user.addCamera);
router.get('/getCameras', user.getCameras);
router.get('/getCamera/:name', user.getCameraByName);
router.post('/deleteCamera', user.deleteCamera);
router.delete('/camera/:name', user.deleteCamera);

/* ─── ATTENDANCE CLASS ROUTES ─── */
router.post(
    '/attendance/classes',
    attendanceController.upload.array('images', 50),
    attendanceController.createClass
);
router.get('/attendance/classes', attendanceController.getClasses);
router.get('/attendance/classes/:classId', attendanceController.getClassById);
router.post(
    '/attendance/classes/:classId/images',
    attendanceController.upload.array('images', 50),
    attendanceController.addImagesToClass
);
router.delete('/attendance/classes/:classId', attendanceController.deleteClass);

/* ─── LOGOUT ─── */
router.post('/logout', (req, res) => {
    req.session.destroy(err => {
        if (err) {
            console.error(err);
            return res.status(500).json({ success: false });
        }
        res.clearCookie('connect.sid');
        res.json({ success: true });
    });
});

module.exports = router;