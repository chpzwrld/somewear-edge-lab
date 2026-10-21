#!/usr/bin/env python3
"""
Somewear Edge Lab - course launcher.

  python3 course.py                 show your progress and what to do next
  python3 course.py lesson <0-3>    open a lesson
  python3 course.py run <1-3>       run YOUR code for a module and watch it work (Ctrl+C to stop)
  python3 course.py check <1-3>     grade your exercise for a module
  python3 course.py hint <1-3>      reveal the next hint for a module
  python3 course.py demo <1-3>      watch the finished (reference) version run
  python3 course.py solution <1-3>  show the reference solution (try hints first!)
  python3 course.py reset <1-3>     put a module's exercise file back to its starting state
"""
import json
import os
import pydoc
import shutil
import signal
import subprocess
import sys
import textwrap
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROGRESS_FILE = ROOT / ".course_progress.json"
STARTERS = ROOT / ".course" / "starters"
LOGDIR = Path("/tmp/edge-course")
PY = sys.executable
SUDO = [] if os.geteuid() == 0 else ["sudo"]
COLOR = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None

LESSONS = {
    0: ("Welcome & how this course works", "lessons/00-welcome.md"),
    1: ("Telemetry ingest: serial-to-UDP bridge", "lessons/01-serial-to-udp.md"),
    2: ("MAVLink to Cursor-on-Target gateway", "lessons/02-mavlink-to-cot.md"),
    3: ("Tactical link watchdog & PACE failover", "lessons/03-tvpn-failover.md"),
}
EXERCISES = {1: "bridge_serial_udp.py", 2: "mavlink_to_cot.py", 3: "tvpn_watchdog.sh"}
GRADERS = {1: [PY, "tests/test_m1.py"], 2: [PY, "tests/test_m2.py"], 3: ["bash", "tests/test_m3.sh"]}

HINTS = {
    1: [
        "TODO 1 is a single line. Python's socket module creates sockets with "
        "socket.socket(family, type). Which two constants mean 'IPv4' and 'UDP'? "
        "(Lesson 1, section 'UDP in 60 seconds'.)",
        "TODO 2 is also one line. The serial port object `ser` has a .read(n) method. "
        "How many bytes should you ask for? Look at the constants at the top of the file.",
        "TODO 3: an empty bytes object b\"\" counts as False, so `if data:` only runs when "
        "something arrived. Inside it, call sock.sendto(data, address) - the address is a "
        "tuple: (ip, port). Then return len(data).",
        "Nearly the answer:\n"
        "  TODO 1:  return socket.socket(socket.AF_INET, socket.SOCK_DGRAM)\n"
        "  TODO 2:  data = ser.read(CHUNK_SIZE)\n"
        "  TODO 3:  if data:\n"
        "               sock.sendto(data, (UDP_TARGET_IP, UDP_TARGET_PORT))\n"
        "               return len(data)",
    ],
    2: [
        "TODO 1 is three divisions. 361234000 / 1e7 = 36.1234 and 120500 / 1000.0 = 120.5. "
        "Return all three in a tuple: return (a, b, c).",
        "TODO 2: `if geoid_sep is None:` is how Python checks 'no value yet'. You need two "
        "return statements - one inside the if, one after it.",
        "TODO 3: copy the example <point .../> from the comment into an f-string, then swap the "
        "numbers for {lat:.7f}, {lon:.7f} and {hae:.2f}. Wrap the f-string in single quotes (f'...') "
        "so the double quotes inside it are fine.",
        "TODO 4 is one line: sock.sendto(<bytes>, (<group ip>, <port>)). Turn the text into "
        "bytes with cot_xml.encode(\"utf-8\"); the group and port are constants at the top.",
    ],
    3: [
        "TODO 1: copy the ping command from los_ok() into probe(). Change -I \"$PRIMARY_DEV\" to "
        "-I \"$TVPN_SRC\" and \"$PRIMARY_GW\" to \"$TARGET_NODE\". Then delete the `return 0` line.",
        "TODO 2: fill in the template from the comment: <destination> = \"$TARGET_NODE/32\", "
        "<gateway> = \"$gw\", <interface> = \"$dev\", <source-ip> = \"$TVPN_SRC\".",
        "TODO 3 goes right after the [WARN] log line:\n"
        "  if (( fails >= FAIL_THRESHOLD )); then\n"
        "      log \"[ALERT] ...\"\n"
        "      set_path CONTINGENCY\n"
        "      fails=0\n"
        "  fi",
        "TODO 4 mirrors TODO 3: compare recov with RECOVER_THRESHOLD, then call set_path PRIMARY "
        "and set recov=0.",
        "Debugging tip: `python3 course.py run 3` lets you jam/unjam while watching your log. "
        "`sudo bash -x exercises/tvpn_watchdog.sh` prints every command as it runs.",
    ],
}


