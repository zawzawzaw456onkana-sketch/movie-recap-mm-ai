from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import uuid
import json
import time
from werkzeug.utils import secure_filename

app = Flask(__name__)
CORS(app)

# =========================
# CONFIG
# =========================

UPLOAD_FOLDER = "uploads"
JOB_FOLDER = "jobs"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(JOB_FOLDER, exist_ok=True)

ALLOWED_VIDEO_EXTENSIONS = {
    "mp4",
    "mov",
    "mkv",
    "avi",
    "webm",
    "m4v"
}

ALLOWED_AUDIO_EXTENSIONS = {
    "mp3",
    "wav",
    "m4a",
    "aac",
    "ogg",
    "flac"
}


# =========================
# HELPERS
# =========================

def allowed_extension(filename, allowed_extensions):
    if not filename or "." not in filename:
        return False

    extension = filename.rsplit(".", 1)[1].lower()

    return extension in allowed_extensions


def create_job():
    job_id = str(uuid.uuid4())

    job_dir = os.path.join(
        JOB_FOLDER,
        job_id
    )

    os.makedirs(job_dir, exist_ok=True)

    return job_id, job_dir


def save_job(job_id, data):
    job_file = os.path.join(
        JOB_FOLDER,
        job_id,
        "job.json"
    )

    with open(
        job_file,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=2
        )


def load_job(job_id):
    job_file = os.path.join(
        JOB_FOLDER,
        job_id,
        "job.json"
    )

    if not os.path.exists(job_file):
        return None

    with open(
        job_file,
        "r",
        encoding="utf-8"
    ) as f:

        return json.load(f)


# =========================
# HOME
# =========================

@app.route("/")
def home():

    return jsonify({
        "status": "ok",
        "message": "MovieRecap MM AI backend is running",
        "version": "2.0"
    })


# =========================
# HEALTH
# =========================

@app.route("/health")
def health():

    return jsonify({
        "status": "healthy",
        "service": "MovieRecap MM AI",
        "version": "2.0"
    })


# =========================
# PROCESS MOVIE
# =========================

