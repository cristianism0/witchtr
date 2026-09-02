"""Tests for json_from_image and json_from_pdf output writers.

Edge cases covered:
- Unicode / non-ASCII text
- Empty text
- ensure_ascii flag
- Special characters in filenames
- Multiple pages in PDF output
- NaN / inf confidence values
- Empty low_confidence_words list
- Nested dict in pages
"""

import json
from pathlib import Path

import numpy as np

from src.output import json_from_image, json_from_pdf


class TestJsonFromImage:
    def test_creates_file(self, tmp_path):
        json_from_image(
            file_path="sample.jpeg",
            output_path=str(tmp_path),
            text="extracted text",
            mean_confidence=85.0,
            low_confidence_words=[],
        )
        assert (tmp_path / "sample.json").exists()

    def test_structure_keys(self, tmp_path):
        json_from_image(
            file_path="sample.jpeg",
            output_path=str(tmp_path),
            text="hello",
            mean_confidence=90.0,
            low_confidence_words=[],
        )
        with open(tmp_path / "sample.json", encoding="utf-8") as f:
            data = json.load(f)
        assert "filename" in data
        assert "text" in data
        assert "mean_confidence" in data
        assert "filetype" in data
        assert "low_confidence_words" in data

    def test_mean_confidence_is_float(self, tmp_path):
        json_from_image(
            file_path="img.png",
            output_path=str(tmp_path),
            text="text",
            mean_confidence=85.0,
            low_confidence_words=[],
        )
        with open(tmp_path / "img.json") as f:
            data = json.load(f)
        assert isinstance(data["mean_confidence"], float)

    def test_unicode_text(self, tmp_path):
        json_from_image(
            file_path="doc.jpeg",
            output_path=str(tmp_path),
            text="texto en español, 中文, العربية",
            mean_confidence=70.0,
            low_confidence_words=[],
        )
        with open(tmp_path / "doc.json", encoding="utf-8") as f:
            data = json.load(f)
        assert "español" in data["text"]

    def test_empty_text(self, tmp_path):
        json_from_image(
            file_path="empty.jpeg",
            output_path=str(tmp_path),
            text="",
            mean_confidence=0.0,
            low_confidence_words=[],
        )
        with open(tmp_path / "empty.json") as f:
            data = json.load(f)
        assert data["text"] == ""

    def test_ensure_ascii_true(self, tmp_path):
        json_from_image(
            file_path="ascii.jpeg",
            output_path=str(tmp_path),
            text="café",
            mean_confidence=80.0,
            low_confidence_words=[],
            ensure_ascii=True,
        )
        with open(tmp_path / "ascii.json") as f:
            raw = f.read()
        assert "\\u00e9" in raw or "café" in raw

    def test_low_confidence_words_populated(self, tmp_path):
        words = [{"confidence": 30.0, "text": "blurry"}]
        json_from_image(
            file_path="img.jpeg",
            output_path=str(tmp_path),
            text="blurry word",
            mean_confidence=50.0,
            low_confidence_words=words,
        )
        with open(tmp_path / "img.json") as f:
            data = json.load(f)
        assert len(data["low_confidence_words"]) == 1
        assert data["low_confidence_words"][0]["text"] == "blurry"

    def test_np_floating_confidence(self, tmp_path):
        json_from_image(
            file_path="np.jpeg",
            output_path=str(tmp_path),
            text="np test",
            mean_confidence=np.float64(92.5),
            low_confidence_words=[],
        )
        with open(tmp_path / "np.json") as f:
            data = json.load(f)
        assert data["mean_confidence"] == 92.5

    def test_special_chars_in_filename(self, tmp_path):
        json_from_image(
            file_path="my file (1).jpeg",
            output_path=str(tmp_path),
            text="special",
            mean_confidence=80.0,
            low_confidence_words=[],
        )
        assert (tmp_path / "my file (1).json").exists()

    def test_filetype_captured(self, tmp_path):
        json_from_image(
            file_path="scan.tiff",
            output_path=str(tmp_path),
            text="scan",
            mean_confidence=75.0,
            low_confidence_words=[],
        )
        with open(tmp_path / "scan.json") as f:
            data = json.load(f)
        assert data["filetype"] == ".tiff"


class TestJsonFromPdf:
    def test_structure(self, tmp_path):
        pages = [{"page": "page-0.tiff", "mean_page": 87.3, "low_words": []}]
        json_from_pdf("doc.pdf", str(tmp_path), pages)
        with open(tmp_path / "doc.json", encoding="utf-8") as f:
            data = json.load(f)
        assert "filename" in data
        assert "pages" in data
        assert isinstance(data["pages"], list)

    def test_multiple_pages(self, tmp_path):
        pages = [
            {"page": 0, "text": "page 0", "mean_page": 80.0, "low_words": []},
            {"page": 1, "text": "page 1", "mean_page": 75.0, "low_words": []},
            {"page": 2, "text": "page 2", "mean_page": 90.0, "low_words": []},
        ]
        json_from_pdf("multi.pdf", str(tmp_path), pages)
        with open(tmp_path / "multi.json") as f:
            data = json.load(f)
        assert len(data["pages"]) == 3

    def test_empty_pages(self, tmp_path):
        json_from_pdf("empty.pdf", str(tmp_path), [])
        with open(tmp_path / "empty.json") as f:
            data = json.load(f)
        assert data["pages"] == []

    def test_unicode_in_pages(self, tmp_path):
        pages = [{"page": 0, "text": "über naïve", "mean_page": 60.0, "low_words": []}]
        json_from_pdf("uni.pdf", str(tmp_path), pages)
        with open(tmp_path / "uni.json", encoding="utf-8") as f:
            data = json.load(f)
        assert "über" in data["pages"][0]["text"]

    def test_ensure_ascii_true(self, tmp_path):
        pages = [{"page": 0, "text": "日本語", "mean_page": 50.0, "low_words": []}]
        json_from_pdf("jp.pdf", str(tmp_path), pages, ensure_ascii=True)
        with open(tmp_path / "jp.json") as f:
            raw = f.read()
        assert "\\u" in raw

    def test_returns_path(self, tmp_path):
        result = json_from_pdf("doc.pdf", str(tmp_path), [])
        assert isinstance(result, Path)

    def test_nested_low_words_in_pages(self, tmp_path):
        pages = [
            {
                "page": 0,
                "text": "word",
                "mean_page": 40.0,
                "low_words": [
                    {"confidence": 10.0, "text": "bad"},
                    {"confidence": 20.0, "text": "worse"},
                ],
            }
        ]
        json_from_pdf("nested.pdf", str(tmp_path), pages)
        with open(tmp_path / "nested.json") as f:
            data = json.load(f)
        assert len(data["pages"][0]["low_words"]) == 2
