#!/usr/bin/env python3
"""Grader for Module 1 (Serial-to-UDP bridge).

Usage: python3 tests/test_m1.py [path/to/bridge_serial_udp.py]
(defaults to exercises/bridge_serial_udp.py - normally run via: python3 course.py check 1)
"""
import errno
import socket
import sys
import time

from grading import (COURSE_PROCS, ROOT, Background, Fail, call, info, kill_stale, load_module,
                     ok, run_grader, step)
from pymavlink.dialects.v20 import ardupilotmega as mavlink2

TARGET = sys.argv[1] if len(sys.argv) > 1 else str(ROOT / "exercises" / "bridge_serial_udp.py")
PORT = 14550
TOTAL = 4


class FakeSerial:
    """Pretends to be a serial port that returns preset chunks of bytes."""

    def __init__(self, *chunks):
        self.chunks = list(chunks)
        self.read_sizes = []

    def read(self, n):
        self.read_sizes.append(n)
        return self.chunks.pop(0) if self.chunks else b""


def bind_listener():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.bind(("127.0.0.1", PORT))
    except OSError as e:
        if e.errno == errno.EADDRINUSE:
            raise Fail(f"UDP port {PORT} is already in use by another program.",
                       hint="Stop anything else that's running (Ctrl+C in other terminals), "
                            "especially your Module 2 gateway, then check again.")
        raise
    sock.settimeout(1.0)
    return sock


def drain(sock):
    sock.setblocking(False)
    try:
        while True:
            sock.recvfrom(4096)
    except BlockingIOError:
        pass
    finally:
        sock.settimeout(1.0)


def steps():
    kill_stale(*COURSE_PROCS)
    listener = bind_listener()

    step(1, TOTAL, "Loading your bridge code")
    mod = load_module(TARGET)
    ok(f"{TARGET.split('/')[-1]} loads without errors")

    step(2, TOTAL, "TODO 1 - create_udp_socket()")
    sock = call("create_udp_socket", mod.create_udp_socket)
    if sock is None:
        raise Fail("create_udp_socket() returned None.",
                   hint="Replace `return None` with code that creates and returns a socket: "
                        "socket.socket(<family>, <type>)")
    if not isinstance(sock, socket.socket):
        raise Fail(f"create_udp_socket() returned a {type(sock).__name__}, not a socket.")
    if sock.family != socket.AF_INET:
        raise Fail("Your socket isn't using IPv4.", hint="The first argument should be socket.AF_INET")
    if sock.type != socket.SOCK_DGRAM:
        raise Fail("Your socket is not a UDP socket (it looks like TCP).",
                   hint="UDP sockets use socket.SOCK_DGRAM as the second argument "
                        "(SOCK_STREAM would be TCP).")
    ok("returns an IPv4 UDP socket")

    step(3, TOTAL, "TODO 2 & 3 - forward()")
    drain(listener)
    payload = b"\xfd\x09MAVLINK-TEST-BYTES\x00\xff"
    fake = FakeSerial(payload)
    sent = call("forward", mod.forward, fake, sock)
    if not fake.read_sizes:
        raise Fail("forward() never read from the serial port.",
                   hint="TODO 2: use ser.read(CHUNK_SIZE) to get the bytes.")
    if fake.read_sizes[0] != mod.CHUNK_SIZE:
        info(f"(note: you read {fake.read_sizes[0]} bytes at a time; CHUNK_SIZE is {mod.CHUNK_SIZE})")
    try:
        got, _ = listener.recvfrom(4096)
    except socket.timeout:
        raise Fail(f"forward() read the data but nothing arrived on UDP {PORT}.",
                   hint="TODO 3: send it with sock.sendto(data, (UDP_TARGET_IP, UDP_TARGET_PORT))")
    if got != payload:
        raise Fail(f"The bytes changed on the way: sent {payload!r}, received {got!r}.",
                   hint="A bridge must forward the bytes exactly as read - don't decode, "
                        "strip or convert them.")
    if sent != len(payload):
        raise Fail(f"forward() returned {sent!r}; it should return the number of bytes sent "
                   f"({len(payload)}).", hint="TODO 3: after sendto(...), return len(data)")
    ok("forwards the exact bytes it reads and returns the byte count")

    empty_sent = call("forward", mod.forward, FakeSerial(b""), sock)
    try:
        listener.recvfrom(4096)
        raise Fail("forward() sent an empty packet when the serial port had no data.",
                   hint="TODO 3: only send when `data` is not empty (if data: ...)")
    except socket.timeout:
        pass
    if empty_sent != 0:
        raise Fail(f"With no data, forward() should return 0 but returned {empty_sent!r}.")
    ok("does nothing when no data arrives (returns 0)")

    step(4, TOTAL, "End to end - simulator -> your bridge -> UDP 14550")
    drain(listener)
    with Background() as bg:
        bg.start("simulator", [sys.executable, "simulator/flight_sim.py"])
        bg.start("bridge", [sys.executable, TARGET])
        parser = mavlink2.MAVLink(None)
        parser.robust_parsing = True
        seen, nbytes = set(), 0
        deadline = time.time() + 8
        while time.time() < deadline and not {"HEARTBEAT", "GLOBAL_POSITION_INT"} <= seen:
            try:
                data, _ = listener.recvfrom(4096)
            except socket.timeout:
                continue
            nbytes += len(data)
            for m in parser.parse_buffer(data) or []:
                if m.get_type() != "BAD_DATA":
                    seen.add(m.get_type())
        if not nbytes:
            raise Fail("Your bridge ran, but no data arrived on UDP 14550 within 8 seconds.\n"
                       "       Bridge output:\n" + bg.log_tail("bridge"))
        if "GLOBAL_POSITION_INT" not in seen:
            raise Fail(f"Data arrived ({nbytes} bytes) but it isn't valid MAVLink.",
                       hint="Forward the raw bytes unchanged.")
    ok(f"received {nbytes} bytes of valid MAVLink: {', '.join(sorted(seen))}")


if __name__ == "__main__":
    run_grader("Module 1: Serial-to-UDP Bridge", steps)
