import asyncio
import io
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException, UploadFile

from app.api import content_routes
from app.models.academic import Subject
from app.models.resource import LearningResource, ResourceSource
from app.models.syllabus import Unit, VerificationStatus
from app.models.user import AccountStatus, UserRole
from app.services.content import validate_external_url


def _admin():
    return SimpleNamespace(
        id=uuid.uuid4(),
        full_name="Admin Faculty",
        email="admin@rvce.edu.in",
        role=UserRole.ADMIN_FACULTY,
        account_status=AccountStatus.ACTIVE,
        email_verified=True,
    )


def _student():
    return SimpleNamespace(
        id=uuid.uuid4(),
        full_name="Student User",
        email="student@rvce.edu.in",
        role=UserRole.STUDENT,
        account_status=AccountStatus.ACTIVE,
        email_verified=True,
    )


def test_validate_external_url_valid_schemes():
    # Valid YouTube video
    assert validate_external_url("https://www.youtube.com/watch?v=2E7MmKv0Y24") == "https://www.youtube.com/watch?v=2E7MmKv0Y24"
    # Valid YouTube short URL
    assert validate_external_url("https://youtu.be/dQw4w9WgXcQ") == "https://youtu.be/dQw4w9WgXcQ"
    # Valid YouTube playlist
    assert validate_external_url("https://www.youtube.com/playlist?list=PLBlnK6fEyqRhqJPDXcvYzAf6WBGQDF52T") == "https://www.youtube.com/playlist?list=PLBlnK6fEyqRhqJPDXcvYzAf6WBGQDF52T"
    # Valid educational website
    assert validate_external_url("https://ocw.mit.edu/courses/electrical-engineering-and-computer-science/") == "https://ocw.mit.edu/courses/electrical-engineering-and-computer-science/"
    # Optional url when None
    assert validate_external_url(None, required=False) is None


def test_validate_external_url_rejects_invalid_and_ssrf():
    # Invalid schemes
    with pytest.raises(HTTPException) as exc:
        validate_external_url("ftp://example.com/file.pdf")
    assert exc.value.status_code == 422

    with pytest.raises(HTTPException) as exc:
        validate_external_url("javascript:alert(1)")
    assert exc.value.status_code == 422

    # Malformed URL
    with pytest.raises(HTTPException) as exc:
        validate_external_url("not-a-valid-url")
    assert exc.value.status_code == 422

    # Localhost / Private IP addresses (SSRF protection)
    with pytest.raises(HTTPException) as exc:
        validate_external_url("http://localhost:8000/api")
    assert exc.value.status_code == 422

    with pytest.raises(HTTPException) as exc:
        validate_external_url("http://127.0.0.1/admin")
    assert exc.value.status_code == 422

    with pytest.raises(HTTPException) as exc:
        validate_external_url("http://169.254.169.254/latest/meta-data/")
    assert exc.value.status_code == 422

    with pytest.raises(HTTPException) as exc:
        validate_external_url("http://10.0.0.1/internal")
    assert exc.value.status_code == 422

    # Required check
    with pytest.raises(HTTPException) as exc:
        validate_external_url("", required=True)
    assert exc.value.status_code == 422


def test_admin_upload_resource_file_source_pdf():
    subject_id = uuid.uuid4()
    admin_user = _admin()

    mock_db = MagicMock()
    mock_subject = SimpleNamespace(
        id=subject_id,
        code="CS201",
        name="Data Structures",
        semester=3,
        academic_scheme="2022",
        active=True,
    )
    mock_db.get.side_effect = lambda model, key: mock_subject if model == Subject and key == subject_id else None

    fake_scheme = SimpleNamespace(id=uuid.uuid4(), name="2022")
    fake_semester = SimpleNamespace(id=uuid.uuid4(), number=3)

    upload_file = UploadFile(
        file=io.BytesIO(b"%PDF-1.4 test pdf content"),
        filename="lecture_notes.pdf",
        headers={"content-type": "application/pdf"},
    )

    with patch("app.api.content_routes.storage.upload_bytes") as mock_storage, \
         patch("app.api.content_routes._subject_context", return_value=(fake_scheme, fake_semester)):

        res = asyncio.run(content_routes.admin_upload_resource(
            file=upload_file,
            subject_id=subject_id,
            resource_type="NOTES",
            title="Lecture Notes on Trees",
            resource_source="FILE",
            status="VERIFIED",
            admin=admin_user,
            db=mock_db,
        ))

        assert res["resource_source"] == "FILE"
        assert res["title"] == "Lecture Notes on Trees"
        assert res["original_filename"] == "lecture_notes.pdf"
        assert res["file_type"] == "pdf"
        assert mock_db.add.called
        assert mock_db.commit.called
        assert mock_storage.called


