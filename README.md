# LinkedIn Data Enrichment Scraper (1M Records Scale)

A resilient, high-performance data enrichment tool engineered to extract **Current Company Names** and **LinkedIn Profile URLs** for datasets up to 1 Million records without triggering IP blocks or account suspensions.

---

## 🌟 Key Features

1. **Proxy & IP Rotation Manager (`proxy_manager.py`)**:
   - Supports HTTP, HTTPS, and SOCKS5 residential proxy pools.
   - Per-worker automatic rotation with IP health tracking and cool-off management for rate-limited IPs (HTTP 429/403).

2. **Stealth Browser Automation (`browser_engine.py`)**:
   - Built with **Playwright Stealth**, masking `navigator.webdriver`, spoofing Chrome runtime objects, dynamic viewports, and canvas/WebGL fingerprint masking.

3. **Human-Like Behavior Simulator (`human_emulation.py`)**:
   - Bezier curve mouse movements, natural scroll behaviors with micro-pauses, and Gaussian noise delay timing to evade bot-detection algorithms.

4. **Headers & Session Manager (`session_manager.py`)**:
   - Rotates User-Agents (`fake-useragent`), custom anti-bot HTTP request headers (`Sec-Fetch-*`, `Accept-Language`), and session tokens.

5. **SQLite Checkpoint & Resume Pipeline (`data_pipeline.py`)**:
   - Built-in SQLite state queue (`checkpoint_queue.db`) guarantees atomic updates and crash resilience. If paused or interrupted, resume from item #450,000 without starting over.

6. **Interactive Terminal UI (`main.py`)**:
   - Powered by `rich` with color-coded live progress metrics, completion stats, ETAs, and graceful interrupt handling.

---

## 📁 Directory Structure

```
e:/Link/linkedin/
├── linkedin_enricher/
│   ├── __init__.py
│   ├── config.py                 # Central settings & parameters
│   ├── proxy_manager.py          # Proxy rotation & IP health manager
│   ├── human_emulation.py        # Bezier mouse & Gaussian delay engine
│   ├── browser_engine.py         # Playwright stealth browser engine
│   ├── session_manager.py        # Header & session rotator
│   ├── search_engine_fallback.py # X-Ray search parser
│   └── data_pipeline.py          # SQLite queue & CSV export pipeline
├── main.py                       # CLI application entry point
├── sample_input.csv              # Sample CSV dataset (Username, City)
├── proxies.txt                   # Proxy configuration file
└── README.md                     # Documentation
```

---

## 🚀 Quick Start Guide

### 1. Prerequisites
Ensure Python 3.9+ and required packages are installed:
```bash
pip install playwright httpx beautifulsoup4 fake-useragent rich pandas
playwright install chromium
```

### 2. Configure Proxies (Recommended for 1M records)
Add your HTTP, HTTPS, or SOCKS5 residential proxies to `proxies.txt` (one per line):
```text
http://username:password@proxy.example.com:8080
socks5://username:password@proxy.example.com:1080
```

### 3. Prepare Input CSV File
Ensure your CSV contains columns for **Username** (or Name/Contact) and **City** (location in Washington / WA state):
```csv
Contact,City
Kelly Atkinson,Seattle
Robert Jones,Redmond
Donald Montgomery,Bellevue
```

### 4. Run Data Enrichment Tool
To run the enrichment tool:
```bash
python main.py --input your_1m_dataset.csv --output enriched_output.csv --workers 10
```

### Command Options:
- `--input` / `-i`: Path to input CSV dataset.
- `--output` / `-o`: Path for enriched output CSV.
- `--workers` / `-w`: Concurrency level (number of parallel worker tasks).
- `--proxies` / `-p`: Path to proxy list file (`proxies.txt`).
- `--reset-db`: Clears existing SQLite checkpoint database to start clean.
- `--export-only`: Exports current SQLite queue state directly to CSV without running scraper.

---

## 🛡 Anti-Blocking Best Practices

1. **Use Residential Proxies:** Datacenter IPs are easily flagged. Use rotating residential proxies (Smartproxy, BrightData, Webshare, Oxylabs).
2. **Optimal Concurrency:** Recommended `5-15` workers when using residential proxies.
3. **Automatic Checkpointing:** Press `Ctrl+C` at any time to pause safely. Run `python main.py` again to resume where you left off.
