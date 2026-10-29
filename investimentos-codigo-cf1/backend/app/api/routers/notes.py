"""Anotações e fontes de leitura do Jornal."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_id, get_db
from app.schemas.notes import NoteRead, NoteWrite, SourceRead, SourceWrite
from app.services import notes_service
from app.services.notes_service import NoteNotFoundError

router = APIRouter()


@router.get("/notes", response_model=list[NoteRead])
def list_notes(
    search: str | None = Query(default=None, max_length=100),
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    """Fixadas primeiro, depois as mais recentes."""
    return notes_service.list_notes(db, user_id, search=search)


@router.post("/notes", response_model=NoteRead, status_code=201)
def create_note(
    body: NoteWrite, db: Session = Depends(get_db), user_id: UUID = Depends(get_current_user_id)
):
    return notes_service.create_note(db, user_id, body)


@router.put("/notes/{note_id}", response_model=NoteRead)
def update_note(
    note_id: UUID,
    body: NoteWrite,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    try:
        return notes_service.update_note(db, user_id, note_id, body)
    except NoteNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/notes/{note_id}", status_code=204)
def delete_note(
    note_id: UUID, db: Session = Depends(get_db), user_id: UUID = Depends(get_current_user_id)
):
    try:
        notes_service.delete_note(db, user_id, note_id)
    except NoteNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(status_code=204)


@router.get("/reading-sources", response_model=list[SourceRead])
def list_sources(db: Session = Depends(get_db), user_id: UUID = Depends(get_current_user_id)):
    return notes_service.list_sources(db, user_id)


@router.post("/reading-sources", response_model=SourceRead, status_code=201)
def create_source(
    body: SourceWrite, db: Session = Depends(get_db), user_id: UUID = Depends(get_current_user_id)
):
    return notes_service.save_source(db, user_id, body)


@router.put("/reading-sources/{source_id}", response_model=SourceRead)
def update_source(
    source_id: UUID,
    body: SourceWrite,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    try:
        return notes_service.save_source(db, user_id, body, source_id)
    except NoteNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/reading-sources/{source_id}", status_code=204)
def delete_source(
    source_id: UUID, db: Session = Depends(get_db), user_id: UUID = Depends(get_current_user_id)
):
    try:
        notes_service.delete_source(db, user_id, source_id)
    except NoteNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(status_code=204)
