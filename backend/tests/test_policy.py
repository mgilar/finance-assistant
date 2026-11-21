import pytest

from app.policy import load_policy


@pytest.fixture(scope="module")
def policy():
    return load_policy()


def test_header_metadata(policy):
    assert policy.label == "FIN-POL-014 v3.2 (effective 01-Jan-2025)"


def test_all_units_parsed_in_order(policy):
    assert list(policy.units) == [
        "1", "2.1", "2.2", "2.3", "3", "3.1", "4.1", "4.2", "4.3",
        "5.1", "5.2", "6.1", "7.1", "7.2", "8.1", "8.2", "9.1",
    ]


def test_threshold_table_is_its_own_unit(policy):
    table = policy.units["3"]
    assert table.title == "Approval Thresholds"
    assert "50,000.01 – 250,000 | Finance Director" in table.text


def test_clause_keeps_section_title(policy):
    assert policy.units["4.1"].title == "Vendor Management"
    assert "ACTIVE" in policy.units["4.1"].text


def test_prompt_rendering_tags_every_unit(policy):
    rendered = policy.render_for_prompt()
    for uid in policy.units:
        assert f"[§{uid}]" in rendered