def test_admin_upload_resource_link_source_youtube():
    subject_id = uuid.uuid4()
    admin_user = _admin()

    mock_db = MagicMock()
    mock_subject = SimpleNamespace(
        id=subject_id,
        code="CS201",
        name="Data Structures",
        semester=3,
        academic_scheme="2022",
        active=True,
    )
    mock_db.get.side_effect = lambda model, key: mock_subject if model == Subject and key == subject_id else None

    fake_scheme = SimpleNamespace(id=uuid.uuid4(), name="2022")
    fake_semester = SimpleNamespace(id=uuid.uuid4(), number=3)

    with patch("app.api.content_routes._subject_context", return_value=(fake_scheme, fake_semester)):
        res = asyncio.run(content_routes.admin_upload_resource(
            file=None,
            subject_id=subject_id,
            resource_type="STUDY_MATERIAL",
            title="MIT Graph Algorithms Lecture",
            resource_source="LINK",
            external_url="https://www.youtube.com/watch?v=2E7MmKv0Y24",
            link_title="MIT OCW Video",
            status="VERIFIED",
            admin=admin_user,
            db=mock_db,
        ))

        assert res["resource_source"] == "LINK"
        assert res["external_url"] == "https://www.youtube.com/watch?v=2E7MmKv0Y24"
        assert res["link_title"] == "MIT OCW Video"
        assert res["original_filename"] is None
        assert res["file_type"] is None
        assert mock_db.add.called
        assert mock_db.commit.called


def test_admin_upload_resource_both_source_file_and_link():
    subject_id = uuid.uuid4()
    admin_user = _admin()

    mock_db = MagicMock()
    mock_subject = SimpleNamespace(
        id=subject_id,
        code="CS201",
        name="Data Structures",
        semester=3,
        academic_scheme="2022",
        active=True,
    )
    mock_db.get.side_effect = lambda model, key: mock_subject if model == Subject and key == subject_id else None

    fake_scheme = SimpleNamespace(id=uuid.uuid4(), name="2022")
    fake_semester = SimpleNamespace(id=uuid.uuid4(), number=3)

    upload_file = UploadFile(
        file=io.BytesIO(b"%PDF-1.4 test pdf content"),
        filename="sorting_guide.pdf",
        headers={"content-type": "application/pdf"},
    )

    with patch("app.api.content_routes.storage.upload_bytes") as mock_storage, \
         patch("app.api.content_routes._subject_context", return_value=(fake_scheme, fake_semester)):

        res = asyncio.run(content_routes.admin_upload_resource(
            file=upload_file,
            subject_id=subject_id,
            resource_type="REFERENCE",
            title="Sorting Reference & Princeton Slides",
            resource_source="BOTH",
            external_url="https://algs4.cs.princeton.edu/lectures/",
            link_title="Princeton Slides",
            status="VERIFIED",
            admin=admin_user,
            db=mock_db,
        ))

        assert res["resource_source"] == "BOTH"
        assert res["external_url"] == "https://algs4.cs.princeton.edu/lectures/"
        assert res["link_title"] == "Princeton Slides"
        assert res["original_filename"] == "sorting_guide.pdf"
        assert res["file_type"] == "pdf"
        assert mock_storage.called


def test_admin_upload_resource_validates_required_fields_by_source():
    subject_id = uuid.uuid4()
    admin_user = _admin()
    mock_db = MagicMock()
    mock_subject = SimpleNamespace(
        id=subject_id,
        code="CS201",
        name="Data Structures",
        semester=3,
        academic_scheme="2022",
        active=True,
    )
    mock_db.get.side_effect = lambda model, key: mock_subject if model == Subject and key == subject_id else None

    fake_scheme = SimpleNamespace(id=uuid.uuid4(), name="2022")
    fake_semester = SimpleNamespace(id=uuid.uuid4(), number=3)

    with patch("app.api.content_routes._subject_context", return_value=(fake_scheme, fake_semester)):
        # FILE source requires file
        with pytest.raises(HTTPException) as exc:
            asyncio.run(content_routes.admin_upload_resource(
                file=None,
                subject_id=subject_id,
                resource_type="NOTES",
                title="Test Resource",
                resource_source="FILE",
                admin=admin_user,
                db=mock_db,
            ))
        assert exc.value.status_code == 422
        assert "file is required" in exc.value.detail.lower()

        # LINK source requires external_url
        with pytest.raises(HTTPException) as exc:
            asyncio.run(content_routes.admin_upload_resource(
                file=None,
                subject_id=subject_id,
                resource_type="NOTES",
                title="Test Resource",
                resource_source="LINK",
                external_url=None,
                admin=admin_user,
                db=mock_db,
            ))
        assert exc.value.status_code == 422
        assert "url is required" in exc.value.detail.lower()


