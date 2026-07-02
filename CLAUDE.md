# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Quick Start

```bash
python app.py
```
Open http://127.0.0.1:5001

## Architecture

This is a Flask web app that captures homepage screenshots of URLs using Playwright, simulating different OS/browser environments.

### Core Components

**app.py** - Flask server with:
- `/` - HTML interface (tabs: Capture / History)
- `/api/process` - SSE endpoint for batch URL processing
- `/api/capture` - Single URL capture endpoint
- `/api/captures` - List/get/delete capture records
- Screenshots stored in `static/screenshots/yyyy-mm-dd/`

**db.py** - SQLite storage with captures table containing: URL, status_code, os_model, browser_model, screenshot_path, location, IPs, WHOIS data

**templates/index.html** + **static/** - Dark-themed UI with tab switching, bulk URL input, progress streaming, history with search/pagination

### Device/Browser Simulation

The app simulates different operating systems and browsers to capture realistic screenshots. This is important because malicious/phishing websites often detect the visitor's OS and browser to apply different strategies (e.g., hiding deceptive elements from Desktop users while targeting Mobile users).

**OS Presets** (each has unique viewport size and User Agent):
| OS | Viewport | `is_mobile` | Supported Browsers | User Agent Example |
|---|---|---|---|---|
| Windows | 1920x1080 | No | Chrome, Edge, Firefox | `Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36` |
| macOS | 1440x900 | No | Chrome, Edge, Firefox, Safari | `Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36` |
| Linux | 1920x1080 | No | Chrome, Firefox | `Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36` |
| iPhone | 390x844 | Yes | Safari, Chrome, Firefox | `Mozilla/5.0 (iPhone; CPU iPhone OS 17_4_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1` |
| Android | 412x915 | Yes | Chrome, Firefox | `Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36` |

**Browser Engines** (different rendering engines):
| Browser | Playwright Engine | Notes |
|---|---|---|
| Chrome | chromium | Standard Chrome User Agent |
| Edge | chromium | Edge-specific suffix in UA (`Edg/124.0.0.0`) |
| Firefox | firefox | Gecko-based User Agent (`rv:125.0`) |
| Safari | webkit | Apple Safari rendering (macOS/iOS only) |

**Key differences by OS** (when same browser selected):
1. **User Agent string** - Website identifies your OS via `navigator.userAgent`
2. **Viewport size** - Affects responsive web design rendering
3. **`is_mobile` flag** - Enables/disables mobile-specific behaviors (touch events, viewport meta handling)

**Browser Support by OS**:
- Windows: Chrome, Edge, Firefox (Safari not available on Windows)
- macOS: Chrome, Edge, Firefox, Safari (all major browsers)
- Linux: Chrome, Firefox (Safari not available on Linux)
- iPhone: Safari, Chrome, Firefox
- Android: Chrome, Firefox

### External Services
- IP geolocation: ip-api.com, ipinfo.io
- WHOIS: disabled (returns "NA")

## Development

Install dependencies: `pip install -r requirements.txt`

Install Playwright browsers: `python -m playwright install chromium firefox webkit`
