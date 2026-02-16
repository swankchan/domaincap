"""
Batch URL Screenshot Web App
- Batch process URL list
- Capture homepage screenshots
- Report invalid URLs
- Display successful screenshots on the same page
- Store records in SQLite for history review
- Record location (e.g. VPN location) when capturing
"""

import json
import re
import socket
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import urlopen, Request

from flask import Flask, Response, render_template, request, jsonify, send_from_directory, stream_with_context
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

from db import init_db, insert_capture, get_all_captures, delete_capture, delete_captures_bulk

# PyInstaller: when frozen, use _MEIPASS for bundled files, cwd for writable screenshots
if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys._MEIPASS)
    UPLOAD_FOLDER = Path.cwd() / "screenshots"  # Writable folder next to exe
else:
    BASE_DIR = Path(__file__).resolve().parent
    UPLOAD_FOLDER = BASE_DIR / "static" / "screenshots"
UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)

init_db()

app = Flask(
    __name__,
    template_folder=str(BASE_DIR / "templates"),
    static_folder=str(BASE_DIR / "static"),
)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16MB


def normalize_url(url: str) -> str:
    """Convert input to valid URL. Handles safety placeholders like [.] -> ."""
    url = url.strip()
    if not url:
        return ""
    # Restore dots from safety placeholders: [.] (.) (dot) -> .
    url = re.sub(r"\[\.\]", ".", url, flags=re.IGNORECASE)
    url = re.sub(r"\(\.\)", ".", url, flags=re.IGNORECASE)
    url = re.sub(r"\(dot\)", ".", url, flags=re.IGNORECASE)
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url


def get_location() -> str | None:
    """
    Get current location based on public IP (reflects VPN if active).
    Tries ip-api.com (HTTP) first, then ipinfo.io (HTTPS) as fallback.
    Returns e.g. "Hong Kong, Central, HK".
    """
    def try_ipapi():
        req = Request(
            "http://ip-api.com/json/?fields=status,country,countryCode,regionName,city",
            headers={"User-Agent": "DomainCap/1.0"},
        )
        with urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
        if data.get("status") != "success":
            return None
        parts = [p for p in (data.get("city"), data.get("regionName"), data.get("country")) if p]
        return "|".join(parts) if parts else data.get("country")

    def try_ipinfo():
        req = Request(
            "https://ipinfo.io/json",
            headers={"User-Agent": "DomainCap/1.0"},
        )
        with urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
        parts = [p for p in (data.get("city"), data.get("region"), data.get("country")) if p]
        return "|".join(parts) if parts else None

    for fn in (try_ipapi, try_ipinfo):
        try:
            result = fn()
            if result:
                return result
        except Exception:
            pass
    return None


def format_location_display(location: str | None) -> str:
    """Extract country/region for display. Full location stored as city|region|country."""
    if not location:
        return "-"
    parts = [p.strip() for p in location.split("|") if p.strip()]
    return parts[-1] if parts else "-"


def resolve_domain_ips(url: str) -> tuple[str, str]:
    """
    Resolve domain to IPs and lookup country code for each.
    Returns (comma-separated IPs, newline-separated "IP | CC" with 2-char country code).
    """
    def lookup_ip_geo(ip: str) -> str:
        """Lookup IP geolocation. Returns 2-char country code (e.g. HK, US) or empty."""
        try:
            req = Request(
                f"http://ip-api.com/json/{ip}?fields=status,countryCode",
                headers={"User-Agent": "DomainCap/1.0"},
            )
            with urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read().decode())
            if data.get("status") != "success":
                return ""
            cc = (data.get("countryCode") or "").strip().upper()
            return cc[:2] if cc else ""
        except Exception:
            return ""

    try:
        parsed = urlparse(url)
        host = parsed.hostname or parsed.netloc.split(":")[0]
        if not host or host.startswith("["):
            return "", ""
        _, _, ip_list = socket.gethostbyname_ex(host)
        ips = sorted(set(ip_list)) if ip_list else []
        if not ips:
            return "", ""
        ip_geo_lines = []
        for ip in ips:
            cc = lookup_ip_geo(ip)
            ip_geo_lines.append(f"{ip} | {cc}" if cc else ip)
        return ", ".join(ips), "\n".join(ip_geo_lines)
    except (socket.gaierror, socket.timeout, OSError, ValueError):
        return "", ""


def extract_urls(text: str) -> list[str]:
    """Extract URL list from text"""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    urls = []
    for line in lines:
        # Support comma, space delimiters
        for part in re.split(r"[\s,]+", line):
            part = part.strip()
            if part:
                url = normalize_url(part)
                if url and url not in urls:
                    urls.append(url)
    return urls


