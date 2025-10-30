# server.py — ラベル+15pt / 薄型ミニグラフ / 合計人数グラフ追加版
from flask import Flask, jsonify, request, send_from_directory
import time, os, json

app = Flask(__name__, static_folder="static")

# ===== 設定 =====
NUM_SEATS    = 8
MAX_HISTORY  = 360           # 5秒ごと約30分
EDIT_MODE_FLAG = False       # 位置微調整が必要なら True に

# ===== 最終座標（あなたの提供値） =====
SEATS_NORM_DATA = [
    {"x": 0.0623, "y": 0.1666, "w": 0.0858, "h": 0.1678},
    {"x": 0.0623, "y": 0.4133, "w": 0.0868, "h": 0.1716},
    {"x": 0.0623, "y": 0.6639, "w": 0.0868, "h": 0.1697},
    {"x": 0.2961, "y": 0.1642, "w": 0.0879, "h": 0.1716},
    {"x": 0.4657, "y": 0.1661, "w": 0.0889, "h": 0.1697},
    {"x": 0.7004, "y": 0.1646, "w": 0.0879, "h": 0.1716},
    {"x": 0.7014, "y": 0.4133, "w": 0.0868, "h": 0.1716},
    {"x": 0.7004, "y": 0.6619, "w": 0.0879, "h": 0.1736}
]

# ===== ランタイム状態 =====
latest_data = {"timestamp": time.time(), "seats": [0]*NUM_SEATS, "count": 0}
history_log = []  # [{timestamp, seats[], count}...]

