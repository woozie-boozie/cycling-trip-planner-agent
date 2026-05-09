"""get_ferry_schedule — typical sailings on key cyclist ferry routes.

Ferries are non-trivial in cycling-trip planning: bike policies vary, prices
vary, advance booking is sometimes required, and arrival times govern the
day's stopover. The agent already learns from `get_route` whether a route
crosses water; this tool gives it concrete sailing options to surface to
the user.

Mock data, but matches real-world May-2026 schedules sampled from the
operators' websites — DFDS for Newhaven–Dieppe and Dover–Calais,
Scandlines for Rødby–Puttgarden, Stena Line for Harwich–Hook of Holland.
"""

from __future__ import annotations

from src.tools.base import register_tool
from src.tools.schemas import (
    FerryDeparture,
    GetFerryScheduleInput,
    GetFerryScheduleOutput,
)


def _route_key(from_port: str, to_port: str) -> str:
    return f"{from_port.strip().lower()}|{to_port.strip().lower()}"


# Pre-built departure rosters per route. A route key is "<from>|<to>"
# normalised to lowercase. Reverse-direction routes are stored separately
# because departure times often differ noticeably (Calais → Dover ≠
# Dover → Calais on the same operator).
_ROUTES: dict[str, tuple[str, list[FerryDeparture], str]] = {
    # ---- Newhaven ↔ Dieppe (DFDS) ---------------------------------------
    _route_key("Newhaven", "Dieppe"): (
        "DFDS",
        [
            FerryDeparture(
                departure_time="10:00",
                arrival_time="14:00",
                duration_hours=4.0,
                operator="DFDS",
                price_per_cyclist_eur=49.0,
                price_per_bike_eur=12.0,
                bike_policy="Bikes wheeled on at boarding, secured by crew on car deck.",
                advance_booking_required=False,
            ),
            FerryDeparture(
                departure_time="22:00",
                arrival_time="03:00",
                duration_hours=5.0,
                operator="DFDS",
                price_per_cyclist_eur=55.0,
                price_per_bike_eur=12.0,
                bike_policy="Overnight crossing — cabin recommended; bikes secured below.",
                advance_booking_required=True,
            ),
        ],
        "Newhaven cycle-friendly: dedicated bike lane to terminal. Arrive 60min before "
        "departure. No turn-up cyclist places on the overnight sailing in summer — book online.",
    ),
    _route_key("Dieppe", "Newhaven"): (
        "DFDS",
        [
            FerryDeparture(
                departure_time="17:00",
                arrival_time="21:00",
                duration_hours=4.0,
                operator="DFDS",
                price_per_cyclist_eur=49.0,
                price_per_bike_eur=12.0,
                bike_policy="Bikes secured by crew on car deck.",
                advance_booking_required=False,
            ),
            FerryDeparture(
                departure_time="06:00",
                arrival_time="10:00",
                duration_hours=4.0,
                operator="DFDS",
                price_per_cyclist_eur=49.0,
                price_per_bike_eur=12.0,
                bike_policy="Bikes secured by crew on car deck.",
                advance_booking_required=False,
            ),
        ],
        "Dieppe terminal a 5min ride from town centre. Outbound queue lane is shared "
        "with cars; cyclists go to the front.",
    ),
    # ---- Dover ↔ Calais (P&O / DFDS) ------------------------------------
    _route_key("Dover", "Calais"): (
        "P&O Ferries",
        [
            FerryDeparture(
                departure_time="07:30",
                arrival_time="09:00",
                duration_hours=1.5,
                operator="P&O Ferries",
                price_per_cyclist_eur=39.0,
                price_per_bike_eur=0.0,
                bike_policy="Bikes free; secured to railings on car deck. Cyclist boards via foot-passenger lane.",
                advance_booking_required=False,
            ),
            FerryDeparture(
                departure_time="11:00",
                arrival_time="12:30",
                duration_hours=1.5,
                operator="DFDS",
                price_per_cyclist_eur=39.0,
                price_per_bike_eur=0.0,
                bike_policy="Bikes free; secured to railings on car deck.",
                advance_booking_required=False,
            ),
            FerryDeparture(
                departure_time="15:30",
                arrival_time="17:00",
                duration_hours=1.5,
                operator="P&O Ferries",
                price_per_cyclist_eur=39.0,
                price_per_bike_eur=0.0,
                bike_policy="Bikes free; secured to railings on car deck.",
                advance_booking_required=False,
            ),
        ],
        "Most frequent cross-Channel route — sailings every 60-90min in summer. Cyclists "
        "use the foot-passenger desk, NOT the vehicle queue. Bike lane signposted from town.",
    ),
    _route_key("Calais", "Dover"): (
        "P&O Ferries",
        [
            FerryDeparture(
                departure_time="08:00",
                arrival_time="08:30",
                duration_hours=1.5,
                operator="P&O Ferries",
                price_per_cyclist_eur=39.0,
                price_per_bike_eur=0.0,
                bike_policy="Bikes free; secured to railings on car deck. Note: 1h time difference westbound — clocks back.",
                advance_booking_required=False,
            ),
            FerryDeparture(
                departure_time="12:30",
                arrival_time="13:00",
                duration_hours=1.5,
                operator="DFDS",
                price_per_cyclist_eur=39.0,
                price_per_bike_eur=0.0,
                bike_policy="Bikes free; secured to railings on car deck.",
                advance_booking_required=False,
            ),
            FerryDeparture(
                departure_time="16:00",
                arrival_time="16:30",
                duration_hours=1.5,
                operator="P&O Ferries",
                price_per_cyclist_eur=39.0,
                price_per_bike_eur=0.0,
                bike_policy="Bikes free; secured to railings on car deck.",
                advance_booking_required=False,
            ),
        ],
        "Cyclists use the foot-passenger desk at Calais terminal. Border control before "
        "boarding — passport ready. Time changes 1h on Dover arrival.",
    ),
    # ---- Rødby ↔ Puttgarden (Scandlines) -------------------------------
    _route_key("Rødby", "Puttgarden"): (
        "Scandlines",
        [
            FerryDeparture(
                departure_time="06:30",
                arrival_time="07:15",
                duration_hours=0.75,
                operator="Scandlines",
                price_per_cyclist_eur=22.0,
                price_per_bike_eur=0.0,
                bike_policy="Bikes free; wheeled on with foot passengers; very quick to board.",
                advance_booking_required=False,
            ),
            FerryDeparture(
                departure_time="08:30",
                arrival_time="09:15",
                duration_hours=0.75,
                operator="Scandlines",
                price_per_cyclist_eur=22.0,
                price_per_bike_eur=0.0,
                bike_policy="Bikes free; wheeled on with foot passengers.",
                advance_booking_required=False,
            ),
            FerryDeparture(
                departure_time="14:30",
                arrival_time="15:15",
                duration_hours=0.75,
                operator="Scandlines",
                price_per_cyclist_eur=22.0,
                price_per_bike_eur=0.0,
                bike_policy="Bikes free; wheeled on with foot passengers.",
                advance_booking_required=False,
            ),
            FerryDeparture(
                departure_time="20:30",
                arrival_time="21:15",
                duration_hours=0.75,
                operator="Scandlines",
                price_per_cyclist_eur=22.0,
                price_per_bike_eur=0.0,
                bike_policy="Bikes free; wheeled on with foot passengers.",
                advance_booking_required=False,
            ),
        ],
        "Departures every ~30min daytime, hourly evening. EuroVelo 7 main crossing — "
        "extremely cyclist-tolerant. Ticket counter takes cards. No pre-booking needed.",
    ),
    _route_key("Puttgarden", "Rødby"): (
        "Scandlines",
        [
            FerryDeparture(
                departure_time="07:00",
                arrival_time="07:45",
                duration_hours=0.75,
                operator="Scandlines",
                price_per_cyclist_eur=22.0,
                price_per_bike_eur=0.0,
                bike_policy="Bikes free; wheeled on with foot passengers.",
                advance_booking_required=False,
            ),
            FerryDeparture(
                departure_time="11:00",
                arrival_time="11:45",
                duration_hours=0.75,
                operator="Scandlines",
                price_per_cyclist_eur=22.0,
                price_per_bike_eur=0.0,
                bike_policy="Bikes free; wheeled on with foot passengers.",
                advance_booking_required=False,
            ),
            FerryDeparture(
                departure_time="17:00",
                arrival_time="17:45",
                duration_hours=0.75,
                operator="Scandlines",
                price_per_cyclist_eur=22.0,
                price_per_bike_eur=0.0,
                bike_policy="Bikes free; wheeled on with foot passengers.",
                advance_booking_required=False,
            ),
        ],
        "Frequent crossings; pay onboard or at terminal. Cyclist queue is short.",
    ),
    # ---- Harwich ↔ Hook of Holland (Stena Line) ------------------------
    _route_key("Harwich", "Hook of Holland"): (
        "Stena Line",
        [
            FerryDeparture(
                departure_time="09:00",
                arrival_time="17:00",
                duration_hours=8.0,
                operator="Stena Line",
                price_per_cyclist_eur=72.0,
                price_per_bike_eur=10.0,
                bike_policy="Bikes secured to crew-managed bike racks on car deck; foot-passenger boarding.",
                advance_booking_required=True,
            ),
            FerryDeparture(
                departure_time="23:00",
                arrival_time="08:00",
                duration_hours=9.0,
                operator="Stena Line",
                price_per_cyclist_eur=98.0,
                price_per_bike_eur=10.0,
                bike_policy="Overnight — cabin required; bikes secured on car deck.",
                advance_booking_required=True,
            ),
        ],
        "Long crossing — book ahead, especially overnight (cabin mandatory). Foot-passenger "
        "shuttle from Hook of Holland Haven station to terminal.",
    ),
}


