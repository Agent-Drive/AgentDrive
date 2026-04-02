from agentdrive.models.types import FileStatus


def test_uploading_status_exists():
    assert FileStatus.UPLOADING == "uploading"
    assert FileStatus.UPLOADING in FileStatus.__members__.values()
