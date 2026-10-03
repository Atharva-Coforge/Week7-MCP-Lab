"""Compare a draft decision with the latest eligibility observation."""

from __future__ import annotations

import re
from collections.abc import Iterable

from equipment_agent.tools import catalog_items

_REPLACEMENT_WORD = r"replac(?:e|ement|ing)"
_ADDITION_WORD = r"another|additional|extra|second|third|fourth"
_REPLACEMENT = re.compile(rf"\b{_REPLACEMENT_WORD}\b", re.IGNORECASE)
_EXCEPTION = re.compile(
    r"\b(?:damaged|damage|lost|loss|stolen|theft|steal(?:ing)?)\b"
    r"|\bearly\s+replacement\b"
    r"|\breplacement\s+early\b"
    r"|\breplace\s+early\b",
    re.IGNORECASE,
)


def word_forms(item: str) -> set[str]:
    """The policy name and its regular plural. The item list itself comes from the policy file."""
    name = item.strip().lower()
    if name.endswith(("s", "x", "z", "ch", "sh")):
        plural = name + "es"
    elif len(name) > 1 and name.endswith("y") and name[-2] not in "aeiou":
        plural = name[:-1] + "ies"
    else:
        plural = name + "s"
    return {name, plural}


def _catalog_forms(items: Iterable[str] | None) -> list[tuple[str, str]]:
    names = [name.strip().lower() for name in (items if items is not None else catalog_items())]
    forms = [(form, name) for name in names for form in word_forms(name)]
    forms.sort(key=lambda pair: len(pair[0]), reverse=True)
    return forms


def catalog_items_named(sentence: str, items: Iterable[str] | None = None) -> list[str]:
    """Policy items named in the sentence, in the order they appear."""
    forms = _catalog_forms(items)
    if not forms:
        return []
    pattern = re.compile(r"\b(" + "|".join(re.escape(form) for form, _name in forms) + r")\b", re.IGNORECASE)
    found: list[str] = []
    for match in pattern.finditer(sentence):
        word = match.group(1).lower()
        for form, name in forms:
            if form == word and name not in found:
                found.append(name)
                break
    return found


def catalog_item(sentence: str, items: Iterable[str] | None = None) -> str | None:
    """The policy item named in the sentence, singular or plural."""
    named = catalog_items_named(sentence, items)
    return named[0] if named else None


def quantity_before_item(
    sentence: str,
    items: Iterable[str] | None = None,
    *,
    item: str | None = None,
) -> int:
    """A numeral written immediately before `item`. Any other sentence is one unit.

    A number before a different catalog word does not count. "2 monitors" is not
    a quantity for a laptop check.
    """
    names = [item.strip().lower()] if item else [name for _form, name in _catalog_forms(items)]
    forms = sorted({form for name in names for form in word_forms(name)}, key=len, reverse=True)
    if not forms:
        return 1
    pattern = re.compile(r"\b(\d+)\s+(?:" + "|".join(re.escape(form) for form in forms) + r")\b", re.IGNORECASE)
    match = pattern.search(sentence)
    if match is None:
        return 1
    return max(int(match.group(1)), 1)


def _item_pattern(item: str) -> str:
    forms = sorted(word_forms(item.strip().lower()), key=len, reverse=True)
    return "(?:" + "|".join(re.escape(form) for form in forms) + ")"


def _word_near_item(sentence: str, item: str, word: str) -> bool:
    """True when `word` modifies this catalog item, not some other noun."""
    item_re = _item_pattern(item)
    gap = r"(?:[\s,]+\w+){0,6}[\s,]+"
    pattern = rf"\b(?:{word})\b{gap}{item_re}\b|\b{item_re}\b{gap}(?:{word})\b"
    return re.search(pattern, sentence, re.IGNORECASE) is not None


def asks_for_addition(sentence: str, item: str | None = None) -> bool:
    """True when an addition word modifies `item`.

    "a second monitor" is an addition of a monitor. "my second office" is not an
    addition of a laptop. "another laptop" does not make a monitor an addition.
    """
    if not item:
        return False
    item_re = _item_pattern(item)
    gap = r"(?:[\s,]+\w+){0,3}[\s,]+"
    pattern = rf"\b(?:{_ADDITION_WORD})\b{gap}{item_re}\b|\bone more{gap}{item_re}\b"
    return re.search(pattern, sentence, re.IGNORECASE) is not None


def asks_for_replacement(sentence: str, item: str | None = None) -> bool:
    """True when this item is a replacement, not one more unit.

    "a laptop replacement" and "can I get a replacement?" with the laptop named
    count. "a laptop replacement" does not make a monitor a replacement.
    """
    if not item or _REPLACEMENT.search(sentence) is None:
        return False
    if _word_near_item(sentence, item, _REPLACEMENT_WORD):
        return True
    for other in catalog_items_named(sentence):
        if other != item.strip().lower() and _word_near_item(sentence, other, _REPLACEMENT_WORD):
            return False
    return re.search(rf"\b{_item_pattern(item)}\b", sentence, re.IGNORECASE) is not None


