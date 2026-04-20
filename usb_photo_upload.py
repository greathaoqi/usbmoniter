#!/usr/bin/env python3
import os
import sys
import time
import logging
import pyudev
from typing import List

from config import get_config, Config
from utils import (
    StateManager,
    DingTalkNotifier,
    RsyncUploader,
    UsbDetector,
    State
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


def process_usb_device(config: Config, state_manager: StateManager,
                       rsync_uploader: RsyncUploader, notifier: DingTalkNotifier) -> None:
    """Process newly detected USB device - scan, upload, notify, unmount.
    Groups files by folder, tracks last maximum number per folder for incremental upload.
    Supports multiple folders like CC/, DS/, DCIM/100CANON etc."""
    start_time = time.time()
    logger.info("Starting USB photo backup process...")

    # Get all mounted USB devices
    mount_points = UsbDetector.get_mount_points()
    if not mount_points:
        logger.warning("No mounted USB devices found, exiting.")
        return

    # For simplicity, process the first found USB drive
    mount_point = mount_points[0]
    logger.info(f"Found USB mount point: {mount_point}")

    # Load state
    state = state_manager.load()

    # Find all photo files grouped by folder
    files_by_folder = UsbDetector.find_photo_files_by_folder(mount_point, config)

    # Count total files
    total_files = sum(len(files) for files in files_by_folder.values())
    logger.info(f"Found {total_files} supported files in {len(files_by_folder)} folders")

    if total_files == 0:
        logger.info("No supported files found, nothing to do.")
        if config.notify_on_success:
            notifier.send(success=True, files_uploaded=0, total_files=state.total_files_uploaded,
                         error_msg="No photos found on USB drive")
        return

    # Filter files to upload: only those with number > last uploaded in each folder
    files_to_upload = UsbDetector.filter_files_to_upload(files_by_folder, state_manager, mount_point)

    logger.info(f"{len(files_to_upload)} new files to upload across {len(files_by_folder)} folders")

    if not files_to_upload:
        logger.info("No new files to upload, everything is already backed up.")
        if config.notify_on_success:
            notifier.send(success=True, files_uploaded=0, total_files=state.total_files_uploaded,
                         error_msg="No new files to upload")
        # Still try to unmount if auto_unmount is enabled
        if config.auto_unmount and len(mount_points) > 0:
            logger.info(f"Auto-unmounting {mount_point}")
            UsbDetector.unmount(mount_point)
        return

    # Send start notification to DingTalk: show how many files will be uploaded
    if config.notify_on_success:
        notifier.send_start(len(files_to_upload))

    # Upload files one by one
    success_count = 0
    error_files: List[str] = []

    for photo_path in files_to_upload:
        filename = os.path.basename(photo_path)
        # Get relative folder for this file
        rel_folder = os.path.relpath(os.path.dirname(photo_path), mount_point)

        # Get remote relative path - organized by date or keep original structure
        if config.organize_by_date:
            rel_path = UsbDetector.get_organized_relative_path(photo_path, mount_point, config)
        else:
            rel_path = UsbDetector.get_relative_path(photo_path, mount_point)

        if rsync_uploader.upload_file(photo_path, config.synology_remote_path, rel_path):
            success_count += 1
            # Update state after each successful upload for resume capability
            # Tracks per folder, keeps maximum number
            state = state_manager.update_after_upload(rel_folder, filename, 1)
        else:
            error_files.append(filename)

    # Generate result
    elapsed = time.time() - start_time
    logger.info(f"Backup completed in {elapsed:.1f} seconds. "
                f"Successfully uploaded {success_count}/{len(files_to_upload)} files.")

    if error_files:
        error_msg = f"Failed to upload {len(error_files)} files: {', '.join(error_files[:5])}"
        if len(error_files) > 5:
            error_msg += f" ... ({len(error_files)} total)"
        logger.error(error_msg)
    else:
        error_msg = None

    # Send notification
    if (success_count > 0 and config.notify_on_success) or \
       (error_files and config.notify_on_failure):
        notifier.send(
            success=len(error_files) == 0,
            files_uploaded=success_count,
            total_files=state.total_files_uploaded,
            error_msg=error_msg
        )

    # Unmount if configured and successful
    if config.auto_unmount and (error_files is None or success_count > 0):
        logger.info(f"Auto-unmounting {mount_point}")
        unmount_success = UsbDetector.unmount(mount_point)
        if not unmount_success:
            logger.error(f"Failed to unmount {mount_point}")
            if config.notify_on_failure:
                notifier.send(
                    success=False,
                    files_uploaded=success_count,
                    total_files=state.total_files_uploaded,
                    error_msg=f"Upload completed but failed to unmount USB drive: {mount_point}"
                )


def is_usb_device(device: pyudev.Device) -> bool:
    """Check if device is on USB bus."""
    # Check if device is connected via USB
    if device.get('ID_BUS') == 'usb':
        return True
    # Check parent devices
    parent = device.parent
    while parent:
        if parent.get('ID_BUS') == 'usb':
            return True
        if 'usb' in parent.get('DEVTYPE', '') or 'usb' in parent.get('SUBSYSTEM', ''):
            return True
        parent = parent.parent
    return False

def monitor_usb_devices(config: Config):
    """Main loop that monitors for USB device insertion events.
    Only processes block devices on USB bus."""
    context = pyudev.Context()
    monitor = pyudev.Monitor.from_netlink(context)
    monitor.filter_by(subsystem='block', device_type='partition')

    logger.info("USB photo upload service started. Waiting for USB device insertion...")

    state_path = os.path.join(config.install_dir, "state.json")
    state_manager = StateManager(state_path)
    rsync_uploader = RsyncUploader(config)
    notifier = DingTalkNotifier(config.dingtalk_webhook, config.dingtalk_secret)

    # Process any already mounted USB devices on startup
    # When triggered by udev add event, udisks may still be mounting the device
    # Wait a few seconds for mounting to complete before scanning
    try:
        logger.info("Waiting for USB device mount to complete...")
        time.sleep(5)
        process_usb_device(config, state_manager, rsync_uploader, notifier)
    except Exception as e:
        logger.error(f"Error processing USB device on startup: {e}", exc_info=True)
        if config.notify_on_failure:
            notifier.send(success=False, files_uploaded=0,
                         total_files=state_manager.load().total_files_uploaded,
                         error_msg=f"Startup processing error: {str(e)}")

    # Listen for new events
    for device in iter(monitor.poll, None):
        if device.action == 'add':
            # Only process if device is on USB bus
            if not is_usb_device(device):
                logger.debug(f"Ignoring non-USB block device: {device.device_path}")
                continue

            logger.info(f"USB device added: {device.device_path}")
            # Give udisks a moment to mount the device
            time.sleep(3)
            try:
                process_usb_device(config, state_manager, rsync_uploader, notifier)
            except Exception as e:
                logger.error(f"Error processing USB device: {e}", exc_info=True)
                if config.notify_on_failure:
                    notifier.send(success=False, files_uploaded=0,
                                 total_files=state_manager.load().total_files_uploaded,
                                 error_msg=f"Error: {str(e)}")


def main():
    """Main entry point."""
    try:
        config = get_config()
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        sys.exit(1)

    # If run directly with arguments, process once and exit (for debugging)
    if len(sys.argv) > 1 and sys.argv[1] == '--once':
        state_path = os.path.join(config.install_dir, "state.json")
        state_manager = StateManager(state_path)
        rsync_uploader = RsyncUploader(config)
        notifier = DingTalkNotifier(config.dingtalk_webhook)
        process_usb_device(config, state_manager, rsync_uploader, notifier)
        return

    # Otherwise, start monitoring
    monitor_usb_devices(config)


if __name__ == "__main__":
    main()
