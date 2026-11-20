import pytest

from arzi.domain.enums import CitationStatus, IrdaiList
from arzi.rules.reference import citations, index_citations, non_payable_items

# Status marks exactly as in docs/context/03_DOMAIN_RULES_IRDAI.md. Changing one is a
# regulatory change and needs the owner's sign-off.
EXPECTED_STATUS = {
    "IRDAI_MC_2024": CitationStatus.VERIFIED,
    "IRDAI_CASHLESS_TAT": CitationStatus.VERIFY,
    "IRDAI_PROP_DED_2020": CitationStatus.VERIFIED,
    "IRDAI_PED_36M": CitationStatus.VERIFIED,
    "IRDAI_MORATORIUM_60M": CitationStatus.VERIFIED,
    "IRDAI_NON_PAYABLE_ANNEX_I": CitationStatus.VERIFY,
    "INSURER_GRIEVANCE_15D": CitationStatus.VERIFY,
    "OMBUDSMAN_RULES_2017": CitationStatus.VERIFIED,
    "BIMA_BHAROSA": CitationStatus.VERIFIED,
}


def test_citation_whitelist_matches_the_domain_brief() -> None:
    assert {cid: c.status for cid, c in citations().items()} == EXPECTED_STATUS


def test_circular_numbers_are_the_ones_in_the_brief() -> None:
    assert "IRDAI/HLT/CIR/PRO/84/5/2024" in citations()["IRDAI_MC_2024"].ref
    assert "IRDAI/HLT/REG/CIR/151/06/2020" in citations()["IRDAI_PROP_DED_2020"].ref


def test_no_citation_carries_an_unverified_url() -> None:
    assert all(c.url is None for c in citations().values())


def test_duplicate_citation_ids_are_rejected() -> None:
    entry = citations()["BIMA_BHAROSA"]
    with pytest.raises(ValueError, match="duplicate"):
        index_citations((entry, entry))


def test_non_payable_lists_have_the_printed_sizes_and_stay_unverified() -> None:
    items = non_payable_items()
    sizes = {name: sum(1 for i in items if i.list is name) for name in IrdaiList}
    assert sizes == {IrdaiList.I: 68, IrdaiList.II: 37, IrdaiList.III: 23, IrdaiList.IV: 18}
    for name in IrdaiList:
        numbers = [i.number for i in items if i.list is name]
        assert numbers == list(range(1, len(numbers) + 1))
    # Verified only after a person reviews the parsed list against the scan.
    assert all(item.status is CitationStatus.VERIFY for item in items)
    assert all("Annexure I" in item.source for item in items)


@pytest.mark.parametrize(
    ("item", "expected"),
    [
        ("BABY FOOD", IrdaiList.I),
        ("BEAUTY SERVICES", IrdaiList.I),
        ("LAUNDRY CHARGES", IrdaiList.I),
        ("COLD PACK/HOT PACK", IrdaiList.I),
        ("CREPE BANDAGE", IrdaiList.I),
        ("ADMISSION/REGISTRATION CHARGES", IrdaiList.IV),
    ],
)
def test_items_named_in_the_domain_brief_are_on_the_expected_list(
    item: str, expected: IrdaiList
) -> None:
    assert {i.item: i.list for i in non_payable_items()}[item] is expected


def test_every_alias_names_something_specific() -> None:
    generic = {"charges", "charge", "cost", "costs", "expenses", "etc", "any"}
    for item in non_payable_items():
        for alias in item.aliases:
            assert any(w not in generic and len(w) > 2 for w in alias.split()), alias
