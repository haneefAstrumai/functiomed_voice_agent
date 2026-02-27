from dataclasses import dataclass, field
from typing import Optional
from enum import Enum


# ─────────────────────────────────────────────────────────────
# All possible positions in the conversation
# ─────────────────────────────────────────────────────────────

class ConversationState(Enum):
    """
    Each value represents exactly where the agent is
    in the conversation at any given moment.
    """
    IDLE             = "idle"             # Call connected, nothing started
    GREETING         = "greeting"         # Agent sent welcome, waiting for user
    INTENT_DETECTION = "intent_detection" # Figuring out: FAQ or booking?
    FAQ              = "faq"              # Answering a clinic question via RAG

    # ── Booking flow states (in order) ──
    COLLECT_SERVICE  = "collect_service"  # Asking: what service?
    COLLECT_DATE     = "collect_date"     # Asking: what date?
    SHOW_SLOTS       = "show_slots"       # Reading available slots aloud
    COLLECT_SLOT     = "collect_slot"     # Asking: which time?
    COLLECT_NAME     = "collect_name"     # Asking: full name?
    COLLECT_PHONE    = "collect_phone"    # Asking: phone number?
    CONFIRM_BOOKING  = "confirm_booking"  # Reading back all details, yes/no
    BOOKING_DONE     = "booking_done"     # Saved to SQLite, flow complete


# ─────────────────────────────────────────────────────────────
# One instance per active LiveKit room — this is the agent's memory
# ─────────────────────────────────────────────────────────────

@dataclass
class BookingSession:
    """
    Holds ALL information about one patient's conversation.
    Created when a room is opened, destroyed when the call ends.
    """

    # ── Identity ─────────────────────────────────────────────
    room_id: str                                    # e.g. "room-1"
    language: str = "en"                            # "en" or "de"

    # ── State machine position ────────────────────────────────
    state: ConversationState = ConversationState.IDLE

    # ── State history stack (enables "go back") ───────────────
    # Each state transition pushes the OLD state here.
    # Saying "go back" pops the last state and returns to it.
    state_history: list = field(default_factory=list)

    # ── Booking data (filled step by step) ───────────────────
    service:         Optional[str] = None   # e.g. "physiotherapy"
    date:            Optional[str] = None   # e.g. "2025-03-20"
    time:            Optional[str] = None   # e.g. "10:00"
    name:            Optional[str] = None   # e.g. "Maria Müller"
    phone:           Optional[str] = None   # e.g. "+41791234567"


    # ── Available slots for chosen date (fetched from SQLite) ─
    available_slots: list = field(default_factory=list)

    # ── FAQ state memory ─────────────────────────────────────
    # When user asks FAQ mid-booking, we save the booking state,
    # answer the FAQ, then restore the booking state.
    pre_faq_state:   Optional[ConversationState] = None

    # ─────────────────────────────────────────────────────────
    # Helper methods
    # ─────────────────────────────────────────────────────────

    def transition_to(self, new_state: ConversationState):
        """
        Move to a new state, saving the current one to history.
        This enables the 'go back' feature.
        """
        self.state_history.append(self.state)
        self.state = new_state

    def go_back(self) -> bool:
        """
        Return to the previous state.
        Returns True if successful, False if already at the beginning.
        """
        if self.state_history:
            self.state = self.state_history.pop()
            return True
        return False

    def reset_booking(self):
        """
        Clear all collected booking data and return to IDLE.
        Called when user says 'cancel' or after a completed booking.
        """
        self.service         = None
        self.date            = None
        self.time            = None
        self.name            = None
        self.phone           = None
        self.available_slots = []
        self.state_history   = []
        self.pre_faq_state   = None
        self.state           = ConversationState.IDLE

    def is_booking_complete(self) -> bool:
        """Check if all required booking fields are filled."""
        return all([
            self.service,
            self.date,
            self.time,
            self.name,
            self.phone,
        ])

    def summary(self) -> str:
        """
        Return a human-readable confirmation summary.
        Language-aware: German or English.
        """
        if self.language == "de":
            return (
                f"Name: {self.name}\n"
                f"Service: {self.service}\n"
                f"Datum: {self.date} um {self.time} Uhr\n"
                f"Telefon: {self.phone}\n"
                
            )
        return (
            f"Name: {self.name}\n"
            f"Service: {self.service}\n"
            f"Date: {self.date} at {self.time}\n"
            f"Phone: {self.phone}\n"
            
        )