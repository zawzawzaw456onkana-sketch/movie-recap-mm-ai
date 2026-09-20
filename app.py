from flask import Flask, request, jsonify
from flask_cors import CORS

import os
import uuid
import json
import time
import threading
import subprocess

from werkzeug.utils import secure_filename
from openai import OpenAI
import imageio_ffmpeg


app = Flask(__name__)
CORS(app)


# =========================================================
# CONFIG
# =========================================================

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
    "flac",
    "webm"
}


# =========================================================
# OPENAI
# =========================================================

OPENAI_API_KEY = os.environ.get(
    "OPENAI_API_KEY"
)

if OPENAI_API_KEY:
    client = OpenAI(
        api_key=OPENAI_API_KEY
    )
else:
    client = None


# =========================================================
# HELPERS
# =========================================================

def allowed_extension(
    filename,
    allowed_extensions
):

    if not filename:
        return False

    if "." not in filename:
        return False

    extension = filename.rsplit(
        ".",
        1
    )[1].lower()

    return extension in allowed_extensions


def create_job():

    job_id = str(
        uuid.uuid4()
    )

    job_dir = os.path.join(
        JOB_FOLDER,
        job_id
    )

    os.makedirs(
        job_dir,
        exist_ok=True
    )

    return job_id, job_dir


def job_file_path(job_id):

    return os.path.join(
        JOB_FOLDER,
        job_id,
        "job.json"
    )


