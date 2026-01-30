const mongoose = require('mongoose');
const schema = mongoose.Schema;
const { projectSchema } = require('../Models/model');
const userSchema = new schema({
    Name: { type: String, match: /([A-ZÀ-ÿ-a-z. ']+[ ]*)+/, required: true },
    EmailAddress: { type: String, match: /^[^\s@]+@[^\s@]+\.[^\s@]+$/ },
    Password: { type: String, match: /^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&])[A-Za-z\d!@#$%^&*()-_=+{};:,<.>]{8,}/, required: true },
    projects: {
        type: [projectSchema],
        default: []
    }
}, { timestamps: true });

const User = mongoose.model('User', userSchema);
module.exports = User;