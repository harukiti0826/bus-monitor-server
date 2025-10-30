from flask import Flask, jsonify, request, send_from_directory
import time, os

app = Flask(__name__, static_folder="static")

# ====== 座席数（8ch） ======
NUM_SEATS = 8

# ====== 最新状態 + 履歴 ======
latest_data = {
    "timestamp": time.time(),
    "seats": [0]*NUM_SEATS,
    "count": 0
}
history_log = []         # 各要素: {"timestamp": <float or str>, "seats": [0/1...], "count": int}
MAX_HISTORY = 360        # 5秒周期で約30分分

# 静的ファイル（バス図）
@app.route("/static/<path:filename>")
def static_files(filename):
    return send_from_directory(app.static_folder, filename)

# ====== メインダッシュボード ======
@app.route("/")
def index():
    return f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8" />
<title>Bus Monitor</title>
<meta name="viewport" content="width=device-width,initial-scale=1" />
<style>
  body {{
    font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
    color: #222; background:#f5f5f5; margin:0; padding:0 10px 60px;
  }}
  h1 {{
    font-size: 1.4rem; display:flex; gap:.5rem; align-items:center; margin:16px 0 8px;
  }}
  .sub {{
    color:#666; font-size:.9rem; margin-bottom:14px;
  }}

  /* ===== バス図オーバーレイ ===== */
  .bus-wrap {{
    position: relative;
    width: 100%;
    max-width: 980px;
    margin: 0 auto 14px auto;
    aspect-ratio: 16 / 9;      /* 画像比率目安。合わなければ後で微調整OK */
    background: #ddd url('/static/bus.png') center/contain no-repeat;
    border-radius: 12px;
    box-shadow: 0 10px 24px rgba(0,0,0,.08);
  }}
  .seat-overlay {{
    position: absolute;
    width: 9.5%;      /* 各座席札の幅（％で指定） */
    height: 16%;
    border: 2px solid #202020;
    border-radius: 6px;
    display:flex; align-items:center; justify-content:center;
    font-weight:700;
    box-shadow: 0 6px 16px rgba(0,0,0,.12);
  }}
  .free  {{ background:#bdbdbd; color:#111; }}
  .occ   {{ background:#8bdc6a; color:#111; }}

  /* ===== 数字カード ===== */
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
  <div class="sub">last update: <span id="ts">---</span> / 5秒ごとに自動更新〜ザウルス</div>

  <!-- ===== バス図オーバーレイ ===== -->
  <div class="bus-wrap" id="bus">
    <!-- JSで座席オーバーレイ（8個）を生成します -->
  </div>

  <!-- ===== 数字カード ===== -->
  <div class="cards">
    <div class="card">
      <div class="muted">現在乗車中</div>
      <div class="big"><span id="count">0</span> 人</div>
    </div>
    <div class="card">
      <div class="muted">席配列</div>
      <div style="font-family:monospace" id="seats">[0,0,0,0,0,0,0,0]</div>
    </div>
  </div>

  <!-- ===== ミニグラフ（8本） ===== -->
  <div class="charts" id="charts">
    <!-- Seat1..Seat8 の行をJSで生成 -->
  </div>

  <footer>Render配信中🟢 / Chart.js & custom overlay 🦖</footer>

  <!-- Chart.js CDN -->
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <script>
    // ====== 座席数（JS側も8に合わせる） ======
    const NUM_SEATS = {NUM_SEATS};

    // ====== バス図の座席オーバーレイ座標（%単位） ======
    //   top/left/width/height を % で指定（画像に対する相対位置）。
    //   添付の図に合わせて初期値を置いています。微調整はここをいじればOK。
    //   座席の並び: S1..S8（管理PCの並びに合わせて対応づけてね）
    const SEAT_POS = [
      // 左列 上→下
      {{top:12, left:9.5,  w:9.5, h:16}},  // S1
      {{top:39, left:9.5,  w:9.5, h:16}},  // S2
      {{top:66, left:9.5,  w:9.5, h:16}},  // S3

      // 中列（例：中央2席）
      {{top:17, left:44,  w:9.5, h:16}},   // S4
      {{top:17, left:58,  w:9.5, h:16}},   // S5

      // 右列 上→下
      {{top:12, left:83,  w:9.5, h:16}},   // S6
      {{top:39, left:83,  w:9.5, h:16}},   // S7
      {{top:66, left:83,  w:9.5, h:16}},   // S8
    ];

    // ====== DOM構築：オーバーレイ座席札を作成 ======
    function buildSeatOverlays() {{
      const bus = document.getElementById("bus");
      bus.innerHTML = "";
      for (let i=0; i<NUM_SEATS; i++) {{
        const pos = SEAT_POS[i];
        const d = document.createElement("div");
        d.className = "seat-overlay free";
        d.style.top = pos.top + "%";
        d.style.left = pos.left + "%";
        d.style.width = pos.w + "%";
        d.style.height = pos.h + "%";
        d.id = "seatbox_"+i;
        d.textContent = "空";
        bus.appendChild(d);
      }}
    }}

    // ====== ミニグラフ 8本を生成 ======
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

        // Chartインスタンス（空で初期化）
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
              y: {{
                beginAtZero:true, suggestedMax:1,
                ticks: {{ stepSize:1 }}
              }},
              x: {{
                ticks: {{ maxRotation:0, autoSkip:true, maxTicksLimit:6 }}
              }}
            }}
          }}
        }});
        charts.push(chart);
      }}
    }}

    // ====== /status を取得して、数/座席オーバーレイ更新 ======
    async function updateStatus() {{
      const r = await fetch("/status");
      const data = await r.json();

      // タイムスタンプ表示
      const ts = data.timestamp;
      let tsStr = ts;
      if (typeof ts === "number") {{
        const d = new Date(ts*1000);
        tsStr = d.toLocaleString();
      }}
      document.getElementById("ts").textContent = tsStr || "---";

      // 人数
      document.getElementById("count").textContent = (data.count ?? 0);

      // 座席配列
      const seats = (data.seats || []).slice(0, NUM_SEATS);
      document.getElementById("seats").textContent = JSON.stringify(seats);

      // オーバーレイの色/表示更新
      for (let i=0; i<NUM_SEATS; i++) {{
        const d = document.getElementById("seatbox_"+i);
        if (!d) continue;
        if (seats[i] === 1) {{
          d.classList.remove("free");
          d.classList.add("occ");
          d.textContent = "着座中";
        }} else {{
          d.classList.remove("occ");
          d.classList.add("free");
          d.textContent = "空";
        }}
      }}
    }}

    // ====== /history を取得して、8本のチャートに反映 ======
    async function updateCharts() {{
      const r = await fetch("/history");
      const hist = await r.json();
      const samples = hist.samples || [];  // 古→新の順で返ってくる想定

      // ラベル（時間）
      const labels = samples.map(s => {{
        if (typeof s.timestamp === "number") {{
          return new Date(s.timestamp*1000).toLocaleTimeString();
        }} else {{
          return String(s.timestamp).slice(11,19);  // "HH:MM:SS"
        }}
      }});

      // 各席の系列を作る
      const series = Array.from({{length:NUM_SEATS}}, () => []);
      for (const s of samples) {{
        for (let i=0; i<NUM_SEATS; i++) {{
          const v = (s.seats && s.seats[i] === 1) ? 1 : 0;
          series[i].push(v);
        }}
      }}

      // 8本分のチャートを更新
      for (let i=0; i<NUM_SEATS; i++) {{
        const ch = charts[i];
        if (!ch) continue;
        ch.data.labels = labels;
        ch.data.datasets[0].data = series[i];
        ch.update();
      }}
    }}

    async function refreshAll() {{
      try {{
        await updateStatus();
        await updateCharts();
      }} catch(e) {{
        console.error(e);
      }}
    }}

    // 初期構築＆定期更新
    buildSeatOverlays();
    buildCharts();
    refreshAll();
    setInterval(refreshAll, 5000);
  </script>
</body>
</html>
    """

# ====== 最新状態を返す ======
@app.route("/status")
def status():
    return jsonify(latest_data)

# ====== 履歴を返す（古→新で最大 MAX_HISTORY 件） ======
@app.route("/history")
def history():
    return jsonify({"samples": history_log[-MAX_HISTORY:]})

# ====== 管理PCからの push ======
@app.route("/push", methods=["POST"])
def push():
    global latest_data, history_log
    data = request.get_json()
    if not data:
        return jsonify({"error":"no data"}), 400

    # 座席配列は8chに揃える（不足は0で埋め、超過は切り捨て）
    seats = (data.get("seats") or [])
    if len(seats) < NUM_SEATS:
        seats = seats + [0]*(NUM_SEATS - len(seats))
    seats = seats[:NUM_SEATS]

    count = int(data.get("count", sum(1 for v in seats if v==1)))
    ts    = data.get("timestamp", time.time())

    latest_data = {"timestamp": ts, "seats": seats, "count": count}

    # 履歴追加（上限を超えたら古い方を削る）
    history_log.append({"timestamp": ts, "seats": seats, "count": count})
    if len(history_log) > MAX_HISTORY:
        history_log = history_log[-MAX_HISTORY:]

    return jsonify({"ok": True})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
