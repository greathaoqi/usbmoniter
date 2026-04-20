#!/usr/bin/env python3
# Run with virtualenv python:
# /opt/usb-photo-upload/venv/bin/python3 debug-usb.py

import psutil
import pyudev
import os
import sys

INSTALL_DIR = os.path.dirname(os.path.abspath(__file__))
VENV_DIR = os.path.join(INSTALL_DIR, "venv")

print("=== USB Device Debug Info ===\n")
print(f"Python: {sys.executable}")
print()

# 1. Print all disk partitions
print("1. All mounted partitions:")
print("-" * 50)
for partition in psutil.disk_partitions():
    print(f"  Device: {partition.device}")
    print(f"  Mountpoint: {partition.mountpoint}")
    print(f"  Fstype: {partition.fstype}")
    print()

# 2. Print all block devices via pyudev
print("\n2. All block devices (via pyudev):")
print("-" * 50)
context = pyudev.Context()
for device in context.list_devices(subsystem='block'):
    id_bus = device.get('ID_BUS')
    devtype = device.get('DEVTYPE')
    devpath = device.get('DEVPATH')
    device_node = device.device_node
    print(f"  Device node: {device_node}")
    print(f"  DEVTYPE: {devtype}")
    print(f"  ID_BUS: {id_bus}")
    print(f"  DEVPATH: {devpath}")
    if device.parent:
        print(f"  Parent: {device.parent.device_node}")
        parent_id_bus = device.parent.get('ID_BUS')
        print(f"  Parent ID_BUS: {parent_id_bus}")
    print()

# 3. Test UsbDetector filtering
sys.path.insert(0, INSTALL_DIR)
from utils import UsbDetector
print("\n3. Filtered USB mount points (what the program sees):")
print("-" * 50)
usb_mounts = UsbDetector.get_mount_points()
print(f"Found {len(usb_mounts)} USB mount points:")
for mp in usb_mounts:
    print(f"  {mp}")

print("\n=== Debug complete ===")
print("\nInsert your USB and run this script again to see if it's detected:")
print(f"  sudo {sys.executable} {os.path.abspath(__file__)}")
print("\nIf using virtual environment (installed by installer):")
print(f"  sudo /opt/usb-photo-upload/venv/bin/python3 {os.path.abspath(__file__)}")
print("\nThen send me the output and I'll fix the detection.")
