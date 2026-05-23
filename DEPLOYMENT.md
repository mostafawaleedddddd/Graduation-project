# Deployment Guide - ModuVision to Vercel

## Quick Start Deployment

### Step 1: Prepare Your Repository

```bash
# Ensure all changes are committed
git add .
git commit -m "Prepare for Vercel deployment"
git push origin main
```

### Step 2: Deploy to Vercel

#### Option A: Using Vercel CLI (Recommended)

```bash
# Install Vercel CLI globally (if not already installed)
npm install -g vercel

# Deploy from project root
cd /path/to/Graduation-project
vercel

# Follow the prompts:
# - Link to existing project? Yes (prj_dTPAFEWpWU6QGx2XeBqRss3R4TNL)
# - Confirm project settings? Yes
# - Set environment variables? Yes (see below)
```

#### Option B: Using Vercel Dashboard

1. Go to [https://vercel.com/dashboard](https://vercel.com/dashboard)
2. Find "Graduation-project"
3. Click "Settings"
4. Go to "Environment Variables"
5. Add the variables listed below
6. Go to "Deployments"
7. Click "Deploy"

### Step 3: Configure Environment Variables

In Vercel Project Settings → Environment Variables, add:

| Variable | Value | Note |
|----------|-------|------|
| `MONGO_URI` | `mongodb+srv://user:pass@cluster.mongodb.net/moduvision` | Replace with your MongoDB Atlas connection string |
| `SESSION_SECRET` | `your-secure-random-key-here` | Generate a random secure string |
| `NODE_ENV` | `production` | Fixed value |

**To generate a secure SESSION_SECRET:**
```bash
node -e "console.log(require('crypto').randomBytes(32).toString('hex'))"
```

### Step 4: Verify Deployment

After deployment completes:

1. **Check Deployment Status**
   - Go to Vercel Dashboard
   - View "Recent Deployments"
   - Status should be "Ready"

2. **Test the Application**
   - Click the deployment link
   - Should see ModuVision dashboard
   - Check console for errors (F12 → Console tab)

3. **Test API Endpoints**
   ```bash
   # Replace with your Vercel domain
   curl https://your-project.vercel.app/
   curl https://your-project.vercel.app/user
   ```

## Deployment Architecture

### What Gets Deployed

```
Vercel Deployment
├── Node.js Server (Port 3000)
│   ├── Express API
│   ├── EJS Templates
│   ├── User Authentication
│   └── Database Connections
└── Static Assets
    ├── HTML/CSS/JS
    └── Images/Media
```

### Important Notes

⚠️ **Python Server Limitation:**
- The Python FastAPI server (Port 8000) with AI models is NOT deployed to Vercel
- Reason: Vercel doesn't support long-running Python processes
- **Solution:** Deploy Python separately to:
  - Railway.app
  - Render.com
  - AWS EC2
  - Google Cloud Run
  - Your own server/VPS

## Advanced: Deploying Python Separately

### Option 1: Deploy Python to Railway.app

1. **Create Railway Account**
   - Go to [railway.app](https://railway.app)
   - Sign up with GitHub

2. **Deploy from GitHub**
   - Click "New Project"
   - Select "Deploy from GitHub repo"
   - Choose your Graduation-project repo
   - Configure:
     - Root directory: `Code/Public/python`
     - Start command: `python Server.py`

3. **Set Environment Variables**
   - Add in Railway dashboard:
     - `PORT=8000`
     - Any other required env vars

4. **Get Public URL**
   - Railway provides a public URL (e.g., `https://project-production.up.railway.app`)
   - Update your Node.js server to point to this URL

### Option 2: Deploy Python to Render.com

1. **Create Render Account**
   - Go to [render.com](https://render.com)
   - Connect GitHub account

2. **Create Web Service**
   - New → Web Service
   - Select your repository
   - Configure:
     - Root directory: `Code/Public/python`
     - Runtime: Python 3
     - Build command: `pip install -r requirements.txt`
     - Start command: `python Server.py`
   - Set environment variables
   - Deploy

### Option 3: Use Vercel Functions (Advanced)

Create API routes to handle Python calls:

```javascript
// pages/api/video-stream.js
export default async function handler(req, res) {
  // Forward requests to external Python server
  const pythonServerUrl = process.env.PYTHON_SERVER_URL;
  const response = await fetch(`${pythonServerUrl}/video`);
  // Handle streaming response
}
```

## Monitoring & Logs

### View Deployment Logs

```bash
# Using Vercel CLI
vercel logs --follow

# Or in Vercel Dashboard
# Go to Deployments → Select deployment → View Logs
```

### Common Log Messages

| Log | Meaning | Action |
|-----|---------|--------|
| `ModuVision running on http://localhost:3000` | Server started successfully | ✓ Normal |
| `MongoDB connection warning` | DB connection failed (non-critical) | ℹ️ Add MongoDB URI |
| `Cannot find module` | Missing dependency | Run `npm install` |
| `Port already in use` | Another process on port 3000 | Check other services |

## Troubleshooting Deployment

### Issue: Deployment Failed - Build Error

**Solution:**
1. Check build logs in Vercel Dashboard
2. Verify all dependencies in `package.json`
3. Run locally: `npm install && npm run build`
4. Push fixes and redeploy

### Issue: 404 on Home Page

**Solution:**
1. Check routes in `Code/routes/MainRoutes.js`
2. Verify view files in `Code/Views/`
3. Check that files match route paths

### Issue: Database Connection Fails

**Solution:**
1. Verify `MONGO_URI` in environment variables
2. Check MongoDB Atlas firewall settings
3. Confirm database exists
4. Server runs without DB (see logs)

### Issue: Environment Variables Not Working

**Solution:**
1. Redeploy after adding env vars (new deployment picks them up)
2. Verify variable names match exactly
3. Check Vercel dashboard → Settings → Environment Variables
4. Remove and re-add variables if needed

### Issue: Changes Not Deployed

**Solution:**
```bash
# Force redeploy
vercel --prod

# Or push new commit
git commit --allow-empty -m "Force redeploy"
git push origin main
```

## Rollback to Previous Deployment

In Vercel Dashboard:
1. Go to Deployments
2. Find the previous working deployment
3. Click the three-dot menu
4. Select "Promote to Production"

## Performance Tips

1. **Enable Edge Caching**
   - Set cache headers in middleware
   - Static assets automatically cached

2. **Optimize Database Queries**
   - Use indexes in MongoDB
   - Minimize data transfers

3. **Reduce Dependencies**
   - Remove unused packages
   - Regularly audit with `npm audit`

4. **Monitor Performance**
   - Use Vercel Analytics
   - Check deployment details

## Security in Production

✓ **Enabled:**
- HTTPS by default
- Secure session cookies
- Environment variable protection
- MongoDB authentication

⚠️ **Review:**
- Change `SESSION_SECRET` regularly
- Audit user permissions
- Monitor access logs
- Use VPN for admin access

## Custom Domain Setup

1. **Go to Vercel Project Settings**
2. **Domains** section
3. **Add custom domain**
4. **Follow DNS configuration steps**
5. **Wait 24 hours for DNS propagation**

## Next Steps

1. ✓ Deploy Node.js to Vercel
2. → Deploy Python server to Railway/Render
3. → Update Python server URL in Node.js config
4. → Test end-to-end integration
5. → Monitor logs and performance
6. → Set up analytics and alerts

---

**Need Help?**
- Check [Vercel Documentation](https://vercel.com/docs)
- View deployment logs: `vercel logs --follow`
- Contact Vercel support: vercel.com/help
