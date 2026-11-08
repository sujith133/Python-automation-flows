"""
OnBlick session capture -> auto-generated Markdown documentation.

What it does
------------
1. Opens a real Chromium window at the URL you give it.
2. You browse / click / type in OnBlick exactly like a normal user.
   (Log in by hand in the window -- nothing is hardcoded.)
3. After every meaningful action (click, form change, navigation) it:
       - takes a screenshot,
       - records a human-readable description of the step.
4. When you close the window (or press Ctrl+C in the terminal) it writes
   a step-by-step Markdown doc with the screenshots embedded.

Your login is remembered between runs via a local browser profile folder,
so you only sign in once.

Usage
-----
    python onblick_capture.py https://your-onblick-url.com
    # or set it once:
    python onblick_capture.py            (defaults to OnBlick login page)

Output
------
    ./output/<run-name>/
        doc.md                 <- the documentation
        screenshots/000.png    <- one per step
        ...
    ./.profile/                <- persistent login (git-ignore this)
"""

import sys
import time
import datetime as _dt
from pathlib import Path

from playwright.sync_api import sync_playwright, Error as PWError

# ---------------------------------------------------------------- config
DEFAULT_URL = "https://app.onblick.com/"          # change if yours differs
ROOT = Path(__file__).resolve().parent
PROFILE_DIR = ROOT / ".profile"                   # persists your login
OUTPUT_ROOT = ROOT / "output"


# ---------------------------------------------------------------- recorder
class Recorder:
    """Collects steps and screenshots, then renders Markdown."""

    def __init__(self, run_dir: Path):
        self.run_dir = run_dir
        self.shots_dir = run_dir / "screenshots"
        self.shots_dir.mkdir(parents=True, exist_ok=True)
        self.steps: list[dict] = []
        self._last_sig = None          # de-dupe identical back-to-back events
        self._last_time = 0.0

    def add(self, page, kind: str, description: str):
        # collapse duplicate events fired within 400ms (e.g. click + change)
        sig = (kind, description)
        now = time.time()
        if sig == self._last_sig and (now - self._last_time) < 0.4:
            return
        self._last_sig = sig
        self._last_time = now

        idx = len(self.steps)
        shot_rel = f"screenshots/{idx:03d}.png"
        shot_abs = self.run_dir / shot_rel
        try:
            page.screenshot(path=str(shot_abs))
        except PWError:
            shot_rel = None            # page may be navigating/closed

        self.steps.append(
            {
                "n": idx + 1,
                "kind": kind,
                "desc": description,
                "url": _safe(lambda: page.url, ""),
                "title": _safe(lambda: page.title(), ""),
                "shot": shot_rel,
                "ts": _dt.datetime.now().strftime("%H:%M:%S"),
            }
        )
        print(f"  [{idx + 1:>3}] {kind:<10} {description[:70]}")

    def write_markdown(self):
        md = self.run_dir / "doc.md"
        lines = [
            f"# OnBlick walkthrough",
            "",
            f"_Captured {_dt.datetime.now():%Y-%m-%d %H:%M} — {len(self.steps)} steps_",
            "",
            "| # | Action | Description |",
            "|---|--------|-------------|",
        ]
        for s in self.steps:
            lines.append(
                f"| {s['n']} | {s['kind']} | {s['desc'].replace('|', '\\|')} |"
            )
        lines += ["", "---", ""]

        for s in self.steps:
            lines.append(f"## Step {s['n']} — {s['kind']}")
            lines.append("")
            lines.append(f"**{s['desc']}**")
            lines.append("")
            if s["title"]:
                lines.append(f"- Page: {s['title']}")
            if s["url"]:
                lines.append(f"- URL: `{s['url']}`")
            lines.append(f"- Time: {s['ts']}")
            lines.append("")
            if s["shot"]:
                lines.append(f"![Step {s['n']}]({s['shot']})")
            lines.append("")
        md.write_text("\n".join(lines), encoding="utf-8")
        return md


def _safe(fn, default):
    try:
        return fn()
    except Exception:
        return default


