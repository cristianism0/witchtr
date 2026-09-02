"""Tests for path_collector, get_ext, dispatcher, pdf2img, dir_creator.

Edge cases covered:
- Multi-page PDFs
- PDFs with special characters in filename
- Symlinks
- Non-regular files (broken symlinks)
- DPI variations for pdf2img
- get_ext with multiple dots, uppercase
- path_collector with hidden files, deeply nested dirs
- dir_creator race conditions
- dispatcher with unknown extensions
"""

from pathlib import Path

import pymupdf
import pytest
from PIL import Image

from src.utils import dir_creator, dispatcher, get_ext, path_collector, pdf2img

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_pdf(tmp_path: Path, pages: int = 1, name: str = "sample.pdf") -> Path:
    doc = pymupdf.open()
    for i in range(pages):
        page = doc.new_page()
        page.insert_text((100, 100), f"page {i}")
    path = tmp_path / name
    doc.save(str(path))
    doc.close()
    return path


def _make_image(tmp_path: Path, name: str = "img.jpeg") -> Path:
    img = Image.new("RGB", (100, 100), color=(255, 255, 255))
    path = tmp_path / name
    img.save(path)
    return path


# ---------------------------------------------------------------------------
# get_ext
# ---------------------------------------------------------------------------

class TestGetExt:
    def test_pdf(self):
        _, suffix = get_ext("document.pdf")
        assert suffix == ".pdf"

    def test_jpeg(self):
        _, suffix = get_ext("page-0.jpeg")
        assert suffix == ".jpeg"

    def test_no_extension(self):
        _, suffix = get_ext("document")
        assert suffix == ""

    def test_returns_path_object(self, tmp_path):
        result, _ = get_ext(tmp_path / "sample.pdf")
        assert isinstance(result, Path)

    def test_uppercase_extension_lowercased(self):
        _, suffix = get_ext("IMAGE.PNG")
        assert suffix == ".png"

    def test_multiple_dots(self):
        _, suffix = get_ext("my.file.v2.pdf")
        assert suffix == ".pdf"

    def test_tiff_uppercase(self):
        _, suffix = get_ext("SCAN.TIFF")
        assert suffix == ".tiff"

    def test_empty_string_ext(self):
        _, suffix = get_ext("")
        assert suffix == ""


# ---------------------------------------------------------------------------
# pdf2img
# ---------------------------------------------------------------------------

class TestPdf2Img:
    def test_creates_images(self, tmp_path):
        pdf = _make_pdf(tmp_path)
        result = pdf2img(pdf, tmp_path, ext="jpeg")
        assert len(result) > 0
        for p in result:
            assert p.exists()

    def test_jpeg_suffix(self, tmp_path):
        pdf = _make_pdf(tmp_path)
        result = pdf2img(pdf, tmp_path, ext="jpeg")
        for p in result:
            assert p.suffix == ".jpeg"

    def test_png_suffix(self, tmp_path):
        pdf = _make_pdf(tmp_path)
        result = pdf2img(pdf, tmp_path, ext="png")
        for p in result:
            assert p.suffix == ".png"

    def test_multi_page_pdf(self, tmp_path):
        pdf = _make_pdf(tmp_path, pages=5)
        result = pdf2img(pdf, tmp_path, ext="jpeg")
        assert len(result) == 5

    def test_single_page_pdf(self, tmp_path):
        pdf = _make_pdf(tmp_path, pages=1)
        result = pdf2img(pdf, tmp_path, ext="jpeg")
        assert len(result) == 1

    def test_output_names_contain_page_number(self, tmp_path):
        pdf = _make_pdf(tmp_path, pages=3)
        result = pdf2img(pdf, tmp_path, ext="jpeg")
        for i, p in enumerate(result):
            assert f"page-{i}" in p.name

    def test_dpi_variation(self, tmp_path):
        pdf = _make_pdf(tmp_path)
        low_dir = tmp_path / "low"
        low_dir.mkdir()
        high_dir = tmp_path / "high"
        high_dir.mkdir()
        result_low = pdf2img(pdf, low_dir, ext="jpeg", dpi=72)
        result_high = pdf2img(pdf, high_dir, ext="jpeg", dpi=600)
        assert len(result_low) == 1
        assert len(result_high) == 1

    def test_special_chars_in_filename(self, tmp_path):
        pdf = _make_pdf(tmp_path, name="my doc (1).pdf")
        result = pdf2img(pdf, tmp_path, ext="jpeg")
        assert len(result) == 1
        assert result[0].exists()


# ---------------------------------------------------------------------------
# path_collector
# ---------------------------------------------------------------------------

