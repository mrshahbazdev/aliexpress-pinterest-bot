"""Flask web UI for managing AliExpress products and Pinterest content.

Provides a dashboard to:
- Configure database connection via the UI (no .env needed)
- Paste browser cookies and configure settings
- Fetch products page-by-page from AliExpress
- Save products to MySQL (duplicate-free)
- Generate Pinterest titles, descriptions & hashtags via AI
- REST API for programmatic access
"""

from __future__ import annotations

import asyncio
import base64
import httpx
import json
import math
import urllib.parse

from flask import Flask, jsonify, redirect, request, url_for

from ae_pinner.ai_generator import AIProvider, generate_pin_content
from ae_pinner.aliexpress import AliExpressClient, Product
from ae_pinner.config import Config
from ae_pinner.database import Database
from ae_pinner.pinterest import PinterestClient

app = Flask(__name__)

_db: Database | None = None
_config: Config | None = None


def get_db() -> Database:
    assert _db is not None, "Database not initialized"
    return _db


def get_config() -> Config:
    assert _config is not None, "Config not initialized"
    return _config


def _is_db_ready() -> bool:
    return _db is not None


def init_app(config: Config) -> Flask:
    """Initialize Flask app with config and database."""
    global _db, _config
    _config = config
    if config.db_configured:
        try:
            _db = Database(
                host=config.db_host,
                port=config.db_port,
                name=config.db_name,
                user=config.db_user,
                password=config.db_password,
            )
            _db.init_tables()
        except Exception:
            _db = None
    return app


def _try_connect_db(host: str, port: int, name: str, user: str, password: str) -> str:
    """Try connecting to DB. Returns empty string on success, error msg on fail."""
    global _db
    try:
        db = Database(host=host, port=port, name=name, user=user, password=password)
        db.init_tables()
        _db = db
        return ""
    except Exception as e:
        return str(e)


# ---------------------------------------------------------------------------
# Master HTML template (single-page feel with dark theme)
# ---------------------------------------------------------------------------

MASTER_TEMPLATE = r"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AE &rarr; Pinterest Bot</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
     background:#0a0a0f;color:#e0e0e0;min-height:100vh}

/* --- Navbar --- */
.nav{background:#12121f;padding:14px 24px;display:flex;align-items:center;
     justify-content:space-between;border-bottom:1px solid #1e1e35;
     position:sticky;top:0;z-index:50}
