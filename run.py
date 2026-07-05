#!/usr/bin/env python3
# run.py — Stock-Ward v4 local launcher.
# If not already inside the project's .venv, it re-launches itself with the
# venv interpreter (creating the venv + installing deps on first run), then
# starts the FastAPI server and opens the app in the default browser.
import os
import sys
import subprocess
import threading
import time
import webbrowser

ROOT = os.path.dirname(os.path.abspath(__file__))
VENV_DIR = os.path.join(ROOT, ".venv")
HOST = "127.0.0.1"
PORT = int(os.environ.get("STOCKWARD_PORT", "8377"))
URL = f"http://{HOST}:{PORT}"


def _venv_python():
    if os.name == "nt":
        return os.path.join(VENV_DIR, "Scripts", "python.exe")
    return os.path.join(VENV_DIR, "bin", "python")


def _in_venv():
    """True when the running interpreter lives inside our .venv."""
    try:
        return os.path.commonpath([os.path.abspath(sys.prefix), VENV_DIR]) == VENV_DIR
    except ValueError:
        return False


def ensure_venv_and_reexec():
    """Create .venv + install requirements, then re-run under it.

    Skipped when STOCKWARD_NO_VENV=1 (run.bat already handled it, or the user
    manages their own environment)."""
    if getattr(sys, "frozen", False):
        return  # packaged .exe: deps are bundled, no venv needed
    if _in_venv() or os.environ.get("STOCKWARD_NO_VENV") == "1":
        return
    py = _venv_python()
    if not os.path.exists(py):
        print(f"[Stock-Ward] Creating virtual environment in {VENV_DIR} ...")
        import venv
        venv.EnvBuilder(with_pip=True, upgrade_deps=True).create(VENV_DIR)
        print("[Stock-Ward] Installing dependencies ...")
        subprocess.check_call([py, "-m", "pip", "install", "-r",
                               os.path.join(ROOT, "requirements.txt")])
    env = dict(os.environ, STOCKWARD_NO_VENV="1")
    sys.exit(subprocess.call([py, os.path.abspath(__file__)], env=env))


def _wait_for_server(timeout=30):
    import urllib.request
    for _ in range(int(timeout * 2)):
        try:
            urllib.request.urlopen(URL + "/api/rf", timeout=1)
            return True
        except Exception:
            time.sleep(0.5)
    return False


def _serve_background():
    """Run uvicorn in a daemon thread (signal handlers disabled)."""
    import uvicorn
    import server
    config = uvicorn.Config(server.app, host=HOST, port=PORT, log_level="warning")
    srv = uvicorn.Server(config)
    srv.install_signal_handlers = lambda: None
    t = threading.Thread(target=srv.run, daemon=True)
    t.start()
    return srv


def _run_desktop_window():
    """Native desktop window via pywebview. Returns False if unavailable."""
    if os.environ.get("STOCKWARD_BROWSER") == "1":
        return False
    try:
        import webview  # pywebview
    except Exception:
        return False
    _serve_background()
    if not _wait_for_server():
        print("[Stock-Ward] server did not start in time")
    webview.create_window("Stock-Ward Terminal", URL, width=1480, height=920,
                          min_size=(1100, 720), background_color="#0b0f17")
    webview.start()  # blocks until the window is closed
    return True


def main():
    os.chdir(ROOT)
    ensure_venv_and_reexec()
    try:
        import uvicorn  # noqa
    except ImportError:
        print("Installing dependencies (first run)...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])

    print(f"\n  Stock-Ward v4  ->  {URL}\n")
    # Preferred: launch as a native desktop window (feels like an app).
    if _run_desktop_window():
        return
    # Fallback: serve + open the default browser.
    print("  (desktop window unavailable — opening in browser; Ctrl+C to stop)\n")
    threading.Thread(target=lambda: (_wait_for_server(), webbrowser.open(URL)), daemon=True).start()
    import uvicorn
    if getattr(sys, "frozen", False):
        import server
        uvicorn.run(server.app, host=HOST, port=PORT, log_level="warning")
    else:
        uvicorn.run("server:app", host=HOST, port=PORT, log_level="warning")


if __name__ == "__main__":
    main()
