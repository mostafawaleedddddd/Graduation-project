const mongoose = require("mongoose");
const Schema = mongoose.Schema;

/* ─── PROJECT SCHEMA ─── */
const projectSchema = new Schema(
  {
    name: {
      type: String,
      required: true,
      trim: true
    },

    pipeline: {
      type: [String],
      enum: [
        "Color Detection",
        "Object Detection",
        "Tracking",
        "Object Counting",
        "Gap Detection",
        "Heatmap",
        "Parking Management",
        "Attendance"
      ],
      default: []
    },

    owner: {
      type: Schema.Types.ObjectId,
      ref: "User",
      required: true
    }
  },
  { timestamps: true }
);

/* 🔐 UNIQUE PER USER */
projectSchema.index(
  { name: 1, owner: 1 },
  { unique: true }
);

const Project = mongoose.model("Project", projectSchema);

/* ─── ATTENDANCE CLASS SCHEMA ─── */
const attendanceClassSchema = new Schema(
  {
    name: {
      type: String,
      required: true,
      trim: true
    },

    owner: {
      type: Schema.Types.ObjectId,
      ref: "User",
      required: true
    },

    images: [
      {
        filename: { type: String, required: true },
        originalName: { type: String, required: true },
        mimetype: { type: String, required: true },
        size: { type: Number },
        uploadedAt: { type: Date, default: Date.now }
      }
    ]
  },
  { timestamps: true }
);

/* 🔐 UNIQUE CLASS NAME PER USER */
attendanceClassSchema.index(
  { name: 1, owner: 1 },
  { unique: true }
);

const AttendanceClass = mongoose.model("AttendanceClass", attendanceClassSchema);

module.exports = { Project, AttendanceClass };