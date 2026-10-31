"""Account-local generation traces and turn records; provider credentials never enter this API."""
from datetime import datetime, timezone
from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
import uuid


def now():
    return datetime.now(timezone.utc).isoformat()


class PlayerActivity:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        path.parent.chmod(0o700)
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, kind TEXT NOT NULL, status TEXT NOT NULL, started TEXT NOT NULL, updated TEXT NOT NULL, data TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 0)')
            db.execute('CREATE TABLE IF NOT EXISTS events (seq INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL, stage TEXT NOT NULL, status TEXT NOT NULL, timestamp TEXT NOT NULL, data TEXT NOT NULL)')
        path.chmod(0o600)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def begin(self, kind, data):
        run_id = 'gen-' + uuid.uuid4().hex if kind == 'generation' else 'act-' + uuid.uuid4().hex
        stamp = now()
        with self.connect() as db:
            db.execute('INSERT INTO runs VALUES (?, ?, ?, ?, ?, ?, 0)', (run_id, kind, 'running', stamp, stamp, json.dumps(data, ensure_ascii=False)))
        return run_id

    def event(self, run_id, stage, status, data):
        with self.connect() as db:
            db.execute('INSERT INTO events (run_id,stage,status,timestamp,data) VALUES (?,?,?,?,?)', (run_id,stage,status,now(),json.dumps(data,ensure_ascii=False)))

    def finish(self, run_id, status, changes):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT data FROM runs WHERE id=?',(run_id,)).fetchone()
            data = {**json.loads(row['data']), **changes}
            db.execute('UPDATE runs SET status=?, updated=?, data=? WHERE id=?',(status,now(),json.dumps(data,ensure_ascii=False),run_id))

    def get(self, run_id):
        with self.connect() as db:
            row = db.execute('SELECT * FROM runs WHERE id=?',(run_id,)).fetchone()
            if row is None:
                raise LookupError('紀錄不存在')
            result = dict(row); result['data'] = json.loads(result['data'])
            result['events'] = [{**dict(event),'data':json.loads(event['data'])} for event in db.execute('SELECT * FROM events WHERE run_id=? ORDER BY seq',(run_id,))]
            return result

    def list_generations(self):
        with self.connect() as db:
            rows = db.execute("SELECT * FROM runs WHERE kind='generation' ORDER BY started DESC LIMIT 50").fetchall()
        return [{'id':row['id'],'status':row['status'],'started':row['started'],'updated':row['updated'],'revision':row['revision'],'saved_character_id':json.loads(row['data']).get('saved_character_id'),'name':(json.loads(row['data']).get('draft') or {}).get('character',{}).get('character_name','尚未完成')} for row in rows]

    def save_draft(self, run_id, revision, draft):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute("SELECT * FROM runs WHERE id=? AND kind='generation'",(run_id,)).fetchone()
            if row is None:
                raise LookupError('草稿不存在')
            data = json.loads(row['data'])
            if row['status'] != 'completed' or row['revision'] != revision or data.get('saved_character_id'):
                raise ValueError('草稿已變更或已儲存為角色，請重新讀取。')
            draft = {**draft,'generation_id':run_id,'revision':revision+1}
            data['draft'] = draft
            db.execute('UPDATE runs SET data=?,revision=?,updated=? WHERE id=?',(json.dumps(data,ensure_ascii=False),revision+1,now(),run_id))
        return draft

    def character_saved(self, character, save_id):
        generation_id = character.source.get('generation_id')
        if generation_id:
            # This database is already scoped to the authenticated account.
            run = self.get(generation_id)
            if run['kind'] != 'generation':
                raise LookupError('生成紀錄不存在')
            self.finish(generation_id, 'completed', {'saved_character_id':character.id,'saved_character':character.model_dump()})
            self.event(generation_id,'character_saved','completed',{'character_id':character.id})
        self.finish(save_id,'completed',{'character':character.model_dump()})


class RecordedGenerationClient:
    stages = ['character_profile','style_guide','presentation','hobbies']

    def __init__(self, client, activity, run_id):
        self.client, self.activity, self.run_id, self.index = client, activity, run_id, 0

    async def complete(self, *, model, temperature, prompt, json_mode=False):
        kwargs = {'model':model,'temperature':temperature,'prompt':prompt,'json_mode':json_mode}
        stage = self.stages[self.index]; self.index += 1
        # Only the public GenerationClient parameters are captured, never transport/key objects.
        self.activity.event(self.run_id,stage,'started',kwargs)
        try:
            result = await self.client.complete(**kwargs)
        except BaseException as error:
            self.activity.event(self.run_id,stage,'failed',{'error_type':type(error).__name__})
            raise
        self.activity.event(self.run_id,stage,'completed',{'output':result})
        return result
