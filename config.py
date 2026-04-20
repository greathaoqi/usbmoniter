import os
from typing import List
from dotenv import load_dotenv


class Config:
    def __init__(self):
        load_dotenv()

        # Synology settings
        self.synology_host = self._get_required("SYNOLOGY_HOST")
        self.synology_user = self._get_required("SYNOLOGY_USER")
        self.synology_port = int(os.getenv("SYNOLOGY_PORT", "22"))
        self.synology_remote_path = self._get_required("SYNOLOGY_REMOTE_PATH")

        # DingTalk settings
        self.dingtalk_webhook = self._get_required("DINGTALK_WEBHOOK")

        # USB settings
        supported_exts = os.getenv(
            "SUPPORTED_EXTENSIONS",
            ".jpg,.jpeg,.png,.raw,.arw,.cr2,.nef,.heic,.mp4,.mov,.avi"
        )
        self.supported_extensions: List[str] = [
            ext.strip().lower() for ext in supported_exts.split(",")
        ]

        # Specific folders to process: only files in these folders will be processed.
        # Comma separated, matches if folder path contains any of these names.
        # Common examples: "DCIM,CC,DS" for DJI/Sony/Canon cameras
        specific_folders = os.getenv("SPECIFIC_FOLDERS", "")
        if specific_folders:
            self.specific_folders: List[str] = [
                f.strip().lower() for f in specific_folders.split(",") if f.strip()
            ]
        else:
            self.specific_folders: List[str] = []

        # Behavior settings
        self.auto_unmount = self._parse_bool(os.getenv("AUTO_UNMOUNT", "true"))
        self.notify_on_success = self._parse_bool(os.getenv("NOTIFY_ON_SUCCESS", "true"))
        self.notify_on_failure = self._parse_bool(os.getenv("NOTIFY_ON_FAILURE", "true"))

        # Organize by date: create subdirectories by shooting date (YYYY.mm.dd/filename)
        # Works for both photos (EXIF) and videos (file modification time)
        self.organize_by_date = self._parse_bool(os.getenv("ORGANIZE_BY_DATE", "true"))

        # Installation directory (where state.json is stored)
        self.install_dir = os.getenv("INSTALL_DIR", "/opt/usb-photo-upload")

    def _get_required(self, name: str) -> str:
        value = os.getenv(name)
        if value is None:
            raise ValueError(f"Missing required environment variable: {name}")
        return value.strip()

    def _parse_bool(self, value: str) -> bool:
        return value.lower() in ("true", "1", "yes", "on")

    def is_supported_extension(self, filename: str) -> bool:
        """Check if file extension is supported (whitelist)."""
        ext = os.path.splitext(filename)[1].lower()
        return ext in self.supported_extensions

    def is_folder_allowed(self, folder_path: str) -> bool:
        """Check if folder should be processed.
        If specific_folders is empty, all folders are allowed.
        Otherwise, only folders that contain any of the specific folder names are allowed."""
        if not self.specific_folders:
            return True

        folder_path_lower = folder_path.lower()
        for allowed_folder in self.specific_folders:
            if allowed_folder in folder_path_lower:
                return True
        return False


_config = None


def get_config() -> Config:
    """Get singleton config instance."""
    global _config
    if _config is None:
        _config = Config()
    return _config
