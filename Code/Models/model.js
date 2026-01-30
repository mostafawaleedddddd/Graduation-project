const mongoose = require("mongoose");
const Schema = mongoose.Schema;

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
        "Tracking"
      ],
      default: []
    }
  },
  { timestamps: true }
);
const Project=mongoose.model('Project',projectSchema);
module.exports = { Project, projectSchema };