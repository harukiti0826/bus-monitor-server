# server.py — SVGオーバーレイ + 8chミニグラフ + 編集モード(位置&サイズ) + 一括ダンプ
from flask import Flask, jsonify, request, send_from_directory
import time, os

app = Flask(__name__, static_folder="static")

# ===== 設定 =====
NUM_SEATS    = 8              # 席数
MAX_HISTORY  = 360            # 履歴保存数（5秒周期で約30分）

# 最新状態と履歴
latest_data = {
    "timestamp": time.time(),        # epoch秒 or 文字列でもOK（受信側でそのまま返す）
    "seats": [0]*NUM_SEATS,          # 0=空, 1=着座
    "count": 0
}
history_log = []                    # [{timestamp, seats[8], count}, ...]

# 静的ファイル（バス図など）
@app.route("/static/<path:filename>")
def static_files(filename):
    return send_from_directory(app.static_folder, filename)

# ===== メインダッシュボード =====
@app.route("/")
def index():
    return f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width,initial-scale=1" />
<title>Bus Monitor</title>

<style>
  body {{
    font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
    color: #222; background:#f5f5f5; margin:0; padding:12px 10px 60px;
  }}
  h1 {{
    font-size: 1.4rem; display:flex; gap:.5rem; align-items:center; margin:12px 0 6px;
  }}
  .sub {{
    color:#666; font-size:.9rem; margin-bottom:12px;
  }}

  /* ===== バス図（SVG） ===== */
  .bus-wrap {{
    width: 100%;
    max-width: 980px;
    margin: 0 auto 14px auto;
    background: #f5f5f5;
    border-radius: 12px;
    box-shadow: 0 10px 24px rgba(0,0,0,.08);
  }}
  .seat-rect.free {{ fill: #bdbdbd; stroke: #202020; stroke-width: 2; }}
  .seat-rect.occ  {{ fill: #8bdc6a; stroke: #202020; stroke-width: 2; }}
  .seat-label {{
    font: 700 16px system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
    fill:#111;
  }}

  /* === 編集ハンドル === */
  .handle {{ fill:#fff; stroke:#111; stroke-width:2; }}
  .handle.tl, .handle.br {{ cursor: nwse-resize; }}
  .handle.tr, .handle.bl {{ cursor: nesw-resize; }}

  /* ===== カード ===== */
  .cards {{
    display:flex; gap:12px; flex-wrap:wrap; margin:12px auto 18px; max-width:980px;
  }}
  .card {{
    background:#fff; padding:12px 14px; border-radius:12px;
    box-shadow:0 10px 24px rgba(0,0,0,.07); min-width:220px;
  }}
  .big   {{ font-size:2rem; font-weight:800; }}
  .muted {{ color:#666; font-size:.9rem; }}

  /* ===== ミニグラフ（8本縦積み） ===== */
  .charts {{
    max-width:980px; margin:0 auto;
    background:#fff; border-radius:16px; box-shadow:0 10px 24px rgba(0,0,0,.07);
    padding:12px;
  }}
  .chart-row {{
    display:flex; align-items:center; gap:10px; margin:6px 0;
  }}
  .chart-title {{ width:70px; text-align:right; font-size:.9rem; color:#444; }}
  .chart-box   {{ flex:1; }}
  canvas       {{ width:100%; height:70px; }}

  footer {{ text-align:center; color:#888; font-size:.8rem; margin-top:14px; }}
</style>
</head>
<body>
  <h1>🚌 Bus Monitor</h1>
  <div class="sub">last update: <span id="ts">---</span> / 5秒ごとに自動更新</div>

  <!-- ===== バス図（SVGに画像を貼り、同一座標で座席を描く） ===== -->
  <div class="bus-wrap">
    <svg id="bus-svg" width="100%" height="auto" preserveAspectRatio="xMidYMid meet"></svg>
  </div>

  <!-- 編集用ツールバー（本番時は消してOK） -->
  <div style="max-width:980px;margin:8px auto 0;display:flex;gap:8px;justify-content:flex-end;">
    <button id="dumpBtn" style="padding:.5rem .8rem;border-radius:8px;border:1px solid #ccc;background:#fff;cursor:pointer;">
      現在座標をコンソールに出力
    </button>
    <span id="editHint" style="color:#666;font-size:.9rem;"></span>
  </div>

  <!-- ===== 数字カード ===== -->
  <div class="cards">
    <div class="card">
      <div class="muted">現在乗車中</div>
      <div class="big"><span id="count">0</span> 人</div>
    </div>
    <div class="card">
      <div class="muted">席配列</div>
      <div style="font-family:monospace" id="seats">[{", ".join("0" for _ in range(NUM_SEATS))}]</div>
    </div>
  </div>

  <!-- ===== ミニグラフ（8本） ===== -->
  <div class="charts" id="charts"></div>

  <footer>Render配信中 / Chart.js + SVG overlay</footer>

  <!-- Chart.js CDN -->
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>

  <script>
    // ====== 席数（JS側もPythonと合わせる） ======
    const NUM_SEATS = {NUM_SEATS};

    // ====== 座席正規化座標（0..1）。x,y,w,h を画像基準で記述 ======
    // 位置合わせ後はここにペーストで確定！
    const SEATS_NORM = [
      // 左列 上→下
      {{x:0.095, y:0.12, w:0.095, h:0.16}}, // S1
      {{x:0.095, y:0.39, w:0.095, h:0.16}}, // S2
      {{x:0.095, y:0.66, w:0.095, h:0.16}}, // S3
      // 中央列
      {{x:0.44,  y:0.17, w:0.095, h:0.16}}, // S4
      {{x:0.58,  y:0.17, w:0.095, h:0.16}}, // S5
      // 右列 上→下
      {{x:0.83,  y:0.12, w:0.095, h:0.16}}, // S6
      {{x:0.83,  y:0.39, w:0.095, h:0.16}}, // S7
      {{x:0.83,  y:0.66, w:0.095, h:0.16}}  // S8
    ];

    // ==== 編集モード（位置&サイズをドラッグで編集） ====
    const EDIT_MODE = true;  // ← 調整が終わったら false にしてデプロイ！

    // 画像の自然サイズ（自動取得）
    let IMG_W = 0, IMG_H = 0;

    function loadImage(src) {{
      return new Promise((resolve, reject) => {{
        const im = new Image();
        im.onload = () => resolve(im);
        im.onerror = reject;
        im.src = src + '?v=' + Date.now(); // cache bust
      }});
    }}

    function normToAbs(norm) {{
      return {{ x: norm.x * IMG_W, y: norm.y * IMG_H, w: norm.w * IMG_W, h: norm.h * IMG_H }};
    }}
    function absToNorm(abs) {{
      return {{ x: abs.x / IMG_W, y: abs.y / IMG_H, w: abs.w / IMG_W, h: abs.h / IMG_H }};
    }}

    async function initBusSvg() {{
      const svg = document.getElementById('bus-svg');

      // 画像ロードしてnaturalサイズを取得
      const img = await loadImage('/static/bus.png');
      IMG_W = img.naturalWidth;
      IMG_H = img.naturalHeight;

      // f-string内のJSテンプレは ${{...}} にする（Pythonに食われないように）
      svg.setAttribute('viewBox', `0 0 ${{IMG_W}} ${{IMG_H}}`);

      // 背景画像
      const imageEl = document.createElementNS('http://www.w3.org/2000/svg', 'image');
      imageEl.setAttributeNS('http://www.w3.org/1999/xlink', 'href', '/static/bus.png');
      imageEl.setAttribute('x', '0');
      imageEl.setAttribute('y', '0');
      imageEl.setAttribute('width', IMG_W);
      imageEl.setAttribute('height', IMG_H);
      svg.appendChild(imageEl);

      // 座席レイヤ
      const seatLayer = document.createElementNS('http://www.w3.org/2000/svg', 'g');
      seatLayer.setAttribute('id', 'seat-layer');
      svg.appendChild(seatLayer);

      for (let i=0; i<NUM_SEATS; i++) {{
        const g = document.createElementNS('http://www.w3.org/2000/svg', 'g');
        g.setAttribute('data-index', String(i));

        const {{x,y,w,h}} = normToAbs(SEATS_NORM[i]);
        const r = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
        r.setAttribute('x', x);
        r.setAttribute('y', y);
        r.setAttribute('rx', 10);
        r.setAttribute('ry', 10);
        r.setAttribute('width', w);
        r.setAttribute('height', h);
        r.setAttribute('class', 'seat-rect free');
        r.setAttribute('id', `seat-rect-${{i}}`);

        const t = document.createElementNS('http://www.w3.org/2000/svg', 'text');
        t.setAttribute('x', x + w/2);
        t.setAttribute('y', y + h/2 + 6);
        t.setAttribute('text-anchor', 'middle');
        t.setAttribute('class', 'seat-label');
        t.setAttribute('id', `seat-label-${{i}}`);
        t.textContent = '空';

        g.appendChild(r);
        g.appendChild(t);
        seatLayer.appendChild(g);

        if (EDIT_MODE) {{
          attachSeatEditors(svg, g, r, t, i);  // 位置＆サイズ編集を有効化
        }}
      }}

      // 編集ヒント表示
      const hint = document.getElementById('editHint');
      if (EDIT_MODE && hint) {{
        hint.textContent = '編集モード: 四角ドラッグ=移動 / 四隅丸ドラッグ=サイズ / 右のボタンで全席座標を出力';
      }} else if (hint) {{
        hint.textContent = '';
      }}
    }}

    // === 角ハンドルつきエディタ ===
    function attachSeatEditors(svg, group, rect, text, idx) {{
      let dragging = false, resizing = false;
      let which = null; // 'tl' | 'tr' | 'bl' | 'br'
      let start = {{x:0, y:0}};
      let orig  = {{x:0, y:0, w:0, h:0}};

      // 四隅ハンドルを作成
      const handles = makeHandles(rect);
      for (const c of Object.values(handles)) group.appendChild(c);

      // move: 四角をつかんで移動 or ハンドルでリサイズ
      group.addEventListener('mousedown', (e) => {{
        if (!EDIT_MODE) return;

        const target = e.target;
        if (target.classList.contains('handle')) {{
          resizing = true;
          which = target.dataset.which; // tl/tr/bl/br
        }} else {{
          dragging = true;
        }}

        start = svgPoint(svg, e);
        orig.x = parseFloat(rect.getAttribute('x'));
        orig.y = parseFloat(rect.getAttribute('y'));
        orig.w = parseFloat(rect.getAttribute('width'));
        orig.h = parseFloat(rect.getAttribute('height'));
        e.preventDefault();
      }});

      window.addEventListener('mousemove', (e) => {{
        if (!EDIT_MODE) return;
        if (!dragging && !resizing) return;

        const p = svgPoint(svg, e);
        const dx = p.x - start.x;
        const dy = p.y - start.y;

        let nx = orig.x, ny = orig.y, nw = orig.w, nh = orig.h;

        if (dragging) {{
          nx = orig.x + dx;
          ny = orig.y + dy;
        }} else if (resizing) {{
          switch (which) {{
            case 'tl': nx = orig.x + dx; ny = orig.y + dy; nw = orig.w - dx; nh = orig.h - dy; break;
            case 'tr': ny = orig.y + dy; nw = orig.w + dx; nh = orig.h - dy; break;
            case 'bl': nx = orig.x + dx; nw = orig.w - dx; nh = orig.h + dy; break;
            case 'br': nw = orig.w + dx; nh = orig.h + dy; break;
          }}
        }}

        // 最小サイズ＆画像範囲にクリップ
        const MIN = 8; // px
        nx = Math.max(0, nx);
        ny = Math.max(0, ny);
        nw = Math.max(MIN, Math.min(nw, IMG_W - nx));
        nh = Math.max(MIN, Math.min(nh, IMG_H - ny));

        rect.setAttribute('x', nx);
        rect.setAttribute('y', ny);
        rect.setAttribute('width',  nw);
        rect.setAttribute('height', nh);

        text.setAttribute('x', nx + nw/2);
        text.setAttribute('y', ny + nh/2 + 6);

        updateHandlesPosition(rect, handles);
      }});

      window.addEventListener('mouseup', () => {{
        if (!EDIT_MODE) return;
        if (!dragging && !resizing) return;
        dragging = false; resizing = false; which = null;

        // 正規化座標でログ
        const x = parseFloat(rect.getAttribute('x'));
        const y = parseFloat(rect.getAttribute('y'));
        const w = parseFloat(rect.getAttribute('width'));
        const h = parseFloat(rect.getAttribute('height'));
        const norm = {{
          x: +(x/IMG_W).toFixed(4),
          y: +(y/IMG_H).toFixed(4),
          w: +(w/IMG_W).toFixed(4),
          h: +(h/IMG_H).toFixed(4)
        }};
        console.log(`S${{idx+1}}:`, JSON.stringify(norm));
      }});
    }}

    // 四隅ハンドルの生成
    function makeHandles(rect) {{
      const defs = [
        {{ which:'tl', cls:'handle tl' }},
        {{ which:'tr', cls:'handle tr' }},
        {{ which:'bl', cls:'handle bl' }},
        {{ which:'br', cls:'handle br' }},
      ];
      const hs = {{}};
      for (const d of defs) {{
        const c = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
        c.setAttribute('r', 8);               // ハンドルの大きさ
        c.setAttribute('class', d.cls);
        c.dataset.which = d.which;
        hs[d.which] = c;
      }}
      updateHandlesPosition(rect, hs);
      return hs;
    }}

    // ハンドル位置の更新（rectの四隅）
    function updateHandlesPosition(rect, hs) {{
      const x = parseFloat(rect.getAttribute('x'));
      const y = parseFloat(rect.getAttribute('y'));
      const w = parseFloat(rect.getAttribute('width'));
      const h = parseFloat(rect.getAttribute('height'));

      hs.tl?.setAttribute('cx', x);
      hs.tl?.setAttribute('cy', y);

      hs.tr?.setAttribute('cx', x + w);
      hs.tr?.setAttribute('cy', y);

      hs.bl?.setAttribute('cx', x);
      hs.bl?.setAttribute('cy', y + h);

      hs.br?.setAttribute('cx', x + w);
      hs.br?.setAttribute('cy', y + h);
    }}

    // 画面座標→SVG座標
    function svgPoint(svg, evt) {{
      const pt = svg.createSVGPoint();
      pt.x = evt.clientX; pt.y = evt.clientY;
      return pt.matrixTransform(svg.getScreenCTM().inverse());
    }}

    // ====== ミニグラフを8本生成 ======
    let charts = [];
    function buildCharts() {{
      const wrap = document.getElementById("charts");
      wrap.innerHTML = "";
      charts = [];
      for (let i=0; i<NUM_SEATS; i++) {{
        const row = document.createElement("div");
        row.className = "chart-row";

        const title = document.createElement("div");
        title.className = "chart-title";
        title.textContent = "Seat " + (i+1);

        const box = document.createElement("div");
        box.className = "chart-box";
        const c = document.createElement("canvas");
        c.id = "cv_"+i;
        box.appendChild(c);

        row.appendChild(title);
        row.appendChild(box);
        wrap.appendChild(row);

        const ctx = c.getContext("2d");
        const chart = new Chart(ctx, {{
          type: "line",
          data: {{
            labels: [],
            datasets: [{{
              label: "S"+(i+1),
              data: [],
              borderWidth: 2,
              fill: false,
              tension: 0.2
            }}]
          }},
          options: {{
            responsive: true,
            animation: false,
            plugins: {{ legend: {{ display:false }} }},
            scales: {{
              y: {{ beginAtZero:true, suggestedMax:1, ticks: {{ stepSize:1 }} }},
              x: {{ ticks: {{ maxRotation:0, autoSkip:true, maxTicksLimit:6 }} }}
            }}
          }}
        }});
        charts.push(chart);
      }}
    }}

    // ====== /status を取得して数値とSVG座席を更新 ======
    async function updateStatus() {{
      const res = await fetch("/status");
      const data = await res.json();

      const tsRaw = data.timestamp;
      let tsReadable = tsRaw;
      if (typeof tsRaw === "number") {{
        tsReadable = new Date(tsRaw * 1000).toLocaleString();
      }}
      const tsEl = document.getElementById("ts");
      if (tsEl) tsEl.textContent = tsReadable ?? '---';

      const countEl = document.getElementById("count");
      if (countEl) countEl.textContent = data.count ?? 0;

      const seatsEl = document.getElementById("seats");
      if (seatsEl) seatsEl.textContent = JSON.stringify((data.seats||[]).slice(0, NUM_SEATS));

      const seats = (data.seats || []).slice(0, NUM_SEATS);
      for (let i=0; i<NUM_SEATS; i++) {{
        const occ = seats[i] === 1;
        const r = document.getElementById(`seat-rect-${{i}}`);
        const t = document.getElementById(`seat-label-${{i}}`);
        if (!r || !t) continue;
        r.setAttribute('class', `seat-rect ${{occ ? 'occ' : 'free'}}`);
        t.textContent = occ ? '着座中' : '空';
      }}
    }}

    // ====== /history を取得して8本のグラフを更新 ======
    async function updateCharts() {{
      const r = await fetch("/history");
      const hist = await r.json();
      const samples = hist.samples || [];  // 古→新想定

      const labels = samples.map(s => {{
        if (typeof s.timestamp === "number") {{
          return new Date(s.timestamp*1000).toLocaleTimeString();
        }} else {{
          return String(s.timestamp).slice(11,19);
        }}
      }});

      const series = Array.from({{length:NUM_SEATS}}, () => []);
      for (const s of samples) {{
        for (let i=0; i<NUM_SEATS; i++) {{
          const v = (s.seats && s.seats[i] === 1) ? 1 : 0;
          series[i].push(v);
        }}
      }}

      for (let i=0; i<NUM_SEATS; i++) {{
        const ch = charts[i];
        if (!ch) continue;
        ch.data.labels = labels;
        ch.data.datasets[0].data = series[i];
        ch.update();
      }}
    }}

    // 一括ダンプ：現在の座標(正規化)を全席分コンソールに出力
    function dumpAllSeatNorms() {{
      const out = [];
      for (let i=0; i<NUM_SEATS; i++) {{
        const r = document.getElementById(`seat-rect-${{i}}`);
        if (!r) continue;
        const x = parseFloat(r.getAttribute('x'));
        const y = parseFloat(r.getAttribute('y'));
        const w = parseFloat(r.getAttribute('width'));
        const h = parseFloat(r.getAttribute('height'));
        out.push({{
          x: +(x/IMG_W).toFixed(4),
          y: +(y/IMG_H).toFixed(4),
          w: +(w/IMG_W).toFixed(4),
          h: +(h/IMG_H).toFixed(4),
        }});
      }}
      console.log("=== SEATS_NORM paste this ===");
      console.log(JSON.stringify(out, null, 2));
    }}
    document.getElementById('dumpBtn')?.addEventListener('click', dumpAllSeatNorms);

    async function refreshAll() {{
      try {{
        await updateStatus();
        await updateCharts();
      }} catch(e) {{
        console.error(e);
      }}
    }}

    // 初期化 → 周期更新
    (async () => {{
      await initBusSvg();
      buildCharts();
      await refreshAll();
      setInterval(refreshAll, 5000);
    }})();
  </script>
</body>
</html>
    """

# ===== API: 最新状態 =====
@app.route("/status")
def status():
    return jsonify(latest_data)

# ===== API: 履歴（古→新で最大MAX_HISTORY件） =====
@app.route("/history")
def history():
    return jsonify({"samples": history_log[-MAX_HISTORY:]})

# ===== API: 管理PC → サーバー（座席データ受信） =====
@app.route("/push", methods=["POST"])
def push():
    global latest_data, history_log

    data = request.get_json()
    if not data:
        return jsonify({"error":"no data"}), 400

    # seats 長さをNUM_SEATSに合わせる
    seats = (data.get("seats") or [])
    if len(seats) < NUM_SEATS:
        seats = seats + [0]*(NUM_SEATS - len(seats))
    seats = seats[:NUM_SEATS]

    # count が無ければ seats から計算
    count = int(data.get("count", sum(1 for v in seats if v == 1)))
    ts    = data.get("timestamp", time.time())

    latest_data = {"timestamp": ts, "seats": seats, "count": count}

    history_log.append({"timestamp": ts, "seats": seats, "count": count})
    if len(history_log) > MAX_HISTORY:
        history_log = history_log[-MAX_HISTORY:]

    return jsonify({"ok": True})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)


