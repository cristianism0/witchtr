import uuid
from pathlib import Path
from typing import Annotated
from concurrent.futures import ProcessPoolExecutor

import magic
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Request,
    HTTPException,
    UploadFile,
)
from sqlalchemy.orm import Session

from api.database.repository import DBJobRepository
from api.database.session import get_db
from api.services.witchtr_service import run_job

router = APIRouter()

# for while - will change to MinIO in the future
INPUT_DIR = Path("api/data/input")
OUTPUT_DIR = Path("api/data/output")
INPUT_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_TYPES = [
    "application/pdf",
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/tiff",
    "image/tif",
    "image.gif",
    "image/webp",
    "image/jp2",
    "image/pnm",
    "image/pbm",
    "image/ppm",
    "image/pnm",
]

# 20MB maximum upload per file
MAX_UPLOAD_SIZE = 20 * 1024 * 1024


@router.post("/send")
async def send_input(
    request: Request,
    files: Annotated[list[UploadFile], File()],
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> list[dict[str, str | None]]:
    """
    Function POST to receive files.
    - Initialize DB session with auto close().
    - MIME checking using default FastAPI + Pymagic.
    - Memory writing (deprecated)
    """
    repo = DBJobRepository(db)
    executor: ProcessPoolExecutor = request.app.state.executor
    jobs: list[dict[str, str | None]] = []

    f_size: int = 0
    for f in files:
        f_size += f.size if f.size else 0

        if f.size and f.size > MAX_UPLOAD_SIZE or f_size >= 2 * MAX_UPLOAD_SIZE:
            raise HTTPException(status_code=413, detail="File too large")

        header = await f.read(2048)
        _ = await f.seek(0)
        magic_val = magic.from_buffer(header, mime=True)

        if f.content_type and magic_val not in ALLOWED_TYPES:
            raise HTTPException(
                status_code=415,
                detail=f"File {f.filename} type not allowed. Allowed: {', '.join(ALLOWED_TYPES)}",
            )

        job_id = str(uuid.uuid4())
        file_path = INPUT_DIR / f"{job_id}_{f.filename}"
        _ = file_path.write_bytes(await f.read())

        repo.create_job(job_id, f.filename)
        background_tasks.add_task(
            run_job, job_id, file_path, OUTPUT_DIR, repo, executor
        )
        jobs.append({"job_id": job_id, "filename": f.filename})
    return jobs


@router.get("/jobs/{id}")
def job_status(id: str, db: Session = Depends(get_db)):
    """
    Function GET to tracking the OCR processing if there is one with id.
    """
    repo = DBJobRepository(db)
    job = repo.get_job(id)

    if not job:
        raise HTTPException(status_code=404, detail=f"job not found with ID: {id}")
    return {"job_id": id, "status": job.status, "error": job.error}


@router.get("/jobs/{id}/result")
def get_result(id: str, db: Session = Depends(get_db)):
    """
    Function GET to locate the result of a processing with id.
    - Data collected inside the database section.
    """
    repo = DBJobRepository(db)
    job = repo.get_job(id)

    if not job:
        raise HTTPException(status_code=404, detail=f"job not found with ID: {id}")
    if job.status.value != "done":
        raise HTTPException(status_code=202, detail="job still in progress")
    return {
        "job_id": id,
        "status": job.status,
        "error": job.error,
        "result": job.result,
    }
