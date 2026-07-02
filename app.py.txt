"""
Batch URL Screenshot Web App
- Batch process URL list
- Capture homepage screenshots
- Report invalid URLs
- Display successful screenshots on the same page
- Store records in SQLite for history review
- Record location (e.g. VPN location) when capturing
"""
import os
from dotenv import load_dotenv
load_dotenv() # 讀取 .env 檔案

import json
import re
import socket
import sys
import time

from datetime import datetime, timezone, timedelta
HKT = timezone(timedelta(hours=8))

from pathlib import Path
from urllib.parse import urlparse
from urllib.request import urlopen, Request

from flask import Flask, Response, render_template, request, jsonify, send_from_directory, stream_with_context
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

from db import init_db, insert_capture, get_all_captures, get_capture, delete_capture, delete_captures_bulk, get_whois_data

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
    """Convert input to valid URL. Handles safety placeholders and removes brackets."""
    url = url.strip()
    if not url:
        return ""
    # Remove all common bracket types: [], (), {}, <>
    url = re.sub(r"[\[\]\(\)\{\}<>]", "", url)
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
# Note: Safari only supports macOS and iOS - not Windows or Linux
DEVICE_PRESETS = {
    "windows": {
        "viewport": {"width": 1920, "height": 1080},
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "is_mobile": False,
        "supported_browsers": ["chrome", "edge", "firefox"],
    },
    "macos": {
        "viewport": {"width": 1440, "height": 900},
        "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "is_mobile": False,
        "supported_browsers": ["chrome", "edge", "firefox", "safari"],
    },
    "linux": {
        "viewport": {"width": 1920, "height": 1080},
        "user_agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "is_mobile": False,
        "supported_browsers": ["chrome", "firefox"],
    },
    "iphone": {
        "viewport": {"width": 390, "height": 844},
        "user_agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
        "is_mobile": True,
        "supported_browsers": ["safari", "chrome", "firefox"],
    },
    "android": {
        "viewport": {"width": 412, "height": 915},
        "user_agent": "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36",
        "is_mobile": True,
        "supported_browsers": ["chrome", "firefox"],
    },
}

# Browser-specific user agent templates (for dynamic switching within OS)
BROWSER_UA = {
    "chrome": "Mozilla/5.0 ({os_platform}) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "edge": "Mozilla/5.0 ({os_platform}) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0",
    "firefox": "Mozilla/5.0 ({os_platform}; rv:125.0) Gecko/20100101 Firefox/125.0",
    "safari": "Mozilla/5.0 ({os_platform}) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
}

# Mobile browser User Agents
BROWSER_UA_MOBILE = {
    "safari": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
    "chrome": "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) CriOS/124.0.0.0 Mobile/20221205 Safari/604.1",
    "firefox": "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) FxiOS/125.0 Mobile/20221205 Safari/604.1",
}


def get_browser_engine(browser: str):
    """Map browser name to Playwright engine. Safari uses webkit, others use chromium or firefox."""
    engines = {"chrome": "chromium", "edge": "chromium", "firefox": "firefox", "safari": "webkit"}
    return engines.get(browser, "chromium")


def get_supported_browsers(os_name: str) -> list[str]:
    """Get list of browsers supported for a given OS."""
    os_preset = DEVICE_PRESETS.get(os_name)
    return os_preset.get("supported_browsers", []) if os_preset else []


def url_to_filename(url: str) -> str:
    """
    Convert URL to screenshot filename base, keeping file extension.
    Examples:
      https://wsdXXX.lol/hk → wsdxxx.lol-hk
      https://wsdXXX.ai/hk/login.html → wsdxxx.ai-hk-login.html
      https://wsdazmr.com/hkwsd/login.html → wsdazmr.com-hkwsd-login.html
    Returns filename without directory path and without .png extension.
    """
    parsed = urlparse(url)
    domain = parsed.netloc or parsed.hostname or "unknown"
    path = parsed.path.strip("/") or ""

    # Keep file extension from last path segment if present
    if path:
        parts = path.split("/")
        path = "/".join(parts)

    # Join domain and path with hyphens
    if path:
        base_name = f"{domain}-{path.replace('/', '-')}".replace("--", "-")
    else:
        base_name = domain

    # Remove any trailing hyphens and force lowercase
    base_name = base_name.strip("-").lower()
    return base_name


def generate_screenshot_filename(url: str, os_name: str, browser_name: str, screenshot_dir: Path) -> str:
    """
    Generate screenshot filename with OS and browser info appended.
    Format: url_basename-os-browser.png
    Example: wsdxxx.lol-hk-windows-chrome.png
    Handles number collisions if the same URL/OS/Browser captured multiple times in same day.
    """
    base_name = url_to_filename(url)
    filename = f"{base_name}-{os_name.lower()}-{browser_name.lower()}.png"

    # Check for collisions: if file exists, append -1, -2, etc.
    if not (screenshot_dir / filename).exists():
        return filename

    # Collision detected: append counter
    counter = 1
    while True:
        collision_filename = f"{base_name}-{os_name.lower()}-{browser_name.lower()}-{counter}.png"
        if not (screenshot_dir / collision_filename).exists():
            return collision_filename
        counter += 1


