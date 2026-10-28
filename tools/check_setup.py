"""Checks that everything Otto needs is in place - without using any of your free voice answers.

Run from the project folder:  python tools\\check_setup.py
"""
import sys, os
from pathlib import Path
from importlib.metadata import version, PackageNotFoundError
sys.stdout.reconfigure(encoding="utf-8")

print("=== 1. Python ===")
ok = sys.version_info[:2] == (3, 11)
print(f"Python {sys.version.split()[0]}  {'OK' if ok else 'WARNING: Python 3.11 is recommended'}")
print("venv: " + ("OK" if sys.prefix != sys.base_prefix else "NOT ACTIVE -> run .venv\\Scripts\\activate"))

print("\n=== 2. Libraries ===")
for p in ["groq", "google-genai", "openwakeword", "edge-tts", "python-dotenv", "numpy", "scipy",
          "sounddevice", "soundfile", "miniaudio", "webrtcvad-wheels", "tzdata",
          "arabic-reshaper", "python-bidi"]:
    try:
        print(f"OK       {p} {version(p)}")
    except PackageNotFoundError:
        print(f"MISSING  {p}  -> run: pip install -r requirements.txt")

print("\n=== 3. Files ===")
for f in [".env", "models/hey_otto.onnx", "system_prompt.txt", "otto.py", "listen.py", "voice.py", "wake.py"]:
    p = Path(f)
    print(f"OK       {f}" if p.exists() else f"MISSING  {f}")

print("\n=== 4. Keys in .env (hidden) ===")
from dotenv import load_dotenv
load_dotenv()
g = os.getenv("GROQ_API_KEY", "").strip()
m = os.getenv("GEMINI_API_KEY", "").strip()
print("GROQ_API_KEY:   " + (f"found ({len(g)} chars)" if g else "MISSING"))
print("GEMINI_API_KEY: " + (f"found ({len(m)} chars)" if m else "MISSING (Otto will use the backup voice only)"))

print("\n=== 5. Do the keys work? (no quota used) ===")
try:
    from groq import Groq
    ids = [x.id for x in Groq(api_key=g).models.list().data]
    print("Groq:   OK")
    for need in ["whisper-large-v3", "openai/gpt-oss-120b"]:
        print(f"        {need}: {'available' if need in ids else 'NOT FOUND'}")
except Exception as e:
    print(f"Groq:   FAILED -> {type(e).__name__}: {str(e)[:150]}")
if m:
    try:
        from google import genai
        gem = genai.Client(api_key=m)
        names = [x.name for x in gem.models.list()]
        print(f"Gemini: OK - gemini-3.8-flash-tts " + ("available" if any("3.8-flash-tts" in n for n in names) else "not listed (may still work)"))
    except Exception as e:
        print(f"Gemini: FAILED -> {type(e).__name__}: {str(e)[:150]}")

print("\n=== 6. Audio ===")
import sounddevice as sd
try:
    print(f"Default mic:     {sd.query_devices(kind='input')['name']}")
    print(f"Default speaker: {sd.query_devices(kind='output')['name']}")
except Exception as e:
    print(f"Audio devices: error -> {e}")
print(f"INPUT_DEVICE in .env: {os.getenv('INPUT_DEVICE') or '(empty -> default mic)'}")
