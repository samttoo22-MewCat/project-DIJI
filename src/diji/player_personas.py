"""Account-owned player personas, separate from AI-extracted user profiles."""
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field
from .domain import UserPersona


class PlayerPersonaInput(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    label: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=80)
    sex: str = Field(default='', max_length=80)
    age: str = Field(default='', max_length=40)
    description: str = Field(default='', max_length=8000)


class PlayerPersona(PlayerPersonaInput):
    id: str

    def persona(self):
        return UserPersona(**self.model_dump(exclude={'id', 'label'}))


class PlayerPersonaStore:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        path.parent.chmod(0o700)
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS personas (id TEXT PRIMARY KEY, data TEXT NOT NULL)')
        path.chmod(0o600)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path)
        try:
            with db:
                yield db
        finally:
            db.close()

    def list(self):
        with self.connect() as db:
            return [PlayerPersona.model_validate_json(row[0]) for row in db.execute('SELECT data FROM personas ORDER BY rowid')]

    def get(self, persona_id):
        with self.connect() as db:
            row = db.execute('SELECT data FROM personas WHERE id=?', (persona_id,)).fetchone()
        if row is None:
            raise LookupError(persona_id)
        return PlayerPersona.model_validate_json(row[0])

    def save(self, value: PlayerPersonaInput, persona_id=None):
        record = PlayerPersona(id=persona_id or f'player-{uuid4()}', **value.model_dump())
        with self.connect() as db:
            if persona_id:
                result = db.execute('UPDATE personas SET data=? WHERE id=?', (record.model_dump_json(), persona_id))
                if result.rowcount == 0:
                    raise LookupError(persona_id)
            else:
                db.execute('INSERT INTO personas VALUES (?,?)', (record.id, record.model_dump_json()))
        return record

    def delete(self, persona_id):
        with self.connect() as db:
            result = db.execute('DELETE FROM personas WHERE id=?', (persona_id,))
            if result.rowcount == 0:
                raise LookupError(persona_id)
