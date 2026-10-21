# Lesson 2 - MAVLink to Cursor-on-Target: the Gateway

## The mission

Your bridge now delivers raw MAVLink to UDP 14550. But the ATAK tablets on the network can't
read MAVLink - they speak **Cursor-on-Target (CoT)**. You'll build the **gateway** that
decodes each position report, converts it into a CoT event, and broadcasts it so every ATAK
device on the network sees the drone on its map.

```
 UDP 14550 ──> YOUR GATEWAY ──> decode MAVLink ──> convert units ──> CoT XML ──> 239.2.3.1:6969 ──> ATAK
```

---

## Concept 1: Reading MAVLink numbers

To keep packets small, MAVLink avoids decimals. It sends **scaled whole numbers**, and you
convert them back:

| Field (GLOBAL_POSITION_INT) | Raw example | Unit | To get everyday units |
|---|---|---|---|
| `lat` | `361234000` | degrees x 10^7 | divide by `1e7` -> `36.1234` deg |
| `lon` | `-1151234000` | degrees x 10^7 | divide by `1e7` -> `-115.1234` deg |
| `alt` | `120500` | millimeters (above mean sea level) | divide by `1000` -> `120.5` m |
| `vx`, `vy` | `1100` | cm/s (north, east) | divide by `100` -> m/s |
| `hdg` | `35700` | centidegrees | divide by `100` -> `357` deg |

`1e7` is Python for 10,000,000. Seven decimal places of a degree is about 1 cm - more than
enough precision.

You saw these raw values in Lesson 1's explore step. In this module the `pymavlink` library
does the decoding for you: each message becomes an object, so you just write `msg.lat`.

## Concept 2: Cursor-on-Target (CoT)

CoT is the message format of the TAK ecosystem (ATAK on Android, WinTAK, iTAK, TAK Server).
Every CoT message is one XML **event** describing one thing - a friendly unit, a drone, a
marker:

```xml
<event version="2.0" uid="DRONE_RECON_01" type="a-f-A-M-F-Q"
       time="2026-01-31T12:00:00.000Z" start="2026-01-31T12:00:00.000Z"
       stale="2026-01-31T12:00:30.000Z" how="m-g">
  <point lat="36.1234000" lon="-115.1234000" hae="90.50" ce="5.0" le="5.0"/>
  <detail>
    <contact callsign="DRONE_RECON_01"/>
    <track course="357.0" speed="11.10"/>
  </detail>
</event>
```

| Part | Meaning |
|---|---|
| `uid` | unique ID. Same uid = same icon, so updates *move* it instead of adding a new one |
| `type` | what it is, coded (below) |
| `time` / `start` / `stale` | when sent / valid from / when to grey it out if no update arrives |
| `how` | how the position was obtained: `m-g` = machine, GPS |
| `<point>` | the location: `lat`, `lon`, `hae` (height, see Concept 3), `ce`/`le` = error in meters |
| `<contact callsign>` | the name shown on the map |
| `<track>` | direction of travel (degrees) and speed (m/s) - ATAK draws a heading line |

**Reading the type code** `a-f-A-M-F-Q` (based on MIL-STD-2525 symbology):
`a` = atom (a real thing) · `f` = friendly (`h` hostile, `n` neutral, `u` unknown) ·
`A` = air · `M` = military · `F` = fixed wing · `Q` = drone/UAV.
Change one letter and the map symbol changes - `a-h-A-M-F-Q` would show a *hostile* drone.

**XML basics:** elements look like `<name attribute="value">...</name>`, or self-closing
`<name attribute="value"/>`. Attribute values must be in quotes. One missing quote or `/`
and the whole message is unreadable.

## Concept 3: Which altitude? MSL vs HAE

"Altitude" depends on what you measure from:

- **MSL** - height above *mean sea level*. What pilots and MAVLink's `alt` use.
- **HAE** - height above the *ellipsoid*: the smooth mathematical model of Earth that GPS
  (WGS84) is built on. **CoT's `hae` attribute requires this.**

The difference between them is the **geoid separation**, and it changes with location
(around -30 m in southern Nevada, where our drone flies). Mix them up and a drone flying at
120 m MSL appears 30 m too high on every map - a real problem for deconfliction.

Conveniently, the drone's `GPS_RAW_INT` message reports *both* heights, so the gateway learns
the separation: `geoid_sep = alt_ellipsoid - alt_msl`, and then `HAE = MSL + geoid_sep`.
That code is already in `main()`; you'll write the conversion function.

