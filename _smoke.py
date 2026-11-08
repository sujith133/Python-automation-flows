import time, json, shutil
from pathlib import Path
from playwright.sync_api import sync_playwright
import onblick_capture as oc

run_dir = oc.OUTPUT_ROOT / "smoketest"
if run_dir.exists(): shutil.rmtree(run_dir)
rec = oc.Recorder(run_dir)

html = "<h1>Test</h1><button id=b>Hello</button><input id=i placeholder='name'><select id=s><option>A</option><option>B</option></select>"
data_url = "data:text/html," + html.replace(" ", "%20").replace("<","%3C").replace(">","%3E").replace("'","%27")

with sync_playwright() as p:
    ctx = p.chromium.launch(headless=True).new_context(viewport={"width":1200,"height":800})
    ctx.expose_binding("__obStep", lambda s,pl: rec.add(s["page"], json.loads(pl)["kind"], json.loads(pl)["desc"]))
    ctx.add_init_script(oc.INIT_SCRIPT)
    page = ctx.new_page()
    page.on("framenavigated", lambda f: f==page.main_frame and rec.add(page,"navigate",f"Opened {f.url[:40]}"))
    page.goto(data_url, wait_until="domcontentloaded")
    page.click("#b")
    page.fill("#i", "manikanta"); page.dispatch_event("#i","change")
    page.select_option("#s", label="B")
    page.wait_for_timeout(500)
    ctx.close()

md = rec.write_markdown()
print("STEPS:", len(rec.steps))
print("MD size:", md.stat().st_size)
print("Shots:", sorted(p.name for p in (run_dir/"screenshots").glob("*.png")))
print("---KINDS---", [s["kind"] for s in rec.steps])
