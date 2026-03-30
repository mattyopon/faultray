"""E2E test: Visit all 17+ pages, take screenshots, click all buttons."""
import os
import json
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

BASE_URL = "https://faultray.com"
SCREENSHOT_DIR = "/home/user/repos/faultray-app/tests/screenshots"

PAGES = [
    ("/", "Landing Page"),
    ("/login", "Login"),
    ("/dashboard", "Dashboard"),
    ("/pricing", "Pricing"),
    ("/topology", "Topology"),
    ("/heatmap", "Heatmap"),
    ("/whatif", "What-If"),
    ("/compliance", "Compliance"),
    ("/score-detail", "Score Detail"),
    ("/cost", "Cost Analysis"),
    ("/security", "Security"),
    ("/fmea", "FMEA"),
    ("/advisor", "AI Advisor"),
    ("/reports", "Reports"),
    ("/incidents", "Incidents"),
    ("/benchmark", "Benchmark"),
    ("/simulate", "Simulate"),
    ("/results", "Results"),
    ("/suggestions", "Suggestions"),
    ("/settings", "Settings"),
    ("/demo", "Demo"),
]


def run_tests():
    os.makedirs(SCREENSHOT_DIR, exist_ok=True)
    results = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1440, "height": 900},
            ignore_https_errors=True,
        )
        page = context.new_page()

        for path, name in PAGES:
            url = f"{BASE_URL}{path}"
            page_result = {
                "page": name,
                "path": path,
                "url": url,
                "status": "OK",
                "screenshot": None,
                "buttons_found": 0,
                "buttons_clicked": 0,
                "buttons_unresponsive": [],
                "errors": [],
            }

            try:
                # Navigate
                resp = page.goto(url, wait_until="networkidle", timeout=15000)
                if resp:
                    page_result["http_status"] = resp.status

                # Wait a moment for client rendering
                page.wait_for_timeout(1500)

                # Screenshot
                ss_file = f"{SCREENSHOT_DIR}/{name.lower().replace(' ', '_')}.png"
                page.screenshot(path=ss_file, full_page=True)
                page_result["screenshot"] = ss_file

                # Find all clickable buttons (button elements, [role=button])
                buttons = page.query_selector_all(
                    "button:visible, a.btn:visible, [role='button']:visible"
                )
                page_result["buttons_found"] = len(buttons)

                # Try clicking each button
                for i, btn in enumerate(buttons):
                    btn_text = ""
                    try:
                        btn_text = (btn.inner_text() or "").strip()[:50]
                    except Exception:
                        pass

                    # Skip navigation links that would leave the page
                    tag = btn.evaluate("el => el.tagName").lower()
                    href = btn.get_attribute("href") or ""
                    if tag == "a" and href and not href.startswith("#") and not href.startswith("javascript"):
                        continue

                    # Skip OAuth buttons (would redirect to external providers)
                    if any(
                        kw in btn_text.lower()
                        for kw in ["github", "google", "sign in", "sign out", "log out"]
                    ):
                        continue

                    try:
                        # Listen for console errors
                        errors_before = []
                        page.on("console", lambda msg: errors_before.append(msg.text) if msg.type == "error" else None)

                        btn.click(timeout=3000, force=True)
                        page.wait_for_timeout(500)
                        page_result["buttons_clicked"] += 1

                    except PlaywrightTimeout:
                        page_result["buttons_unresponsive"].append(btn_text or f"button_{i}")
                    except Exception as e:
                        err_msg = str(e)[:100]
                        if "detached" not in err_msg.lower() and "intercept" not in err_msg.lower():
                            page_result["errors"].append(
                                f"Button '{btn_text}': {err_msg}"
                            )

                # After clicking, take another screenshot
                try:
                    ss_after = f"{SCREENSHOT_DIR}/{name.lower().replace(' ', '_')}_after.png"
                    page.screenshot(path=ss_after, full_page=True)
                except Exception:
                    pass

            except Exception as e:
                page_result["status"] = "ERROR"
                page_result["errors"].append(str(e)[:200])

            results.append(page_result)
            print(f"  {'OK' if page_result['status'] == 'OK' else 'ERR'} {name:20s} "
                  f"buttons={page_result['buttons_found']} "
                  f"clicked={page_result['buttons_clicked']} "
                  f"unresponsive={len(page_result['buttons_unresponsive'])}")

        browser.close()

    # Summary
    print("\n" + "=" * 60)
    print("E2E TEST SUMMARY")
    print("=" * 60)
    total_pages = len(results)
    ok_pages = sum(1 for r in results if r["status"] == "OK")
    total_buttons = sum(r["buttons_found"] for r in results)
    total_clicked = sum(r["buttons_clicked"] for r in results)
    total_unresponsive = sum(len(r["buttons_unresponsive"]) for r in results)

    print(f"Pages tested:     {ok_pages}/{total_pages}")
    print(f"Total buttons:    {total_buttons}")
    print(f"Buttons clicked:  {total_clicked}")
    print(f"Unresponsive:     {total_unresponsive}")

    if total_unresponsive > 0:
        print("\nUnresponsive buttons:")
        for r in results:
            for btn in r["buttons_unresponsive"]:
                print(f"  [{r['page']}] {btn}")

    errors = [(r["page"], e) for r in results for e in r["errors"]]
    if errors:
        print(f"\nErrors ({len(errors)}):")
        for pg, err in errors:
            print(f"  [{pg}] {err}")

    # Save JSON report
    report_path = f"{SCREENSHOT_DIR}/report.json"
    with open(report_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nReport saved: {report_path}")

    return results


if __name__ == "__main__":
    run_tests()
