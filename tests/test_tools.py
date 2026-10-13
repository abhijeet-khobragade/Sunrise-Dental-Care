from datetime import date

import pytest
from sqlalchemy import select

from app.database import Handoff
from app.tools import ToolError, book_appointment, check_availability, escalate_to_human, slots_for_day
from tests.conftest import NOW


def booking(**overrides):
    args = {
        "patient_name": "Priya Sharma",
        "phone": "+91 98765 43210",
        "service": "Filling",
        "date": "2026-10-13",
        "time": "10:30",
    }
    return {**args, **overrides}


def test_opening_hours():
    assert slots_for_day(date(2026, 10, 18)) == []  # Sunday
    weekday = slots_for_day(date(2026, 10, 13))  # Tuesday
    assert weekday[0] == "09:00" and weekday[-1] == "17:30"
    assert "13:00" not in weekday  # lunch
    assert slots_for_day(date(2026, 10, 17))[-1] == "13:30"  # Saturday ends at 2 PM


def test_availability_hides_past_slots_today(db):
    result = check_availability(db, "2026-10-12", NOW)  # NOW is 10:15 on this day
    assert "09:30" not in result and "10:30" in result


def test_closed_on_sunday(db):
    assert "closed" in check_availability(db, "2026-10-18", NOW)


@pytest.mark.parametrize("bad_date", ["2026-10-01", "next tuesday", "2027-06-01"])
def test_invalid_dates_are_rejected(db, bad_date):
    with pytest.raises(ToolError):
        check_availability(db, bad_date, NOW)


def test_booking_saves_and_removes_the_slot(db):
    result = book_appointment(db, booking(), NOW)
    assert "SDC-0001" in result
    assert "10:30" not in check_availability(db, "2026-10-13", NOW)


def test_double_booking_is_blocked(db):
    book_appointment(db, booking(), NOW)
    with pytest.raises(ToolError, match="not available"):
        book_appointment(db, booking(patient_name="Rahul Verma"), NOW)


@pytest.mark.parametrize(
    "overrides",
    [{"phone": "12345"}, {"patient_name": " "}, {"time": "13:00"}, {"service": "Haircut"}],
)
def test_bad_booking_details_are_rejected(db, overrides):
    with pytest.raises(ToolError):
        book_appointment(db, booking(**overrides), NOW)


def test_escalation_creates_ticket(db):
    result = escalate_to_human(
        db, "session-123", {"reason": "billing", "summary": "Charged twice", "contact": "Amit 9999999999"}
    )
    assert "HD-0001" in result
    assert db.scalars(select(Handoff)).one().reason == "billing"
