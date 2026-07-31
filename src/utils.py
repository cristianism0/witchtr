import logging
from datetime import datetime
from pathlib import Path

import pymupdf

logger = logging.getLogger(__name__)


def pdf2img(
    file_path: Path, output_dir: Path, ext: str = "jpeg", dpi: int = 300
) -> list[Path]:
    """
    Transform each line of a PDF into a image and return all images path:
    Image extensions: jpeg (default), tiff, png
    """
    ext = ext.strip().lower()
    doc = pymupdf.open(file_path)
    paths = []
    fname = file_path.name
    for page in doc:
        pix = page.get_pixmap(dpi=dpi)
        out = Path(output_dir) / f"{fname}_page-{page.number}.{ext}"
        pix.pil_save(out, format=ext, dpi=(dpi, dpi), quality=100)
        logger.info(f"image saved from {fname} with dpi={dpi} at {out}")
        paths.append(out)

    return paths


def get_ext(file_path: Path) -> tuple[Path, str]:
    """
    Collect the file extension - PDF or Tesseract/PymuPDF supported image.
    """
    file = Path(file_path)
    # tesseract can read file with no extension
    return file, file.suffix.lower()


def path_collector(input_path: Path, recursive: bool) -> list[Path]:
    """
    Walker recursivelly or not if its a directory and return all the files inside of it.
    """
    in_path = Path(input_path)

    if not in_path.exists():
        return []

    if in_path.is_dir():
        pattern = "**/*" if recursive else "*"
        logger.warning(
            f"pattern glob select {"'**/*' (recursive)" if recursive else "'*' (non-recursive)"}"
        )
        return [f for f in in_path.glob(pattern) if f.is_file()]
    else:
        return [in_path]


def dir_creator(output_path: Path) -> Path:
    """
    Create the ocr-pipe/output directory in path.
    """
    now = datetime.now()
    out = output_path / "output"

    if output_path.exists() and out.exists():
        out = output_path / f"output_{now.strftime('%y-%m-%d-%S')}"

    # out = base / "output"
    out.mkdir(parents=True)
    logger.info(f"output directory created at: {out}")
    return out


def dispatcher(
    file: Path, dispatch_dir: Path, ext: str = "jpeg", dpi: int = 300
) -> tuple[list[Path], str]:
    """
    If the file is a PDF -> converts to the select kind of image.
    If its a image, return the image path directly.
    """
    _, suffix = get_ext(file)
    if suffix == ".pdf":
        return pdf2img(file, dispatch_dir, ext=ext, dpi=dpi), suffix
    return [file], suffix
