"""
flow_capture.py

Replays the recorded Lightspeed flow (recorded_flow.py) and saves a FULL-PAGE
(scrolled) screenshot of every screen into ./screenshots/NNN_<name>.png.

- Reuses a saved login session (auth_state.json) so re-runs skip sign-in.
- Before each screenshot, incrementally scrolls to the bottom to trigger any
  lazy-loaded content, then captures the whole page with full_page=True.
- Each click is wrapped so a single missing/renamed link won't abort the run.

Run:  python flow_capture.py
Env:  HEADLESS=1  -> run without a visible browser
"""

import os
import re
from pathlib import Path
from playwright.sync_api import sync_playwright

# ---------------------------------------------------------------- config
BASE = "https://studytestcompany.retail.lightspeed.app"
SIGNIN_URL = f"{BASE}/signin/"
DASHBOARD_URL = f"{BASE}/dashboards?tour_setup"

USERNAME = os.environ.get("LS_USER", "Logitest")
PASSWORD = os.environ.get("LS_PASS", "NewStudy@2026")

HERE = Path(__file__).resolve().parent
SHOTS = HERE / "screenshots"
AUTH = HERE / "auth_state.json"          # sensitive: holds a logged-in session
HEADLESS = os.environ.get("HEADLESS") == "1"
VIEWPORT = {"width": 1440, "height": 900}
PAUSE_MS = int(os.environ.get("PAUSE_MS", "2000"))   # dwell after each click
SLOW_MO = int(os.environ.get("SLOW_MO", "400"))      # ms between browser actions

SHOTS.mkdir(exist_ok=True)
_counter = 0


# ---------------------------------------------------------------- helpers
def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")[:50] or "screen"


# Scrolls every inner scroll container (and the window) to the bottom in steps to
# trigger lazy-loaded content, then back to the top.
_AUTOSCROLL_JS = """async () => {
    const sleep = ms => new Promise(r => setTimeout(r, ms));
    const scrollers = [document.scrollingElement].concat(
        [...document.querySelectorAll('*')].filter(el => {
            const oy = getComputedStyle(el).overflowY;
            return (oy === 'auto' || oy === 'scroll') && el.scrollHeight > el.clientHeight + 20;
        })
    );
    for (const el of scrollers) {
        let last = -1, steps = 0;
        while (steps++ < 300) {
            el.scrollTop = Math.min(el.scrollTop + 500, el.scrollHeight);
            await sleep(90);
            if (el.scrollTop === last) break;
            last = el.scrollTop;
        }
        el.scrollTop = 0;
    }
}"""

# Expands inner scroll containers so a single full_page=True capture includes
# below-the-fold content. Original inline styles are stashed for restore.
_EXPAND_JS = """() => {
    const scrollers = [...document.querySelectorAll('*')].filter(el => {
        const oy = getComputedStyle(el).overflowY;
        return (oy === 'auto' || oy === 'scroll') && el.scrollHeight > el.clientHeight + 20;
    });
    const touched = new Set();
    const mark = el => {
        if (!el || touched.has(el)) return;
        touched.add(el);
        el.setAttribute('data-pw-oldstyle', el.getAttribute('style') || '');
        el.style.setProperty('overflow', 'visible', 'important');
        el.style.setProperty('height', 'auto', 'important');
        el.style.setProperty('max-height', 'none', 'important');
        el.style.setProperty('min-height', '0', 'important');
        el.style.setProperty('flex', 'none', 'important');
    };
    // Expand each scroll container AND all of its ancestors (which are often
    // fixed 100vh flex boxes that would otherwise clip the expanded child).
    for (const s of scrollers) {
        let el = s;
        while (el && el !== document.documentElement) { mark(el); el = el.parentElement; }
    }
    document.documentElement.style.setProperty('height', 'auto', 'important');
    document.body.style.setProperty('height', 'auto', 'important');
    document.body.style.setProperty('overflow', 'visible', 'important');
    return scrollers.length;
}"""

_RESTORE_JS = """() => {
    for (const el of document.querySelectorAll('[data-pw-oldstyle]')) {
        el.setAttribute('style', el.getAttribute('data-pw-oldstyle'));
        el.removeAttribute('data-pw-oldstyle');
    }
}"""


def autoscroll(pg):
    try:
        pg.evaluate(_AUTOSCROLL_JS)
        pg.wait_for_timeout(200)
    except Exception:
        pass


def capture(pg, name: str):
    """Settle the page, trigger lazy content, expand inner scroll areas, then
    save one full-page (entire-scroll) screenshot."""
    global _counter
    _counter += 1
    fname = SHOTS / f"{_counter:03d}_{_slug(name)}.png"
    try:
        pg.wait_for_load_state("networkidle", timeout=12000)
    except Exception:
        pass
    autoscroll(pg)
    expanded = 0
    try:
        expanded = pg.evaluate(_EXPAND_JS)
        pg.wait_for_timeout(350)
    except Exception:
        pass
    try:
        pg.screenshot(path=str(fname), full_page=True)
        print(f"[{_counter:03d}] {fname.name}  (expanded {expanded} scroll area(s))")
    except Exception as e:
        print(f"[{_counter:03d}] FAILED {fname.name}: {e}")
    finally:
        try:
            pg.evaluate(_RESTORE_JS)
        except Exception:
            pass


def do(pg, label: str, action):
    """Capture the screen BEFORE the click, run the click/action, dwell (so it
    feels like real user interaction), then capture the screen AFTER. Never
    fatal — a failed action still leaves the 'before' shot."""
    capture(pg, f"{label}_before")
    try:
        action()
    except Exception as e:
        print(f"  ! skip '{label}': {type(e).__name__}: {str(e)[:80]}")
        return
    pg.wait_for_timeout(PAUSE_MS)
    capture(pg, f"{label}_after")