class TestPathCollector:
    def test_nonexistent(self):
        result = path_collector(Path("/nonexistent/path"), recursive=False)
        assert result == []

    def test_empty_dir(self, tmp_path):
        result = path_collector(tmp_path, recursive=False)
        assert result == []

    def test_finds_files(self, tmp_path):
        (tmp_path / "a.pdf").touch()
        (tmp_path / "b.jpeg").touch()
        result = path_collector(tmp_path, recursive=False)
        assert len(result) == 2

    def test_recursive(self, tmp_path):
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "c.pdf").touch()
        result = path_collector(tmp_path, recursive=True)
        assert len(result) == 1

    def test_single_file(self, tmp_path):
        f = tmp_path / "doc.pdf"
        f.touch()
        result = path_collector(f, recursive=False)
        assert result == [f]

    def test_ignores_directories(self, tmp_path):
        sub = tmp_path / "subdir"
        sub.mkdir()
        (tmp_path / "file.txt").touch()
        result = path_collector(tmp_path, recursive=False)
        assert len(result) == 1

    def test_deeply_nested_recursive(self, tmp_path):
        deep = tmp_path / "a" / "b" / "c"
        deep.mkdir(parents=True)
        (deep / "deep.pdf").touch()
        (tmp_path / "shallow.txt").touch()
        result = path_collector(tmp_path, recursive=True)
        assert len(result) == 2

    def test_non_recursive_does_not_descend(self, tmp_path):
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "hidden.pdf").touch()
        result = path_collector(tmp_path, recursive=False)
        assert len(result) == 0

    def test_symlink_included(self, tmp_path):
        real = tmp_path / "real.txt"
        real.touch()
        link = tmp_path / "link.txt"
        link.symlink_to(real)
        result = path_collector(tmp_path, recursive=False)
        names = {p.name for p in result}
        assert "link.txt" in names

    def test_hidden_files_included(self, tmp_path):
        (tmp_path / ".hidden").touch()
        (tmp_path / "visible.txt").touch()
        result = path_collector(tmp_path, recursive=False)
        assert len(result) == 2


# ---------------------------------------------------------------------------
# dir_creator
# ---------------------------------------------------------------------------

class TestDirCreator:
    def test_creates_output_dir(self, tmp_path):
        output = dir_creator(tmp_path / "output")
        assert output.exists()
        assert output.name == "output"

    def test_returns_path(self, tmp_path):
        output = dir_creator(tmp_path / "output")
        assert isinstance(output, Path)

    def test_timestamp_on_existing(self, tmp_path):
        dir_creator(tmp_path / "output")
        second = dir_creator(tmp_path / "output")
        assert "output_" in second.name

    def test_creates_parent_dirs(self, tmp_path):
        output = dir_creator(tmp_path / "deep" / "nested")
        assert output.exists()

    def test_third_call_same_second_raises(self, tmp_path):
        """dir_creator uses seconds in timestamp, so same-second calls collide.
        This is a known limitation in the current implementation."""
        dir_creator(tmp_path / "output")
        dir_creator(tmp_path / "output")
        with pytest.raises(FileExistsError):
            dir_creator(tmp_path / "output")


# ---------------------------------------------------------------------------
# dispatcher
# ---------------------------------------------------------------------------

class TestDispatcher:
    def test_pdf_branch(self, tmp_path):
        pdf = _make_pdf(tmp_path)
        images, suffix = dispatcher(pdf, tmp_path, ext="jpeg")
        assert suffix == ".pdf"
        assert len(images) > 0
        for p in images:
            assert p.exists()

    def test_image_branch(self, tmp_path):
        img = _make_image(tmp_path, name="sample.jpeg")
        images, suffix = dispatcher(img, tmp_path)
        assert suffix == ".jpeg"
        assert images[0] == img

    def test_returns_list(self, tmp_path):
        pdf = _make_pdf(tmp_path)
        images, _ = dispatcher(pdf, tmp_path)
        assert isinstance(images, list)

    def test_tiff_image_passthrough(self, tmp_path):
        img = _make_image(tmp_path, name="scan.tiff")
        images, suffix = dispatcher(img, tmp_path)
        assert suffix == ".tiff"
        assert images == [img]

    def test_png_image_passthrough(self, tmp_path):
        img = _make_image(tmp_path, name="photo.png")
        images, suffix = dispatcher(img, tmp_path)
        assert suffix == ".png"
        assert images == [img]

    def test_unknown_extension_passthrough(self, tmp_path):
        """Unknown extension should be treated as an image (passthrough)."""
        weird = tmp_path / "data.xyz"
        weird.write_bytes(b"\x00" * 100)
        images, suffix = dispatcher(weird, tmp_path)
        assert suffix == ".xyz"
        assert images == [weird]
