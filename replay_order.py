"""
Replay of the captured OnBlick / online-ordering checkout flow.

Generated from: output/session-20260623-192255/doc.md

HOW RELIABLE IS THIS?
---------------------
The capture recorded human-readable LABELS (button/field text), not exact CSS
selectors, so this script targets elements by role / placeholder / text. That is
robust for the food-ordering portion but you may need to tweak a locator if the
page has two elements with the same text.

Two parts behave very differently:

  * Steps 1-23  (menu -> cart -> checkout -> customer details)
        Replays reliably on the store URL below.

  * Steps 24-42 (PAYMENT)
        The card fields are served from a DIFFERENT domain
        (pre-prod.chefgaa.com) inside payment-gateway IFRAMES, and the original
        checkout URL carried a ONE-TIME token + session id that is now expired.
        You cannot replay the old token. The payment block below is written
        against the *live* iframes that appear after "Proceed to pay", but
        treat it as a starting point -- gateway DOM/timng may differ.

Run:
    python replay_order.py
    python replay_order.py --headless        # no visible window
    python replay_order.py --pause-on-pay    # stop before submitting payment
"""

import sys
from playwright.sync_api import sync_playwright

# ----------------------------------------------------------------- config
STORE_URL = "https://yellow-flower-00da32610.7.azurestaticapps.net/store/kritunga/menu"

CUSTOMER = {
    "name":  "tester",
    "email": "test@chefgaa.com",
    "phone": "122-345-2133",
}

# Test card (Visa test PAN). Only valid on the payment sandbox.
CARD = {
    "number": "4111 1111 1111 1111",
    "expiry": "12 / 28",
    "cvv":    "123",
}

HEADLESS     = "--headless" in sys.argv
PAUSE_ON_PAY = "--pause-on-pay" in sys.argv


def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS, args=["--start-maximized"])
        ctx = browser.new_context(no_viewport=True)
        page = ctx.new_page()

        # --- Step 1: open the menu ------------------------------------
        page.goto(STORE_URL, wait_until="domcontentloaded")

        # --- Steps 2-6: first item -> "Spicy" -> Add ------------------
        # NOTE: ".first" because the menu has many "View More" / "Add" buttons.
        page.get_by_role("button", name="View More").first.click()
        page.get_by_text("Spicy", exact=True).first.click()
        page.get_by_role("button", name="Add").first.click()

        # --- Steps 7-11: second item -> "Extra Spicy" -> Add ----------
        page.get_by_role("button", name="View More").first.click()
        page.get_by_text("Extra Spicy", exact=False).first.click()
        page.get_by_role("button", name="Add").first.click()

        # --- Step 12-13: open cart, proceed to checkout ---------------
        # The captured run clicked a quantity/badge "3" then checkout.
        page.get_by_role("button", name="Proceed to checkout").click()

        # --- Steps 14-16: accept Terms & Conditions checkbox ----------
        page.get_by_text("By checking, you agree", exact=False).first.click()

        # --- Steps 17-22: customer details ----------------------------
        page.get_by_placeholder("Name").fill(CUSTOMER["name"])
        page.get_by_placeholder("Email").fill(CUSTOMER["email"])
        page.get_by_placeholder("Phone").fill(CUSTOMER["phone"])

        # --- Step 23: proceed to pay ----------------------------------
        page.get_by_role("button", name="Proceed to pay").click()

        # =============================================================
        # PAYMENT (steps 24-42) -- cross-origin gateway iframes.
        # The fields live in iframes whose name/placeholder is "Card Number",
        # "MM / YY", "CVV". frame_locator drills into them. If the gateway
        # changed, inspect the live page and adjust these locators.
        # =============================================================
        page.wait_for_timeout(4000)  # let the gateway iframes load

        try:
            # Card number, expiry and cvv are typically three separate iframes;
            # target each by its placeholder text inside the matching iframe:
            page.frame_locator('iframe[id*="ccnumber"], iframe[src*="ccnumber"]') \
                .get_by_placeholder("Card Number").fill(CARD["number"])
            page.frame_locator('iframe[id*="ccexp"], iframe[src*="ccexp"]') \
                .get_by_placeholder("MM / YY").fill(CARD["expiry"])
            page.frame_locator('iframe[id*="cvv"], iframe[src*="cvv"]') \
                .get_by_placeholder("CVV").fill(CARD["cvv"])
        except Exception as e:
            print(f"[payment] iframe locators need adjustment: {e}")
            print("[payment] Pausing so you can fill the card fields by hand...")
            page.pause()

        if PAUSE_ON_PAY:
            print("[payment] --pause-on-pay set; not submitting. Inspector open.")
            page.pause()
        else:
            # --- Step 39-40: submit payment ---------------------------
            page.get_by_role("button", name="Pay").click()
            # --- Step 41: success -------------------------------------
            page.wait_for_url("**/payment-success**", timeout=30000)
            print("[done] Reached payment-success page.")

        ctx.close()
        browser.close()


if __name__ == "__main__":
    run()
