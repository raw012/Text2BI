import base64
from typing import Any


def capture_dashboard_html(html: str) -> tuple[str | None, dict[str, Any], str | None]:
    """Render dashboard HTML in Chromium and return screenshot plus DOM measurements."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None, {}, "Playwright is not installed."

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 1000}, device_scale_factor=1)
            page.set_content(html, wait_until="domcontentloaded")
            page.wait_for_timeout(1200)
            metrics = page.evaluate(
                """() => {
                  const cards = [...document.querySelectorAll('.card')].map((node, index) => {
                    const rect = node.getBoundingClientRect();
                    const title = node.querySelector('h2');
                    return {
                      index,
                      x: Math.round(rect.x),
                      y: Math.round(rect.y),
                      width: Math.round(rect.width),
                      height: Math.round(rect.height),
                      scrollWidth: node.scrollWidth,
                      scrollHeight: node.scrollHeight,
                      titleFontSize: title ? getComputedStyle(title).fontSize : null,
                      titleLineHeight: title ? getComputedStyle(title).lineHeight : null
                    };
                  });
                  return {
                    viewport: {width: innerWidth, height: innerHeight},
                    document: {
                      width: document.documentElement.scrollWidth,
                      height: document.documentElement.scrollHeight
                    },
                    horizontalOverflow: document.documentElement.scrollWidth > innerWidth,
                    cards
                  };
                }"""
            )
            screenshot = page.screenshot(full_page=True, type="png")
            browser.close()
            return base64.b64encode(screenshot).decode("ascii"), metrics, None
    except Exception as exc:
        return None, {}, str(exc)
