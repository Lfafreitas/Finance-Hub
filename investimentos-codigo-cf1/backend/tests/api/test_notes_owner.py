"""Anotação de outro usuário não aparece nem pode ser editada."""

from app.models.note import Note
from tests.test_persistence import make_user


def test_nota_de_outro_usuario_e_invisivel(api_client, db_session):
    client, _user = api_client
    other = make_user(db_session, email="outro-notas@example.com")
    foreign = Note(user_id=other.id, body="segredo do outro", tickers="")
    db_session.add(foreign)
    db_session.flush()

    assert client.get("/notes").json() == []
    assert client.put(f"/notes/{foreign.id}", json={"body": "invadi"}).status_code == 404
    assert client.delete(f"/notes/{foreign.id}").status_code == 404
    db_session.refresh(foreign)
    assert foreign.body == "segredo do outro"
