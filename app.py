import os
import json
import uuid
import shutil
import subprocess
import threading
from pathlib import Path

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from groq import Groq

app = Flask(__name__)
CORS(app)

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
JOBS_DIR = BASE_DIR / "jobs"

UPLOAD_DIR.mkdir(exist_ok=True)
JOBS_DIR.mkdir(exist_ok=True)

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

if GROQ_API_KEY:
    groq_client = Groq(api_key=GROQ_API_KEY)
else:
    groq_client = None


def get_ffmpeg():
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


FFMPEG = get_ffmpeg()


def update_job(job_dir, **changes):
    job_file = job_dir / "job.json"

    try:
        data = json.loads(job_file.read_text(encoding="utf-8"))
    except Exception:
        data = {}

    data.update(changes)

    job_file.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


def create_job():
    job_id = str(uuid.uuid4())
    job_dir = JOBS_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    job = {
        "job_id": job_id,
        "status": "queued",
        "progress": 0,
        "current_step": "Waiting",
        "error": None
    }

    (job_dir / "job.json").write_text(
        json.dumps(job, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    return job_id, job_dir


def extract_audio(movie_path, audio_path):
    command = [
        FFMPEG,
        "-y",
        "-i",
        str(movie_path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-c:a",
        "libmp3lame",
        "-b:a",
        "48k",
        str(audio_path)
    ]

    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    if result.returncode != 0:
        raise RuntimeError(
            "FFmpeg audio extraction failed:\n" + result.stderr[-3000:]
        )


def split_audio(audio_path, chunk_dir, seconds=300):
    chunk_dir.mkdir(exist_ok=True)

    pattern = chunk_dir / "chunk_%04d.mp3"

    command = [
        FFMPEG,
        "-y",
        "-i",
        str(audio_path),
        "-f",
        "segment",
        "-segment_time",
        str(seconds),
        "-reset_timestamps",
        "1",
        "-c",
        "copy",
        str(pattern)
    ]

    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    if result.returncode != 0:
        raise RuntimeError(
            "Audio chunking failed:\n" + result.stderr[-3000:]
        )

    return sorted(chunk_dir.glob("chunk_*.mp3"))


def transcribe_chunk(chunk_path):
    if not groq_client:
        raise RuntimeError(
            "GROQ_API_KEY မတွေ့ပါ။ Render Environment ထဲမှာ "
            "GROQ_API_KEY ထည့်ပေးပါ။"
        )

    with open(chunk_path, "rb") as audio_file:
        result = groq_client.audio.transcriptions.create(
            file=(chunk_path.name, audio_file.read()),
            model="whisper-large-v3-turbo",
            language="zh",
            response_format="text"
        )

    return str(result)


def generate_burmese_recap(transcript, style="detailed"):
    if not groq_client:
        raise RuntimeError(
            "GROQ_API_KEY မတွေ့ပါ။"
        )

    prompt = f"""
You are a professional Burmese movie recap writer.

The following transcript is Chinese movie dialogue.

Write a natural Burmese movie recap script.

Style: {style}

Requirements:
- Write entirely in Burmese.
- Explain the story clearly.
- Keep important characters and events.
- Make it suitable for Burmese YouTube movie recap narration.
- Do not invent events that are not supported by the transcript.
- Do not translate every sentence literally.
- Turn the dialogue into a coherent story.
- Use natural spoken Burmese.
- Organize the story from beginning to end.

Chinese transcript:
{transcript}
"""

    response = groq_client.chat.completions.create(
        model="openai/gpt-oss-20b",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are an expert Burmese movie recap writer. "
                    "Always answer in natural Burmese."
                )
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        temperature=0.4,
        max_tokens=6000
    )

    return response.choices[0].message.content


def process_job(job_id, movie_path, style):
    job_dir = JOBS_DIR / job_id

    try:
        update_job(
            job_dir,
            status="processing",
            progress=5,
            current_step="Audio Extraction"
        )

        audio_path = job_dir / "audio.mp3"
        extract_audio(movie_path, audio_path)

        update_job(
            job_dir,
            progress=15,
            current_step="Audio Chunking"
        )

        chunk_dir = job_dir / "chunks"
        chunks = split_audio(audio_path, chunk_dir, seconds=300)

        if not chunks:
            raise RuntimeError("No audio chunks were created.")

        update_job(
            job_dir,
            progress=20,
            current_step="Chinese Speech → Text",
            total_chunks=len(chunks)
        )

        transcripts = []

        for index, chunk in enumerate(chunks):
            text = transcribe_chunk(chunk)

            if text.strip():
                transcripts.append(
                    f"[Chunk {index + 1}]\n{text.strip()}"
                )

            progress = 20 + int(
                ((index + 1) / len(chunks)) * 45
            )

            update_job(
                job_dir,
                progress=progress,
                current_step=(
                    f"Chinese Speech → Text "
                    f"({index + 1}/{len(chunks)})"
                )
            )

        full_transcript = "\n\n".join(transcripts)

        transcript_path = job_dir / "transcript.txt"
        transcript_path.write_text(
            full_transcript,
            encoding="utf-8"
        )

        update_job(
            job_dir,
            progress=70,
            current_step="Burmese Recap Script"
        )

        recap = generate_burmese_recap(
            full_transcript,
            style
        )

        recap_path = job_dir / "burmese_recap.txt"
        recap_path.write_text(
            recap,
            encoding="utf-8"
        )

        update_job(
            job_dir,
            progress=80,
            current_step="Preparing Results"
        )

        update_job(
            job_dir,
            status="completed",
            progress=100,
            current_step="Completed"
        )

    except Exception as exc:
        update_job(
            job_dir,
            status="error",
            progress=0,
            current_step="Error",
            error=str(exc)
        )


@app.route("/")
def home():
    return jsonify({
        "message": "MovieRecap MM AI backend is running",
        "status": "ok",
        "version": "5.0-free",
        "groq": bool(GROQ_API_KEY),
        "openai": False
    })


@app.route("/health")
def health():
    return jsonify({
        "status": "ok",
        "groq": bool(GROQ_API_KEY),
        "openai": False
    })


@app.route("/process", methods=["POST"])
def process():
    movie = request.files.get("movie")
    style = request.form.get("style", "detailed")
    video_format = request.form.get("video_format", "youtube")
    voice_sample = request.files.get("voice_sample")

    if not movie:
        return jsonify({
            "error": "Movie file မတွေ့ပါ။"
        }), 400

    if not GROQ_API_KEY:
        return jsonify({
            "error": (
                "GROQ_API_KEY မရှိသေးပါ။ "
                "Render Environment ထဲမှာ Free Groq API key ထည့်ပါ။"
            )
        }), 500

    job_id, job_dir = create_job()

    movie_path = job_dir / movie.filename
    movie.save(movie_path)

    if voice_sample:
        voice_path = job_dir / voice_sample.filename
        voice_sample.save(voice_path)

    update_job(
        job_dir,
        movie=movie.filename,
        style=style,
        video_format=video_format,
        voice_sample=bool(voice_sample)
    )

    worker = threading.Thread(
        target=process_job,
        args=(job_id, movie_path, style),
        daemon=True
    )

    worker.start()

    return jsonify({
        "status": "accepted",
        "job_id": job_id,
        "message": "Free AI processing started."
    })


@app.route("/status/<job_id>")
def status(job_id):
    job_dir = JOBS_DIR / job_id
    job_file = job_dir / "job.json"

    if not job_file.exists():
        return jsonify({
            "error": "Job not found"
        }), 404

    data = json.loads(
        job_file.read_text(encoding="utf-8")
    )

    return jsonify(data)


@app.route("/jobs/<job_id>/<filename>")
def job_file(job_id, filename):
    job_dir = JOBS_DIR / job_id

    if not job_dir.exists():
        return jsonify({
            "error": "Job not found"
        }), 404

    return send_from_directory(
        job_dir,
        filename
    )


@app.route("/pipeline")
def pipeline():
    return jsonify({
        "version": "5.0-free",
        "steps": [
            "Audio Extraction",
            "Audio Chunking",
            "Chinese Speech → Text",
            "Burmese Recap Script",
            "Burmese Narration",
            "AI Scene Selection",
            "Burmese Subtitles",
            "Video Rendering",
            "Thumbnail"
        ],
        "ai_provider": "Groq Free Tier"
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(
        host="0.0.0.0",
        port=port
    )