# ---------------------------------------------------------------- helpers
def c(code, text):
    return f"\033[{code}m{text}\033[0m" if COLOR else text


def load_progress():
    try:
        return json.loads(PROGRESS_FILE.read_text())
    except (OSError, ValueError):
        return {"passed": [], "read": [], "hints": {}}


def save_progress(p):
    try:
        PROGRESS_FILE.write_text(json.dumps(p, indent=2))
    except OSError:
        pass


def snapshot_starters():
    """Keeps a pristine copy of each exercise the first time the course runs (used by `reset`)."""
    if STARTERS.exists():
        return
    STARTERS.mkdir(parents=True, exist_ok=True)
    for name in EXERCISES.values():
        src = ROOT / "exercises" / name
        if src.exists():
            shutil.copy2(src, STARTERS / name)


def module_arg(args, allowed):
    if not args or not args[0].isdigit() or int(args[0]) not in allowed:
        sys.exit(f"Please give a module number: {', '.join(map(str, allowed))}")
    return int(args[0])


def target(n, use_solution):
    return f"{'solutions' if use_solution else 'exercises'}/{EXERCISES[n]}"


def env_ok():
    try:
        import pymavlink  # noqa: F401
        import serial  # noqa: F401
        import defusedxml  # noqa: F401
        return True
    except ImportError:
        return False


