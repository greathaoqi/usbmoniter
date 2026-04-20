import os
import json
import time
import datetime
import re
import subprocess
import requests
import psutil
from typing import List, Optional, Tuple, Dict
from dataclasses import dataclass
from PIL import Image
from PIL.ExifTags import TAGS
from config import Config


@dataclass
class FolderState:
    folder_path: str          # Relative folder path from USB root
    last_filename: str        # Last (largest by number) filename uploaded
    last_number: int          # Extracted number from last filename
    total_files: int          # Total files uploaded in this folder


@dataclass
class State:
    # Key: relative folder path, Value: FolderState
    folders: Dict[str, FolderState]
    total_files_uploaded: int
    last_run: str


class StateManager:
    """Manages persisting state to track incremental uploads.
    Tracks last uploaded file per folder, per prefix with maximum number."""

    def __init__(self, state_path: str):
        self.state_path = state_path

    def load(self) -> State:
        """Load state from file, return default state if file doesn't exist."""
        if not os.path.exists(self.state_path):
            return State(
                folders={},
                total_files_uploaded=0,
                last_run=""
            )

        try:
            with open(self.state_path, 'r') as f:
                data = json.load(f)
            folders = {}
            for folder_path, fstate in data.get("folders", {}).items():
                folders[folder_path] = FolderState(
                    folder_path=folder_path,
                    last_filename=fstate.get("last_filename", ""),
                    last_number=fstate.get("last_number", 0),
                    total_files=fstate.get("total_files", 0)
                )
            return State(
                folders=folders,
                total_files_uploaded=data.get("total_files_uploaded", 0),
                last_run=data.get("last_run", "")
            )
        except Exception as e:
            print(f"Error loading state file: {e}, starting fresh")
            return State(
                folders={},
                total_files_uploaded=0,
                last_run=""
            )

    def save(self, state: State) -> None:
        """Save current state to file."""
        folders_data = {}
        for folder_path, fstate in state.folders.items():
            folders_data[folder_path] = {
                "last_filename": fstate.last_filename,
                "last_number": fstate.last_number,
                "total_files": fstate.total_files
            }
        data = {
            "folders": folders_data,
            "total_files_uploaded": state.total_files_uploaded,
            "last_run": state.last_run
        }
        # Ensure directory exists
        os.makedirs(os.path.dirname(self.state_path), exist_ok=True)
        with open(self.state_path, 'w') as f:
            json.dump(data, f, indent=2)

    def update_after_upload(self, folder_path: str, filename: str, count: int = 1) -> State:
        """Update state after successful file upload.
        Extracts number from filename and keeps maximum."""
        state = self.load()

        # Extract number from filename
        num = self._extract_number(filename)
        folder_key = folder_path.rstrip('/')

        if folder_key in state.folders:
            # Update if new number is larger
            if num > state.folders[folder_key].last_number:
                state.folders[folder_key].last_filename = filename
                state.folders[folder_key].last_number = num
            state.folders[folder_key].total_files += count
        else:
            # New folder
            state.folders[folder_key] = FolderState(
                folder_path=folder_key,
                last_filename=filename,
                last_number=num,
                total_files=count
            )

        state.total_files_uploaded += count
        state.last_run = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        self.save(state)
        return state

    @staticmethod
    def _extract_number(filename: str) -> int:
        """Extract the numeric part from filename.
        Examples:
            DSC01234.JPG -> 1234
            IMG_0001.jpg -> 1
            DJI_0012.MP4 -> 12
            DSCN0001.NEF -> 1
            100_0001 -> 1
        Returns 0 if no number found."""
        # Find the last sequence of digits in the filename
        basename = os.path.splitext(filename)[0]
        matches = re.findall(r'\d+', basename)
        if not matches:
            return 0
        # Take the last sequence of digits
        try:
            return int(matches[-1])
        except ValueError:
            return 0

    def get_start_number(self, folder_path: str) -> int:
        """Get the starting number for a folder: any file with number > this gets uploaded."""
        folder_key = folder_path.rstrip('/')
        if folder_key in self.load().folders:
            return self.load().folders[folder_key].last_number
        return 0