.nav h1{font-size:18px;color:#ff4757;letter-spacing:.5px}
.nav-links{display:flex;gap:6px}
.nav-links a{color:#888;text-decoration:none;font-size:13px;
     padding:6px 14px;border-radius:6px;transition:.2s}
.nav-links a:hover,.nav-links a.active{color:#fff;background:#1e1e35}

/* --- Container --- */
.container{max-width:1280px;margin:0 auto;padding:20px 24px}

/* --- Stats row --- */
.stats{display:grid;gap:14px;margin-bottom:20px;
     grid-template-columns:repeat(auto-fit,minmax(180px,1fr))}
.stat{background:#12121f;border-radius:10px;padding:18px;
     text-align:center;border:1px solid #1e1e35}
.stat .n{font-size:28px;font-weight:700;color:#ff4757}
.stat .l{font-size:12px;color:#666;margin-top:2px}

/* --- Card / Section --- */
.card{background:#12121f;border-radius:12px;padding:22px;
     border:1px solid #1e1e35;margin-bottom:20px}
.card h2{color:#ff4757;font-size:16px;margin-bottom:14px;
     display:flex;align-items:center;gap:8px}

/* --- Alerts --- */
.alert{padding:10px 16px;border-radius:8px;margin-bottom:14px;font-size:13px}
.alert-ok{background:rgba(22,199,132,.12);color:#16c784;
     border:1px solid #16c78466}
.alert-err{background:rgba(234,57,67,.12);color:#ea3943;
     border:1px solid #ea394366}
.alert-info{background:rgba(255,71,87,.08);color:#ff4757;
     border:1px solid #ff475766}

/* --- Buttons --- */
.btn{display:inline-flex;align-items:center;gap:6px;
     padding:8px 18px;border-radius:7px;border:none;cursor:pointer;
     font-size:13px;font-weight:500;text-decoration:none;transition:.15s}
.btn-red{background:#ff4757;color:#fff}
.btn-red:hover{background:#e03e4d}
.btn-green{background:#16c784;color:#fff}
.btn-green:hover{background:#12a86d}
.btn-gray{background:#222238;color:#aaa;border:1px solid #333}
.btn-gray:hover{background:#2a2a45}
.btn-sm{padding:5px 12px;font-size:12px}

/* --- Form --- */
.form-row{display:flex;gap:10px;align-items:end;flex-wrap:wrap}
.fg{display:flex;flex-direction:column;gap:3px}
.fg label{font-size:11px;color:#666;
     text-transform:uppercase;letter-spacing:.5px}
.fg input,.fg select,.fg textarea{
     background:#0a0a0f;border:1px solid #333;color:#e0e0e0;
     border-radius:6px;padding:8px 12px;font-size:13px;font-family:inherit}
.fg textarea{min-height:80px;resize:vertical;
     font-family:'Courier New',monospace;font-size:12px}

/* --- Product grid --- */
.pgrid{display:grid;gap:14px;
     grid-template-columns:repeat(auto-fill,minmax(320px,1fr))}
.pcard{background:#0e0e1a;border:1px solid #1e1e35;
     border-radius:10px;overflow:hidden;transition:.2s;position:relative}
.pcard:hover{border-color:#ff4757;transform:translateY(-1px)}
.pcard img{width:100%;height:200px;object-fit:cover}
.pcard .body{padding:14px}
.pcard .ttl{font-size:13px;font-weight:600;margin-bottom:6px;
     display:-webkit-box;-webkit-line-clamp:2;
     -webkit-box-orient:vertical;overflow:hidden;line-height:1.4}
.pcard .prices{display:flex;align-items:center;gap:8px;margin-bottom:6px}
.pcard .price{color:#ff4757;font-weight:700;font-size:17px}
.pcard .oprice{color:#555;text-decoration:line-through;font-size:12px}
.pcard .disc{background:#ff4757;color:#fff;padding:1px 7px;
     border-radius:4px;font-size:11px;font-weight:700}
.pcard .meta{display:flex;gap:10px;font-size:11px;
     color:#666;margin-bottom:10px}
.pcard .acts{display:flex;gap:6px;flex-wrap:wrap}
.badge{display:inline-block;padding:2px 8px;border-radius:4px;
     font-size:10px;font-weight:600}
.badge-ok{background:rgba(22,199,132,.15);color:#16c784}
.badge-warn{background:rgba(255,71,87,.15);color:#ff4757}
.badge-dup{background:rgba(255,193,7,.15);color:#ffc107}

/* --- Pin content box --- */
.pin-box{background:#0a0a0f;border-radius:8px;padding:10px 12px;
     margin-top:10px;border:1px solid #1a1a30;font-size:12px}
.pin-box h4{color:#16c784;font-size:12px;margin-bottom:6px}
.pin-box .pt{color:#e0e0e0;font-weight:600;margin-bottom:3px}
.pin-box .pd{color:#999;line-height:1.5}

/* --- Pagination --- */
.pagi{display:flex;gap:6px;justify-content:center;margin-top:18px}
.pagi a{padding:6px 13px;background:#12121f;color:#888;
     border-radius:6px;text-decoration:none;
     border:1px solid #1e1e35;font-size:13px;transition:.15s}
.pagi a.cur{background:#ff4757;color:#fff;border-color:#ff4757}
.pagi a:hover{border-color:#ff4757}

.empty{text-align:center;padding:40px;color:#555}
.empty p{margin-bottom:14px}

/* --- Cookie status indicator --- */
.cookie-status{display:inline-flex;align-items:center;gap:6px;
     font-size:12px;padding:4px 10px;border-radius:20px}
.cookie-status.ok{background:rgba(22,199,132,.12);color:#16c784}
.cookie-status.none{background:rgba(234,57,67,.12);color:#ea3943}

/* --- Setup page --- */
.setup-center{max-width:520px;margin:60px auto;text-align:center}
.setup-center h2{color:#ff4757;font-size:22px;margin-bottom:8px}
.setup-center p{color:#666;margin-bottom:20px;font-size:14px}
.setup-center .card{text-align:left}
</style>
</head>
<body>
{% if show_nav %}
<nav class="nav">
  <h1>AliExpress &rarr; Pinterest Bot</h1>
  <div class="nav-links">
    <a href="/"
       class="{{ 'active' if page_name == 'dashboard' }}">Dashboard</a>
    <a href="/settings"
       class="{{ 'active' if page_name == 'settings' }}">Settings</a>
    <a href="/fetch"
       class="{{ 'active' if page_name == 'fetch' }}">Fetch Products</a>
    <a href="/products"
       class="{{ 'active' if page_name == 'products' }}">Saved ({{ saved_count }})</a>
  </div>
</nav>
{% endif %}
<div class="container">
{% if msg %}
<div class="alert alert-{{ msg_cls }}">{{ msg }}</div>
{% endif %}
{% block content %}{% endblock %}
</div>
</body>
</html>
"""

# ---------------------------------------------------------------------------
# Database setup template (first-run)
# ---------------------------------------------------------------------------

SETUP_TPL = """
{% extends "master" %}
{% block content %}
<div class="setup-center">
  <h2>Database Setup</h2>
  <p>Enter your MySQL database credentials to get started.</p>
  <div class="card">
    <form method="post" action="/setup">
      <div class="fg" style="margin-bottom:12px">
        <label>Host</label>
        <input name="db_host" value="{{ db_host }}"
               placeholder="db.example.com" required>
      </div>
      <div class="form-row" style="margin-bottom:12px">
        <div class="fg" style="flex:1">
          <label>Port</label>
          <input name="db_port" type="number"
                 value="{{ db_port }}" placeholder="3306">
        </div>
        <div class="fg" style="flex:2">
          <label>Database Name</label>
          <input name="db_name" value="{{ db_name }}"
                 placeholder="my_database" required>
        </div>
      </div>
      <div class="form-row" style="margin-bottom:12px">
        <div class="fg" style="flex:1">
          <label>Username</label>
          <input name="db_user" value="{{ db_user }}"
                 placeholder="db_user" required>
        </div>
        <div class="fg" style="flex:1">
          <label>Password</label>
          <input name="db_password" type="password"
                 value="{{ db_password }}" placeholder="password" required>
        </div>
      </div>
      <button type="submit" class="btn btn-red"
              style="width:100%;justify-content:center">
        Connect &amp; Save
      </button>
    </form>
  </div>
</div>
{% endblock %}
"""

DASHBOARD_TPL = """
{% extends "master" %}
{% block content %}
<div class="stats">
  <div class="stat">
    <div class="n">{{ stats.total }}</div>
    <div class="l">Total Products</div>
  </div>
  <div class="stat">
    <div class="n">{{ stats.with_pins }}</div>
    <div class="l">Pinterest Ready</div>
  </div>
  <div class="stat">
    <div class="n" style="color:#E60023">{{ stats.published }}</div>
    <div class="l">Published</div>
  </div>
  <div class="stat">
    <div class="n">{{ stats.without_pins }}</div>
    <div class="l">Pending AI</div>
  </div>
</div>
<div class="card">
  <h2>Quick Actions</h2>
  <div style="display:flex;gap:10px;flex-wrap:wrap;align-items:center">
    {% if cookie_ok %}
      <span class="cookie-status ok">Cookies configured</span>
    {% else %}
      <span class="cookie-status none">No cookies &mdash;
        <a href="/settings" style="color:#ea3943">set up first</a>
      </span>
    {% endif %}
    <a href="/fetch" class="btn btn-red">Fetch New Products</a>
    <a href="/products" class="btn btn-gray">View Saved</a>
    {% if stats.without_pins > 0 %}
    <form method="post" action="/generate-all" style="display:inline">
      <button class="btn btn-green">
        Generate All Pinterest ({{ stats.without_pins }})
      </button>
    </form>
    {% endif %}
    {% if stats.ready_to_publish > 0 %}
    <form method="post" action="/publish-all" style="display:inline">
      <button class="btn" style="background:#E60023;color:#fff">
        Publish All to Pinterest ({{ stats.ready_to_publish }})
      </button>
    </form>
    {% endif %}
  </div>
</div>
{% endblock %}
"""

SETTINGS_TPL = """
{% extends "master" %}
{% block content %}
<div class="card">
  <h2>AliExpress Request Headers</h2>
  <p style="color:#666;font-size:13px;margin-bottom:14px">
    Open Chrome DevTools &rarr; Network tab &rarr; click any request to
    <code>portals.aliexpress.com</code> &rarr; copy the <b>Request Headers</b>
    section and paste below. Cookies, User-Agent, Referer etc. are extracted
    automatically.
  </p>
  <form method="post" action="/settings">
    <div class="fg" style="margin-bottom:14px">
      <label>Raw Request Headers (paste from Chrome DevTools)</label>
      <textarea name="raw_headers" rows="10"
                style="font-size:11px;line-height:1.4"
                placeholder=":authority&#10;portals.aliexpress.com&#10;:method&#10;GET&#10;cookie&#10;cna=...; xman_us_t=...&#10;user-agent&#10;Mozilla/5.0 ..."
                >{{ raw_headers }}</textarea>
    </div>
    {% if headers_parsed %}
    <div class="alert alert-ok" style="margin-bottom:14px">
      Headers parsed: cookie {{ 'found' if cookie_found else 'MISSING' }},
      user-agent {{ 'found' if ua_found else 'missing' }},
      referer {{ 'found' if referer_found else 'missing' }}
    </div>
    {% endif %}
    <div class="form-row" style="margin-bottom:14px">
      <div class="fg">
        <label>Tracking ID</label>
        <input name="tracking_id" value="{{ tracking_id }}"
               placeholder="default">
      </div>
      <div class="fg">
        <label>Ship To</label>
        <input name="ship_to" value="{{ ship_to }}"
               placeholder="US" style="width:80px">
      </div>
      <div class="fg">
        <label>Currency</label>
        <input name="currency" value="{{ currency }}"
               placeholder="USD" style="width:80px">
      </div>
      <div class="fg">
        <label>Language</label>
        <input name="language" value="{{ language }}"
               placeholder="en" style="width:80px">
      </div>
    </div>
    <button type="submit" class="btn btn-red">Save Settings</button>
  </form>
</div>
<div class="card">
  <h2 style="color:#E60023">
    <svg width="20" height="20" viewBox="0 0 24 24" fill="#E60023" style="vertical-align:middle;margin-right:6px">
      <path d="M12 0C5.373 0 0 5.373 0 12c0 5.084 3.163 9.426 7.627 11.174-.105-.949-.2-2.405.042-3.441.218-.937 1.407-5.965 1.407-5.965s-.359-.719-.359-1.782c0-1.668.967-2.914 2.171-2.914 1.023 0 1.518.769 1.518 1.69 0 1.029-.655 2.568-.994 3.995-.283 1.194.599 2.169 1.777 2.169 2.133 0 3.772-2.249 3.772-5.495 0-2.873-2.064-4.882-5.012-4.882-3.414 0-5.418 2.561-5.418 5.207 0 1.031.397 2.138.893 2.738.098.119.112.224.083.345l-.333 1.36c-.053.22-.174.267-.402.161-1.499-.698-2.436-2.889-2.436-4.649 0-3.785 2.75-7.262 7.929-7.262 4.163 0 7.398 2.967 7.398 6.931 0 4.136-2.607 7.464-6.227 7.464-1.216 0-2.359-.632-2.75-1.378l-.748 2.853c-.271 1.043-1.002 2.35-1.492 3.146C9.57 23.812 10.763 24 12 24c6.627 0 12-5.373 12-12S18.627 0 12 0z"/>
    </svg>
    Pinterest API Settings
  </h2>
  <p style="color:#666;font-size:13px;margin-bottom:14px">
    Enter your Pinterest App details to authenticate automatically and get publishing permissions.
    Get your App ID & Secret from
    <a href="https://developers.pinterest.com/apps/" target="_blank"
       style="color:#E60023">Pinterest Developer Portal</a>.<br>
    <strong style="color:#ff4757;margin-top:6px;display:inline-block">Important:</strong> 
    Make sure you add <code>http://localhost:5000/pinterest/callback</code> to your "Redirect URIs" on Pinterest!
  </p>
  <form method="post" action="/settings/pinterest">
    <div style="display:flex;gap:10px;margin-bottom:12px">
      <div class="fg" style="flex:1">
        <label>App ID (Client ID)</label>
        <input name="pinterest_client_id" value="{{ pinterest_client_id }}" placeholder="1475080">
      </div>
      <div class="fg" style="flex:1">
        <label>App Secret</label>
        <input name="pinterest_client_secret" type="password" value="{{ pinterest_client_secret }}" placeholder="••••••••">
      </div>
    </div>
    <div class="fg" style="margin-bottom:12px">
      <label>Access Token <small>(Auto-filled via Login or paste manually)</small></label>
      <input name="pinterest_token" type="password" id="pinterestTokenInput"
             value="{{ pinterest_token }}"
             placeholder="pina_...">
    </div>
    <div class="fg" style="margin-bottom:12px">
      <label>Board <small style="color:#555">(select where pins will be published)</small></label>
      <div style="display:flex;gap:8px;align-items:center">
        <select name="pinterest_board_id" id="boardSelect"
                style="flex:1;padding:10px 14px;background:#12121f;color:#e0e0e0;
                       border:1px solid #1e1e35;border-radius:8px;font-size:14px">
          {% if pinterest_board_id %}
          <option value="{{ pinterest_board_id }}" selected>
            {% if pinterest_board_name %}{{ pinterest_board_name }}{% else %}Board ID: {{ pinterest_board_id }}{% endif %}
          </option>
          {% else %}
          <option value="">-- Pehle token save karein, phir boards load hongi --</option>
          {% endif %}
          {% for board in pinterest_boards %}
          {% if board.id != pinterest_board_id %}
          <option value="{{ board.id }}">{{ board.name }}</option>
          {% endif %}
          {% endfor %}
        </select>
        <button type="button" onclick="fetchBoards()" class="btn btn-gray"
                style="white-space:nowrap;padding:10px 16px">
          &#8635; Load Boards
        </button>
      </div>
    </div>
    <div class="fg" style="margin-bottom:14px">
      <label style="display:flex;align-items:center;gap:10px;cursor:pointer">
        <input type="checkbox" name="auto_publish" value="1"
               {{ 'checked' if auto_publish }}
               style="width:18px;height:18px;accent-color:#E60023">
        <span>Auto-Publish: Generate hote hi pin automatically publish ho jaye</span>
      </label>
      <small style="color:#555;font-size:11px;display:block;margin-top:4px">
        Jab yeh ON hai, har product ka Pinterest content generate hone ke baad
        wo automatically aapki selected board par publish ho jayega.
      </small>
    </div>
    <div style="display:flex;gap:10px;align-items:center">
      <a href="/pinterest/login" class="btn" style="background:#E60023;color:#fff;text-decoration:none;padding:10px 16px;border-radius:6px;font-weight:bold">
        1. Login with Pinterest
      </a>
      <button type="submit" class="btn btn-gray" style="padding:10px 16px;border-radius:6px">2. Save Settings</button>
      {% if pinterest_token %}
      <span style="color:#4ecb71;font-size:13px">&#10003; Token configured</span>
      {% endif %}
    </div>
  </form>
</div>
<script>
function fetchBoards(){
  var token = document.getElementById('pinterestTokenInput').value;
  if(!token){alert('Pehle Access Token enter karein!');return;}
  var sel = document.getElementById('boardSelect');
  sel.innerHTML = '<option>Loading boards...</option>';
  fetch('/api/pinterest/boards', {
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify({token: token})
  })
  .then(r => r.json())
  .then(data => {
    if(data.error){sel.innerHTML='<option>Error: '+data.error+'</option>';return;}
    sel.innerHTML = '';
    if(data.boards.length === 0){
      sel.innerHTML = '<option value="">Koi board nahi mili</option>';
      return;
    }
    data.boards.forEach(function(b){
      var opt = document.createElement('option');
      opt.value = b.id;
      opt.textContent = b.name + (b.description ? ' - '+b.description.substring(0,30) : '');
      sel.appendChild(opt);
    });
  })
  .catch(e => {sel.innerHTML='<option>Error: '+e+'</option>';});
}
</script>
<div class="card">
  <h2>AI Provider Settings</h2>
  <form method="post" action="/settings/ai">
    <div class="form-row" style="margin-bottom:14px">
      <div class="fg" style="flex:1">
        <label>Gemini API Key (free tier)</label>
        <input name="gemini_key" type="password"
               value="{{ gemini_key }}" placeholder="AIza...">
      </div>
      <div class="fg" style="flex:1">
        <label>OpenAI API Key (alternative)</label>
        <input name="openai_key" type="password"
               value="{{ openai_key }}" placeholder="sk-...">
      </div>
    </div>
    <button type="submit" class="btn btn-red">Save AI Settings</button>
  </form>
</div>
<div class="card">
  <h2>Database Connection</h2>
  <form method="post" action="/settings/db">
    <div class="fg" style="margin-bottom:12px">
      <label>Host</label>
      <input name="db_host" value="{{ cfg_db_host }}"
             placeholder="db.example.com">
    </div>
    <div class="form-row" style="margin-bottom:12px">
      <div class="fg" style="flex:1">
        <label>Port</label>
        <input name="db_port" type="number"
               value="{{ cfg_db_port }}">
      </div>
      <div class="fg" style="flex:2">
        <label>Database Name</label>
        <input name="db_name" value="{{ cfg_db_name }}">
      </div>
    </div>
    <div class="form-row" style="margin-bottom:12px">
      <div class="fg" style="flex:1">
        <label>Username</label>
        <input name="db_user" value="{{ cfg_db_user }}">
      </div>
      <div class="fg" style="flex:1">
        <label>Password</label>
        <input name="db_password" type="password"
               value="{{ cfg_db_password }}">
      </div>
    </div>
    <button type="submit" class="btn btn-red">
      Save &amp; Reconnect
    </button>
  </form>
</div>
{% endblock %}
"""

FETCH_TPL = """
{% extends "master" %}
{% block content %}
<div class="card">
  <h2>Fetch Products from AliExpress</h2>
  {% if not cookie_ok %}
  <div class="alert alert-err">
    No cookies configured.
    <a href="/settings" style="color:#ea3943">Go to Settings</a> first.
  </div>
  {% endif %}
  <form method="post" action="/fetch">
    <div class="form-row">
      <div class="fg">
        <label>Page</label>
        <input type="number" name="page" value="{{ page_num }}"
               min="1" max="999" style="width:80px">
      </div>
      <div class="fg">
        <label>Count</label>
        <select name="count">
          <option value="6" {{ 'selected' if count == 6 }}>6</option>
          <option value="12"
                  {{ 'selected' if count == 12 }}>12</option>
        </select>
      </div>
      <button type="submit" class="btn btn-red"
              {{ 'disabled' if not cookie_ok }}>
        Fetch &amp; Preview
      </button>
    </div>
  </form>
</div>

{% if products %}
<div class="card">
  <h2>Page {{ page_num }} &mdash; {{ products|length }} products</h2>
  <div style="margin-bottom:14px;display:flex;gap:8px;flex-wrap:wrap">
    <form method="post" action="/save-page" style="display:inline">
      <input type="hidden" name="page" value="{{ page_num }}">
      <input type="hidden" name="count" value="{{ count }}">
      <input type="hidden" name="products_json"
             value="{{ products_json | e }}">
      <button type="submit" name="action" value="save"
              class="btn btn-green">Save All to DB</button>
      <button type="submit" name="action" value="save_gen"
              class="btn btn-red">Save + Generate Pinterest</button>
    </form>
  </div>
  <div class="pgrid">
  {% for p in products %}
    <div class="pcard">
      <img src="{{ p.image_url }}" alt="{{ p.title[:40] }}"
           loading="lazy">
      <div class="body">
        <div class="ttl">{{ p.title }}</div>
        <div class="prices">
          <span class="price">{{ p.discount_price }}</span>
          <span class="oprice">{{ p.original_price }}</span>
          {% if p.discount_rate %}
          <span class="disc">{{ p.discount_rate }}% OFF</span>
          {% endif %}
        </div>
        <div class="meta">
          <span>Sales: {{ p.sales_30day }}</span>
          <span>Rating: {{ p.comment_score }}</span>
          <span>Comm: {{ p.commission_rate }}%</span>
        </div>
        <div class="acts">
          <form method="post" action="/save-single"
                style="display:inline">
            <input type="hidden" name="product_json"
                   value='{{ p | tojson }}'>
            <button type="submit"
                    class="btn btn-green btn-sm">Save</button>
          </form>
          <a href="{{ p.item_url }}" target="_blank"
             class="btn btn-gray btn-sm">AliExpress</a>
          {% if p.is_duplicate %}
          <span class="badge badge-dup">Already Saved</span>
          {% endif %}
        </div>
      </div>
    </div>
  {% endfor %}
  </div>
</div>
<div class="pagi">
  {% if page_num > 1 %}
  <a href="/fetch?page={{ page_num - 1 }}&count={{ count }}">
    &larr; Prev</a>
  {% endif %}
  <a class="cur">Page {{ page_num }}</a>
  <a href="/fetch?page={{ page_num + 1 }}&count={{ count }}">
    Next &rarr;</a>
</div>
{% endif %}
{% endblock %}
"""

PRODUCTS_TPL = """
{% extends "master" %}
{% block content %}
<div class="card">
  <h2>Saved Products ({{ total }} total)</h2>
  {% if products %}
  <div style="margin-bottom:14px;display:flex;gap:8px">
    {% if pending_count > 0 %}
    <form method="post" action="/generate-all" style="display:inline">
      <button class="btn btn-green">
        Generate Pinterest for {{ pending_count }} pending
      </button>
    </form>
    {% endif %}
  </div>
  <div class="pgrid">
  {% for p in products %}
    <div class="pcard">
      <a href="/product/{{ p.item_id }}" style="text-decoration:none;color:inherit">
        <img src="{{ p.image_url }}" alt="{{ p.title[:40] }}"
             loading="lazy">
      </a>
      <div class="body">
        <a href="/product/{{ p.item_id }}"
           style="text-decoration:none;color:inherit">
          <div class="ttl">{{ p.title }}</div>
        </a>
        <div class="prices">
          <span class="price">{{ p.discount_price }}</span>
          <span class="oprice">{{ p.original_price }}</span>
          {% if p.discount_rate %}
          <span class="disc">{{ p.discount_rate }}% OFF</span>
          {% endif %}
        </div>
        <div class="meta">
          <span>Sales: {{ p.sales_30day }}</span>
          <span>Rating: {{ p.comment_score }}</span>
          <span>Commission: {{ p.commission_rate }}%</span>
          {% if p.pin_generated %}
          {% if p.pin_published %}
          <span class="badge" style="background:#1a3a1a;color:#4ecb71">Published</span>
          {% else %}
          <span class="badge badge-ok">Pinterest Ready</span>
          {% endif %}
          {% else %}
          <span class="badge badge-warn">No Pin</span>
          {% endif %}
        </div>
        {% if p.pin_generated %}
        <div class="pin-box">
          <h4>Pinterest Content</h4>
          <div class="pt">{{ p.pin_title }}</div>
          <div class="pd">{{ p.pin_description }}</div>
        </div>
        {% endif %}
        <div class="acts" style="margin-top:10px">
          <a href="/product/{{ p.item_id }}"
             class="btn btn-red btn-sm">View Details</a>
          {% if not p.pin_generated %}
          <form method="post"
                action="/generate/{{ p.item_id }}"
                style="display:inline">
            <button class="btn btn-green btn-sm">
              Generate Pinterest</button>
          </form>
          {% elif not p.pin_published %}
          <form method="post"
                action="/publish/{{ p.item_id }}"
                style="display:inline">
            <button class="btn btn-sm"
                    style="background:#E60023;color:#fff">
              Publish to Pinterest</button>
          </form>
          {% else %}
          <a href="{{ p.pin_url }}" target="_blank"
             class="btn btn-sm" style="background:#1a3a1a;color:#4ecb71">
            View on Pinterest</a>
          {% endif %}
          {% if p.promo_url %}
          <a href="{{ p.promo_url }}" target="_blank"
             class="btn btn-gray btn-sm">Affiliate Link</a>
          {% endif %}
          <a href="{{ p.item_url }}" target="_blank"
             class="btn btn-gray btn-sm">AliExpress</a>
          <form method="post"
                action="/delete/{{ p.item_id }}"
                style="display:inline"
                onsubmit="return confirm('Delete?')">
            <button class="btn btn-sm"
                    style="background:#2a1520;color:#ea3943">
              Delete</button>
          </form>
        </div>
      </div>
    </div>
  {% endfor %}
  </div>
  {% if total_pages > 1 %}
  <div class="pagi">
    {% for pg in range(1, total_pages + 1) %}
    <a href="/products?page={{ pg }}"
       class="{{ 'cur' if pg == current_page }}">{{ pg }}</a>
    {% endfor %}
  </div>
  {% endif %}
  {% else %}
  <div class="empty">
    <p>No products saved yet.</p>
    <a href="/fetch" class="btn btn-red">Fetch Products</a>
  </div>
  {% endif %}
</div>
{% endblock %}
"""


# ---------------------------------------------------------------------------
# Product detail template
# ---------------------------------------------------------------------------

PRODUCT_DETAIL_TPL = """
{% extends "master" %}
{% block content %}
<style>
.detail-top{display:grid;grid-template-columns:400px 1fr;gap:24px}
@media(max-width:800px){.detail-top{grid-template-columns:1fr}}
.detail-imgs{display:flex;flex-direction:column;gap:10px}
.detail-imgs .main-img{width:100%;border-radius:10px;
     border:1px solid #1e1e35;object-fit:cover;max-height:400px}
.detail-imgs .thumbs{display:flex;gap:6px;flex-wrap:wrap}
.detail-imgs .thumbs img{width:64px;height:64px;object-fit:cover;
     border-radius:6px;border:1px solid #1e1e35;cursor:pointer;
     transition:.2s;opacity:.7}
.detail-imgs .thumbs img:hover,.detail-imgs .thumbs img.active{
     opacity:1;border-color:#ff4757}
.detail-info h2{font-size:20px;color:#e0e0e0;margin-bottom:12px;
     line-height:1.4}
.detail-info .prices{display:flex;align-items:center;gap:12px;
     margin-bottom:14px}
.detail-info .price{font-size:28px;font-weight:700;color:#ff4757}
.detail-info .oprice{font-size:16px;color:#555;text-decoration:line-through}
.detail-info .disc{background:#ff4757;color:#fff;padding:3px 10px;
     border-radius:5px;font-size:13px;font-weight:700}
.detail-row{display:flex;gap:16px;flex-wrap:wrap;margin-bottom:14px}
.detail-stat{background:#0a0a0f;border:1px solid #1e1e35;
     border-radius:8px;padding:10px 16px;text-align:center;min-width:120px}
.detail-stat .n{font-size:18px;font-weight:700;color:#ff4757}
.detail-stat .l{font-size:11px;color:#666;margin-top:2px}
.detail-links{display:flex;gap:8px;flex-wrap:wrap;margin-top:16px}
.detail-links .btn{padding:10px 20px;font-size:14px}
.section{margin-top:20px}
.section h3{color:#ff4757;font-size:15px;margin-bottom:10px;
     border-bottom:1px solid #1e1e35;padding-bottom:6px}
.pin-detail{background:#0a0a0f;border:1px solid #1a1a30;
     border-radius:10px;padding:16px;margin-top:10px}
.pin-detail .label{font-size:11px;color:#666;text-transform:uppercase;
     letter-spacing:.5px;margin-bottom:3px}
.pin-detail .value{color:#e0e0e0;font-size:14px;margin-bottom:14px;
     line-height:1.6}
.pin-detail .value:last-child{margin-bottom:0}
.copy-btn{background:#222238;color:#aaa;border:1px solid #333;
     padding:4px 10px;border-radius:5px;cursor:pointer;font-size:11px;
     margin-left:8px;transition:.15s}
.copy-btn:hover{background:#2a2a45;color:#fff}
.pinterest-share{background:#E60023;color:#fff;padding:10px 22px;
     border-radius:8px;font-size:14px;font-weight:600;
     text-decoration:none;display:inline-flex;align-items:center;gap:8px}
.pinterest-share:hover{background:#c2001e}
</style>

<div style="margin-bottom:14px">
  <a href="/products" class="btn btn-gray">&larr; Back to Products</a>
</div>

<div class="card">
  <div class="detail-top">
    <div class="detail-imgs">
      <img class="main-img" id="mainImg"
           src="{{ p.image_url }}" alt="{{ p.title[:60] }}">
      {% if all_images|length > 1 %}
      <div class="thumbs">
        {% for img in all_images %}
        <img src="{{ img }}" alt="Image {{ loop.index }}"
             onclick="document.getElementById('mainImg').src=this.src;
                      document.querySelectorAll('.thumbs img').forEach(i=>i.classList.remove('active'));
                      this.classList.add('active')"
             class="{{ 'active' if loop.first }}">
        {% endfor %}
      </div>
      {% endif %}
    </div>

    <div class="detail-info">
      <h2>{{ p.title }}</h2>
      <div class="prices">
        <span class="price">{{ p.discount_price }}</span>
        <span class="oprice">{{ p.original_price }}</span>
        {% if p.discount_rate %}
        <span class="disc">{{ p.discount_rate }}% OFF</span>
        {% endif %}
      </div>

      <div class="detail-row">
        <div class="detail-stat">
          <div class="n">{{ p.sales_30day }}</div>
          <div class="l">Sales (30 day)</div>
        </div>
        <div class="detail-stat">
          <div class="n">{{ p.comment_score }}</div>
          <div class="l">Rating</div>
        </div>
        <div class="detail-stat">
          <div class="n">{{ p.commission_rate }}%</div>
          <div class="l">Commission</div>
        </div>
      </div>

      <div class="detail-stat" style="text-align:left;margin-bottom:14px;width:100%">
        <div class="l">Item ID</div>
        <div style="color:#e0e0e0;font-size:13px;word-break:break-all">{{ p.item_id }}</div>
      </div>

      <div class="detail-links">
        {% if p.promo_url %}
        <a href="{{ p.promo_url }}" target="_blank"
           class="btn btn-red">Affiliate Link</a>
        {% endif %}
        <a href="{{ p.item_url }}" target="_blank"
           class="btn btn-gray">View on AliExpress</a>
        {% if not p.pin_generated %}
        <form method="post" action="/generate/{{ p.item_id }}"
              style="display:inline">
          <button class="btn btn-green">Generate Pinterest SEO</button>
        </form>
        {% endif %}
        <form method="post" action="/delete/{{ p.item_id }}"
              style="display:inline"
              onsubmit="return confirm('Delete this product?')">
          <button class="btn"
                  style="background:#2a1520;color:#ea3943">Delete</button>
        </form>
      </div>
    </div>
  </div>
</div>

<div class="card section">
  <div style="display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid #1e1e35;padding-bottom:6px;margin-bottom:10px">
    <h3 style="border:none;padding:0;margin:0;color:#ff4757;font-size:15px">Pinterest Content (SEO)</h3>
  </div>
  <form method="post" action="/save-seo/{{ p.item_id }}">
    <div class="pin-detail" style="margin-top:10px">
      <div class="label" style="display:flex;justify-content:space-between">
        Pin Title
        <button type="button" class="copy-btn" onclick="copyText('pinTitleInput')" style="margin:0">Copy</button>
      </div>
      <input type="text" id="pinTitleInput" name="pin_title" value="{{ p.pin_title }}" 
             style="width:100%;background:#12121f;border:1px solid #1e1e35;color:#e0e0e0;padding:8px;border-radius:6px;margin-bottom:14px;font-size:14px">

      <div class="label" style="display:flex;justify-content:space-between">
        Pin Description
        <button type="button" class="copy-btn" onclick="copyText('pinDescInput')" style="margin:0">Copy</button>
      </div>
      <textarea id="pinDescInput" name="pin_description" 
                style="width:100%;height:100px;background:#12121f;border:1px solid #1e1e35;color:#e0e0e0;padding:8px;border-radius:6px;margin-bottom:14px;font-size:14px;resize:vertical">{{ p.pin_description }}</textarea>

      <div class="label" style="display:flex;justify-content:space-between">
        Alt Text
        <button type="button" class="copy-btn" onclick="copyText('pinAltInput')" style="margin:0">Copy</button>
      </div>
      <input type="text" id="pinAltInput" name="pin_alt_text" value="{{ p.pin_alt_text }}" 
             style="width:100%;background:#12121f;border:1px solid #1e1e35;color:#e0e0e0;padding:8px;border-radius:6px;margin-bottom:14px;font-size:14px">
      
      <div style="display:flex;gap:10px;margin-top:4px">
        <button type="submit" class="btn btn-gray" style="padding:8px 16px;font-size:13px">Save Manual SEO</button>
        {% if p.pin_generated and not p.pin_published %}
        <span style="color:#4ecb71;font-size:13px;align-self:center">&#10003; Ready to Publish</span>
        {% endif %}
      </div>
    </div>
  </form>

  {% if p.pin_generated %}
  <div style="margin-top:16px;display:flex;gap:10px;flex-wrap:wrap;align-items:center">
    {% if not p.pin_published %}
    <form method="post" action="/publish/{{ p.item_id }}" style="display:inline">
      <button class="btn" style="background:#E60023;color:#fff;padding:10px 22px;
              border-radius:8px;font-size:14px;font-weight:600;
              display:inline-flex;align-items:center;gap:8px;border:none;cursor:pointer">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
          <path d="M12 0C5.373 0 0 5.373 0 12c0 5.084 3.163 9.426 7.627 11.174-.105-.949-.2-2.405.042-3.441.218-.937 1.407-5.965 1.407-5.965s-.359-.719-.359-1.782c0-1.668.967-2.914 2.171-2.914 1.023 0 1.518.769 1.518 1.69 0 1.029-.655 2.568-.994 3.995-.283 1.194.599 2.169 1.777 2.169 2.133 0 3.772-2.249 3.772-5.495 0-2.873-2.064-4.882-5.012-4.882-3.414 0-5.418 2.561-5.418 5.207 0 1.031.397 2.138.893 2.738.098.119.112.224.083.345l-.333 1.36c-.053.22-.174.267-.402.161-1.499-.698-2.436-2.889-2.436-4.649 0-3.785 2.75-7.262 7.929-7.262 4.163 0 7.398 2.967 7.398 6.931 0 4.136-2.607 7.464-6.227 7.464-1.216 0-2.359-.632-2.75-1.378l-.748 2.853c-.271 1.043-1.002 2.35-1.492 3.146C9.57 23.812 10.763 24 12 24c6.627 0 12-5.373 12-12S18.627 0 12 0z"/>
        </svg>
        Publish to Pinterest
      </button>
    </form>
    {% else %}
    <a href="{{ p.pin_url }}" target="_blank"
       style="background:#1a3a1a;color:#4ecb71;padding:10px 22px;
              border-radius:8px;font-size:14px;font-weight:600;
              text-decoration:none;display:inline-flex;align-items:center;gap:8px">
      &#10003; Published &mdash; View on Pinterest
    </a>
    {% endif %}
    <a href="https://www.pinterest.com/pin-builder/?description={{ pin_desc_encoded }}&media={{ pin_media_encoded }}&url={{ pin_url_encoded }}"
       target="_blank" class="pinterest-share" style="background:#333;color:#ccc">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
        <path d="M12 0C5.373 0 0 5.373 0 12c0 5.084 3.163 9.426 7.627 11.174-.105-.949-.2-2.405.042-3.441.218-.937 1.407-5.965 1.407-5.965s-.359-.719-.359-1.782c0-1.668.967-2.914 2.171-2.914 1.023 0 1.518.769 1.518 1.69 0 1.029-.655 2.568-.994 3.995-.283 1.194.599 2.169 1.777 2.169 2.133 0 3.772-2.249 3.772-5.495 0-2.873-2.064-4.882-5.012-4.882-3.414 0-5.418 2.561-5.418 5.207 0 1.031.397 2.138.893 2.738.098.119.112.224.083.345l-.333 1.36c-.053.22-.174.267-.402.161-1.499-.698-2.436-2.889-2.436-4.649 0-3.785 2.75-7.262 7.929-7.262 4.163 0 7.398 2.967 7.398 6.931 0 4.136-2.607 7.464-6.227 7.464-1.216 0-2.359-.632-2.75-1.378l-.748 2.853c-.271 1.043-1.002 2.35-1.492 3.146C9.57 23.812 10.763 24 12 24c6.627 0 12-5.373 12-12S18.627 0 12 0z"/>
      </svg>
      Manual Share
    </a>
    {% if p.promo_url %}
    <button class="copy-btn" style="padding:10px 16px;font-size:13px"
            onclick="copyText('affiliateUrl')">Copy Affiliate Link</button>
    <span id="affiliateUrl" style="display:none">{{ p.promo_url }}</span>
    {% endif %}
  </div>
  {% endif %}
</div>

{% if all_images|length > 1 %}
<div class="card section">
  <h3>All Product Images ({{ all_images|length }})</h3>
  <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:10px;margin-top:10px">
    {% for img in all_images %}
    <a href="{{ img }}" target="_blank">
      <img src="{{ img }}" alt="Product image {{ loop.index }}"
           style="width:100%;height:150px;object-fit:cover;border-radius:8px;
                  border:1px solid #1e1e35;transition:.2s"
           onmouseover="this.style.borderColor='#ff4757'"
           onmouseout="this.style.borderColor='#1e1e35'">
    </a>
    {% endfor %}
  </div>
</div>
{% endif %}

<script>
function copyText(id){
  var el=document.getElementById(id);
  var t=el.value !== undefined ? el.value : (el.innerText||el.textContent);
  navigator.clipboard.writeText(t).then(function(){
    var btns=document.querySelectorAll('.copy-btn');
    btns.forEach(function(b){if(b.onclick&&b.onclick.toString().indexOf(id)>-1){
      var orig=b.textContent;b.textContent='Copied!';
      setTimeout(function(){b.textContent=orig},1500)}})
  })
}
</script>
{% endblock %}
"""


# ---------------------------------------------------------------------------
# Template engine (inline Jinja2)
# ---------------------------------------------------------------------------

_TEMPLATES: dict[str, str] = {
    "master": MASTER_TEMPLATE,
    "setup": SETUP_TPL,
    "dashboard": DASHBOARD_TPL,
    "settings": SETTINGS_TPL,
    "fetch": FETCH_TPL,
    "products": PRODUCTS_TPL,
    "product_detail": PRODUCT_DETAIL_TPL,
}


def _render(template_name: str, **kwargs: object) -> str:
    from jinja2 import BaseLoader, Environment

    class _Loader(BaseLoader):
        def get_source(self, environment: Environment, name: str) -> tuple[str, str | None, None]:
            src = _TEMPLATES.get(name)
            if src is None:
                raise FileNotFoundError(name)
            return src, name, None

    env = Environment(loader=_Loader())
    env.filters["tojson"] = lambda v: json.dumps(v, default=str)
    tmpl = env.get_template(template_name)

    kwargs.setdefault("show_nav", _is_db_ready())
    if _is_db_ready():
        db = get_db()
        stats = db.get_stats()
        kwargs.setdefault("saved_count", stats["total"])
    else:
        kwargs.setdefault("saved_count", 0)
    kwargs.setdefault("msg", request.args.get("msg", ""))
    kwargs.setdefault("msg_cls", request.args.get("msg_cls", "info"))

    return tmpl.render(**kwargs)


def _get_ae_client() -> AliExpressClient | None:
    """Build an AliExpressClient from saved header/cookie settings."""
    db = get_db()
    raw_headers = db.get_setting("raw_headers")
    raw_cookie = db.get_setting("raw_cookie")
    if not raw_headers and not raw_cookie:
        return None
    tracking_id = db.get_setting("tracking_id") or "default"
    if raw_headers:
        return AliExpressClient(raw_headers=raw_headers, tracking_id=tracking_id)
    return AliExpressClient(raw_cookie=raw_cookie, tracking_id=tracking_id)


def _get_fetch_params() -> tuple[str, str, str]:
    """Return (ship_to, currency, language) from DB settings."""
    db = get_db()
    return (
        db.get_setting("ship_to") or "US",
        db.get_setting("currency") or "USD",
        db.get_setting("language") or "en",
    )


def _product_to_dict(p: Product, db: Database) -> dict:
    return {
        "item_id": p.item_id,
        "main_item_id": p.main_item_id,
        "title": p.title,
        "image_url": p.image_url,
        "all_images": p.all_images,
        "original_price": p.original_price,
        "discount_price": p.discount_price,
        "discount_rate": p.discount_rate,
        "sales_30day": p.sales_30day,
        "comment_score": p.comment_score,
        "commission_rate": p.commission_rate,
        "item_url": p.item_url,
        "promo_url": p.promo_url or "",
        "raw_json": p.raw_json,
        "promo_response": p.promo_response,
        "is_duplicate": db.product_exists(p.item_id),
    }


def _dict_to_product(d: dict) -> Product:
    return Product(
        item_id=str(d["item_id"]),
        main_item_id=str(d.get("main_item_id", "")),
        title=d["title"],
        image_url=d.get("image_url", ""),
        all_images=d.get("all_images", []),
        original_price=d.get("original_price", ""),
        discount_price=d.get("discount_price", ""),
        discount_rate=d.get("discount_rate", ""),
        sales_30day=int(d.get("sales_30day", 0)),
        comment_score=d.get("comment_score", ""),
        commission_rate=d.get("commission_rate", ""),
        item_url=d.get("item_url", ""),
        promo_url=d.get("promo_url"),
        raw_json=d.get("raw_json", ""),
        promo_response=d.get("promo_response", ""),
    )


def _dbproduct_to_product(db_product) -> Product:
    """Convert a DBProduct row into a Product for AI generation."""
    return Product(
        item_id=db_product.item_id,
        main_item_id=db_product.main_item_id,
        title=db_product.title,
        image_url=db_product.image_url,
        all_images=(db_product.all_images.split(",") if db_product.all_images else []),
        original_price=db_product.original_price,
        discount_price=db_product.discount_price,
        discount_rate=db_product.discount_rate,
        sales_30day=db_product.sales_30day,
        comment_score=db_product.comment_score,
        commission_rate=db_product.commission_rate,
        item_url=db_product.item_url,
        promo_url=db_product.promo_url,
    )


def _get_ai_keys() -> tuple[str, str]:
    """Return (gemini_key, openai_key) from DB settings."""
    db = get_db()
    gemini = db.get_setting("gemini_key")
    openai = db.get_setting("openai_key")
    return gemini, openai


def _get_pinterest_client() -> PinterestClient | None:
    """Build a PinterestClient from saved settings. Returns None if not configured."""
    db = get_db()
    token = db.get_setting("pinterest_token")
    if not token:
        return None
    return PinterestClient(access_token=token)


def _get_pinterest_board_id() -> str:
    """Return the configured Pinterest board ID."""
    db = get_db()
    return db.get_setting("pinterest_board_id") or ""


def _generate_pin_for_product(product: Product) -> bool:
    """Generate Pinterest content and save to DB. Auto-publishes if enabled."""
    db = get_db()
    gemini_key, openai_key = _get_ai_keys()
    if not gemini_key and not openai_key:
        return False

    provider = AIProvider.GEMINI if gemini_key else AIProvider.OPENAI
    pin_content = asyncio.run(
        generate_pin_content(
            product=product,
            provider=provider,
            gemini_api_key=gemini_key,
            openai_api_key=openai_key,
        )
    )
    db.update_pin_content(product.item_id, pin_content)

    # Auto-publish if enabled
    auto_publish = db.get_setting("auto_publish") == "1"
    if auto_publish:
        _auto_publish_pin(product.item_id)

    return True


def _auto_publish_pin(item_id: str) -> bool:
    """Attempt to auto-publish a pin to Pinterest. Silently fails."""
    db = get_db()
    client = _get_pinterest_client()
    board_id = _get_pinterest_board_id()
    if not client or not board_id:
        return False

    db_product = db.get_product_by_item_id(item_id)
    if not db_product or not db_product.pin_generated or db_product.pin_published:
        return False

    link = db_product.promo_url or db_product.item_url or ""
    try:
        result = asyncio.run(
            client.create_pin(
                board_id=board_id,
                title=db_product.pin_title,
                description=db_product.pin_description,
                link=link,
                image_url=db_product.image_url,
                alt_text=db_product.pin_alt_text,
            )
        )
        if result.success:
            db.update_pin_published(item_id, result.pin_id or "", result.pin_url or "")
            return True
    except Exception:
        pass
    return False


# ---------------------------------------------------------------------------
# Routes - Setup (first run)
# ---------------------------------------------------------------------------


@app.before_request
def _check_db_setup():
    """Redirect all requests to /setup if DB is not configured."""
    allowed = ("/setup", "/static")
    if not _is_db_ready() and not request.path.startswith(allowed):
        return redirect(url_for("setup_page"))


@app.route("/setup", methods=["GET"])
def setup_page() -> str:
    if _is_db_ready():
        return redirect(url_for("dashboard"))
    config = get_config()
    return _render(
        "setup",
        page_name="setup",
        db_host=config.db_host,
        db_port=config.db_port or 3306,
        db_name=config.db_name,
        db_user=config.db_user,
        db_password=config.db_password,
    )


@app.route("/setup", methods=["POST"])
def setup_submit() -> str:
    host = request.form.get("db_host", "").strip()
    port = int(request.form.get("db_port", "3306"))
    name = request.form.get("db_name", "").strip()
    user = request.form.get("db_user", "").strip()
    password = request.form.get("db_password", "").strip()

    err = _try_connect_db(host, port, name, user, password)
    if err:
        return _render(
            "setup",
            page_name="setup",
            db_host=host,
            db_port=port,
            db_name=name,
            db_user=user,
            db_password=password,
            msg=f"Connection failed: {err}",
            msg_cls="err",
        )

    # Save to local config file so it persists across restarts
    config = get_config()
    config.db_host = host
    config.db_port = port
    config.db_name = name
    config.db_user = user
    config.db_password = password
    config.save_db_only()

    return redirect(url_for("dashboard", msg="Connected!", msg_cls="ok"))


# ---------------------------------------------------------------------------
# Routes - Dashboard & Settings
# ---------------------------------------------------------------------------


@app.route("/")
def dashboard() -> str:
    db = get_db()
    stats = db.get_stats()
    cookie_ok = bool(db.get_setting("raw_headers") or db.get_setting("raw_cookie"))
    return _render(
        "dashboard",
        page_name="dashboard",
        stats=stats,
        cookie_ok=cookie_ok,
    )


@app.route("/settings", methods=["GET"])
def settings_page() -> str:
    db = get_db()
    config = get_config()
    from ae_pinner.aliexpress import parse_raw_request_headers

    raw_headers = db.get_setting("raw_headers")
    parsed = parse_raw_request_headers(raw_headers) if raw_headers else {}
    # Try to load boards if token is set
    pinterest_token = db.get_setting("pinterest_token")
    pinterest_board_id = db.get_setting("pinterest_board_id")
    pinterest_boards = []
    pinterest_board_name = ""
    if pinterest_token:
        try:
            client = PinterestClient(access_token=pinterest_token)
            boards = asyncio.run(client.get_boards())
            pinterest_boards = [{"id": b.get("id", ""), "name": b.get("name", "")} for b in boards]
            # Find the name of the currently selected board
            for b in pinterest_boards:
                if b["id"] == pinterest_board_id:
                    pinterest_board_name = b["name"]
                    break
        except Exception:
            pass

    return _render(
        "settings",
        page_name="settings",
        raw_headers=raw_headers,
        headers_parsed=bool(raw_headers),
        cookie_found=bool(parsed.get("cookie")),
        ua_found=bool(parsed.get("user-agent")),
        referer_found=bool(parsed.get("referer")),
        tracking_id=db.get_setting("tracking_id") or "default",
        ship_to=db.get_setting("ship_to") or "US",
        currency=db.get_setting("currency") or "USD",
        language=db.get_setting("language") or "en",
        pinterest_token=pinterest_token,
        pinterest_client_id=db.get_setting("pinterest_client_id") or "",
        pinterest_client_secret=db.get_setting("pinterest_client_secret") or "",
        pinterest_board_id=pinterest_board_id,
        pinterest_boards=pinterest_boards,
        pinterest_board_name=pinterest_board_name,
        auto_publish=db.get_setting("auto_publish") == "1",
        gemini_key=db.get_setting("gemini_key"),
        openai_key=db.get_setting("openai_key"),
        cfg_db_host=config.db_host,
        cfg_db_port=config.db_port,
        cfg_db_name=config.db_name,
        cfg_db_user=config.db_user,
        cfg_db_password=config.db_password,
    )


@app.route("/settings", methods=["POST"])
def save_settings() -> str:
    db = get_db()
    db.set_setting("raw_headers", request.form.get("raw_headers", "").strip())
    db.set_setting("tracking_id", request.form.get("tracking_id", "default").strip())
    db.set_setting("ship_to", request.form.get("ship_to", "US").strip())
    db.set_setting("currency", request.form.get("currency", "USD").strip())
    db.set_setting("language", request.form.get("language", "en").strip())
    return redirect(url_for("settings_page", msg="Settings saved!", msg_cls="ok"))


@app.route("/settings/ai", methods=["POST"])
def save_ai_settings() -> str:
    db = get_db()
    db.set_setting("gemini_key", request.form.get("gemini_key", "").strip())
    db.set_setting("openai_key", request.form.get("openai_key", "").strip())
    return redirect(url_for("settings_page", msg="AI settings saved!", msg_cls="ok"))


@app.route("/settings/pinterest", methods=["POST"])
def save_pinterest_settings() -> str:
    db = get_db()
    db.set_setting("pinterest_client_id", request.form.get("pinterest_client_id", "").strip())
    db.set_setting("pinterest_client_secret", request.form.get("pinterest_client_secret", "").strip())
    db.set_setting("pinterest_token", request.form.get("pinterest_token", "").strip())
    db.set_setting("pinterest_board_id", request.form.get("pinterest_board_id", "").strip())
    db.set_setting("auto_publish", "1" if request.form.get("auto_publish") else "0")
    return redirect(url_for("settings_page", msg="Pinterest settings saved!", msg_cls="ok"))


@app.route("/pinterest/login")
def pinterest_login() -> str:
    db = get_db()
    client_id = db.get_setting("pinterest_client_id")
    if not client_id:
        return redirect(url_for("settings_page", msg="Please save your App ID (Client ID) first!", msg_cls="err"))
        
    redirect_uri = "http://localhost:5000/pinterest/callback"
    scopes = "boards:read,boards:write,pins:read,pins:write"
    url = f"https://www.pinterest.com/oauth/?client_id={client_id}&redirect_uri={redirect_uri}&response_type=code&scope={scopes}"
    return redirect(url)


@app.route("/pinterest/callback")
def pinterest_callback() -> str:
    code = request.args.get("code")
    if not code:
        err = request.args.get("error", "Unknown error")
        return redirect(url_for("settings_page", msg=f"Pinterest login failed: {err}", msg_cls="err"))
        
    db = get_db()
    client_id = db.get_setting("pinterest_client_id")
    client_secret = db.get_setting("pinterest_client_secret")
    
    if not client_id or not client_secret:
        return redirect(url_for("settings_page", msg="App ID or Secret missing in settings.", msg_cls="err"))
        
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": "http://localhost:5000/pinterest/callback"
    }
    
    try:
        with httpx.Client(timeout=10) as client:
            resp = client.post(
                "https://api.pinterest.com/v5/oauth/token", 
                auth=(client_id, client_secret), 
                data=data
            )
            resp.raise_for_status()
            token_data = resp.json()
            access_token = token_data.get("access_token")
            if access_token:
                db.set_setting("pinterest_token", access_token)
                return redirect(url_for("settings_page", msg="Successfully logged in to Pinterest!", msg_cls="ok"))
            else:
                return redirect(url_for("settings_page", msg="Failed to get access token from response.", msg_cls="err"))
    except Exception as e:
        err_msg = str(e)
        if hasattr(e, "response") and e.response:
            err_msg += f" - {e.response.text}"
            
        debug_info = f" (ID length: {len(client_id)}, Secret length: {len(client_secret)}, Secret starts with: {client_secret[:3]}...)"
        return redirect(url_for("settings_page", msg=f"Error exchanging token: {err_msg}{debug_info}", msg_cls="err"))


@app.route("/settings/db", methods=["POST"])
def save_db_settings() -> str:
    host = request.form.get("db_host", "").strip()
    port = int(request.form.get("db_port", "3306"))
    name = request.form.get("db_name", "").strip()
    user = request.form.get("db_user", "").strip()
    password = request.form.get("db_password", "").strip()

    err = _try_connect_db(host, port, name, user, password)
    if err:
        return redirect(
            url_for(
                "settings_page",
                msg=f"DB connection failed: {err}",
                msg_cls="err",
            )
        )

    config = get_config()
    config.db_host = host
    config.db_port = port
    config.db_name = name
    config.db_user = user
    config.db_password = password
    config.save_db_only()

    return redirect(url_for("settings_page", msg="Database reconnected!", msg_cls="ok"))


# ---------------------------------------------------------------------------
# Routes - Fetch & Save
# ---------------------------------------------------------------------------


@app.route("/fetch", methods=["GET"])
def fetch_page() -> str:
    db = get_db()
    page_num = int(request.args.get("page", 1))
    count = int(request.args.get("count", 12))
    cookie_ok = bool(db.get_setting("raw_headers") or db.get_setting("raw_cookie"))
    return _render(
        "fetch",
        page_name="fetch",
        products=[],
        page_num=page_num,
        count=count,
        cookie_ok=cookie_ok,
        products_json="[]",
    )


@app.route("/fetch", methods=["POST"])
def fetch_products() -> str:
    db = get_db()
    page_num = int(request.form.get("page", 1))
    count = int(request.form.get("count", 12))

    ae = _get_ae_client()
    if not ae:
        return redirect(
            url_for(
                "settings_page",
                msg="Set cookies first!",
                msg_cls="err",
            )
        )

    ship_to, currency, language = _get_fetch_params()

    try:
        products = asyncio.run(
            ae.fetch_products_with_promo_links(
                page_num=page_num,
                page_size=count,
                ship_to=ship_to,
                currency=currency,
                language=language,
            )
        )
    except Exception as e:
        return _render(
            "fetch",
            page_name="fetch",
            products=[],
            page_num=page_num,
            count=count,
            cookie_ok=True,
            products_json="[]",
            msg=f"Error: {e}",
            msg_cls="err",
        )

    display = [_product_to_dict(p, db) for p in products]
    products_json = json.dumps(display, default=str)

    if products:
        msg = f"Found {len(products)} products on page {page_num}"
    else:
        msg = "No products found. Cookies may be expired."
    msg_cls = "ok" if products else "err"

    return _render(
        "fetch",
        page_name="fetch",
        products=display,
        page_num=page_num,
        count=count,
        cookie_ok=True,
        products_json=products_json,
        msg=msg,
        msg_cls=msg_cls,
    )


@app.route("/save-page", methods=["POST"])
def save_page() -> str:
    db = get_db()
    action = request.form.get("action", "save")
    products_json = request.form.get("products_json", "[]")
    items = json.loads(products_json)

    saved = 0
    skipped = 0
    for item_dict in items:
        product = _dict_to_product(item_dict)
        ok = db.save_product(product)
        if ok:
            saved += 1
            if action == "save_gen":
                try:
                    _generate_pin_for_product(product)
                except Exception:
                    pass
        else:
            skipped += 1

    msg = f"Saved {saved} products"
    if skipped:
        msg += f", {skipped} duplicates skipped"
    return redirect(url_for("dashboard", msg=msg, msg_cls="ok"))


@app.route("/save-single", methods=["POST"])
def save_single() -> str:
    db = get_db()
    product_json = request.form.get("product_json", "{}")
    item_dict = json.loads(product_json)
    product = _dict_to_product(item_dict)

    ok = db.save_product(product)
    if ok:
        msg = f"Saved: {product.title[:50]}..."
        msg_cls = "ok"
    else:
        msg = "Already saved (duplicate)"
        msg_cls = "info"

    return redirect(url_for("products_page", msg=msg, msg_cls=msg_cls))


# ---------------------------------------------------------------------------
# Routes - Products & Pinterest
# ---------------------------------------------------------------------------


@app.route("/products")
def products_page() -> str:
    db = get_db()
    page = int(request.args.get("page", 1))
    per_page = 12
    products, total = db.get_all_products(page=page, per_page=per_page)
    total_pages = max(1, math.ceil(total / per_page))
    stats = db.get_stats()
    return _render(
        "products",
        page_name="products",
        products=products,
        total=total,
        current_page=page,
        total_pages=total_pages,
        pending_count=stats["without_pins"],
    )


@app.route("/product/<item_id>")
def product_detail(item_id: str) -> str:
    db = get_db()
    p = db.get_product_by_item_id(item_id)
    if not p:
        return redirect(url_for("products_page", msg="Product not found", msg_cls="err"))

    all_images = [i for i in p.all_images.split(",") if i] if p.all_images else []
    if p.image_url and p.image_url not in all_images:
        all_images.insert(0, p.image_url)

    pin_desc_encoded = ""
    pin_media_encoded = ""
    pin_url_encoded = ""
    if p.pin_generated:
        pin_desc_encoded = urllib.parse.quote(p.pin_description or "", safe="")
        pin_media_encoded = urllib.parse.quote(p.image_url or "", safe="")
        link = p.promo_url or p.item_url or ""
        pin_url_encoded = urllib.parse.quote(link, safe="")

    return _render(
        "product_detail",
        page_name="products",
        p=p,
        all_images=all_images,
        pin_desc_encoded=pin_desc_encoded,
        pin_media_encoded=pin_media_encoded,
        pin_url_encoded=pin_url_encoded,
    )


@app.route("/generate/<item_id>", methods=["POST"])
def generate_single(item_id: str) -> str:
    db = get_db()
    db_product = db.get_product_by_item_id(item_id)
    if not db_product:
        return redirect(url_for("products_page", msg="Product not found", msg_cls="err"))

    product = _dbproduct_to_product(db_product)
    try:
        ok = _generate_pin_for_product(product)
        if ok:
            msg = f"Generated for: {db_product.title[:40]}..."
            msg_cls = "ok"
        else:
            msg = "No AI key configured. Go to Settings."
            msg_cls = "err"
    except Exception as e:
        msg = f"AI error: {e}"
        msg_cls = "err"

    return redirect(url_for("products_page", msg=msg, msg_cls=msg_cls))


@app.route("/save-seo/<item_id>", methods=["POST"])
def save_seo_manual(item_id: str) -> str:
    from ae_pinner.ai_generator import PinContent
    db = get_db()
    pin_title = request.form.get("pin_title", "").strip()
    pin_description = request.form.get("pin_description", "").strip()
    pin_alt_text = request.form.get("pin_alt_text", "").strip()
    
    content = PinContent(title=pin_title, description=pin_description, alt_text=pin_alt_text)
    db.update_pin_content(item_id, content)
    return redirect(url_for("product_detail", item_id=item_id, msg="Manual SEO saved!", msg_cls="ok"))


@app.route("/generate-all", methods=["POST"])
def generate_all() -> str:
    db = get_db()
    pending = db.get_products_without_pins()
    generated = 0
    failed = 0

    for db_product in pending:
        product = _dbproduct_to_product(db_product)
        try:
            ok = _generate_pin_for_product(product)
            if ok:
                generated += 1
            else:
                failed += 1
        except Exception:
            failed += 1

    msg = f"Generated {generated} Pinterest descriptions"
    if failed:
        msg += f", {failed} failed"
    msg_cls = "ok" if generated > 0 else "err"
    return redirect(url_for("dashboard", msg=msg, msg_cls=msg_cls))


@app.route("/publish/<item_id>", methods=["POST"])
def publish_single(item_id: str) -> str:
    """Publish a single product as a pin to Pinterest via API."""
    db = get_db()
    db_product = db.get_product_by_item_id(item_id)
    if not db_product:
        return redirect(url_for("products_page", msg="Product not found", msg_cls="err"))
    if not db_product.pin_generated:
        return redirect(url_for("product_detail", item_id=item_id,
                                msg="Generate Pinterest content first", msg_cls="err"))
    if db_product.pin_published:
        return redirect(url_for("product_detail", item_id=item_id,
                                msg="Already published", msg_cls="ok"))

    client = _get_pinterest_client()
    if not client:
        return redirect(url_for("settings_page",
                                msg="Pinterest token not configured. Set it up first!",
                                msg_cls="err"))
    board_id = _get_pinterest_board_id()
    if not board_id:
        return redirect(url_for("settings_page",
                                msg="Pinterest Board ID not configured. Set it up first!",
                                msg_cls="err"))

    link = db_product.promo_url or db_product.item_url or ""
    try:
        result = asyncio.run(
            client.create_pin(
                board_id=board_id,
                title=db_product.pin_title,
                description=db_product.pin_description,
                link=link,
                image_url=db_product.image_url,
                alt_text=db_product.pin_alt_text,
            )
        )
    except Exception as e:
        return redirect(url_for("product_detail", item_id=item_id,
                                msg=f"Pinterest API error: {e}", msg_cls="err"))

    if result.success:
        db.update_pin_published(item_id, result.pin_id or "", result.pin_url or "")
        return redirect(url_for("product_detail", item_id=item_id,
                                msg="Published to Pinterest!", msg_cls="ok"))
    else:
        return redirect(url_for("product_detail", item_id=item_id,
                                msg=f"Pinterest error: {result.error}", msg_cls="err"))


@app.route("/publish-all", methods=["POST"])
def publish_all() -> str:
    """Publish all ready (generated but not published) products to Pinterest."""
    import time

    client = _get_pinterest_client()
    if not client:
        return redirect(url_for("settings_page",
                                msg="Pinterest token not configured!", msg_cls="err"))
    board_id = _get_pinterest_board_id()
    if not board_id:
        return redirect(url_for("settings_page",
                                msg="Pinterest Board ID not configured!", msg_cls="err"))

    db = get_db()
    ready = db.get_products_ready_to_publish()
    published = 0
    failed = 0

    for db_product in ready:
        link = db_product.promo_url or db_product.item_url or ""
        try:
            result = asyncio.run(
                client.create_pin(
                    board_id=board_id,
                    title=db_product.pin_title,
                    description=db_product.pin_description,
                    link=link,
                    image_url=db_product.image_url,
                    alt_text=db_product.pin_alt_text,
                )
            )
            if result.success:
                db.update_pin_published(
                    db_product.item_id, result.pin_id or "", result.pin_url or ""
                )
                published += 1
            else:
                failed += 1
        except Exception:
            failed += 1
        # Rate limiting: 1 second delay between pins
        time.sleep(1)

    msg = f"Published {published} pins to Pinterest"
    if failed:
        msg += f", {failed} failed"
    msg_cls = "ok" if published > 0 else "err"
    return redirect(url_for("dashboard", msg=msg, msg_cls=msg_cls))


@app.route("/delete/<item_id>", methods=["POST"])
def delete_product(item_id: str) -> str:
    db = get_db()
    ok = db.delete_product(item_id)
    msg = "Product deleted" if ok else "Product not found"
    msg_cls = "ok" if ok else "err"
    return redirect(url_for("products_page", msg=msg, msg_cls=msg_cls))


# ===================================================================
# REST API - JSON endpoints for programmatic access
# ===================================================================


@app.route("/api/stats")
def api_stats():
    """GET /api/stats - Product statistics."""
    db = get_db()
    return jsonify(db.get_stats())


@app.route("/api/products")
def api_products():
    """GET /api/products?page=1&per_page=20 - List saved products."""
    db = get_db()
    page = int(request.args.get("page", 1))
    per_page = int(request.args.get("per_page", 20))
    products, total = db.get_all_products(page=page, per_page=per_page)
    return jsonify(
        {
            "total": total,
            "page": page,
            "per_page": per_page,
            "products": [
                {
                    "item_id": p.item_id,
                    "title": p.title,
                    "image_url": p.image_url,
                    "original_price": p.original_price,
                    "discount_price": p.discount_price,
                    "discount_rate": p.discount_rate,
                    "sales_30day": p.sales_30day,
                    "comment_score": p.comment_score,
                    "commission_rate": p.commission_rate,
                    "item_url": p.item_url,
                    "promo_url": p.promo_url,
                    "pin_title": p.pin_title,
                    "pin_description": p.pin_description,
                    "pin_alt_text": p.pin_alt_text,
                    "pin_generated": p.pin_generated,
                    "created_at": str(p.created_at),
                }
                for p in products
            ],
        }
    )


@app.route("/api/products/<item_id>")
def api_product_detail(item_id: str):
    """GET /api/products/<item_id> - Single product details."""
    db = get_db()
    p = db.get_product_by_item_id(item_id)
    if not p:
        return jsonify({"error": "not found"}), 404
    raw = None
    if p.raw_json:
        try:
            raw = json.loads(p.raw_json)
        except (json.JSONDecodeError, TypeError):
            raw = p.raw_json
    promo = None
    if p.promo_response:
        try:
            promo = json.loads(p.promo_response)
        except (json.JSONDecodeError, TypeError):
            promo = p.promo_response
    return jsonify(
        {
            "item_id": p.item_id,
            "title": p.title,
            "image_url": p.image_url,
            "all_images": p.all_images,
            "original_price": p.original_price,
            "discount_price": p.discount_price,
            "discount_rate": p.discount_rate,
            "sales_30day": p.sales_30day,
            "commission_rate": p.commission_rate,
            "item_url": p.item_url,
            "promo_url": p.promo_url,
            "raw_json": raw,
            "promo_response": promo,
            "pin_title": p.pin_title,
            "pin_description": p.pin_description,
            "pin_alt_text": p.pin_alt_text,
            "pin_generated": p.pin_generated,
        }
    )


@app.route("/api/products/<item_id>", methods=["DELETE"])
def api_delete_product(item_id: str):
    """DELETE /api/products/<item_id> - Delete a product."""
    db = get_db()
    ok = db.delete_product(item_id)
    if not ok:
        return jsonify({"error": "not found"}), 404
    return jsonify({"deleted": item_id})


@app.route("/api/fetch", methods=["POST"])
def api_fetch():
    """POST /api/fetch {page, count, save} - Fetch & optionally save."""
    db = get_db()
    data = request.get_json(force=True) or {}
    page_num = data.get("page", 1)
    count = data.get("count", 12)
    save = data.get("save", False)

    ae = _get_ae_client()
    if not ae:
        return jsonify({"error": "cookies not configured"}), 400

    ship_to, currency, language = _get_fetch_params()
    try:
        products = asyncio.run(
            ae.fetch_products_with_promo_links(
                page_num=page_num,
                page_size=count,
                ship_to=ship_to,
                currency=currency,
                language=language,
            )
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    saved_count = 0
    if save:
        for p in products:
            if db.save_product(p):
                saved_count += 1

    return jsonify(
        {
            "page": page_num,
            "fetched": len(products),
            "saved": saved_count if save else None,
            "products": [_product_to_dict(p, db) for p in products],
        }
    )


@app.route("/api/generate/<item_id>", methods=["POST"])
def api_generate(item_id: str):
    """POST /api/generate/<item_id> - Generate Pinterest content."""
    db = get_db()
    db_product = db.get_product_by_item_id(item_id)
    if not db_product:
        return jsonify({"error": "not found"}), 404

    product = _dbproduct_to_product(db_product)
    try:
        ok = _generate_pin_for_product(product)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    if not ok:
        return jsonify({"error": "no AI key configured"}), 400

    updated = db.get_product_by_item_id(item_id)
    return jsonify(
        {
            "item_id": item_id,
            "pin_title": updated.pin_title if updated else "",
            "pin_description": updated.pin_description if updated else "",
            "pin_alt_text": updated.pin_alt_text if updated else "",
        }
    )


@app.route("/api/publish/<item_id>", methods=["POST"])
def api_publish(item_id: str):
    """POST /api/publish/<item_id> - Publish a product as a pin to Pinterest."""
    db = get_db()
    db_product = db.get_product_by_item_id(item_id)
    if not db_product:
        return jsonify({"error": "not found"}), 404
    if not db_product.pin_generated:
        return jsonify({"error": "Pinterest content not generated yet"}), 400
    if db_product.pin_published:
        return jsonify({
            "item_id": item_id,
            "already_published": True,
            "pin_id": db_product.pin_id,
            "pin_url": db_product.pin_url,
        })

    client = _get_pinterest_client()
    if not client:
        return jsonify({"error": "Pinterest token not configured"}), 400
    board_id = _get_pinterest_board_id()
    if not board_id:
        return jsonify({"error": "Pinterest board ID not configured"}), 400

    link = db_product.promo_url or db_product.item_url or ""
    try:
        result = asyncio.run(
            client.create_pin(
                board_id=board_id,
                title=db_product.pin_title,
                description=db_product.pin_description,
                link=link,
                image_url=db_product.image_url,
                alt_text=db_product.pin_alt_text,
            )
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    if result.success:
        db.update_pin_published(item_id, result.pin_id or "", result.pin_url or "")
        return jsonify({
            "item_id": item_id,
            "pin_id": result.pin_id,
            "pin_url": result.pin_url,
            "published": True,
        })
    else:
        return jsonify({"error": result.error}), 500


@app.route("/api/pinterest/boards", methods=["POST"])
def api_pinterest_boards():
    """POST /api/pinterest/boards - Fetch boards for a Pinterest token."""
    data = request.get_json(force=True) or {}
    token = data.get("token", "").strip()
    if not token:
        # Fall back to saved token
        db = get_db()
        token = db.get_setting("pinterest_token")
    if not token:
        return jsonify({"error": "No token provided"}), 400

    try:
        client = PinterestClient(access_token=token)
        boards = asyncio.run(client.get_boards())
        return jsonify({
            "boards": [
                {
                    "id": b.get("id", ""),
                    "name": b.get("name", ""),
                    "description": b.get("description", ""),
                }
                for b in boards
            ]
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/settings", methods=["GET"])
def api_get_settings():
    """GET /api/settings - Current settings (cookies masked)."""
    db = get_db()
    raw_headers = db.get_setting("raw_headers")
    raw_cookie = db.get_setting("raw_cookie")
    return jsonify(
        {
            "headers_set": bool(raw_headers),
            "cookies_set": bool(raw_headers or raw_cookie),
            "tracking_id": db.get_setting("tracking_id") or "default",
            "ship_to": db.get_setting("ship_to") or "US",
            "currency": db.get_setting("currency") or "USD",
            "language": db.get_setting("language") or "en",
            "gemini_key_set": bool(db.get_setting("gemini_key")),
            "openai_key_set": bool(db.get_setting("openai_key")),
            "pinterest_token_set": bool(db.get_setting("pinterest_token")),
            "pinterest_board_id": db.get_setting("pinterest_board_id") or "",
            "auto_publish": db.get_setting("auto_publish") == "1",
        }
    )


@app.route("/api/settings", methods=["POST"])
def api_save_settings():
    """POST /api/settings {raw_cookie, tracking_id, ...} - Update."""
    db = get_db()
    data = request.get_json(force=True) or {}
    allowed = (
        "raw_headers",
        "raw_cookie",
        "tracking_id",
        "ship_to",
        "currency",
        "language",
        "gemini_key",
        "openai_key",
        "pinterest_token",
        "pinterest_board_id",
        "auto_publish",
    )
    updated = []
    for key in allowed:
        if key in data:
            db.set_setting(key, str(data[key]).strip())
            updated.append(key)
    return jsonify({"updated": updated})
