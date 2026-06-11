"""
Behavioral Security Monitor: Desktop Application Entry Point

Starts the Flask backend in a daemon thread, waits for it to be ready,
then opens the app in the default browser. If pywebview is installed,
opens in a native desktop window instead.
"""

import os
import sys
import socket
import threading
import time
import webbrowser

# Ensure the project root is on the import path so 'backend' and 'config' resolve
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
from config import ENV_PATH

# Load .env before any backend imports that might read environment variables
load_dotenv(ENV_PATH)


def find_free_port(start=5000, end=5010):
    """Find the first available port in the given range."""
    for port in range(start, end + 1):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.bind(("127.0.0.1", port))
            s.close()
            return port
        except OSError:
            continue
    raise RuntimeError(f"No free port found in range {start}-{end}")


def start_flask(port):
    """Run the Flask server in the current thread (called as daemon).

    Prefers Waitress (production-grade WSGI) over Flask's built-in dev
    server. Falls back to app.run() if Waitress isn't installed.
    """
    from backend.app import create_app
    app = create_app()
    try:
        from waitress import serve
        serve(app, host="127.0.0.1", port=port, threads=8, _quiet=True)
    except ImportError:
        app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False)


def wait_for_server(port, timeout=15):
    """Block until the Flask server responds on the given port."""
    import urllib.request
    url = f"http://127.0.0.1:{port}/api/health"
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            resp = urllib.request.urlopen(url, timeout=2)
            if resp.status == 200:
                return True
        except Exception:
            pass
        time.sleep(0.15)
    return False


def main():
    port = find_free_port()
    print(f"Starting backend on port {port}...")

    # Start Flask in a daemon thread
    server_thread = threading.Thread(target=start_flask, args=(port,), daemon=True)
    server_thread.start()

    # Wait until Flask is accepting requests
    if not wait_for_server(port):
        print("ERROR: Flask server did not start in time.")
        sys.exit(1)

    app_url = f"http://127.0.0.1:{port}"
    print(f"Backend ready at {app_url}")

    # Try native window first, fall back to browser
    try:
        import webview
        print("Opening native desktop window...")

        # Resolve icon path for both dev and PyInstaller-frozen contexts
        base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
        icon_path = os.path.join(base, "frontend", "static", "icon.ico")
        if not os.path.exists(icon_path):
            icon_path = None  # fall back gracefully

        window_kwargs = dict(
            title="HumanSeeker",
            url=f"{app_url}/",
            width=1100,
            height=800,
            min_size=(800, 600),
        )

        window = webview.create_window(**window_kwargs)

        start_kwargs = dict(
            debug=os.environ.get("DEBUG", "").lower() in ("1", "true"),
        )
        if icon_path:
            start_kwargs["icon"] = icon_path

        webview.start(**start_kwargs)
        print("Window closed. Shutting down.")
    except ImportError:
        print("Opening in browser (install 'pywebview' for a native window)...")
        webbrowser.open(app_url)
        print()
        print("=" * 55)
        print("  Behavioral Security Monitor is running!")
        print(f"  Open {app_url} if it didn't open automatically.")
        print()
        print("  Press Ctrl+C to stop the server.")
        print("=" * 55)
        print()
        try:
            # Keep the main thread alive so the daemon Flask thread stays running
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nShutting down.")


if __name__ == "__main__":
    main()