## Concept 4: Multicast

So far you've sent to one address (**unicast**). ATAK devices discover each other with
**multicast**: you send *one* packet to a special **group address**, and every device that
has joined that group receives it - like a radio channel.

- Multicast addresses are in the range `224.0.0.0` - `239.255.255.255`.
- ATAK's default situational-awareness group is **`239.2.3.1` port `6969`**.
- **TTL** (time to live) limits how many routers the packets may cross - we use 2, so they
  stay on the local network.

Sending to a multicast group uses the same `sendto()` you used in Module 1.

---

## Explore (10 minutes)

**1. See the raw position numbers.** Start the simulator in one terminal:

```bash
python3 simulator/flight_sim.py
```

In a second terminal, show just the position messages:

```bash
python3 tools/mav_inspect.py --serial --type GLOBAL_POSITION_INT
```

Compare the raw `lat=...` with the converted value printed next to it. Then try
`--type GPS_RAW_INT` and compare the two altitudes - the difference is the geoid separation.
`Ctrl+C` both when done.

**2. See the goal.** Watch the finished gateway feed a stand-in ATAK display:

```bash
python3 course.py demo 2
```

Each line is one CoT update, exactly as an ATAK tablet would receive it. Watch the
coordinates and course change as the drone flies its circle. `Ctrl+C` to stop.

Want to see the full XML? Run `python3 course.py demo 2` in one terminal and
`python3 tools/cot_listen.py --xml` in another.

---

## Your task

Open **`exercises/mavlink_to_cot.py`**. Four `TODO`s, each in its own small function:

**TODO 1 - `convert_position(msg)`**: return `(lat_degrees, lon_degrees, alt_msl_meters)`
from the raw MAVLink fields.

**TODO 2 - `msl_to_hae(alt_msl, geoid_sep)`**: return the HAE. If `geoid_sep` is `None`
(no GPS data yet), return the MSL altitude unchanged.

**TODO 3 - `generate_cot()`**: build the `<point .../>` element as an f-string. The rest of
the event is already written around it.

**TODO 4 - `send_cot(sock, cot_xml)`**: send the XML to the TAK multicast group. Remember:
sockets send *bytes*, so encode the text first.

### Try it

```bash
python3 course.py run 2
```

This runs the simulator, a bridge, and *your* gateway, and shows what an ATAK device would
receive. Your gateway's own output is in `/tmp/edge-course/gateway.log`.

### Check it

```bash
python3 course.py check 2
```

---

## Knowledge check

1. MAVLink reports `lat=-337856000`. What latitude is that, and is it north or south?
2. Two CoT events arrive with the same `uid` but different positions. What does ATAK do?
3. Why must the gateway send HAE rather than MSL altitude?
4. What's the advantage of multicast over sending a copy to each tablet's IP address?
5. What would `type="a-h-G"` show on the map?

<details><summary>Answers</summary>

1. -33.7856 degrees - negative latitude is south (that's Sydney, Australia).
2. It moves the existing icon - same `uid` means same object. Different uids would create
   two separate icons.
3. CoT's `hae` attribute is defined as height above the WGS84 ellipsoid. Sending MSL puts
   the drone tens of meters off vertically, depending on location.
4. The sender doesn't need to know who's listening. Any device that joins the group gets the
   updates - tablets can come and go without reconfiguring the gateway.
5. A hostile (`h`) ground (`G`) object.

</details>

## In the field

- On a real tactical network, any ATAK device on the same LAN that's joined `239.2.3.1:6969`
  would show your drone. (A cloud workspace can't multicast onto your home network, which is
  why this course includes a listener.)
- Across wider networks, CoT usually goes through a **TAK Server** over TCP/TLS instead of
  multicast, and gets encrypted in transit.
- Pick `stale` with care: too short and icons flicker grey between updates; too long and a
  crashed drone keeps showing as live.
- Open-source projects in the TAK community do this same MAVLink-to-CoT translation - now you
  know what's inside them.

## Bonus challenges

1. Set `COT_CALLSIGN=RAVEN_2 python3 course.py run 2` - what changes in the listener?
2. Add `<remarks>` inside `<detail>` with the drone's ground speed in km/h.
3. Only send CoT when the drone has moved more than 5 m since the last update (hint: the
   difference in latitude times 111,320 is roughly meters north).

**Next:** `python3 course.py lesson 3`
