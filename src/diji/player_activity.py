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
            db.execute('CREATE TABLE IF NOT EXISTS draft_versions (run_id TEXT NOT NULL, revision INTEGER NOT NULL, created TEXT NOT NULL, source TEXT NOT NULL, note TEXT NOT NULL, restored_from INTEGER, data TEXT NOT NULL, PRIMARY KEY(run_id,revision))')
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
            row = db.execute('SELECT * FROM runs WHERE id=?',(run_id,)).fetchone()
            data = {**json.loads(row['data']), **changes}
            db.execute('UPDATE runs SET status=?, updated=?, data=? WHERE id=?',(status,now(),json.dumps(data,ensure_ascii=False),run_id))
            if row['kind'] == 'generation' and changes.get('draft'):
                self._seed_versions(db, {**dict(row),'data':json.dumps(data,ensure_ascii=False)})

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
            rows = db.execute("SELECT * FROM runs WHERE kind='generation' ORDER BY started DESC").fetchall()
        return [{'id':row['id'],'status':row['status'],'started':row['started'],'updated':row['updated'],'revision':row['revision'],'saved_character_id':json.loads(row['data']).get('saved_character_id'),'name':(json.loads(row['data']).get('draft') or {}).get('character',{}).get('character_name','尚未完成')} for row in rows]

    @staticmethod
    def _put_version(db, run_id, revision, draft, source, stamp, note='', restored_from=None, *, strict=False):
        snapshot = {**draft,'generation_id':run_id,'revision':revision}
        db.execute(('INSERT' if strict else 'INSERT OR IGNORE')+' INTO draft_versions VALUES (?,?,?,?,?,?,?)',
            (run_id,revision,stamp,source,note,restored_from,json.dumps(snapshot,ensure_ascii=False)))

    def _seed_versions(self, db, row):
        if db.execute('SELECT 1 FROM draft_versions WHERE run_id=? LIMIT 1',(row['id'],)).fetchone():
            return
        data = json.loads(row['data'])
        if not data.get('draft'):
            return
        from .character_generation.service import CharacterGenerationResult, CharacterGenerationService, GeneratedCharacter
        outputs = {event['stage']:event for event in db.execute("SELECT * FROM events WHERE run_id=? AND status='completed'",(row['id'],))}
        if all(stage in outputs for stage in ('character_profile','style_guide','presentation','hobbies')):
            try:
                raw = {key:json.loads(event['data'])['output'] for key,event in outputs.items() if key in ('character_profile','style_guide','presentation','hobbies')}
                character = GeneratedCharacter.model_validate(json.loads(CharacterGenerationService._json_object(raw['character_profile'])))
                presentation = json.loads(CharacterGenerationService._json_object(raw['presentation']))
                initial = CharacterGenerationResult(generation_id=row['id'],character=character,style_guide=raw['style_guide'],
                    full_prompt=CharacterGenerationService._full_prompt(character,raw['style_guide']),
                    description_for_app=str(presentation.get('description_for_app','')),brief_description=str(presentation.get('brief_description','')),
                    category=str(presentation.get('category','未分類')),hobbies=raw['hobbies'])
                self._put_version(db,row['id'],0,initial.model_dump(),'generated',outputs['hobbies']['timestamp'])
            except (ValueError,KeyError,TypeError):
                pass
        for audit in db.execute("SELECT * FROM runs WHERE kind='draft_revision' ORDER BY started"):
            revision = json.loads(audit['data'])
            if revision.get('generation_id') != row['id']:
                continue
            if revision.get('before') is not None:
                self._put_version(db,row['id'],revision['base_revision'],revision['before'],'recovered',audit['started'],'從既有修改前快照匯入')
            if audit['status'] == 'completed' and revision.get('result_revision') is not None and revision.get('proposed'):
                self._put_version(db,row['id'],revision['result_revision'],revision['proposed'],'ai',audit['updated'],revision.get('summary',''))
        self._put_version(db,row['id'],row['revision'],data['draft'],'generated' if row['revision']==0 else 'recovered',row['updated'],'既有完整草稿')

    def versions(self, run_id, before=None, limit=100):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute("SELECT * FROM runs WHERE id=? AND kind='generation'",(run_id,)).fetchone()
            if row is None:
                raise LookupError('草稿不存在')
            self._seed_versions(db,row)
            rows = db.execute('SELECT revision,created,source,note,restored_from FROM draft_versions WHERE run_id=? AND (? IS NULL OR revision<?) ORDER BY revision DESC LIMIT ?',
                (run_id,before,before,limit+1)).fetchall()
            return {'versions':[dict(item) for item in rows[:limit]],'has_more':len(rows)>limit,'next_before':rows[limit-1]['revision'] if len(rows)>limit else None,'current_revision':row['revision']}

    def version(self, run_id, revision):
        self.versions(run_id,limit=1)
        with self.connect() as db:
            row = db.execute('SELECT * FROM draft_versions WHERE run_id=? AND revision=?',(run_id,revision)).fetchone()
            if row is None:
                raise LookupError('版本不存在')
            return {**{k:row[k] for k in row.keys() if k!='data'},'draft':json.loads(row['data'])}

    def save_draft(self, run_id, revision, draft, *, source='manual', note='', restored_from=None):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute("SELECT * FROM runs WHERE id=? AND kind='generation'",(run_id,)).fetchone()
            if row is None:
                raise LookupError('草稿不存在')
            data = json.loads(row['data'])
            if row['status'] != 'completed' or row['revision'] != revision or data.get('saved_character_id'):
                raise ValueError('草稿已變更或已儲存為角色，請重新讀取。')
            self._seed_versions(db,row)
            draft = {**draft,'generation_id':run_id,'revision':revision+1}
            data['draft'] = draft
            self._put_version(db,run_id,revision+1,draft,source,now(),note,restored_from,strict=True)
            db.execute('UPDATE runs SET data=?,revision=?,updated=? WHERE id=?',(json.dumps(data,ensure_ascii=False),revision+1,now(),run_id))
        return draft

    def restore_version(self, run_id, target_revision, expected_revision):
        self.versions(run_id,limit=1)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute("SELECT * FROM runs WHERE id=? AND kind='generation'",(run_id,)).fetchone()
            if row is None:
                raise LookupError('草稿不存在')
            data = json.loads(row['data'])
            if row['revision'] != expected_revision or row['status'] != 'completed':
                raise ValueError('草稿已變更，請重新讀取後再還原')
            target = db.execute('SELECT data FROM draft_versions WHERE run_id=? AND revision=?',(run_id,target_revision)).fetchone()
            if target is None:
                raise LookupError('版本不存在')
            stamp = now()
            if data.get('saved_character_id'):
                new_id = 'gen-' + uuid.uuid4().hex
                draft = {**json.loads(target['data']),'generation_id':new_id,'revision':0}
                fork = {'draft':draft,'request':data.get('request',{}),'parent_generation_id':run_id,'parent_revision':target_revision}
                db.execute('INSERT INTO runs VALUES (?,?,?,?,?,?,0)',(new_id,'generation','completed',stamp,stamp,json.dumps(fork,ensure_ascii=False)))
                self._put_version(db,new_id,0,draft,'rollback',stamp,f'從原草稿版本 {target_revision+1} 建立',target_revision,strict=True)
            else:
                draft = {**json.loads(target['data']),'generation_id':run_id,'revision':expected_revision+1}
                self._put_version(db,run_id,expected_revision+1,draft,'rollback',stamp,f'還原版本 {target_revision+1}',target_revision,strict=True)
                data['draft'] = draft
                db.execute('UPDATE runs SET data=?,revision=?,updated=? WHERE id=?',(json.dumps(data,ensure_ascii=False),expected_revision+1,stamp,run_id))
            db.execute('INSERT INTO events (run_id,stage,status,timestamp,data) VALUES (?,?,?,?,?)',
                (run_id,'draft_rollback','completed',stamp,json.dumps({'from_revision':expected_revision,'target_revision':target_revision,'result_generation_id':draft['generation_id'],'result_revision':draft['revision']})))
            return draft

    def character_saved(self, character, save_id):
        generation_id = character.source.get('generation_id')
        if generation_id:
            # This database is already scoped to the authenticated account.
            run = self.get(generation_id)
            if run['kind'] != 'generation':
                raise LookupError('生成紀錄不存在')
            if run['data'].get('draft') and not run['data'].get('saved_character_id'):
                current = run['data']['draft']
                confirmed = {**current,'character':{**character.profile,'character_name':character.name},'style_guide':character.style_guide,
                    'full_prompt':character.full_prompt,'description_for_app':character.premise,
                    **{key:character.generation_metadata.get(key,current.get(key,'')) for key in ('brief_description','category','hobbies')}}
                if confirmed != current:
                    self.save_draft(generation_id,run['revision'],confirmed,source='confirmed',note='確認儲存角色時的完整設定')
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
