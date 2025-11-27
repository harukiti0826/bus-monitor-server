# server.py — Bus Monitor + 座席編集モード + ヘッダー背景画像
from flask import Flask, jsonify, request, send_from_directory
import time, os, json

app = Flask(__name__, static_folder="static")

# ===== 基本設定 =====
NUM_SEATS       = 8
MAX_HISTORY     = 360            # 5秒ごと約30分
EDIT_MODE_FLAG  = False          # 座席位置調整が終わったら False

# ===== 座席座標（正規化 0〜1）— 編集後 =====
SEATS_NORM_DATA = [
    {"x": 0.23836330219294652, "y": 0.6645828609044532, "w": 0.0858, "h": 0.1678},
    {"x": 0.23757626260431156, "y": 0.4128449835721427, "w": 0.0868, "h": 0.1716},
    {"x": 0.23780967326582064, "y": 0.16558325792424336, "w": 0.0868, "h": 0.1697},
    {"x": 0.4657748481506432,  "y": 0.16465501642785724, "w": 0.0879, "h": 0.1716},
    {"x": 0.6311739655771905,  "y": 0.16564499184697415, "w": 0.0889, "h": 0.1697},
    {"x": 0.8607392705797984,  "y": 0.16505500815302585, "w": 0.0879, "h": 0.1716},
    {"x": 0.8610390385952712,  "y": 0.4137549998781945,  "w": 0.0868, "h": 0.1716},
    {"x": 0.8605059278294506,  "y": 0.6614450001218056,  "w": 0.0879, "h": 0.1736}
]

# ===== ランタイム状態 =====
latest_data = {"timestamp": time.time(), "seats": [0]*NUM_SEATS, "count": 0}
history_log = []  # [{timestamp, seats[], count}, ...]

# ===== 静的配信（bus.png や header.png は static/ に置く） =====
@app.route("/static/<path:filename>")
def static_files(filename):
    return send_from_directory(app.static_folder, filename)

# ===== UI =====
@app.route("/")
def index():
    seats_norm_json = json.dumps(SEATS_NORM_DATA)
    edit_mode_js    = str(EDIT_MODE_FLAG).lower()
    return f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width,initial-scale=1" />
<title>Bus Monitor</title>
<style>
  :root {{ --card-pad: 10px; }}
  body {{
    font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
    color:#222; background:#f5f5f5; margin:0; padding:12px 10px 60px;
  }}
  h1 {{ font-size:1.4rem; display:flex; gap:.5rem; align-items:center; margin:12px 0 6px; }}
  .sub {{ color:#666; font-size:.9rem; margin-bottom:12px; }}

  /* ★ 画像付きヘッダー（🚌 Bus Monitor の背景） */
  .hero {{
    max-width: 980px;
    margin: 0 auto 12px;
    padding: 28px 16px 36px;  /* ← 縦方向の余白をほぼ2倍にして高さアップ */
    border-radius: 16px;
    background-image: url('/static/header.png');
    background-size: cover;
    background-position: center;
    background-repeat: no-repeat;
    color: #fff;
    box-shadow: 0 10px 24px rgba(0,0,0,.15);
  }}
  .hero h1 {{
    margin: 0 0 4px;
    font-size: 1.6rem;
    display: flex;
    gap: .5rem;
    align-items: center;
  }}
  .hero .sub {{
    margin: 0;
    font-size: .9rem;
    color: #f5f5f5;
  }}

  .bus-wrap {{
    width:100%; max-width:980px; margin:0 auto 14px;
    background:#f5f5f5; border-radius:12px; box-shadow:0 10px 24px rgba(0,0,0,.08);
  }}

  .seat-rect.free {{ fill:#bdbdbd; stroke:#202020; stroke-width:2; }}
  .seat-rect.occ  {{ fill:#8bdc6a; stroke:#202020; stroke-width:2; }}

  /* 中央の状態ラベル（空/着座中）80pt */
  .seat-label {{
    font: 700 80px system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
    fill:#111;
    paint-order: stroke; stroke: #fff; stroke-width: 4px;
  }}
  /* 左上の席番号 — 60pt */
  .seat-num {{
    font: 700 60px system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
    fill:#111;
    paint-order: stroke; stroke: #fff; stroke-width: 3px;
  }}
