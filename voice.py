"""Otto's mouth.

Main voice:   Gemini 3.8 Flash TTS, voice "Bodi" (Egyptian Arabic), streamed while it is generated
Backup voice: Microsoft Edge "Shakir" (ar-EG), used automatically when Bodi's free limit is used up

Otto sends ONE Gemini request per answer and counts them in quota.json,
so it never wastes requests on errors. The greeting is made once and saved.
"""
import os, re, json, time, base64, asyncio
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import numpy as np
import sounddevice as sd
import soundfile as sf
import miniaudio
import edge_tts
from dotenv import load_dotenv

load_dotenv()
_key = os.getenv("GEMINI_API_KEY", "").strip()
gem = None
if _key:
    from google import genai
    gem = genai.Client(api_key=_key)                      # kept open for the whole run

VOICE = os.getenv("GEMINI_VOICE", "Bodi")
MODEL = os.getenv("GEMINI_TTS_MODEL", "gemini-3.8-flash-tts")
EDGE_VOICE = os.getenv("EDGE_VOICE", "ar-EG-ShakirNeural")   # backup: male Egyptian voice, like Bodi
RPD = int(os.getenv("GEMINI_TTS_RPD", "10"))              # free plan: 10 a day
RPM = int(os.getenv("GEMINI_TTS_RPM", "3"))               # free plan: 3 a minute
QUOTA_FILE = Path("quota.json")
GREETING_FILE = Path("greeting.wav")
GREETING = "أيوه، أنا سامعك. أقدر أساعدك في إيه؟"
PACIFIC = ZoneInfo("America/Los_Angeles")                 # Google's daily limit resets at midnight here
first_sound = 0.0                                         # when the last answer started playing


# ---------- free-limit counter ----------
def _load():
    today = datetime.now(PACIFIC).date().isoformat()
    try:
        q = json.loads(QUOTA_FILE.read_text())
    except Exception:
        q = {}
    if q.get("date") != today:
        q = {"date": today, "used": 0, "recent": [], "blocked_until": 0}
    return q


def _save(q):
    QUOTA_FILE.write_text(json.dumps(q))


def bodi_left():
    return max(0, RPD - _load()["used"]) if gem else 0


def _can_use_bodi():
    if gem is None:
        return False
    q, now = _load(), time.time()
    if now < q["blocked_until"] or q["used"] >= RPD:
        return False
    return len([t for t in q["recent"] if now - t < 60]) < RPM


def _count_bodi():
    q, now = _load(), time.time()
    q["used"] += 1
    q["recent"] = [t for t in q["recent"] if now - t < 60] + [now]
    _save(q)


def _block(daily):
    q = _load()
    if daily:
        q["used"] = RPD
    else:
        q["blocked_until"] = time.time() + 65
    _save(q)


# ---------- the two voices ----------
def clean(text):
    """Removes things a voice would read badly: links, markdown symbols, emojis."""
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"[*_#`>|~\[\]{}]", "", text)
    text = re.sub(r"[\U0001F000-\U0001FAFF☀-➿]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _speak_bodi(text):
    """One Gemini request; plays the audio while it is still arriving. Returns the audio."""
    global first_sound
    stream = gem.interactions.create(
        model=MODEL,
        input=[{"type": "user_input", "content": [{"type": "text", "text": text}]}],
        response_format={"type": "audio"},
        generation_config={"speech_config": [{"voice": VOICE, "language": "ar-EG"}]},
        stream=True,
    )
    player, carry, audio = None, b"", bytearray()
    try:
        for ev in stream:
            if getattr(ev, "event_type", "") != "step.delta":
                continue
            d = ev.delta
            if getattr(d, "type", "") == "audio" and getattr(d, "data", None):
                chunk = carry + base64.b64decode(d.data)
                even = len(chunk) // 2 * 2
                chunk, carry = chunk[:even], chunk[even:]
                if player is None:
                    player = sd.RawOutputStream(samplerate=24000, channels=1, dtype="int16")
                    player.start()
                    first_sound = time.time()
                player.write(chunk)
                audio += chunk
    finally:
        if player:
            player.stop()      # waits until the last bit has played
            player.close()
    if not audio:
        raise RuntimeError("Gemini returned no audio")
    return bytes(audio)


def _speak_edge(text):
    global first_sound

    async def run():
        mp3 = bytearray()
        async for c in edge_tts.Communicate(text, EDGE_VOICE).stream():
            if c["type"] == "audio":
                mp3 += c["data"]
        return bytes(mp3)

    dec = miniaudio.decode(asyncio.run(run()), output_format=miniaudio.SampleFormat.SIGNED16, nchannels=1)
    first_sound = time.time()
    sd.play(np.frombuffer(dec.samples, dtype=np.int16), dec.sample_rate)
    sd.wait()


def speak(text):
    """Bodi if there's quota left, otherwise the backup voice."""
    text = clean(text)
    if not text:
        return
    if _can_use_bodi():
        try:
            _count_bodi()
            _speak_bodi(text)
            print(f"   [Bodi - {bodi_left()} left today]")
            return
        except Exception as e:
            msg = str(e).lower()
            if "429" in msg or "resource_exhausted" in msg or "quota" in msg:
                _block(daily="day" in msg)
                print("   (Bodi's limit reached - using the backup voice)")
            else:
                print(f"   (Bodi failed: {type(e).__name__}: {str(e)[:200]} - using the backup voice)")
    _speak_edge(text)
    print("   [backup voice]")


def greet():
    """The greeting is made with Bodi ONCE and saved, so it never uses the daily limit again."""
    if GREETING_FILE.exists():
        data, rate = sf.read(GREETING_FILE, dtype="int16")
        sd.play(data, rate)
        sd.wait()
        return
    if _can_use_bodi():
        try:
            _count_bodi()
            audio = _speak_bodi(GREETING)
            sf.write(GREETING_FILE, np.frombuffer(audio, dtype=np.int16), 24000)
            print("   (greeting saved - it's free from now on)")
            return
        except Exception as e:
            print(f"   (couldn't make the greeting with Bodi: {str(e)[:200]})")
    _speak_edge(GREETING)


if __name__ == "__main__":
    # Quick test: plays (and saves) the greeting.
    print(f"Bodi answers left today: {bodi_left()}/{RPD}")
    greet()
    print(f"Bodi answers left today: {bodi_left()}/{RPD}")
