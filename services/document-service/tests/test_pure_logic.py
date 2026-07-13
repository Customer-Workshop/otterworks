"""Focused tests for schema validation and document helper logic."""

import uuid

import pytest
from pydantic import ValidationError

from app.api.documents import _ensure_owner, _extract_user_id
from app.schemas.document import (
    CommentCreate,
    DocumentCreate,
    DocumentPatch,
    TemplateCreate,
)
from app.services.document_service import DocumentService, _word_count


def test_word_count_handles_empty_and_whitespace():
    assert _word_count("") == 0
    assert _word_count("  one\t two\nthree ") == 3


def test_document_create_defaults_and_constraints():
    owner_id = uuid.uuid4()
    document = DocumentCreate(title="Title", owner_id=owner_id)
    assert document.content == ""
    assert document.content_type == "text/markdown"

    with pytest.raises(ValidationError):
        DocumentCreate(title="", owner_id=owner_id)
    with pytest.raises(ValidationError):
        DocumentCreate(title="x" * 501, owner_id=owner_id)


def test_document_patch_rejects_null_not_null_fields():
    with pytest.raises(ValidationError, match="title cannot be null"):
        DocumentPatch(title=None)
    with pytest.raises(ValidationError, match="content cannot be null"):
        DocumentPatch.model_validate({"title": "ok", "content": None})

    assert DocumentPatch.model_validate({"title": "Updated"}).model_fields_set == {"title"}


def test_other_schemas_validate_required_fields():
    with pytest.raises(ValidationError):
        CommentCreate(author_id=uuid.uuid4(), content="")
    with pytest.raises(ValidationError):
        TemplateCreate(name="", created_by=uuid.uuid4())


def test_paginate_never_returns_zero_pages():
    assert DocumentService.paginate(0, 1, 20) == 1
    assert DocumentService.paginate(21, 2, 20) == 2
    assert DocumentService.paginate(20, 1, 0) == 1


def test_extract_user_id_accepts_forwarded_id_without_jwt_secret(monkeypatch):
    user_id = uuid.uuid4()
    monkeypatch.delenv("JWT_SECRET", raising=False)

    from starlette.requests import Request

    scope = {
        "type": "http",
        "headers": [
            (b"authorization", b"Bearer forwarded-token"),
            (b"x-user-id", str(user_id).encode()),
        ],
    }
    assert _extract_user_id(Request(scope)) == user_id


def test_ensure_owner_rejects_other_users():
    from fastapi import HTTPException

    owner_id = uuid.uuid4()
    document = type("Document", (), {"owner_id": owner_id})()
    _ensure_owner(document, owner_id)
    with pytest.raises(HTTPException) as exc:
        _ensure_owner(document, uuid.uuid4())
    assert exc.value.status_code == 403