def test_download_link_only_resource_returns_400():
    resource_id = uuid.uuid4()
    admin_user = _admin()

    link_only_resource = SimpleNamespace(
        id=resource_id,
        title="Link Resource",
        resource_source="LINK",
        storage_path=None,
        active=True,
        verification_status=VerificationStatus.VERIFIED,
        subject_id=uuid.uuid4(),
    )

    mock_db = MagicMock()
    mock_db.get.return_value = link_only_resource

    # Admin download check
    with pytest.raises(HTTPException) as exc:
        content_routes.admin_download(
            kind="resource",
            content_id=resource_id,
            preview=False,
            admin=admin_user,
            db=mock_db,
        )
    assert exc.value.status_code == 400
    assert "no downloadable file" in exc.value.detail.lower()

    # Student download check
    student_user = _student()
    with patch("app.api.content_routes._student_profile", return_value=SimpleNamespace()), \
         patch("app.api.content_routes._enrolled_subject_ids", return_value={link_only_resource.subject_id}), \
         patch("app.api.content_routes._require_enrolled"):
        with pytest.raises(HTTPException) as s_exc:
            content_routes.student_download(
                kind="resource",
                content_id=resource_id,
                preview=False,
                student=student_user,
                db=mock_db,
            )
        assert s_exc.value.status_code == 400
        assert "no downloadable file" in s_exc.value.detail.lower()


def test_admin_update_resource_subject_reassignment():
    from app.schemas.content import ResourceUpdate
    old_subject_id = uuid.uuid4()
    new_subject_id = uuid.uuid4()
    scheme_id = uuid.uuid4()
    semester_id = uuid.uuid4()
    resource_id = uuid.uuid4()

    resource = SimpleNamespace(
        id=resource_id,
        title="ADLD Notes",
        description="Logic design material",
        subject_id=old_subject_id,
        academic_scheme_id=scheme_id,
        semester_id=semester_id,
        unit_id=None,
        resource_type="NOTES",
        resource_source="FILE",
        external_url=None,
        link_title=None,
        original_filename="notes.pdf",
        file_type="pdf",
        file_size=1024,
        verification_status=VerificationStatus.VERIFIED,
        active=True,
        uploaded_at=None,
        uploaded_by=None,
        updated_at=None,
    )
    new_subject = SimpleNamespace(
        id=new_subject_id,
        code="CS234AI",
        name="Applied Digital Logic Design",
        academic_scheme_id=scheme_id,
        semester_id=semester_id,
        active=True,
    )

    mock_db = MagicMock()
    mock_db.get.side_effect = lambda model, obj_id: (
        resource if obj_id == resource_id else new_subject if obj_id == new_subject_id else None
    )

    res = content_routes.admin_update_resource(
        resource_id=resource_id,
        payload=ResourceUpdate(subject_id=new_subject_id),
        admin=_admin(),
        db=mock_db,
    )

    assert resource.subject_id == new_subject_id
    assert res["subject_code"] == "CS234AI"
    assert res["subject_name"] == "Applied Digital Logic Design"


def test_student_list_resources_shows_verified_active_and_respects_subject_scope():
    subject_id = uuid.uuid4()
    scheme_id = uuid.uuid4()
    semester_id = uuid.uuid4()

    student_user = _student()
    profile = SimpleNamespace(
        id=uuid.uuid4(),
        academic_scheme_id=scheme_id,
        current_semester_id=semester_id,
        branch_id=None,
    )

    verified_resource = SimpleNamespace(
        id=uuid.uuid4(),
        title="ADLD Both Resource",
        description="Notes and YouTube video",
        subject_id=subject_id,
        academic_scheme_id=scheme_id,
        semester_id=semester_id,
        unit_id=None,
        resource_type="STUDY_MATERIAL",
        resource_source="BOTH",
        external_url="https://www.youtube.com/watch?v=v4J1Cpr_XUw",
        link_title="ADLD Video Lecture",
        original_filename="adld.pdf",
        file_type="pdf",
        file_size=2048,
        verification_status=VerificationStatus.VERIFIED,
        active=True,
        uploaded_at=None,
        uploaded_by=None,
    )
    subject = SimpleNamespace(id=subject_id, code="CS234AI", name="ADLD", active=True)

    mock_db = MagicMock()
    mock_db.scalars.return_value.all.return_value = [verified_resource]
    mock_db.scalars.return_value.first.return_value = profile

    with patch("app.api.content_routes._student_profile", return_value=profile), \
         patch("app.api.content_routes._enrolled_subject_ids", return_value={subject_id}), \
         patch("app.api.content_routes._subjects_map", return_value={subject_id: subject}):
        result = content_routes.student_list_resources(student=student_user, db=mock_db)

    assert result["total"] == 1
    assert result["items"][0]["title"] == "ADLD Both Resource"
    assert result["items"][0]["resource_source"] == "BOTH"
    assert result["items"][0]["external_url"] == "https://www.youtube.com/watch?v=v4J1Cpr_XUw"
    assert result["items"][0]["subject_code"] == "CS234AI"
