"""Shared helpers for the course graders: pretty output, loading student code, background processes."""
import importlib.util
import os
import signal
import subprocess
import sys
import time
import traceback
from pathlib import Path

sys.dont_write_bytecode = True   # keep exercises/ free of __pycache__ folders
ROOT = Path(__file__).resolve().parent.parent
LOGDIR = Path("/tmp/edge-course")
COLOR = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None


def _c(code, text):
    return f"\033[{code}m{text}\033[0m" if COLOR else text


def step(n, total, text):
    print(_c("1", f"\n[{n}/{total}] {text}"))


def ok(text):
    print(_c("32", "  PASS ") + text)


def info(text):
    print("       " + text)


class Fail(Exception):
    """Raised to stop grading with a friendly message (and an optional hint)."""

    def __init__(self, message, hint=None):
        super().__init__(message)
        self.hint = hint


def report_failure(e):
    print(_c("31", "  FAIL ") + str(e))
    if getattr(e, "hint", None):
        for line in e.hint.splitlines():
            print(_c("33", "  HINT ") + line)


def run_grader(title, steps_fn):
    """Runs steps_fn(); prints a summary; exits 0 on success, 1 on failure."""
    print(_c("1;36", f"=== {title} ==="))
    try:
        steps_fn()
    except Fail as e:
        report_failure(e)
        print(_c("31", "\nNot quite yet - fix the item above and run the check again."))
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nStopped.")
        sys.exit(130)
    print(_c("1;32", f"\n[SUCCESS] {title} - all checks passed!"))


def load_module(path, name="student_module"):
    """Imports a student's .py file, turning errors into friendly failures."""
    path = Path(path)
    if not path.exists():
        raise Fail(f"Can't find {path}.")
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except SyntaxError as e:
        raise Fail(f"Python can't read {path.name}: syntax error on line {e.lineno}: {e.msg}",
                   hint=f"Look closely at line {e.lineno} (and the line above it) for a missing "
                        "bracket, quote, colon, or wrong indentation.")
    except Exception as e:
        raise Fail(f"{path.name} crashed while loading: {type(e).__name__}: {e}",
                   hint=traceback.format_exc(limit=2).strip())
    return mod


def call(fn_name, fn, *args):
    """Calls a student function, turning exceptions into friendly failures."""
    try:
        return fn(*args)
    except Exception as e:
        tb = traceback.extract_tb(e.__traceback__)[-1]
        hint = f"The error happened on line {tb.lineno}: {tb.line}"
        if "bytes-like object is required" in str(e):
            hint += "\nSockets send bytes, not text - convert a string first with .encode(\"utf-8\")"
        raise Fail(f"{fn_name}() raised {type(e).__name__}: {e}", hint=hint)


class Background:
    """Starts helper processes (simulator, bridge, ...) and always cleans them up."""

    def __init__(self):
        self.procs = []
        LOGDIR.mkdir(parents=True, exist_ok=True)

    def start(self, name, cmd, settle=1.5):
        log = open(LOGDIR / f"{name}.log", "w")
        p = subprocess.Popen(cmd, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                             start_new_session=True)
        self.procs.append((name, p))
        time.sleep(settle)
        if p.poll() is not None:
            raise Fail(f"{name} exited immediately. Its output:\n" + self.log_tail(name),
                       hint=f"Try running it by hand to see the error: {' '.join(map(str, cmd))}")
        return p

    @staticmethod
    def log_tail(name, lines=15):
        try:
            text = (LOGDIR / f"{name}.log").read_text().strip().splitlines()
            return "\n".join("         | " + l for l in text[-lines:]) or "         | (no output)"
        except OSError:
            return "         | (no log)"

    def stop(self):
        for _, p in reversed(self.procs):
            if p.poll() is None:
                try:
                    os.killpg(p.pid, signal.SIGINT)
                except OSError:
                    pass
        deadline = time.time() + 3
        for _, p in self.procs:
            try:
                p.wait(timeout=max(0.1, deadline - time.time()))
            except subprocess.TimeoutExpired:
                os.killpg(p.pid, signal.SIGKILL)
        self.procs.clear()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.stop()


def _ancestors():
    pids, pid = set(), os.getpid()
    while pid > 1:
        pids.add(pid)
        try:
            with open(f"/proc/{pid}/stat") as f:
                pid = int(f.read().rsplit(")", 1)[1].split()[1])
        except (OSError, ValueError, IndexError):
            break
    return pids


def kill_stale(*scripts):
    """Stops leftover course processes from an earlier run (they would hold the UDP ports).

    Only python processes whose script argument ends with one of `scripts` are stopped,
    never this process or its parents.
    """
    if not os.path.isdir("/proc"):
        return
    mine, killed = _ancestors(), False
    for entry in os.listdir("/proc"):
        if not entry.isdigit() or int(entry) in mine:
            continue
        try:
            with open(f"/proc/{entry}/cmdline", "rb") as f:
                argv = [a.decode(errors="replace") for a in f.read().split(b"\0") if a]
        except OSError:
            continue
        if len(argv) < 2 or "python" not in os.path.basename(argv[0]):
            continue
        if any(a.endswith(s) for a in argv[1:3] for s in scripts):
            try:
                os.kill(int(entry), signal.SIGINT)
                killed = True
            except OSError:
                pass
    if killed:
        time.sleep(1.0)


COURSE_PROCS = ("simulator/flight_sim.py", "bridge_serial_udp.py", "mavlink_to_cot.py",
                "tools/mav_inspect.py", "tools/cot_listen.py")