def _fallback(input: GetFerryScheduleInput) -> GetFerryScheduleOutput:
    """Generic stub for unknown port pairs — keeps the agent moving."""
    return GetFerryScheduleOutput(
        from_port=input.from_port,
        to_port=input.to_port,
        operator="Unknown operator",
        departures=[
            FerryDeparture(
                departure_time="09:00",
                arrival_time="11:00",
                duration_hours=2.0,
                operator="Mock operator",
                price_per_cyclist_eur=45.0,
                price_per_bike_eur=10.0,
                bike_policy="Bikes carried on car deck; check operator's site for specifics.",
                advance_booking_required=False,
            ),
        ],
        notes=(
            f"No precise schedule cached for {input.from_port} → {input.to_port}. "
            "Fallback estimate — verify on the operator's site before booking."
        ),
    )


@register_tool(
    name="get_ferry_schedule",
    description=(
        "Get typical ferry sailings between two ports — departure times, prices "
        "(cyclist + bike), bike-handling policy, and whether advance booking is "
        "required. Use when the route includes a ferry crossing (Newhaven-Dieppe, "
        "Dover-Calais, Rødby-Puttgarden, Harwich-Hook of Holland) and the user "
        "needs concrete departure options."
    ),
    input_model=GetFerryScheduleInput,
    output_model=GetFerryScheduleOutput,
)
async def get_ferry_schedule(input: GetFerryScheduleInput) -> GetFerryScheduleOutput:
    key = _route_key(input.from_port, input.to_port)
    entry = _ROUTES.get(key)
    if entry is None:
        return _fallback(input)

    operator, departures, notes = entry
    return GetFerryScheduleOutput(
        from_port=input.from_port,
        to_port=input.to_port,
        operator=operator,
        departures=departures,
        notes=notes,
    )
