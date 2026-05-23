```markdown
# 👁️ ModuVision

ModuVision is a web-based security and surveillance platform built with Node.js, Express, EJS, and MongoDB. It combines user authentication, camera management, project configuration, and attendance-class workflows with a collection of Python-based computer vision tools.

## 🚀 Project Overview

The application is designed to support:

* **🔐 Secure Access:** User sign up, login, and session-based access control.
* **📹 Device Control:** Camera management for each authenticated user.
* **⚙️ Custom Pipelines:** Project creation with a modular pipeline of computer vision features.
* **👥 Smart Tracking:** Attendance class creation using image uploads and saved face reference data.
* **🧠 AI Power:** Integration with Python vision scripts located under `Code/Public/python` for advanced detection and recognition.

## ✨ Key Features

* **🔐 Authentication**: Users can register accounts, log in, and receive a session-based dashboard experience.
* **📹 Camera Support**: Add, list, retrieve, and delete camera entries by name and URL.
* **📁 Project Management**: Create and manage user-specific projects with selected vision pipeline stages.
* **👩‍🏫 Attendance Classes**: Upload face images into named classes, view classes, add more images, and delete classes.
* **🐍 Python Vision Integration**: The repository includes a folder of vision scripts for tasks such as weapon detection, fire detection, tracking, and attendance.

## 📂 Repository Structure

* 📄 `Code/index.js` - Main Express server and application entry point.
* 📦 `Code/package.json` - Node.js dependencies.
* 🛣️ `Code/routes/` - Route definitions for main pages and authenticated user actions.
* 🧠 `Code/controllers/` - Controller logic for authentication, projects, cameras, and attendance.
* 📊 `Code/Models/` - Mongoose schemas for users, projects, and attendance classes.
* 🖥️ `Code/Views/` - EJS templates for UI pages.
* 🖼️ `Code/Public/` - Static assets, styles, and Python vision files.
* 🐍 `Code/Public/python/` - Python scripts, models, and attendance image storage.

## 🛠️ Technology Stack

* 🟢 Node.js
* 🚂 Express
* 🎨 EJS templating
* 🍃 MongoDB / Mongoose
* 🍪 express-session
* 📂 Multer file uploads
* 🐍 Python vision scripts and model files

## 🏁 Getting Started

1. Install dependencies from the `Code` folder:

```sh
cd "d:\visual studio code\Graduation-project\Code"
npm install
```

2. Create a `.env` file in `Code` and define your MongoDB connection:

```env
MONGO_URI=mongodb://localhost:27017/moduvision
SESSION_SECRET=your-secret
```

3. Start the application:

```sh
node index.js
```

4. Open the app in a browser:

```sh
http://localhost:3000
```

## Notes

- The Python scripts are stored under `Code/Public/python` and are intended to support detection and attendance workflows.
- Uploaded attendance images are organized under `Code/Public/python/attendance_images`.
