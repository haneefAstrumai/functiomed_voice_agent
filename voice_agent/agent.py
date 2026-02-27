"""
voice_agent/agent.py

Functiomed Voice Agent — Stateful LiveKit participant.

Architecture:
  - Connects to a LiveKit room as a Python participant
  - Receives text messages via DataChannel from the React browser
  - Processes messages through a state machine (BookingSession)
  - Uses existing RAG pipeline (chating.py) for FAQ answers
  - Saves confirmed bookings to SQLite (database/db.py)
  - Sends text responses back via DataChannel → browser speaks them via TTS
"""

import asyncio
import json
import logging
import re
import os
from datetime import date, timedelta
from typing import Optional        # ← ADD THIS LINE
from dotenv import load_dotenv

from livekit import agents, rtc

from voice_agent.state import BookingSession, ConversationState
# from state import BookingSession, ConversationState
from database.db import get_available_slots, book_appointment
from chating.chating import ask_llm

load_dotenv()


# ─────────────────────────────────────────────────────────────
# Logging setup
# ─────────────────────────────────────────────────────────────

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("functiomed-agent")


# ─────────────────────────────────────────────────────────────
# In-memory session store  { room_name → BookingSession }
# One BookingSession per active LiveKit room.
# ─────────────────────────────────────────────────────────────

_sessions: dict[str, BookingSession] = {}


def get_session(room_id: str) -> BookingSession:
    """Get existing session or create a new one for this room."""
    if room_id not in _sessions:
        _sessions[room_id] = BookingSession(room_id=room_id)
        logger.info(f"📋 New session created for room: {room_id}")
    return _sessions[room_id]


def clear_session(room_id: str):
    """Remove session when call ends."""
    _sessions.pop(room_id, None)
    logger.info(f"🗑️  Session cleared for room: {room_id}")


# ─────────────────────────────────────────────────────────────
# Services the clinic offers
# ─────────────────────────────────────────────────────────────

CANONICAL_SERVICES = [
    "physiotherapy",
    "massage",
    "osteopathy",
    "mental coaching",
    "ergotherapy",
    "acupuncture",
    "nutrition counseling",
]

# Maps spoken/typed variations → canonical service name
SERVICE_ALIASES = {
    # English
    "physio":            "physiotherapy",
    "physiotherapy":     "physiotherapy",
    "physical therapy":  "physiotherapy",
    "massage":           "massage",
    "osteo":             "osteopathy",
    "osteopathy":        "osteopathy",
    "mental":            "mental coaching",
    "mental coaching":   "mental coaching",
    "coaching":          "mental coaching",
    "ergo":              "ergotherapy",
    "ergotherapy":       "ergotherapy",
    "occupational":      "ergotherapy",
    "acupuncture":       "acupuncture",
    "nutrition":         "nutrition counseling",
    "dietitian":         "nutrition counseling",
    # German
    "physiotherapie":    "physiotherapy",
    "krankengymnastik":  "physiotherapy",
    "massage":           "massage",
    "osteopathie":       "osteopathy",
    "mentaltraining":    "mental coaching",
    "mental training":   "mental coaching",
    "ergotherapie":      "ergotherapy",
    "akupunktur":        "acupuncture",
    "ernährung":         "nutrition counseling",
    "ernährungsberatung":"nutrition counseling",
    "ernaehrung":        "nutrition counseling",
}


# ─────────────────────────────────────────────────────────────
# SECTION A — Language Detection
# ─────────────────────────────────────────────────────────────

def detect_language(text: str) -> str:
    """
    Detect whether the user is speaking German or English.
    Uses a simple keyword scoring approach.
    Returns "de" or "en".
    """
    german_words = [
        "ich", "bitte", "danke", "möchte", "mochte", "termin",
        "buchen", "hallo", "ja", "nein", "wie", "können", "konnen",
        "wann", "welche", "einen", "eine", "der", "die", "das",
        "für", "fur", "und", "oder", "mit", "von", "auf", "ist",
        "guten", "morgen", "tag", "abend",
    ]
    text_lower = text.lower()
    score = sum(1 for word in german_words if word in text_lower.split())
    return "de" if score >= 2 else "en"


