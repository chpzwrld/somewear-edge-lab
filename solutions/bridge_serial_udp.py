#!/usr/bin/env python3
"""
MODULE 1 SOLUTION - Serial-to-UDP Telemetry Bridge
Lesson: lessons/01-serial-to-udp.md

Goal: read raw bytes from the drone's serial port and forward them,
unchanged, to UDP 127.0.0.1:14550.

Fill in every block marked TODO (there are 3).
  Try it:       python3 course.py run 1
  Grade it:     python3 course.py check 1
  Stuck?        python3 course.py hint 1
"""
import socket
import sys
import time

import serial   # the "pyserial" library: talks to serial ports

SERIAL_PORT = "/tmp/ttyDroneSim"   # created by simulator/flight_sim.py
BAUD_RATE = 115200                 # serial speed in bits per second
UDP_TARGET_IP = "127.0.0.1"        # "localhost" - this same machine
UDP_TARGET_PORT = 14550            # the standard MAVLink ground-station port
CHUNK_SIZE = 512                   # max bytes to read from serial at a time


def open_serial():
    """Opens the serial port, retrying until the simulator is running. (Provided.)"""
    while True:
        try:
            ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1.0)
            ser.reset_input_buffer()   # throw away old bytes that queued up before we connected
            return ser
        except (serial.SerialException, OSError) as e:
            print(f"[!] Cannot open {SERIAL_PORT} ({e}). Is the simulator running? Retrying...",
                  flush=True)
            time.sleep(2)


def create_udp_socket():
    """Creates and returns a UDP socket."""
    # TODO 1: Create a UDP socket and return it.
    #   A socket needs two settings:
    #     - address family: socket.AF_INET    (IPv4 addresses like 127.0.0.1)
    #     - socket type:    socket.SOCK_DGRAM (datagrams = UDP)
    return socket.socket(socket.AF_INET, socket.SOCK_DGRAM)


def forward(ser, sock):
    """Reads one chunk from the serial port and sends it over UDP.

    Returns the number of bytes forwarded (0 if nothing arrived).
    """
    # TODO 2: Read up to CHUNK_SIZE bytes from the serial port.
    #   ser.read(n) waits up to 1 second and returns a `bytes` object.
    #   It may be empty (b"") if no data arrived in time.
    data = ser.read(CHUNK_SIZE)

    # TODO 3: If `data` is not empty:
    #     - send it to (UDP_TARGET_IP, UDP_TARGET_PORT) with sock.sendto(...)
    #     - return how many bytes you sent: len(data)
    if data:
        sock.sendto(data, (UDP_TARGET_IP, UDP_TARGET_PORT))
        return len(data)

    return 0


def run_bridge():
    """Main loop. (Provided - it calls your functions above.)"""
    sock = create_udp_socket()
    if sock is None:
        sys.exit("[!] create_udp_socket() returned None - finish TODO 1 first.")
    print(f"Connecting to {SERIAL_PORT}...", flush=True)
    ser = open_serial()
    print(f"[+] Bridging {SERIAL_PORT} -> udp://{UDP_TARGET_IP}:{UDP_TARGET_PORT}", flush=True)

    total, last_report = 0, time.time()
    try:
        while True:
            total += forward(ser, sock)
            if time.time() - last_report >= 5:          # progress report every 5 seconds
                print(f"[*] Forwarded {total} bytes so far", flush=True)
                last_report = time.time()
    except KeyboardInterrupt:
        print(f"\n[*] Bridge stopped. Forwarded {total} bytes.")


if __name__ == "__main__":
    run_bridge()
