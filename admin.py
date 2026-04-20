import os
import re
import signal
import socket
import time
from pathlib import Path


def _load_env():
    p = Path(__file__).parent / ".env"
    if not p.exists():
        return
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_env()

_SAFE_NAME = re.compile(r"^[a-zA-Z0-9_\-]{1,64}$")

def _validate_name(name):
    if not _SAFE_NAME.match(name):
        raise ValueError(f"BU_NAME must be alphanumeric/dash/underscore, 1-64 chars, got: {name!r}")
    return name

def _runtime_dir():
    """Private runtime directory (mode 0o700), matching daemon.py."""
    d = Path(os.environ.get("XDG_RUNTIME_DIR", f"/tmp/browser-harness-{os.getuid()}"))
    d.mkdir(mode=0o700, exist_ok=True)
    return d

NAME = _validate_name(os.environ.get("BU_NAME", "default"))


def _paths(name):
    n = _validate_name(name or NAME)
    rd = _runtime_dir()
    return str(rd / f"bu-{n}.sock"), str(rd / f"bu-{n}.pid")


def _log_tail(name):
    n = _validate_name(name or NAME)
    p = _runtime_dir() / f"bu-{n}.log"
    try:
        return p.read_text().strip().splitlines()[-1]
    except (FileNotFoundError, IndexError):
        return None


def daemon_alive(name=None):
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(1)
        s.connect(_paths(name)[0])
        s.close()
        return True
    except (FileNotFoundError, ConnectionRefusedError, socket.timeout):
        return False


def ensure_daemon(wait=60.0, name=None):
    """Idempotent. Starts a local-only daemon connecting to the user's Chrome."""
    if daemon_alive(name):
        return
    import subprocess

    e = {**os.environ, **({"BU_NAME": name} if name else {})}
    # Strip any cloud-related env vars to prevent accidental remote connections
    for key in ("BU_CDP_WS", "BU_BROWSER_ID", "BROWSER_USE_API_KEY"):
        e.pop(key, None)
    p = subprocess.Popen(
        ["uv", "run", "daemon.py"],
        cwd=os.path.dirname(os.path.abspath(__file__)),
        env=e,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    deadline = time.time() + wait
    while time.time() < deadline:
        if daemon_alive(name):
            return
        if p.poll() is not None:
            break
        time.sleep(0.2)
    msg = _log_tail(name)
    rd = _runtime_dir()
    raise RuntimeError(msg or f"daemon {name or NAME} didn't come up -- check {rd}/bu-{name or NAME}.log")


def restart_daemon(name=None):
    """Stop the daemon + cleanup socket/pid files."""
    sock, pid_path = _paths(name)
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(5)
        s.connect(sock)
        s.sendall(b'{"meta":"shutdown"}\n')
        s.recv(1024)
        s.close()
    except Exception:
        pass
    try:
        pid = int(open(pid_path).read())
    except (FileNotFoundError, ValueError):
        pid = None
    if pid:
        for _ in range(75):
            try:
                os.kill(pid, 0)
                time.sleep(0.2)
            except ProcessLookupError:
                break
        else:
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
    for f in (sock, pid_path):
        try:
            os.unlink(f)
        except FileNotFoundError:
            pass