# ─────────────────────────────────────────────────────────────
# SECTION B — Intent Detection
# ─────────────────────────────────────────────────────────────

def detect_intent(text: str) -> str:
    """
    Determine what the user wants to do.
    Returns: "book", "faq", "cancel", "go_back", or "unknown"
    """
    text_lower = text.lower()

    # Cancel intent
    cancel_words = ["cancel", "stop", "abort", "quit", "exit",
                    "abbrechen", "stopp", "aufhören", "beenden"]
    if any(w in text_lower for w in cancel_words):
        return "cancel"

    # Go back intent
    back_words = ["go back", "back", "previous", "zurück", "zuruck", "nochmal"]
    if any(w in text_lower for w in back_words):
        return "go_back"

    # Booking intent
    book_words = ["book", "appointment", "reserve", "schedule", "buchen",
                  "termin", "anmelden", "reservieren", "möchte einen",
                  "make an appointment", "book an appointment"]
    if any(w in text_lower for w in book_words):
        return "book"

    # If it matches a known service → probably booking
    if detect_service(text):
        return "book"

    return "faq"


# ─────────────────────────────────────────────────────────────
# SECTION C — Input Parsers
# ─────────────────────────────────────────────────────────────

def detect_service(text: str) -> Optional[str]:
    """
    Extract a canonical service name from natural language.
    Returns the service name or None if not found.
    """
    text_lower = text.lower().strip()
    for alias, canonical in SERVICE_ALIASES.items():
        if alias in text_lower:
            return canonical
    return None


def detect_date(text: str) -> str | None:
    """
    Parse a date from natural language text.
    Returns YYYY-MM-DD string or None if not parseable.
    """
    today     = date.today()
    text_low  = text.lower().strip()

    # Relative dates
    if any(w in text_low for w in ["today", "heute", "jetzt"]):
        return today.strftime("%Y-%m-%d")

    if any(w in text_low for w in ["tomorrow", "morgen"]):
        return (today + timedelta(days=1)).strftime("%Y-%m-%d")

    if "next week" in text_low or "nächste woche" in text_low:
        return (today + timedelta(weeks=1)).strftime("%Y-%m-%d")

    # Explicit ISO format: 2025-03-15
    m = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", text)
    if m:
        return m.group(1)

    # European format: 15.03.2025 or 15/03/2025 or 15-03-2025
    m = re.search(r"\b(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{4})\b", text)
    if m:
        day, month, year = m.group(1), m.group(2), m.group(3)
        return f"{year}-{month.zfill(2)}-{day.zfill(2)}"

    # Format without year: 15.03 or 15/03
    m = re.search(r"\b(\d{1,2})[.\-/](\d{1,2})\b", text)
    if m:
        day, month = m.group(1), m.group(2)
        year = str(today.year)
        return f"{year}-{month.zfill(2)}-{day.zfill(2)}"

    # Written month names (English)
    month_names = {
        "january": 1, "february": 2, "march": 3, "april": 4,
        "may": 5, "june": 6, "july": 7, "august": 8,
        "september": 9, "october": 10, "november": 11, "december": 12,
        # German
        "januar": 1, "februar": 2, "märz": 3, "maerz": 3,
        "mai": 5, "juni": 6, "juli": 7, "august": 8,
        "september": 9, "oktober": 10, "november": 11, "dezember": 12,
    }
    for month_name, month_num in month_names.items():
        m = re.search(rf"\b(\d{{1,2}})\s*\.?\s*{month_name}\b", text_low)
        if m:
            day = int(m.group(1))
            return f"{today.year}-{str(month_num).zfill(2)}-{str(day).zfill(2)}"

    return None


