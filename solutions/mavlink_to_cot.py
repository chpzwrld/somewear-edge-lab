#!/usr/bin/env python3
"""
MODULE 2 SOLUTION - MAVLink to Cursor-on-Target (CoT) Gateway
Lesson: lessons/02-mavlink-to-cot.md

Goal: turn the drone's binary MAVLink position reports (arriving on UDP 14550)
into Cursor-on-Target XML that ATAK understands, and multicast it to the
TAK situational-awareness group 239.2.3.1:6969.

Fill in every block marked TODO (there are 4).
  Try it:       python3 course.py run 2
  Grade it:     python3 course.py check 2
  Stuck?        python3 course.py hint 2
"""
import math
import os
import socket
import time
from xml.sax.saxutils import quoteattr

from pymavlink import mavutil

TAK_MULTICAST_IP = "239.2.3.1"   # ATAK's default situational-awareness multicast group
TAK_PORT = 6969
UDP_INGEST_PORT = 14550          # where Module 1's bridge delivers MAVLink
CALLSIGN = os.environ.get("COT_CALLSIGN", "DRONE_RECON_01")
COT_TYPE = os.environ.get("COT_TYPE", "a-f-A-M-F-Q")   # friendly / air / military / fixed-wing / UAV
STALE_SECONDS = 30               # ATAK greys the icon out if no update arrives for this long


def convert_position(msg):
    """Converts a MAVLink GLOBAL_POSITION_INT message into everyday units.

    MAVLink sends whole numbers to save space:
        msg.lat, msg.lon  -> degrees  x 10,000,000   (e.g. 361234000 means 36.1234)
        msg.alt           -> millimeters above mean sea level (MSL)

    Returns a tuple: (lat_degrees, lon_degrees, alt_msl_meters)
    """
    # TODO 1: Convert the three values and return them as a tuple.
    #   Divide lat and lon by 1e7. Divide alt by 1000.0 (mm -> m).
    return (msg.lat / 1e7, msg.lon / 1e7, msg.alt / 1000.0)


def msl_to_hae(alt_msl, geoid_sep):
    """Converts altitude above mean sea level (MSL) to height above the
    WGS84 ellipsoid (HAE), which is what CoT expects.

    geoid_sep is (HAE - MSL) in meters, learned from the GPS. It is None
    until the first GPS_RAW_INT message arrives.
    """
    # TODO 2: If geoid_sep is None, we can't correct yet: return alt_msl unchanged.
    #   Otherwise return alt_msl + geoid_sep.
    if geoid_sep is None:
        return alt_msl
    return alt_msl + geoid_sep


def iso(ts):
    """Formats a Unix timestamp the way CoT wants: 2026-01-31T12:00:00.000Z (Provided.)"""
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(ts)) + f".{int(ts % 1 * 1000):03d}Z"


def generate_cot(lat, lon, hae, course=0.0, speed=0.0, callsign=CALLSIGN, cot_type=COT_TYPE):
    """Builds one Cursor-on-Target <event> as an XML string."""
    now = time.time()

    # TODO 3: Build the <point> element. It must look like this (one line):
    #     <point lat="36.1234000" lon="-115.1234000" hae="90.50" ce="5.0" le="5.0"/>
    #   Use an f-string. Format lat/lon with 7 decimals ({lat:.7f}) and hae with 2 ({hae:.2f}).
    #   ce/le are the position error estimates in meters - just use 5.0 for both.
    point = f'<point lat="{lat:.7f}" lon="{lon:.7f}" hae="{hae:.2f}" ce="5.0" le="5.0"/>'

    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<event version="2.0" uid={quoteattr(callsign)} type={quoteattr(cot_type)} '
        f'time="{iso(now)}" start="{iso(now)}" stale="{iso(now + STALE_SECONDS)}" how="m-g">\n'
        f'  {point}\n'
        '  <detail>\n'
        f'    <contact callsign={quoteattr(callsign)}/>\n'
        f'    <track course="{course:.1f}" speed="{speed:.2f}"/>\n'
        '  </detail>\n'
        '</event>'
    )


def create_cot_socket():
    """Creates a UDP socket set up for multicast. (Provided.)"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)   # cross at most 2 routers
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_LOOP, 1)  # let listeners on this machine hear it
    return sock


def send_cot(sock, cot_xml):
    """Sends one CoT XML string to the TAK multicast group."""
    # TODO 4: Send the XML to (TAK_MULTICAST_IP, TAK_PORT) with sock.sendto(...).
    #   Sockets send bytes, not text: convert first with cot_xml.encode("utf-8").
    sock.sendto(cot_xml.encode("utf-8"), (TAK_MULTICAST_IP, TAK_PORT))


def main():
    """Main loop. (Provided - it calls your functions above.)"""
    src = mavutil.mavlink_connection(f"udpin:127.0.0.1:{UDP_INGEST_PORT}")
    cot_sock = create_cot_socket()
    print(f"[*] Listening for MAVLink on udp://127.0.0.1:{UDP_INGEST_PORT}; "
          f"publishing CoT to {TAK_MULTICAST_IP}:{TAK_PORT}", flush=True)

    geoid_sep = None
    try:
        while True:
            msg = src.recv_match(type=["GLOBAL_POSITION_INT", "GPS_RAW_INT"], blocking=True, timeout=5)
            if msg is None:
                print("[!] No telemetry for 5s - is the bridge running?", flush=True)
                continue

            if msg.get_type() == "GPS_RAW_INT":
                # The GPS reports both MSL and ellipsoid altitude; the difference is the geoid separation.
                if getattr(msg, "alt_ellipsoid", 0):
                    geoid_sep = (msg.alt_ellipsoid - msg.alt) / 1000.0
                continue

            lat, lon, alt_msl = convert_position(msg)
            hae = msl_to_hae(alt_msl, geoid_sep)
            course = msg.hdg / 100.0 if msg.hdg != 65535 else 0.0   # centidegrees -> degrees
            speed = math.hypot(msg.vx, msg.vy) / 100.0              # cm/s -> m/s

            send_cot(cot_sock, generate_cot(lat, lon, hae, course, speed))
            print(f"[CoT Sent] Lat: {lat:.5f}, Lon: {lon:.5f}, HAE: {hae:.1f}m "
                  f"(MSL {alt_msl:.1f}m), Crs: {course:.0f}", flush=True)
    except KeyboardInterrupt:
        print("\n[*] Gateway stopped.")


if __name__ == "__main__":
    main()
