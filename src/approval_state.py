"""Approval state management — persisted as JSON."""

import json
import os
from datetime import datetime


class ApprovalState:
    """Tracks pending / approved / sent status for each (employee_id, month) pair."""

    def __init__(self, state_file: str):
        self._file = state_file
        self._state: dict = {}
        self._load()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self):
        if os.path.exists(self._file):
            try:
                with open(self._file, "r", encoding="utf-8") as f:
                    self._state = json.load(f)
            except (json.JSONDecodeError, OSError):
                self._state = {}
        else:
            self._state = {}

    def _save(self):
        os.makedirs(os.path.dirname(self._file) if os.path.dirname(self._file) else ".", exist_ok=True)
        with open(self._file, "w", encoding="utf-8") as f:
            json.dump(self._state, f, indent=2)

    # ------------------------------------------------------------------
    # Key construction
    # ------------------------------------------------------------------

    @staticmethod
    def _key(employee_id: str, month: str) -> str:
        return f"{employee_id}_{month}"

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get(self, employee_id: str, month: str) -> dict:
        k = self._key(employee_id, month)
        return self._state.get(k, {
            "status": "pending",
            "approved_at": None,
            "sent_at": None,
            "commission_total_at_approval": None,
        })

    def get_all_for_month(self, month: str) -> dict:
        """Return all states for a given month string (YYYY-MM-DD)."""
        result = {}
        for k, v in self._state.items():
            if k.endswith(f"_{month}"):
                emp_id = k[: -(len(month) + 1)]
                result[emp_id] = v
        return result

    def status(self, employee_id: str, month: str) -> str:
        return self.get(employee_id, month)["status"]

    # ------------------------------------------------------------------
    # Mutations
    # ------------------------------------------------------------------

    def approve(self, employee_id: str, month: str, commission_total: float = None):
        k = self._key(employee_id, month)
        existing = self._state.get(k, {})
        if existing.get("status") == "sent":
            return  # already sent — no change
        self._state[k] = {
            "status": "approved",
            "approved_at": datetime.utcnow().isoformat(),
            "sent_at": existing.get("sent_at"),
            "commission_total_at_approval": commission_total,
        }
        self._save()

    def unapprove(self, employee_id: str, month: str):
        k = self._key(employee_id, month)
        existing = self._state.get(k, {})
        if existing.get("status") == "sent":
            return  # cannot undo a sent statement
        self._state[k] = {
            "status": "pending",
            "approved_at": None,
            "sent_at": None,
            "commission_total_at_approval": None,
        }
        self._save()

    def mark_sent(self, employee_id: str, month: str):
        k = self._key(employee_id, month)
        existing = self._state.get(k, {})
        existing["status"] = "sent"
        existing["sent_at"] = datetime.utcnow().isoformat()
        self._state[k] = existing
        self._save()

    def reset_to_pending(self, employee_id: str, month: str, reason: str = "data changed"):
        """Reset a sent/approved record back to pending (e.g. after data correction)."""
        k = self._key(employee_id, month)
        self._state[k] = {
            "status": "pending",
            "approved_at": None,
            "sent_at": None,
            "commission_total_at_approval": None,
            "reset_reason": reason,
        }
        self._save()

    # ------------------------------------------------------------------
    # Stale detection: auto-reset if commission total changed since approval
    # ------------------------------------------------------------------

    def check_and_reset_stale(self, employee_id: str, month: str, current_total: float):
        """If commission total changed since approval, reset status to pending."""
        k = self._key(employee_id, month)
        entry = self._state.get(k, {})
        if entry.get("status") not in ("approved", "sent"):
            return
        stored = entry.get("commission_total_at_approval")
        if stored is not None and abs(float(stored) - current_total) > 0.01:
            self.reset_to_pending(employee_id, month, reason="commission total changed after approval")

    # ------------------------------------------------------------------
    # Batch helpers for send
    # ------------------------------------------------------------------

    def get_approved_unsent(self, month: str) -> list[str]:
        """Return employee_ids that are approved but not yet sent for a month."""
        result = []
        for k, v in self._state.items():
            if k.endswith(f"_{month}") and v.get("status") == "approved":
                emp_id = k[: -(len(month) + 1)]
                result.append(emp_id)
        return result