# OS/Device viewport presets (width, height, is_mobile) + user agent templates
DEVICE_PRESETS = {
    "windows": {
        "viewport": {"width": 1920, "height": 1080},
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) {browser_ua}",
        "is_mobile": False,
    },
    "macos": {
        "viewport": {"width": 1440, "height": 900},
        "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) {browser_ua}",
        "is_mobile": False,
    },
    "linux": {
        "viewport": {"width": 1920, "height": 1080},
        "user_agent": "Mozilla/5.0 (X11; Linux x86_64) {browser_ua}",
        "is_mobile": False,
    },
    "iphone": {
        "viewport": {"width": 390, "height": 844},
        "user_agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 {browser_ua}",
        "user_agent_mobile": True,
        "is_mobile": True,
    },
    "android": {
        "viewport": {"width": 412, "height": 915},
        "user_agent": "Mozilla/5.0 (Linux; Android 14; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
        "user_agent_mobile": False,  # Use fixed UA
        "is_mobile": True,
    },
}

BROWSER_UA = {
    "chrome": "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "edge": "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
    "firefox": "Gecko/20100101 Firefox/121.0",
    "safari": "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
}
# Mobile browser UA suffixes (appended after AppleWebKit/605.1.15 for iOS/Android)
BROWSER_UA_MOBILE = {
    "chrome": "(KHTML, like Gecko) CriOS/120.0.0.0 Mobile/15E148 Safari/604.1",
    "edge": "(KHTML, like Gecko) EdgiOS/120.0.0.0 Mobile/15E148 Safari/604.1",
    "firefox": "(KHTML, like Gecko) FxiOS/121.0 Mobile/15E148 Safari/605.1.15",
    "safari": "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
}


def get_browser_engine(browser: str):
    """Map browser name to Playwright engine. Safari uses webkit, others use chromium or firefox."""
    engines = {"chrome": "chromium", "edge": "chromium", "firefox": "firefox", "safari": "webkit"}
    return engines.get(browser, "chromium")


def capture_screenshot(
    url: str, output_path: Path, os: str = "windows", browser: str = "chrome"
) -> tuple[bool, str, int | None, float]:
    """
    Capture homepage screenshot of URL.
    Simulates the given OS and browser environment.
    Returns (success, error_message, status_code, elapsed_seconds).
    """
    os_preset = DEVICE_PRESETS.get(os, DEVICE_PRESETS["windows"])
    if os_preset.get("user_agent_mobile"):
        browser_ua = BROWSER_UA_MOBILE.get(browser, BROWSER_UA_MOBILE["safari"])
        user_agent = os_preset["user_agent"].format(browser_ua=browser_ua)
    elif os == "android":
        user_agent = os_preset["user_agent"]
    else:
        browser_ua = BROWSER_UA.get(browser, BROWSER_UA["chrome"])
        user_agent = os_preset["user_agent"].format(browser_ua=browser_ua)

    context_options = {
        "viewport": os_preset["viewport"],
        "user_agent": user_agent,
        "ignore_https_errors": True,
        "is_mobile": os_preset["is_mobile"],
    }

    engine = get_browser_engine(browser)
    t0 = time.perf_counter()

    try:
        with sync_playwright() as p:
            launch = getattr(p, engine).launch
            try:
                browser_instance = launch(headless=True)
            except Exception:
                # Fallback to chromium if firefox/webkit not installed
                browser_instance = p.chromium.launch(headless=True)

            context = browser_instance.new_context(**context_options)
            page = context.new_page()
            page.set_default_timeout(15000)

            response = None
            try:
                response = page.goto(url, wait_until="domcontentloaded")
                # Don't abort on 4xx: SPAs may return 404 but serve index.html in body;
                # page can still render. We record status and capture screenshot anyway.
                page.wait_for_load_state("networkidle", timeout=8000)
                # Extra wait for SPA to render (React/Vue etc. need time to mount)
                page.wait_for_timeout(2500)
                # 304 = Not Modified: body empty, browser uses cache; needs more time to render
                if response and response.status == 304:
                    page.wait_for_timeout(5000)
            except PlaywrightTimeout:
                pass  # Continue; screenshot may still succeed

            page.screenshot(path=str(output_path), full_page=False)
            elapsed = time.perf_counter() - t0
            status = response.status if response else None
            browser_instance.close()
            return True, "", status, elapsed
    except Exception as e:
        elapsed = time.perf_counter() - t0
        err = str(e).lower()
        if "timeout" in err or "timed out" in err:
            return False, "Connection timeout", None, elapsed
        if "net::" in err or "connection" in err:
            return False, "Connection failed", None, elapsed
        if "refused" in err:
            return False, "Connection refused", None, elapsed
        if "dns" in err or "name or service not known" in err:
            return False, "DNS resolution failed", None, elapsed
        return False, str(e)[:100], None, elapsed


