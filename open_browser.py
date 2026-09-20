"""Open the browser only after the local service responds; used by the launcher."""
import sys
import time
import urllib.request
import webbrowser

port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
for attempt in range(40):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1) as response:
            if response.status == 200:
                webbrowser.open(f"http://127.0.0.1:{port}/")
                break
    except OSError:
        time.sleep(0.5)
