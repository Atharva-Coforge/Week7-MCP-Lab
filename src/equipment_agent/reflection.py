"""Compare a draft decision with the latest eligibility observation."""

from __future__ import annotations


def reflect_on_draft(decision: str, eligibility: dict | None) -> dict:
    """Return whether the draft matches the tool result.

    An escalation is left in place, because that choice depends on the sentence.
    Approved and denied must match the eligibility observation.
    """
    if decision == "escalated" or eligibility is None:
        return {
            "confirmed": True,
            "note": "Confirmed. The draft does not contradict an eligibility result.",
        }

    within_policy = eligibility.get("eligible") is True and eligibility.get("reason") == "within_policy"
    reason = eligibility.get("reason")
    count = eligibility.get("count")
    maximum = eligibility.get("max_count")

    if decision == "approved" and not within_policy:
        return {
            "confirmed": False,
            "note": f"Rejected. The draft says approved, but eligibility reason is {reason}.",
        }
    if decision == "denied" and within_policy:
        return {
            "confirmed": False,
            "note": (
                "Rejected. The draft says denied, but eligibility is within_policy "
                f"with count {count} of max {maximum}."
            ),
        }
    return {
        "confirmed": True,
        "note": "Confirmed. The draft matches the eligibility observation.",
    }


def decision_from_eligibility(eligibility: dict | None) -> str:
    """The decision the eligibility observation supports."""
    if not eligibility:
        return "escalated"
    if eligibility.get("eligible") is True and eligibility.get("reason") == "within_policy":
        return "approved"
    if eligibility.get("reason") in {"too_soon", "at_limit", "terminated"}:
        return "denied"
    return "escalated"
