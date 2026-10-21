#!/usr/bin/env python3
"""
Flight Simulator Daemon (the drone mock).

Emulates an ArduPilot flight controller streaming MAVLink 2 over a virtual
serial port at /tmp/ttyDroneSim:
  - HEARTBEAT            @ 1 Hz
  - GLOBAL_POSITION_INT  @ 2 Hz  (lat/lon, alt MSL, velocity, heading)
  - GPS_RAW_INT          @ 2 Hz  (includes alt_ellipsoid = WGS84 HAE)
"""
import errno
import math
import os
import pty
import time
import tty

from pymavlink.dialects.v20 import ardupilotmega as mavlink2

SYMLINK_PATH = "/tmp/ttyDroneSim"
BASE_LAT, BASE_LON = 36.1234, -115.1234
# Simulated geoid separation (HAE - MSL). Roughly EGM96 for southern Nevada.
GEOID_SEPARATION_M = -30.0
ORBIT_DEG = 0.005          # orbit size in degrees
OMEGA = 0.02               # orbit angular rate, rad/s (~11 m/s, ~5 min per lap)
UPDATE_PERIOD = 0.5        # seconds between position reports (2 Hz)
M_PER_DEG = 111_320.0      # meters per degree of latitude


class PtyWriter:
    """File-like wrapper so the MAVLink encoder can write to the pty master.

    The master is non-blocking: if no reader is attached and the kernel
    buffer is full, frames are dropped instead of stalling the simulator
    (a real autopilot doesn't stop flying because nobody is listening).
    """

    def __init__(self, fd):
        self.fd = fd
        self.dropped = 0

    def write(self, buf):
        try:
            os.write(self.fd, buf)
        except BlockingIOError:
            self.dropped += 1
        except OSError as e:
            if e.errno not in (errno.EAGAIN, errno.EIO):
                raise
            self.dropped += 1


def run_sim():
    master, slave = pty.openpty()
    tty.setraw(slave)                # binary-safe: no CR/LF translation or echo
    os.set_blocking(master, False)
    port_name = os.ttyname(slave)    # keep `slave` open so writes never hit EIO

    if os.path.lexists(SYMLINK_PATH):
        os.remove(SYMLINK_PATH)
    os.symlink(port_name, SYMLINK_PATH)
    print(f"[*] Simulated Drone Telemetry running on {SYMLINK_PATH} -> {port_name}", flush=True)

    # The simulator writes to the MASTER end; consumers open the SLAVE end.
    mav = mavlink2.MAVLink(PtyWriter(master), srcSystem=1, srcComponent=1)

    angle = 0.0
    boot = time.time()
    last_hb = 0.0
    try:
        while True:
            now = time.time()
            boot_ms = int((now - boot) * 1000) & 0xFFFFFFFF

            if now - last_hb >= 1.0:
                mav.heartbeat_send(
                    mavlink2.MAV_TYPE_QUADROTOR,
                    mavlink2.MAV_AUTOPILOT_ARDUPILOTMEGA,
                    mavlink2.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED, 0,
                    mavlink2.MAV_STATE_ACTIVE,
                )
                last_hb = now

            # Orbit of 0.005 deg (~550 m N-S), altitude oscillating 110-130 m MSL
            lat_deg = BASE_LAT + ORBIT_DEG * math.sin(angle)
            lon_deg = BASE_LON + ORBIT_DEG * math.cos(angle)
            alt_msl = 120.0 + 10.0 * math.sin(angle)

            # Velocity = derivative of the orbit (m/s), so course/speed are consistent
            vn = M_PER_DEG * ORBIT_DEG * math.cos(angle) * OMEGA
            ve = -M_PER_DEG * math.cos(math.radians(BASE_LAT)) * ORBIT_DEG * math.sin(angle) * OMEGA
            vd = -10.0 * math.cos(angle) * OMEGA
            ground_speed = math.hypot(vn, ve)
            course = math.degrees(math.atan2(ve, vn)) % 360.0
            hdg_cdeg = int(course * 100) % 36000                # uint16, 0..35999

            # GPS first, so receivers learn the geoid separation before the first position
            mav.gps_raw_int_send(
                int(now * 1e6),
                3,                                        # 3D fix
                int(lat_deg * 1e7), int(lon_deg * 1e7),
                int(alt_msl * 1000),
                80, 120,                                  # eph, epv
                int(ground_speed * 100),                  # ground speed cm/s
                hdg_cdeg,
                14,                                       # satellites
                int((alt_msl + GEOID_SEPARATION_M) * 1000),  # alt_ellipsoid (mm HAE)
            )
            mav.global_position_int_send(
                boot_ms,
                int(lat_deg * 1e7), int(lon_deg * 1e7),
                int(alt_msl * 1000),     # mm MSL
                10000,                   # mm above home
                int(vn * 100), int(ve * 100), int(vd * 100),   # cm/s N/E/D
                hdg_cdeg,
            )

            angle = (angle + OMEGA * UPDATE_PERIOD) % (2 * math.pi)
            time.sleep(UPDATE_PERIOD)
    except KeyboardInterrupt:
        print("\n[*] Simulator stopped.")
    finally:
        if os.path.islink(SYMLINK_PATH) and os.readlink(SYMLINK_PATH) == port_name:
            os.remove(SYMLINK_PATH)


if __name__ == "__main__":
    run_sim()