def detect_time(text: str, available_slots: list) -> str | None:
    """
    Match what the user says to an actual available slot time.
    Returns HH:MM string or None if no match.
    """
    if not available_slots:
        return None

    # Extract any number from the text
    m = re.search(r"\b(\d{1,2})(?::(\d{2}))?\b", text)
    if m:
        hour   = m.group(1).zfill(2)
        minute = m.group(2) if m.group(2) else "00"
        candidate = f"{hour}:{minute}"

        # Exact match first
        for slot in available_slots:
            if slot["time"] == candidate:
                return candidate

        # Hour-only match (e.g. user says "9" → matches "09:00")
        for slot in available_slots:
            if slot["time"].startswith(hour + ":"):
                return slot["time"]

    # Word-to-number mapping for spoken times
    word_to_hour = {
        "nine": 9, "ten": 10, "eleven": 11,
        "twelve": 12, "one": 13, "two": 14,
        "three": 15, "four": 16, "five": 17,
        "neun": 9, "zehn": 10, "elf": 11,
        "zwölf": 12, "dreizehn": 13,
    }
    text_lower = text.lower()
    for word, hour_int in word_to_hour.items():
        if word in text_lower:
            hour_str = str(hour_int).zfill(2)
            for slot in available_slots:
                if slot["time"].startswith(hour_str + ":"):
                    return slot["time"]

    # If only one slot is available, any confirmation accepts it
    if len(available_slots) == 1:
        yes_words = ["yes", "ja", "ok", "that", "that one", "fine", "good"]
        if any(w in text.lower() for w in yes_words):
            return available_slots[0]["time"]

    return None


def detect_yes_no(text: str) -> str | None:
    """Returns 'yes', 'no', or None."""
    t = text.lower()
    yes = ["yes", "ja", "correct", "korrekt", "right", "stimmt",
           "confirm", "bestätigen", "yep", "yup", "sure", "ok", "okay"]
    no  = ["no", "nein", "wrong", "falsch", "cancel", "abbrechen",
           "incorrect", "not right", "change"]
    if any(w in t for w in yes):
        return "yes"
    if any(w in t for w in no):
        return "no"
    return None


# ─────────────────────────────────────────────────────────────
# SECTION D — Response Builder
# Centralised so all text is in one place and easy to edit
# ─────────────────────────────────────────────────────────────

