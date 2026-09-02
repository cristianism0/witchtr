# WitcHTR - OCR Pipeline

A pipeline that extracts text from PDFs and images using Tesseract OCR, returning structured JSON output with confidence metrics per word and page. Available as a CLI tool and a REST API.

## What it does

**CLI:** Accepts a directory or file of PDFs/images, runs OCR via pyTesseract, and produces one JSON file per document with extracted text and confidence metrics.

**API:** A FastAPI service that accepts file uploads, processes them through the same OCR pipeline, stores results in PostgreSQL, and exposes job tracking and result retrieval endpoints.

```
input/
├── document.pdf
└── scan.jpeg

output/
├── document.json
└── scan.json
└── pipeline.log
```

## Pipeline
```
                                           ┌-> IMG            -> tesseract ┐
directory -> path_collector -> dispatcher                                JSON
                                           └-> PDF -> pdf2img -> tesseract ┘
```

1. **path_collector** — walks the input directory (recursively or not).
2. **dispatcher** — routes each file: PDF goes through `pdf2img`, images go directly to OCR.
3. **pdf2img** — converts each PDF page to an image via `pymupdf`.
4. **tesseract** — runs OCR via `pytesseract`, returning text and per-word confidence.
5. **output** — structures results and writes JSON to the output directory.

## JSON output structure

**PDF:**
```json
{
  "filename": "document.pdf",
  "pages": [
    {
      "page": 0,
      "text": "extracted text here",
      "mean_page": 87.3,
      "low_words": [
        {"confidence": 42.0, "text": "obscvro"}
      ]
    }
  ]
}
```

**Image:**
```json
{
  "filename": "scan.jpeg",
  "filetype": ".jpeg",
  "text": "extracted text here",
  "mean_confidence": 91.2,
  "low_confidence_words": []
}
```

## Requirements

