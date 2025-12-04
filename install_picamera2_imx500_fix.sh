#!/bin/bash
set -e  # Exit on error

echo "=========================================="
echo "Picamera2 IMX500 Automated Fix Script"
echo "=========================================="
echo ""
echo "This script will:"
echo "  1. Remove broken Picamera2 0.3.32"
echo "  2. Install dependencies (excluding broken OpenEXR)"
echo "  3. Clone and build known-good Picamera2 version"
echo "  4. Patch for Python 3.13 compatibility"
echo "  5. Test IMX500 initialization"
echo "  6. Launch your backend"
echo ""
read -p "Press Enter to continue or Ctrl+C to cancel..."

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Step 1: Remove broken Picamera2 0.3.32
echo ""
echo -e "${YELLOW}[1/7] Removing Picamera2 0.3.32...${NC}"
sudo apt remove python3-picamera2 -y || true

# Step 2: Install dependencies (without OpenEXR to avoid segfaults)
echo ""
echo -e "${YELLOW}[2/7] Installing dependencies...${NC}"
sudo apt install -y \
    python3-pip \
    python3-numpy \
    python3-pil \
    python3-simplejpeg \
    python3-prctl \
    python3-libcamera \
    libcap-dev \
    git \
    python3-dev \
    python3-setuptools \
    python3-build

# Install python3-imath (but NOT python3-openexr)
sudo apt install -y python3-imath

# Step 3: Clone Picamera2 repository
echo ""
echo -e "${YELLOW}[3/7] Cloning Picamera2 repository...${NC}"
TEMP_DIR="/tmp/picamera2_build"
rm -rf "$TEMP_DIR"
mkdir -p "$TEMP_DIR"
cd "$TEMP_DIR"

git clone https://github.com/raspberrypi/picamera2.git
cd picamera2

# Use a known-good commit (before 0.3.32 broke things)
# Commit f9ad0b7 is from early November 2024, known to work with IMX500
echo ""
echo -e "${YELLOW}[4/7] Checking out known-good version...${NC}"
git checkout v0.3.21  # Known stable version with IMX500 support

# Step 4: Patch for Python 3.13 compatibility
echo ""
echo -e "${YELLOW}[5/7] Patching for Python 3.13 compatibility...${NC}"

# Patch 1: Fix Imath import (if needed)
if grep -q "^import Imath$" picamera2/devices/imx500/imx500.py 2>/dev/null; then
    echo "  - Fixing Imath import case sensitivity..."
    sed -i 's/^import Imath$/import imath as Imath  # Python 3.13 fix/' picamera2/devices/imx500/imx500.py
fi

# Patch 2: Remove OpenEXR dependency (if present)
if grep -q "^import OpenEXR$" picamera2/devices/imx500/imx500.py 2>/dev/null; then
    echo "  - Removing OpenEXR import (causes segfault)..."
    sed -i 's/^import OpenEXR$/# import OpenEXR  # Disabled - Python 3.13 segfault/' picamera2/devices/imx500/imx500.py
    
    # Fix type hints that reference OpenEXR
    sed -i 's/exr_input: OpenEXR\.InputFile/exr_input/' picamera2/devices/imx500/imx500.py
    
    # Add NotImplementedError to prepare_tensor_for_injection
    sed -i '/def prepare_tensor_for_injection/a\        raise NotImplementedError("OpenEXR support disabled due to Python 3.13 compatibility")' picamera2/devices/imx500/imx500.py
fi

# Step 5: Build and install
echo ""
echo -e "${YELLOW}[6/7] Building and installing Picamera2...${NC}"
python3 -m build --wheel
# Install without dependencies since system packages are fine
sudo pip3 install --break-system-packages --no-deps dist/*.whl --force-reinstall

# Verify installation
echo ""
echo -e "${YELLOW}[7/7] Testing installation...${NC}"
python3 -c "
from picamera2 import Picamera2
print('✓ Picamera2 imported successfully')

try:
    from picamera2.devices.imx500 import IMX500
    print('✓ IMX500 module imported successfully')
except Exception as e:
    print(f'✗ IMX500 import failed: {e}')
    exit(1)

try:
    import picamera2
    version = getattr(picamera2, '__version__', 'unknown')
    print(f'✓ Picamera2 version: {version}')
except:
    print('✓ Picamera2 installed (version unavailable)')
"

if [ $? -eq 0 ]; then
    echo ""
    echo -e "${GREEN}=========================================="
    echo -e "✓ Installation successful!"
    echo -e "==========================================${NC}"
    echo ""
    
    # Test IMX500 firmware load
    echo -e "${YELLOW}Testing IMX500 firmware upload (this may take 10-15 seconds)...${NC}"
    python3 << 'EOF'
import sys
try:
    from picamera2.devices.imx500 import IMX500
    print("[Test] Initializing IMX500...")
    imx = IMX500("/usr/share/imx500-models/imx500_network_ssd_mobilenetv2_fpnlite_320x320_pp.rpk")
    print("✓ IMX500 firmware loaded successfully")
    print("✓ Network intrinsics:", imx.network_intrinsics)
except Exception as e:
    print(f"✗ IMX500 test failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
EOF
    
    if [ $? -eq 0 ]; then
        echo ""
        echo -e "${GREEN}✓ IMX500 hardware test passed!${NC}"
        echo ""
        
        # Clean up
        cd /home/thela/Desktop/Pi-Ai-Camera-
        rm -rf "$TEMP_DIR"
        
        # Restart backend
        echo -e "${YELLOW}Stopping any running backend...${NC}"
        pkill -9 -f uvicorn 2>/dev/null || true
        sleep 2
        
        echo -e "${YELLOW}Starting backend with IMX500 support...${NC}"
        nohup ./run.sh > /tmp/backend.log 2>&1 &
        BACKEND_PID=$!
        echo "Backend started with PID: $BACKEND_PID"
        
        # Wait for startup
        sleep 10
        
        echo ""
        echo -e "${GREEN}=========================================="
        echo -e "✓ Setup complete!"
        echo -e "==========================================${NC}"
        echo ""
        echo "Backend log: tail -f /tmp/backend.log"
        echo "Live stream: http://100.84.75.9:8080/live"
        echo ""
        echo "Checking backend status..."
        tail -30 /tmp/backend.log
        
    else
        echo ""
        echo -e "${RED}✗ IMX500 test failed. Check errors above.${NC}"
        exit 1
    fi
else
    echo ""
    echo -e "${RED}✗ Installation failed. Check errors above.${NC}"
    exit 1
fi
