#!/usr/bin/env python3
"""
DCC Leaderboard server — Jeff's 47th
Run: python3 server.py
Then open http://<your-mac-ip>:5500 on any device on the same WiFi.
"""
import json, os, time
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

HERE       = Path(__file__).parent
STATE_FILE = HERE / "state.json"
IMAGES_DIR = HERE / "images"
AUDIO_DIR  = HERE / "audio"
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".ogg"}

DEFAULT_STATE = {
    "crawlers": [],
    "settings": {
        "title1": "PARTY-GOER RANKINGS",
        "title2": "JEFF'S 47TH",
        "subtitle": "Floor 47 · Dungeons & Degeneracy",
        "bannerImage":      None,
        "celebrationImage": None,
        "celebrationAudio": None,
    },
    "lastAction": None,
    "celebration": None,  # {id, image, audio} consumed by display screen
}

def load_state():
    if STATE_FILE.exists():
        try:
            s = json.loads(STATE_FILE.read_text())
            s.setdefault("celebration", None)
            s["settings"].setdefault("bannerImage",      None)
            s["settings"].setdefault("celebrationImage", None)
            s["settings"].setdefault("celebrationAudio", None)
            return s
        except Exception:
            pass
    return json.loads(json.dumps(DEFAULT_STATE))

def save_state(state):
    STATE_FILE.write_text(json.dumps(state, indent=2))

def list_files(directory: Path, exts: set):
    if not directory.exists():
        return []
    return sorted(f.name for f in directory.iterdir() if f.suffix.lower() in exts)

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

IMAGES_DIR.mkdir(exist_ok=True)
AUDIO_DIR.mkdir(exist_ok=True)
app.mount("/images", StaticFiles(directory=str(IMAGES_DIR)), name="images")
app.mount("/audio",  StaticFiles(directory=str(AUDIO_DIR)),  name="audio")

# ── Models ───────────────────────────────────────────────────────────────────

class AddCrawlerReq(BaseModel):
    name: str

class AwardPointsReq(BaseModel):
    delta: int

class SettingsReq(BaseModel):
    title1:            Optional[str] = None
    title2:            Optional[str] = None
    subtitle:          Optional[str] = None
    bannerImage:       Optional[str] = None
    celebrationImage:  Optional[str] = None
    celebrationAudio:  Optional[str] = None

class ConfirmReq(BaseModel):
    confirm: str

# ── API ──────────────────────────────────────────────────────────────────────

@app.get("/api/state")
def get_state():
    return load_state()

@app.get("/api/images")
def get_images():
    return {"images": list_files(IMAGES_DIR, IMAGE_EXTS)}

@app.get("/api/audio")
def get_audio():
    return {"audio": list_files(AUDIO_DIR, AUDIO_EXTS)}

@app.post("/api/crawlers")
def add_crawler(req: AddCrawlerReq):
    name = req.name.strip()
    if not name:
        raise HTTPException(400, "Name required")
    state = load_state()
    crawler_id = f"{int(time.time()*1000)}-{os.urandom(3).hex()}"
    state["crawlers"].append({"id": crawler_id, "name": name, "points": 0})
    save_state(state)
    return state

@app.delete("/api/crawlers/{crawler_id}")
def remove_crawler(crawler_id: str):
    state = load_state()
    state["crawlers"] = [c for c in state["crawlers"] if c["id"] != crawler_id]
    save_state(state)
    return state

@app.post("/api/crawlers/{crawler_id}/points")
def award_points(crawler_id: str, req: AwardPointsReq):
    state = load_state()
    crawler = next((c for c in state["crawlers"] if c["id"] == crawler_id), None)
    if not crawler:
        raise HTTPException(404, "Crawler not found")
    prev = crawler["points"]
    crawler["points"] += req.delta
    state["lastAction"] = {"id": crawler_id, "name": crawler["name"], "prevPoints": prev, "delta": req.delta}
    img   = state["settings"].get("celebrationImage")
    audio = state["settings"].get("celebrationAudio")
    if img or audio:
        state["celebration"] = {"id": os.urandom(4).hex(), "image": img, "audio": audio}
    else:
        state["celebration"] = None
    save_state(state)
    return state

@app.post("/api/undo")
def undo():
    state = load_state()
    last = state.get("lastAction")
    if not last:
        raise HTTPException(400, "Nothing to undo")
    crawler = next((c for c in state["crawlers"] if c["id"] == last["id"]), None)
    if crawler:
        crawler["points"] = last["prevPoints"]
    state["lastAction"] = None
    save_state(state)
    return state

@app.post("/api/settings")
def update_settings(req: SettingsReq):
    state = load_state()
    if req.title1           is not None: state["settings"]["title1"]            = req.title1
    if req.title2           is not None: state["settings"]["title2"]            = req.title2
    if req.subtitle         is not None: state["settings"]["subtitle"]          = req.subtitle
    if req.bannerImage      is not None: state["settings"]["bannerImage"]       = req.bannerImage      or None
    if req.celebrationImage is not None: state["settings"]["celebrationImage"]  = req.celebrationImage or None
    if req.celebrationAudio is not None: state["settings"]["celebrationAudio"]  = req.celebrationAudio or None
    save_state(state)
    return state

@app.post("/api/clear-celebration")
def clear_celebration():
    state = load_state()
    state["celebration"] = None
    save_state(state)
    return {"ok": True}

@app.post("/api/reset-points")
def reset_points(req: ConfirmReq):
    if req.confirm != "RESET":
        raise HTTPException(400, "Confirmation required")
    state = load_state()
    for c in state["crawlers"]:
        c["points"] = 0
    state["lastAction"] = None
    save_state(state)
    return state

@app.post("/api/clear-all")
def clear_all(req: ConfirmReq):
    if req.confirm != "RESET":
        raise HTTPException(400, "Confirmation required")
    state = load_state()
    state["crawlers"] = []
    state["lastAction"] = None
    save_state(state)
    return state

# ── Static ───────────────────────────────────────────────────────────────────

ICON_CACHE = "public, max-age=86400"

@app.get("/favicon.ico")
def favicon():
    return FileResponse(HERE / "favicon.ico", media_type="image/x-icon", headers={"Cache-Control": ICON_CACHE})

@app.get("/apple-touch-icon.png")
@app.get("/apple-touch-icon-precomposed.png")
@app.get("/apple-touch-icon-120x120.png")
@app.get("/apple-touch-icon-120x120-precomposed.png")
def apple_touch_icon():
    return FileResponse(HERE / "apple-touch-icon.png", media_type="image/png", headers={"Cache-Control": ICON_CACHE})

@app.get("/")
def root():
    return FileResponse(HERE / "index.html", headers={"Cache-Control": "no-cache, no-store, must-revalidate"})

if __name__ == "__main__":
    import subprocess
    try:
        local_ip = subprocess.check_output(["ipconfig", "getifaddr", "en0"], text=True).strip()
        if not local_ip:
            raise ValueError
    except Exception:
        try:
            local_ip = subprocess.check_output(["ipconfig", "getifaddr", "en1"], text=True).strip() or "unknown"
        except Exception:
            local_ip = "unknown"
    print(f"\n{'='*50}")
    print(f"  DCC LEADERBOARD — Jeff's 47th")
    print(f"{'='*50}")
    print(f"  Local:   http://localhost:5500")
    print(f"  Network: http://{local_ip}:5500")
    print(f"\n  TV Display: http://{local_ip}:5500?screen=display")
    print(f"  iPhone Admin: http://{local_ip}:5500?screen=admin")
    print(f"{'='*50}\n")
    uvicorn.run(app, host="0.0.0.0", port=5500)
