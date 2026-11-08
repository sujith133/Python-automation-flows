"""Launch Playwright recorder (codegen) with a viewport sized to your full
screen, so no buttons or links end up clipped below the fold or hidden
behind the recorder toolbar.

Writes recorded actions directly to recorded_flow.py via codegen's
built-in --output flag.

Usage:
    python run_codegen_capture.py

Optional environment variables:
    LS_BASE_URL       Base app URL. Defaults to the Lightspeed test tenant.
    LS_CODEGEN_OUT    Output file path. Defaults to ./recorded_flow.py
    LS_VIEWPORT       Override viewport as "WIDTHxHEIGHT", e.g. "1920x1080".
                       If not set, the script auto-detects your screen size.
"""

import os
import subprocess
import sys
from pathlib import Path

DEFAULT_URL = "https://studytestcompany.retail.lightspeed.app/signin/?return=%2Fdashboards"

# Reserve space for the OS title bar / taskbar / codegen's in-page toolbar,
# so the window doesn't get cut off the top or bottom of the screen.
HEIGHT_MARGIN = 120


def detect_screen_size() -> tuple[int, int]:
    """Best-effort screen resolution detection. Falls back to 1920x1080."""
    try:
        import tkinter as tk

        root = tk.Tk()
        root.withdraw()
        width = root.winfo_screenwidth()
        height = root.winfo_screenheight()
        root.destroy()
        if width > 0 and height > 0:
            return width, height
    except Exception:
        pass
    return 1920, 1080


def get_viewport_size() -> tuple[int, int]:
    override = os.environ.get("LS_VIEWPORT")
    if override:
        try:
            w, h = override.lower().split("x")
            return int(w), int(h)
        except ValueError:
            print(f"Ignoring invalid LS_VIEWPORT='{override}', auto-detecting instead.")

    width, height = detect_screen_size()
    height = max(height - HEIGHT_MARGIN, 600)
    return width, height


def main() -> int:
    project_dir = Path(__file__).resolve().parent
    output_path = Path(
        os.environ.get("LS_CODEGEN_OUT", str(project_dir / "recorded_flow.py"))
    ).resolve()
    url = os.environ.get("LS_BASE_URL", DEFAULT_URL)
    width, height = get_viewport_size()

    cmd = [
        sys.executable, "-m", "playwright", "codegen",
        "--browser=chromium",
        f"--viewport-size={width},{height}",
        f"--output={output_path}",
        url,
    ]

    print("Starting Playwright recorder...")
    print(f"URL: {url}")
    print(f"Output: {output_path}")
    print(f"Viewport: {width}x{height} (auto-detected, minus {HEIGHT_MARGIN}px margin)")
    print("Interact with every button/link you want captured, then close the browser.\n")

    try:
        result = subprocess.run(cmd)
    except FileNotFoundError:
        print(
            "Playwright is not installed for this Python environment.\n"
            "Run: pip install -r requirements.txt\n"
            "Then: python -m playwright install",
            file=sys.stderr,
        )
        return 1

    if output_path.exists() and output_path.stat().st_size > 0:
        print(f"\nSaved recording to: {output_path}")
    else:
        print("\nThe browser closed, but the output file is empty or missing.")

    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())