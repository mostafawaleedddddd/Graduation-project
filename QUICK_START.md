# Quick Start Guide - ModuVision

## 🚀 Get Running in 2 Minutes

### Prerequisites Installed?
- ✓ Node.js (v18+)
- ✓ Python (v3.8+)
- ✓ npm/yarn
- (Optional) MongoDB for data persistence

---

## 📱 Local Development

### Option 1: Automatic (Recommended)
```bash
# From project root, run:
./start.sh
```

This starts everything:
- Node.js Server → `http://localhost:3000`
- Python Server → `http://localhost:8000`

---

### Option 2: Manual Startup

**Terminal 1:**
```bash
cd Code
npm install  # First time only
node index.js
```
✓ Shows: `ModuVision running on http://localhost:3000`

**Terminal 2:**
```bash
cd Code/Public/python
# First time:
# pip install -r requirements.txt

python Server.py
```
✓ Shows: `Application startup complete` (if FastAPI is running)

---

## 🌐 Your Application

### Access Points
| Service | URL | Purpose |
|---------|-----|---------|
| Dashboard | `http://localhost:3000` | Web interface & API |
| Video Stream | `http://localhost:8000/video` | Live MJPEG feed |
| WebSocket | `ws://localhost:8000/ws` | Real-time streaming |
| API Status | `http://localhost:8000/nmn_status` | Pipeline diagnostics |

---

## 🌍 Deploy to Vercel (Production)

### 1. One-Command Deploy
```bash
npm install -g vercel
vercel --prod
```

### 2. Or Manual Deploy
```bash
git add .
git commit -m "Ready to deploy"
git push origin main
```
Then go to [Vercel Dashboard](https://vercel.com/dashboard) and click Deploy

### 3. Set Environment Variables in Vercel
```
MONGO_URI = your-mongodb-connection-string
SESSION_SECRET = your-secure-random-key
NODE_ENV = production
```

✓ Deployed! Get your URL from Vercel dashboard

---

## ⚠️ Important Notes

### Python Server Limitation
- Vercel does NOT support long-running Python processes
- **Solution:** Deploy Python separately to Railway.app or Render.com
- See `DEPLOYMENT.md` for detailed Python deployment guide

### Database Setup
- MongoDB required for full features
- Works without DB (non-critical)
- Use MongoDB Atlas free tier: `mongodb.com/cloud/atlas`

### Structure Preserved ✓
```
Code/
├── index.js              ← Node server entry
├── controllers/          ← Business logic
├── routes/               ← API routes
├── Views/                ← HTML templates
└── Public/
    └── python/
        └── Server.py     ← Python AI server
```
**No core files were changed - structure intact!**

---

## 🔧 Troubleshooting

### "Port 3000 already in use"
```bash
# Kill existing process
lsof -i :3000
kill -9 <PID>

# Or use different port
PORT=3001 node index.js
```

### "Python: ModuleNotFoundError"
```bash
# Install required packages
cd Code/Public/python
pip install -r requirements.txt
```

### "MongoDB connection error"
- This is OK - server runs without database
- To use DB: install MongoDB or MongoDB Atlas
- Update `MONGO_URI` in `.env`

### Still having issues?
1. Check README.md for detailed setup
2. Review error messages in terminal
3. See DEPLOYMENT.md for advanced solutions

---

## 📚 Next Steps

1. **Develop locally** → `./start.sh` → Make changes
2. **Test features** → Visit `http://localhost:3000`
3. **Configure AI pipeline** → Web dashboard
4. **Deploy** → `vercel --prod` → Share your URL

---

## 📖 Documentation

| File | Purpose |
|------|---------|
| `README.md` | Full documentation & API reference |
| `DEPLOYMENT.md` | Vercel & Python server deployment |
| `QUICK_START.md` | This file (quick reference) |

---

## 💡 Pro Tips

### Development
```bash
# Auto-restart on file changes
npm install -g nodemon
nodemon Code/index.js
```

### Testing
```bash
# Test Node.js endpoint
curl http://localhost:3000/

# Test Python endpoint
curl http://localhost:8000/video
```

### Performance
- Lower resolution for faster processing
- Increase FPS in `Server.py` for responsiveness
- Use GPU if available (CUDA)

---

## ✅ Checklist

- [ ] Dependencies installed (`npm install`)
- [ ] `.env` file created with `MONGO_URI`
- [ ] Node server starts without errors
- [ ] Can access `http://localhost:3000`
- [ ] (Optional) Python server running on port 8000
- [ ] Ready to deploy to Vercel

---

**Time to productivity: ~2 minutes ⚡**

Start with: `./start.sh`

Questions? See full documentation in README.md and DEPLOYMENT.md
