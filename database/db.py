import sqlite3
import os
from datetime import date, timedelta

# ─────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────

DB_PATH = "database/functiomed.db"


# ─────────────────────────────────────────────
# Connection
# ─────────────────────────────────────────────

def get_connection():
    """Return a SQLite connection with row_factory enabled."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row   # rows behave like dicts
    return conn


# ─────────────────────────────────────────────
# Initialize DB (run on startup)
# ─────────────────────────────────────────────

def init_db():
    """
    Create all tables if they don't exist.
    Safe to call on every application startup.
    """
    os.makedirs("database", exist_ok=True)
    conn = get_connection()

    conn.executescript("""
        -- Table 1: confirmed appointments
        CREATE TABLE IF NOT EXISTS appointments (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT    NOT NULL,
            phone       TEXT    NOT NULL,
            service     TEXT    NOT NULL,
            date        TEXT    NOT NULL,
            time        TEXT    NOT NULL,
            status      TEXT    DEFAULT 'confirmed',
            created_at  TEXT    DEFAULT (datetime('now')),
            room_id     TEXT    DEFAULT ''
        );

        -- Table 2: available time slots (pre-seeded)
        CREATE TABLE IF NOT EXISTS available_slots (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            date        TEXT    NOT NULL,
            time        TEXT    NOT NULL,
            service     TEXT    NOT NULL,
            is_booked   INTEGER DEFAULT 0,
            UNIQUE(date, time, service)
        );
    """)

    conn.commit()
    conn.close()
    print("✅ Database initialized — tables ready")


# ─────────────────────────────────────────────
# Seed available slots
# ─────────────────────────────────────────────

def seed_slots():
    """
    Insert available time slots for the next 14 days.
    Skips dates/times that already exist (idempotent).
    """
    conn = get_connection()

    services = [
        "physiotherapy",
        "massage",
        "osteopathy",
        "mental coaching",
    ]

    times = [
        "09:00", "10:00", "11:00",
        "13:00", "14:00", "15:00", "16:00",
    ]

    inserted = 0
    for i in range(1, 15):                          # next 14 days
        day = (date.today() + timedelta(days=i)).strftime("%Y-%m-%d")
        for service in services:
            for t in times:
                try:
                    conn.execute(
                        "INSERT OR IGNORE INTO available_slots (date, time, service) VALUES (?, ?, ?)",
                        (day, t, service)
                    )
                    inserted += 1
                except Exception:
                    pass

    conn.commit()
    conn.close()
    print(f"✅ Slots seeded — {inserted} rows inserted (duplicates ignored)")


# ─────────────────────────────────────────────
# CRUD Operations
# ─────────────────────────────────────────────

def get_available_slots(date_str: str, service: str = None) -> list:
    """
    Return all free slots for a given date.
    Optionally filter by service.
    """
    conn = get_connection()

    if service:
        rows = conn.execute(
            """SELECT * FROM available_slots
               WHERE date = ? AND service = ? AND is_booked = 0
               ORDER BY time""",
            (date_str, service)
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT * FROM available_slots
               WHERE date = ? AND is_booked = 0
               ORDER BY time""",
            (date_str,)
        ).fetchall()

    conn.close()
    return [dict(r) for r in rows]


def book_appointment(
    name: str,
    phone: str,
    service: str,
    date_str: str,
    time_str: str,
    room_id: str = "",
) -> dict:
    """
    Save a confirmed appointment and mark the slot as booked.
    Uses a transaction — both writes succeed or both are rolled back.
    """
    conn = get_connection()

    try:
        # Step 1: Mark slot as taken
        conn.execute(
            """UPDATE available_slots
               SET is_booked = 1
               WHERE date = ? AND time = ? AND service = ?""",
            (date_str, time_str, service)
        )

        # Step 2: Insert appointment record
        cursor = conn.execute(
            """INSERT INTO appointments
       (name, phone, service, date, time, room_id)
       VALUES (?, ?, ?, ?, ?, ?)""",   # 6 question marks
    (name, phone, service, date_str, time_str, room_id)
)

        conn.commit()
        appointment_id = cursor.lastrowid
        print(f"✅ Appointment #{appointment_id} booked for {name} — {service} on {date_str} at {time_str}")
        return {"success": True, "appointment_id": appointment_id}

    except Exception as e:
        conn.rollback()
        print(f"❌ Booking failed: {e}")
        return {"success": False, "error": str(e)}

    finally:
        conn.close()


def get_appointments(date_str: str = None) -> list:
    """
    Return all appointments, optionally filtered by date.
    Used by the admin dashboard.
    """
    conn = get_connection()

    if date_str:
        rows = conn.execute(
            "SELECT * FROM appointments WHERE date = ? ORDER BY time",
            (date_str,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM appointments ORDER BY date, time"
        ).fetchall()

    conn.close()
    return [dict(r) for r in rows]


def cancel_appointment(appointment_id: int) -> dict:
    """
    Cancel an appointment and free up the slot.
    """
    conn = get_connection()

    try:
        # Get the appointment details first
        row = conn.execute(
            "SELECT * FROM appointments WHERE id = ?",
            (appointment_id,)
        ).fetchone()

        if not row:
            return {"success": False, "error": "Appointment not found"}

        appt = dict(row)

        # Free the slot
        conn.execute(
            """UPDATE available_slots SET is_booked = 0
               WHERE date = ? AND time = ? AND service = ?""",
            (appt["date"], appt["time"], appt["service"])
        )

        # Update appointment status
        conn.execute(
            "UPDATE appointments SET status = 'cancelled' WHERE id = ?",
            (appointment_id,)
        )

        conn.commit()
        return {"success": True, "appointment_id": appointment_id}

    except Exception as e:
        conn.rollback()
        return {"success": False, "error": str(e)}

    finally:
        conn.close()