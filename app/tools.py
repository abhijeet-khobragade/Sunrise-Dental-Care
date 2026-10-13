"""Tools the chatbot can call, and the Python code that runs them.

Claude never touches the database directly. It asks to call a tool, our code
validates the input and does the work, and the result goes back to Claude.
"""

import re
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import Appointment, Handoff
from app.knowledge import KnowledgeBase

SERVICES = [
    "Checkup and cleaning",
    "Filling",
    "Root canal treatment",
    "Teeth whitening",
    "Braces consultation",
    "Tooth extraction",
    "Emergency visit",
]
MAX_DAYS_AHEAD = 60


class ToolError(Exception):
    """Invalid tool input. The message is sent back to Claude so it can fix the problem."""


def _schema(properties: dict, required: list[str]) -> dict:
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


TOOLS = [
    {
        "name": "search_knowledge_base",
        "description": (
            "Search the clinic's documents (hours, location, dentists, services, prices, "
            "payment, insurance and other policies). Call this before answering any "
            "question about the clinic."
        ),
        "input_schema": _schema(
            {"query": {"type": "string", "description": "What to look for, e.g. 'root canal price'"}},
            ["query"],
        ),
        "strict": True,
    },
    {
        "name": "check_availability",
        "description": "List the free 30-minute appointment slots on a given date.",
        "input_schema": _schema(
            {"date": {"type": "string", "description": "Date in YYYY-MM-DD format"}},
            ["date"],
        ),
        "strict": True,
    },
    {
        "name": "book_appointment",
        "description": (
            "Book an appointment. Only call this after the patient has confirmed the "
            "service, date, time, their name and their phone number."
        ),
        "input_schema": _schema(
            {
                "patient_name": {"type": "string"},
                "phone": {"type": "string", "description": "10-digit mobile number"},
                "service": {"type": "string", "enum": SERVICES},
                "date": {"type": "string", "description": "YYYY-MM-DD"},
                "time": {"type": "string", "description": "HH:MM (24-hour), one of the free slots"},
            },
            ["patient_name", "phone", "service", "date", "time"],
        ),
        "strict": True,
    },
    {
        "name": "escalate_to_human",
        "description": (
            "Hand the conversation to clinic staff. Use when the customer asks for a "
            "human, has a complaint, a medical question that needs a dentist, a billing "
            "dispute, or anything the documents don't answer."
        ),
        "input_schema": _schema(
            {
                "reason": {"type": "string", "description": "Short reason, e.g. 'billing complaint'"},
                "summary": {"type": "string", "description": "What staff need to know"},
                "contact": {
                    "type": "string",
                    "description": "Customer's name and phone/email, or 'not provided'",
                },
            },
            ["reason", "summary", "contact"],
        ),
        "strict": True,
    },
]


# ---------- Opening hours ----------

def slots_for_day(day: date) -> list[str]:
    """All bookable start times. Mon-Fri 9-18 with lunch 13-14, Sat 9-14, Sun closed."""
    weekday = day.weekday()  # Monday = 0, Sunday = 6
    if weekday == 6:
        return []
    closing_hour = 14 if weekday == 5 else 18
    slots = []
    for hour in range(9, closing_hour):
        if hour == 13 and weekday != 5:
            continue  # lunch break
        slots += [f"{hour:02d}:00", f"{hour:02d}:30"]
    return slots


def _parse_date(value: str, now: datetime) -> date:
    try:
        day = date.fromisoformat(value)
    except ValueError:
        raise ToolError(f"'{value}' is not a valid date. Use YYYY-MM-DD.")
    if day < now.date():
        raise ToolError(f"{value} is in the past. Today is {now.date().isoformat()}.")
    if day > now.date() + timedelta(days=MAX_DAYS_AHEAD):
        raise ToolError(f"Bookings open only {MAX_DAYS_AHEAD} days ahead.")
    return day


def _free_slots(db: Session, day: date, now: datetime) -> list[str]:
    booked = set(db.scalars(select(Appointment.time).where(Appointment.date == day.isoformat())))
    free = [s for s in slots_for_day(day) if s not in booked]
    if day == now.date():
        free = [s for s in free if s > now.strftime("%H:%M")]
    return free


# ---------- Tool implementations ----------

def search_knowledge_base(kb: KnowledgeBase, query: str) -> str:
    chunks = kb.search(query)
    if not chunks:
        return "No matching information found in the clinic documents."
    return "\n\n---\n\n".join(f"[Source: {c.source} > {c.title}]\n{c.text}" for c in chunks)


def check_availability(db: Session, date_str: str, now: datetime) -> str:
    day = _parse_date(date_str, now)
    if not slots_for_day(day):
        return f"The clinic is closed on {day:%A}, {day.isoformat()}."
    free = _free_slots(db, day, now)
    if not free:
        return f"No free slots left on {day:%A}, {day.isoformat()}."
    return f"Free slots on {day:%A}, {day.isoformat()}: {', '.join(free)}"


def book_appointment(db: Session, args: dict, now: datetime) -> str:
    name = args["patient_name"].strip()
    if len(name) < 2:
        raise ToolError("Please get the patient's full name.")

    digits = re.sub(r"\D", "", args["phone"])
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]  # drop the +91 country code
    if len(digits) != 10:
        raise ToolError("The phone number must have 10 digits.")

    if args["service"] not in SERVICES:
        raise ToolError(f"Unknown service. Choose one of: {', '.join(SERVICES)}")

    day = _parse_date(args["date"], now)
    time = args["time"]
    if time not in _free_slots(db, day, now):
        raise ToolError(f"{time} on {day.isoformat()} is not available. Check availability again.")

    appointment = Appointment(
        patient_name=name, phone=digits, service=args["service"], date=day.isoformat(), time=time
    )
    db.add(appointment)
    try:
        db.commit()
    except IntegrityError:  # someone else booked this slot a moment ago
        db.rollback()
        raise ToolError(f"{time} on {day.isoformat()} was just taken. Offer another slot.")
    return (
        f"Booked. Confirmation number SDC-{appointment.id:04d}: {appointment.service} for "
        f"{name} on {day:%A, %d %B %Y} at {time}."
    )


def escalate_to_human(db: Session, session_id: str, args: dict) -> str:
    handoff = Handoff(
        session_id=session_id,
        reason=args["reason"][:200],
        summary=args["summary"],
        contact=args["contact"][:100],
    )
    db.add(handoff)
    db.commit()
    return (
        f"Ticket HD-{handoff.id:04d} created. A staff member will contact the customer "
        "during clinic hours (usually within 2 hours)."
    )


def run_tool(
    name: str, args: dict, *, db: Session, kb: KnowledgeBase, session_id: str, now: datetime
) -> str:
    """Run one tool by name. Raises ToolError for bad input."""
    if name == "search_knowledge_base":
        return search_knowledge_base(kb, args["query"])
    if name == "check_availability":
        return check_availability(db, args["date"], now)
    if name == "book_appointment":
        return book_appointment(db, args, now)
    if name == "escalate_to_human":
        return escalate_to_human(db, session_id, args)
    raise ToolError(f"Unknown tool: {name}")
