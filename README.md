# Batch URL Screenshot

Web app to batch process multiple URLs, capture homepage screenshots, and report invalid links.

## Features

- Batch input multiple URLs (one per line, or comma/space separated)
- **OS/Device simulation**: Windows, macOS, Linux, iPhone, Android (different viewport sizes)
- **Browser simulation**: Chrome, Firefox, Safari, Edge (different engines & user agents)
- Automatically capture homepage screenshots for each URL
- Report invalid URLs (timeout, 404, DNS errors, etc.)
- Display all successful screenshots on the same page

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

3. Install Playwright browser (required on first run):

```bash
python -m playwright install chromium
```

For Firefox and Safari simulation, also run:

```bash
python -m playwright install firefox webkit
```

## Run

```bash
python app.py
```

Open your browser and go to: <http://127.0.0.1:5000>

## Usage

1. Paste or enter URLs in the text box
2. Click "Capture Screenshots"
3. Wait for processing to complete
4. View the invalid URL list and successful screenshots in the report

Recommended: up to 50 URLs per batch to avoid long processing times.

---

## Build Executable (Run on Another Machine)

To create a standalone `.exe` that can run on other Windows machines without Python:

1. Install PyInstaller:

```bash
pip install pyinstaller
```

2. Build the executable:

```bash
# Windows
build.bat

# Or manually:
pyinstaller build_exe.spec
```

3. Output: `dist/screencap_url.exe`

4. Copy `screencap_url.exe` to the target machine and run it. Open http://127.0.0.1:5000 in your browser.

**First run on new machine:** Playwright will auto-download Chromium (~150MB) when you first capture a screenshot. An internet connection is required for this one-time download.
