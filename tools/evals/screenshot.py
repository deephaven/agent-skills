"""Reliable dashboard screenshots via dh serve + Playwright.

Workflow:
1. Spawn `dh serve <script> --no-browser --port <free>` as a subprocess.
2. Poll the server URL until it responds.
3. Drive Playwright to /iframe/widget/?name=<widget_name>.
4. Settle: panel ready → spinners gone → grid canvases sized → networkidle.
5. Take a full-page PNG.
6. Tear down the server.
"""

from __future__ import annotations

import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
from playwright.sync_api import Page, TimeoutError as PWTimeout, sync_playwright


PANEL_LOAD_TIMEOUT_MS = 30_000
SETTLE_TIMEOUT_MS = 20_000
SERVER_READY_TIMEOUT_S = 60
POST_SETTLE_PAUSE_MS = 750  # final animation/transition settle

SPINNER_SELECTORS = [
    ".loading-spinner",
    '[role="progressbar"]',
    '[data-testid="api-bootstrap-loading-spinner"]',
]


def find_free_port() -> int:
    with socket.socket() as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def wait_for_server(port: int, timeout: float = SERVER_READY_TIMEOUT_S) -> bool:
    """Poll the dh server until it responds with HTTP 200."""
    url = f"http://localhost:{port}/"
    deadline = time.monotonic() + timeout
    last_err = None
    while time.monotonic() < deadline:
        try:
            r = httpx.get(url, timeout=2.0)
            if r.status_code < 500:
                return True
        except (httpx.ConnectError, httpx.ReadTimeout, httpx.RemoteProtocolError) as e:
            last_err = e
        time.sleep(0.5)
    if last_err:
        print(f"server never ready: {last_err}", file=sys.stderr)
    return False


def settle_dashboard(page: Page) -> None:
    """Wait for a Deephaven dashboard to be visually settled.

    Order matters: spinners can appear during late-stage data fetches even
    after the panel is "ready", so we re-check spinners after the grid step.
    """
    page.wait_for_selector(
        ".dh-inner-react-panel",
        state="attached",
        timeout=PANEL_LOAD_TIMEOUT_MS,
    )

    page.wait_for_function(
        """() => {
            const panel = document.querySelector('.dh-inner-react-panel');
            if (!panel || panel.children.length === 0) return false;
            const overlay = document.querySelector('.iris-panel-message-overlay');
            if (!overlay) return true;
            const msg = document.querySelector('.message-content');
            return !!(msg && msg.textContent && msg.textContent.trim());
        }""",
        timeout=PANEL_LOAD_TIMEOUT_MS,
    )

    for sel in SPINNER_SELECTORS:
        try:
            page.wait_for_selector(sel, state="hidden", timeout=SETTLE_TIMEOUT_MS)
        except PWTimeout:
            pass

    # Grid canvases must have non-zero dimensions to be considered rendered.
    try:
        page.wait_for_function(
            """() => {
                const canvases = document.querySelectorAll('.iris-grid canvas.grid-canvas');
                if (canvases.length === 0) return true; // no grids = ok
                return Array.from(canvases).every(c => c.width > 0 && c.height > 0);
            }""",
            timeout=SETTLE_TIMEOUT_MS,
        )
    except PWTimeout:
        pass

    # Re-check spinners after the grid step in case data loads were triggered.
    for sel in SPINNER_SELECTORS:
        try:
            page.wait_for_selector(sel, state="hidden", timeout=5_000)
        except PWTimeout:
            pass

    # Nudge Golden Layout to recompute sizes — fixes cases where panels are
    # stacked with zero-height bodies because the initial layout pass ran
    # before the iframe had final dimensions.
    page.evaluate("window.dispatchEvent(new Event('resize'))")
    page.wait_for_timeout(250)

    # Wait for every visible Deephaven panel container to have non-zero size.
    # Catches Golden Layout collapse where panels exist in the DOM but have
    # zero-height bodies. Allow a generous timeout but don't fail outright —
    # a buggy script may legitimately produce a blank panel.
    try:
        page.wait_for_function(
            """() => {
                const panels = document.querySelectorAll('.dh-react-panel');
                if (panels.length === 0) return false;
                return Array.from(panels).every(p => {
                    const r = p.getBoundingClientRect();
                    return r.width > 0 && r.height > 0;
                });
            }""",
            timeout=SETTLE_TIMEOUT_MS,
        )
    except PWTimeout:
        pass

    try:
        page.wait_for_load_state("networkidle", timeout=10_000)
    except PWTimeout:
        pass

    page.wait_for_timeout(POST_SETTLE_PAUSE_MS)


def capture_screenshot(
    script_path: Path,
    output_path: Path,
    widget_name: str | None,
    viewport: tuple[int, int] = (1600, 1000),
    server_timeout: float = SERVER_READY_TIMEOUT_S,
) -> dict:
    """Capture a settled screenshot of a Deephaven dashboard.

    Returns a dict with keys: success (bool), error (str|None), bytes (int|None).
    """
    port = find_free_port()
    server_proc = subprocess.Popen(
        ["dh", "serve", str(script_path), "--no-browser", "--port", str(port)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    try:
        if not wait_for_server(port, timeout=server_timeout):
            return {"success": False, "error": "dh serve never became ready", "bytes": None}

        if widget_name:
            url = f"http://localhost:{port}/iframe/widget/?name={widget_name}"
        else:
            url = f"http://localhost:{port}/"

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(viewport={"width": viewport[0], "height": viewport[1]})
            page = context.new_page()
            page_errors: list[str] = []
            page.on("pageerror", lambda e: page_errors.append(str(e)))

            try:
                page.goto(url, wait_until="domcontentloaded", timeout=PANEL_LOAD_TIMEOUT_MS)
                settle_dashboard(page)
                output_path.parent.mkdir(parents=True, exist_ok=True)
                page.screenshot(path=str(output_path), full_page=True)
            finally:
                context.close()
                browser.close()

        size = output_path.stat().st_size if output_path.exists() else 0
        return {
            "success": output_path.exists() and size > 0,
            "error": "; ".join(page_errors) or None,
            "bytes": size,
        }
    except Exception as e:
        return {"success": False, "error": f"{type(e).__name__}: {e}", "bytes": None}
    finally:
        server_proc.terminate()
        try:
            server_proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server_proc.kill()
            server_proc.wait()


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Screenshot a Deephaven dashboard")
    parser.add_argument("script", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--widget", default=None)
    args = parser.parse_args()
    result = capture_screenshot(args.script, args.out, args.widget)
    print(result)
    sys.exit(0 if result["success"] else 1)


if __name__ == "__main__":
    main()
