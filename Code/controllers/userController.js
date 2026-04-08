// Importing Database Models of Users
const users = require('../Models/user');
// Importing Modules
const path = require('path');

function login(req, res) {
  const { email, password } = req.body;

  users.findOne({ EmailAddress: email, Password: password })
    .then(user => {
      if (!user) {
        return res.json({
          success: false,
          message: "Wrong email or password"
        });
      }
      console.log(user);
      req.session.user = user;
      req.session.role = 'User';

      res.json({
        success: true
      });
    })
    .catch(err => {
      console.error(err);
      res.status(500).json({
        success: false,
        message: "Server error"
      });
    });
};
async function addUser(req, res) {
  try {
    let Full_name = req.body.fullName;
    let email = req.body.email;
    console.log("REQ BODY:", req.body);
    const query = { EmailAddress: email, Name: Full_name }
    let user = await users.findOne(query);
    if (user) {
      res.status(400).json({ success: false, message: "User already exists" });
    }
    else {
      let password = req.body.password;
      let email = req.body.email;
      let user = new users({
        Name: Full_name,
        EmailAddress: email,
        Password: password
      });
      await user.save()
        .then(() => {
          res.json({ success: true, message: "Account created successfully" });
        })
    }
  }
  catch (error) {
    console.error(error);  // Log the error for debugging
    res.status(500).json({ success: false, message: "Internal server error" });
  }
}
async function checkCredentials(req, res) {
  var query = { EmailAddress: req.body.email, Password: req.body.password };
  var found = false;
  await users.find(query)
    .then(result => {
      if (result.length > 0) {
        found = true;
      }
    })
    .catch(err => {
      console.log(err);
    });
  if (found) {
    res.json({ success: true, message: "Account Already Exists" });
  } else {
    res.json({ success: false, message: "Account does not exist" });
  }
}
async function addCamera(req, res) {
  try {
    console.log("REQ BODY:", req.body);
    console.log("TYPE OF NAME:", typeof req.body.name);
    const { name, url } = req.body;
    
    if (!name || !url) {
      return res.json({ success: false, message: "Name and URL required" });
    }

    const userId = req.session.user._id;

    const user = await users.findById(userId);

    if (!user) {
      return res.json({ success: false, message: "User not found" });
    }

    // 🔥 add/update camera
    user.cameras.set(name, url);

    await user.save();

    res.json({ success: true, message: "Camera added successfully" });

  } catch (err) {
    console.error(err);
    res.status(500).json({ success: false, message: "Server error" });
  }
}
async function getCameras(req, res) {
  try {
    const userId = req.session.user._id;

    const user = await users.findById(userId);

    if (!user) {
      return res.json({ success: false, message: "User not found" });
    }

    res.json({
      success: true,
      cameras: user.cameras
    });

  } catch (err) {
    console.error(err);
    res.status(500).json({ success: false, message: "Server error" });
  }
}
async function getCameraByName(req, res) {
  try {
    const { name } = req.params;

    const userId = req.session.user._id;

    const user = await users.findById(userId);

    if (!user) {
      return res.json({ success: false, message: "User not found" });
    }

    const cameraUrl = user.cameras.get(name);

    if (!cameraUrl) {
      return res.json({ success: false, message: "Camera not found" });
    }

    res.json({
      success: true,
      name,
      url: cameraUrl
    });

  } catch (err) {
    console.error(err);
    res.status(500).json({ success: false, message: "Server error" });
  }
}
module.exports = {
  login,
  checkCredentials,
  addUser,
  addCamera,
  getCameras,
  getCameraByName
};