def save_job(
    job_id,
    data
):

    path = job_file_path(
        job_id
    )

    with open(
        path,
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

    path = job_file_path(
        job_id
    )

    if not os.path.exists(path):
        return None

    with open(
        path,
        "r",
        encoding="utf-8"
    ) as f:

        return json.load(f)


def update_job(
    job_id,
    **changes
):

    job = load_job(
        job_id
    )

    if job is None:
        return

    job.update(
        changes
    )

    job["updated_at"] = int(
        time.time()
    )

    save_job(
        job_id,
        job
    )


def update_pipeline(
    job_id,
    step,
    status
):

    job = load_job(
        job_id
    )

    if job is None:
        return

    job["pipeline"][step] = status

    job["updated_at"] = int(
        time.time()
    )

    save_job(
        job_id,
        job
    )


def get_ffmpeg():

    return imageio_ffmpeg.get_ffmpeg_exe()


# =========================================================
# AUDIO EXTRACTION
# =========================================================

def extract_audio(
    movie_path,
    audio_path
):

    ffmpeg = get_ffmpeg()

    command = [

        ffmpeg,

        "-y",

        "-i",
        movie_path,

        "-vn",

        "-ac",
        "1",

        "-ar",
        "16000",

        "-c:a",
        "libmp3lame",

        "-b:a",
        "64k",

        audio_path

    ]

    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    if result.returncode != 0:

        raise RuntimeError(
            "Audio extraction failed: "
            + result.stderr[-2000:]
        )


# =========================================================
# TRANSCRIPTION
# =========================================================

def transcribe_audio(
    audio_path
):

    if client is None:

        raise RuntimeError(
            "OPENAI_API_KEY မရှိသေးပါ။ Render Environment Variables ထဲမှာ OPENAI_API_KEY ထည့်ပါ။"
        )


    with open(
        audio_path,
        "rb"
    ) as audio_file:

        result = client.audio.transcriptions.create(

            model="gpt-4o-transcribe",

            file=audio_file,

            language="zh",

            response_format="json"

        )


    return result.text


# =========================================================
# BURMESE RECAP SCRIPT
# =========================================================

def generate_burmese_recap(
    transcript,
    recap_style
):

    if client is None:

        raise RuntimeError(
            "OPENAI_API_KEY မရှိသေးပါ။"
        )


    style_map = {

        "cinematic":
            "ရုပ်ရှင်ဆန်ပြီး suspense ပါအောင်",

        "natural":
            "လူတစ်ယောက်က သူငယ်ချင်းကို ဇာတ်လမ်းပြောသလို သဘာဝကျကျ",

        "fast":
            "မြန်မြန်ဆန်ဆန်၊ အဓိကအချက်တွေကိုပဲ ထိထိမိမိ",

        "detailed":
            "ဇာတ်လမ်းအကြောင်းအရာကို အသေးစိတ်၊ အစမှအဆုံး ရှင်းပြသလို"

    }


    selected_style = style_map.get(
        recap_style,
        style_map["cinematic"]
    )


    prompt = f"""
You are an expert Myanmar movie recap script writer.

The source movie dialogue/transcript is Chinese.

Write a natural Burmese movie recap script.

Style:
{selected_style}

Requirements:

- Write entirely in Burmese.
- Do not translate word-for-word.
- Explain events clearly.
- Keep character relationships understandable.
- Preserve important plot events.
- Make it engaging for a Myanmar audience.
- Do not invent events that are not supported by the transcript.
- Do not include unnecessary analysis.
- Do not mention that you are an AI.
- Format as a narration script.

Chinese transcript:

{transcript}
"""


    response = client.responses.create(

        model="gpt-5.6-luna",

        input=prompt

    )


    return response.output_text


# =========================================================
# COMPLETE AI JOB
# =========================================================

def run_pipeline(
    job_id,
    movie_path,
    job_dir,
    recap_style
):

    try:

        # -------------------------------------------------
        # AUDIO
        # -------------------------------------------------

        update_job(
            job_id,
            status="processing"
        )

        update_pipeline(
            job_id,
            "audio_extraction",
            "processing"
        )


        audio_path = os.path.join(
            job_dir,
            "movie_audio.mp3"
        )


        extract_audio(
            movie_path,
            audio_path
        )


        update_pipeline(
            job_id,
            "audio_extraction",
            "completed"
        )


        # -------------------------------------------------
        # TRANSCRIPTION
        # -------------------------------------------------

        update_pipeline(
            job_id,
            "transcription",
            "processing"
        )


        transcript = transcribe_audio(
            audio_path
        )


        transcript_path = os.path.join(
            job_dir,
            "transcript.txt"
        )


        with open(
            transcript_path,
            "w",
            encoding="utf-8"
        ) as f:

            f.write(
                transcript
            )


        update_pipeline(
            job_id,
            "transcription",
            "completed"
        )


        # -------------------------------------------------
        # BURMESE RECAP
        # -------------------------------------------------

        update_pipeline(
            job_id,
            "recap_script",
            "processing"
        )


        recap = generate_burmese_recap(
            transcript,
            recap_style
        )


        recap_path = os.path.join(
            job_dir,
            "burmese_recap.txt"
        )


        with open(
            recap_path,
            "w",
            encoding="utf-8"
        ) as f:

            f.write(
                recap
            )


        update_pipeline(
            job_id,
            "recap_script",
            "completed"
        )


        # -------------------------------------------------
        # NEXT STEPS
        # -------------------------------------------------

        update_pipeline(
            job_id,
            "narration",
            "pending"
        )

        update_pipeline(
            job_id,
            "scene_selection",
            "pending"
        )

        update_pipeline(
            job_id,
            "subtitle",
            "pending"
        )

        update_pipeline(
            job_id,
            "video_render",
            "pending"
        )

        update_pipeline(
            job_id,
            "thumbnail",
            "pending"
        )

        update_pipeline(
            job_id,
            "final_output",
            "pending"
        )


        update_job(
            job_id,
            status="completed",
            message="Transcription နှင့် Burmese Recap Script ပြီးပါပြီ။",
            files={
                "transcript":
                    "transcript.txt",

                "burmese_recap":
                    "burmese_recap.txt"
            }
        )


    except Exception as e:

        update_job(
            job_id,
            status="error",
            error=str(e)
        )


# =========================================================
# HOME
# =========================================================

@app.route("/")
def home():

    return jsonify({

        "status": "ok",

        "message":
            "MovieRecap MM AI backend is running",

        "version":
            "3.0",

        "openai":
            bool(OPENAI_API_KEY)

    })


# =========================================================
# HEALTH
# =========================================================

@app.route("/health")
def health():

    return jsonify({

        "status": "healthy",

        "service":
            "MovieRecap MM AI",

        "version":
            "3.0"

    })


# =========================================================
# PROCESS
# =========================================================

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


        # -------------------------------------------------
        # SOURCE CHECK
        # -------------------------------------------------

        if (
            not movie_file
            or not movie_file.filename
        ) and not movie_url:

            return jsonify({

                "status": "error",

                "message":
                    "Movie file သို့မဟုတ် authorized video URL ထည့်ပါ။"

            }), 400


        # -------------------------------------------------
        # API KEY CHECK
        # -------------------------------------------------

        if client is None:

            return jsonify({

                "status": "error",

                "message":
                    "OPENAI_API_KEY မထည့်ရသေးပါ။ Render → Environment → OPENAI_API_KEY ကို ထည့်ပါ။"

            }), 503


        # -------------------------------------------------
        # CREATE JOB
        # -------------------------------------------------

        job_id, job_dir = create_job()


        movie_path = None


        # -------------------------------------------------
        # MOVIE FILE
        # -------------------------------------------------

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
                        "MP4, MOV, MKV, AVI, WEBM, M4V video ကို အသုံးပြုပါ။"

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


        # -------------------------------------------------
        # VOICE SAMPLE
        # -------------------------------------------------

        voice_saved = False

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
                        "Supported audio format မဟုတ်ပါ။"

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


        # -------------------------------------------------
        # JOB
        # -------------------------------------------------

        job_data = {

            "job_id":
                job_id,

            "status":
                "queued",

            "created_at":
                int(time.time()),

            "movie": {

                "uploaded":
                    bool(movie_path),

                "filename":
                    movie_file.filename
                    if movie_path
                    else None,

                "url":
                    movie_url
                    if movie_url
                    else None

            },

            "voice": {

                "uploaded":
                    voice_saved

            },

            "options": {

                "recap_style":
                    recap_style,

                "video_format":
                    video_format

            },

            "pipeline": {

                "upload":
                    "completed",

                "audio_extraction":
                    "queued",

                "transcription":
                    "queued",

                "recap_script":
                    "queued",

                "narration":
                    "pending",

                "scene_selection":
                    "pending",

                "subtitle":
                    "pending",

                "video_render":
                    "pending",

                "thumbnail":
                    "pending",

                "final_output":
                    "pending"

            }

        }


        save_job(
            job_id,
            job_data
        )


        # -------------------------------------------------
        # START BACKGROUND JOB
        # -------------------------------------------------

        if movie_path:

            worker = threading.Thread(

                target=run_pipeline,

                args=(

                    job_id,

                    movie_path,

                    job_dir,

                    recap_style

                ),

                daemon=True

            )

            worker.start()


        else:

            update_job(
                job_id,
                status="waiting_for_video_download",
                message=
                    "URL processing will be added in the next pipeline stage."
            )


        # -------------------------------------------------
        # RESPONSE
        # -------------------------------------------------

        return jsonify({

            "status":
                "queued",

            "message":
                "Movie ကို လက်ခံပြီး AI processing စတင်ပါပြီ။",

            "job_id":
                job_id,

            "status_url":
                "/status/" + job_id,

            "next":
                "Audio → Chinese transcription → Burmese recap"

        }), 202


    except Exception as e:

        return jsonify({

            "status":
                "error",

            "message":
                str(e)

        }), 500


# =========================================================
# JOB STATUS
# =========================================================

@app.route(
    "/status/<job_id>",
    methods=["GET"]
)
def job_status(job_id):

    job = load_job(
        job_id
    )


    if job is None:

        return jsonify({

            "status":
                "error",

            "message":
                "Job မတွေ့ပါ။"

        }), 404


    return jsonify(
        job
    )


# =========================================================
# PIPELINE
# =========================================================

@app.route(
    "/pipeline",
    methods=["GET"]
)
def pipeline():

    return jsonify({

        "status":
            "ok",

        "pipeline": [

            {
                "step": 1,
                "name": "Movie Upload",
                "status": "ready"
            },

            {
                "step": 2,
                "name": "Audio Extraction",
                "status": "implemented"
            },

            {
                "step": 3,
                "name": "Chinese Speech Transcription",
                "status": "implemented"
            },

            {
                "step": 4,
                "name": "Burmese Recap Script",
                "status": "implemented"
            },

            {
                "step": 5,
                "name": "Burmese Narration",
                "status": "next"
            },

            {
                "step": 6,
                "name": "AI Scene Selection",
                "status": "next"
            },

            {
                "step": 7,
                "name": "Subtitle Generation",
                "status": "next"
            },

            {
                "step": 8,
                "name": "Video Rendering",
                "status": "next"
            },

            {
                "step": 9,
                "name": "Thumbnail",
                "status": "next"
            },

            {
                "step": 10,
                "name": "Final Download",
                "status": "next"
            }

        ]

    })


# =========================================================
# SERVER
# =========================================================

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
