from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import uuid

app = Flask(__name__)
CORS(app)

UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


@app.route("/")
def home():
    return jsonify({
        "status": "ok",
        "message": "MovieRecap MM AI backend is running"
    })


@app.route("/health")
def health():
    return jsonify({
        "status": "healthy"
    })


@app.route("/process", methods=["POST"])
def process_movie():

    try:
        movie_file = request.files.get("movie")
        voice_file = request.files.get("voice")

        movie_url = request.form.get("movie_url", "")
        recap_style = request.form.get("recap_style", "cinematic")
        video_format = request.form.get("video_format", "youtube")

        movie_path = None
        voice_path = None

        # Movie file
        if movie_file and movie_file.filename:

            movie_name = (
                str(uuid.uuid4()) +
                "_" +
                movie_file.filename
            )

            movie_path = os.path.join(
                UPLOAD_FOLDER,
                movie_name
            )

            movie_file.save(movie_path)

        # Voice file
        if voice_file and voice_file.filename:

            voice_name = (
                str(uuid.uuid4()) +
                "_" +
                voice_file.filename
            )

            voice_path = os.path.join(
                UPLOAD_FOLDER,
                voice_name
            )

            voice_file.save(voice_path)

        # Check movie source
        if not movie_path and not movie_url:

            return jsonify({
                "status": "error",
                "message": "Movie file သို့မဟုတ် authorized video URL ထည့်ပါ။"
            }), 400

        return jsonify({

            "status": "received",

            "message":
                "Movie ကို Backend ဆီ အောင်မြင်စွာ လက်ခံရရှိပါပြီ။",

            "movie_file":
                bool(movie_path),

            "movie_url":
                movie_url if movie_url else None,

            "voice_file":
                bool(voice_path),

            "recap_style":
                recap_style,

            "video_format":
                video_format,

            "next_step":
                "AI movie analysis and rendering pipeline will run here."

        })

    except Exception as e:

        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=10000
    )
