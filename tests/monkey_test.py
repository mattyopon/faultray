"""FaultRay Streamlit UI — モンキーテスト（自動ランダム操作テスト）.

Playwrightで画面要素をランダムにクリック・入力し、
クラッシュ・エラー・例外が発生しないかを検証する。
"""

import random
import time
import json
from datetime import datetime
import pytest

pw = pytest.importorskip("playwright.sync_api", reason="playwright not installed")
sync_playwright = pw.sync_playwright
Page = pw.Page
PlaywrightTimeout = pw.TimeoutError

BASE_URL = "http://localhost:8501"
TOTAL_ACTIONS = 100
RESULTS = {
    "total_actions": 0,
    "clicks": 0,
    "inputs": 0,
    "selects": 0,
    "errors_found": [],
    "console_errors": [],
    "crashes": [],
    "screenshots": [],
    "start_time": None,
    "end_time": None,
}

RANDOM_INPUTS = [
    "",  # 空文字
    "test",
    "'; DROP TABLE users; --",  # SQLインジェクション
    "<script>alert('xss')</script>",  # XSS
    "a" * 10000,  # 超長文字列
    "日本語テスト",
    "0",
    "-1",
    "999999999",
    "null",
    "undefined",
    "true",
    "false",
    "../../../etc/passwd",  # パストラバーサル
    "${7*7}",  # テンプレートインジェクション
    "{{7*7}}",
]


def collect_console_errors(page: Page) -> None:
    """ブラウザコンソールのエラーを収集."""
    page.on("console", lambda msg: (
        RESULTS["console_errors"].append({
            "type": msg.type,
            "text": msg.text,
            "url": page.url,
            "time": datetime.now().isoformat(),
        })
        if msg.type == "error" else None
    ))

    page.on("pageerror", lambda err: (
        RESULTS["crashes"].append({
            "error": str(err),
            "url": page.url,
            "time": datetime.now().isoformat(),
        })
    ))


def get_clickable_elements(page: Page) -> list:
    """クリック可能な要素を全て取得."""
    selectors = [
        "button",
        "a",
        "[role='button']",
        "input[type='checkbox']",
        "input[type='radio']",
        ".stButton > button",
        ".stSelectbox > div",
        ".stRadio > div > label",
        ".stCheckbox > label",
        ".stTab > button",
        "[data-testid]",
        ".stExpander > summary",
        "summary",
    ]
    elements = []
    for sel in selectors:
        try:
            found = page.query_selector_all(sel)
            elements.extend(found)
        except Exception:
            pass
    return elements


def get_input_elements(page: Page) -> list:
    """入力可能な要素を全て取得."""
    selectors = [
        "input[type='text']",
        "input[type='number']",
        "textarea",
        ".stTextInput input",
        ".stNumberInput input",
        ".stTextArea textarea",
    ]
    elements = []
    for sel in selectors:
        try:
            found = page.query_selector_all(sel)
            elements.extend(found)
        except Exception:
            pass
    return elements


def get_select_elements(page: Page) -> list:
    """セレクトボックスを取得."""
    selectors = [
        "select",
        ".stSelectbox",
    ]
    elements = []
    for sel in selectors:
        try:
            found = page.query_selector_all(sel)
            elements.extend(found)
        except Exception:
            pass
    return elements


def check_for_errors(page: Page, action_desc: str) -> None:
    """画面上のエラー表示を検出."""
    error_selectors = [
        ".stException",
        ".stError",
        "[data-testid='stException']",
        ".element-container .stAlert",
    ]
    for sel in error_selectors:
        try:
            errors = page.query_selector_all(sel)
            for err in errors:
                text = err.inner_text()
                if text and len(text) > 5:
                    RESULTS["errors_found"].append({
                        "type": "ui_error",
                        "selector": sel,
                        "text": text[:500],
                        "action": action_desc,
                        "url": page.url,
                        "time": datetime.now().isoformat(),
                    })
        except Exception:
            pass


def do_random_action(page: Page, action_num: int) -> str:
    """ランダムなアクションを1つ実行."""
    action_type = random.choices(
        ["click", "input", "select", "scroll", "navigate"],
        weights=[50, 20, 10, 10, 10],
        k=1,
    )[0]

    desc = f"action_{action_num}: "

    try:
        if action_type == "click":
            elements = get_clickable_elements(page)
            if elements:
                el = random.choice(elements)
                tag = el.evaluate("e => e.tagName") or "?"
                text = (el.inner_text() or "")[:30]
                desc += f"click [{tag}] '{text}'"
                el.click(timeout=3000, force=True)
                RESULTS["clicks"] += 1
            else:
                desc += "click (no elements found)"

        elif action_type == "input":
            elements = get_input_elements(page)
            if elements:
                el = random.choice(elements)
                value = random.choice(RANDOM_INPUTS)
                desc += f"input '{value[:20]}'"
                el.fill("")
                el.fill(value)
                RESULTS["inputs"] += 1
            else:
                desc += "input (no elements found)"

        elif action_type == "select":
            elements = get_select_elements(page)
            if elements:
                el = random.choice(elements)
                desc += "select (click to open)"
                el.click(timeout=3000, force=True)
                RESULTS["selects"] += 1
            else:
                desc += "select (no elements found)"

        elif action_type == "scroll":
            direction = random.choice(["up", "down"])
            amount = random.randint(100, 800)
            desc += f"scroll {direction} {amount}px"
            if direction == "down":
                page.mouse.wheel(0, amount)
            else:
                page.mouse.wheel(0, -amount)

        elif action_type == "navigate":
            desc += "navigate (reload)"
            page.reload(wait_until="networkidle", timeout=10000)

    except PlaywrightTimeout:
        desc += " [TIMEOUT]"
    except Exception as e:
        desc += f" [ERROR: {str(e)[:100]}]"

    return desc


