from fastapi import FastAPI
from fastapi.responses import FileResponse
import subprocess
import uuid
import os
import glob
import threading
import re
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # allow all (for development)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
os.makedirs("downloads", exist_ok=True)

jobs = {}

# -------------------------------
# PARSE PROGRESS
# -------------------------------
def parse_progress(line, job_id):
    try:
        percent_match = re.search(r'(\d+\.?\d*)%', line)
        speed_match = re.search(r'at\s+([\d\.]+\w+/s)', line)
        eta_match = re.search(r'ETA\s+([\d:]+)', line)

        if percent_match:
            jobs[job_id]["progress"] = float(percent_match.group(1))

        if speed_match:
            jobs[job_id]["speed"] = speed_match.group(1)

        if eta_match:
            jobs[job_id]["eta"] = eta_match.group(1)
    except:
        pass


# -------------------------------
# PROCESS VIDEO
# -------------------------------
def process_video(job_id, url, start, end):
    video_id = job_id

    input_template = f"downloads/{video_id}.%(ext)s"
    output_file = f"downloads/{video_id}_clip.mp4"

    try:
        jobs[job_id]["status"] = "downloading"
        jobs[job_id]["progress"] = 0

        process = subprocess.Popen(
            f'yt-dlp --cookies cookies.txt -f "bestvideo[ext=mp4]+bestaudio[ext=m4a]/mp4" '
            f'--merge-output-format mp4 -o "{input_template}" "{url}"',
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )

        for line in process.stdout:
            print(line.strip())
            parse_progress(line, job_id)

        process.wait()

        files = glob.glob(f"downloads/{video_id}*")
        if not files:
            jobs[job_id]["status"] = "error"
            jobs[job_id]["message"] = "Download failed"
            return

        input_file = files[0]

        # TRIM
        jobs[job_id]["status"] = "trimming"
        jobs[job_id]["progress"] = 95

        subprocess.run(
            f'ffmpeg -i "{input_file}" -ss {start} -to {end} -c copy "{output_file}"',
            shell=True
        )

        if not os.path.exists(output_file):
            jobs[job_id]["status"] = "error"
            jobs[job_id]["message"] = "Trimming failed"
            return

        jobs[job_id]["progress"] = 100
        jobs[job_id]["status"] = "done"
        jobs[job_id]["file"] = output_file

    except Exception as e:
        jobs[job_id]["status"] = "error"
        jobs[job_id]["message"] = str(e)


# -------------------------------
# START JOB
# -------------------------------
@app.get("/start")
def start_clip(url: str, start: str, end: str):
    job_id = str(uuid.uuid4())

    jobs[job_id] = {
        "status": "starting",
        "progress": 0,
        "speed": "",
        "eta": ""
    }

    threading.Thread(target=process_video, args=(job_id, url, start, end)).start()

    return {"job_id": job_id}


# -------------------------------
# STATUS
# -------------------------------
@app.get("/status")
def get_status(job_id: str):
    return jobs.get(job_id, {"error": "Invalid job_id"})

@app.get("/preview")
def preview(url: str):
    return {"preview_url": url}

# -------------------------------
# DOWNLOAD
# -------------------------------
@app.get("/download")
def download_file(job_id: str):
    job = jobs.get(job_id)

    if not job or job.get("status") != "done":
        return {"error": "File not ready"}

    return FileResponse(job["file"], media_type="video/mp4", filename="clip.mp4")