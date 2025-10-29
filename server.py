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
    # timestamp が数値(float)のときも 文字列(isoformat)のときも安全に表示する
    ts = latest_data.get("timestamp", None)

    # tsが数値なら "YYYY-mm-dd HH:MM:SS" にフォーマット
    # tsが文字列ならそのまま使う
    if isinstance(ts, (int, float)):
        ts_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(ts))
    else:
        # 文字列(isoformatなど)はそのまま
        ts_str = str(ts)

    seats_list = latest_data.get("seats", [])
    count_now = latest_data.get("count", 0)

    return f"""
    <h1>🚌 Bus Monitor</h1>
    <p>last update: {ts_str}</p>
    <p>current count: {count_now}人</p>
    <p>seats: {seats_list}</p>
    <p style='color:gray;'>Renderで公開中〜ザウルス🦖</p>
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

    # 安全にマージ更新（足りないキーがあっても死なないように）
    latest_data = {
        "timestamp": data.get("timestamp", latest_data.get("timestamp")),
        "seats": data.get("seats", latest_data.get("seats", [])),
        "count": data.get("count", latest_data.get("count", 0))
    }

    return jsonify({"ok": True})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