def R(key: str, lang: str, **kwargs) -> str:
    """
    Return a response string by key, in the correct language.
    kwargs are used for string formatting placeholders.
    """
    responses = {

        # ── Greetings ─────────────────────────────────────────
        "welcome": {
            "en": "Welcome to Functiomed! I can answer questions about our clinic or help you book an appointment. How can I help you today?",
            "de": "Willkommen bei Functiomed! Ich kann Ihnen Fragen über unsere Klinik beantworten oder Ihnen helfen, einen Termin zu buchen. Wie kann ich Ihnen heute helfen?",
        },

        # ── Booking flow ──────────────────────────────────────
        "ask_service": {
            "en": "Which service would you like to book? We offer physiotherapy, massage, osteopathy, mental coaching, ergotherapy, acupuncture, and nutrition counseling.",
            "de": "Welchen Service möchten Sie buchen? Wir bieten Physiotherapie, Massage, Osteopathie, Mental Coaching, Ergotherapie, Akupunktur und Ernährungsberatung an.",
        },
        "service_not_found": {
            "en": "I didn't catch that service. Please choose from: physiotherapy, massage, osteopathy, mental coaching, or acupuncture.",
            "de": "Den Service habe ich nicht verstanden. Bitte wählen Sie aus: Physiotherapie, Massage, Osteopathie, Mental Coaching oder Akupunktur.",
        },
        "service_confirmed": {
            "en": "Great, {service}! What date would you like? You can say tomorrow, or a specific date like March 15th.",
            "de": "Sehr gut, {service}! Für welches Datum möchten Sie buchen? Sie können zum Beispiel morgen oder einen bestimmten Termin sagen.",
        },
        "ask_date": {
            "en": "What date would you like the appointment?",
            "de": "Für welches Datum möchten Sie den Termin?",
        },
        "date_not_found": {
            "en": "I didn't catch the date. Please say something like tomorrow, or a date like March 15th.",
            "de": "Das Datum habe ich nicht verstanden. Bitte sagen Sie zum Beispiel morgen oder den 15. März.",
        },
        "no_slots": {
            "en": "Sorry, there are no available slots for {service} on {date}. Would you like to try a different date?",
            "de": "Es tut mir leid, für {service} am {date} sind keine Termine verfügbar. Möchten Sie ein anderes Datum versuchen?",
        },
        "available_slots": {
            "en": "On {date} we have these available times for {service}: {times}. Which time works for you?",
            "de": "Am {date} sind folgende Zeiten für {service} verfügbar: {times}. Welche Zeit passt Ihnen?",
        },
        "time_not_found": {
            "en": "That time is not available. Please choose from: {times}.",
            "de": "Diese Zeit ist nicht verfügbar. Bitte wählen Sie aus: {times}.",
        },
        "ask_name": {
            "en": "Perfect! What is your full name?",
            "de": "Perfekt! Wie ist Ihr vollständiger Name?",
        },
        "ask_phone": {
            "en": "And your phone number?",
            "de": "Und Ihre Telefonnummer?",
        },
        "phone_invalid": {
            "en": "Please provide a complete phone number, for example plus 41 79 123 45 67.",
            "de": "Bitte nennen Sie eine vollständige Telefonnummer, zum Beispiel plus 41 79 123 45 67.",
        },
        "confirm_booking": {
            "en": "Let me confirm your appointment:\n{summary}\nShall I confirm this booking? Please say yes or no.",
            "de": "Ich bestätige Ihren Termin:\n{summary}\nSoll ich diesen Termin buchen? Bitte sagen Sie ja oder nein.",
        },
        "booking_success": {
            "en": "Your appointment is confirmed! Is there anything else I can help you with?",
            "de": "Ihr Termin ist bestätigt! Ihre Buchungsnummer ist . Kann ich Ihnen noch bei etwas helfen?",
        },
        "booking_failed": {
            "en": "I'm sorry, there was a technical problem saving your appointment. Please call us directly at the clinic.",
            "de": "Es tut mir leid, es gab ein technisches Problem beim Speichern Ihres Termins. Bitte rufen Sie uns direkt in der Klinik an.",
        },

        # ── Cancellation / Navigation ─────────────────────────
        "cancelled": {
            "en": "Booking cancelled. How else can I help you?",
            "de": "Buchung abgebrochen. Wie kann ich Ihnen sonst helfen?",
        },
        "went_back": {
            "en": "No problem, let's go back.",
            "de": "Kein Problem, wir gehen einen Schritt zurück.",
        },
        "at_beginning": {
            "en": "We are already at the beginning. How can I help you?",
            "de": "Wir sind bereits am Anfang. Wie kann ich Ihnen helfen?",
        },
        "confirm_yes_no": {
            "en": "Please say yes to confirm or no to cancel.",
            "de": "Bitte sagen Sie ja zum Bestätigen oder nein zum Abbrechen.",
        },
        "fallback": {
            "en": "I'm not sure I understood. Could you rephrase that?",
            "de": "Ich bin mir nicht sicher, ob ich das verstanden habe. Könnten Sie das umformulieren?",
        },
        "faq_resume_booking": {
            "en": "I hope that answered your question! Now, back to your booking —",
            "de": "Ich hoffe, das hat Ihre Frage beantwortet! Jetzt zurück zu Ihrer Buchung —",
        },
    }

    template = responses.get(key, {}).get(lang) or responses.get(key, {}).get("en", f"[{key}]")
    try:
        return template.format(**kwargs)
    except KeyError:
        return template