# ---------------------------------------------------------------- JS hook
# Injected into every page/frame. Reports user actions back to Python.
INIT_SCRIPT = r"""
(() => {
  // Guard on the document (not window): a replaced document loses its
  // listeners while window persists, so we must re-attach per document.
  if (document.__obCaptureInstalled) return;
  document.__obCaptureInstalled = true;

  const describe = (el) => {
    if (!el) return 'unknown element';
    const tag = el.tagName ? el.tagName.toLowerCase() : 'node';
    const txt = (el.innerText || el.value || el.getAttribute?.('aria-label')
                 || el.getAttribute?.('placeholder') || el.name || el.id || '')
                .toString().trim().replace(/\s+/g, ' ').slice(0, 60);
    const role = el.getAttribute?.('role');
    let label = tag;
    if (role) label += `[role=${role}]`;
    if (txt) label += ` "${txt}"`;
    return label;
  };

  const send = (kind, desc) => {
    try { window.__obStep(JSON.stringify({ kind, desc })); } catch (e) {}
  };

  // Report each loaded document as a navigation step.
  if (document.readyState === 'complete') {
    send('navigate', 'Opened ' + location.pathname + location.search);
  } else {
    window.addEventListener('load', () =>
      send('navigate', 'Opened ' + location.pathname + location.search), { once: true });
  }

  document.addEventListener('click', (e) => {
    const el = e.target.closest('button, a, [role=button], input, label, [onclick]') || e.target;
    send('click', 'Clicked ' + describe(el));
  }, true);

  document.addEventListener('change', (e) => {
    const el = e.target;
    const tag = (el.tagName || '').toLowerCase();
    if (tag === 'select') {
      const opt = el.options?.[el.selectedIndex]?.text || el.value;
      send('select', 'Selected "' + opt + '" in ' + describe(el));
    } else if (el.type === 'checkbox' || el.type === 'radio') {
      send('toggle', (el.checked ? 'Checked ' : 'Unchecked ') + describe(el));
    } else {
      send('input', 'Filled ' + describe(el));
    }
  }, true);

  document.addEventListener('submit', (e) => {
    send('submit', 'Submitted form ' + describe(e.target));
  }, true);
})();
"""


# ---------------------------------------------------------------- wiring
def main():
    url = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_URL
    stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = OUTPUT_ROOT / f"session-{stamp}"
    rec = Recorder(run_dir)

    print(f"\nOnBlick capture")
    print(f"  target : {url}")
    print(f"  output : {run_dir}")
    print(f"  profile: {PROFILE_DIR} (login is remembered here)\n")
    print("Browse OnBlick normally. Log in by hand if prompted.")
    print("Close the browser window (or press Ctrl+C) when done.\n")

    # IMPORTANT: Playwright's sync API deadlocks if you call any page method
    # (e.g. screenshot) from inside an event/binding callback. So the binding
    # callback only ENQUEUES the action; the main loop below takes the
    # screenshot and records the step where it is safe to do so.
    import json
    pending: list[tuple] = []

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=False,
            # no_viewport => the page fills the real (maximized) window instead
            # of a fixed size, so nothing on the right gets clipped.
            no_viewport=True,
            args=["--start-maximized"],
        )

        def on_step(source, payload):
            try:
                data = json.loads(payload)
            except Exception:
                return
            pending.append((source["page"], data.get("kind", "action"),
                            data.get("desc", "")))

        # Context-level binding + init script => EVERY page/popup is captured.
        context.expose_binding("__obStep", on_step)
        context.add_init_script(INIT_SCRIPT)

        closed = {"v": False}
        context.on("close", lambda: closed.__setitem__("v", True))

        page = context.pages[0] if context.pages else context.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded")
        except PWError as e:
            print(f"  (navigation note: {e})")

        # Keep alive until the user closes the browser. wait_for_timeout pumps
        # the event loop so binding callbacks fire; then we drain the queue.
        try:
            while not closed["v"] and context.pages:
                live = context.pages[-1]
                try:
                    live.wait_for_timeout(300)
                except PWError:
                    break
                while pending:
                    pg, kind, desc = pending.pop(0)
                    rec.add(pg, kind, desc)
        except KeyboardInterrupt:
            print("\nStopping (Ctrl+C)...")
        finally:
            # drain anything left, then close
            while pending:
                pg, kind, desc = pending.pop(0)
                rec.add(pg, kind, desc)
            try:
                context.close()
            except Exception:
                pass

    md = rec.write_markdown()
    print(f"\nDone. {len(rec.steps)} steps captured.")
    print(f"Documentation: {md}")
    print(f"Open it in VS Code to view with screenshots inline.\n")


if __name__ == "__main__":
    main()
