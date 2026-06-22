# AliExpress → Pinterest Auto-Pin Bot

Automatically fetch trending products from your AliExpress Affiliate Portal, generate AI-powered Pinterest descriptions (using **Gemini** or **OpenAI**), and create pins with your affiliate links.

## How It Works

```
AliExpress Affiliate API → AI (Gemini/OpenAI) → Pinterest API v5
     (products)             (descriptions)        (create pins)
```

1. **Fetch** trending/recommended products from `portals.aliexpress.com`
2. **Generate** affiliate promo links for each product
3. **AI-generate** catchy Pinterest titles, descriptions & hashtags
4. **Create** pins on your Pinterest board with affiliate links

## Setup

### 1. Install

```bash
pip install -e .
```

### 2. Configure

```bash
cp .env.example .env
# Edit .env with your credentials
```

### 3. Get Your Credentials

#### Pinterest Access Token
1. Go to https://developers.pinterest.com/apps/
2. Select your app → "Generate access token"
3. Grant `pins:read`, `pins:write`, `boards:read` permissions

#### Pinterest Board ID
```bash
ae-pinner boards  # Lists your boards with IDs
```

#### Gemini API Key (Free)
1. Go to https://aistudio.google.com/apikey
2. Create an API key

#### AliExpress Cookies
1. Log into https://portals.aliexpress.com
2. Open DevTools → Network tab
3. Find any request and copy `xman_us_t` and `xman_us_f` cookie values

## Usage

### Create pins (full run)
```bash
ae-pinner run --ai gemini --count 12
```

### Dry run (preview without creating pins)
```bash
ae-pinner run --ai gemini --count 5 --dry-run
```

### Use OpenAI instead of Gemini
```bash
ae-pinner run --ai openai --count 12
```

### Verify all connections
```bash
ae-pinner verify
```

### List Pinterest boards
```bash
ae-pinner boards
```

## Options

| Flag | Default | Description |
|------|---------|-------------|
| `--ai` | `gemini` | AI provider (`gemini` or `openai`) |
| `--page` | `1` | Page number for products |
| `--count` | `12` | Products per run (max 12) |
| `--dry-run` | off | Preview mode, no pins created |
| `--env-file` | `.env` | Path to config file |

## Architecture

```
src/ae_pinner/
├── __init__.py
├── cli.py           # Click CLI commands
├── config.py        # .env loader
├── aliexpress.py    # AliExpress API client
├── ai_generator.py  # OpenAI + Gemini pin content generator
├── pinterest.py     # Pinterest API v5 client
└── bot.py           # Main orchestrator
```

## Notes

- AliExpress cookies expire periodically — refresh them from your browser
- Pinterest trial access allows limited API calls
- Rate limit: 1.5s delay between pin creations to avoid Pinterest throttling
- Product images from AliExpress are public URLs — no hosting needed
