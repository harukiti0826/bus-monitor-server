# server.py — 1↔3 表示入替 & 席番号60pt版 + 編集モード対応
from flask import Flask, jsonify, request, send_from_directory
import time, os, json

app = Flask(__name__, static_folder="static")

# ===== 基本設定 =====
NUM_SEATS       = 8
MAX_HISTORY     = 120            # 5秒ごと約10分
EDIT_MODE_FLAG  = False          # 位置調整が終わったら False

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

# ===== 静的配信（bus.png は static/ に置く） =====
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

  .cards {{
    display:flex; gap:10px; flex-wrap:wrap; margin:8px auto 12px; max-width:980px;
  }}
  .card {{
    background:#fff; padding:var(--card-pad); border-radius:12px;
    box-shadow:0 10px 24px rgba(0,0,0,.07); min-width:220px;
  }}
  .big {{ font-size:2rem; font-weight:800; }}
  .muted {{ color:#666; font-size:.9rem; }}

  /* 合計人数グラフ（固定サイズ＋余白） */
  .total-chart-wrap {{
    max-width: 980px; margin: 0 auto 16px; background: #fff;
    border-radius: 16px; box-shadow: 0 10px 24px rgba(0,0,0,.07);
    padding: 12px; height: 150px; position: relative;
  }}
  #totalChart {{ position:absolute; left:0; top:0; width:100%; height:100%; display:block; }}

  /* ミニグラフ（余白あり） */
  .charts {{
    max-width:980px; margin:0 auto; background:#fff; border-radius:16px;
    box-shadow:0 10px 24px rgba(0,0,0,.07); padding:16px;
  }}
  .chart-row {{ display:flex; align-items:center; gap:14px; margin:8px 0; }}
  .chart-title {{ width:78px; text-align:right; font-size:.95rem; color:#444; }}
  .chart-box {{ flex:1; min-width:0; }}
  .chart-box canvas {{ width:100%; height:54px; }}

  footer {{ text-align:center; color:#888; font-size:.8rem; margin-top:12px; }}
</style>
</head>
<body>
  <h1>🚌 Bus Monitor</h1>
  <div class="sub">last update: <span id="ts">---</span> / 5秒ごとに自動更新</div>

  <div class="bus-wrap">
    <svg id="bus-svg" width="100%" height="auto" preserveAspectRatio="xMidYMid meet"></svg>
  </div>

  <div class="total-chart-wrap">
    <div class="muted" style="margin-bottom:6px;">合計人数の推移</div>
    <canvas id="totalChart"></canvas>
  </div>

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

  <div class="charts" id="charts"></div>

  <footer>Render配信中 / Chart.js + SVG overlay</footer>

  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <script>
    // ===== Pythonから注入 =====
    const NUM_SEATS   = {NUM_SEATS};
    const SEATS_NORM  = {seats_norm_json};
    const EDIT_MODE   = {edit_mode_js};
    const LABEL_OFFSET = 0.08;               // 中央ラベルを下げる割合（座席高さの8%）

    // ★ 1と3を入れ替え（見た目ラベルを ③,②,① に）
    const SEAT_NUM_LABELS = ['①','②','③','④','⑤','⑥','⑦','⑧'];

    let IMG_W = 0, IMG_H = 0;
    let seatRects = [], seatNums = [], seatLabels = [];

    function loadImage(src) {{
      return new Promise((resolve, reject) => {{
        const im = new Image();
        im.onload = () => resolve(im);
        im.onerror = reject;
        im.src = src + '?v=' + Date.now();
      }});
    }}
    function normToAbs(n) {{ return {{ x:n.x*IMG_W, y:n.y*IMG_H, w:n.w*IMG_W, h:n.h*IMG_H }}; }}

    function applySeatLayout(idx) {{
      const n = SEATS_NORM[idx];
      const a = normToAbs(n);
      const r = seatRects[idx];
      const num = seatNums[idx];
      const t = seatLabels[idx];
      if (!r || !num || !t) return;

      r.setAttribute('x', a.x);
      r.setAttribute('y', a.y);
      r.setAttribute('width', a.w);
      r.setAttribute('height', a.h);

      num.setAttribute('x', a.x + Math.max(8, a.w * 0.03));
      num.setAttribute('y', a.y + a.h * 0.12);

      t.setAttribute('x', a.x + a.w / 2);
      t.setAttribute('y', a.y + a.h * (0.5 + LABEL_OFFSET));
    }}

    async function initBusSvg() {{
      const svg = document.getElementById('bus-svg');
      const img = await loadImage('/static/bus.png');
      IMG_W = img.naturalWidth; IMG_H = img.naturalHeight;
      svg.setAttribute('viewBox', `0 0 ${{IMG_W}} ${{IMG_H}}`);

      const imageEl = document.createElementNS('http://www.w3.org/2000/svg', 'image');
      imageEl.setAttributeNS('http://www.w3.org/1999/xlink', 'href', '/static/bus.png');
      imageEl.setAttribute('x','0'); imageEl.setAttribute('y','0');
      imageEl.setAttribute('width', IMG_W); imageEl.setAttribute('height', IMG_H);
      svg.appendChild(imageEl);

      const seatLayer = document.createElementNS('http://www.w3.org/2000/svg', 'g');
      seatLayer.setAttribute('id','seat-layer'); svg.appendChild(seatLayer);

      seatRects = new Array(NUM_SEATS);
      seatNums = new Array(NUM_SEATS);
      seatLabels = new Array(NUM_SEATS);

      for (let i=0;i<NUM_SEATS;i++) {{
        const g = document.createElementNS('http://www.w3.org/2000/svg', 'g');
        g.setAttribute('data-index', String(i));

        const r = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
        r.setAttribute('rx',10); r.setAttribute('ry',10);
        r.setAttribute('class','seat-rect free');
        r.setAttribute('id',`seat-rect-${{i}}`);

        const num = document.createElementNS('http://www.w3.org/2000/svg', 'text');
        num.setAttribute('dominant-baseline', 'hanging');
        num.setAttribute('class','seat-num');
        num.textContent = SEAT_NUM_LABELS[i];

        const t = document.createElementNS('http://www.w3.org/2000/svg', 'text');
        t.setAttribute('text-anchor','middle');
        t.setAttribute('dominant-baseline','middle');
        t.setAttribute('class','seat-label');
        t.setAttribute('id',`seat-label-${{i}}`);
        t.textContent = '空';

        seatRects[i] = r;
        seatNums[i] = num;
        seatLabels[i] = t;

        applySeatLayout(i);

        g.appendChild(r); g.appendChild(num); g.appendChild(t); seatLayer.appendChild(g);
      }}

      if (EDIT_MODE) {{
        enableEditMode();
      }}
    }}

    function enableEditMode() {{
      const svg = document.getElementById('bus-svg');
      if (!svg) return;
      svg.style.touchAction = 'none';

      let dragInfo = null;

      seatRects.forEach((rect, idx) => {{
        if (!rect) return;
        rect.style.cursor = 'move';

        rect.addEventListener('pointerdown', e => {{
          dragInfo = {{
            idx,
            pointerId: e.pointerId,
            startX: e.clientX,
            startY: e.clientY,
            startNorm: {{ ...SEATS_NORM[idx] }}
          }};
          rect.setPointerCapture(e.pointerId);
        }});

        rect.addEventListener('pointermove', e => {{
          if (!dragInfo || dragInfo.idx !== idx) return;
          const dx = e.clientX - dragInfo.startX;
          const dy = e.clientY - dragInfo.startY;
          const dxNorm = dx / IMG_W;
          const dyNorm = dy / IMG_H;
          const n = SEATS_NORM[idx];
          n.x = dragInfo.startNorm.x + dxNorm;
          n.y = dragInfo.startNorm.y + dyNorm;
          applySeatLayout(idx);
        }});

        rect.addEventListener('pointerup', e => {{
          if (!dragInfo || dragInfo.idx !== idx) return;
          try {{
            rect.releasePointerCapture(dragInfo.pointerId);
          }} catch (err) {{}}
          dragInfo = null;
          console.log('UPDATED SEATS_NORM:', JSON.stringify(SEATS_NORM, null, 2));
        }});

        rect.addEventListener('pointercancel', e => {{
          if (!dragInfo || dragInfo.idx !== idx) return;
          try {{
            rect.releasePointerCapture(dragInfo.pointerId);
          }} catch (err) {{}}
          dragInfo = null;
        }});
      }});

      alert('編集モード: 座席をドラッグして位置調整できます。\\n調整後、ブラウザのコンソールに出た SEATS_NORM を server.py にコピーしてください。');
    }}

    // ===== グラフ =====
    let charts=[], totalChart=null;

    function buildTotalChart() {{
      const ctx = document.getElementById('totalChart').getContext('2d');
      if (totalChart) totalChart.destroy();
      totalChart = new Chart(ctx, {{
        type: "line",
        data: {{ labels: [], datasets: [{{ label: "Total", data: [], borderWidth: 2, fill: false, tension: 0.2 }}] }},
        options: {{
          responsive: true,
          maintainAspectRatio: false,
          animation: false,
          elements: {{ point: {{ radius: 0 }} }},
          plugins: {{ legend: {{ display:false }} }},
          scales: {{
            y: {{ beginAtZero: true, suggestedMax: {NUM_SEATS}, ticks: {{ stepSize: 1 }} }},
            x: {{ ticks: {{ maxRotation: 0, autoSkip: true, maxTicksLimit: 8 }} }}
          }},
          layout: {{ padding: {{ top: 6, right: 6, bottom: 6, left: 6 }} }}
        }}
      }});
    }}

    function buildSeatCharts() {{
      const wrap=document.getElementById("charts"); wrap.innerHTML=""; charts=[];
      for (let i=0;i<NUM_SEATS;i++) {{
        const row=document.createElement("div"); row.className="chart-row";
        const title=document.createElement("div"); title.className="chart-title"; title.textContent="Seat "+(i+1);
        const box=document.createElement("div"); box.className="chart-box";
        const c=document.createElement("canvas"); c.id="cv_"+i; box.appendChild(c);
        row.appendChild(title); row.appendChild(box); wrap.appendChild(row);

        const ctx=c.getContext("2d");
        const chart=new Chart(ctx, {{
          type:"line",
          data:{{ labels:[], datasets:[{{ label:"S"+(i+1), data:[], borderWidth:2, fill:false, tension: 0.2 }}] }},
          options:{{
            responsive:true, maintainAspectRatio:false, animation:false,
            plugins:{{legend:{{display:false}}}},
            scales:{{
              y:{{ beginAtZero:true, suggestedMax:1, ticks:{{ stepSize:1, display:false }}, grid:{{ display:false }} }},
              x:{{ ticks:{{ maxRotation:0, autoSkip:true, maxTicksLimit:6, font:{{ size:10 }} }}, grid:{{ display:false }} }}
            }},
            layout:{{ padding: {{ top: 4, right: 4, bottom: 4, left: 4 }} }},
            elements:{{ point:{{ radius:0 }} }}
          }}
        }});
        charts.push(chart);
      }}
    }}

    async function updateStatus() {{
      const res=await fetch("/status"); const data=await res.json();
      const tsRaw=data.timestamp; let tsReadable=tsRaw;
      if (typeof tsRaw==="number") tsReadable=new Date(tsRaw*1000).toLocaleString();
      document.getElementById("ts").textContent = tsReadable ?? '---';
      document.getElementById("count").textContent = data.count ?? 0;
      document.getElementById("seats").textContent = JSON.stringify((data.seats||[]).slice(0,NUM_SEATS));

      const seats=(data.seats||[]).slice(0,NUM_SEATS);
      for (let i=0;i<NUM_SEATS;i++) {{
        const occ=seats[i]===1;
        const r=document.getElementById(`seat-rect-${{i}}`);
        const t=document.getElementById(`seat-label-${{i}}`);
        if (!r||!t) continue;
        r.setAttribute('class', `seat-rect ${{occ ? 'occ':'free'}}`);
        t.textContent = occ ? '着座中' : '空';
      }}
    }}

    async function updateCharts() {{
      const r=await fetch("/history"); const hist=await r.json();
      const samples=hist.samples||[];
      const labels=samples.map(s=> typeof s.timestamp==="number" ? new Date(s.timestamp*1000).toLocaleTimeString() : String(s.timestamp).slice(11,19));

      const totals = samples.map(s => Number.isInteger(s.count) ? s.count : (s.seats||[]).reduce((a,v)=>a+(v===1?1:0),0));
      if (totalChart) {{
        totalChart.data.labels = labels;
        totalChart.data.datasets[0].data = totals;
        totalChart.update();
      }}

      const series=Array.from({{length:NUM_SEATS}}, ()=>[]);
      for (const s of samples) {{
        for (let i=0;i<NUM_SEATS;i++) series[i].push((s.seats && s.seats[i]===1)?1:0);
      }}
      for (let i=0;i<NUM_SEATS;i++) {{
        const ch=charts[i]; if (!ch) continue;
        ch.data.labels=labels; ch.data.datasets[0].data=series[i]; ch.update();
      }}
    }}

    async function refreshAll() {{
      try {{ await updateStatus(); await updateCharts(); }} catch(e) {{ console.error(e); }}
    }}

    (async () => {{
      await initBusSvg();
      buildTotalChart();
      buildSeatCharts();
      await refreshAll();
      setInterval(refreshAll, 5000);//描画間隔
    }})();
  </script>
</body>
</html>
    """

# ===== API =====
@app.route("/status")
def status():
    return jsonify(latest_data)

@app.route("/history")
def history():
    return jsonify({"samples": history_log[-MAX_HISTORY:]})

@app.route("/push", methods=["POST"])
def push():
    global latest_data, history_log
    data = request.get_json()
    if not data:
        return jsonify({"error":"no data"}), 400

    seats = (data.get("seats") or [])
    if len(seats) < NUM_SEATS:
        seats = seats + [0]*(NUM_SEATS - len(seats))
    seats = seats[:NUM_SEATS]

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



