from abc import ABC, abstractmethod
import pandas as pd


class BaseCommissionPlan(ABC):
    """Abstract base class for all commission plans.

    Each role (SDR, AE, AM, CS, …) subclasses this and implements the
    two calculation methods plus the metadata helpers.
    """

    role: str = ""

    @abstractmethod
    def calculate_monthly(
        self,
        employee: pd.Series,
        month: pd.Timestamp,
        activities: pd.DataFrame,
        closed_won: pd.DataFrame,
        fx_df: pd.DataFrame,
        salary_history: pd.DataFrame,
        cs_performance: dict = None,
    ) -> dict:
        """Return a dict of commission components for one employee-month.

        Keys must include at minimum:
            employee_id, month, total_commission, currency
        Plus one key per commission component (e.g. outbound_sao_comm).

        salary_history is provided for roles that base commission on salary (AM, CS).
        cs_performance is a dict of DataFrames for CS-specific inputs (NRR, CSAT, etc.).
        SDR plans can ignore both.
        """
        ...

    @abstractmethod
    def calculate_quarterly_accelerator(
        self,
        employee: pd.Series,
        year: int,
        quarter: int,
        activities: pd.DataFrame,
        salary_history: pd.DataFrame,
        cs_performance: dict = None,
    ) -> dict:
        """Return a dict with the quarterly accelerator / bonus amount (if any).

        Keys: employee_id, year, quarter, quarter_end_month,
              accelerator_topup, currency
        Return accelerator_topup=0 if nothing applies.
        salary_history is provided for salary-based bonus roles.
        cs_performance is a dict of DataFrames for CS-specific inputs.
        """
        ...

    @abstractmethod
    def get_rates(self, currency: str) -> dict:
        """Return the rate schedule for the given currency."""
        ...

    @abstractmethod
    def get_components(self) -> list[str]:
        """Return ordered list of commission component keys for UI columns."""
        ...