@app.route(
    "/process",
    methods=["POST"]
)
def process_movie():

    try:

        movie_file = request.files.get(
            "movie"
        )

        voice_file = request.files.get(
            "voice"
        )

        movie_url = request.form.get(
            "movie_url",
            ""
        ).strip()

        recap_style = request.form.get(
            "recap_style",
            "cinematic"
        ).strip()

        video_format = request.form.get(
            "video_format",
            "youtube"
        ).strip()


        # =========================
        # MOVIE SOURCE CHECK
        # =========================

        if (
            not movie_file
            or not movie_file.filename
        ) and not movie_url:

            return jsonify({
                "status": "error",
                "message":
                    "Movie file သို့မဟုတ် authorized video URL ထည့်ပါ။"
            }), 400


        # =========================
        # CREATE JOB
        # =========================

        job_id, job_dir = create_job()


        movie_saved = False
        voice_saved = False

        movie_path = None
        voice_path = None


        # =========================
        # SAVE MOVIE FILE
        # =========================

        if (
            movie_file
            and movie_file.filename
        ):

            if not allowed_extension(
                movie_file.filename,
                ALLOWED_VIDEO_EXTENSIONS
            ):

                return jsonify({
                    "status": "error",
                    "message":
                        "Supported video format မဟုတ်ပါ။ MP4, MOV, MKV, AVI, WEBM ကို အသုံးပြုပါ။"
                }), 400


            safe_name = secure_filename(
                movie_file.filename
            )

            movie_path = os.path.join(
                job_dir,
                "movie_" + safe_name
            )

            movie_file.save(
                movie_path
            )

            movie_saved = True


        # =========================
        # SAVE VOICE FILE
        # =========================

        if (
            voice_file
            and voice_file.filename
        ):

            if not allowed_extension(
                voice_file.filename,
                ALLOWED_AUDIO_EXTENSIONS
            ):

                return jsonify({
                    "status": "error",
                    "message":
                        "Supported audio format မဟုတ်ပါ။ MP3, WAV, M4A, AAC, OGG, FLAC ကို အသုံးပြုပါ။"
                }), 400


            safe_voice_name = secure_filename(
                voice_file.filename
            )

            voice_path = os.path.join(
                job_dir,
                "voice_" + safe_voice_name
            )

            voice_file.save(
                voice_path
            )

            voice_saved = True


        # =========================
        # CREATE JOB DATA
        # =========================

        job_data = {

            "job_id": job_id,

            "status": "queued",

            "created_at": int(
                time.time()
            ),

            "movie": {

                "uploaded": movie_saved,

                "filename":
                    movie_file.filename
                    if movie_saved
                    else None,

                "url":
                    movie_url
                    if movie_url
                    else None

            },

            "voice": {

                "uploaded": voice_saved,

                "filename":
                    voice_file.filename
                    if voice_saved
                    else None

            },

            "options": {

                "recap_style":
                    recap_style,

                "video_format":
                    video_format

            },

            "pipeline": {

                "upload": "completed",

                "audio_extraction": "pending",

                "transcription": "pending",

                "recap_script": "pending",

                "narration": "pending",

                "scene_selection": "pending",

                "subtitle": "pending",

                "video_render": "pending",

                "thumbnail": "pending",

                "final_output": "pending"

            }

        }


        save_job(
            job_id,
            job_data
        )


        # =========================
        # RESPONSE
        # =========================

        return jsonify({

            "status": "queued",

            "message":
                "Movie ကို လက်ခံပြီး AI pipeline အတွက် job တည်ဆောက်ပြီးပါပြီ။",

            "job_id":
                job_id,

            "movie_uploaded":
                movie_saved,

            "voice_uploaded":
                voice_saved,

            "recap_style":
                recap_style,

            "video_format":
                video_format,

            "next_step":
                "Audio extraction → transcription → Burmese recap script"

        }), 202


    except Exception as e:

        return jsonify({

            "status": "error",

            "message":
                str(e)

        }), 500


# =========================
# JOB STATUS
# =========================

@app.route(
    "/status/<job_id>",
    methods=["GET"]
)
def job_status(job_id):

    try:

        job = load_job(
            job_id
        )

        if job is None:

            return jsonify({

                "status": "error",

                "message":
                    "Job မတွေ့ပါ။"

            }), 404


        return jsonify(
            job
        )


    except Exception as e:

        return jsonify({

            "status": "error",

            "message":
                str(e)

        }), 500


# =========================
# PIPELINE INFO
# =========================

@app.route(
    "/pipeline",
    methods=["GET"]
)
def pipeline():

    return jsonify({

        "status": "ok",

        "pipeline": [

            {
                "step": 1,
                "name": "Movie Upload",
                "status": "ready"
            },

            {
                "step": 2,
                "name": "Audio Extraction",
                "status": "planned"
            },

            {
                "step": 3,
                "name": "Chinese Speech Transcription",
                "status": "planned"
            },

            {
                "step": 4,
                "name": "Burmese Recap Script",
                "status": "planned"
            },

            {
                "step": 5,
                "name": "Burmese Narration",
                "status": "planned"
            },

            {
                "step": 6,
                "name": "AI Scene Selection",
                "status": "planned"
            },

            {
                "step": 7,
                "name": "Subtitle Generation",
                "status": "planned"
            },

            {
                "step": 8,
                "name": "Video Rendering",
                "status": "planned"
            },

            {
                "step": 9,
                "name": "Thumbnail",
                "status": "planned"
            },

            {
                "step": 10,
                "name": "Final Download",
                "status": "planned"
            }

        ]

    })


# =========================
# RUN SERVER
# =========================

if __name__ == "__main__":

    port = int(
        os.environ.get(
            "PORT",
            10000
        )
    )

    app.run(
        host="0.0.0.0",
        port=port
    )