# ===== 静的配信 =====
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
  :root {{
    --card-pad: 10px;
  }}
  body {{
    font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
    color:#222; background:#f5f5f5; margin:0; padding:12px 10px 60px;
  }}
  h1 {{ font-size:1.4rem; display:flex; gap:.5rem; align-items:center; margin:12px 0 6px; }}
  .sub {{ color:#666; font-size:.9rem; margin-bottom:12px; }}

  .bus-wrap {{
    width:100%; max-width:980px; margin:0 auto 10px auto;
    background:#f5f5f5; border-radius:12px; box-shadow:0 10px 24px rgba(0,0,0,.08);
  }}
  .seat-rect.free {{ fill:#bdbdbd; stroke:#202020; stroke-width:2; }}
  .seat-rect.occ  {{ fill:#8bdc6a; stroke:#202020; stroke-width:2; }}
  /* ★ ラベル +15pt（16→31px） */
  .seat-label {{
    font: 700 31px system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
    fill:#111;
    paint-order: stroke; stroke: #fff; stroke-width: 2px; /* 視認性UP */
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

  /* ★ グラフを薄型・横長に圧縮 */
  .charts {{
    max-width:980px; margin:0 auto; background:#fff; border-radius:16px;
    box-shadow:0 10px 24px rgba(0,0,0,.07); padding:8px 10px;
  }}
  .chart-row {{ display:flex; align-items:center; gap:8px; margin:2px 0; }}
  .chart-title {{ width:64px; text-align:right; font-size:.85rem; color:#444; }}
  .chart-box {{ flex:1; min-width:0; }}
  /* ★ 1本あたり高さを約36pxへ */
  .chart-box canvas {{ width:100%; height:36px; }}

  /* ★ 合計人数グラフ（少し大きめ） */
  .total-chart-wrap {{
    max-width:980px; margin:0 auto 10px; background:#fff; border-radius:16px;
    box-shadow:0 10px 24px rgba(0,0,0,.07); padding:10px;
  }}
  #totalChart {{ width:100%; height:60px; }}

  footer {{ text-align:center; color:#888; font-size:.8rem; margin-top:12px; }}
</style>
</head>
<body>
  <h1>🚌 Bus Monitor</h1>
  <div class="sub">last update: <span id="ts">---</span> / 5秒ごとに自動更新</div>

  <div class="bus-wrap">
    <svg id="bus-svg" width="100%" height="auto" preserveAspectRatio="xMidYMid meet"></svg>
  </div>

  <!-- 合計人数グラフ -->
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
    // ===== Pythonから安全に注入 =====
    const NUM_SEATS  = {NUM_SEATS};
    const SEATS_NORM = {seats_norm_json};
    const EDIT_MODE  = {edit_mode_js};

    let IMG_W = 0, IMG_H = 0;

    function loadImage(src) {{
      return new Promise((resolve, reject) => {{
        const im = new Image();
        im.onload = () => resolve(im);
        im.onerror = reject;
        im.src = src + '?v=' + Date.now();
      }});
    }}
    function normToAbs(n) {{ return {{ x:n.x*IMG_W, y:n.y*IMG_H, w:n.w*IMG_W, h:n.h*IMG_H }}; }}
    function absToNorm(a) {{ return {{ x:a.x/IMG_W, y:a.y/IMG_H, w:a.w/IMG_W, h:a.h/IMG_H }}; }}

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

      for (let i=0;i<NUM_SEATS;i++) {{
        const g = document.createElementNS('http://www.w3.org/2000/svg', 'g');
        g.setAttribute('data-index', String(i));

        const {{x,y,w,h}} = normToAbs(SEATS_NORM[i]);
        const r = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
        r.setAttribute('x',x); r.setAttribute('y',y);
        r.setAttribute('rx',10); r.setAttribute('ry',10);
        r.setAttribute('width',w); r.setAttribute('height',h);
        r.setAttribute('class','seat-rect free');
        r.setAttribute('id',`seat-rect-${{i}}`);

        const t = document.createElementNS('http://www.w3.org/2000/svg', 'text');
        t.setAttribute('x', x + w/2); t.setAttribute('y', y + h/2 + 6);
        t.setAttribute('text-anchor','middle'); t.setAttribute('class','seat-label');
        t.setAttribute('id',`seat-label-${{i}}`); t.textContent = '空';

        g.appendChild(r); g.appendChild(t); seatLayer.appendChild(g);
        if (EDIT_MODE) attachSeatEditors(svg, g, r, t, i);
      }}
    }}

    // ===（任意）編集ツール：位置＆サイズ（前バージョン通り）===
    function attachSeatEditors(svg, group, rect, text, idx) {{
      let dragging=false, resizing=false, which=null;
      let start={{x:0,y:0}}, orig={{x:0,y:0,w:0,h:0}};
      const handles = makeHandles(rect);
      for (const c of Object.values(handles)) group.appendChild(c);

      group.addEventListener('mousedown', (e) => {{
        if (!EDIT_MODE) return;
        const t=e.target;
        if (t.classList.contains('handle')) {{ resizing=true; which=t.dataset.which; }}
        else {{ dragging=true; }}
        start = svgPoint(svg, e);
        orig.x=+rect.getAttribute('x'); orig.y=+rect.getAttribute('y');
        orig.w=+rect.getAttribute('width'); orig.h=+rect.getAttribute('height');
        e.preventDefault();
      }});
      window.addEventListener('mousemove', (e) => {{
        if (!EDIT_MODE) return;
        if (!dragging && !resizing) return;
        const p=svgPoint(svg,e); const dx=p.x-start.x, dy=p.y-start.y;
        let nx=orig.x, ny=orig.y, nw=orig.w, nh=orig.h;
        if (dragging) {{ nx=orig.x+dx; ny=orig.y+dy; }}
        else if (resizing) {{
          switch(which) {{
            case 'tl': nx=orig.x+dx; ny=orig.y+dy; nw=orig.w-dx; nh=orig.h-dy; break;
            case 'tr': ny=orig.y+dy; nw=orig.w+dx; nh=orig.h-dy; break;
            case 'bl': nx=orig.x+dx; nw=orig.w-dx; nh=orig.h+dy; break;
            case 'br': nw=orig.w+dx; nh=orig.h+dy; break;
          }}
        }}
        const MIN=8;
        nx=Math.max(0,nx); ny=Math.max(0,ny);
        nw=Math.max(MIN,Math.min(nw,IMG_W-nx));
        nh=Math.max(MIN,Math.min(nh,IMG_H-ny));
        rect.setAttribute('x',nx); rect.setAttribute('y',ny);
        rect.setAttribute('width',nw); rect.setAttribute('height',nh);
        text.setAttribute('x', nx+nw/2); text.setAttribute('y', ny+nh/2+6);
        updateHandlesPosition(rect, handles);
      }});
      window.addEventListener('mouseup', () => {{
        if (!EDIT_MODE) return;
        if (!dragging && !resizing) return;
        dragging=false; resizing=false; which=null;
        const x=+rect.getAttribute('x'), y=+rect.getAttribute('y');
        const w=+rect.getAttribute('width'), h=+rect.getAttribute('height');
        const norm={{x:+(x/IMG_W).toFixed(4), y:+(y/IMG_H).toFixed(4), w:+(w/IMG_W).toFixed(4), h:+(h/IMG_H).toFixed(4)}};
        console.log(`S${{idx+1}}:`, JSON.stringify(norm));
      }});
    }}
    function makeHandles(rect) {{
      const defs=[{{which:'tl',cls:'handle tl'}},{{which:'tr',cls:'handle tr'}},{{which:'bl',cls:'handle bl'}},{{which:'br',cls:'handle br'}}];
      const hs={{}}; for (const d of defs) {{
        const c=document.createElementNS('http://www.w3.org/2000/svg','circle');
        c.setAttribute('r',8); c.setAttribute('class',d.cls); c.dataset.which=d.which; hs[d.which]=c;
      }} updateHandlesPosition(rect, hs); return hs;
    }}
    function updateHandlesPosition(rect, hs) {{
      const x=+rect.getAttribute('x'), y=+rect.getAttribute('y');
      const w=+rect.getAttribute('width'), h=+rect.getAttribute('height');
      hs.tl?.setAttribute('cx',x);     hs.tl?.setAttribute('cy',y);
      hs.tr?.setAttribute('cx',x+w);   hs.tr?.setAttribute('cy',y);
      hs.bl?.setAttribute('cx',x);     hs.bl?.setAttribute('cy',y+h);
      hs.br?.setAttribute('cx',x+w);   hs.br?.setAttribute('cy',y+h);
    }}
    function svgPoint(svg, evt) {{
      const pt=svg.createSVGPoint(); pt.x=evt.clientX; pt.y=evt.clientY;
      return pt.matrixTransform(svg.getScreenCTM().inverse());
    }}

    // ===== グラフ =====
    let charts=[], totalChart=null;

    function buildTotalChart() {{
      const ctx = document.getElementById('totalChart').getContext('2d');
      totalChart = new Chart(ctx, {{
        type: "line",
        data: {{ labels: [], datasets: [{{ label: "Total", data: [], borderWidth: 2, fill: false, tension: 0.2 }}] }},
        options: {{
          responsive: true, maintainAspectRatio: false, animation: false,
          plugins: {{ legend: {{ display:false }} }},
          scales: {{
            y: {{ beginAtZero: true, suggestedMax: {NUM_SEATS}, ticks: {{ stepSize: 1 }} }},
            x: {{ ticks: {{ maxRotation: 0, autoSkip: true, maxTicksLimit: 8 }} }}
          }},
          elements: {{ point: {{ radius: 0 }} }}
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
          data:{{ labels:[], datasets:[{{ label:"S"+(i+1), data:[], borderWidth:2, fill:false, tension:0.2 }}] }},
          options:{{
            responsive:true, maintainAspectRatio:false, animation:false,
            plugins:{{legend:{{display:false}}}},
            scales:{{
              y:{{ beginAtZero:true, suggestedMax:1, ticks:{{ stepSize:1, display:false }} }},
              x:{{ ticks:{{ maxRotation:0, autoSkip:true, maxTicksLimit:6, font:{{ size:10 }} }} }}
            }},
            layout:{{ padding:0 }},
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

      // 合計人数
      const totals = samples.map(s => Number.isInteger(s.count) ? s.count : (s.seats||[]).reduce((a,v)=>a+(v===1?1:0),0));
      if (totalChart) {{
        totalChart.data.labels = labels;
        totalChart.data.datasets[0].data = totals;
        totalChart.update();
      }}

      // 各席
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
      setInterval(refreshAll, 5000);
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
