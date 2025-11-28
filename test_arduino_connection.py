#!/usr/bin/env python3
"""Simple script to test Arduino connection"""
import serial
import serial.tools.list_ports
import time

print("Available serial ports:")
ports = list(serial.tools.list_ports.comports())
if not ports:
    print("  No ports found!")
else:
    for p in ports:
        print(f"  {p.device} - {p.description}")

if ports:
    print("\nTesting connection to first port...")
    port = ports[0].device
    try:
        print(f"Opening {port}...")
        conn = serial.Serial(port, 9600, timeout=1, write_timeout=3)
        print(f"✓ Connection opened!")
        
        time.sleep(2)  # Wait for Arduino to initialize
        print("Sending test command...")
        conn.write(b'CAM:ACTIVE\n')
        conn.flush()
        print("✓ Command sent!")
        
        time.sleep(1)
        conn.close()
        print("✓ Connection closed successfully")
    except Exception as e:
        print(f"✗ Error: {e}")

