from collections import Counter

from app.schemas_registry import validation_errors
from evals.paths import MANIFEST
from evals.runner import load_manifest, select


def test_ac1_manifest_valid_files_exist_licences_present() -> None:
    version, documents = load_manifest(MANIFEST)

    assert version == 1
    assert len(documents) >= 20
    assert len({d.id for d in documents}) == len(documents)
    for document in documents:
        assert document.path.is_file(), document.id
        assert document.path.stat().st_size < 500_000, document.id  # repo-friendly
    raw = MANIFEST.read_text()
    assert raw.count('"licence"') == len(documents)
    assert "CC BY 4.0" in raw


def test_ac1_every_truth_validates_against_its_schema() -> None:
    _, documents = load_manifest(MANIFEST)

    problems = {d.id: validation_errors(d.schema_id, d.truth) for d in documents}

    assert {k: v for k, v in problems.items() if v} == {}


def test_ac1_covers_three_types_and_both_formats() -> None:
    _, documents = load_manifest(MANIFEST)

    assert set(Counter(d.doc_type for d in documents)) == {"invoice", "receipt", "purchase_order"}
    assert {d.content_type for d in documents} == {"application/pdf", "image/jpeg"}
    assert {d.source for d in documents} == {"synthetic", "cord-v2"}


def test_small_samples_cover_every_source_and_type() -> None:
    _, documents = load_manifest(MANIFEST)

    sample = select(documents, 4)

    assert {(d.source, d.doc_type) for d in sample} == {
        ("cord-v2", "receipt"),
        ("synthetic", "invoice"),
        ("synthetic", "purchase_order"),
        ("synthetic", "receipt"),
    }
    assert select(documents, 4) == sample  # stable
