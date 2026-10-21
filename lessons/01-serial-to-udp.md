# Lesson 1 - Telemetry Ingest: the Serial-to-UDP Bridge

## The mission

You're at the launch point. The drone's autopilot is plugged into your edge device with a
serial cable, streaming telemetry. But the ground-control software (and Module 2's gateway)
listens on the **network**, at UDP port **14550**. Your job: build the bridge that moves
every byte from the cable to the network, untouched.

```
 autopilot ──serial cable──> /tmp/ttyDroneSim ──> YOUR BRIDGE ──UDP──> 127.0.0.1:14550
```

By the end of this lesson you'll understand serial ports, bytes, UDP sockets, and the basics
of MAVLink - and you'll have written a working bridge.

---

## Concept 1: Serial ports

A **serial port** sends data one bit after another down a wire - the oldest and simplest way
for two devices to talk. Autopilots, GPS units, radios and sensors almost all have one.

- On Linux a serial port looks like a file, e.g. `/dev/ttyUSB0` or `/dev/ttyACM0`.
- Both ends must agree on the speed, the **baud rate** (bits per second). Ours is `115200`.
  If the speeds don't match you get garbage.
- A serial port carries **raw bytes**. It has no idea what they mean.

In this lab there's no cable: the simulator creates a *virtual* serial port (a Linux
"pseudo-terminal") and publishes it at `/tmp/ttyDroneSim`. To your code it behaves exactly
like real hardware. In Python we use the **pyserial** library:

```python
import serial
port = serial.Serial("/dev/ttyUSB0", 9600, timeout=1.0)   # open: device path, baud rate
chunk = port.read(64)    # wait up to 1 s (the timeout), return up to 64 bytes
```

`read()` returns a **bytes** object. If nothing arrives before the timeout, it returns empty
bytes, `b""`.

## Concept 2: Bytes

Everything that travels over a wire or a network is **bytes** - numbers from 0 to 255.
Python shows them like `b"\xfd\x1c\x00..."` where `\xfd` means the byte with hex value FD
(253). Text is just bytes that happen to map to letters. MAVLink is *not* text, so a bridge
must never "decode" or change it - it passes the bytes through exactly as they came.

## Concept 3: MAVLink in a nutshell

**MAVLink** is the telemetry protocol used by ArduPilot and PX4 autopilots. It's binary and
compact - built for slow radio links. Every message is a small **packet**:

```
 FD  1C  00 00  2A  01 01  21 00 00  [ ...payload: the actual numbers... ]  [checksum]
 │   │   │      │   │  │   └ message ID (0x21 = 33 = GLOBAL_POSITION_INT)
 │   │   │      │   │  └ component ID
 │   │   │      │   └ system ID (which vehicle)
 │   │   │      └ sequence number (counts up; gaps = lost packets)
 │   │   └ two flag bytes (usually 00 00)
 │   └ payload length (0x1C = 28 bytes)
 └ start marker: every MAVLink 2 packet begins with byte 0xFD
```

Our simulated drone sends:

| Message | How often | Contents |
|---|---|---|
| `HEARTBEAT` | 1 per second | "I'm alive" + vehicle type (quadrotor) |
| `GLOBAL_POSITION_INT` | 2 per second | latitude, longitude, altitude, velocity, heading |
| `GPS_RAW_INT` | 2 per second | GPS fix quality, satellites, altitude (two ways) |

You don't decode MAVLink in this module - just move it. You'll decode it in Module 2.

## Concept 4: UDP in 60 seconds

Programs talk over a network through **sockets**. An address is an **IP + port**:

- **IP address** - which machine. `127.0.0.1` ("localhost", the loopback address) means
  *this same machine*: the data never leaves the computer.
- **Port** - which program on that machine (0-65535). MAVLink ground stations listen on
  **14550** by convention.

There are two main kinds of socket:

| | **TCP** (`SOCK_STREAM`) | **UDP** (`SOCK_DGRAM`) |
|---|---|---|
| Connection | must connect first | none - just send |
| Delivery | guaranteed, in order, retried | best effort, may be lost |
| Unit | a continuous stream | separate packets ("datagrams") |
| Good for | files, web pages | live telemetry, voice, video |