- Python 3.14+
- [uv](https://docs.astral.sh/uv/) (*optional*)
- Tesseract — install via package manager
- PostgreSQL (*required for API only*)

```bash
# Debian/Ubuntu
sudo apt install tesseract-ocr

# Arch
sudo pacman -S tesseract-ocr

# macOS
brew install tesseract
```

## Installation

```bash
git clone https://github.com/cristianism0/ocr-pipeline
cd ocr-pipeline

# for uv
uv sync

# for python
pip install -r requirements/base.txt
```

### Requirements groups
There are 3 groups of requirements inside `requirements/` directory and `pyproject.toml`:

| Group | File | Description |
|-------|------|-------------|
| base | `requirements/base.txt` | CLI dependencies only (tesseract pipeline) |
| api | `requirements/api.txt` | API dependencies (FastAPI, SQLAlchemy, psycopg2) |
| dev | `requirements/dev.txt` | All dependencies including dev tools (pytest, ruff) |

For CLI usage, install `base.txt`. For the API, install `api.txt`. For development, install `dev.txt` or use `uv sync --group dev`.

### API configuration

The API requires a PostgreSQL connection. Create a `.env` file in the project root:

```
DATABASE_URL=postgresql://user:password@localhost:5432/ocrdb
```

The `jobs` table is created automatically on startup.

## Usage

### CLI

Using `uv`:
```bash
uv run main.py <input> [options]
```

Using `python`:
```bash
python main.py <input> [options]
```

Using `make + docker`:
```bash
make build
make run INPUT=<input> [options]
```

CLI Arguments:
| Argument | Description | Default |
|---|---|---|
| `-i`, `--input` | Input file or directory (required) | — |
| `-o`, `--output` | Output directory for JSON files | timestamped `output/` dir |
| `--dispatch` | Directory for PDF page images | `data/dispatch` |
| `-r`, `--recursive` | Scan subdirectories recursively | `False` |
| `--ext` | Image format for PDF conversion | `jpeg` |
| `-p`, `--precision` | Confidence threshold for low-confidence words | `60.0` |
| `-w`, `--workers` | Number of cores for multiprocessing | `4` |
| `--dpi` | DPI for PDF-to-image conversion | `300` |
| `-ascii`, `--ensure-ascii` | Write JSON with ASCII encoding | `False` |

Use `-h` or `--help` flag to help.

### Make CLI Arguments:
| Arguments | CLI Correspondent |
|-----------|-------------------|
|`INPUT`| `-i`, `--input`|
|`OUTPUT`|`-o`, `--output`|
|`DISPATCH`| `--dispatch` |
|`RECURSIVE`|`-r`, `--recursive`|
|`EXTENSION`|`--ext`|
|`PRECISION`|`-p`, `--precision`|
|`WORKERS`|`-w`, `--workers`|
|`ASCII`|`--ensure-ascii` |

Use `make help` or `make` to help.

**Examples:**

```bash
# single file - the `-i` flag is optional
uv run main.py data/input/file.jpeg -w 1

# recursive, custom output, png conversion
uv run main.py -i documents/ -o results/ -r --ext png --dispatch images

# lower confidence threshold
uv run main.py -i data/input -p 75.0

# custom DPI
uv run main.py -i data/input --dpi 150

# make run
make build && make run INPUT=article.pdf DISPATCH=images WORKERS=2
```

### API

Build and run the API container:

```bash
make build-api
make run-api
```

Or run directly with uvicorn:

```bash
uv run uvicorn api.main:app --host 0.0.0.0 --port 8000
```

The API will be available at `http://localhost:8000` with auto-generated docs at `http://localhost:8000/docs`.

#### Endpoints

**POST /send** — Upload files for OCR processing

Accepts multipart form data with one or more files. MIME types are validated server-side.

```bash
curl -X POST http://localhost:8000/send \
  -F "files=@document.pdf" \
  -F "files=@scan.jpeg"
```

Response:
```json
[
  {"job_id": "uuid-1", "filename": "document.pdf"},
  {"job_id": "uuid-2", "filename": "scan.jpeg"}
]
```

Allowed types: `application/pdf`, `image/jpeg`, `image/jpg`, `image/png`, `image/tiff`, `image/tif`, `image/gif`, `image/webp`, `image/jp2`, `image/pnm`, `image/pbm`, `image/ppm`

Max upload: 20MB per file, 40MB total per request.

**GET /jobs/{id}** — Check job status

```bash
curl http://localhost:8000/jobs/{job_id}
```

Response:
```json
{"job_id": "uuid-1", "status": "done", "error": null}
```

Status values: `pending`, `running`, `done`, `error`

**GET /jobs/{id}/result** — Get OCR result

Returns the full OCR result once the job is done (HTTP 202 if still processing).

```bash
curl http://localhost:8000/jobs/{job_id}/result
```

Response (when done):
```json
{
  "job_id": "uuid-1",
  "status": "done",
  "error": null,
  "result": {"filename": "scan.jpeg", "text": "...", "mean_confidence": 91.2}
}
```

## Project structure

```
.
├── src/
│   ├── pipe.py       # OCR functions: text extraction and confidence
│   ├── utils.py      # I/O handlers: path collection, dispatch, pdf2img
│   └── output.py     # JSON construction and writing
├── api/
│   ├── main.py               # FastAPI app with lifespan and executor
│   ├── routes/
│   │   └── witchtr_router.py # POST /send, GET /jobs/{id}, GET /jobs/{id}/result
│   ├── schemas/
│   │   └── classes.py        # Pydantic schemas (placeholder)
│   ├── services/
│   │   └── witchtr_service.py # Background job execution
│   └── database/
│       ├── session.py        # SQLAlchemy engine and session
│       ├── models.py         # Job model with status enum
│       └── repository.py     # DB repository with Protocol pattern
├── data/
│   ├── input/        # place input files here (gitignored)
│   ├── dispatch/     # intermediate PDF page images (gitignored)
│   └── output/       # JSON results (gitignored)
├── tests/
│   ├── test_pipe.py
│   ├── test_utils.py
│   ├── test_output.py
│   └── test_api.py
├── main.py
├── pyproject.toml
├── .python-version
├── requirements/  # for python setup
├── Dockerfile
├── Makefile       # using make for better approach on docker
└── uv.lock
```

## Running tests

```bash
# all tests
uv run pytest tests/ -v

# with coverage
uv run pytest tests/ --cov=src --cov-report=term-missing
```

## Architecture decisions

**Procedural over object-oriented**
The pipeline is a linear data transformation — each step receives input and returns output with no shared state.

**One JSON per document, not per page**
PDFs are aggregated into a single JSON file with a `pages` array. Processing pages as individual files would scatter the output and make downstream consumption harder.

**Separate dispatch directory**
PDF-converted images are written to `data/dispatch/`, not to the input directory. This prevents `path_collector` from picking up intermediate files on the next run.

**`--precision` as a CLI argument**
The confidence threshold for flagging low-confidence words defaults to `60.0` but is exposed via CLI. Documents from different periods and digitization quality require different thresholds.

**API: ProcessPoolExecutor with background tasks**
The API runs OCR in a `ProcessPoolExecutor` via FastAPI `BackgroundTasks`, keeping the request/response cycle non-blocking. Job state is tracked in PostgreSQL.

**API: Protocol-based repository**
`DBRepoTemplate` uses a `Protocol` class for engine-agnostic database access, making it easy to swap implementations.

**Containerization and Make**
Using a container to avoid the need to install any dependency for the pipe (unless docker). This avoids even the need to install *tesseract*. A multi-stage Dockerfile builds separate `cli` and `api` targets.

## Known limitations

- **Manuscripts and HTR** — Tesseract was not trained for handwritten text recognition. For HTR, see [Kraken](https://kraken.re) or [Calamari](https://github.com/Calamari-OCR/calamari).
- **Low DPI scans** — images below 200 DPI produce consistently low confidence. Rescan at 300 DPI minimum for better results.
- **18th and 19th century documents** — mean confidence below 60 is common due to ink degradation and non-standard typefaces.
- **Multi-column layouts** — Tesseract reads left-to-right across the full page width, mixing columns. Layout analysis is not implemented.
- **Native digital PDFs** — PDFs with a text layer do not need OCR. The pipeline converts them to images anyway; confidence will be high but the step is unnecessary.

## What's next

- [x] Multiprocessing with `Pool` and process-safe logging via `QueueHandler`
- [x] Containerization and Makefile integration
- [x] API using FastAPI
- [x] DB integration using PostgreSQL, MIME validation
- [ ] Docker Compose + MinIO to remove disk writing
- [ ] New OCR engines