def run_monkey_test():
    """モンキーテスト実行."""
    RESULTS["start_time"] = datetime.now().isoformat()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1280, "height": 720},
            locale="ja-JP",
        )
        page = context.new_page()

        # コンソールエラー収集開始
        collect_console_errors(page)

        # ページ読み込み
        print(f"🐒 モンキーテスト開始: {BASE_URL}")
        print(f"   計画アクション数: {TOTAL_ACTIONS}")
        print()

        try:
            page.goto(BASE_URL, wait_until="networkidle", timeout=30000)
        except PlaywrightTimeout:
            print("⚠️  初期ロードがタイムアウト（30秒）。続行します。")
            page.goto(BASE_URL, timeout=60000)

        time.sleep(3)  # Streamlitの初期レンダリング待ち

        # 初期状態のスクリーンショット
        page.screenshot(path="/tmp/monkey_00_initial.png")
        RESULTS["screenshots"].append("/tmp/monkey_00_initial.png")

        # ランダムアクション実行
        for i in range(1, TOTAL_ACTIONS + 1):
            desc = do_random_action(page, i)
            RESULTS["total_actions"] += 1

            # アクション後にエラーチェック
            time.sleep(0.5)  # Streamlitの再レンダリング待ち
            check_for_errors(page, desc)

            # 進捗表示（10アクションごと）
            if i % 10 == 0:
                print(f"   [{i}/{TOTAL_ACTIONS}] {desc}")
                page.screenshot(path=f"/tmp/monkey_{i:02d}.png")
                RESULTS["screenshots"].append(f"/tmp/monkey_{i:02d}.png")

            # ページがクラッシュしていたら復帰
            try:
                page.wait_for_load_state("domcontentloaded", timeout=5000)
            except PlaywrightTimeout:
                print("   ⚠️ ページ無応答。リロードします。")
                try:
                    page.goto(BASE_URL, wait_until="networkidle", timeout=15000)
                    time.sleep(2)
                except Exception:
                    pass

        # 最終スクリーンショット
        page.screenshot(path="/tmp/monkey_final.png")
        RESULTS["screenshots"].append("/tmp/monkey_final.png")

        browser.close()

    RESULTS["end_time"] = datetime.now().isoformat()

    # レポート出力
    print()
    print("=" * 60)
    print("🐒 モンキーテスト結果レポート")
    print("=" * 60)
    print(f"総アクション数:    {RESULTS['total_actions']}")
    print(f"  クリック:        {RESULTS['clicks']}")
    print(f"  入力:            {RESULTS['inputs']}")
    print(f"  セレクト:        {RESULTS['selects']}")
    print()
    print(f"UI エラー検出:     {len(RESULTS['errors_found'])}件")
    print(f"コンソールエラー:  {len(RESULTS['console_errors'])}件")
    print(f"クラッシュ:        {len(RESULTS['crashes'])}件")
    print()

    if RESULTS["errors_found"]:
        print("--- UI エラー詳細 ---")
        for err in RESULTS["errors_found"]:
            print(f"  [{err['time']}] {err['action']}")
            print(f"    {err['text'][:200]}")
            print()

    if RESULTS["console_errors"]:
        print("--- コンソールエラー詳細 ---")
        seen = set()
        for err in RESULTS["console_errors"]:
            key = err["text"][:100]
            if key not in seen:
                seen.add(key)
                print(f"  [{err['type']}] {err['text'][:200]}")
        print()

    if RESULTS["crashes"]:
        print("--- クラッシュ詳細 ---")
        for crash in RESULTS["crashes"]:
            print(f"  [{crash['time']}] {crash['error'][:300]}")
        print()

    # 判定
    total_issues = len(RESULTS["errors_found"]) + len(RESULTS["crashes"])
    if total_issues == 0:
        print("✅ 不具合なし。モンキーテスト通過。")
    else:
        print(f"❌ {total_issues}件の不具合を検出。")

    # JSON出力
    with open("/tmp/monkey_test_results.json", "w") as f:
        json.dump(RESULTS, f, indent=2, ensure_ascii=False)
    print("\n詳細: /tmp/monkey_test_results.json")

    return total_issues


if __name__ == "__main__":
    issues = run_monkey_test()
    exit(1 if issues > 0 else 0)