# ─────────────────────────────────────────────────────────────
# SECTION E — State Machine Logic
# ─────────────────────────────────────────────────────────────

async def process_message(text: str, session: BookingSession) -> str:
    """
    Core state machine.
    Takes user text + current session → returns agent response text.
    Also updates session state and stored data as a side effect.
    """
    lang  = session.language
    state = session.state

    logger.info(f"[{session.room_id}] State: {state.value} | Input: '{text[:60]}'")

    # ── UNIVERSAL: Detect language on early messages ──────────
    if state in (ConversationState.IDLE, ConversationState.GREETING):
        detected = detect_language(text)
        if detected != session.language:
            session.language = detected
            lang = detected
            logger.info(f"Language detected: {lang}")

    # ── UNIVERSAL: Cancel at any point ───────────────────────
    if detect_intent(text) == "cancel" and state not in (
        ConversationState.IDLE, ConversationState.GREETING
    ):
        session.reset_booking()
        return R("cancelled", lang)

    # ── UNIVERSAL: Go back ────────────────────────────────────
    if detect_intent(text) == "go_back":
        went = session.go_back()
        if went:
            return R("went_back", lang) + " " + _prompt_for_current_state(session)
        else:
            return R("at_beginning", lang)

    # ─────────────────────────────────────────────────────────
    # State: IDLE / GREETING — figure out what user wants
    # ─────────────────────────────────────────────────────────
    if state in (ConversationState.IDLE, ConversationState.GREETING):
        intent = detect_intent(text)

        if intent == "book":
            session.transition_to(ConversationState.COLLECT_SERVICE)
            return R("ask_service", lang)
        else:
            # Treat as FAQ — use RAG pipeline
            session.transition_to(ConversationState.FAQ)
            answer = await _ask_rag(text)
            session.transition_to(ConversationState.IDLE)
            return answer

    # ─────────────────────────────────────────────────────────
    # State: FAQ mid-booking (user asked a question during booking)
    # ─────────────────────────────────────────────────────────
    if state == ConversationState.FAQ:
        answer = await _ask_rag(text)
        # Restore pre-FAQ state if there was one
        if session.pre_faq_state:
            session.state = session.pre_faq_state
            session.pre_faq_state = None
            resume_prompt = _prompt_for_current_state(session)
            return answer + "\n\n" + R("faq_resume_booking", lang) + " " + resume_prompt
        session.state = ConversationState.IDLE
        return answer

    # ─────────────────────────────────────────────────────────
    # State: COLLECT_SERVICE
    # ─────────────────────────────────────────────────────────
    if state == ConversationState.COLLECT_SERVICE:

        # FAQ interrupt — user asked a question instead of naming a service
        if detect_intent(text) == "faq" and not detect_service(text):
            session.pre_faq_state = state
            session.state = ConversationState.FAQ
            answer = await _ask_rag(text)
            session.state = state
            session.pre_faq_state = None
            return answer + "\n\n" + R("ask_service", lang)

        service = detect_service(text)
        if not service:
            return R("service_not_found", lang)

        session.service = service
        session.transition_to(ConversationState.COLLECT_DATE)
        return R("service_confirmed", lang, service=service)

    # ─────────────────────────────────────────────────────────
    # State: COLLECT_DATE
    # ─────────────────────────────────────────────────────────
    if state == ConversationState.COLLECT_DATE:

        # FAQ interrupt
        if detect_intent(text) == "faq" and not detect_date(text):
            session.pre_faq_state = state
            session.state = ConversationState.FAQ
            answer = await _ask_rag(text)
            session.state = state
            session.pre_faq_state = None
            return answer + "\n\n" + R("ask_date", lang)

        parsed_date = detect_date(text)
        if not parsed_date:
            return R("date_not_found", lang)

        # Query SQLite for available slots
        slots = get_available_slots(parsed_date, session.service)

        if not slots:
            return R("no_slots", lang, service=session.service, date=parsed_date)

        session.date            = parsed_date
        session.available_slots = slots
        session.transition_to(ConversationState.COLLECT_SLOT)

        times = ", ".join(s["time"] for s in slots[:5])  # Show max 5
        return R("available_slots", lang,
                 date=parsed_date, service=session.service, times=times)

    # ─────────────────────────────────────────────────────────
    # State: COLLECT_SLOT
    # ─────────────────────────────────────────────────────────
    if state == ConversationState.COLLECT_SLOT:

        chosen_time = detect_time(text, session.available_slots)
        if not chosen_time:
            times = ", ".join(s["time"] for s in session.available_slots[:5])
            return R("time_not_found", lang, times=times)

        session.time = chosen_time
        session.transition_to(ConversationState.COLLECT_NAME)
        return R("ask_name", lang)

    # ─────────────────────────────────────────────────────────
    # State: COLLECT_NAME
    # ─────────────────────────────────────────────────────────
    if state == ConversationState.COLLECT_NAME:

        name = text.strip().title()
        if len(name) < 2:
            return R("ask_name", lang)   # Too short, re-ask

        session.name = name
        session.transition_to(ConversationState.COLLECT_PHONE)
        return R("ask_phone", lang)
    # ─────────────────────────────────────────────────────────
    # State: COLLECT_PHONE
    # ─────────────────────────────────────────────────────────
    if state == ConversationState.COLLECT_PHONE:

        # Strip everything except digits and +
        phone = re.sub(r"[^\d+]", "", text)
        if len(phone) < 9:
            return R("phone_invalid", lang)

        session.phone = phone
        session.transition_to(ConversationState.CONFIRM_BOOKING)
        return R("confirm_booking", lang, summary=session.summary())

    # ─────────────────────────────────────────────────────────
    # State: CONFIRM_BOOKING
    # ─────────────────────────────────────────────────────────
    if state == ConversationState.CONFIRM_BOOKING:

        answer = detect_yes_no(text)

        if answer == "yes":
            # ── Save to SQLite ────────────────────────────────
            result = book_appointment(
                name     = session.name,
                phone    = session.phone,
                service  = session.service,
                date_str = session.date,
                time_str = session.time,
                room_id  = session.room_id,
            )

            if result["success"]:
                appt_id = result["appointment_id"]
                session.transition_to(ConversationState.BOOKING_DONE)
                session.reset_booking()   # Clear data, return to IDLE
                return R("booking_success", lang, appt_id=appt_id,)
            else:
                session.reset_booking()
                return R("booking_failed", lang)

        elif answer == "no":
            session.reset_booking()
            return R("cancelled", lang)

        else:
            return R("confirm_yes_no", lang)

    # ─────────────────────────────────────────────────────────
    # State: BOOKING_DONE — ready for next request
    # ─────────────────────────────────────────────────────────
    if state == ConversationState.BOOKING_DONE:
        session.reset_booking()
        return await process_message(text, session)   # Reprocess as new intent

    # Fallback
    return R("fallback", lang)


