from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route("/")
def home():
    return jsonify({
        "status": "ok",
        "message": "MovieRecap MM AI backend is running"
    })

@app.route("/health")
def health():
    return jsonify({"status": "healthy"})

@app.route("/process", methods=["POST"])
def process_movie():
    return jsonify({
        "status": "received",
        "message": "Movie file received. AI processing will be connected next."
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
