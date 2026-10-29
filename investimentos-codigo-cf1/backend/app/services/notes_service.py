"""Anotações e fontes de leitura (CRUD simples, sempre do usuário certo)."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.note import Note, ReadingSource
from app.schemas.notes import NoteRead, NoteWrite, SourceWrite


class NoteNotFoundError(Exception):
    pass


def _read(note: Note) -> NoteRead:
    return NoteRead(
        id=note.id,
        title=note.title,
        body=note.body,
        quote=note.quote,
        source_title=note.source_title,
        source_url=note.source_url,
        tickers=[t for t in note.tickers.split(",") if t],
        pinned=note.pinned,
        share_with_claude=note.share_with_claude,
        created_at=note.created_at,
        updated_at=note.updated_at,
    )


def _apply(note: Note, data: NoteWrite) -> None:
    note.title = data.title
    note.body = data.body
    note.quote = data.quote
    note.source_title = data.source_title
    note.source_url = data.source_url
    note.tickers = ",".join(data.tickers)
    note.pinned = data.pinned
    note.share_with_claude = data.share_with_claude


def list_notes(
    db: Session, user_id: UUID, *, search: str | None = None, shared_only: bool = False
) -> list[NoteRead]:
    stmt = select(Note).where(Note.user_id == user_id)
    if shared_only:
        stmt = stmt.where(Note.share_with_claude.is_(True))
    if search and search.strip():
        like = f"%{search.strip()}%"
        stmt = stmt.where(
            or_(
                Note.title.ilike(like),
                Note.body.ilike(like),
                Note.quote.ilike(like),
                Note.tickers.ilike(like),
            )
        )
    stmt = stmt.order_by(Note.pinned.desc(), Note.updated_at.desc())
    return [_read(n) for n in db.scalars(stmt).all()]


def _get(db: Session, user_id: UUID, note_id: UUID) -> Note:
    note = db.get(Note, note_id)
    if note is None or note.user_id != user_id:
        raise NoteNotFoundError("anotação não encontrada")
    return note


def create_note(db: Session, user_id: UUID, data: NoteWrite) -> NoteRead:
    note = Note(user_id=user_id)
    _apply(note, data)
    db.add(note)
    db.flush()
    return _read(note)


def update_note(db: Session, user_id: UUID, note_id: UUID, data: NoteWrite) -> NoteRead:
    note = _get(db, user_id, note_id)
    _apply(note, data)
    db.flush()
    return _read(note)


def delete_note(db: Session, user_id: UUID, note_id: UUID) -> None:
    db.delete(_get(db, user_id, note_id))
    db.flush()


def list_sources(db: Session, user_id: UUID, *, active_only: bool = False) -> list[ReadingSource]:
    stmt = select(ReadingSource).where(ReadingSource.user_id == user_id)
    if active_only:
        stmt = stmt.where(ReadingSource.active.is_(True))
    return list(db.scalars(stmt.order_by(ReadingSource.created_at)).all())


def save_source(
    db: Session, user_id: UUID, data: SourceWrite, source_id: UUID | None = None
) -> ReadingSource:
    if source_id is None:
        source = ReadingSource(user_id=user_id)
        db.add(source)
    else:
        source = db.get(ReadingSource, source_id)
        if source is None or source.user_id != user_id:
            raise NoteNotFoundError("fonte não encontrada")
    source.name, source.url, source.focus, source.active = (
        data.name,
        data.url,
        data.focus,
        data.active,
    )
    db.flush()
    return source


def delete_source(db: Session, user_id: UUID, source_id: UUID) -> None:
    source = db.get(ReadingSource, source_id)
    if source is None or source.user_id != user_id:
        raise NoteNotFoundError("fonte não encontrada")
    db.delete(source)
    db.flush()
