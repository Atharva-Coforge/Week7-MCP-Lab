from equipment_agent.reflection import (
    catalog_item,
    correction_note,
    decision_from_eligibility,
    decision_text,
    quantity_before_item,
    reflect_on_draft,
)

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


def test_approve_or_deny_without_eligibility_is_rejected():
    approved = reflect_on_draft("approved", None)
    denied = reflect_on_draft("denied", None)

    assert approved["confirmed"] is False
    assert denied["confirmed"] is False
    assert "check_request_eligibility was not called" in approved["note"]
    assert reflect_on_draft("escalated", None)["confirmed"] is True
    assert decision_from_eligibility(None) == "escalated"
    assert decision_text("escalated", None).startswith("Decision: escalated")


def test_matching_drafts_are_confirmed():
    ordinary = "My laptop is slow, can I get a replacement?"
    assert reflect_on_draft("approved", WITHIN)["confirmed"] is True
    assert reflect_on_draft("denied", TOO_SOON)["confirmed"] is True
    assert reflect_on_draft("denied", TOO_SOON, sentence=ordinary)["confirmed"] is True
    assert reflect_on_draft("escalated", TOO_SOON)["confirmed"] is True


def test_unclear_sentence_cannot_become_an_approval():
    unclear = "Can I get new equipment? My setup isn't great."
    approved = reflect_on_draft("approved", WITHIN, sentence=unclear)
    denied = reflect_on_draft("denied", WITHIN, sentence=unclear)

    assert catalog_item(unclear) is None
    assert approved["confirmed"] is False
    assert "no catalog item" in approved["note"]
    assert denied["confirmed"] is False
    assert reflect_on_draft("escalated", WITHIN, sentence=unclear)["confirmed"] is True
    assert decision_from_eligibility(WITHIN, sentence=unclear) == "escalated"
    assert "no catalog item" in decision_text("escalated", WITHIN, unclear)


def test_exception_request_cannot_be_denied_for_too_soon():
    damaged = "I know my laptop is only 1 year old, but it was damaged. Can I get a replacement early?"
    denied = reflect_on_draft("denied", TOO_SOON, sentence=damaged)
    approved = reflect_on_draft("approved", WITHIN, sentence=damaged)

    assert denied["confirmed"] is False
    assert "exception" in denied["note"]
    assert approved["confirmed"] is False
    assert decision_from_eligibility(TOO_SOON, sentence=damaged) == "escalated"
    assert decision_text("escalated", TOO_SOON, damaged).startswith("Decision: escalated")
    assert "exception" in decision_text("escalated", TOO_SOON, damaged)


def test_catalog_words_come_from_the_supplied_items():
    supplies = ["tablet", "box", "berry"]

    assert catalog_item("I need 3 tablets for class", supplies) == "tablet"
    assert catalog_item("We need boxes", supplies) == "box"
    assert catalog_item("Order berries", supplies) == "berry"
    assert catalog_item("I need a monitor", supplies) is None
    assert quantity_before_item("I need 3 tablets for class", supplies) == 3
    assert quantity_before_item("I need a tablet", supplies) == 1


def test_ordinary_catalog_escalation_follows_eligibility():
    monitors = "I need 200 monitors for gaming"
    at_limit = {"eligible": False, "reason": "at_limit", "count": 1, "max_count": 2, "item": "monitor"}
    missing = reflect_on_draft("escalated", None, sentence=monitors)
    limited = reflect_on_draft("escalated", at_limit, sentence=monitors)
    second = reflect_on_draft("escalated", WITHIN, sentence="I need a second monitor.")
    slow = reflect_on_draft(
        "escalated",
        TOO_SOON,
        sentence="My laptop is slow, can I get a replacement?",
    )

    assert missing["confirmed"] is False
    assert "check_request_eligibility" in missing["note"]
    assert limited["confirmed"] is False
    assert "decision is denied" in limited["note"]
    assert second["confirmed"] is False
    assert "decision is approved" in second["note"]
    assert slow["confirmed"] is False
    assert decision_from_eligibility(at_limit) == "denied"
    assert decision_from_eligibility(WITHIN) == "approved"


def test_unclear_and_exception_escalations_stay():
    unclear = "Can I get new equipment? My setup isn't great."
    damaged = "I know my laptop is only 1 year old, but it was damaged. Can I get a replacement early?"

    assert reflect_on_draft("escalated", None, sentence=unclear)["confirmed"] is True
    assert reflect_on_draft("escalated", TOO_SOON, sentence=damaged)["confirmed"] is True


def test_correction_follows_the_eligibility_reason():
    assert decision_from_eligibility(WITHIN) == "approved"
    assert decision_from_eligibility(TOO_SOON) == "denied"


def test_corrected_scratchpad_agrees_with_the_approval():
    eligibility = {
        "eligible": True,
        "reason": "within_policy",
        "item": "monitor",
        "count": 2,
        "max_count": 2,
        "age_years": 4,
    }
    note = correction_note("denied", "approved", eligibility)
    text = decision_text("approved", eligibility)

    assert "decision is approved" in note
    assert "Rejected" not in note
    assert text.startswith("Decision: approved")
    assert "within policy" in text
    assert "Rejected" not in text