def get_screenshot_date_dir(created_at: str) -> str:
    """
    Extract date from ISO datetime string and return as YYYY-MM-DD.
    Example: 2026-03-20T14:30:45.123456 → 2026-03-20
    """
    return created_at[:10] if len(created_at) >= 10 else datetime.now().strftime("%Y-%m-%d")


def capture_screenshot(
    url: str, output_path: Path, os: str = "windows", browser: str = "chrome", headless: bool = True, watermark: bool = True
) -> tuple[bool, str, int | None, float]:
    """
    Capture homepage screenshot of URL.
    Simulates the given OS and browser environment.
    Returns (success, error_message, status_code, elapsed_seconds).
    """
    os_preset = DEVICE_PRESETS.get(os, DEVICE_PRESETS["windows"])

    # Build user agent based on OS and browser
    if os_preset.get("is_mobile"):
        # Mobile devices use fixed UA (iOS/Android)
        if browser in BROWSER_UA_MOBILE:
            user_agent = BROWSER_UA_MOBILE[browser]
        else:
            user_agent = os_preset["user_agent"]
    else:
        # Desktop: use browser-specific UA with OS platform info
        os_platform = ""
        if os == "windows":
            os_platform = "Windows NT 10.0; Win64; x64"
        elif os == "macos":
            os_platform = "Macintosh; Intel Mac OS X 10_15_7"
        elif os == "linux":
            os_platform = "X11; Linux x86_64"

        browser_template = BROWSER_UA.get(browser, BROWSER_UA["chrome"])
        user_agent = browser_template.format(os_platform=os_platform)
    
    import os
    env_js = os.environ.get("DEFAULT_JS_ENABLED", "True").lower() == "true"
    
    context_options = {
        "viewport": os_preset["viewport"],
        "user_agent": user_agent,
        "ignore_https_errors": True,
        "is_mobile": os_preset["is_mobile"],
        
        # 💡 從前端請求中讀取，預設沿用 .env 的設定
        # js_param = request.args.get("js_enabled", str(os.environ.get("DEFAULT_JS_ENABLED", "False"))),
        # is_js_enabled = js_param.lower() == "true",
        # 🔒 貼在這裡：提高批量 URL 檢查的安全防禦
        # "javaScriptEnabled": False, 
        "java_script_enabled": env_js,
        "accept_downloads": False, # 💡 注意：Playwright Python 的參數名是底線 accept_downloads
        
        # Additional options to appear more human-like
        "locale": "zh-HK",
        "timezone_id": "Asia/Hong_Kong",
        "permissions": [],
        "geolocation": None,
        "extra_http_headers": {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-HK,zh-Hant;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept-Encoding": "gzip, deflate",
            "DNT": "1",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        },
    }

    engine = get_browser_engine(browser)
    t0 = time.perf_counter()

    try:
        with sync_playwright() as p:
            # Use Playwright bundled browsers only
            try:
                launch = getattr(p, engine).launch
                browser_instance = launch(headless=headless)
                print(f"Using Playwright bundled {engine} browser (headless={headless})")
            except Exception as launch_err:
                raise RuntimeError(f"Playwright {engine} browser not installed. Please run: python -m playwright install {engine}. Error: {launch_err}")

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

            # Inject watermark with timestamp and URL (if enabled)
            if watermark:
                timestamp = datetime.now(HKT).strftime("%Y-%m-%d %H:%M:%S")
                watermark_html = f"""<div id="domaincap-watermark" style="
                    position: fixed;
                    bottom: 10px;
                    right: 10px;
                    background: rgba(15, 20, 25, 0.85);
                    color: #e6edf3;
                    font-family: 'JetBrains Mono', monospace;
                    font-size: 11px;
                    padding: 6px 10px;
                    border-radius: 4px;
                    border: 1px solid rgba(88, 166, 255, 0.3);
                    z-index: 9999;
                    max-width: 300px;
                    text-align: right;
                    box-shadow: 0 2px 8px rgba(0,0,0,0.3);
                ">
                    <div style="color: #79b8ff; margin-bottom: 2px;">{timestamp}</div>
                    <div style="color: #58a6ff; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;" title="{url.replace('&', '&amp;')}">{url}</div>
                </div>"""

                page.add_style_tag(content="""
                    #domaincap-watermark * { box-sizing: border-box; }
                """)
                page.evaluate(f"""document.body.insertAdjacentHTML('beforeend', `{watermark_html}`)""")

                # Wait for watermark render
                page.wait_for_timeout(100)

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
        if "blocked" in err or "403" in err or "forbidden" in err:
            return False, "Request blocked by server", None, elapsed
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


@app.route("/api/captures", methods=["GET"])
def api_list_captures():
    """Return a list of recent capture records."""
    limit = request.args.get("limit", default=500, type=int)
    limit = max(1, min(limit, 2000))
    captures = get_all_captures(limit=limit)
    return jsonify({"captures": captures})


@app.route("/api/captures/<int:capture_id>", methods=["GET"])
def api_get_capture(capture_id):
    """Return a single capture record by ID."""
    capture = get_capture(capture_id)
    if not capture:
        return jsonify({"error": "Capture not found"}), 404
    return jsonify(capture)


