"""Unit tests for DBJobRepository.

Edge cases covered:
- Creating jobs with various states
- Updating non-existent jobs (no-op, no crash)
- get_job for missing PK
- Close with owned vs borrowed session
- Multiple updates on same job
- Large result payloads
- Unicode filenames
"""

import uuid

import pytest

from api.database.models import Job, State
from api.database.repository import DBJobRepository


class TestCreateJob:
    def test_creates_pending_job(self, repo, db_session):
        job_id = str(uuid.uuid4())
        repo.create_job(job_id, "test.png")
        job = db_session.get(Job, job_id)
        assert job is not None
        assert job.status == State.PENDING
        assert job.filename == "test.png"

    def test_unicode_filename(self, repo, db_session):
        job_id = str(uuid.uuid4())
        repo.create_job(job_id, "archivo con espacios y ñ.pdf")
        job = db_session.get(Job, job_id)
        assert job.filename == "archivo con espacios y ñ.pdf"

    def test_multiple_jobs(self, repo, db_session):
        ids = [str(uuid.uuid4()) for _ in range(5)]
        for i, jid in enumerate(ids):
            repo.create_job(jid, f"file_{i}.png")
        for jid in ids:
            assert db_session.get(Job, jid) is not None

    def test_none_filename_raises_integrity_error(self, repo, db_session):
        job_id = str(uuid.uuid4())
        with pytest.raises(Exception):
            repo.create_job(job_id, None)
            db_session.rollback()


class TestUpdateJob:
    def test_update_to_running(self, repo, db_session):
        job_id = str(uuid.uuid4())
        repo.create_job(job_id, "img.png")
        repo.update_job(job_id, State.RUNNING)
        job = db_session.get(Job, job_id)
        assert job.status == State.RUNNING

    def test_update_to_done_with_result(self, repo, db_session):
        job_id = str(uuid.uuid4())
        repo.create_job(job_id, "img.png")
        result = {"text": "hello", "confidence": 90.0}
        repo.update_job(job_id, State.DONE, result=result)
        job = db_session.get(Job, job_id)
        assert job.status == State.DONE
        assert job.result == result

    def test_update_to_error_with_message(self, repo, db_session):
        job_id = str(uuid.uuid4())
        repo.create_job(job_id, "img.png")
        repo.update_job(job_id, State.ERROR, error="OOM")
        job = db_session.get(Job, job_id)
        assert job.status == State.ERROR
        assert job.error == "OOM"

    def test_update_nonexistent_job_no_crash(self, repo):
        repo.update_job("nonexistent-id", State.DONE)  # should not raise

    def test_multiple_updates(self, repo, db_session):
        job_id = str(uuid.uuid4())
        repo.create_job(job_id, "img.png")
        repo.update_job(job_id, State.RUNNING)
        repo.update_job(job_id, State.DONE, result={"ok": True})
        job = db_session.get(Job, job_id)
        assert job.status == State.DONE
        assert job.result == {"ok": True}

    def test_large_result_payload(self, repo, db_session):
        job_id = str(uuid.uuid4())
        repo.create_job(job_id, "big.pdf")
        large_result = {"pages": [{"text": "x" * 10000} for _ in range(100)]}
        repo.update_job(job_id, State.DONE, result=large_result)
        job = db_session.get(Job, job_id)
        assert len(job.result["pages"]) == 100


class TestGetJob:
    def test_existing_job(self, repo, db_session):
        job_id = str(uuid.uuid4())
        repo.create_job(job_id, "test.png")
        job = repo.get_job(job_id)
        assert job is not None
        assert job.job_id == job_id

    def test_missing_job_returns_none(self, repo):
        result = repo.get_job(str(uuid.uuid4()))
        assert result is None


class TestClose:
    def test_close_owns_session(self, db_session):
        repo = DBJobRepository(db_session)
        repo.close()  # should not raise; session was passed in
        # When owned=false (session passed in), close() is a no-op
        # The session is still usable after close() because _owns_session=False
        assert db_session.is_active

    def test_close_creates_own_session(self):
        repo = DBJobRepository()  # no session → owns it
        repo.close()  # should close cleanly
