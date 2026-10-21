#!/usr/bin/env python3
"""
MAVLink Inspector - see what the drone is saying.

  python3 tools/mav_inspect.py                 # decode MAVLink arriving on UDP 14550 (after your bridge)
  python3 tools/mav_inspect.py --serial        # decode straight from the serial port (no bridge needed)
  python3 tools/mav_inspect.py --serial --raw  # also show the raw bytes in hex
  python3 tools/mav_inspect.py --type GLOBAL_POSITION_INT   # only one message type

Press Ctrl+C to stop.
"""
import argparse
import signal
import socket
import time

from pymavlink.dialects.v20 import ardupilotmega as mavlink2


def describe(m):
    t = m.get_type()
    if t == "HEARTBEAT":
        return (f"type={mavlink2.enums['MAV_TYPE'][m.type].name}  "
                f"autopilot={mavlink2.enums['MAV_AUTOPILOT'][m.autopilot].name}")
    if t == "GLOBAL_POSITION_INT":
        return (f"lat={m.lat} lon={m.lon} alt={m.alt}  ->  {m.lat / 1e7:.5f}, {m.lon / 1e7:.5f}, "
                f"{m.alt / 1000:.1f} m MSL   hdg={m.hdg / 100:.0f} deg")
    if t == "GPS_RAW_INT":
        return (f"fix={m.fix_type} sats={m.satellites_visible}  alt(MSL)={m.alt / 1000:.1f} m  "
                f"alt(ellipsoid)={m.alt_ellipsoid / 1000:.1f} m")
    return str(m.to_dict())


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--serial", action="store_true", help="read /tmp/ttyDroneSim directly")
    ap.add_argument("--raw", action="store_true", help="print raw bytes as hex")
    ap.add_argument("--type", help="only show this message type, e.g. HEARTBEAT")
    args = ap.parse_args()

    if args.serial:
        import serial
        ser = serial.Serial("/tmp/ttyDroneSim", 115200, timeout=1.0)
        ser.reset_input_buffer()
        read = lambda: ser.read(512)
        print("[*] Reading MAVLink directly from serial /tmp/ttyDroneSim (Ctrl+C to stop)")
    else:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(("127.0.0.1", 14550))
        sock.settimeout(1.0)

        def read():
            try:
                return sock.recvfrom(4096)[0]
            except socket.timeout:
                return b""
        print("[*] Listening for MAVLink on UDP 127.0.0.1:14550 (Ctrl+C to stop)")

    parser = mavlink2.MAVLink(None)
    parser.robust_parsing = True
    counts, quiet_since = {}, time.time()
    try:
        while True:
            data = read()
            if not data:
                if time.time() - quiet_since > 3:
                    print("    ...no data yet (is the simulator running? is the bridge running?)")
                    quiet_since = time.time()
                continue
            quiet_since = time.time()
            if args.raw:
                print(f"  raw {len(data):3d} bytes: {data[:48].hex(' ')}{' ...' if len(data) > 48 else ''}")
            for m in parser.parse_buffer(data) or []:
                t = m.get_type()
                if t == "BAD_DATA" or (args.type and t != args.type):
                    continue
                counts[t] = counts.get(t, 0) + 1
                print(f"  {t:<20} #{counts[t]:<4} {describe(m)}")
    except KeyboardInterrupt:
        print("\n[*] Message counts:", counts or "none")


if __name__ == "__main__":
    signal.signal(signal.SIGPIPE, signal.SIG_DFL)   # exit quietly if output is piped to e.g. head
    main()
