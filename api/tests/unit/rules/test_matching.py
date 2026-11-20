import pytest

from arzi.domain.enums import IrdaiList
from arzi.rules.matching import THRESHOLD, coverage_score, match_non_payable, mentions, normalise


def test_normalise_strips_punctuation_quantities_units_and_connectors() -> None:
    assert normalise("Crepe Bandage (10cm) x2 Nos.") == ("crepe", "bandage")
    assert normalise("Laundry charges - 3 nos @ 400") == ("laundry", "charges")
    assert normalise("Cold/Hot pack 500ml") == ("cold", "hot", "pack")
    assert normalise("Osteoarthritis of the knee") == ("osteoarthritis", "knee")
    assert normalise("") == ()


@pytest.mark.parametrize(
    ("description", "expected_list", "expected_item"),
    [
        ("Laundry", IrdaiList.I, "Laundry"),
        ("Laundry charges x3", IrdaiList.I, "Laundry"),
        ("LAUNDARY CHARGES", IrdaiList.I, "Laundry"),  # spelling variant
        ("Cold pack / hot pack", IrdaiList.I, "Cold pack / hot pack"),
        ("Crepe bandage 10 cm", IrdaiList.I, "Crepe bandage"),
        ("Registration charges", IrdaiList.IV, "Admission / registration charges"),
        ("Admission charges", IrdaiList.IV, "Admission / registration charges"),
    ],
)
def test_matches_reference_items(
    description: str, expected_list: IrdaiList, expected_item: str
) -> None:
    match = match_non_payable(description)
    assert match is not None
    assert match.item.list is expected_list
    assert match.item.item == expected_item
    assert match.score >= THRESHOLD


@pytest.mark.parametrize(
    "description",
    ["Charges", "Surgeon fees", "Pharmacy", "Admission kit", "Room charges", "Bandage", "", "..."],
)
def test_generic_or_unrelated_lines_do_not_match(description: str) -> None:
    assert match_non_payable(description) is None


def test_earlier_entry_wins_a_tie() -> None:
    match = match_non_payable("Cold pack hot pack")
    assert match is not None
    assert match.alias == "cold pack"


def test_coverage_score() -> None:
    assert coverage_score((), ("a",)) == 0.0
    assert coverage_score(("a",), ()) == 0.0
    assert coverage_score(("laundry",), ("laundry", "charges")) == 100.0


def test_mentions_conditions_in_diagnosis_or_procedure() -> None:
    texts = ("Primary osteoarthritis, right knee", "Right total knee replacement")
    assert mentions("Osteoarthritis of knee", texts)
    assert mentions("knee replacement", texts)
    assert not mentions("Cataract", texts)
    assert not mentions("Osteoarthritis of hip", texts)
    assert not mentions("Cataract", ())
