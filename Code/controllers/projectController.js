const  Project  = require('../Models/model');
console.log(Project);


async function createProject(req, res) {
  try {
    if (!req.session.user) {
      return res.status(401).json({ success: false, message: 'Unauthorized' });
    }

    const { name, pipeline } = req.body;

    if (!name) {
      return res.status(400).json({ success: false, message: 'Project name is required' });
    }

    const project = new Project({
      name,
      pipeline: pipeline || [],
      owner: req.session.user._id
    });

    await project.save();
    
    res.status(201).json({
      success: true,
      project
    });

  } catch (err) {
    if (err.code === 11000) {
      return res.status(409).json({
        success: false,
        message: "You already have a project with this name"
      });
    }

    console.error(err);
    res.status(500).json({ success: false, message: 'Failed to create project' });
  }
}

/* ================= GET ALL PROJECTS ================= */
async function getUserProjects(req, res) {
  try {
    if (!req.session.user) {
      return res.status(401).json({ success: false, message: 'Unauthorized' });
    }

    const projects = await Project.find({
      owner: req.session.user._id
    }).sort({ createdAt: -1 });

    res.json({
      success: true,
      projects
    });

  } catch (err) {
    console.error(err);
    res.status(500).json({ success: false, message: 'Failed to fetch projects' });
  }
}

/* ================= GET PROJECT BY ID ================= */
async function getProjectById(req, res) {
  try {
    if (!req.session.user) {
      return res.status(401).json({ success: false, message: 'Unauthorized' });
    }

    const { projectId } = req.params;

    const project = await Project.findOne({
      _id: projectId,
      owner: req.session.user._id
    });

    if (!project) {
      return res.status(404).json({ success: false, message: 'Project not found' });
    }

    res.json({
      success: true,
      project
    });

  } catch (err) {
    console.error(err);
    res.status(500).json({ success: false, message: 'Failed to fetch project' });
  }
}

/* ================= DELETE PROJECT ================= */
async function deleteProject(req, res) {
  try {
    if (!req.session.user) {
      return res.status(401).json({ success: false, message: 'Unauthorized' });
    }

    const { projectId } = req.params;

    const deleted = await Project.findOneAndDelete({
      _id: projectId,
      owner: req.session.user._id   // 🔐 FIX
    });

    if (!deleted) {
      return res.status(404).json({ success: false, message: 'Project not found' });
    }

    res.json({ success: true, message: 'Project deleted' });

  } catch (err) {
    console.error(err);
    res.status(500).json({ success: false, message: 'Failed to delete project' });
  }
}


module.exports = {
  createProject,
  getUserProjects,
  getProjectById,
  deleteProject
};
