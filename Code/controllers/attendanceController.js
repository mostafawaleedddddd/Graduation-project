const path = require('path');
const fs   = require('fs');
const multer = require('multer');
const { AttendanceClass } = require('../Models/model');

/* ═══════════════════════════════════════════════════════════
   SAVE PATH
   Images are stored inside the Python model's lookup folder,
   organised as:  attendance_images/<className>/<file>
   The Python face-recognition model scans this directory
   when searching for a match during live attendance.
════════════════════════════════════════════════════════════ */
const ATTENDANCE_ROOT = path.resolve(
  '../Code/Public/python/attendance_images'
);

/* ─── MULTER STORAGE ─── */
// Files land in a _tmp folder first; we move them to <className>/ inside the handler
// because for NEW classes the class name isn't known until the handler runs.
function sanitizeFileName(name) {
  return name
    .replace(/[<>:"/\\|?*\x00-\x1F]/g, '_')
    .replace(/\s+/g, ' ')
    .trim();
}

function getUniqueFilename(dir, name) {
  let candidate = name;
  const ext = path.extname(name);
  const base = path.basename(name, ext);
  let count = 1;

  while (fs.existsSync(path.join(dir, candidate))) {
    candidate = `${base}-${count}${ext}`;
    count += 1;
  }

  return candidate;
}

const storage = multer.diskStorage({
  destination: (req, file, cb) => {
    const tmp = path.join(ATTENDANCE_ROOT, '_tmp');
    fs.mkdirSync(tmp, { recursive: true });
    cb(null, tmp);
  },
  filename: (req, file, cb) => {
    const original = sanitizeFileName(path.basename(file.originalname || 'image'));
    const name = getUniqueFilename(path.join(ATTENDANCE_ROOT, '_tmp'), original);
    cb(null, name);
  }
});

const fileFilter = (req, file, cb) => {
  const allowed = /jpeg|jpg|png|gif|webp/;
  const ext  = allowed.test(path.extname(file.originalname).toLowerCase());
  const mime = allowed.test(file.mimetype);
  if (ext && mime) cb(null, true);
  else cb(new Error('Only image files are allowed'));
};

const upload = multer({
  storage,
  fileFilter,
  limits: { fileSize: 10 * 1024 * 1024 } // 10 MB per image
});

/* ─── Helper: sanitize folder names (strip invalid Windows path chars) ─── */
function sanitizeDirName(name) {
  return name.replace(/[<>:"/\\|?*\x00-\x1F]/g, '_').trim();
}

/* ─── Helper: move temp-uploaded files → attendance_images/<className>/ ─── */
function moveFilesToClassDir(files, className) {
  const classDir = path.join(ATTENDANCE_ROOT, sanitizeDirName(className));
  fs.mkdirSync(classDir, { recursive: true });

  return files.map(f => {
    const dest = path.join(classDir, f.filename);
    fs.renameSync(f.path, dest);
    return {
      filename:     f.filename,
      originalName: f.originalname,
      mimetype:     f.mimetype,
      size:         f.size,
      fullPath:     dest
    };
  });
}

/* ═══════════════════════════════════════════════════════════
   CREATE CLASS
   POST /user/attendance/classes
   Body (multipart): name, images[]
   Result on disk: attendance_images/<name>/<img1>, <img2>, ...
════════════════════════════════════════════════════════════ */
async function createClass(req, res) {
  try {
    if (!req.session.user) {
      (req.files || []).forEach(f => fs.unlink(f.path, () => {}));
      return res.status(401).json({ success: false, message: 'Unauthorized' });
    }

    const { name } = req.body;
    if (!name || !name.trim()) {
      (req.files || []).forEach(f => fs.unlink(f.path, () => {}));
      return res.status(400).json({ success: false, message: 'Class name is required' });
    }

    const trimmedName = name.trim();
    const images = moveFilesToClassDir(req.files || [], trimmedName);

    const attendanceClass = new AttendanceClass({
      name:  trimmedName,
      owner: req.session.user._id,
      images
    });

    await attendanceClass.save();
    res.status(201).json({ success: true, attendanceClass });

  } catch (err) {
    (req.files || []).forEach(f => fs.unlink(f.path, () => {}));

    if (err.code === 11000) {
      return res.status(409).json({
        success: false,
        message: 'You already have a class with this name'
      });
    }
    console.error(err);
    res.status(500).json({ success: false, message: 'Failed to create class' });
  }
}

/* ═══════════════════════════════════════════════════════════
   GET ALL CLASSES  (for the dropdown)
   GET /user/attendance/classes
════════════════════════════════════════════════════════════ */
async function getClasses(req, res) {
  try {
    if (!req.session.user) {
      return res.status(401).json({ success: false, message: 'Unauthorized' });
    }

    const classes = await AttendanceClass
      .find({ owner: req.session.user._id })
      .select('name images createdAt')
      .sort({ createdAt: -1 });

    res.json({ success: true, classes });

  } catch (err) {
    console.error(err);
    res.status(500).json({ success: false, message: 'Failed to fetch classes' });
  }
}

/* ═══════════════════════════════════════════════════════════
   GET SINGLE CLASS
   GET /user/attendance/classes/:classId
════════════════════════════════════════════════════════════ */
async function getClassById(req, res) {
  try {
    if (!req.session.user) {
      return res.status(401).json({ success: false, message: 'Unauthorized' });
    }

    const attendanceClass = await AttendanceClass.findOne({
      _id:   req.params.classId,
      owner: req.session.user._id
    });

    if (!attendanceClass) {
      return res.status(404).json({ success: false, message: 'Class not found' });
    }

    res.json({ success: true, attendanceClass });

  } catch (err) {
    console.error(err);
    res.status(500).json({ success: false, message: 'Failed to fetch class' });
  }
}

/* ═══════════════════════════════════════════════════════════
   ADD MORE IMAGES TO EXISTING CLASS
   POST /user/attendance/classes/:classId/images
   Body (multipart): images[]
════════════════════════════════════════════════════════════ */
async function addImagesToClass(req, res) {
  try {
    if (!req.session.user) {
      (req.files || []).forEach(f => fs.unlink(f.path, () => {}));
      return res.status(401).json({ success: false, message: 'Unauthorized' });
    }

    const attendanceClass = await AttendanceClass.findOne({
      _id:   req.params.classId,
      owner: req.session.user._id
    });

    if (!attendanceClass) {
      (req.files || []).forEach(f => fs.unlink(f.path, () => {}));
      return res.status(404).json({ success: false, message: 'Class not found' });
    }

    const newImages = moveFilesToClassDir(req.files || [], attendanceClass.name);
    attendanceClass.images.push(...newImages);
    await attendanceClass.save();

    res.json({ success: true, attendanceClass });

  } catch (err) {
    (req.files || []).forEach(f => fs.unlink(f.path, () => {}));
    console.error(err);
    res.status(500).json({ success: false, message: 'Failed to add images' });
  }
}

/* ═══════════════════════════════════════════════════════════
   DELETE CLASS
   DELETE /user/attendance/classes/:classId
   Removes the DB record AND the entire class folder from disk
════════════════════════════════════════════════════════════ */
async function deleteClass(req, res) {
  try {
    if (!req.session.user) {
      return res.status(401).json({ success: false, message: 'Unauthorized' });
    }

    const deleted = await AttendanceClass.findOneAndDelete({
      _id:   req.params.classId,
      owner: req.session.user._id
    });

    if (!deleted) {
      return res.status(404).json({ success: false, message: 'Class not found' });
    }

    // Remove the entire class folder so Python stops recognising those faces
    const classDir = path.join(ATTENDANCE_ROOT, sanitizeDirName(deleted.name));
    if (fs.existsSync(classDir)) {
      fs.rmSync(classDir, { recursive: true, force: true });
    }

    res.json({ success: true, message: 'Class deleted' });

  } catch (err) {
    console.error(err);
    res.status(500).json({ success: false, message: 'Failed to delete class' });
  }
}

module.exports = {
  upload,
  createClass,
  getClasses,
  getClassById,
  addImagesToClass,
  deleteClass,
  sanitizeFileName
};