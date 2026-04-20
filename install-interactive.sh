#!/bin/bash
set -e

# Interactive installer for USB Photo Auto-Upload to Synology
# This script asks user for configuration and installs everything automatically

INSTALL_DIR="/opt/usb-photo-upload"
VENV_DIR="$INSTALL_DIR/venv"

echo "=== USB 照片自动上传群辉 - 交互式安装 ==="
echo

# Check if running as root
if [ "$(id -u)" -ne 0 ]; then
    echo "错误: 必须用 root 运行安装程序 (使用 sudo)."
    exit 1
fi

# Function to read input with default value
read_input() {
    local prompt="$1"
    local default="$2"
    if [ -n "$default" ]; then
        read -p "$prompt [$default]: " input
        if [ -z "$input" ]; then
            echo "$default"
            return
        fi
    else
        read -p "$prompt: " input
    fi
    echo "$input"
}

echo ">>> 请输入配置信息："
echo

SYNOLOGY_HOST=$(read_input "群辉 IP 或主机名" "")
if [ -z "$SYNOLOGY_HOST" ]; then
    echo "错误: 群辉地址不能为空"
    exit 1
fi

SYNOLOGY_USER=$(read_input "群辉用户名" "")
if [ -z "$SYNOLOGY_USER" ]; then
    echo "错误: 群辉用户名不能为空"
    exit 1
fi

SYNOLOGY_PORT=$(read_input "群辉 SSH 端口" "22")

SYNOLOGY_REMOTE_PATH=$(read_input "群辉远程路径 (例如 /volume1/photo/camera)" "")
if [ -z "$SYNOLOGY_REMOTE_PATH" ]; then
    echo "错误: 远程路径不能为空"
    exit 1
fi

DINGTALK_WEBHOOK=$(read_input "钉钉机器人 Webhook URL" "")

SPECIFIC_FOLDERS=$(read_input "只处理特定文件夹 (例如 DCIM,CC,DS，留空处理所有)" "")

ORGANIZE_BY_DATE=$(read_input "按拍摄日期创建子目录 (true/false)" "true")

AUTO_UNMOUNT=$(read_input "完成后自动卸载 U 盘 (true/false)" "true")

echo
echo ">>> 开始安装..."
echo

# Install system dependencies
echo "[1/8] 安装系统依赖..."
apt-get update
apt-get install -y python3 python3-pip python3-venv rsync git

# Create installation directory
echo "[2/8] 创建安装目录..."
mkdir -p "$INSTALL_DIR"

# Copy all files
echo "[3/8] 复制程序文件..."
cp -f usb_photo_upload.py config.py utils.py "$INSTALL_DIR/"
cp -f requirements.txt "$INSTALL_DIR/"
cp -f 99-usb-photo-upload.rules "$INSTALL_DIR/"
cp -f usb-photo-upload.service "$INSTALL_DIR/"

# Generate .env configuration file
echo "[4/8] 生成配置文件..."
cat > "$INSTALL_DIR/.env" <<EOF
# Synology NAS Configuration
SYNOLOGY_HOST=$SYNOLOGY_HOST
SYNOLOGY_USER=$SYNOLOGY_USER
SYNOLOGY_PORT=$SYNOLOGY_PORT
SYNOLOGY_REMOTE_PATH=$SYNOLOGY_REMOTE_PATH

# DingTalk Robot Webhook
DINGTALK_WEBHOOK=$DINGTALK_WEBHOOK

# Supported file extensions (whitelist)
SUPPORTED_EXTENSIONS=.jpg,.jpeg,.png,.raw,.arw,.cr2,.nef,.heic,.mp4,.mov,.avi

# Specific folders to process (comma separated, leave empty for all)
SPECIFIC_FOLDERS=$SPECIFIC_FOLDERS

# Behavior Settings
AUTO_UNMOUNT=$AUTO_UNMOUNT
NOTIFY_ON_SUCCESS=true
NOTIFY_ON_FAILURE=true
ORGANIZE_BY_DATE=$ORGANIZE_BY_DATE

# Installation directory
INSTALL_DIR=$INSTALL_DIR
EOF

# Create Python virtual environment
echo "[5/8] 创建 Python 虚拟环境..."
python3 -m venv "$VENV_DIR"

# Install Python dependencies into virtual environment
echo "[6/8] 安装 Python 依赖..."
"$VENV_DIR/bin/pip" install -r "$INSTALL_DIR/requirements.txt"

# Make main script executable
chmod +x "$INSTALL_DIR/usb_photo_upload.py"

# Copy udev rule
echo "[7/8] 安装 udev 规则..."
cp -f 99-usb-photo-upload.rules /etc/udev/rules.d/

# Update systemd service with correct venv path
echo "[8/8] 安装 systemd 服务..."
sed "s|@INSTALL_DIR@|$INSTALL_DIR|g" usb-photo-upload.service > /etc/systemd/system/usb-photo-upload.service

# Reload configurations
echo ">>> 重载配置..."
udevadm control --reload-rules
systemctl daemon-reload

# Enable and start service
echo ">>> 启用并启动服务..."
systemctl enable usb-photo-upload
systemctl start usb-photo-upload

echo
echo "================================================"
echo "        安装完成！"
echo "================================================"
echo
echo "安装目录: $INSTALL_DIR"
echo "虚拟环境: $VENV_DIR"
echo "配置文件: $INSTALL_DIR/.env"
echo "服务状态: $(systemctl is-active usb-photo-upload)"
echo
echo "下一步：设置 SSH 免密登录到群辉"
echo "--------------------------------"
if [ ! -f "/root/.ssh/id_rsa.pub" ]; then
    echo "还没有 SSH 密钥，先生成："
    echo "  sudo ssh-keygen -t rsa"
fi
echo "复制公钥到群辉："
echo "  sudo ssh-copy-id $SYNOLOGY_USER@$SYNOLOGY_HOST"
echo "测试连接："
echo "  sudo ssh $SYNOLOGY_USER@$SYNOLOGY_HOST -p $SYNOLOGY_PORT"
echo
echo "查看日志："
echo "  journalctl -u usb-photo-upload -f"
echo
echo "检查服务状态："
echo "  sudo systemctl status usb-photo-upload"
echo
