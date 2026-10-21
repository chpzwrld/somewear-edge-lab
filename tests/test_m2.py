#!/usr/bin/env python3
"""Grader for Module 2 (MAVLink -> Cursor-on-Target gateway).

Usage: python3 tests/test_m2.py [path/to/mavlink_to_cot.py]
(defaults to exercises/mavlink_to_cot.py - normally run via: python3 course.py check 2)
The end-to-end step uses the reference Module 1 bridge, so this module can be
graded on its own.
"""
import socket
import struct
import sys
from datetime import datetime
from types import SimpleNamespace

from defusedxml import ElementTree as ET   # safe XML parsing for data from the network
from grading import (COURSE_PROCS, ROOT, Background, Fail, call, kill_stale, load_module, ok,
                     run_grader, step)

TARGET = sys.argv[1] if len(sys.argv) > 1 else str(ROOT / "exercises" / "mavlink_to_cot.py")
MCAST_GROUP, PORT = "239.2.3.1", 6969
TOTAL = 6


def close(a, b, tol=1e-6):
    return isinstance(a, (int, float)) and abs(a - b) <= tol


def validate_cot(xml_bytes):
    """Returns (root, problems). problems is empty when the XML is a valid CoT track."""
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as e:
        return None, [f"the XML can't be parsed: {e}"]
    problems = []
    if root.tag != "event":
        return root, [f"root element is <{root.tag}>, expected <event>"]
    for attr in ("version", "uid", "type", "time", "start", "stale", "how"):
        if not root.get(attr):
            problems.append(f"<event> is missing the '{attr}' attribute")
    try:
        t = lambda s: datetime.fromisoformat(s.replace("Z", "+00:00"))
        if t(root.get("stale")) <= t(root.get("time")):
            problems.append("stale time is not after the event time")
    except Exception as e:
        problems.append(f"bad timestamp: {e}")
    point = root.find("point")
    if point is None:
        problems.append("there is no <point> element")
    else:
        for attr in ("lat", "lon", "hae", "ce", "le"):
            try:
                float(point.get(attr))
            except (TypeError, ValueError):
                problems.append(f"<point> attribute '{attr}' is missing or not a number")
    if root.find("detail/contact") is None:
        problems.append("missing <detail><contact callsign=...>")
    return root, problems


def multicast_listener(timeout=3.0):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("", PORT))
    mreq = struct.pack("=4s4s", socket.inet_aton(MCAST_GROUP), socket.inet_aton("0.0.0.0"))
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
    sock.settimeout(timeout)
    return sock


