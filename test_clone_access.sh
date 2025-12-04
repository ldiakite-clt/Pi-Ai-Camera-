#!/bin/bash
# Quick test script to verify backend file access after fresh clone

echo "=================================="
echo "Testing Backend File Accessibility"
echo "=================================="
echo ""

# Test directory
TEST_DIR="/tmp/Pi-Ai-Camera-test-$$"

echo "1. Cloning repository to temporary location..."
git clone https://github.com/ldiakite-clt/Pi-Ai-Camera-.git "$TEST_DIR" 2>&1 | grep -E "(Cloning|done)"

if [ ! -d "$TEST_DIR" ]; then
    echo "❌ Failed to clone repository"
    exit 1
fi

cd "$TEST_DIR"

echo ""
echo "2. Checking backend files..."
BACKEND_FILES=(
    "backend/main.py"
    "backend/rpicam_streaming.py"
    "backend/object_detection.py"
    "backend/ai_camera.py"
    "backend/rpicam_detector.py"
    "backend/camera.py"
    "backend/database.py"
    "backend/video_utils.py"
)

ALL_FOUND=true
for file in "${BACKEND_FILES[@]}"; do
    if [ -f "$file" ]; then
        SIZE=$(du -h "$file" | cut -f1)
        echo "   ✅ $file ($SIZE)"
    else
        echo "   ❌ $file - NOT FOUND"
        ALL_FOUND=false
    fi
done

echo ""
echo "3. Checking Python imports..."
cd "$TEST_DIR"
python3 -c "import sys; sys.path.insert(0, '.'); from backend.rpicam_streaming import RPiCamStreaming; print('   ✅ rpicam_streaming imports successfully')" 2>&1 | grep -E "(✅|Error)"
python3 -c "import sys; sys.path.insert(0, '.'); from backend.object_detection import COCO_CLASSES; print('   ✅ object_detection imports successfully')" 2>&1 | grep -E "(✅|Error)"

echo ""
echo "4. Checking documentation..."
if [ -f "README.md" ]; then
    LINES=$(wc -l < README.md)
    echo "   ✅ README.md exists ($LINES lines)"
else
    echo "   ❌ README.md missing"
fi

if [ -f "verify_system.sh" ]; then
    echo "   ✅ verify_system.sh exists"
else
    echo "   ❌ verify_system.sh missing"
fi

echo ""
echo "5. Cleanup..."
cd /tmp
rm -rf "$TEST_DIR"
echo "   ✅ Test directory removed"

echo ""
if [ "$ALL_FOUND" = true ]; then
    echo "=================================="
    echo "✅ ALL TESTS PASSED"
    echo "=================================="
    echo ""
    echo "Backend files are fully accessible in the repository."
    echo "You can safely clone on any machine and access all code."
    echo ""
    echo "Clone command:"
    echo "  git clone https://github.com/ldiakite-clt/Pi-Ai-Camera-.git"
else
    echo "=================================="
    echo "❌ SOME TESTS FAILED"
    echo "=================================="
    echo "Check the errors above."
fi
