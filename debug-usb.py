#!/usr/bin/env python3
import psutil
import pyudev
import os

print("=== USB Device Debug Info ===\n")

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
    print()

# 3. Test UsbDetector filtering
from utils import UsbDetector
print("\n3. Filtered USB mount points (what the program sees):")
print("-" * 50)
usb_mounts = UsbDetector.get_mount_points()
print(f"Found {len(usb_mounts)} USB mount points:")
for mp in usb_mounts:
    print(f"  {mp}")

print("\n=== Debug complete ===")
print("\nInsert your USB and run this script again to see if it's detected:")
print(f"  sudo {os.path.abspath('debug-usb.py')}")
print("\nThen send me the output and I'll fix the detection.")