def _prompt_for_current_state(session: BookingSession) -> str:
    """After going back, re-ask the question for the current state."""
    lang  = session.language
    state = session.state
    prompts = {
        ConversationState.COLLECT_SERVICE: R("ask_service", lang),
        ConversationState.COLLECT_DATE:    R("service_confirmed", lang, service=session.service or ""),
        ConversationState.COLLECT_SLOT: (
            R("available_slots", lang,
              date=session.date or "",
              service=session.service or "",
              times=", ".join(s["time"] for s in session.available_slots[:5]))
            if session.available_slots else R("ask_date", lang)
        ),
        ConversationState.COLLECT_NAME:  R("ask_name", lang),
        ConversationState.COLLECT_EMAIL: R("ask_email", lang, name=session.name or ""),
        ConversationState.COLLECT_PHONE: R("ask_phone", lang),
        ConversationState.CONFIRM_BOOKING: R("confirm_booking", lang, summary=session.summary()),
    }
    return prompts.get(state, R("welcome", lang))


async def _ask_rag(query: str) -> str:
    """
    Call your existing RAG pipeline in a thread pool.
    ask_llm() is synchronous, so we run it in executor to avoid
    blocking the async event loop.
    """
    loop = asyncio.get_event_loop()
    try:
        answer = await loop.run_in_executor(None, ask_llm, query)
        return answer
    except Exception as e:
        logger.error(f"RAG error: {e}")
        return "I'm sorry, I couldn't retrieve that information right now."


