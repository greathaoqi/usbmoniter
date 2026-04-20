# USB 照片自动上传群辉工具 (Linux)

自动检测插入的相机 U 盘，增量备份照片到群辉 Synology NAS，完成后发送钉钉通知并自动弹出 U 盘。

## 功能

- ✅ 自动检测 U 盘插入
- ✅ 增量备份：基于上次上传的文件名，只上传该文件之后的新照片
- ✅ **按拍摄日期组织目录**：`YYYY/YYYY-MM/filename`，兼容照片和视频
- ✅ rsync over SSH 传输到群辉，稳定可靠
- ✅ 备份完成后发送钉钉通知
- ✅ 自动卸载弹出 U 盘
- ✅ 开机自启后台服务

## 安装（推荐交互式安装）

1. 克隆或复制文件到你的 Linux 机器：

```bash
git clone <repo-url>
cd usbmoniter
```

2. 运行交互式安装脚本（需要 root）：

```bash
sudo chmod +x install-interactive.sh
sudo ./install-interactive.sh
```

脚本会自动：
- 安装系统依赖
- 创建目录并复制文件
- 创建 Python **虚拟环境**（不污染系统 Python）
- 交互式询问你的配置信息
- 自动生成 `.env` 配置文件
- 在虚拟环境中安装 Python 依赖
- 安装 udev 规则和 systemd 服务
- 启动服务

3. 设置 SSH 免密登录到群辉：

```bash
# 生成密钥（如果还没有）
sudo ssh-keygen

# 复制公钥到群辉
sudo ssh-copy-id your_username@your_synology_ip
```

测试连接：
```bash
sudo ssh your_username@your_synology_ip
# 应该不需要密码就能登录
```

5. 重启服务：

```bash
sudo systemctl restart usb-photo-upload
```

## 配置说明

| 配置项 | 说明 | 示例 |
|--------|------|------|
| `SYNOLOGY_HOST` | 群辉 IP 或域名 | `192.168.1.100` |
| `SYNOLOGY_USER` | 群辉用户名 | `photo` |
| `SYNOLOGY_PORT` | SSH 端口 | `22` |
| `SYNOLOGY_REMOTE_PATH` | 远程照片路径 | `/volume1/photo/camera/` |
| `DINGTALK_WEBHOOK` | 钉钉机器人 Webhook | `https://oapi.dingtalk.com/robot/send?access_token=xxx` |
| `DINGTALK_SECRET` | 钉钉机器人密钥（加签验证，可选） | `your_secret_here` |
| `SUPPORTED_EXTENSIONS` | 白名单：支持的文件扩展名 | `.jpg,.jpeg,.png,.raw,.mp4,...` |
| `SPECIFIC_FOLDERS` | 白名单：只处理这些文件夹（逗号分隔） | `DCIM,CC,DS` |
| `AUTO_UNMOUNT` | 是否自动卸载 | `true` |
| `NOTIFY_ON_SUCCESS` | 成功时通知 | `true` |
| `NOTIFY_ON_FAILURE` | 失败时通知 | `true` |
| `ORGANIZE_BY_DATE` | 是否按拍摄日期创建子目录 | `true` |

## 创建钉钉机器人

1. 打开钉钉群 → 群设置 → 机器人管理
2. 添加机器人 → 自定义机器人
3. 填写名称，选择「加签」或「关键词」安全设置
4. 复制 Webhook URL 到 `.env` 配置文件

## 增量备份原理

程序会在 `/opt/usb-photo-upload/state.json` 按文件夹分别记录每个文件夹中最大的文件编号：

```json
{
  "folders": {
    "DCIM/100CANON": {
      "last_filename": "DSC01234.JPG",
      "last_number": 1234,
      "total_files": 1234
    },
    "CC": {
      "last_filename": "DJI_0056.JPG",
      "last_number": 56,
      "total_files": 56
    },
    "DS": {
      "last_filename": "DJI_0120.MP4",
      "last_number": 120,
      "total_files": 120
    }
  },
  "total_files_uploaded": 1410,
  "last_run": "2026-04-20T10:30:00Z"
}
```

**特点：**

