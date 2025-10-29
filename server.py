from flask import Flask, jsonify, request
import time, os

app = Flask(__name__)

latest_data = {
    "timestamp": time.time(),  # 初期はUNIX秒(float)
    "seats": [0, 1, 0, 0, 1, 0, 0, 0, 0, 0],
    "count": 2
}

@app.route("/")
def index():
    # simpleビュー（動いてるやつ）
    ts = latest_data.get("timestamp", None)
    if isinstance(ts, (int, float)):
        ts_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(ts))
    else:
        ts_str = str(ts)

    html = f"""
    <h1>🚌 Bus Monitor (simple)</h1>
    <p>last update: {ts_str}</p>
    <p>current count: {latest_data.get("count",0)}人</p>
    <p>seats: {latest_data.get("seats",[])}</p>
    <p style='color:gray;'>※本番ビューは /dashboard です🦖</p>
    """
    return html


@app.route("/dashboard")
def dashboard():
    # 5秒ごとに /status をfetchして画面を更新するビュー
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8" />
        <title>Bus Live Dashboard</title>
        <style>
            body {
                font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                background: #f5f5f5;
                color: #222;
                max-width: 900px;
                margin: 1.5rem auto 4rem auto;
                line-height: 1.4;
            }

            header {
                display: flex;
                align-items: flex-end;
                justify-content: space-between;
                flex-wrap: wrap;
                gap: 1rem;
                margin-bottom: 1.5rem;
            }

            .title-box {
                display: flex;
                align-items: center;
                gap: .6rem;
                font-weight: 600;
                font-size: 1.4rem;
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

            .seats-wrapper {
                background: white;
                border-radius: 16px;
                box-shadow: 0 10px 24px rgba(0,0,0,0.07);
                padding: 1rem 1.2rem 1.5rem 1.2rem;
            }

            .seats-title {
                font-weight: 600;
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
                text-align: center;
                line-height: 1.4;
                color: white;
                box-shadow: 0 6px 16px rgba(0,0,0,0.12);
            }

            .seat-free {
                background: #777; /* 空席 */
            }

            .seat-occupied {
                background: #2ecc71; /* 着座中グリーン */
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
            <div>
                <div class="title-box">
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

        <section class="seats-wrapper">
            <div class="seats-title">
                <div>座席ステータス</div>
                <div class="note-row">1 = 着座中 / 0 = 空席</div>
            </div>

            <div class="seats-grid" id="seats-grid">
                <!-- JSでSeat1〜Seat10をここに描画する -->
            </div>
        </section>

        <footer>
            5秒ごとに自動更新中 / Renderで配信中〜ザウルス🦖
        </footer>

        <script>
        function renderSeats(seatsArray) {
            const grid = document.getElementById("seats-grid");
            grid.innerHTML = "";

            for (let i = 0; i < 10; i++) {
                const val = (seatsArray && seatsArray[i] === 1) ? 1 : 0;
                const occupied = (val === 1);

                const div = document.createElement("div");
                div.className = "seat-card " + (occupied ? "seat-occupied" : "seat-free");
                div.innerHTML = `
                    Seat ${i+1}<br>
                    ${occupied ? "着座中" : "空"}
                `;
                grid.appendChild(div);
            }
        }

        async function refreshData() {
            try {
                const res = await fetch("/status");
                const data = await res.json();

                let tsReadable = data.timestamp;
                if (typeof data.timestamp === "number") {
                    const d = new Date(data.timestamp * 1000);
                    tsReadable = d.toLocaleString();
                }

                document.getElementById("last-ts").textContent = tsReadable || "---";
                document.getElementById("count-num").textContent = (data.count ?? "0");
                renderSeats(data.seats);
            } catch (err) {
                console.error("refreshData failed:", err);
            }
        }

        refreshData();
        setInterval(refreshData, 5000);
        </script>
    </body>
    </html>
    """


@app.route("/status")
def status():
    return jsonify(latest_data)


@app.route("/push", methods=["POST"])
def push():
    global latest_data
    data = request.get_json()
    if not data:
        return jsonify({"error": "no data"}), 400

    latest_data = {
        "timestamp": data.get("timestamp", latest_data.get("timestamp")),
        "seats": data.get("seats", latest_data.get("seats", [])),
        "count": data.get("count", latest_data.get("count", 0))
    }

    return jsonify({"ok": True})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

