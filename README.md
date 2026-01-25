# GhostLedger Umbrel App Bundle

This directory contains everything needed to deploy GhostLedger on Umbrel.

## Directory Structure

```
ghostledger-umbrel/
├── umbrel-app-store.yml     # Community App Store manifest
├── ghostledger/             # The app itself
│   ├── umbrel-app.yml       # App manifest for Umbrel
│   ├── docker-compose.yml   # Docker orchestration
│   ├── exports.sh           # Environment exports
│   ├── Dockerfile           # Container build file
│   ├── app.py               # Streamlit application
│   ├── acb_engine.py        # ACB calculation engine
│   ├── parsers.py           # CSV parsers
│   ├── requirements.txt     # Python dependencies
│   └── README.md            # App documentation
└── README.md                # This file
```

## Deployment Options

### Option 1: Publish as Community App Store (Recommended)

1. **Create a GitHub repository** named `ghostledger-umbrel-store` (or similar)

2. **Push this directory structure** to the repo:
   ```bash
   cd ghostledger-umbrel
   git init
   git add .
   git commit -m "Initial GhostLedger Umbrel app"
   git remote add origin https://github.com/YOUR_USERNAME/ghostledger-umbrel-store.git
   git push -u origin main
   ```

3. **Build and push the Docker image** to Docker Hub:
   ```bash
   cd ghostledger
   
   # Login to Docker Hub
   docker login
   
   # Build multi-architecture image
   docker buildx create --use
   docker buildx build --platform linux/arm64,linux/amd64 \
     --tag YOUR_DOCKERHUB/ghostledger:v1.0.0 \
     --push .
   ```

4. **Update docker-compose.yml** with your Docker Hub image:
   ```yaml
   image: YOUR_DOCKERHUB/ghostledger:v1.0.0@sha256:YOUR_DIGEST
   ```

5. **Users install by adding your Community App Store**:
   - Umbrel > App Store > ⚙️ > Community App Stores
   - Add: `https://github.com/YOUR_USERNAME/ghostledger-umbrel-store`

### Option 2: Submit to Official Umbrel App Store

1. Fork `https://github.com/getumbrel/umbrel-apps`

2. Create a new branch:
   ```bash
   git checkout -b add-ghostledger
   ```

3. Copy the `ghostledger/` directory to the root of the umbrel-apps repo

4. Submit a Pull Request to `getumbrel/umbrel-apps`

5. Follow Umbrel's review process

### Option 3: Local Development/Testing

1. **SSH into your Umbrel**:
   ```bash
   ssh umbrel@umbrel.local
   ```

2. **Copy the app directory**:
   ```bash
   cd ~/umbrel/app-data
   mkdir -p ghostledger
   # Copy files via scp or git clone
   ```

3. **Build the Docker image locally on Umbrel**:
   ```bash
   cd ~/umbrel/app-data/ghostledger
   docker build -t ghostledger:local .
   ```

4. **Update docker-compose.yml to use local image**:
   ```yaml
   image: ghostledger:local
   ```

5. **Install the app**:
   ```bash
   ~/umbrel/scripts/app install ghostledger
   ```

## Getting the Docker Image Digest

After pushing your image, get the digest for deterministic builds:

```bash
docker buildx imagetools inspect YOUR_DOCKERHUB/ghostledger:v1.0.0
```

Look for the multi-architecture manifest digest (starts with `sha256:`).

Update your `docker-compose.yml`:
```yaml
image: ghostledger/ghostledger:v1.0.0@sha256:abc123...
```

## Testing Checklist

- [ ] App installs successfully on Umbrel
- [ ] Web UI loads at `http://umbrel.local:8501`
- [ ] File upload works for both price and transaction CSVs
- [ ] ACB calculations produce correct results
- [ ] Schedule 3 export downloads properly
- [ ] App survives Umbrel restart
- [ ] Works on Raspberry Pi 4 (ARM64)
- [ ] Works on x86 hardware (AMD64)

## Updating the App

1. Increment version in `umbrel-app.yml`
2. Add release notes to `releaseNotes` field
3. Build and push new Docker image with new tag
4. Update image tag and digest in `docker-compose.yml`
5. Commit and push changes

## Support

- GitHub Issues: https://github.com/ghostledger/ghostledger/issues
- Umbrel Community: https://community.getumbrel.com

---

Happy self-sovereign tax calculating! 🍁👻