def dismiss_register_prompt(pg):
    """The Sell screen may show a 'This register has been open for N days'
    reconciliation prompt that covers the product area. Click 'Start selling
    anyway' (non-destructive) to get past it. No-op if not present."""
    try:
        link = pg.get_by_text("Start selling anyway")
        if link.count() > 0:
            link.first.click()
            pg.wait_for_timeout(800)
            print("  . dismissed 'register open' prompt")
    except Exception as e:
        print(f"  . register prompt skip: {type(e).__name__}: {str(e)[:70]}")


def select_register(pg, name="Main Register"):
    """The Sell screen opens with a 'Select Register' chooser (LifeStore tab,
    Main Register / Online register cards). Click the given register card.
    No-op if the chooser isn't present."""
    try:
        card = pg.get_by_text(name, exact=True)
        if card.count() > 0:
            card.first.click()
            pg.wait_for_timeout(2500)
            print(f"  . selected register '{name}'")
    except Exception as e:
        print(f"  . register select skip: {type(e).__name__}: {str(e)[:70]}")


def product_search(pg, name):
    """Type a product name into the Sell search box (data-testid=product-search)
    and click the exact-name result so the product opens — products aren't
    listed until searched."""
    box = pg.get_by_test_id("product-search")
    box.click()
    box.fill(name)
    pg.wait_for_timeout(1500)
    # Results render as .vd-id-badge__header-title (testid=badgeHeader); the
    # exact-name entry is the parent product to open.
    pg.get_by_test_id("badgeHeader").filter(
        has_text=re.compile(rf"^{re.escape(name)}$")).first.click()


def act(action):
    """Run an intermediate action (typing / focus) WITHOUT a screenshot.
    Used for fill/press keystrokes that are part of a larger interaction."""
    try:
        action()
    except Exception as e:
        print(f"  . act skip: {type(e).__name__}: {str(e)[:70]}")


def step(pg, label, action):
    """Run one recorded action, dwell, then capture ONE screenshot of the
    resulting screen. Never fatal — a failed action is logged and the screen
    is still captured so its state is visible."""
    ok = True
    try:
        action()
    except Exception as e:
        ok = False
        print(f"  ! skip '{label}': {type(e).__name__}: {str(e)[:80]}")
    pg.wait_for_timeout(PAUSE_MS if ok else 400)
    capture(pg, label)


def step_download(pg, label, action):
    """Like step(), but the action triggers a file download."""
    try:
        with pg.expect_download(timeout=15000) as di:
            action()
        print(f"  downloaded {di.value.suggested_filename}")
    except Exception as e:
        print(f"  ! skip '{label}': {type(e).__name__}: {str(e)[:80]}")
    pg.wait_for_timeout(PAUSE_MS)
    capture(pg, label)


def step_popup(pg, label, action):
    """Like step(), but the action opens a new tab/popup (the 'other tab' the
    recorded flow visits). Capture the popup and return it."""
    newp = None
    try:
        with pg.expect_popup(timeout=15000) as pi:
            action()
        newp = pi.value
        try:
            newp.wait_for_load_state("domcontentloaded", timeout=12000)
        except Exception:
            pass
        newp.wait_for_timeout(PAUSE_MS)
        capture(newp, f"{label}_popup")
    except Exception as e:
        print(f"  ! skip '{label}': {type(e).__name__}: {str(e)[:80]}")
        capture(pg, label)
    return newp


def ecwid(pg):
    """FrameLocator for the embedded Lightspeed eCom (Ecwid) admin iframe."""
    return pg.frame_locator('iframe[title="ecwid-frame"]')


# ---------------------------------------------------------------- flow
def safe_goto(pg, url, tries=3):
    """Navigate, tolerating net::ERR_ABORTED — the app fires a client-side
    redirect (e.g. the ?tour_setup tour) that aborts the original navigation
    even though the page itself loads fine."""
    for attempt in range(1, tries + 1):
        try:
            pg.goto(url, wait_until="domcontentloaded")
            return
        except Exception as e:
            msg = str(e)
            if "ERR_ABORTED" in msg:
                # The navigation was interrupted by the app's own redirect;
                # let it settle and treat the current page as loaded.
                try:
                    pg.wait_for_load_state("domcontentloaded", timeout=8000)
                except Exception:
                    pass
                return
            if attempt == tries:
                raise
            pg.wait_for_timeout(1000)


def login_if_needed(context, page):
    safe_goto(page, DASHBOARD_URL)
    if "signin" in page.url or page.get_by_test_id("userName").count() > 0:
        print("Signing in...")
        safe_goto(page, SIGNIN_URL)
        page.get_by_test_id("userName").fill(USERNAME)
        page.get_by_test_id("password").fill(PASSWORD)
        page.get_by_test_id("signin").click()
        page.wait_for_load_state("networkidle")
        context.storage_state(path=str(AUTH))
        print(f"Saved session -> {AUTH.name}")
        safe_goto(page, DASHBOARD_URL)
    else:
        print("Reused saved session.")