class Procs:
    """Background helper processes that are always cleaned up."""

    def __init__(self):
        self.items = []
        LOGDIR.mkdir(parents=True, exist_ok=True)

    def start(self, name, cmd, settle=1.5):
        log = open(LOGDIR / f"{name}.log", "w")
        p = subprocess.Popen(cmd, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        self.items.append(p)
        time.sleep(settle)
        if p.poll() is not None:
            print(c("31", f"[!] {name} stopped right away. Its output:"))
            print((LOGDIR / f"{name}.log").read_text())
            self.stop()
            sys.exit(1)
        print(f"  started {name:<10} (log: {LOGDIR / (name + '.log')})")

    def stop(self):
        for p in self.items:
            if p.poll() is None:
                try:
                    os.killpg(p.pid, signal.SIGINT)
                except OSError:
                    pass
        for p in self.items:
            try:
                p.wait(timeout=3)
            except subprocess.TimeoutExpired:
                os.killpg(p.pid, signal.SIGKILL)
        self.items.clear()


def stop_stale():
    sys.path.insert(0, str(ROOT / "tests"))
    from grading import COURSE_PROCS, kill_stale
    kill_stale(*COURSE_PROCS)


# ---------------------------------------------------------------- commands
def cmd_status(_args):
    p = load_progress()
    print(c("1;36", "\n  Somewear Edge Lab - hands-on course"))
    print("  " + "-" * 52)
    next_step = None
    for n, (title, _) in LESSONS.items():
        done = (n == 0 and 0 in p["read"]) or (n in p["passed"])
        if done:
            mark, note = c("32", "[x]"), c("32", "read" if n == 0 else "passed")
        elif next_step is None:
            mark, note = c("33", "[>]"), c("33", "you are here")
            next_step = n
        else:
            mark, note = "[ ]", ""
        print(f"  {mark} {n}  {title:<42} {note}")
    print()
    if not env_ok():
        print(c("31", "  Setup needed: run   bash .devcontainer/setup.sh\n"))
    if next_step is None:
        print(c("1;32", "  You've completed every module. Nice work!"))
        print("  Try the bonus challenges at the end of each lesson.\n")
    elif next_step == 0 or next_step not in p["read"]:
        print(f"  Next:  python3 course.py lesson {next_step}\n")
    else:
        print(f"  Next:  edit exercises/{EXERCISES[next_step]}, then\n"
              f"         python3 course.py run {next_step}     (try it)\n"
              f"         python3 course.py check {next_step}   (grade it)\n")
    print("  All commands:  python3 course.py help\n")


def cmd_lesson(args):
    n = module_arg(args, LESSONS)
    title, rel = LESSONS[n]
    p = load_progress()
    if n not in p["read"]:
        p["read"].append(n)
        save_progress(p)
    path = ROOT / rel
    if os.environ.get("TERM_PROGRAM") == "vscode" and shutil.which("code"):
        subprocess.run(["code", str(path)])
        print(f"Opened {rel} in the editor.")
        print("Tip: press Ctrl+Shift+V (Cmd+Shift+V on Mac) for the formatted preview.")
    else:
        pydoc.pager(path.read_text())
        print(f"(Lesson file: {rel} - open it in any Markdown viewer for nicer formatting.)")


def cmd_check(args):
    if args and args[0] == "all":
        failed = [n for n in (1, 2, 3) if subprocess.run(GRADERS[n] + [target(n, "--solution" in args)],
                                                         cwd=ROOT).returncode != 0]
        sys.exit(1 if failed else 0)
    n = module_arg(args, (1, 2, 3))
    use_solution = "--solution" in args
    rc = subprocess.run(GRADERS[n] + [target(n, use_solution)], cwd=ROOT).returncode
    if rc == 0 and not use_solution:
        p = load_progress()
        if n not in p["passed"]:
            p["passed"].append(n)
            save_progress(p)
        nxt = n + 1
        print(f"\nModule {n} complete! " + (f"Next: python3 course.py lesson {nxt}" if nxt in LESSONS
                                            else "That was the last module - congratulations!"))
    elif rc != 0 and not use_solution:
        print(f"Need help? python3 course.py hint {n}")
    sys.exit(rc)


def cmd_hint(args):
    n = module_arg(args, HINTS)
    p = load_progress()
    shown = p["hints"].get(str(n), 0)
    if "--all" in args:
        shown = len(HINTS[n])
    elif shown < len(HINTS[n]):
        shown += 1
    p["hints"][str(n)] = shown
    save_progress(p)
    print(c("1", f"\nHints for module {n} ({shown} of {len(HINTS[n])} revealed):\n"))
    for i, h in enumerate(HINTS[n][:shown], 1):
        first, *rest = h.splitlines()
        wrapped = textwrap.wrap(first, width=84) or [""]
        print(c("33", f"  {i}. ") + wrapped[0])
        for line in wrapped[1:] + rest:
            print("     " + line)
        print()
    if shown < len(HINTS[n]):
        print(f"Run the same command again for the next hint.\n")
    else:
        print(f"That's every hint. Still stuck? python3 course.py solution {n}\n")


def cmd_solution(args):
    n = module_arg(args, (1, 2, 3))
    if "--yes" not in args:
        print(f"This shows exactly how to finish module {n}. Working it out yourself (with "
              f"`python3 course.py hint {n}`) is how the skills stick.")
        if input("Show the solution anyway? [y/N] ").strip().lower() not in ("y", "yes"):
            return
    ex, sol = ROOT / target(n, False), ROOT / target(n, True)
    print(c("1", f"\nDifferences between your file ({ex.relative_to(ROOT)}) and the solution "
                 f"({sol.relative_to(ROOT)}):\n  lines starting with - are yours, + are the solution\n"))
    subprocess.run(["diff", "-u", "--color=auto" if COLOR else "--color=never", str(ex), str(sol)])


def cmd_reset(args):
    n = module_arg(args, (1, 2, 3))
    starter = STARTERS / EXERCISES[n]
    if not starter.exists():
        sys.exit("No starter copy saved. If you use git:  git checkout -- exercises/" + EXERCISES[n])
    if "--yes" not in args and input(f"Replace exercises/{EXERCISES[n]} with the original starter? "
                                     "Your changes will be lost. [y/N] ").strip().lower() not in ("y", "yes"):
        return
    backup = ROOT / "exercises" / (EXERCISES[n] + ".bak")
    shutil.copy2(ROOT / "exercises" / EXERCISES[n], backup)
    shutil.copy2(starter, ROOT / "exercises" / EXERCISES[n])
    print(f"Reset exercises/{EXERCISES[n]} (your old version is saved as {backup.name}).")


def cmd_run(args, use_solution=False):
    n = module_arg(args, (1, 2, 3))
    use_solution = use_solution or "--solution" in args
    who = "the reference solution" if use_solution else "your code"
    if n == 3:
        return run_failover_lab(target(3, use_solution), who)
    stop_stale()
    procs = Procs()
    try:
        print(c("1", f"\nModule {n}: running {who}  (press Ctrl+C to stop)\n"))
        procs.start("simulator", [PY, "simulator/flight_sim.py"])
        if n == 1:
            procs.start("bridge", [PY, target(1, use_solution)])
            print(c("1", "\nDecoding whatever arrives on UDP 14550 - if your bridge works you'll see "
                         "drone messages:\n"))
            subprocess.run([PY, "tools/mav_inspect.py"], cwd=ROOT)
        else:
            procs.start("bridge", [PY, "solutions/bridge_serial_udp.py"])
            procs.start("gateway", [PY, target(2, use_solution)], settle=2.5)
            print(c("1", "\nThis 'ATAK' listener shows every CoT track your gateway multicasts:\n"))
            subprocess.run([PY, "tools/cot_listen.py"], cwd=ROOT)
    except KeyboardInterrupt:
        pass
    finally:
        procs.stop()
        print("Stopped everything.")


def run_failover_lab(script, who):
    net = ["bash", "lab/tvpn_lab_net.sh"]
    if subprocess.run(SUDO + net + ["up"], cwd=ROOT).returncode != 0:
        sys.exit("Could not build the lab network (needs root / network-admin rights).")
    wd = subprocess.Popen(SUDO + ["bash", script], cwd=ROOT, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, text=True, start_new_session=True)

    def pump():
        for line in wd.stdout:
            print(c("36", "  watchdog | ") + line.rstrip(), flush=True)
    threading.Thread(target=pump, daemon=True).start()

    print(c("1", f"\nModule 3: lab network up, running {who}.\n"))
    menu = "  [j] jam LOS   [u] restore LOS   [s] status   [p] ping peer   [q] quit\n"
    try:
        time.sleep(1)
        while True:
            choice = input(menu).strip().lower()[:1]
            if choice == "j":
                subprocess.run(SUDO + net + ["jam"], cwd=ROOT)
            elif choice == "u":
                subprocess.run(SUDO + net + ["unjam"], cwd=ROOT)
            elif choice == "s":
                subprocess.run(SUDO + net + ["status"], cwd=ROOT)
            elif choice == "p":
                subprocess.run(["ping", "-c", "3", "-I", "100.64.2.102", "100.64.2.1"])
            elif choice == "q":
                break
            if wd.poll() is not None:
                print(c("31", "  The watchdog has stopped (see its output above)."))
    except (KeyboardInterrupt, EOFError):
        pass
    finally:
        subprocess.run(SUDO + ["kill", "-TERM", str(wd.pid)], stderr=subprocess.DEVNULL)
        try:
            wd.wait(timeout=3)
        except subprocess.TimeoutExpired:
            subprocess.run(SUDO + ["kill", "-KILL", str(wd.pid)], stderr=subprocess.DEVNULL)
        subprocess.run(SUDO + net + ["down"], cwd=ROOT, stdout=subprocess.DEVNULL)
        print("\nWatchdog stopped and lab network removed.")


def cmd_help(_args):
    print(__doc__)


COMMANDS = {
    "status": cmd_status, "lesson": cmd_lesson, "run": cmd_run, "check": cmd_check,
    "hint": cmd_hint, "solution": cmd_solution, "reset": cmd_reset, "help": cmd_help,
    "demo": lambda a: cmd_run(a, use_solution=True),
}

if __name__ == "__main__":
    signal.signal(signal.SIGPIPE, signal.SIG_DFL)   # exit quietly if output is piped to e.g. head
    os.chdir(ROOT)
    snapshot_starters()
    argv = sys.argv[1:] or ["status"]
    if argv[0] in ("-h", "--help"):
        argv = ["help"]
    if argv[0] not in COMMANDS:
        sys.exit(f"Unknown command '{argv[0]}'. Try: python3 course.py help")
    COMMANDS[argv[0]](argv[1:])
