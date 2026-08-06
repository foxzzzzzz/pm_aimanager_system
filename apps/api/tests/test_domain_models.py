from datetime import date

import pytest
from pydantic import ValidationError

from project_manager_api.domain.models import PlanDateState, PlanWindow


def test_scheduled_plan_window_requires_dates() -> None:
    with pytest.raises(ValidationError):
        PlanWindow(state=PlanDateState.SCHEDULED)


def test_not_applicable_plan_window_rejects_dates() -> None:
    with pytest.raises(ValidationError):
        PlanWindow(
            state=PlanDateState.NOT_APPLICABLE,
            start_date=date(2026, 8, 1),
            end_date=date(2026, 8, 1),
        )


def test_scheduled_range_preserves_both_boundaries() -> None:
    window = PlanWindow(
        state=PlanDateState.SCHEDULED,
        start_date=date(2026, 9, 11),
        end_date=date(2026, 9, 26),
    )

    assert window.start_date == date(2026, 9, 11)
    assert window.end_date == date(2026, 9, 26)
