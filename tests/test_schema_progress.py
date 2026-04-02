from agentdrive.schemas.files import FileDetailResponse
import uuid
from datetime import datetime


def test_file_detail_response_includes_progress():
    data = {
        "id": uuid.uuid4(),
        "filename": "test.pdf",
        "content_type": "pdf",
        "file_size": 1000,
        "status": "processing",
        "extra_metadata": {},
        "created_at": datetime.now(),
        "chunk_count": 0,
        "total_batches": 17,
        "completed_batches": 12,
        "current_phase": "enriching",
    }
    response = FileDetailResponse.model_validate(data)
    assert response.total_batches == 17
    assert response.completed_batches == 12
    assert response.current_phase == "enriching"


def test_file_detail_response_defaults_progress():
    data = {
        "id": uuid.uuid4(),
        "filename": "test.pdf",
        "content_type": "pdf",
        "file_size": 1000,
        "status": "ready",
        "extra_metadata": {},
        "created_at": datetime.now(),
    }
    response = FileDetailResponse.model_validate(data)
    assert response.total_batches == 0
    assert response.completed_batches == 0
    assert response.current_phase is None