@app.route("/")
def index():
    captures = get_all_captures()
    tab = request.args.get("tab", "capture")
    return render_template(
        "index.html",
        captures=captures,
        active_tab=tab,
        format_location_display=format_location_display,
    )


@app.route("/screenshots/<path:filename>")
def serve_screenshot(filename):
    """Serve screenshot files (works for both dev and frozen exe)"""
    return send_from_directory(UPLOAD_FOLDER, filename)


@app.route("/api/capture/bulk-delete", methods=["POST"])
def api_bulk_delete_captures():
    """Delete multiple capture records and their screenshot files."""
    data = request.get_json() or {}
    ids = data.get("ids", [])
    if not isinstance(ids, list):
        return jsonify({"error": "ids must be an array"}), 400
    ids = [int(x) for x in ids if isinstance(x, (int, str)) and str(x).isdigit()]
    if not ids:
        return jsonify({"error": "No valid ids"}), 400
    deleted, paths = delete_captures_bulk(ids)
    for p in paths:
        if p:
            try:
                (UPLOAD_FOLDER / p).unlink(missing_ok=True)
            except OSError:
                pass
    return jsonify({"ok": True, "deleted": deleted})


@app.route("/api/capture/<int:capture_id>", methods=["DELETE"])
def api_delete_capture(capture_id):
    """Delete a capture record and its screenshot file."""
    success, screenshot_path = delete_capture(capture_id)
    if not success:
        return jsonify({"error": "Capture not found"}), 404
    if screenshot_path:
        try:
            (UPLOAD_FOLDER / screenshot_path).unlink(missing_ok=True)
        except OSError:
            pass
    return jsonify({"ok": True})


def _sse_message(obj: dict) -> str:
    return f"data: {json.dumps(obj)}\n\n"


@app.route("/api/process", methods=["POST"])
def process_urls():
    """Batch process URLs: validate and capture screenshots. Streams progress via SSE."""
    data = request.get_json() or {}
    text = data.get("urls", "")
    os_choice = data.get("os", "windows")
    browser_choice = data.get("browser", "chrome")

    if not text.strip():
        return jsonify({"error": "Please enter at least one URL"}), 400

    urls = extract_urls(text)

    if not urls:
        return jsonify({"error": "No valid URLs found"}), 400

    if len(urls) > 50:
        return jsonify({"error": "Maximum 50 URLs per batch"}), 400

    def generate():
        total = len(urls)
        location = get_location()
        results = []

        for i, url in enumerate(urls, 1):
            yield _sse_message({
                "type": "progress",
                "current": i,
                "total": total,
                "url": url,
            })

            filename = f"{uuid.uuid4().hex}.png"
            output_path = UPLOAD_FOLDER / filename

            success, error_msg, status_code, elapsed = capture_screenshot(
                url, output_path, os=os_choice, browser=browser_choice
            )

            created_at = datetime.now().isoformat()
            screenshot_rel = f"/screenshots/{filename}" if success else None
            domain_ips, ip_geo = resolve_domain_ips(url)

            insert_capture(
                created_at=created_at,
                url=url,
                status_code=status_code,
                os_model=os_choice,
                browser_model=browser_choice,
                screenshot_path=filename if success else None,
                duration_seconds=elapsed,
                location=location,
                domain_ips=domain_ips,
                ip_geo=ip_geo,
            )

            if success:
                results.append({
                    "url": url,
                    "valid": True,
                    "screenshot": screenshot_rel,
                    "status_code": status_code,
                    "created_at": created_at,
                    "duration_seconds": round(elapsed, 2),
                })
            else:
                results.append({
                    "url": url,
                    "valid": False,
                    "error": error_msg,
                    "status_code": status_code,
                    "created_at": created_at,
                    "duration_seconds": round(elapsed, 2),
                })

        yield _sse_message({
            "type": "done",
            "total": len(results),
            "valid_count": sum(1 for r in results if r["valid"]),
            "invalid_count": sum(1 for r in results if not r["valid"]),
            "os": os_choice,
            "browser": browser_choice,
            "results": results,
        })

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


if __name__ == "__main__":
    app.run(debug=not getattr(sys, "frozen", False), host="127.0.0.1", port=5000)
