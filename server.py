from flask import Flask, jsonify, request
import time, os

app = Flask(__name__)

# 最新状態を保持する辞書
latest_data = {
    "timestamp": time.time(),          # 初期はUNIX秒(float)
    "seats": [0, 1, 0, 0, 1, 0, 0, 0, 0, 0],
    "count": 2
}

@app.route("/")
def index():
    # /status を5秒ごとにfetchして画面を自動更新してくれるビュー
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8" />
        <title>Bus Monitor (auto)</title>
        <style>
            body {
                font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                max-width: 480px;
                margin: 1.5rem auto;
                line-height: 1.5;
                color: #222;
            }
            h1 {
                font-size: 1.6rem;
                display: flex;
                align-items: center;
                gap: .5rem;
                margin-bottom: 1rem;
            }
            .card {
                background: #f9f9f9;
                border-radius: 12px;
                padding: 1rem 1.2rem;
                box-shadow: 0 4px 12px rgba(0,0,0,0.05);
                margin-bottom: 1rem;
            }
            .label {
                font-size: .8rem;
                color: #666;
                margin-top: .25rem;
            }
            .seats-box {
                font-family: monospace;
                font-size: .95rem;
                background: #fff;
                border-radius: 8px;
                border: 1px solid #ddd;
                padding: .6rem .8rem;
                word-break: break-word;
            }
            footer {
                font-size: .8rem;
                color: #888;
                text-align: center;
                margin-top: 2rem;
            }
        </style>
    </head>
    <body>

        <h1>🚌 Bus Monitor (auto)</h1>

        <div class="card">
            <div><strong>last update:</strong> <span id="ts">---</span></div>
            <div style="font-size:1.2rem; margin-top:.5rem;">
                <strong>current count:</strong> <span id="count">0</span> 人
            </div>
            <div class="label">現在乗車中の人数</div>
        </div>

        <div class="card">
            <div style="font-weight:600; margin-bottom:.4rem;">seats:</div>
            <div class="seats-box" id="seats">[0,0,0,0,0,0,0,0,0,0]</div>
            <div class="label">1=着座中 / 0=空席</div>
        </div>

        <footer>
            5秒ごとに自動更新中〜ザウルス🦖
        </footer>

        <script>
        async function updateStatus() {
            try {
                const res = await fetch("/status");
                const data = await res.json();

                // timestamp は push元によって数値(UNIX秒)か文字列(isoformat)が来る
                const tsRaw = data.timestamp;
                let tsReadable = tsRaw;

                if (typeof tsRaw === "number") {
                    const d = new Date(tsRaw * 1000);
                    tsReadable = d.toLocaleString();
                }

                document.getElementById("ts").textContent = tsReadable || "---";
                document.getElementById("count").textContent = data.count ?? "0";
                document.getElementById("seats").textContent = JSON.stringify(data.seats);
            } catch (err) {
                console.error("update failed:", err);
            }
        }

        // 最初に1回即更新
        updateStatus();
        // 5秒ごとに最新データ取得
        setInterval(updateStatus, 5000);
        </script>

    </body>
    </html>
    """

@app.route("/status")
def status():
    # 最新データをそのまま返す
    return jsonify(latest_data)

@app.route("/push", methods=["POST"])
def push():
    # 管理PCから座席データを受け取って更新する
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


