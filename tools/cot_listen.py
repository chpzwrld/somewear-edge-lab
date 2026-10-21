#!/usr/bin/env python3
"""
CoT Listener - a stand-in for an ATAK tablet.

Joins the TAK situational-awareness multicast group (239.2.3.1:6969) and prints
every Cursor-on-Target track it hears, the way ATAK would place it on the map.

  python3 tools/cot_listen.py         # one summary line per track update
  python3 tools/cot_listen.py --xml   # also print the full XML

Press Ctrl+C to stop.
"""
import argparse
import signal
import socket
import struct
import time

from defusedxml import ElementTree as ET   # safe parsing for untrusted network data

GROUP, PORT = "239.2.3.1", 6969


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--xml", action="store_true", help="print the full XML of each event")
    args = ap.parse_args()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("", PORT))
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP,
                    struct.pack("=4s4s", socket.inet_aton(GROUP), socket.inet_aton("0.0.0.0")))
    sock.settimeout(3.0)
    print(f"[*] 'ATAK' listening on {GROUP}:{PORT} (Ctrl+C to stop)")

    n = 0
    try:
        while True:
            try:
                data, sender = sock.recvfrom(8192)
            except socket.timeout:
                print("    ...no CoT yet (is your gateway running?)")
                continue
            n += 1
            try:
                ev = ET.fromstring(data)
                pt = ev.find("point")
                contact = ev.find("detail/contact")
                track = ev.find("detail/track")
                print(f"  #{n:<4} {time.strftime('%H:%M:%S')}  "
                      f"{(contact.get('callsign') if contact is not None else ev.get('uid'))}  "
                      f"[{ev.get('type')}]  {float(pt.get('lat')):.5f}, {float(pt.get('lon')):.5f}  "
                      f"HAE {float(pt.get('hae')):.1f} m"
                      + (f"  course {float(track.get('course')):.0f}  speed {float(track.get('speed')):.1f} m/s"
                         if track is not None else ""))
            except Exception as e:
                print(f"  #{n:<4} could not read this CoT ({type(e).__name__}: {e})")
            if args.xml:
                print(data.decode(errors="replace"), "\n")
    except KeyboardInterrupt:
        print(f"\n[*] Received {n} CoT events.")


if __name__ == "__main__":
    signal.signal(signal.SIGPIPE, signal.SIG_DFL)   # exit quietly if output is piped to e.g. head
    main()
