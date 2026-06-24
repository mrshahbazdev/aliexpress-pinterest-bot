# AliExpress → Pinterest Auto-Pin Bot

Fetch trending products from your AliExpress Affiliate Portal, save them to a MySQL database, generate AI-powered Pinterest content, and manage everything through a **web UI** or **REST API** — no `.env` file required.

## How It Works

```
AliExpress Portal API → MySQL Database → AI (Gemini/OpenAI) → Pinterest
  (fetch products)     (persist + dedup)  (pin descriptions)    (create pins)
```

### Key Features

- **Web UI** — Dark-themed dashboard to fetch, save, and manage products
- **No .env needed** — All settings (DB, cookies, AI keys) entered via the UI
- **Database** — MySQL storage with deduplication (no duplicate products)
- **REST API** — JSON endpoints for programmatic access
- **AI Content** — Gemini (free) or OpenAI for Pinterest titles, descriptions, hashtags
- **Exe Ready** — Build as a standalone executable with PyInstaller
- **Cookie Paste** — Paste the full `cookie:` header from DevTools, auto-parsed

---

## Quick Start (Web UI)

### 1. Install

```bash
git clone https://github.com/mrshahbazdev/aliexpress-pinterest-bot.git
cd aliexpress-pinterest-bot
pip install -e .
```

### 2. Run

```bash
ae-pinner web
```

Open **http://localhost:5000** in your browser.

### 3. First Run — Database Setup

On first launch you'll see a **Database Setup** page. Enter your MySQL credentials:

| Field    | Example                            |
|----------|------------------------------------|
| Host     | `db.example.com`                   |
| Port     | `3306`                             |
| Database | `my_database`                      |
| Username | `db_user`                          |
| Password | `secret`                           |

Click **Connect & Save**. Credentials are stored locally in `~/.config/ae-pinner/config.json` (Linux) or `%APPDATA%\ae-pinner\config.json` (Windows) so you never need to enter them again.

### 4. Configure Cookies

Go to **Settings** and paste the full `cookie:` header from your browser:

1. Log into https://portals.aliexpress.com
2. Open DevTools (F12) → **Network** tab
3. Click any request → copy the entire `cookie:` header value
4. Paste it into the **Full Cookie Header** field

### 5. Fetch & Save Products

Go to **Fetch Products**, select page/count, click **Fetch & Preview**.
- **Save All to DB** — saves all fetched products (skips duplicates)
- **Save + Generate Pinterest** — saves and generates AI content

### 6. Generate Pinterest Content

Go to **Saved Products** and click **Generate Pinterest** on individual products, or use **Generate All** from the dashboard.

> Requires a Gemini or OpenAI API key (set in **Settings → AI Provider Settings**).

---

## Building an Executable (EXE)

Build a standalone `.exe` so the app runs without Python installed:

```bash
# Install PyInstaller
pip install pyinstaller

# Build the exe
pyinstaller --onefile --name ae-pinner \
  --hidden-import=ae_pinner.web \
  --hidden-import=ae_pinner.database \
  --hidden-import=ae_pinner.ai_generator \
  --hidden-import=ae_pinner.aliexpress \
  --hidden-import=ae_pinner.config \
  --hidden-import=mysql.connector \
  --collect-all flask \
  --collect-all jinja2 \
  src/ae_pinner/cli.py
```

The exe will be in `dist/ae-pinner.exe`. Run it:

```bash
# Start the web UI
./dist/ae-pinner web --port 5000

# Or on Windows
dist\ae-pinner.exe web --port 5000
```

All settings are stored in the local config file — no `.env` file needed.

---

## REST API

All API endpoints return JSON. Base URL: `http://localhost:5000`

### Products

| Method   | Endpoint                  | Description                |
|----------|---------------------------|----------------------------|
| `GET`    | `/api/products`           | List saved products        |
| `GET`    | `/api/products/<item_id>` | Get single product         |
| `DELETE` | `/api/products/<item_id>` | Delete a product           |
| `GET`    | `/api/stats`              | Product statistics         |

#### List Products

```bash
curl http://localhost:5000/api/products?page=1&per_page=20
```

```json
{
  "total": 48,
  "page": 1,
  "per_page": 20,
  "products": [
    {
      "item_id": "1005012175190799",
      "title": "Halo Cat Eye Nail Magnet Ring...",
      "discount_price": "USD 0.99",
      "original_price": "USD 2.73",
      "pin_title": "Only $0.99! Cat Eye Nail Tool...",
      "pin_description": "Transform your manicure...",
      "pin_generated": true
    }
  ]
}
```

