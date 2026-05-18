# Build and Deploy Script for Railway
# Run this before pushing to GitHub

import shutil
import os

# Paths
FRONTEND_DIST = os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'dist', 'build', 'h5')
BACKEND_FRONTEND = os.path.join(os.path.dirname(__file__), 'frontend')

# Remove old frontend folder if exists
if os.path.exists(BACKEND_FRONTEND):
    shutil.rmtree(BACKEND_FRONTEND)

# Copy frontend build to backend
shutil.copytree(FRONTEND_DIST, BACKEND_FRONTEND)

print("Frontend copied to backend/frontend/")
print("Ready to push to GitHub and deploy on Railway!")
