# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

- **Install (recommended interactive):** `sudo ./install-interactive.sh`
- **Manual test/debug:** `sudo python usb_photo_upload.py --once`
- **Check service status:** `sudo systemctl status usb-photo-upload`
- **View live logs:** `journalctl -u usb-photo-upload -f`
- **Restart service:** `sudo systemctl restart usb-photo-upload`
- **Install Python dependencies:** `pip install -r requirements.txt`

## Architecture

This is a Linux daemon that automatically detects USB camera cards, incrementally backs up photos/videos to a Synology NAS over SSH/rsync, sends DingTalk notifications, and unmounts the drive when done.

### High-level structure

- **`usb_photo_upload.py`**: Main entry point
  - Entry: `main()` → parses args, gets config
  - `--once` mode: processes once and exits (for testing)
  - Normal mode: `monitor_usb_devices()` → uses pyudev to listen for USB block device add events, triggers processing
  - `process_usb_device()`: orchestrates the full workflow: detect USB → scan files → filter incremental → upload → notify → unmount

- **`utils.py`**: All utility classes
  - `StateManager`: Persists incremental upload state to `state.json`. Tracks per-folder: last filename, max file number. Updates after each successful upload for resume capability.
  - `DateExtractor`: Gets shooting date from EXIF (photos) or file modification time (videos).
  - `DingTalkNotifier`: Sends start/success/failure notifications via webhook with HMAC signature verification.
  - `RsyncUploader`: Uploads files via `rsync` over SSH.
  - `UsbDetector`: Discovers mounted USB devices, scans/filters photo files by whitelist (extensions + folders), organizes by date, unmounts and powers off devices.

- **`config.py`**: Configuration via `.env` file (python-dotenv). Singleton `Config` class with validation helper methods.
- **`.env.example`**: Example configuration. Copy to `.env` and fill in.

### Incremental Backup Logic

The system tracks state **per folder** on the USB device:
1. Extract the last sequence of digits from filenames (e.g., `DSC01234.JPG` → `1234`)
2. Only upload files where the number is greater than the max number seen in that folder
3. State is updated after each successful upload so uploads can resume after interruption
4. Multiple folders (e.g., `DCIM/100CANON`, `CC`, `DS`) are tracked independently

### Date-organized Directory Structure

When `ORGANIZE_BY_DATE=true`:
- Photos: EXIF `DateTimeOriginal` → `YYYY.mm.dd/filename`
- Videos/no EXIF: file modification time → `YYYY.mm.dd/filename`

### Installation Components

The installer sets up:
1. udev rule (`/etc/udev/rules.d/99-usb-photo-upload.rules`) - triggers on USB block device add
2. systemd service (`/etc/systemd/system/usb-photo-upload.service`) - runs the monitor as a background service
3. Python virtual environment in `/opt/usb-photo-upload/venv`
4. `state.json` persists upload state in the install directory

## Key Dependencies

- `pyudev`: USB device monitoring via udev
- `psutil`: Disk partition detection
- `requests`: DingTalk webhook calls
- `python-dotenv`: Environment configuration
- `Pillow`: EXIF date extraction
- `rsync`: File transfer (system-level dependency)
