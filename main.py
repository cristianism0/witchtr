import argparse
import logging
from logging.handlers import QueueHandler, QueueListener
from multiprocessing import Pool, Queue
from pathlib import Path
from typing import TypedDict

from numpy import floating

from src.output import json_from_image, json_from_pdf
from src.pipe import WordConf, mean_conf, page_conf_text, page_text
from src.utils import dir_creator, dispatcher, path_collector


class PdfContent(TypedDict):
    page: int
    text: bytes | str | dict[str, str | bytes]
    mean_page: float | floating
    low_words: list[WordConf]


def get_args():
    parser = argparse.ArgumentParser(
        prog="WitcHTR - OCR Pipeline",
        description="""Pipeline using OCR with Pytesseract to collect text from files.\n
        Supported types: .pdf, .txt, .tiff, .jpeg, .png""",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    # group = parser.add_mutually_exclusive_group(required=True)
    _ = parser.add_argument(
        "input_pos",
        nargs="?",
        default=None,
        help="The directory or file that will be read (positional, opcional).",
    )
    _ = parser.add_argument(
        "-i",
        "--input",
        help="The directory of file that will be read.",
    )
    _ = parser.add_argument(
        "-o",
        "--output",
        default=None,
        help="The directory where the files will be saved.",
    )
    _ = parser.add_argument(
        "-r",
        "--recursive",
        action="store_true",
        default=False,
        help="Search all files inside all directories on the directory passed.",
    )
    _ = parser.add_argument(
        "-ascii",
        "--ensure-ascii",
        action="store_true",
        default=False,
        help="Generate a JSON file with ASCII compatibility.",
    )
    _ = parser.add_argument(
        "--ext",
        default="jpeg",
        help="All .pdf file will be converted to pages with this extension.",
    )
    _ = parser.add_argument(
        "--dispatch",
        default="data/dispatch",
        help="All .pdf converted pages will be send to this selected directory. Will be created if does not exists.",
    )
    _ = parser.add_argument(
        "-p",
        "--precision",
        type=float,
        default=60.0,
        help="Minimum confidence for words.",
    )
    _ = parser.add_argument(
        "-w",
        "--workers",
        type=int,
        default=4,
        help="Number of cores for multiprocessing.",
    )
    _ = parser.add_argument(
        "--dpi",
        type=int,
        default=300,
        help="DPI for image convertion.",
    )

    args = parser.parse_args()
    args.input = args.input or args.input_pos

    if args.input is None:
        parser.error("You need to pass an input file/directory using -i.")

    return args


def multi_init(log_queue: Queue):
    """
    Initilize the logging queue. All files logs will be send to this place.
    """
    queue_handler = QueueHandler(log_queue)
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(queue_handler)


def process_file(fargs: tuple[Path, Path, Path, str, float, bool, dpi]):
    """
    Pipeline function, all arguments are received in the Pool:
        - Log each action on each process
        - Manage dispatch
        - Create the JSON file with contents
    """
    f, dispatch_path, output_path, ext, precision, ensure_ascii, dpi = fargs
    logger = logging.getLogger(__name__)
    try:
        logger.info(f"processing file {f.name}.")
        img_p, suffix = dispatcher(file=f, dispatch_dir=dispatch_path, ext=ext)
        if suffix == ".pdf":
            pdf_content: list[PdfContent] = []
            for i, page in enumerate(img_p):
                conf, low_words = page_conf_text(
                    file_path=page, min_word_conf=precision
                )
                conf_values = [item["confidence"] for item in conf]
                mean = mean_conf(conf_values)
                text = page_text(page)

                pdf_content.append(
                    {
                        "page": i,
                        "text": text,
                        "mean_page": mean,
                        "low_words": low_words,
                    }
                )
                if mean <= precision:
                    logger.warning(
                        f"file {f.name}: page {i} with mean confidence lower than {precision}"
                    )

            _ = json_from_pdf(
                file_path=f,
                output_path=output_path,
                pages=pdf_content,
                ensure_ascii=ensure_ascii,
            )
            logger.info(f"file {f.name} was processed with {len(pdf_content)} pages.")

        else:
            conf, low_words = page_conf_text(file_path=f, min_word_conf=precision)
            conf_values = [item["confidence"] for item in conf]
            mean = mean_conf(conf_values)
            text = page_text(f)
            if mean <= precision:
                logger.warning(f"{f.name}: with mean {mean:.2f} lower than {precision}")

            _ = json_from_image(
                file_path=f,
                output_path=output_path,
                text=text,
                mean_confidence=mean,
                low_confidence_words=low_words,
                ensure_ascii=ensure_ascii,
            )
            logger.info(f"file {f.name} was processed.")
    except Exception as e:
        logger.error(f"failed to process the file {f.name}: {e}.")


def main():
    args = get_args()
    print(args)
    input_path = Path(args.input)
    output_path = (
        dir_creator(Path("."))
        if args.output is None
        else dir_creator(Path(args.output))
    )
    output_path.mkdir(parents=True, exist_ok=True)
    dispatch_path = Path(args.dispatch)
    dispatch_path.mkdir(parents=True, exist_ok=True)

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(logging.INFO)
    stream_handler.setFormatter(fmt)
    file_handler = logging.FileHandler(output_path / "pipeline.log", encoding="utf-8")
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(fmt)

    log_queue = Queue()
    listener = QueueListener(
        log_queue,
        stream_handler,
        file_handler,
        respect_handler_level=True,
    )
    listener.start()

    multi_init(log_queue)
    logger = logging.getLogger(__name__)

    # program start
    logger.info("program started")
    data_paths = path_collector(input_path=input_path, recursive=args.recursive)
    logger.info(f"{len(data_paths)} files found.")

    p_args = [
        (
            f,
            dispatch_path,
            output_path,
            args.ext,
            args.precision,
            args.ensure_ascii,
            args.dpi,
        )
        for f in data_paths
    ]

    with Pool(
        processes=args.workers,
        initializer=multi_init,
        initargs=(log_queue,),
    ) as pool:
        _ = pool.map(process_file, p_args)

    logger.info("pipeline finished.")
    listener.stop()


if __name__ == "__main__":
    main()