@app.route("/api/capture", methods=["POST"])
def api_capture_url():
    """Capture a single URL (non-SSE API)."""
    data = request.get_json() or {}
    url = data.get("url", "")
    os_choice = data.get("os", "windows")
    browser_choice = data.get("browser", "chrome")
    headless = data.get("headless", True)

    if not isinstance(url, str) or not url.strip():
        return jsonify({"error": "Missing url"}), 400

    url = normalize_url(url)
    if not url:
        return jsonify({"error": "Invalid url"}), 400

    # Validate browser is supported for selected OS
    supported = get_supported_browsers(os_choice)
    if browser_choice not in supported:
        return jsonify({"error": f"Browser '{browser_choice}' is not supported on {os_choice}. Supported: {', '.join(supported)}"}), 400

    created_at = datetime.now().isoformat()
    date_dir_str = get_screenshot_date_dir(created_at)
    date_dir = UPLOAD_FOLDER / date_dir_str
    date_dir.mkdir(parents=True, exist_ok=True)

    filename = generate_screenshot_filename(url, os_choice, browser_choice, date_dir)
    output_path = date_dir / filename

    success, error_msg, status_code, elapsed = capture_screenshot(
        url, output_path, os=os_choice, browser=browser_choice, headless=headless, watermark=data.get("watermark", True)
    )

    # Store relative path in database: yyyy-mm-dd/filename
    screenshot_rel_path = f"{date_dir_str}/{filename}" if success else None
    screenshot_rel = f"/screenshots/{screenshot_rel_path}" if success else None
    domain_ips, ip_geo = resolve_domain_ips(url)
    reg_date, exp_date, registrar = get_whois_data(url)

    insert_capture(
        created_at=created_at,
        url=url,
        status_code=status_code,
        os_model=os_choice,
        browser_model=browser_choice,
        screenshot_path=screenshot_rel_path,
        duration_seconds=elapsed,
        location=get_location(),
        domain_ips=domain_ips,
        ip_geo=ip_geo,
        domain_registered_date=reg_date,
        domain_expiration_date=exp_date,
        domain_registrar=registrar,
    )

    result = {
        "url": url,
        "valid": success,
        "status_code": status_code,
        "created_at": created_at,
        "duration_seconds": round(elapsed, 2),
    }
    if success:
        result["screenshot"] = screenshot_rel
    else:
        result["error"] = error_msg

    return jsonify(result), (200 if success else 502)


def _sse_message(obj: dict) -> str:
    return f"data: {json.dumps(obj)}\n\n"


@app.route("/api/process", methods=["POST"])
def process_urls():
    """Batch process URLs: validate and capture screenshots. Streams progress via SSE."""
    data = request.get_json() or {}
    text = data.get("urls", "")
    os_choice = data.get("os", "windows")
    browser_choice = data.get("browser", "chrome")
    headless = data.get("headless", True)

    if not text.strip():
        return jsonify({"error": "Please enter at least one URL"}), 400

    urls = extract_urls(text)

    if not urls:
        return jsonify({"error": "No valid URLs found"}), 400

    if len(urls) > 500:
        return jsonify({"error": "Maximum 500 URLs per batch"}), 400

    # Validate browser is supported for selected OS
    supported = get_supported_browsers(os_choice)
    if browser_choice not in supported:
        return jsonify({"error": f"Browser '{browser_choice}' is not supported on {os_choice}. Supported: {', '.join(supported)}"}), 400

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

            created_at = datetime.now().isoformat()
            date_dir_str = get_screenshot_date_dir(created_at)
            date_dir = UPLOAD_FOLDER / date_dir_str
            date_dir.mkdir(parents=True, exist_ok=True)

            filename = generate_screenshot_filename(url, os_choice, browser_choice, date_dir)
            output_path = date_dir / filename

            success, error_msg, status_code, elapsed = capture_screenshot(
                url, output_path, os=os_choice, browser=browser_choice, headless=headless, watermark=data.get("watermark", True)
            )

            # Store relative path in database: yyyy-mm-dd/filename
            screenshot_rel_path = f"{date_dir_str}/{filename}" if success else None
            screenshot_rel = f"/screenshots/{screenshot_rel_path}" if success else None
            domain_ips, ip_geo = resolve_domain_ips(url)
            reg_date, exp_date, registrar = get_whois_data(url)

            insert_capture(
                created_at=created_at,
                url=url,
                status_code=status_code,
                os_model=os_choice,
                browser_model=browser_choice,
                screenshot_path=screenshot_rel_path,
                duration_seconds=elapsed,
                location=location,
                domain_ips=domain_ips,
                ip_geo=ip_geo,
                domain_registered_date=reg_date,
                domain_expiration_date=exp_date,
                domain_registrar=registrar,
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
    # 支援透過環境變數指定 Host，預設在 Docker 外仍為 127.0.0.1
    import os
    flask_host = os.environ.get("FLASK_HOST", "0.0.0.0")
    app.run(debug=not getattr(sys, "frozen", False), host=flask_host, port=5001)
