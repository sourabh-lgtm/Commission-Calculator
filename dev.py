"""Development launcher with auto-reload.

Watches all .py source files and restarts launch.py automatically whenever
one changes.  The browser tab stays open — just press F5 after a restart.

Usage:
    py -3 dev.py [--port 8050] [--data-dir data]
"""
import glob
import os
import subprocess
import sys
import time


def _mtimes() -> dict:
    times = {}
    for pat in ["src/**/*.py", "*.py", "export_excel.py"]:
        for path in glob.glob(pat, recursive=True):
            if ".venv" in path or "__pycache__" in path:
                continue
            try:
                times[path] = os.path.getmtime(path)
            except OSError:
                pass
    return times


def _start(extra_args: list, open_browser: bool) -> subprocess.Popen:
    cmd = [sys.executable, "launch.py"] + extra_args
    if not open_browser:
        cmd.append("--no-browser")
    return subprocess.Popen(cmd)


def main() -> None:
    # Pass any extra flags (--port, --data-dir) through to launch.py
    extra = sys.argv[1:]

    mtimes = _mtimes()
    proc = _start(extra, open_browser=True)
    print("[dev] Watching for changes. Press Ctrl+C to stop.")

    try:
        while True:
            time.sleep(1)
            new_mtimes = _mtimes()
            changed = [f for f, t in new_mtimes.items() if mtimes.get(f) != t]
            if changed:
                label = os.path.basename(changed[0])
                print(f"[dev] {label} changed — restarting...")
                proc.terminate()
                proc.wait()
                time.sleep(0.5)          # let the OS free the port
                proc = _start(extra, open_browser=False)
                mtimes = new_mtimes
                print("[dev] Ready. Refresh your browser tab (F5).")
    except KeyboardInterrupt:
        print("\n[dev] Stopped.")
        proc.terminate()


if __name__ == "__main__":
    main()
