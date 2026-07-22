from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta


@dataclass
class SimulationClock:
    start_date: date
    total_days: int
    current_day: int = 1

    def __post_init__(self) -> None:
        if self.total_days <= 0:
            raise ValueError("total_days must be greater than zero.")

        if self.current_day < 1:
            raise ValueError(
                "current_day must be greater than or equal to 1."
            )

        if self.current_day > self.total_days:
            raise ValueError(
                "current_day cannot exceed total_days."
            )

    @property
    def current_date(self) -> date:
        return self.start_date + timedelta(days=self.current_day - 1)

    @property
    def day_of_week(self) -> int:
        """
        Return the weekday as an integer.

        Monday = 0
        Sunday = 6
        """
        return self.current_date.weekday()

    @property
    def day_name(self) -> str:
        return self.current_date.strftime("%A")

    @property
    def month(self) -> int:
        return self.current_date.month

    @property
    def year(self) -> int:
        return self.current_date.year

    @property
    def day_of_year(self) -> int:
        return self.current_date.timetuple().tm_yday

    @property
    def is_weekend(self) -> bool:
        return self.day_of_week >= 5

    @property
    def is_finished(self) -> bool:
        return self.current_day >= self.total_days

    @property
    def remaining_days(self) -> int:
        return self.total_days - self.current_day

    def advance(self, days: int = 1) -> None:
        if days <= 0:
            raise ValueError("days must be greater than zero.")

        next_day = self.current_day + days

        if next_day > self.total_days:
            raise StopIteration(
                "The simulation clock cannot advance beyond total_days."
            )

        self.current_day = next_day

    def reset(self) -> None:
        self.current_day = 1

    def summary(self) -> str:
        return (
            f"Simulation Day  : {self.current_day}/{self.total_days}\n"
            f"Current Date    : {self.current_date.isoformat()}\n"
            f"Day Name        : {self.day_name}\n"
            f"Day of Week     : {self.day_of_week}\n"
            f"Day of Year     : {self.day_of_year}\n"
            f"Weekend         : {self.is_weekend}\n"
            f"Remaining Days  : {self.remaining_days}"
        )