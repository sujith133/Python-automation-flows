import re
from pathlib import Path
from playwright.sync_api import Playwright, Locator, sync_playwright, expect

# Pause this many ms after EVERY click event (lets API calls finish loading).
CLICK_PAUSE_MS = 2000

# Screenshots are saved here, one per click (000.png, 001.png, ...).
SHOTS = Path(__file__).resolve().parent / "codegen_shots"
SHOTS.mkdir(exist_ok=True)
_shot_n = 0

# Wrap Locator.click so each (non text-field) click saves a BEFORE and AFTER
# screenshot, with a pause in between for API loads. Clicks into text inputs
# (Name/Email/Phone/Card/CVV...) are skipped -- we only document real actions.
_orig_click = Locator.click


def _is_text_field(locator):
    """True if the locator points at a text input / textarea / editable box."""
    try:
        return bool(locator.evaluate(
            """(el) => {
                const tag = el.tagName ? el.tagName.toLowerCase() : '';
                if (tag === 'textarea') return true;
                if (tag === 'input') {
                    const t = (el.getAttribute('type') || 'text').toLowerCase();
                    return ['text','email','tel','number','password','search','url',''].includes(t);
                }
                return el.isContentEditable === true;
            }"""
        ))
    except Exception:
        return False


def _shot(page, label):
    try:
        page.screenshot(path=str(SHOTS / f"{_shot_n:03d}_{label}.png"))
    except Exception as e:
        print(f"  [click {_shot_n:>3}] {label} screenshot skipped: {e}")


def _click_with_pause(self, *args, **kwargs):
    global _shot_n
    text_field = _is_text_field(self)
    if not text_field:
        _shot(self.page, "before")
    result = _orig_click(self, *args, **kwargs)
    self.page.wait_for_timeout(CLICK_PAUSE_MS)
    if not text_field:
        _shot(self.page, "after")
        print(f"  [click {_shot_n:>3}] before + after saved")
        _shot_n += 1
    return result


Locator.click = _click_with_pause


def run(playwright: Playwright) -> None:
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context()
    page = context.new_page()
    page.goto("https://yellow-flower-00da32610.7.azurestaticapps.net/store/kritunga/menu")
    page.get_by_role("button", name="DD2- Okatree").click()
    page.get_by_role("button", name="View More").first.click()
    page.locator(".relative.inline-flex.items-center.justify-center").first.click()
    page.get_by_role("button", name="Add").click()
    page.get_by_role("button", name="Cart").click()
    page.get_by_role("button", name="Proceed to checkout").click()
    page.get_by_role("textbox", name="Name Name*").click()
    page.get_by_role("textbox", name="Name Name*").fill("twst")
    page.get_by_role("textbox", name="Email Email*").click()
    page.get_by_role("textbox", name="Email Email*").fill("sujith@gmail.com")
    page.get_by_role("textbox", name="Phone Phone*").click()
    page.get_by_role("textbox", name="Phone Phone*").fill("123-456-7890")
    page.locator(".mt-4 > .group > .relative.inline-flex > .z-10").click()
    page.get_by_role("button", name="Proceed to pay $60.98 →").click()
    page.locator("#CollectJSInlineccnumber").content_frame.get_by_role("textbox", name="Card Number").click()
    page.locator("#CollectJSInlineccnumber").content_frame.get_by_role("textbox", name="Card Number").fill("4111 1111 1111 1111")
    page.locator("#CollectJSInlineccexp").content_frame.get_by_role("textbox", name="MM / YY").click()
    page.locator("#CollectJSInlineccnumber").content_frame.get_by_role("textbox", name="Card Number").fill("4111 1111 1111 1111")
    page.locator("#CollectJSInlineccexp").content_frame.get_by_role("textbox", name="MM / YY").fill("12 / 26")
    page.locator("#CollectJSInlinecvv").content_frame.get_by_role("textbox", name="CVV").click()
    page.locator("#CollectJSInlinecvv").content_frame.get_by_role("textbox", name="CVV").fill("123")
    page.get_by_role("button", name="Pay $").click()
    page.goto("https://yellow-flower-00da32610.7.azurestaticapps.net/payment-success?session_id=3726935b-198d-43c7-a7b7-90ecba825927")
    page.get_by_role("button", name="Continue Browsing").click()
    page.close()

    # ---------------------
    context.close()
    browser.close()


with sync_playwright() as playwright:
    run(playwright)
