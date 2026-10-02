import json

from equipment_agent import tools


def test_known_role_returns_its_limits():
    assert tools.get_policy_limits("standard") == {
        "role": "standard",
        "limits": {
            "monitor": {"max_count": 2, "refresh_years": 3},
            "laptop": {"max_count": 1, "refresh_years": 4},
        },
    }


def test_contractor_monitors_are_not_offered():
    limits = tools.get_policy_limits("contractor")["limits"]

    assert limits["monitor"] == {"max_count": 0, "refresh_years": None}
    assert limits["laptop"] == {"max_count": 1, "refresh_years": 4}


def test_unknown_role():
    assert tools.get_policy_limits("intern") == {
        "role": "intern",
        "error": "unknown_role",
    }


def test_reads_the_patched_policy_file(tmp_path, monkeypatch):
    policies = {"vendor": {"laptop": {"max_count": 1, "refresh_years": 5}}}
    (tmp_path / "policies.json").write_text(json.dumps(policies))
    monkeypatch.setattr(tools, "DATA_DIR", tmp_path)

    assert tools.get_policy_limits("vendor")["limits"]["laptop"]["refresh_years"] == 5
    assert tools.get_policy_limits("standard") == {
        "role": "standard",
        "error": "unknown_role",
    }
