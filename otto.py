"""Otto Cloud - a free, fast, Egyptian-Arabic voice assistant.

    "Hey Otto" -> greeting -> you talk -> Whisper -> gpt-oss-120b -> Bodi speaks -> follow-ups -> sleep

Run:  start_otto.bat   (or:  python otto.py)
"""
import os, sys, time, datetime
from dotenv import load_dotenv
from groq import Groq

load_dotenv()
if not os.getenv("GROQ_API_KEY", "").strip():
    sys.exit("GROQ_API_KEY is missing. Copy .env.example to .env and add your keys.")

import voice
from listen import record_utterance, transcribe, calibrate, show
from wake import wait_for_wake

groq = Groq(api_key=os.getenv("GROQ_API_KEY"))

PROMPT = open("system_prompt.txt", encoding="utf-8").read()
REMINDER = ("(رد بالعامية المصرية في جملة أو اتنين بس. قول بس المعلومات اللي إنت متأكد منها، "
            "ولو مش متأكد قول \"والله مش متأكد\". لو السؤال غريب أو شكله اتسمع غلط، اطلب منه يعيده.)")
FIRST_WAIT = 10         # seconds to wait for your question after the greeting
FOLLOWUP_WAIT = 12      # seconds to wait for a follow-up before sleeping
history = []
log = open("otto_log.txt", "a", encoding="utf-8")


def think(text):
    now = datetime.datetime.now()
    part = "الصبح" if now.hour < 12 else ("بعد الضهر" if now.hour < 18 else "بالليل")
    system = PROMPT + f"\n\nالنهارده: {now:%d-%m-%Y}، والساعة دلوقتي {now.hour % 12 or 12}:{now.minute:02d} {part} (قولها زي ما هي من غير حسابات)."
    messages = ([{"role": "system", "content": system}] + history[-8:]
                + [{"role": "user", "content": f"{text}\n\n{REMINDER}"}])
    r = groq.chat.completions.create(
        model="openai/gpt-oss-120b", messages=messages, temperature=0.3,
        max_completion_tokens=800, reasoning_effort="medium", include_reasoning=False)
    reply = (r.choices[0].message.content or "").strip()
    if not reply:
        reply = "معلش، ممكن تعيد السؤال تاني؟"
    history.extend([{"role": "user", "content": text}, {"role": "assistant", "content": reply}])
    return reply


def conversation():
    """Greeting, then keep answering until you stop asking."""
    history.clear()
    voice.greet()
    wait = FIRST_WAIT
    while True:
        print("\nListening...")
        pcm = record_utterance(max_wait=wait)
        if pcm is None:
            return
        wait = FOLLOWUP_WAIT
        t0 = time.time()
        text = transcribe(pcm)
        t1 = time.time()
        if not text:
            print("   (didn't catch that)")
            continue
        print(f"You:  {show(text)}")
        try:
            reply = think(text)
        except Exception as e:
            print(f"   (brain error: {type(e).__name__}: {str(e)[:150]})")
            reply = "معلش، حصلت مشكلة صغيرة. جرب تاني كمان شوية."
        t2 = time.time()
        print(f"Otto: {show(reply)}")
        voice.speak(reply)
        delay = voice.first_sound - t0
        print(f"   heard {t1 - t0:.1f}s | thought {t2 - t1:.1f}s | voice started {delay:.1f}s after you stopped")
        log.write(f"You:  {text}\nOtto: {reply}\n   heard {t1 - t0:.1f}s | thought {t2 - t1:.1f}s | voice after {delay:.1f}s\n")
        log.flush()


if __name__ == "__main__":
    print("=" * 40)
    print("   OTTO CLOUD")
    print("=" * 40)
    print(f"Bodi answers left today: {voice.bodi_left()}/{voice.RPD}")
    print("Measuring room noise - stay quiet for 1 second...")
    calibrate()
    try:
        while True:
            print("\nSay 'Hey Otto'... (Ctrl+C to quit)")
            print(f"   (woke up - score {wait_for_wake():.2f})")
            conversation()
            print("(no follow-up - Otto went to sleep)")
            print(f"Bodi answers left today: {voice.bodi_left()}/{voice.RPD}")
    except KeyboardInterrupt:
        print("\nBye!")