#### Get Stats

```bash
curl http://localhost:5000/api/stats
```

```json
{
  "total": 48,
  "with_pins": 32,
  "without_pins": 16
}
```

### Fetch & Save

| Method | Endpoint                     | Description                        |
|--------|------------------------------|------------------------------------|
| `POST` | `/api/fetch`                 | Fetch products from AliExpress     |
| `POST` | `/api/generate/<item_id>`    | Generate Pinterest content for one |

#### Fetch Products

```bash
curl -X POST http://localhost:5000/api/fetch \
  -H "Content-Type: application/json" \
  -d '{"page": 1, "count": 12, "save": true}'
```

```json
{
  "page": 1,
  "fetched": 12,
  "saved": 10,
  "products": [...]
}
```

#### Generate Pinterest Content

```bash
curl -X POST http://localhost:5000/api/generate/1005012175190799
```

```json
{
  "item_id": "1005012175190799",
  "pin_title": "Only $0.99! Cat Eye Nail Magnet Tool - 64% OFF",
  "pin_description": "Transform your manicure... #nailart #beauty",
  "pin_alt_text": "Cat eye nail magnet ring tool..."
}
```

### Settings

| Method | Endpoint         | Description             |
|--------|------------------|-------------------------|
| `GET`  | `/api/settings`  | Get current settings    |
| `POST` | `/api/settings`  | Update settings         |

#### Get Settings

```bash
curl http://localhost:5000/api/settings
```

```json
{
  "cookies_set": true,
  "tracking_id": "default",
  "ship_to": "US",
  "currency": "USD",
  "language": "en",
  "gemini_key_set": true,
  "openai_key_set": false
}
```

#### Update Settings

```bash
curl -X POST http://localhost:5000/api/settings \
  -H "Content-Type: application/json" \
  -d '{"raw_cookie": "cna=...; xman_us_t=...", "tracking_id": "default"}'
```

---

## CLI Commands

### `ae-pinner web` — Start Web UI

```bash
ae-pinner web [--host 0.0.0.0] [--port 5000] [--debug]
```

No `.env` file required. Database credentials are entered via the web UI on first run.

### `ae-pinner run` — Create pins (CLI mode)

```bash
ae-pinner run --ai gemini --count 12
ae-pinner run --ai openai --count 5 --dry-run
```

| Option       | Default  | Description                          |
|--------------|----------|--------------------------------------|
| `--ai`       | `gemini` | AI provider (`gemini` or `openai`)   |
| `--page`     | `1`      | Page number                          |
| `--count`    | `12`     | Products to process (max 12)         |
| `--dry-run`  | off      | Preview without creating pins        |
| `--env-file` | `.env`   | Path to config file                  |

### `ae-pinner boards` — List Pinterest boards

```bash
ae-pinner boards
```

### `ae-pinner verify` — Check connections

```bash
ae-pinner verify
```

### `ae-pinner init-db` — Initialize database tables

```bash
ae-pinner init-db
```

---

## Configuration Storage

| Source | Priority | Description |
|--------|----------|-------------|
| Web UI / `config.json` | 1st | Local JSON file persisted by the app |
| `.env` / Environment | 2nd | Optional fallback for CLI usage |

Config file locations:
- **Linux**: `~/.config/ae-pinner/config.json`
- **macOS**: `~/Library/Application Support/ae-pinner/config.json`
- **Windows**: `%APPDATA%\ae-pinner\config.json`

---

## Project Structure

```
aliexpress-pinterest-bot/
├── src/ae_pinner/
│   ├── __init__.py        # Package metadata
│   ├── cli.py             # CLI commands (web, run, boards, verify)
│   ├── config.py          # Config loader (JSON + .env fallback)
│   ├── web.py             # Flask web UI + REST API
│   ├── database.py        # MySQL connection + CRUD operations
│   ├── aliexpress.py      # AliExpress API client
│   ├── ai_generator.py    # AI pin content (Gemini + OpenAI)
│   ├── pinterest.py       # Pinterest API v5
│   └── bot.py             # Main pipeline orchestrator
├── .env.example           # Template (optional, for CLI mode)
├── pyproject.toml         # Python package config
└── README.md
```

---

## Notes & Limitations

- **AliExpress cookies** expire periodically — refresh from browser when needed
- **Pinterest Trial Access** allows limited API calls per day
- **Rate limiting**: 1.5s delay between pin creations
- **Max 12 products** per API call (AliExpress pagination limit)
- Product images are on AliExpress CDN — no re-hosting needed

---

## License

MIT