def steps():
    kill_stale(*COURSE_PROCS)

    step(1, TOTAL, "Loading your gateway code")
    mod = load_module(TARGET)
    ok(f"{TARGET.split('/')[-1]} loads without errors")

    step(2, TOTAL, "TODO 1 - convert_position()")
    msg = SimpleNamespace(lat=361234000, lon=-1151234000, alt=120500)
    res = call("convert_position", mod.convert_position, msg)
    if not isinstance(res, tuple) or len(res) != 3:
        raise Fail(f"convert_position() should return a tuple of 3 numbers, got {res!r}.",
                   hint="return (lat, lon, alt) - three values separated by commas")
    lat, lon, alt = res
    if res == (0.0, 0.0, 0.0):
        raise Fail("convert_position() still returns the placeholder (0.0, 0.0, 0.0).",
                   hint="Use msg.lat, msg.lon and msg.alt to compute real values.")
    if not (close(lat, 36.1234) and close(lon, -115.1234)):
        raise Fail(f"For lat=361234000, lon=-1151234000 you returned lat={lat!r}, lon={lon!r}; "
                   "expected 36.1234 and -115.1234.",
                   hint="MAVLink stores degrees x 10,000,000 - divide by 1e7.")
    if not close(alt, 120.5):
        raise Fail(f"For alt=120500 (millimeters) you returned {alt!r}; expected 120.5 meters.",
                   hint="Divide millimeters by 1000.0 to get meters.")
    ok("36.1234, -115.1234, 120.5 m - units converted correctly")

    step(3, TOTAL, "TODO 2 - msl_to_hae()")
    v = call("msl_to_hae", mod.msl_to_hae, 120.5, None)
    if not close(v, 120.5):
        raise Fail(f"msl_to_hae(120.5, None) returned {v!r}; with no geoid data it should "
                   "return the altitude unchanged (120.5).",
                   hint="if geoid_sep is None: return alt_msl")
    v = call("msl_to_hae", mod.msl_to_hae, 120.5, -30.0)
    if not close(v, 90.5):
        raise Fail(f"msl_to_hae(120.5, -30.0) returned {v!r}; expected 90.5.",
                   hint="HAE = MSL + geoid separation")
    ok("handles both 'no geoid data yet' and the corrected case")

    step(4, TOTAL, "TODO 3 - generate_cot() <point> element")
    xml = call("generate_cot", mod.generate_cot, 36.1234, -115.1234, 90.5, 45.0, 11.0)
    if not isinstance(xml, str):
        raise Fail(f"generate_cot() should return a string, got {type(xml).__name__}.")
    root, problems = validate_cot(xml.encode())
    if problems:
        raise Fail("The CoT XML isn't valid yet: " + "; ".join(problems) + ".",
                   hint='TODO 3: point = f\'<point lat="{lat:.7f}" ... />\' - check the quotes, '
                        "and that the element ends with />")
    p = root.find("point")
    got = (float(p.get("lat")), float(p.get("lon")), float(p.get("hae")))
    if not (close(got[0], 36.1234) and close(got[1], -115.1234) and close(got[2], 90.5, 0.01)):
        raise Fail(f"<point> has lat/lon/hae = {got}, expected (36.1234, -115.1234, 90.5).",
                   hint="Make sure each attribute uses the matching variable.")
    ok("produces a valid CoT event with the right coordinates")

    step(5, TOTAL, "TODO 4 - send_cot() to the TAK multicast group")
    listener = multicast_listener()
    sender = mod.create_cot_socket()
    call("send_cot", mod.send_cot, sender, xml)
    try:
        data, _ = listener.recvfrom(8192)
    except socket.timeout:
        raise Fail(f"Nothing arrived on {MCAST_GROUP}:{PORT}.",
                   hint="TODO 4: sock.sendto(cot_xml.encode(\"utf-8\"), (TAK_MULTICAST_IP, TAK_PORT))")
    if data.decode(errors="replace") != xml:
        raise Fail("A packet arrived but it isn't the XML that was passed to send_cot().")
    ok(f"the XML arrives on {MCAST_GROUP}:{PORT}")

    step(6, TOTAL, "End to end - simulator -> bridge -> your gateway -> ATAK multicast")
    listener.settimeout(8.0)
    with Background() as bg:
        bg.start("simulator", [sys.executable, "simulator/flight_sim.py"])
        bg.start("bridge", [sys.executable, "solutions/bridge_serial_udp.py"])
        bg.start("gateway", [sys.executable, TARGET], settle=2.5)
        try:
            data, _ = listener.recvfrom(8192)
        except socket.timeout:
            raise Fail("Your gateway is running but no CoT arrived within 8 seconds.\n"
                       "       Gateway output:\n" + bg.log_tail("gateway"))
    root, problems = validate_cot(data)
    if problems:
        raise Fail("Received CoT from the live stream, but: " + "; ".join(problems))
    p = root.find("point")
    lat, lon = float(p.get("lat")), float(p.get("lon"))
    if not (36.0 < lat < 36.3 and -115.3 < lon < -115.0):
        raise Fail(f"Live track is at {lat}, {lon} - the simulated drone flies near 36.12, -115.12.")
    ok(f"live track {root.get('uid')} at {lat:.5f}, {lon:.5f}, HAE {float(p.get('hae')):.1f} m")


if __name__ == "__main__":
    run_grader("Module 2: MAVLink to Cursor-on-Target Gateway", steps)
