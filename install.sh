#!/bin/bash
set -e

INSTALL_DIR="/opt/usb-photo-upload"
VENV_DIR="$INSTALL_DIR/venv"

echo "=== USB Photo Auto-Upload Installer ==="
echo

# Check if running as root
if [ "$(id -u)" -ne 0 ]; then
    echo "Error: This installer must be run as root (use sudo)."
    exit 1
fi

# Install system dependencies
echo ">>> Installing system dependencies..."
apt-get update
apt-get install -y python3 python3-pip python3-venv rsync

# Create installation directory
echo ">>> Creating installation directory..."
mkdir -p "$INSTALL_DIR"

# Copy all files
echo ">>> Copying files to $INSTALL_DIR..."
cp -f usb_photo_upload.py config.py utils.py "$INSTALL_DIR/"
cp -f requirements.txt .env.example "$INSTALL_DIR/"

# Create Python virtual environment
echo ">>> Creating Python virtual environment..."
python3 -m venv "$VENV_DIR"

# Install Python dependencies into virtual environment
echo ">>> Installing Python dependencies..."
"$VENV_DIR/bin/pip" install -r "$INSTALL_DIR/requirements.txt"

# Make main script executable
chmod +x "$INSTALL_DIR/usb_photo_upload.py"

# Copy udev rule
echo ">>> Installing udev rule..."
cp -f 99-usb-photo-upload.rules /etc/udev/rules.d/

# Copy systemd service with path substitution
echo ">>> Installing systemd service..."
sed "s|@INSTALL_DIR@|$INSTALL_DIR|g" usb-photo-upload.service > /etc/systemd/system/usb-photo-upload.service

# Reload configurations
echo ">>> Reloading udev and systemd..."
udevadm control --reload-rules
systemctl daemon-reload

# Enable and start service
echo ">>> Enabling and starting service..."
systemctl enable usb-photo-upload
systemctl start usb-photo-upload

echo
echo "=== Installation Complete ==="
echo
echo "Next steps:"
echo "1. Copy $INSTALL_DIR/.env.example to $INSTALL_DIR/.env"
echo "2. Edit $INSTALL_DIR/.env with your Synology and DingTalk settings"
echo "3. Setup SSH key for root to access Synology: sudo ssh-copy-id your-user@your-synology-ip"
echo "4. Restart the service: sudo systemctl restart usb-photo-upload"
echo
echo "Check service status: sudo systemctl status usb-photo-upload"
echo "View logs: journalctl -u usb-photo-upload -f"
echo
