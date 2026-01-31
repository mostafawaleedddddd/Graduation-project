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
    },

    owner: {
      type: Schema.Types.ObjectId,
      ref: "User",
      required: true
    }
  },
  { timestamps: true }
);

/* 🔐 USER-SCOPED UNIQUENESS */
projectSchema.index(
  { name: 1, owner: 1 },
  { unique: true }
);

const Project = mongoose.model("Project", projectSchema);
module.exports = { Project, projectSchema };