def asks_for_exception(sentence: str) -> bool:
    """True when the sentence asks to break a rule: damage, loss, theft, or an early replacement."""
    return _EXCEPTION.search(sentence) is not None


def ordinary_catalog_request(sentence: str) -> str | None:
    """The named item when this is an ordinary catalog request, not an exception or an unclear sentence."""
    if asks_for_exception(sentence):
        return None
    return catalog_item(sentence)


def reflect_on_draft(decision: str, eligibility: dict | None, sentence: str = "") -> dict:
    """Return whether the draft matches the tool result.

    An escalation stays only when the sentence names no catalog item, or it asks for an exception.
    An exception is escalated even when eligibility is too_soon. An ordinary catalog request
    is approved or denied from the eligibility result.
    Approved and denied are confirmed only when an eligibility result is present and matches.
    """
    if asks_for_exception(sentence) and decision != "escalated":
        return {
            "confirmed": False,
            "note": (
                f"Rejected. The draft says {decision}, but the sentence asks for an exception. "
                "The only decision is escalated. Call flag_for_human_review."
            ),
        }
    if sentence and catalog_item(sentence) is None and decision != "escalated":
        return {
            "confirmed": False,
            "note": (
                f"Rejected. The draft says {decision}, but the sentence names no catalog item. "
                "The only decision is escalated. Call flag_for_human_review."
            ),
        }
    item = ordinary_catalog_request(sentence)
    if decision == "escalated" and item:
        if eligibility is None:
            return {
                "confirmed": False,
                "note": (
                    f"Rejected. The draft says escalated, but the sentence names {item} "
                    "and does not ask for an exception. Call check_request_eligibility before deciding."
                ),
            }
        expected = decision_from_eligibility(eligibility, sentence)
        if expected != "escalated":
            reason = eligibility.get("reason")
            return {
                "confirmed": False,
                "note": (
                    f"Rejected. The draft says escalated, but the sentence names {item} "
                    f"and eligibility reason is {reason}. The decision is {expected}."
                ),
            }
    if decision in {"approved", "denied"} and eligibility is None:
        return {
            "confirmed": False,
            "note": (
                f"Rejected. The draft says {decision}, but check_request_eligibility was not called. "
                "Call that tool before approving or denying."
            ),
        }
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


def correction_note(draft: str, decision: str, eligibility: dict | None, sentence: str = "") -> str:
    """Say how a rejected draft was replaced, in agreement with the final decision."""
    if asks_for_exception(sentence) and decision == "escalated":
        return f"The draft said {draft}. The sentence asks for an exception, so the decision is escalated."
    if sentence and catalog_item(sentence) is None and decision == "escalated":
        return f"The draft said {draft}. The sentence names no catalog item, so the decision is escalated."
    if not eligibility:
        return f"The draft said {draft}. No eligibility result was available, so the decision is {decision}."
    if decision == "approved":
        item = eligibility.get("item", "item")
        count = eligibility.get("count")
        maximum = eligibility.get("max_count")
        return (
            f"The draft said {draft}. The {item} is within policy "
            f"with count {count} of max {maximum}, so the decision is approved."
        )
    reason = eligibility.get("reason")
    return f"The draft said {draft}. Eligibility reason is {reason}, so the decision is {decision}."


def decision_text(decision: str, eligibility: dict | None, sentence: str = "") -> str:
    """The Decision block. The explanation states the same outcome as the first line."""
    if asks_for_exception(sentence) and decision == "escalated":
        return "Decision: escalated\nThe sentence asks for an exception, so a person must review it."
    if sentence and catalog_item(sentence) is None and decision == "escalated":
        return "Decision: escalated\nThe sentence names no catalog item."
    if not eligibility:
        if decision == "escalated":
            return "Decision: escalated\nNo eligibility check confirmed this request."
        return f"Decision: {decision}"
    item = eligibility.get("item", "item")
    reason = eligibility.get("reason")
    count = eligibility.get("count")
    maximum = eligibility.get("max_count")
    age = eligibility.get("age_years")
    if decision == "approved":
        age_clause = f" The newest {item} is {age} years old." if age is not None else ""
        return (
            f"Decision: approved\nThe {item} is within policy. Count is {count} of max {maximum}.{age_clause}"
        )
    if decision == "denied":
        return f"Decision: denied\nEligibility reason is {reason}."
    return f"Decision: escalated\nEligibility reason is {reason}."


def decision_from_eligibility(eligibility: dict | None, sentence: str = "") -> str:
    """The decision the eligibility observation supports.

    An exception in the sentence is escalated even when the tool says too_soon.
    """
    if asks_for_exception(sentence):
        return "escalated"
    if sentence and catalog_item(sentence) is None:
        return "escalated"
    if not eligibility:
        return "escalated"
    if eligibility.get("eligible") is True and eligibility.get("reason") == "within_policy":
        return "approved"
    if eligibility.get("reason") in {"too_soon", "at_limit", "terminated"}:
        return "denied"
    return "escalated"
