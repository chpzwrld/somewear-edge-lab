# Somewear Edge Lab

**A hands-on course in drone-to-ATAK edge integration, for beginners.**

You'll write the three pieces of software that put a drone on a soldier's map and keep it
there under jamming:

```
 DRONE                     EDGE DEVICE (you build this)                      ATAK TABLETS
 autopilot ──serial──> [1: bridge] ──UDP 14550──> [2: gateway] ──CoT multicast──> map icon
                              [3: watchdog fails over LOS radio <-> SATCOM]
```

| Module | You learn | You write |
|---|---|---|
| 1. Serial-to-UDP bridge | serial ports, bytes, UDP sockets, MAVLink basics | Python |
| 2. MAVLink to Cursor-on-Target gateway | MAVLink units, XML, CoT, MSL vs HAE, multicast | Python |
| 3. Link watchdog & PACE failover | IP routing, ping, PACE planning, failover logic | Bash |

No hardware needed: a simulator plays the drone and a virtual network plays the radios.
Each module has a lesson, an exercise with `TODO` blanks, progressive hints, and an automatic
grader that tells you exactly what to fix. Total time: about 2-3 hours.

---

## Launch the course

Pick whichever fits you. All three give you the same environment.

### Option A - GitHub Codespaces (easiest, runs in your browser)

[![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/chpzwrld/somewear-edge-lab)

Click the button (or on GitHub: **Code -> Codespaces -> Create codespace**). Setup runs
automatically (~2 minutes); Lesson 0 opens when it's ready.

### Option B - Docker, on your own computer (Linux, macOS or Windows)

1. Install [Docker Desktop](https://docs.docker.com/get-docker/) (Linux: Docker Engine) and
   start it. Works on Intel and Apple-silicon Macs, Windows 10/11 and Linux.
2. Get the course: unzip `somewear-edge-lab.zip`, or
   `git clone https://github.com/chpzwrld/somewear-edge-lab.git`
3. Launch it:
   - **macOS / Linux:** open a terminal in the folder and run `./launch.sh`
   - **Windows:** double-click `launch.cmd` (or run it from PowerShell)

The first launch builds the course environment (a few minutes), then drops you into a
terminal inside it, showing your progress. Edit the files in the course folder with any
editor on your computer (VS Code, Notepad++, ...) - changes show up inside instantly and
your work stays in the folder. Need a second terminal? Run `./launch.sh` (or `launch.cmd`)
again in another window while the first is open. Type `exit` to leave.

### Option C - VS Code Dev Containers (local, no cloud)

With [VS Code](https://code.visualstudio.com/), Docker, and the
[Dev Containers extension](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers):
open the folder, then **Reopen in Container** when prompted.

> Running directly on a Linux machine also works: `bash .devcontainer/setup.sh`, then
> `python3 course.py`. Module 3 needs `sudo`. On macOS/Windows use Option B or C.

---

## Take the course

Everything goes through one command:

```bash
python3 course.py               # your progress + what to do next
python3 course.py lesson 0      # start here
```

| Command | What it does |
|---|---|
| `python3 course.py lesson <0-3>` | open a lesson |
| `python3 course.py run <1-3>` | run *your* code and watch it work |
| `python3 course.py check <1-3>` | grade your exercise |
| `python3 course.py hint <1-3>` | reveal the next hint |
| `python3 course.py demo <1-3>` | watch the finished version run |
| `python3 course.py solution <1-3>` | compare your file with the answer |
| `python3 course.py reset <1-3>` | start an exercise over |

## What's in the repo

```
course.py              the course launcher
lessons/               00-welcome ... 03-tvpn-failover - read these
exercises/             YOUR code: fill in the TODOs here
simulator/             the simulated drone (MAVLink over a virtual serial port)
lab/                   the simulated LOS + SATCOM network for Module 3
tools/                 mav_inspect.py (see MAVLink) and cot_listen.py (an ATAK stand-in)
tests/                 the graders
solutions/             reference answers (no peeking until you've tried!)
```

## For instructors

- `python3 course.py check all --solution` verifies the reference solutions end to end.
- `python3 course.py demo <n>` is handy for live walkthroughs.
- Progress is stored per learner in `.course_progress.json` (git-ignored).
- The CoT callsign and type can be changed with the `COT_CALLSIGN` / `COT_TYPE` environment
  variables.
