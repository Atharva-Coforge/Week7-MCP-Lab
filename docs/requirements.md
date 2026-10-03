# Equipment request requirements

An employee submits a natural-language equipment request. The system looks up that employee's role, tenure, and current gear, checks the policy for that role, and returns one of three decisions: **approved**, **denied**, or **escalated**.

Role, status, tenure, and current equipment always come from the employee record. The sentence is not a source for those facts.

## Request fields


| Field             | Where it comes from                                     | Required                       |
| ----------------- | ------------------------------------------------------- | ------------------------------ |
| `employee_id`     | Submitted with the request                              | Yes                            |
| Reason            | The employee's sentence                                 | Yes                            |
| Role              | `employees.json`, via `get_employee_info`               | Looked up                      |
| Status            | `employees.json`, via `get_employee_info`               | Looked up                      |
| Tenure            | `employees.json`, via `get_employee_info`               | Looked up                      |
| Current equipment | `employees.json`, via `get_employee_info`               | Looked up                      |
| Item              | Named in the sentence, then checked against the catalog | Only if the sentence names one |


The catalog is `laptop`, `monitor`, `keyboard`, `webcam`, and `phone` (a company phone). Phrases such as "second monitor" and "laptop replacement" map to those items. A sentence that names none of them has no catalog item.

## Policy rules

Limits live in `data/policies.json`, keyed by role.


| Role         | Monitor                    | Laptop                       | Keyboard            | Webcam               | Phone                         |
| ------------ | -------------------------- | ---------------------------- | ------------------- | -------------------- | ----------------------------- |
| `standard`   | Up to 2, one every 3 years | 1, replacement every 4 years | 1, every 2 years    | 1, every 4 years     | None (`max_count` 0)          |
| `manager`    | Up to 2, one every 3 years | 1, replacement every 2 years | 1, every 2 years    | 1, every 3 years     | 1, every 2 years              |
| `contractor` | None (`max_count` 0)       | 1, replacement every 4 years | 1, every 2 years    | None (`max_count` 0) | None (`max_count` 0)          |


A request for an item is inside policy only when all of the following are true:

- The employee id exists.
- The employee status is `active`. A `terminated` record stops the check before the item rules run.
- The role exists in the policy file.
- The item is in the catalog for that role.
- After this request the employee would still be within `max_count`. A replacement of one unit keeps the count the same. An added unit increases the count by one. A numeral written immediately before the item is a quantity. Quantity above `max_count`, or owned count plus quantity above `max_count`, is outside the limit.
- The employee does not own that item yet, or the newest matching item is at least `refresh_years` old. Age is computed from `assigned_on`. It is not stored on the asset.

`check_request_eligibility` reports `eligible` and one reason code:


| Code               | Meaning                                                                                                                         |
| ------------------ | ------------------------------------------------------------------------------------------------------------------------------- |
| `within_policy`    | The item passes the count limit and the refresh window                                                                          |
| `too_soon`         | They own the item, and the newest one is younger than `refresh_years`                                                           |
| `at_limit`         | The requested quantity, or one more unit, would exceed `max_count`. A contractor monitor request uses this code, because that role is offered none. |
| `terminated`       | The employee status is `terminated`. Item and refresh rules are not applied.                                                    |
| `unknown_employee` | The employee id is not on file                                                                                                  |
| `unknown_role`     | The employee's role has no policy                                                                                               |
| `unknown_item`     | The item is not in the catalog                                                                                                  |




## Asset age

Each asset is stored the way an IT asset system stores it: an `asset_tag`, an `item`, and the date it was assigned (`assigned_on`). Policy keeps the refresh interval. The check computes age at decision time.

Age is the number of full years from `assigned_on` to the day the request is decided. On the assignment anniversary the year counts. The newest asset of a type is the one with the latest `assigned_on`. A live request uses that calendar day. Unit tests pass `2026-10-01` so the examples below stay checkable when the calendar moves.

When `max_count` is 0, `refresh_years` is null and the check does not use it.

## Decisions

Final answers are only `approved`, `denied`, or `escalated`.

- **Approve** when the sentence names a catalog item and eligibility is `within_policy`.
- **Deny** when eligibility is `terminated`, or when the sentence names a catalog item, asks for an ordinary refresh or addition (slow, old, "I need a second monitor"), and eligibility is `too_soon` or `at_limit`. A denial does not call `flag_for_human_review`.
- **Escalate** by calling `flag_for_human_review` in either ambiguous case below. The decision includes that tool's reason.



## What counts as ambiguous

The system escalates instead of deciding on its own in two cases:

1. **Unclear reason.** The sentence does not name a catalog item. Example: "Can I get new equipment? My setup isn't great." The agent does not guess whether they want a laptop or a monitor.
2. **Outside policy.** The sentence asks to break a rule the eligibility check enforces: damage, loss, theft, or an explicit early replacement. An ordinary "too soon" result becomes a denial. A request for an exception becomes an escalation, even when the tool would also return `too_soon`.

Anything the tools did not confirm stays undecided. The agent does not invent an approval to be helpful.

## Demonstration requests

These four records are in `data/employees.json`. The ages below are what the rules produce on 2026-10-01. A request decided on a later day uses that later day, so a laptop can cross its refresh window without a code change.


| Id   | Role     | Gear that matters                          | Sentence                                                                                | Expected decision                                                                 |
| ---- | -------- | ------------------------------------------ | --------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------- |
| E101 | standard | `MON-E101-1` assigned 2022-04-21 (4 years) | I need a second monitor.                                                                | Approved. Count would become 2, and 4 years meets the 3-year monitor rule.        |
| E102 | manager  | `LPT-E102-1` assigned 2025-12-01 (0 years) | My laptop is slow, can I get a replacement?                                             | Denied. Ordinary replacement, and the laptop is inside the 2-year manager window. |
| E103 | standard | Laptop and monitor on file                 | Can I get new equipment? My setup isn't great.                                          | Escalated. No catalog item is named.                                              |
| E104 | standard | `LPT-E104-1` assigned 2025-08-11 (1 year)  | I know my laptop is only 1 year old, but it was damaged. Can I get a replacement early? | Escalated. The sentence asks for an exception to the 4-year laptop window.        |


E101 keeps one monitor so a second monitor can still be approved. E102 and E103 each have two monitors, which is the role maximum. Their graded sentences are still the laptop denial and the unclear request.

E105 and E106 are contractors used to exercise that role. They are not extra demonstration runs. On 2026-10-01, Quinn Adler (`LPT-E105-1`, assigned 2022-06-18) is eligible for a laptop replacement. Casey Brooks (`LPT-E106-1`, assigned 2025-07-09) is inside the 4-year window. A monitor request for either person is `at_limit`.

E107, Morgan Ellis, is `terminated`. The laptop assigned on 2019-05-02 would otherwise be old enough for a standard replacement. Eligibility returns `terminated`, and the agent denies the request.

## Data files

- `data/employees.json` holds the synthetic people: id, name, role, status (`active` or `terminated`), tenure, and equipment (`asset_tag`, `item`, `assigned_on`).
- `data/policies.json` holds `max_count` and `refresh_years` for each role and catalog item.
- `data/escalations.jsonl` starts empty. `flag_for_human_review` appends one JSON object per escalation.