class DateExtractor:
    """Extract shooting date from photo EXIF or use file modification time for videos."""

    @staticmethod
    def get_date_taken(file_path: str) -> datetime.datetime:
        """Get the date when photo/video was taken.
        For photos: tries to extract from EXIF first.
        Falls back to file modification time if EXIF not available."""
        filename = os.path.basename(file_path).lower()
        ext = os.path.splitext(filename)[1]

        # Try EXIF for image formats
        image_extensions = ('.jpg', '.jpeg', '.png', '.raw', '.arw', '.cr2', '.nef', '.heic')
        if ext in image_extensions:
            try:
                exif_date = DateExtractor._extract_exif_date(file_path)
                if exif_date:
                    return exif_date
            except Exception:
                pass

        # Fallback to file modification time
        mtime = os.path.getmtime(file_path)
        return datetime.datetime.fromtimestamp(mtime)

    @staticmethod
    def _extract_exif_date(file_path: str) -> Optional[datetime.datetime]:
        """Extract date from EXIF DateTimeOriginal tag."""
        try:
            with Image.open(file_path) as img:
                exif_data = img.getexif()
                if not exif_data:
                    return None

                # Find DateTimeOriginal tag
                for tag_id, value in exif_data.items():
                    tag = TAGS.get(tag_id, tag_id)
                    if tag == 'DateTimeOriginal':
                        # Format: "YYYY:MM:DD HH:MM:SS"
                        try:
                            return datetime.datetime.strptime(value, "%Y:%m:%d %H:%M:%S")
                        except ValueError:
                            pass
                    elif tag == 'DateTime':
                        try:
                            return datetime.datetime.strptime(value, "%Y:%m:%d %H:%M:%S")
                        except ValueError:
                            pass

            return None
        except Exception:
            return None


class DingTalkNotifier:
    """Sends notifications to DingTalk via webhook."""

    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    def send_start(self, files_to_upload: int) -> bool:
        """Send notification when backup starts, showing how many files will be uploaded."""
        content = "🔔 USB 照片备份开始\n\n"
        content += f"检测到新 U 盘插入，本次需要备份 {files_to_upload} 个文件"

        payload = {
            "msgtype": "text",
            "text": {
                "content": content
            }
        }

        try:
            response = requests.post(self.webhook_url, json=payload, timeout=10)
            response.raise_for_status()
            result = response.json()
            if result.get("errcode", 0) != 0:
                print(f"DingTalk API error: {result.get('errmsg')}")
                return False
            return True
        except Exception as e:
            print(f"Failed to send DingTalk start notification: {e}")
            return False

    def send(self, success: bool, files_uploaded: int, total_files: int, error_msg: Optional[str] = None) -> bool:
        """Send notification about backup completion."""
        status_text = "✅ 备份成功" if success else "❌ 备份失败"

        content = f"{status_text}\n\n"
        content += f"本次上传: {files_uploaded} 个文件\n"
        content += f"累计上传: {total_files} 个文件\n"

        if error_msg:
            content += f"\n错误信息: {error_msg}"

        payload = {
            "msgtype": "text",
            "text": {
                "content": content
            }
        }

        try:
            response = requests.post(self.webhook_url, json=payload, timeout=10)
            response.raise_for_status()
            result = response.json()
            if result.get("errcode", 0) != 0:
                print(f"DingTalk API error: {result.get('errmsg')}")
                return False
            return True
        except Exception as e:
            print(f"Failed to send DingTalk notification: {e}")
            return False


class RsyncUploader:
    """Uploads files to Synology via rsync over SSH."""

    def __init__(self, config: Config):
        self.config = config

    def upload_file(self, local_file: str, remote_base_path: str, relative_path: str) -> bool:
        """Upload a single file to Synology using rsync."""
        remote_dest = (
            f"{self.config.synology_user}@{self.config.synology_host}:"
            f"{self.config.synology_remote_path.rstrip('/')}/{relative_path}"
        )

        # Ensure parent directory exists on remote
        # rsync will create it automatically with -a flag

        cmd = [
            "rsync", "-av",
            "-e", f"ssh -p {self.config.synology_port}",
            "--progress",
            local_file,
            remote_dest
        ]

        try:
            print(f"Uploading: {relative_path}")
            result = subprocess.run(cmd, check=True, capture_output=False)
            return result.returncode == 0
        except subprocess.CalledProcessError as e:
            print(f"Upload failed for {local_file}: {e}")
            return False


