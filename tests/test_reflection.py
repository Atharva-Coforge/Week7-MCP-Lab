from equipment_agent.reflection import decision_from_eligibility, reflect_on_draft

WITHIN = {"eligible": True, "reason": "within_policy", "count": 1, "max_count": 2}
TOO_SOON = {"eligible": False, "reason": "too_soon", "count": 1, "max_count": 1}


def test_denied_draft_is_rejected_when_the_monitor_is_within_policy():
    result = reflect_on_draft("denied", WITHIN)

    assert result["confirmed"] is False
    assert "count 1 of max 2" in result["note"]


def test_approved_draft_is_rejected_when_eligibility_is_false():
    result = reflect_on_draft("approved", TOO_SOON)

    assert result["confirmed"] is False
    assert "too_soon" in result["note"]


def test_matching_drafts_are_confirmed():
    assert reflect_on_draft("approved", WITHIN)["confirmed"] is True
    assert reflect_on_draft("denied", TOO_SOON)["confirmed"] is True
    assert reflect_on_draft("escalated", TOO_SOON)["confirmed"] is True


def test_correction_follows_the_eligibility_reason():
    assert decision_from_eligibility(WITHIN) == "approved"
    assert decision_from_eligibility(TOO_SOON) == "denied"
