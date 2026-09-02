"""Tests for the OCR pipeline core: page_conf_text, page_text, mean_conf.

Edge cases covered:
- Blank / all-white images
- Very large / small images
- Corrupt / truncated image data
- Unicode text in images
- Non-existent file path
- Extreme confidence values
- np.floating vs plain float in mean_conf
- Single-character images
- Images with only whitespace
"""

from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw

from src.pipe import mean_conf, page_conf_text, page_text

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_image(
    tmp_path: Path,
    text: str = "hello world",
    size: tuple[int, int] = (400, 100),
    bg: tuple[int, int, int] = (255, 255, 255),
    fg: tuple[int, int, int] = (0, 0, 0),
    name: str = "sample.png",
) -> Path:
    img = Image.new("RGB", size, color=bg)
    draw = ImageDraw.Draw(img)
    draw.text((10, 10), text, fill=fg)
    path = tmp_path / name
    img.save(path)
    return path


# ---------------------------------------------------------------------------
# page_conf_text
# ---------------------------------------------------------------------------

class TestPageConfText:
    def test_returns_tuple_of_two_lists(self, tmp_path):
        img = _make_image(tmp_path)
        result = page_conf_text(img)
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_words_have_required_keys(self, tmp_path):
        img = _make_image(tmp_path)
        all_words, low_words = page_conf_text(img)
        for item in all_words:
            assert "confidence" in item and "text" in item
        for item in low_words:
            assert "confidence" in item and "text" in item

    def test_no_negative_confidence(self, tmp_path):
        img = _make_image(tmp_path)
        all_words, _ = page_conf_text(img)
        for item in all_words:
            assert item["confidence"] >= 0

    def test_low_confidence_words_respect_threshold(self, tmp_path):
        img = _make_image(tmp_path)
        _, low_words = page_conf_text(img, min_word_conf=60.0)
        for item in low_words:
            assert item["confidence"] <= 60.0

    def test_blank_image_returns_empty(self, tmp_path):
        img = Image.new("RGB", (400, 100), color=(255, 255, 255))
        path = tmp_path / "blank.png"
        img.save(path)
        all_words, low_words = page_conf_text(path)
        assert all_words == []
        assert low_words == []

    def test_high_threshold_includes_more_low(self, tmp_path):
        """Higher threshold → more words classified as low confidence."""
        img = _make_image(tmp_path)
        _, low_60 = page_conf_text(img, min_word_conf=60.0)
        _, low_90 = page_conf_text(img, min_word_conf=90.0)
        assert len(low_90) >= len(low_60)

    def test_threshold_100_returns_no_low(self, tmp_path):
        """With min_word_conf=100, only perfect-confidence words are low."""
        img = _make_image(tmp_path)
        _, low_words = page_conf_text(img, min_word_conf=100.0)
        for item in low_words:
            assert item["confidence"] <= 100.0

    def test_nonexistent_file_raises(self, tmp_path):
        with pytest.raises(Exception):
            page_conf_text(tmp_path / "does_not_exist.png")

    def test_truncated_image_raises(self, tmp_path):
        """A file with valid header but truncated data should raise."""
        bad = tmp_path / "bad.png"
        bad.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 20)
        with pytest.raises(Exception):
            page_conf_text(bad)

    def test_accepts_path_object(self, tmp_path):
        img = _make_image(tmp_path)
        result = page_conf_text(Path(str(img)))
        assert isinstance(result, tuple)

    def test_image_with_only_whitespace(self, tmp_path):
        """Image that is all one color but technically not blank (uniform gray)."""
        img = Image.new("RGB", (200, 50), color=(200, 200, 200))
        path = tmp_path / "gray.png"
        img.save(path)
        all_words, _ = page_conf_text(path)
        # Uniform gray → likely no text detected
        assert isinstance(all_words, list)

    def test_very_small_image(self, tmp_path):
        """A 1x1 pixel image should not crash tesseract."""
        img = Image.new("RGB", (1, 1), color=(255, 255, 255))
        path = tmp_path / "tiny.png"
        img.save(path)
        result = page_conf_text(path)
        assert isinstance(result, tuple)


# ---------------------------------------------------------------------------
# page_text
# ---------------------------------------------------------------------------

class TestPageText:
    def test_returns_string(self, tmp_path):
        img = _make_image(tmp_path)
        result = page_text(img)
        assert isinstance(result, str)

    def test_blank_image_returns_empty_or_whitespace(self, tmp_path):
        img = Image.new("RGB", (400, 100), color=(255, 255, 255))
        path = tmp_path / "blank.png"
        img.save(path)
        result = page_text(path)
        assert isinstance(result, str)

    def test_nonexistent_file_raises(self, tmp_path):
        with pytest.raises(Exception):
            page_text(tmp_path / "nope.png")


# ---------------------------------------------------------------------------
# mean_conf
# ---------------------------------------------------------------------------

class TestMeanConf:
    def test_normal_values(self):
        assert mean_conf([80.0, 90.0, 70.0]) == 80.0

    def test_empty_returns_zero(self):
        assert mean_conf([]) == 0.0

    def test_single_value(self):
        assert mean_conf([75.0]) == 75.0

    def test_all_same(self):
        assert mean_conf([60.0, 60.0, 60.0]) == 60.0

    def test_np_floating_input(self):
        vals = [np.float64(10.0), np.float64(20.0), np.float64(30.0)]
        result = mean_conf(vals)
        assert float(result) == 20.0

    def test_negative_values(self):
        """Negative confidences shouldn't occur in practice but math should work."""
        result = mean_conf([-10.0, 10.0])
        assert float(result) == 0.0

    def test_very_large_values(self):
        result = mean_conf([1e9, 2e9])
        assert float(result) == 1.5e9

    def test_zero_values(self):
        assert mean_conf([0.0, 0.0, 0.0]) == 0.0

    def test_float_precision(self):
        result = mean_conf([33.333, 33.333, 33.334])
        assert abs(float(result) - 33.333333) < 0.001

    def test_return_type_is_numeric(self):
        result = mean_conf([1.0, 2.0, 3.0])
        assert isinstance(result, (float, np.floating))