class UsbDetector:
    """Detects mounted USB devices and finds mount points."""

    @staticmethod
    def get_mount_points() -> List[str]:
        """Get all mount points that are on USB devices."""
        usb_mounts = []
        for partition in psutil.disk_partitions():
            # Check if device path contains usb or /dev/sd* (usually USB on many systems)
            if '/dev/' in partition.device and (
                'usb' in partition.device.lower() or
                partition.fstype not in ('devtmpfs', 'tmpfs', 'sysfs', 'proc')
            ):
                # Skip system partitions
                if not any(skip in partition.mountpoint for skip in ('/sys', '/proc', '/dev', '/run')):
                    usb_mounts.append(partition.mountpoint)
        return usb_mounts

    @staticmethod
    def find_photo_files_by_folder(mount_point: str, config: Config) -> Dict[str, List[str]]:
        """Recursively find all supported photo/video files on the mounted USB.
        Returns files grouped by folder.
        Only processes files in allowed specific folders (if configured), and only allows whitelisted extensions."""
        files_by_folder: Dict[str, List[str]] = {}

        for root, _, files in os.walk(mount_point):
            # Check if this folder is allowed (specific folders filtering)
            rel_folder = os.path.relpath(root, mount_point)
            if rel_folder == '.':
                rel_folder = ''  # root folder

            # Skip this folder if not in allowed list (when specific folders configured)
            if not config.is_folder_allowed(rel_folder):
                continue

            for filename in files:
                # Only allow whitelisted extensions
                if config.is_supported_extension(filename):
                    full_path = os.path.join(root, filename)
                    if rel_folder not in files_by_folder:
                        files_by_folder[rel_folder] = []
                    files_by_folder[rel_folder].append(full_path)

        # Sort files in each folder by extracted number (ascending)
        for folder in files_by_folder:
            # Sort by extracted number, then by filename
            files_by_folder[folder].sort(key=lambda x: (StateManager._extract_number(os.path.basename(x)), os.path.basename(x)))

        return files_by_folder

    @staticmethod
    def filter_files_to_upload(files_by_folder: Dict[str, List[str]], state_manager: StateManager, mount_point: str) -> List[str]:
        """Filter files: only return files with number greater than last uploaded in each folder.
        This handles multiple folders (like CC/, DS/) independently."""
        files_to_upload = []

        for folder_path, files in files_by_folder.items():
            # Get last number for this folder
            start_num = state_manager.get_start_number(folder_path)
            for file_path in files:
                filename = os.path.basename(file_path)
                num = StateManager._extract_number(filename)
                if num > start_num:
                    files_to_upload.append(file_path)
                elif num == 0 and start_num == 0:
                    # No numbers found, first file - upload it
                    files_to_upload.append(file_path)

        return files_to_upload

    @staticmethod
    def get_organized_relative_path(full_path: str, mount_point: str, config: Config) -> str:
        """Get relative path organized by shooting date.
        Creates structure like: YYYY.mm.dd/filename
        Preserves original filename."""
        filename = os.path.basename(full_path)

        # Get shooting date
        dt = DateExtractor.get_date_taken(full_path)
        # Format: YYYY.mm.dd/filename (e.g., 2024.04.20/DSC01234.JPG)
        date_dir = f"{dt.year}.{dt.month:02d}.{dt.day:02d}"

        # Ensure forward slashes for remote path
        return f"{date_dir}/{filename}".replace(os.path.sep, '/')

    @staticmethod
    def get_relative_path(full_path: str, mount_point: str) -> str:
        """Get relative path from mount point for preserving directory structure on remote."""
        rel_path = os.path.relpath(full_path, mount_point)
        # Ensure forward slashes for remote path
        return rel_path.replace(os.path.sep, '/')

    @staticmethod
    def unmount(mount_point: str) -> bool:
        """Unmount the USB drive."""
        try:
            subprocess.run(["umount", mount_point], check=True, capture_output=True)
            print(f"Successfully unmounted {mount_point}")

            # Try to power off the device after unmount for safe removal
            # This is optional but nice to have
            UsbDetector._power_off_device(mount_point)
            return True
        except subprocess.CalledProcessError as e:
            print(f"Failed to unmount {mount_point}: {e.stderr.decode()}")
            return False

    @staticmethod
    def _power_off_device(mount_point: str) -> None:
        """Try to power off the USB device after unmount."""
        try:
            # Find the device from mount point
            for partition in psutil.disk_partitions():
                if partition.mountpoint == mount_point:
                    device = partition.device
                    # Get the parent device (e.g., /dev/sdb from /dev/sdb1)
                    if '1' in device:
                        base_device = device.rstrip('0123456789')
                        # Find the syspath
                        # This approach varies by system, but let's try common paths
                        if base_device.startswith('/dev/'):
                            base_name = base_device[5:]  # sdb
                            sys_path = f"/sys/block/{base_name}/device/delete"
                            if os.path.exists(sys_path):
                                with open(sys_path, 'w') as f:
                                    f.write("1\n")
                                print(f"Powered off device {base_device}")
                    break
        except Exception as e:
            print(f"Could not power off device: {e}")
