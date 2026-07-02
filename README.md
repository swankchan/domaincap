This program simulates different OS and browser behavior when browsing given URLs. Phishing websites may hide from Desktop users and target Mobile users because on smaller screens, details are less visible and mistakes are more easily made.

## Environment
1. Python 3.12.13
2. Use Conda activate DomainCap
3. Browsers: Chrome, Edge, Firefox, Safari (Safari only on macOS/iOS)

### Install Playwright browsers
```bash
python -m playwright install chromium firefox webkit
```

Screenshots are stored at `./static/screenshots`

## Features

- Batch input multiple URLs (one per line, or comma/space separated)
- **OS/Device simulation**: Windows, macOS, Linux, iPhone, Android (different viewport sizes and User Agent strings)
- **Browser simulation**: Chrome, Firefox, Safari, Edge (different rendering engines and User Agent strings)

**Browser Support by OS**:
- Windows: Chrome, Edge, Firefox (Safari not supported on Windows)
- macOS: Chrome, Edge, Firefox, Safari
- Linux: Chrome, Firefox (Safari not supported on Linux)
- iPhone: Safari, Chrome, Firefox
- Android: Chrome, Firefox

- Automatically capture homepage screenshots for each URL
- Report invalid URLs (timeout, 404, DNS errors, etc.)
- Display all successful screenshots on the same page

### Why OS/Browser Simulation Matters

Malicious/phishing websites often detect the visitor's OS and browser to apply different strategies:
- Hide deceptive elements from Desktop users (larger screen, more details visible)
- Target Mobile users (smaller screen, faster scrolling, more prone to mistakes)

The app simulates these differences by:
1. **User Agent string** - Website identifies your OS via `navigator.userAgent`
2. **Viewport size** - Affects responsive web design rendering
3. **Mobile flag** - Enables/disables mobile-specific behaviors (touch events, viewport meta handling)

## Interfaces

This project provides two web interfaces:

### 1. Flask Interface (Default)
Full-featured web application with custom styling, tabs, and advanced features.

### 2. Gradio Interface (Alternative)
*(Removed as the script has been deleted)*

## Installation

1. Create a virtual environment (recommended):

```bash
python -m venv venv
venv\Scripts\activate   # Windows
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

For Gradio interface (optional):
```bash
pip install gradio>=4.0.0
```

## Run

### Flask Interface (Full-featured)
```bash
python app.py
```
Open your browser and go to: <http://127.0.0.1:5001>

### Gradio Interface (Simplified)
```bash
python app_gradio.py
```
Open your browser and go to: <http://127.0.0.1:7860>

## Usage

### Flask Interface
1. Paste or enter URLs in the text box
    - automatically skips "[" & "]"
2. Click "Capture Screenshots"
3. Wait for processing to complete
4. View the invalid URL list and successful screenshots in the report



Recommended: up to 100 URLs per batch (Flask) or 50 URLs (Gradio) to avoid long processing times.

**First run on new machine:** Playwright will auto-download Chromium (~150MB) when you first capture a screenshot. An internet connection is required for this one-time download.

## API

The app exposes a small JSON API (same server). Use it to integrate with scripts or other services.

### List captures

`GET /api/captures?limit=<n>`

- Returns the most recent capture records (newest first).
- `limit` is optional (default 500, max 2000).

Example:
```bash
curl http://127.0.0.1:5001/api/captures?limit=20
```

### Get a capture by ID

`GET /api/captures/<id>`

Example:
```bash
curl http://127.0.0.1:5001/api/captures/123
```

### Capture a single URL (non-SSE)

`POST /api/capture`

Body (JSON):
```json
{
  "url": "https://example.com",
  "os": "windows",
  "browser": "chrome"
}
```

Example:
```bash
curl -X POST http://127.0.0.1:5001/api/capture \
  -H "Content-Type: application/json" \
  -d '{"url":"https://example.com","os":"windows","browser":"chrome"}'
```

### Delete a capture

`DELETE /api/capture/<id>`

Example:
```bash
curl -X DELETE http://127.0.0.1:5001/api/capture/123
```