def run(playwright):
    # Start fresh: remove any screenshots from previous runs.
    for old in SHOTS.glob("*.png"):
        old.unlink()

    browser = playwright.chromium.launch(headless=HEADLESS, slow_mo=SLOW_MO)
    ctx_kwargs = {"viewport": VIEWPORT}
    if AUTH.exists():
        ctx_kwargs["storage_state"] = str(AUTH)
    context = browser.new_context(**ctx_kwargs)
    page = context.new_page()

    # --- Full app tour (mirrors recorded_flow.py, one screenshot per step) ----
    login_if_needed(context, page)
    capture(page, "dashboard")

    # --- Dashboard date range + top-seller tabs
    step(page, "dash_this_week", lambda: page.get_by_text("This week").click())
    step(page, "dash_today", lambda: page.get_by_text("Today").click())
    step(page, "dash_top_by_revenue", lambda: page.get_by_test_id("tab-button-topbyrevenue").click())
    step(page, "dash_top_by_count", lambda: page.get_by_test_id("tab-button-topbycount").click())

    # --- Sell -> pick register
    step(page, "sell", lambda: page.get_by_role("link", name=" Sell").first.click())
    select_register(page, "Main Register")
    dismiss_register_prompt(page)
    step(page, "retrieve_sale", lambda: page.get_by_role("button", name=" Retrieve sale").click())

    # --- Open / Close register (close then re-open)
    step(page, "open_close", lambda: page.get_by_role("link", name="Open / Close").click())
    step(page, "closure_row", lambda: page.locator(".PJLV > div:nth-child(6)").click())
    step(page, "col_expected", lambda: page.get_by_role("columnheader", name="Expected (Rs)").click())
    step(page, "col_expected_2", lambda: page.get_by_role("columnheader", name="Expected (Rs)").click())
    step(page, "col_counted", lambda: page.get_by_role("columnheader", name="Counted (Rs)").click())
    step(page, "col_differences", lambda: page.get_by_role("columnheader", name="Differences (Rs)").click())
    step(page, "add_register_note", lambda: page.get_by_role("textbox", name="Type to add a register").click())
    step(page, "note_field", lambda: page.locator("div").filter(has_text=re.compile(r"^Note$")).first.click())
    act(lambda: page.get_by_role("textbox", name="Type to add a register").click())
    act(lambda: page.get_by_role("textbox", name="Type to add a register").fill("hkjhj"))
    step(page, "close_register", lambda: page.get_by_role("button", name="Close register").click())
    act(lambda: page.get_by_role("textbox", name="Opening float ₹").click())
    act(lambda: page.get_by_role("textbox", name="Opening float ₹").click())
    act(lambda: page.get_by_role("textbox", name="Opening float ₹").fill("10000"))
    step(page, "open_register", lambda: page.get_by_role("button", name="Open Register").click())
    step(page, "goto_webregister", lambda: safe_goto(page, f"{BASE}/webregister/"))
    select_register(page, "Main Register")
    dismiss_register_prompt(page)

    # --- Sales history
    step(page, "sales_history", lambda: page.get_by_role("link", name="Sales history").click())
    step(page, "goto_sales_all", lambda: safe_goto(page, f"{BASE}/sales/all"))
    step(page, "sales_tab_completed", lambda: page.get_by_test_id("tab-button-completed").click())
    step(page, "sales_tab_continue", lambda: page.get_by_test_id("tab-button-continue").click())
    step(page, "sales_status_menu", lambda: page.get_by_text("AllProcess returnContinue sale").click())
    step(page, "sales_tab_all", lambda: page.get_by_test_id("tab-button-all").click())
    step_download(page, "sales_export_list", lambda: page.get_by_role("button", name=" Export list").click())

    # --- Cash management
    step(page, "cash_management", lambda: page.get_by_role("link", name="Cash management").click())
    step(page, "cash_row", lambda: page.get_by_role("cell", name="Jul 5, 2026, 1:58 PM").click())
    step(page, "remove_cash", lambda: page.get_by_role("button", name="Remove cash").click())
    step(page, "remove_cash_esc", lambda: page.get_by_role("button", name="ESC").click())
    step(page, "add_cash", lambda: page.get_by_role("button", name="Add cash").click())
    step(page, "add_cash_cancel", lambda: page.get_by_role("button", name="Cancel").click())
    step(page, "cash_user", lambda: page.get_by_text("LogiTest (LogiTest)").click())
    step(page, "cash_email", lambda: page.get_by_text("bavisetty.srinivas@gmail.com").click())

    # --- Status / Settings
    step(page, "status", lambda: page.get_by_role("link", name="Status").click())
    step(page, "reset_data", lambda: page.get_by_role("button", name="Reset data").click())
    step(page, "reset_data_cancel", lambda: page.get_by_role("button", name="Cancel").click())
    step(page, "settings", lambda: page.get_by_role("link", name="Settings").click())
    step(page, "settings_media", lambda: page.locator(".wr-media").first.click())
    step(page, "settings_checkbox_off", lambda: page.get_by_role("checkbox").uncheck())
    step(page, "settings_checkbox_on", lambda: page.get_by_role("checkbox").check())
    step(page, "enable_training_mode", lambda: page.get_by_role("button", name="Enable training mode").click())
    step(page, "training_esc", lambda: page.get_by_role("button", name="ESC").click())
    step(page, "enable_tutorial_off", lambda: page.get_by_role("checkbox", name="Enable tutorial").uncheck())

    # --- Training mode navigation
    step(page, "drawer_sell", lambda: page.get_by_test_id("SidebarDrawer").get_by_role("link", name="Sell").click())
    step(page, "topbar_home", lambda: page.get_by_test_id("TopbarContentItem").get_by_role("link", name="Home").click())
    step(page, "sell_again", lambda: page.get_by_role("link", name=" Sell").click())
    step(page, "drawer_item_1", lambda: page.get_by_test_id("SidebarDrawerItem").nth(1).click())
    step(page, "drawer_item_1b", lambda: page.get_by_test_id("SidebarDrawerItem").nth(1).click())
    step(page, "switch", lambda: page.get_by_role("button", name="Switch ").click())
    step(page, "popover_list_item", lambda: page.get_by_test_id("popover-list-item").click())
    step(page, "exit_training", lambda: page.get_by_role("button", name="Exit training").click())
    step(page, "switch_2", lambda: page.get_by_role("button", name="Switch ").click())
    step(page, "quick_key_grid", lambda: page.locator(".vd-quick-key-grid").click())
    step(page, "cash_management_2", lambda: page.get_by_role("link", name="Cash management").click())
    step(page, "status_2", lambda: page.get_by_role("link", name="Status").click())
    step(page, "settings_2", lambda: page.get_by_role("link", name="Settings").click())
    step(page, "edit_layout", lambda: page.get_by_role("listitem").filter(has_text="New layoutCurrent Layout").get_by_test_id("edit-layout-button").click())
    step(page, "settings_3", lambda: page.get_by_role("link", name="Settings").click())
    step(page, "quotes", lambda: page.get_by_role("link", name="Quotes").click())
    step(page, "goto_quotes", lambda: safe_goto(page, f"{BASE}/quotes"))
    step(page, "settings_4", lambda: page.get_by_role("link", name="Settings").click())
    step(page, "quotes_2", lambda: page.get_by_role("link", name="Quotes").click())

    # --- Online store (opens popup tabs)
    step(page, "online", lambda: page.get_by_role("link", name=" Online").click())
    step(page, "goto_online_overview", lambda: safe_goto(page, f"{BASE}/online/overview#dashboard"))
    page1 = step_popup(page, "online_edit_site", lambda: ecwid(page).get_by_role("button", name="Edit Site").click())
    if page1:
        step(page1, "online_editor", lambda: safe_goto(page1, "https://studytestcompany.company.site/editor?lang=en&from_admin#/"))
    page2 = step_popup(page, "online_ways_to_use", lambda: ecwid(page).get_by_role("link", name="Ways to use Lightspeed eCom").click())
    if page2:
        try:
            page2.close()
        except Exception:
            pass
    if page1:
        step(page1, "online_editor_2", lambda: safe_goto(page1, "https://studytestcompany.company.site/editor?lang=en&from_admin#/"))
        try:
            page1.close()
        except Exception:
            pass
    step(page, "online_store", lambda: page.get_by_role("link", name="Online store").click())
    step(page, "website", lambda: page.get_by_role("link", name="Website").click())
    step(page, "web_tab_categories", lambda: page.get_by_test_id("tab-button-categories").click())
    step(page, "web_tab_filters", lambda: page.get_by_test_id("tab-button-filters").click())
    step(page, "web_tab_overview", lambda: page.get_by_test_id("tab-button-overview").click())
    step(page, "web_tab_categories_2", lambda: page.get_by_test_id("tab-button-categories").click())
    step(page, "web_collapse_all", lambda: ecwid(page).get_by_text("Collapse All").click())
    step(page, "web_front_page", lambda: ecwid(page).get_by_text("Front page (0)").click())
    step(page, "web_categories_desc", lambda: page.get_by_text("A list of categories in your").click())
    step(page, "web_cell_dcscsc", lambda: ecwid(page).get_by_role("cell", name="dcscsc (0)", exact=True).click())
    step(page, "web_mensfashion", lambda: ecwid(page).get_by_text("mensfashion (0)").click())
    step(page, "web_tabbar", lambda: page.get_by_text("OverviewCategoriesFilters").click())
    step(page, "web_tabbar_2", lambda: page.get_by_text("OverviewCategoriesFilters").click())
    step(page, "web_tab_filters_2", lambda: page.get_by_test_id("tab-button-filters").click())
    step(page, "tiktok", lambda: page.get_by_role("link", name="TikTok").click())
    step(page, "settings_5", lambda: page.get_by_role("link", name="Settings").click())

    # --- Reporting
    step(page, "reporting", lambda: page.get_by_role("link", name=" Reporting").click())
    step(page, "report_week", lambda: page.get_by_text("Week").click())
    step(page, "report_month", lambda: page.get_by_text("Month").click())
    step(page, "report_outlet", lambda: page.locator("div").filter(has_text=re.compile(r"^Outlet$")).click())
    step(page, "report_lifestore_off", lambda: page.get_by_role("checkbox", name="LifeStore").uncheck())
    step(page, "report_multiselect", lambda: page.get_by_test_id("multiselect-popover-input").click())
    step(page, "report_multiselect_2", lambda: page.get_by_test_id("multiselect-popover-input").click())
    step(page, "report_all_outlets", lambda: page.get_by_role("listitem").filter(has_text="All outlets (1)").click())
    step(page, "report_prev_month", lambda: page.get_by_text("₹702UpPrevious month").click())
    step(page, "sales_reports", lambda: page.get_by_role("link", name="Sales reports").click())
    step(page, "goto_report_summary", lambda: safe_goto(page, f"{BASE}/reporting/summary?definition=%7B%22metric%22%3A%22total_revenue%22%2C%22constraints%22%3A%7B%22entities%22%3A%5B%5D%7D%2C%22granularity%22%3A%22week%22%2C%22periodType%22%3A%22last_n%22%2C%22periodCount%22%3A4%2C%22selectedDate%22%3A%222026-07-05T14%3A00%3A00%22%2C%22startDate%22%3A%222026-06-08T00%3A00%3A00%22%2C%22endDate%22%3A%222026-07-05T14%3A00%3A00%22%2C%22order%22%3A%5B%7B%22metric%22%3A%22total_revenue%22%2C%22dimension%22%3A%22summary%22%2C%22direction%22%3A%22desc%22%2C%22alphabetical%22%3Afalse%2C%22period%22%3Anull%7D%5D%2C%22dateGrouping%22%3A%22none%22%2C%22productGrouping%22%3A%22all%22%2C%22options%22%3A%7B%22includeGiftCards%22%3Afalse%7D%2C%22reportView%22%3A%22table%22%2C%22optionalAggregates%22%3A%5B%5D%2C%22dimensionMetadata%22%3A%5B%5D%7D&id=sale-summary&type=prepared"))
    step(page, "report_format_result", lambda: page.get_by_test_id("format-result-button").click())
    step(page, "report_by_weekday", lambda: page.get_by_text("By weekday").click())
    step(page, "report_by_hour", lambda: page.get_by_text("By hour", exact=True).click())
    step(page, "report_export", lambda: page.get_by_test_id("export-report-button").click())
    step(page, "report_chart", lambda: page.get_by_text("Chart").click())
    step(page, "inventory_reports", lambda: page.get_by_role("link", name="Inventory reports").click())
    step(page, "inv_tab_summary", lambda: page.get_by_test_id("tab-button-inventory-summary").click())
    step(page, "inv_tab_turns", lambda: page.get_by_test_id("tab-button-inventory-turns").click())
    step(page, "inv_tab_sell_through", lambda: page.get_by_test_id("tab-button-sell-through").click())
    step(page, "inv_tab_dusty", lambda: page.get_by_test_id("tab-button-dusty-inventory").click())
    step(page, "inv_tab_replenishment", lambda: page.get_by_test_id("tab-button-inventory-replenishment").click())
    step(page, "adjustment_reports", lambda: page.get_by_role("link", name="Adjustment reports").click())
    step(page, "adjustment_reports_2", lambda: page.get_by_role("link", name="Adjustment reports").click())
    step(page, "adj_actions", lambda: page.get_by_role("button", name="Actions...").click())
    step(page, "adj_overview", lambda: page.get_by_text("Get an overview of inventory").click())
    step(page, "cash_movement_reports", lambda: page.get_by_role("link", name="Cash movement reports").click())
    step(page, "payment_reports", lambda: page.get_by_role("link", name="Payment reports").click())
    step(page, "pay_actions", lambda: page.get_by_role("button", name="Actions...").click())
    step(page, "pay_actions_2", lambda: page.get_by_role("button", name="Actions...").click())
    step(page, "pay_report_type", lambda: page.locator("div").filter(has_text="Report type").nth(5).click())
    step(page, "pay_report_measure", lambda: page.locator("input[name=\"report-measure\"]").click())
    step(page, "pay_listitem", lambda: page.get_by_role("listitem").click())
    step(page, "pay_date_range", lambda: page.get_by_role("textbox", name="Choose date range…").click())
    step(page, "pay_format_export", lambda: page.get_by_text("Format results Export report").click())
    step(page, "pay_comparison", lambda: page.get_by_test_id("comparison-select").click())
    step(page, "pay_section", lambda: page.locator("section").nth(5).click())
    step(page, "register_closures", lambda: page.get_by_role("link", name="Register closures").click())
    step(page, "rc_select_register", lambda: page.get_by_label("Register").select_option("021b1f22-6825-11f1-e846-72df2f7de296"))
    step(page, "rc_register_menu", lambda: page.get_by_text("Register All Registers Main").click())
    step(page, "rc_select_all", lambda: page.get_by_label("Register").select_option(""))
    step_download(page, "rc_export_csv", lambda: page.get_by_role("link", name="Export CSV").click())
    step(page, "gift_card_reports", lambda: page.get_by_role("link", name="Gift card reports").click())
    step(page, "gc_section", lambda: page.locator("section").nth(1).click())
    step(page, "gc_number", lambda: page.get_by_role("textbox", name="Gift card number").click())
    step(page, "store_credit_reports", lambda: page.get_by_role("link", name="Store credit reports").click())
    step(page, "tax_reports", lambda: page.get_by_role("link", name="Tax reports").click())
    step(page, "tax_dropdown", lambda: page.get_by_test_id("dropdown-input-container").get_by_role("textbox").click())
    step(page, "tax_date_range", lambda: page.get_by_role("textbox", name="Choose date range…").click())
    step(page, "tax_week_to_date", lambda: page.get_by_role("radio", name="Week to date").check())
    step(page, "tax_week_menu", lambda: page.get_by_text("Week to datePrevious").click())
    step(page, "tax_section", lambda: page.locator("section").nth(5).click())
    step(page, "tax_more_filters", lambda: page.get_by_role("button", name="More filters").click())
    step(page, "tax_add_filter", lambda: page.get_by_role("textbox", name="Add a filter...").click())
    step(page, "user_reports", lambda: page.get_by_role("link", name="User reports").click())
    step(page, "ur_search", lambda: page.get_by_test_id("search-key-words").click())
    step(page, "ur_date_range", lambda: page.get_by_role("textbox", name="Choose date range…").click())
    step(page, "ur_date_range_2", lambda: page.get_by_role("textbox", name="Choose date range…").click())
    step(page, "ur_apply", lambda: page.get_by_role("button", name="Apply").click())
    step(page, "shared_reports", lambda: page.get_by_role("link", name="Shared reports").click())

    # --- Catalog
    step(page, "catalog", lambda: page.get_by_role("link", name=" Catalog").click())
    step(page, "goto_products", lambda: safe_goto(page, f"{BASE}/products?active=true&channelType=any&direction=ASC&field=NAME"))
    step(page, "add_product", lambda: page.get_by_test_id("add-product-button").click())
    step(page, "prod_tab_inventory", lambda: page.get_by_test_id("tab-button-inventory").click())
    step(page, "prod_tab_shipping", lambda: page.get_by_test_id("tab-button-shipping_and_delivery").click())
    step(page, "prod_tab_general", lambda: page.get_by_test_id("tab-button-general").click())
    step(page, "prod_group_similar", lambda: page.get_by_text("This is a group of similar").click())
    step(page, "prod_made_up_of", lambda: page.get_by_text("This product is made up of").click())
    step(page, "prod_tax_lifestore", lambda: page.get_by_test_id("tax-for-LifeStore").click())
    step(page, "prod_select", lambda: page.locator(".vd-popover-tether-target-wrapper.vd-popover-tether-target > .vd-autocomplete-input-container > .vd-select").click())
    step(page, "promotions", lambda: page.get_by_role("link", name="Promotions").click())
    step(page, "products", lambda: page.get_by_role("link", name="Products").click())
    step(page, "select_category", lambda: page.get_by_test_id("select-a-category-input").click())
    step(page, "select_category_2", lambda: page.get_by_test_id("select-a-category-input").click())
    step(page, "select_supplier", lambda: page.get_by_test_id("select-a-supplier-input").click())
    step(page, "select_brand", lambda: page.get_by_test_id("select-a-brand-input").click())
    step(page, "clear_filters", lambda: page.locator("div").filter(has_text="Clear filtersSearch").nth(3).click())
    step(page, "select_category_3", lambda: page.get_by_test_id("select-a-category-input").click())
    step(page, "products_section", lambda: page.locator("section").filter(has_text="Displaying 6 active products").nth(1).click())
    step(page, "table_cell", lambda: page.get_by_test_id("table-body-cell").nth(1).click())
    step(page, "products_2", lambda: page.get_by_role("link", name="Products").click())
    step(page, "products_3", lambda: page.get_by_role("link", name="Products").click())
    step(page, "promotions_2", lambda: page.get_by_role("link", name="Promotions").click())
    step(page, "promo_tab_past", lambda: page.get_by_test_id("tab-button-past").click())
    step(page, "promo_tab_all", lambda: page.get_by_test_id("tab-button-all").click())
    step(page, "promo_tab_current", lambda: page.get_by_test_id("tab-button-current & upcoming").click())
    step(page, "products_4", lambda: page.get_by_role("link", name="Products").click())
    step(page, "promotions_3", lambda: page.get_by_role("link", name="Promotions").click())
    step(page, "promo_tab_past_2", lambda: page.get_by_test_id("tab-button-past").click())
    step(page, "promo_tabbar", lambda: page.get_by_text("Current and upcomingPastAll").click())
    step(page, "promo_tab_all_2", lambda: page.get_by_test_id("tab-button-all").click())
    step(page, "promo_date", lambda: page.get_by_role("textbox", name="Date ").click())
    step(page, "promo_search", lambda: page.get_by_role("textbox", name="Search for promotions ").click())
    step(page, "promo_multiselect", lambda: page.get_by_test_id("multiselect-popover-input").click())
    step(page, "promo_multiselect_2", lambda: page.get_by_test_id("multiselect-popover-input").click())
    step(page, "price_books", lambda: page.get_by_role("link", name="Price books").click())
    step(page, "price_books_section", lambda: page.locator("section").filter(has_text="A list of all of your price").click())
    step(page, "price_btn_group", lambda: page.locator(".vd-btn-group").click())
    step(page, "goto_price_book", lambda: safe_goto(page, f"{BASE}/price_book"))
    step(page, "brands", lambda: page.get_by_role("link", name="Brands").click())
    step(page, "suppliers", lambda: page.get_by_role("link", name="Suppliers").click())
    step(page, "product_tags", lambda: page.get_by_role("link", name="Product tags").click())
    step(page, "product_categories", lambda: page.get_by_role("link", name="Product categories").click())
    step(page, "product_categories_2", lambda: page.get_by_role("link", name="Product categories").click())
    step(page, "adjustment_reasons", lambda: page.get_by_role("link", name="Adjustment reasons").click())
    step(page, "gift_cards", lambda: page.get_by_role("link", name="Gift cards").click())
    step(page, "adjustment_reasons_2", lambda: page.get_by_role("link", name="Adjustment reasons").click())
    step(page, "add_reason", lambda: page.get_by_role("button", name="Add reason").click())
    step(page, "add_reason_esc", lambda: page.get_by_role("button", name="ESC").click())
    step(page, "gift_cards_2", lambda: page.get_by_role("link", name="Gift cards").click())
    step(page, "gc_get_started", lambda: page.get_by_role("button", name="Get started").click())
    step(page, "gc_in_store", lambda: page.get_by_text("In-store only").click())
    step(page, "gc_online_only", lambda: page.locator("div").filter(has_text=re.compile(r"^Online only$")).first.click())
    step(page, "gc_sell", lambda: page.get_by_role("button", name="Sell gift cards").click())

    # --- Services
    step(page, "services", lambda: page.get_by_role("link", name=" Services").click())
    step(page, "statuses", lambda: page.get_by_role("link", name="Statuses").click())
    step(page, "add_status", lambda: page.get_by_role("button", name="Add status").click())
    step(page, "add_status_esc", lambda: page.get_by_role("button", name="ESC").click())

    # --- Inventory
    step(page, "inventory", lambda: page.get_by_role("link", name=" Inventory").click())
    step(page, "order_stock", lambda: page.get_by_role("link", name="Order stock").click())
    step(page, "order_cancel", lambda: page.get_by_test_id("cancel").click())
    step(page, "search_orders", lambda: page.get_by_role("textbox", name="Search orders ").click())
    step(page, "orders_tabbar", lambda: page.get_by_text("OrdersTransfersReturns").click())
    step(page, "tab_stock_transfer", lambda: page.get_by_test_id("tab-button-/inventory/stock-transfer").click())
    step(page, "tab_return", lambda: page.get_by_test_id("tab-button-/inventory/return").click())
    step(page, "inventory_counts", lambda: page.get_by_role("link", name="Inventory counts").click())
    step(page, "ic_tab_upcoming", lambda: page.get_by_test_id("tab-button-upcoming").click())
    step(page, "ic_tab_completed", lambda: page.get_by_test_id("tab-button-completed").click())
    step(page, "ic_tab_cancelled", lambda: page.get_by_test_id("tab-button-cancelled").click())
    step(page, "add_inventory_count", lambda: page.get_by_test_id("page-action-bar").get_by_role("link", name="Add inventory count").click())
    step(page, "ic_save_exit", lambda: page.get_by_test_id("save-and-exit").click())
    step(page, "special_orders", lambda: page.get_by_role("link", name="Special orders").click())
    step(page, "so_tab_ordered", lambda: page.get_by_test_id("tab-button-ordered").click())
    step(page, "so_tab_to_order", lambda: page.get_by_test_id("tab-button-to-order").click())
    step(page, "catalog_2", lambda: page.get_by_role("link", name=" Catalog").click())
    step(page, "inventory_2", lambda: page.get_by_role("link", name=" Inventory").click())
    step(page, "special_orders_2", lambda: page.get_by_role("link", name="Special orders").click())
    step(page, "fulfillments", lambda: page.get_by_role("link", name="Fulfillments").click())
    step(page, "ff_pack_orders", lambda: page.get_by_role("tab", name="Pack orders").click())
    step(page, "ff_pack_orders_2", lambda: page.get_by_role("tab", name="Pack orders").click())
    step(page, "ff_tabbar", lambda: page.get_by_text("AllPack ordersCustomer").click())
    step(page, "ff_delivery", lambda: page.get_by_role("tab", name="Delivery").click())
    step(page, "ff_customer_pickup", lambda: page.get_by_role("tab", name="Customer pickup").click())
    step(page, "ff_status", lambda: page.locator("div").filter(has_text=re.compile(r"^Status$")).click())
    step(page, "ff_multiselect", lambda: page.get_by_test_id("multiselect-popover-input").click())
    step(page, "serial_numbers", lambda: page.get_by_role("link", name="Serial numbers").click())
    step(page, "sn_autocomplete", lambda: page.get_by_test_id("search-filters-form").get_by_test_id("autocomplete-input").click())
    step(page, "sn_add", lambda: page.get_by_role("button", name="Add serial numbers").click())
    step(page, "sn_esc", lambda: page.get_by_role("button", name="ESC").click())

    # --- Customers
    step(page, "customers", lambda: page.get_by_role("link", name=" Customers").click())
    step(page, "cust_groups", lambda: page.get_by_role("link", name="Groups").click())
    step(page, "drawer_customers", lambda: page.get_by_test_id("SidebarDrawer").get_by_role("link", name="Customers").click())
    step(page, "add_customer", lambda: page.get_by_role("button", name="Add customer").click())
    step(page, "add_customer_esc", lambda: page.get_by_role("button", name="ESC").click())
    step(page, "edit_customer", lambda: page.get_by_role("button", name="Edit customer").click())
    step(page, "edit_customer_esc", lambda: page.get_by_role("button", name="ESC").click())
    step(page, "view_sales", lambda: page.get_by_role("link", name="View sales").click())
    step(page, "inventory_3", lambda: page.get_by_role("link", name=" Inventory").click())
    step(page, "customers_2", lambda: page.get_by_role("link", name=" Customers").click())
    step(page, "cust_tab_storecredit", lambda: page.get_by_test_id("tab-button-storecredit").click())
    step(page, "cust_tab_account", lambda: page.get_by_test_id("tab-button-account").click())
    step(page, "cust_tab_notes", lambda: page.get_by_test_id("tab-button-notesoncustomer").click())
    step(page, "cust_groups_2", lambda: page.get_by_role("link", name="Groups").click())
    step(page, "add_group", lambda: page.get_by_role("button", name="Add group").click())
    step(page, "add_group_esc", lambda: page.get_by_role("button", name="ESC").click())

    # --- Setup
    step(page, "setup", lambda: page.get_by_role("link", name=" Setup").click())
    step(page, "store_name", lambda: page.get_by_role("textbox", name="Store name").click())
    step(page, "store_name_2", lambda: page.get_by_role("textbox", name="Store name").click())
    step(page, "store_name_3", lambda: page.get_by_role("textbox", name="Store name").click())
    step(page, "default_currency", lambda: page.get_by_role("textbox", name="Default currency").click())
    step(page, "time_zone", lambda: page.get_by_role("textbox", name="Time zone").click())
    step(page, "barcodes", lambda: page.get_by_role("textbox", name="Select what kind of barcodes").click())
    step(page, "barcodes_2", lambda: page.get_by_role("textbox", name="Select what kind of barcodes").click())
    step(page, "billing", lambda: page.get_by_role("link", name="Billing").click())
    step(page, "billing_flex", lambda: page.locator(".vd-flex").click())
    step(page, "save_billing", lambda: page.get_by_role("button", name="Save billing details").click())
    act(lambda: page.get_by_role("button", name="Save billing details").press("Escape"))
    step(page, "billing_overlay", lambda: page.get_by_test_id("overlay").click())
    step(page, "save_billing_2", lambda: page.get_by_role("button", name="Save billing details").click())
    step(page, "billing_autocomplete", lambda: page.get_by_test_id("scrollable").get_by_test_id("autocomplete-input").click())
    act(lambda: page.get_by_test_id("scrollable").get_by_test_id("autocomplete-input").fill("nhhg"))
    step(page, "save_billing_3", lambda: page.get_by_role("button", name="Save billing details").click())
    step(page, "billing_autocomplete_2", lambda: page.get_by_test_id("scrollable").get_by_test_id("autocomplete-input").click())
    act(lambda: page.get_by_test_id("scrollable").get_by_test_id("autocomplete-input").fill("@gmail.co"))
    step(page, "billing_solymail", lambda: page.get_by_role("link", name="SolyMail - Correos").click())
    step(page, "save_billing_4", lambda: page.get_by_role("button", name="Save billing details").click())
    step(page, "enter_payment_details", lambda: page.get_by_role("button", name="Enter payment details and").click())
    step(page, "payment_cancel", lambda: page.get_by_role("button", name="Cancel").click())
    step(page, "outlets_registers", lambda: page.get_by_role("link", name="Outlets and registers").click())
    step(page, "outlets_registers_2", lambda: page.get_by_role("link", name="Outlets and registers").click())
    step(page, "receipts", lambda: page.get_by_role("link", name="Receipts").click())
    step(page, "outlets_registers_tab", lambda: page.get_by_role("tablist").get_by_role("link", name="Outlets and registers").click())
    step(page, "add_outlet", lambda: page.get_by_role("button", name="Add outlet").click())
    step(page, "add_outlet_esc", lambda: page.get_by_role("button", name="ESC").click())
    step(page, "receipts_2", lambda: page.get_by_role("link", name="Receipts").click())
    step(page, "add_receipt_template", lambda: page.get_by_role("button", name="Add receipt template").click())
    step(page, "add_receipt_cancel", lambda: page.get_by_role("button", name="Cancel").click())
    step(page, "devices_label_printing", lambda: page.get_by_role("link", name="Devices and label printing").click())
    step(page, "devices_tabbar", lambda: page.get_by_text("DevicesLabel printing").click())
    step(page, "tab_label_printing", lambda: page.get_by_test_id("tab-button-tab-label-printing").click())
    step(page, "tab_devices", lambda: page.get_by_test_id("tab-button-tab-devices").click())
    step(page, "payment_types", lambda: page.get_by_role("link", name="Payment types").click())
    step(page, "add_payment_type", lambda: page.get_by_test_id("add-payment-type-button").click())
    step(page, "add_payment_type_esc", lambda: page.get_by_role("button", name="ESC").click())
    step(page, "add_payment_type_2", lambda: page.get_by_test_id("add-payment-type-button").click())
    step(page, "choose_payment_type", lambda: page.get_by_role("textbox", name="Choose a payment type").click())
    step(page, "choose_payment_type_esc", lambda: page.get_by_role("button", name="ESC").click())
    step(page, "on_account", lambda: page.get_by_role("link", name="On-account").click())
    step(page, "sales_taxes", lambda: page.get_by_role("link", name="Sales taxes").click())
    step(page, "loyalty", lambda: page.get_by_role("link", name="Loyalty").click())
    step(page, "users", lambda: page.get_by_role("link", name="Users").click())
    step(page, "users_tabbar", lambda: page.get_by_text("UsersRolesActivity").click())
    step(page, "users_tabbar_2", lambda: page.get_by_text("UsersRolesActivity").click())
    step(page, "roles", lambda: page.get_by_role("link", name="Roles").click())
    step(page, "users_tabbar_3", lambda: page.get_by_text("UsersRolesActivity").click())
    step(page, "users_tab", lambda: page.get_by_role("tablist").get_by_role("link", name="Users").click())
    step(page, "activity", lambda: page.get_by_role("link", name="Activity").click())
    step(page, "users_tab_2", lambda: page.get_by_role("tablist").get_by_role("link", name="Users").click())
    step(page, "add_user", lambda: page.get_by_role("button", name="Add user").click())
    step(page, "add_user_save", lambda: page.get_by_role("button", name="Save").click())
    step(page, "user_back_link", lambda: page.get_by_role("main").get_by_role("link").filter(has_text=re.compile(r"^$")).click())
    step(page, "roles_2", lambda: page.get_by_role("link", name="Roles").click())
    step(page, "add_role", lambda: page.locator("span").filter(has_text="Add role").click())
    step(page, "add_role_cancel", lambda: page.get_by_role("button", name="Cancel").click())
    step(page, "activity_2", lambda: page.get_by_role("link", name="Activity").click())
    step(page, "security", lambda: page.get_by_role("link", name="Security").click())
    step(page, "sec_only_login", lambda: page.get_by_role("radio", name="Only has access to log in").check())
    step(page, "sec_has_access", lambda: page.get_by_role("radio", name="Has access to log in", exact=True).check())
    step(page, "sec_only_login_2", lambda: page.get_by_role("radio", name="Only has access to log in").check())
    step(page, "sec_save", lambda: page.get_by_role("button", name="Save changes").click())
    step(page, "sec_ok_got_it", lambda: page.get_by_role("button", name="OK, got it").click())
    step(page, "apps", lambda: page.get_by_role("link", name="Apps").click())
    step(page, "apps_tab_directory", lambda: page.get_by_test_id("tab-button-tab-directory").click())
    step(page, "apps_tabbar", lambda: page.get_by_text("ConnectedDirectory").click())
    step(page, "store_credit", lambda: page.get_by_role("link", name="Store credit").click())
    step(page, "workflows", lambda: page.get_by_role("link", name="Workflows").click())
    step(page, "wf_tab_rules", lambda: page.get_by_test_id("tab-button-/rules").click())
    step(page, "wf_tab_events", lambda: page.get_by_test_id("tab-button-/events").click())
    step(page, "wf_tab_custom_fields", lambda: page.get_by_test_id("tab-button-/custom-fields").click())
    step(page, "add_custom_field", lambda: page.get_by_role("button", name="Add custom field").click())
    step(page, "add_custom_field_esc", lambda: page.get_by_role("button", name="ESC").click())
    step(page, "wf_tab_rules_2", lambda: page.get_by_test_id("tab-button-/rules").click())
    step(page, "add_business_rule", lambda: page.get_by_role("button", name="Add business rule").click())
    step(page, "add_business_rule_esc", lambda: page.get_by_role("button", name="ESC").click())
    step(page, "wf_tab_events_2", lambda: page.get_by_test_id("tab-button-/events").click())
    step(page, "saved_payment_methods", lambda: page.get_by_role("link", name="Saved payment methods").click())
    step(page, "show_menu", lambda: page.get_by_title("Show menu").click())
    step(page, "hide_menu", lambda: page.get_by_title("Hide menu").click())
    step(page, "home", lambda: page.get_by_role("link", name=" Home").click())

    print(f"\nDone. {_counter} screenshots in {SHOTS}")
    context.close()
    browser.close()


if __name__ == "__main__":
    with sync_playwright() as p:
        run(p)
