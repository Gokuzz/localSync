from uuid import uuid4

from app.db.base import Base
from app.db.session import create_db_engine, create_session_factory
from app.models.stored_file import StoredFile
from app.repositories.stored_files import StoredFileRepository


def test_stored_file_repository_adds_and_finds_by_identity(tmp_path) -> None:
    engine = create_db_engine(f"sqlite:///{(tmp_path / 'repo.db').as_posix()}")
    Base.metadata.create_all(engine)
    session_factory = create_session_factory(engine)

    with session_factory() as session:
        repository = StoredFileRepository(session)
        stored = StoredFile(
            id=str(uuid4()),
            device_id="fake-device-1",
            original_filename="example.bin",
            size=3,
            sha256="a" * 64,
            stored_path="fake-device-1/example_aaaaaaaaaaaa.bin",
            content_type="application/octet-stream",
        )

        repository.add(stored)
        session.commit()

        found = repository.find_by_identity("fake-device-1", 3, "a" * 64)

    assert found is not None
    assert found.stored_path == "fake-device-1/example_aaaaaaaaaaaa.bin"


def test_stored_file_repository_finds_by_stored_path(tmp_path) -> None:
    engine = create_db_engine(f"sqlite:///{(tmp_path / 'repo.db').as_posix()}")
    Base.metadata.create_all(engine)
    session_factory = create_session_factory(engine)

    with session_factory() as session:
        repository = StoredFileRepository(session)
        stored = StoredFile(
            id=str(uuid4()),
            device_id="fake-device-1",
            original_filename="example.bin",
            size=3,
            sha256="a" * 64,
            stored_path="fake-device-1/example_aaaaaaaaaaaa.bin",
            content_type=None,
        )

        repository.add(stored)
        session.commit()

        found = repository.find_by_stored_path("fake-device-1/example_aaaaaaaaaaaa.bin")

    assert found is not None
    assert found.sha256 == "a" * 64
