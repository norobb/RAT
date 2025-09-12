#!/bin/bash
set -e

echo "[INFO] Starting RAT Client build process..."

# --- Configuration ---
PYTHON_SCRIPT="client.py"
ICON_FILE="icon.ico"
DIST_PATH="executables"
BUILD_PATH="build_temp"

# --- OS Detection ---
OS=$(uname -s)
if [ "$OS" = "Linux" ]; then
    EXE_NAME="client-linux"
elif [ "$OS" = "Darwin" ]; then
    EXE_NAME="client-macos"
else
    echo "[ERROR] Unsupported operating system: $OS"
    exit 1
fi

# --- Validation ---
if [ ! -f "$PYTHON_SCRIPT" ]; then
    echo "[ERROR] Main script not found: $PYTHON_SCRIPT"
    exit 1
fi

if [ ! -f "$ICON_FILE" ]; then
    echo "[WARNING] Icon file not found: $ICON_FILE. Building without an icon."
    ICON_OPTION=""
else
    ICON_OPTION="--icon=$ICON_FILE"
fi

# --- Build ---
echo "[INFO] Running PyInstaller..."
pyinstaller --noconsole --onefile --name "$EXE_NAME" $ICON_OPTION --distpath "$DIST_PATH" --workpath "$BUILD_PATH" --clean "$PYTHON_SCRIPT"

if [ $? -ne 0 ]; then
    echo "[ERROR] PyInstaller failed."
    exit 1
fi

echo "[SUCCESS] Executable created successfully in '$DIST_PATH/$EXE_NAME'"

# --- Cleanup ---
echo "[INFO] Cleaning up temporary build files..."
if [ -d "$BUILD_PATH" ]; then
    rm -rf "$BUILD_PATH"
fi
if [ -f "*.spec" ]; then
    rm "*.spec"
fi

echo "[INFO] Build process finished."
