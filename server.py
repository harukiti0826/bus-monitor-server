from flask import Flask, jsonify, request
import time, os

app = Flask(__name__)

latest_data = {
    "timestamp": time.time(),
    "seats": [0, 1, 0, 0, 1, 0, 0, 0, 0, 0],
    "count": 2
}

# ★追加：履歴を保持
history_log = []  # 各要素: { "timestamp": str(or float), "count": int, "seats": [...] }

MAX_HISTORY = 300  # 保存上限（約300サンプルぶんなど）


@app.route("/")
def index():
    # メインダッシュボード（5秒自動更新）
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8" />
        <title>Bus Monitor Dashboard</title>

        <style>
            body {
                font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                max-width: 900px;
                margin: 1.5rem auto 4rem auto;
                line-height: 1.5;
                color: #222;
                background: #f5f5f5;
            }

            header {
                display: flex;
                align-items: flex-end;
                justify-content: space-between;
                flex-wrap: wrap;
                gap: 1rem;
                margin-bottom: 1.5rem;
            }

            .left-head {
                display: flex;
                flex-direction: column;
            }

            .title-row {
                font-size: 1.4rem;
                font-weight: 600;
                display: flex;
                align-items: center;
                gap: .5rem;
            }

            .timestamp {
                font-size: .9rem;
                color: #555;
            }

            .count-box {
                background: white;
                border-radius: 12px;
                box-shadow: 0 10px 24px rgba(0,0,0,0.07);
                padding: 1rem 1.2rem;
                min-width: 200px;
                flex-shrink: 0;
            }
            .count-label {
                font-size: .9rem;
                color: #666;
            }
            .count-value {
                font-size: 2rem;
                font-weight: 700;
                color: #222;
            }

            /* 座席ボード */
            .panel {
                background: white;
                border-radius: 16px;
                box-shadow: 0 10px 24px rgba(0,0,0,0.07);
                padding: 1rem 1.2rem 1.2rem 1.2rem;
                margin-bottom: 1.5rem;
            }

            .panel-title {
                font-weight: 600;
                font-size: 1rem;
                margin-bottom: .5rem;
                display: flex;
                align-items: baseline;
                justify-content: space-between;
                flex-wrap: wrap;
            }

            .seats-grid {
                display: grid;
                grid-template-columns: repeat(2, minmax(120px,1fr));
                gap: 12px;
                max-width: 320px;
            }

            .seat-card {
                border-radius: 12px;
                padding: .8rem;
                font-size: .95rem;
                font-weight: 600;
                text-align: left;
                line-height: 1.4;
                background: #fafafa;
                border: 1px solid #ddd;
                box-shadow: 0 6px 16px rgba(0,0,0,0.06);
                display: flex;
                align-items: center;
                gap: .8rem;
            }

            .led {
                width: 20px;
                height: 20px;
                border-radius: 50%;
                box-shadow: 0 0 10px rgba(0,0,0,0.3);
                border: 2px solid rgba(0,0,0,0.2);
            }

            .led-on {
                background: #2ecc71; /* occupied = green */
            }
            .led-off {
                background: #777; /* free = gray */
            }

            .seat-info-line {
                display: flex;
                flex-direction: column;
            }
            .seat-label {
                font-weight: 600;
            }
            .seat-state {
                font-size: .8rem;
                color: #444;
            }

            /* グラフ部分 */
            .chart-wrap {
                background: white;
                border-radius: 16px;
                box-shadow: 0 10px 24px rgba(0,0,0,0.07);
                padding: 1rem 1.2rem 1.2rem 1.2rem;
            }

            canvas {
                max-width: 100%;
            }

            footer {
                text-align: center;
                font-size: .8rem;
                color: #888;
                margin-top: 2rem;
            }

            .note-row {
                font-size: .8rem;
                color: #555;
                margin-top: .25rem;
            }
        </style>
    </head>
    <body>

        <header>
            <div class="left-head">
                <div class="title-row">
                    <div style="font-size:1.5rem;">🚌</div>
                    <div>Bus Monitor</div>
                </div>
                <div class="timestamp">last update: <span id="last-ts">---</span></div>
            </div>

            <div class="count-box">
                <div class="count-label">現在乗車中</div>
                <div class="count-value"><span id="count-num">0</span> 人</div>
            </div>
        </header>

        <section class="panel">
            <div class="panel-title">
                <div>座席ステータス</div>
                <div class="note-row">● 緑=着座中 / 灰=空席</div>
            </div>

            <div class="seats-grid" id="seats-grid">
                <!-- JSでSeat1〜Seat10をここに描画 -->
            </div>
        </section>

        <section class="chart-wrap">
            <div class="panel-title">
                <div>乗車人数の推移</div>
                <div class="note-row">最新 ~ 過去 (最大300点)</div>
            </div>
            <canvas id="chartSeats" height="200"></canvas>
        </section>

        <footer>
            5秒ごとに自動更新中 / Renderで配信中〜ザウルス🦖
        </footer>

        <!-- グラフ用ライブラリ Chart.js CDN -->
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>

        <script>
        // --- DOM更新系 ---

        function renderSeats(seatsArray) {
            const grid = document.getElementById("seats-grid");
            grid.innerHTML = "";

            for (let i = 0; i < 10; i++) {
                const occupied = (seatsArray && seatsArray[i] === 1);

                const card = document.createElement("div");
                card.className = "seat-card";

                const led = document.createElement("div");
                led.className = "led " + (occupied ? "led-on" : "led-off");

                const info = document.createElement("div");
                info.className = "seat-info-line";
                info.innerHTML = `
                    <div class="seat-label">Seat ${i+1}</div>
                    <div class="seat-state">${occupied ? "着座中" : "空"}</div>
                `;

                card.appendChild(led);
                card.appendChild(info);
                grid.appendChild(card);
            }
        }

        async function fetchStatusAndUpdate() {
            try {
                const res = await fetch("/status");
                const data = await res.json();

                // timestamp 表示成形
                const tsRaw = data.timestamp;
                let tsReadable = tsRaw;
                if (typeof tsRaw === "number") {
                    const d = new Date(tsRaw * 1000);
                    tsReadable = d.toLocaleString();
                }

                document.getElementById("last-ts").textContent = tsReadable || "---";
                document.getElementById("count-num").textContent = (data.count ?? "0");

                renderSeats(data.seats);
            } catch (err) {
                console.error("fetchStatusAndUpdate failed:", err);
            }
        }

        // --- グラフ用 ---

        let chartRef = null;

        function initOrUpdateChart(labels, counts) {
            const ctx = document.getElementById("chartSeats").getContext("2d");

            if (!chartRef) {
                chartRef = new Chart(ctx, {
                    type: "line",
                    data: {
                        labels: labels,
                        datasets: [{
                            label: "乗車人数",
                            data: counts,
                            borderWidth: 2,
                            fill: false,
                            tension: 0.2
                        }]
                    },
                    options: {
                        responsive: true,
                        animation: false,
                        scales: {
                            y: {
                                beginAtZero: true,
                                ticks: {
                                    // 人数は0～10くらい想定？
                                    stepSize: 1
                                }
                            },
                            x: {
                                ticks: {
                                    maxRotation: 0,
                                    autoSkip: true,
                                    maxTicksLimit: 5
                                }
                            }
                        },
                        plugins: {
                            legend: {
                                display: true
                            }
                        }
                    }
                });
            } else {
                chartRef.data.labels = labels;
                chartRef.data.datasets[0].data = counts;
                chartRef.update();
            }
        }

        async function fetchHistoryAndUpdateChart() {
            try {
                const res = await fetch("/history");
                const hist = await res.json();
                // hist.samples: [{timestamp: "...", count: X, seats: [...]}, ...]
                // 新しい順で返すなら逆順に揃える等、サーバー実装と合わせる
                const samples = hist.samples || [];

                const labels = samples.map(s => {
                    // timestampは文字列 or 数値
                    if (typeof s.timestamp === "number") {
                        const d = new Date(s.timestamp * 1000);
                        return d.toLocaleTimeString();
                    } else {
                        // iso文字列のとき
                        return s.timestamp.toString().slice(11,19); // "HH:MM:SS" 抜き
                    }
                });

                const counts = samples.map(s => s.count ?? 0);

                initOrUpdateChart(labels, counts);
            } catch (err) {
                console.error("fetchHistoryAndUpdateChart failed:", err);
            }
        }

        // まとめて呼ぶ
        async function refreshAll() {
            await fetchStatusAndUpdate();
            await fetchHistoryAndUpdateChart();
        }

        // 初回
        refreshAll();
        // 5秒ごと更新
        setInterval(refreshAll, 5000);
        </script>
    </body>
    </html>
    """


@app.route("/status")
def status():
    return jsonify(latest_data)


@app.route("/history")
def history():
    # 直近の履歴を返す
    # 新しい順ではなく「古い→新しい」の時間順に返したいのでそのまま返す
    return jsonify({
        "samples": history_log[-MAX_HISTORY:]
    })


@app.route("/push", methods=["POST"])
def push():
    global latest_data, history_log

    data = request.get_json()
    if not data:
        return jsonify({"error": "no data"}), 400

    # 最新状態を更新
    latest_data = {
        "timestamp": data.get("timestamp", latest_data.get("timestamp")),
        "seats": data.get("seats", latest_data.get("seats", [])),
        "count": data.get("count", latest_data.get("count", 0))
    }

    # 履歴に積む
    history_log.append({
        "timestamp": latest_data["timestamp"],
        "seats": latest_data["seats"],
        "count": latest_data["count"]
    })

    # 上限超えたら古いのから削る
    if len(history_log) > MAX_HISTORY:
        history_log = history_log[-MAX_HISTORY:]

    return jsonify({"ok": True})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