# ─────────────────────────────────────────────────────────────
# SECTION F — LiveKit Agent Entry Point
# ─────────────────────────────────────────────────────────────

async def entrypoint(ctx: agents.JobContext):
    """
    Called by LiveKit when a new room needs an agent.
    Sets up the room connection and DataChannel message handler.
    """
    room_name = ctx.room.name
    logger.info(f"\n{'='*60}")
    logger.info(f"🤖 Agent starting for room: {room_name}")
    logger.info(f"{'='*60}\n")

    # Pre-load vector store once so first query is fast
    # (uses your existing embedding.py)
    logger.info("📚 Pre-loading vector store...")
    from embedding.embedding import build_or_load_vectorstore
    build_or_load_vectorstore()
    logger.info("✅ Vector store ready")

    # Connect agent to the LiveKit room
    await ctx.connect()

    session = get_session(room_name)

    # ── Helper: send text response back to browser ────────────
    async def send_response(text: str, state: str = ""):
        """
        Publish a JSON message to all participants in the room via DataChannel.
        The React browser receives this and speaks it via Web Speech API TTS.
        """
        payload = json.dumps({
            "type":  "agent_response",
            "text":  text,
            "state": state,
        }).encode("utf-8")

        await ctx.room.local_participant.publish_data(
            payload,
            reliable=True,       # Guaranteed delivery (like TCP)
        )
        logger.info(f"[{room_name}] → Sent: '{text[:80]}...' | state={state}")

    # ── Send welcome message immediately ─────────────────────
    session.state = ConversationState.GREETING
    welcome_text  = R("welcome", session.language)
    await send_response(welcome_text, "greeting")

    # ── Listen for incoming DataChannel messages ──────────────
    @ctx.room.on("data_received")
    def on_data_received(data_packet):
        """
        Fired every time the browser sends a message via DataChannel.
        Decode the JSON, run through state machine, send response.
        """
        asyncio.ensure_future(_handle_message(data_packet))

    async def _handle_message(data_packet):
        try:
            raw     = data_packet.data
            payload = json.loads(raw.decode("utf-8"))

            if payload.get("type") != "user_message":
                return

            user_text = payload.get("text", "").strip()
            if not user_text:
                return

            logger.info(f"[{room_name}] ← Received: '{user_text}'")

            # Run state machine
            response_text = await process_message(user_text, session)

            # Send response back
            await send_response(response_text, session.state.value)

        except json.JSONDecodeError:
            logger.warning(f"[{room_name}] Non-JSON data received — ignoring")
        except Exception as e:
            logger.error(f"[{room_name}] Error handling message: {e}")
            import traceback
            traceback.print_exc()

    # ── Clean up when call ends ───────────────────────────────
    @ctx.room.on("disconnected")
    def on_disconnected():
        logger.info(f"[{room_name}] Room disconnected — clearing session")
        clear_session(room_name)

    # Keep the agent alive until the room closes
    logger.info(f"[{room_name}] ✅ Agent ready — waiting for messages")
    await asyncio.Future()   # Run forever until cancelled


# ─────────────────────────────────────────────────────────────
# SECTION G — Run the agent
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    agents.cli.run_app(
        agents.WorkerOptions(entrypoint_fnc=entrypoint)
    )