"""Oil calibration maths (needs homeassistant installed; skipped otherwise)."""

import pathlib
import sys
from datetime import datetime

import pytest

pytest.importorskip("homeassistant")
sys.path.insert(0, str(pathlib.Path(__file__).parents[1] / "custom_components"))

from hotelcollection import calibration, codec  # noqa: E402

SLOTS = [
    codec.ScheduleSlot(1, codec.days_to_mask(["Mon", "Tue", "Wed", "Thu", "Fri"]), "05:30", "12:00", True, 60, 90),
    codec.ScheduleSlot(5, codec.days_to_mask(["Sat", "Sun"]), "20:00", "23:59", True, 70, 90),
]


def test_rate_from_drop():
    # 720 mL at refill, 600 left after 30 h of spraying -> 4.0 mL/h
    assert calibration.calibrated_rate(720, 600, 30) == 4.0


@pytest.mark.parametrize("args", [(720, 600, 3), (500, 520, 30), (720, 0, 10.5)])
def test_rate_refuses_nonsense(args):
    with pytest.raises(ValueError):
        calibration.calibrated_rate(*args)


def test_schedule_hours_between():
    # Fri 16:00 -> Mon 12:00: Sat + Sun 20:00-24:00 at 70/160 (8 h x 0.4375)
    # + Mon 05:30-12:00 at 60/150 (6.5 h x 0.4) = 3.5 + 2.6 h of spraying
    start = datetime(2026, 11, 13, 16, 0)
    end = datetime(2026, 11, 16, 12, 0)
    assert calibration.schedule_hours_between(SLOTS, start, end) == pytest.approx(6.1)
