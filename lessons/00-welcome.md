# Lesson 0 - Welcome to the Somewear Edge Lab

You're about to build the software that gets a drone onto a soldier's map.

A drone's autopilot speaks one language (**MAVLink**, compact binary messages over a serial
cable). The tablets running **ATAK** speak another (**Cursor-on-Target**, small XML messages
on the network). And the radio links connecting everything can be jammed at any moment.
Edge integration is the glue in between - and that's what you'll write.

```
 DRONE                     YOUR EDGE DEVICE                                  ATAK TABLETS
 autopilot ──serial──> [Module 1: bridge] ──UDP──> [Module 2: gateway] ──multicast──> map icon
                                       [Module 3: watchdog keeps the radio link alive]
```

No drone or radio is needed: a **simulator** plays the drone, and a small virtual network
plays the radios.

## How the course works

Each module follows the same loop:

1. **Read** the lesson - concepts first, explained from the ground up.
2. **Explore** - run a few commands and see the real data for yourself.
3. **Code** - open the exercise file and fill in the blanks marked `TODO`.
4. **Run** your code and watch it work: `python3 course.py run <n>`
5. **Check** it: `python3 course.py check <n>` - the grader tests each TODO separately and
   tells you exactly which one needs work.

Stuck? `python3 course.py hint <n>` reveals hints one at a time, from gentle nudge to nearly
the answer. Want to see the goal first? `python3 course.py demo <n>` runs a finished version.

| Command | What it does |
|---|---|
| `python3 course.py` | Your progress and the next step |
| `python3 course.py lesson <0-3>` | Open a lesson |
| `python3 course.py run <1-3>` | Run *your* code and watch it work |
| `python3 course.py check <1-3>` | Grade your exercise |
| `python3 course.py hint <1-3>` | Next hint |
| `python3 course.py demo <1-3>` | Watch the reference solution run |
| `python3 course.py solution <1-3>` | See the answer (after trying!) |
| `python3 course.py reset <1-3>` | Start an exercise over |

## The map of the course

| Module | You'll learn | You'll write | Time |
|---|---|---|---|
| 1. Serial-to-UDP bridge | serial ports, bytes, UDP sockets, MAVLink basics | ~5 lines of Python | 30-45 min |
| 2. MAVLink to CoT gateway | MAVLink units, XML, CoT events, altitude datums, multicast | ~8 lines of Python | 45-60 min |
| 3. Link watchdog & failover | IP routing, ping, PACE planning, bash scripting | ~12 lines of bash | 45-60 min |

## Terminal survival guide

You'll type commands into a **terminal** (also called a shell).

- **Open one:** in VS Code / Codespaces press `` Ctrl+` `` (the backtick key, left of `1`),
  or use the menu *Terminal → New Terminal*.
- **Run a command:** type it and press Enter. Commands in this course are run from the
  course folder (the terminal starts there).
- **Stop a running program:** press `Ctrl+C`. Many programs here run until you stop them.
- **Two things at once:** click the split icon in the terminal panel (or `+` for a new tab).
- **Edit files:** click them in the Explorer panel on the left. Files save with `Ctrl+S`.
- **`sudo`** in front of a command runs it as the administrator (root). Module 3 needs it
  because changing network routes is an admin action.

## Python you'll need

You don't need to be a Python expert. These are the pieces the exercises use:

```python
x = 10 / 4                 # division always gives a decimal number: 2.5
name = "drone"             # text is a "string"
data = b"\x01\x02"         # raw bytes - what actually travels over wires and networks
text = "hi".encode("utf-8")   # string -> bytes   (b"hi")

def add(a, b):             # a function: takes inputs, gives back a result with `return`
    return a + b

if data:                   # empty things (b"", "", 0, None) count as False
    print("got some")

point = (36.1, -115.1)     # a tuple: several values bundled together
lat, lon = point           # ...and unpacked again

print(f"lat={lat:.2f}")    # an f-string: puts values inside text, :.2f = 2 decimals
```

If any of that is new, that's fine - each exercise explains what it needs, and the hints
fill the gaps.

## Ready?

```bash
python3 course.py lesson 1
```
