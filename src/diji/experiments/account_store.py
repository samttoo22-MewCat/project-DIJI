"""Read shared defaults, writing only an account's atomic preset overrides."""
import fcntl
import json
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path

from .models import JailbreakPreset, RECENT_JAILBREAK_CATALOG


class AccountPresetStore:
    def __init__(self, defaults, private):
        self.defaults, self.private = defaults, private

    @staticmethod
    def _scoped(item, scope):
        return item.model_copy(update={'storage_scope':scope}) if isinstance(item,JailbreakPreset) else item

    def list(self):
        items={item.id:self._scoped(item,'default') for item in self.defaults.list()}
        items.update({item.id:self._scoped(item,'personal') for item in self.private.list()})
        return list(items.values())

    def get(self, preset_id):
        return next(item for item in self.list() if item.id==preset_id)

    @contextmanager
    def _lock(self):
        path=self.private.path
        path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        path.parent.chmod(0o700)
        with path.with_suffix('.lock').open('a') as lock:
            os.chmod(lock.name,0o600)
            fcntl.flock(lock,fcntl.LOCK_EX)
            try:yield
            finally:fcntl.flock(lock,fcntl.LOCK_UN)

    def _write(self, items):
        path=self.private.path
        with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=path.parent,delete=False) as output:
            temporary=Path(output.name)
            try:
                json.dump([item.model_dump() for item in items],output,ensure_ascii=False,indent=2)
                output.flush();os.fsync(output.fileno())
            except BaseException:
                temporary.unlink(missing_ok=True);raise
        try:temporary.replace(path)
        finally:temporary.unlink(missing_ok=True)
        path.chmod(0o600)

    def save(self, item):
        item=self._scoped(item,'personal')
        with self._lock():
            items=[existing for existing in self.private.list() if existing.id!=item.id]
            self._write([*items,item])
        return item

    def delete(self, preset_id):
        with self._lock():
            items=self.private.list()
            found=next((item for item in items if item.id==preset_id),None)
            if found is None:
                if any(item.id==preset_id for item in self.defaults.list()):
                    raise ValueError('系統預設越獄不能刪除；編輯後可儲存自己的版本')
                raise StopIteration(preset_id)
            self._write([item for item in items if item.id!=preset_id])
        return self._scoped(found,'personal')

    def import_recent_catalog(self):
        with self._lock():
            known={item.id for item in self.list()}
            added=[self._scoped(item,'personal') for item in RECENT_JAILBREAK_CATALOG if item.id not in known]
            if added:self._write([*self.private.list(),*added])
        return self.list()
