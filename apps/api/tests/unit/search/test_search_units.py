import uuid
from decimal import Decimal

import pytest

from app.search.embed_text import embedding_text
from app.search.service import close_enough, decode_cursor, encode_cursor, fuse
from app.search.text import search_terms, to_tsquery
from tests.support.samples import sample_truth

INVOICE = sample_truth("synthetic-invoice-001")["data"]
RECEIPT = sample_truth("synthetic-receipt-001")["data"]


def test_ac2_terms_split_punctuation_and_keep_squashed_numbers() -> None:
    terms = search_terms(
        {"invoice_number": "INV/2026-27/0142", "total": {"amount": Decimal("16826.8")}}
    )

    assert "INV 2026 27 0142" in terms
    assert "INV2026270142" in terms
    assert "16826 80" in terms


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("Kaver", "kaver:*"),
        ("INV/2026-27/0142", "(inv:* & 2026:* & 27:* & 0142:*) | inv2026270142:*"),
        ("29ABCDE 1234F1Z5", "(29abcde:* & 1234f1z5:*) | 29abcde1234f1z5:*"),
        ("a", None),
        ("  ", None),
        ("!!", None),
    ],
)
def test_ac2_queries_are_prefix_matches_and_also_tried_squashed(
    query: str, expected: str | None
) -> None:
    assert to_tsquery(query) == expected


def test_ac3_rrf_rewards_documents_in_both_lists() -> None:
    a, b, c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()

    assert fuse([a, b], [c, b]) == [b, a, c]
    assert fuse([a], []) == [a]


def test_cursor_round_trip_and_rejects_others() -> None:
    assert decode_cursor(encode_cursor(40)) == 40
    with pytest.raises(ValueError, match=r"."):
        decode_cursor(encode_cursor(10_000))
    with pytest.raises(ValueError, match=r"."):
        decode_cursor("bm9wZQ==")


def test_d3_embedding_text_reads_like_a_sentence() -> None:
    text = embedding_text("invoice", INVOICE)

    assert text.startswith("Invoice SYN/2026-27/0142; from Kaveri Fasteners Private Limited (")
    assert "items: " in text
    assert "total INR 16,826.80" in text
    assert "dated 2026-08-14" in text
    assert embedding_text("receipt", RECEIPT).startswith("Receipt ")


def test_meaning_keeps_documents_close_to_the_best_and_never_far() -> None:
    a, b, c, d = (uuid.uuid4() for _ in range(4))

    assert close_enough([(a, 0.30), (b, 0.33), (c, 0.36), (d, 0.50)]) == [a, b]
    assert close_enough([(a, 0.44), (b, 0.46)]) == [a]  # the absolute cap still applies
    assert close_enough([(a, 0.47)]) == []
    assert close_enough([]) == []
