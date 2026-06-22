# AliExpress → Pinterest Auto-Pin Bot

Automatically fetch trending products from your AliExpress Affiliate Portal, generate AI-powered Pinterest descriptions (using **Google Gemini** or **OpenAI**), and create pins with your affiliate links — all in one command.

## How It Works

```
AliExpress Affiliate Portal API → AI (Gemini / OpenAI) → Pinterest API v5
       (trending products)         (pin descriptions)       (create pins)
```

### Pipeline:
1. **Fetch** trending/recommended products from `portals.aliexpress.com/material/productRecommend.do`
2. **Generate** affiliate promo links via `portals.aliexpress.com/promote/promoteNow.do`
3. **AI-generate** catchy Pinterest titles, descriptions & hashtags (Gemini or OpenAI)
4. **Create** pins on your Pinterest board with product images + affiliate links

### Key Features:
- Supports **Google Gemini** (free tier available) and **OpenAI GPT-4o-mini**
- Uses product images directly from AliExpress (no hosting needed)
- AI generates optimized titles, descriptions with hashtags, and alt text
- Built-in rate limiting (1.5s between pins) to avoid Pinterest throttling
- Dry-run mode to preview pins before creating
- CLI tool with helpful commands (`run`, `boards`, `verify`)

---

## Quick Start

### 1. Install

```bash
git clone https://github.com/mrshahbazdev/aliexpress-pinterest-bot.git
cd aliexpress-pinterest-bot
pip install -e .
```

### 2. Configure

```bash
cp .env.example .env
```

Edit `.env` with your credentials (see below).

### 3. Run

```bash
# Create 12 pins with Gemini AI
ae-pinner run --ai gemini --count 12

# Preview without creating pins
ae-pinner run --ai gemini --count 5 --dry-run

# Use OpenAI instead
ae-pinner run --ai openai --count 12
```

---

## Configuration

### `.env` File

```env
# Pinterest API
PINTEREST_ACCESS_TOKEN=your_token_here
PINTEREST_BOARD_ID=your_board_id_here

# AI Provider (set at least one)
GEMINI_API_KEY=your_gemini_key_here        # Option 1: Google Gemini (free)
OPENAI_API_KEY=your_openai_key_here        # Option 2: OpenAI

# AliExpress Session Cookies
AE_COOKIE_XMAN_US_T=your_xman_us_t_cookie
AE_COOKIE_XMAN_US_F=your_xman_us_f_cookie
AE_TRACKING_ID=default

# Pin Settings
PIN_LANGUAGE=en
PIN_SHIP_TO=US
PIN_CURRENCY=USD
```

---

## Getting Your Credentials

### Pinterest Access Token
1. Go to https://developers.pinterest.com/apps/
2. Select your app (e.g., "cracknns" App ID: 1475080)
3. Click **"Generate access token"**
4. Grant scopes: `pins:read`, `pins:write`, `boards:read`
5. Copy the token into `.env`

### Pinterest Board ID
```bash
ae-pinner boards
# Output:
#   ID: 1234567890  Name: My Products Board
```

### Gemini API Key (Free)
1. Go to https://aistudio.google.com/apikey
2. Click "Create API Key"
3. Copy it into `.env`

### OpenAI API Key (Alternative)
1. Go to https://platform.openai.com/api-keys
2. Create a new key
3. Copy it into `.env`

### AliExpress Cookies
1. Log into https://portals.aliexpress.com (affiliate portal)
2. Open browser DevTools (F12) → **Network** tab
3. Click any request to `portals.aliexpress.com`
4. Find in **Cookie** header:
   - `xman_us_t` → copy value to `AE_COOKIE_XMAN_US_T`
   - `xman_us_f` → copy value to `AE_COOKIE_XMAN_US_F`

> **Note:** AliExpress cookies expire periodically. Refresh them from your browser when the bot stops fetching products.

---

## CLI Commands

### `ae-pinner run` — Create pins
```bash
ae-pinner run [OPTIONS]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--ai` | `gemini` | AI provider (`gemini` or `openai`) |
| `--page` | `1` | Page number for product recommendations |
| `--count` | `12` | Number of products to process (max 12) |
| `--dry-run` | off | Preview mode — no pins created |
| `--env-file` | `.env` | Path to config file |

### `ae-pinner boards` — List Pinterest boards
```bash
ae-pinner boards
```
Shows all your boards with their IDs (needed for `PINTEREST_BOARD_ID`).

### `ae-pinner verify` — Check connections
```bash
ae-pinner verify
```
Tests Pinterest API, AliExpress cookies, and AI key configuration.

---

## Project Structure

```
aliexpress-pinterest-bot/
├── src/ae_pinner/
│   ├── __init__.py        # Package metadata
│   ├── cli.py             # Click CLI (run, boards, verify commands)
│   ├── config.py          # .env loader & validation
│   ├── aliexpress.py      # AliExpress API client (fetch + promo links)
│   ├── ai_generator.py    # AI pin content (Gemini + OpenAI support)
│   ├── pinterest.py       # Pinterest API v5 (create pins)
│   └── bot.py             # Main orchestrator pipeline
├── .env.example           # Template configuration
├── pyproject.toml         # Python package config
└── README.md
```

---

## How AI Generates Pin Content

The bot sends product details to the AI and gets back:

| Field | Example |
|-------|---------|
| **Title** | `Only $0.99! Cat Eye Nail Magnet Tool - 64% OFF` |
| **Description** | `Transform your manicure with this magnetic nail art tool. Was $2.73, now just $0.99! #nailart #manicure #beauty #deals #cateyenails` |
| **Alt Text** | `Cat eye nail magnet ring tool with handle for gel polish manicure` |

The AI is prompted to:
- Keep titles under 100 chars and catchy
- Include 5-8 relevant hashtags
- Mention price drops and urgency
- Use 2-3 emojis for visual appeal
- Sound organic, not spammy

---

## API Endpoints Used

### AliExpress Affiliate Portal
- `GET /material/productRecommend.do` — Fetch trending products
- `GET /promote/promoteNow.do` — Generate affiliate promo link

### Pinterest API v5
- `POST /v5/pins` — Create a pin
- `GET /v5/boards` — List user boards
- `GET /v5/user_account` — Verify token

---

## Notes & Limitations

- **Pinterest Trial Access** allows limited API calls per day
- **AliExpress cookies** expire — refresh from browser when needed
- **Rate limiting**: 1.5s delay between pin creations
- **Max 12 products** per API call (AliExpress pagination)
- Product images are publicly hosted on AliExpress CDN — no re-hosting needed

---

## License

MIT
