import pytest

from app.validation.gstin import check_character, has_valid_format, is_valid, with_valid_checksum

# Widely published sample GSTINs with valid check characters.
VALID = ["27AAPFU0939F1ZV", "29AAGCB7383J1Z4"]


@pytest.mark.parametrize("gstin", VALID)
def test_published_examples_are_valid(gstin: str) -> None:
    assert is_valid(gstin)


@pytest.mark.parametrize("gstin", VALID)
def test_one_wrong_character_breaks_the_checksum(gstin: str) -> None:
    misread = gstin[:8] + ("8" if gstin[8] != "8" else "9") + gstin[9:]

    assert has_valid_format(misread)
    assert not is_valid(misread)


def test_format_rules() -> None:
    assert not has_valid_format("27AAPFU0939F1Z")  # too short
    assert not has_valid_format("27aapfu0939f1zv")  # lowercase
    assert not has_valid_format("27AAPFU0939F0ZV")  # entity number can't be 0
    assert not is_valid("27AAPFU0939F1XV")  # 14th character must be Z


def test_completing_a_gstin() -> None:
    gstin = with_valid_checksum("29ABCDE1234F1Z")

    assert is_valid(gstin)
    assert gstin[:14] == "29ABCDE1234F1Z"
    assert check_character("27AAPFU0939F1Z") == "V"