- ✅ **按文件夹独立记录**：支持 SD 卡上多个文件夹（`CC/`, `DS/`, `DCIM/100CANON`, `DCIM/101CANON` 等）
- ✅ **按数字比较增量**：提取文件名中的数字部分（`DSC01234.JPG` → `1234`，`DJI_0056.JPG` → `56`），只上传编号更大的文件
- ✅ **即使乱序添加文件**也能正确处理
- ✅ 每个文件夹独立增量，互不影响

每次插入 U 盘后：
1. 按文件夹分组扫描所有文件
2. 每个文件夹中，提取每个文件名中的数字
3. 只上传数字大于**本文件夹记录最大值**的文件
4. 上传完每个文件立即更新状态，支持断电/中断恢复

> 大多数相机和无人机按数字顺序命名文件（`DSC00001.JPG`, `DJI_0001.MP4`, ...），所以这个方法非常可靠。

## 白名单过滤

双重白名单过滤确保只处理你需要的文件：

1. **文件扩展名白名单**：只处理照片/视频扩展名，忽略系统文件、缓存等
2. **文件夹白名单**：只处理指定文件夹，其他文件夹完全跳过

配置示例（大疆无人机）：
```
SPECIFIC_FOLDERS=DCIM,CC,DS
```

这意味着只处理路径中包含 `DCIM`、`CC` 或 `DS` 的文件夹，其他文件夹（比如 `MISC`, `SYSTEM`, `LOG` 等）会被完全忽略。

留空 `SPECIFIC_FOLDERS=` 会处理所有文件夹。

## 按拍摄日期组织目录

当 `ORGANIZE_BY_DATE=true` 启用时，程序会自动：

1. 对于**照片**：从 EXIF 信息提取拍摄日期
2. 对于**视频**或无法提取 EXIF 的照片：使用文件修改时间
3. 在群辉创建目录结构：`YYYY.mm.dd/filename`

示例：
```
photo/
├── 2024.03.15/
│   ├── DSC01234.JPG
│   └── DSC01235.JPG
├── 2024.04.20/
│   ├── DSC01500.JPG
│   └── DJI_0001.MP4
```

这样照片会自动按拍摄日期归档，方便管理。

**增量逻辑说明**：
增量备份基于**源 U 盘上的文件名顺序**，和目标目录结构无关。不管你用什么日期格式，增量始终正常工作：
1. 扫描 U 盘上所有文件 → 按原文件名排序
2. 找到上次最后上传的文件名 → 从下一个开始上传
3. 状态文件只记录文件名，不记录目标路径

## 查看日志

```bash
# 查看服务状态
sudo systemctl status usb-photo-upload

# 实时查看日志
journalctl -u usb-photo-upload -f
```

## 手动触发测试

可以手动运行一次处理流程测试：

```bash
cd /opt/usb-photo-upload
sudo python3 usb_photo_upload.py --once
```

## 支持的文件格式

默认支持：
- 图片：`.jpg`, `.jpeg`, `.png`, `.raw`, `.arw`, `.cr2`, `.nef`, `.heic`
- 视频：`.mp4`, `.mov`, `.avi`

可以在 `.env` 的 `SUPPORTED_EXTENSIONS` 添加更多格式。

## 权限说明

服务以 root 用户运行，原因：
- 需要访问 udev 设备事件
- 需要卸载 U 盘的权限
- 需要访问挂载的 U 盘文件系统

SSH 密钥需要放在 `/root/.ssh/` 目录下。

## 故障排查

**U 盘插入后没有反应？**
- 检查日志：`journalctl -u usb-photo-upload -f`
- 确认 U 盘已经被系统挂载（通常会自动挂载到 `/media/`）
- 检查 udev 规则是否正确加载：`udevadm control --reload-rules`

**上传失败？**
- 测试 SSH 连接：`sudo ssh your-user@your-synology-ip`
- 确认远程路径存在并且有写入权限
- 检查网络连通性

**钉钉通知收不到？**
- 检查 Webhook URL 是否正确
- 检查安全设置（关键词或加签配置）
- 测试网络能否访问 `oapi.dingtalk.com`

## 卸载

```bash
sudo systemctl stop usb-photo-upload
sudo systemctl disable usb-photo-upload
sudo rm /etc/systemd/system/usb-photo-upload.service
sudo rm /etc/udev/rules.d/99-usb-photo-upload.rules
sudo rm -rf /opt/usb-photo-upload
sudo systemctl daemon-reload
sudo udevadm control --reload-rules
```

## 许可证

MIT
