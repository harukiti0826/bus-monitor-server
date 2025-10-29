from flask import Flask, jsonify, request
import time, os   # ← osを追加

app = Flask(__name__)

latest_data = {
    "timestamp": time.time(),
    "seats": [0, 1, 0, 0, 1, 0, 0, 0, 0, 0],
    "count": 2
}

@app.route("/")
def index():
    return f"""
    <h1>🚌 Bus Monitor</h1>
    <p>last update: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(latest_data['timestamp']))}</p>
    <p>current count: {latest_data['count']}人</p>
    <p>seats: {latest_data['seats']}</p>
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
    latest_data = data
    return jsonify({"ok": True})

if __name__ == "__main__":
    # Renderが自動で渡すポート番号を取得
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