Telemetry uses **UDP**: if one position report is lost, the next one arrives half a second
later anyway - retrying an old position would just add delay.

In Python:

```python
import socket
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)   # AF_INET = IPv4, SOCK_DGRAM = UDP
s.sendto(b"hello", ("10.0.0.5", 9999))                 # send bytes to (ip, port)
```

---

## Explore (10 minutes)

**1. Start the drone.** In a terminal:

```bash
python3 simulator/flight_sim.py
```

It prints where its serial port is, then keeps running. Leave it.

**2. Listen to the serial port directly.** Open a *second* terminal (split icon) and run:

```bash
python3 tools/mav_inspect.py --serial
```

You're seeing the drone's messages, decoded. Notice the raw values like `lat=361236498` -
remember that for Module 2. Press `Ctrl+C` to stop.

**3. See the actual bytes.**

```bash
python3 tools/mav_inspect.py --serial --raw
```

Find the `fd` at the start of each packet. That's all a bridge ever sees: bytes. `Ctrl+C`
to stop, then stop the simulator in the first terminal with `Ctrl+C` too.

> Only one program should read a serial port at a time - each byte goes to whoever reads it
> first. That's why you stop the inspector before running your bridge.

---

## Your task

Open **`exercises/bridge_serial_udp.py`**. The program is mostly written; you fill in
three `TODO`s. Read the whole file first - the comments explain each piece.

**TODO 1 - `create_udp_socket()`**: create and return a UDP socket (IPv4). One line.

**TODO 2 - read**: in `forward()`, read up to `CHUNK_SIZE` bytes from the serial port into
`data`.

**TODO 3 - send**: if `data` isn't empty, send it to `(UDP_TARGET_IP, UDP_TARGET_PORT)` and
return the number of bytes sent. If it is empty, the function falls through to `return 0`.

`run_bridge()` at the bottom (already written) calls your functions over and over.

### Try it

```bash
python3 course.py run 1
```

This starts the simulator and *your* bridge, then shows whatever arrives on UDP 14550. If you
see `HEARTBEAT` and `GLOBAL_POSITION_INT` messages scrolling, your bridge works. `Ctrl+C` to
stop. If something's wrong, the bridge's error output is in `/tmp/edge-course/bridge.log`.

### Check it

```bash
python3 course.py check 1
```

The grader tests each TODO on its own, then runs the full pipeline end to end.

---

## Knowledge check

1. Why does a bridge forward the bytes unchanged instead of decoding them first?
2. Your bridge works but the ground station shows nothing. It's listening on port 14551.
   What's wrong?
3. Why is UDP a better fit than TCP for live telemetry?
4. `ser.read(512)` returned `b""`. What does that tell you?

<details><summary>Answers</summary>

1. Decoding would be wasted work and risks changing the data. The bridge's only job is
   transport - the receiver (Module 2, or a ground station) does the decoding.
2. The ports don't match. Sender and receiver must agree on IP *and* port.
3. Old positions are worthless once newer ones exist. TCP would stall and retransmit lost
   data, adding delay; UDP keeps the stream live and the next packet replaces a lost one.
4. No data arrived within the 1-second timeout - the drone isn't sending, the simulator
   isn't running, or the cable/baud rate is wrong.

</details>

## In the field

- Real devices appear as `/dev/ttyUSB0`, `/dev/ttyACM0` or `/dev/serial0`. Check
  `ls /dev/tty*` before and after plugging in.
- The #1 serial problem is a **baud-rate mismatch** (ArduPilot telemetry ports commonly use
  57600 or 115200). Wrong baud = garbage bytes, no valid packets.
- Port **14550** is where common ground stations (such as QGroundControl and Mission Planner)
  listen for MAVLink by default.
- Production systems often use tools like `mavlink-router` or MAVProxy, which do exactly
  what you just built - plus routing to several destinations.

## Bonus challenges

1. Make the bridge send to **two** destinations (e.g. ports 14550 and 14551).
2. Count packets as well as bytes: count the `0xFD` start bytes in each chunk.
3. Make `UDP_TARGET_IP` configurable with an environment variable (look at how
   `mavlink_to_cot.py` reads `COT_CALLSIGN`).

**Next:** `python3 course.py lesson 2`
