"""Bound public generation work and API request bodies on this single server."""
from collections import defaultdict, deque
from contextlib import contextmanager
from dataclasses import dataclass
import asyncio
import os
import re
import threading
import time

from starlette.responses import JSONResponse


@dataclass(frozen=True)
class WorkLimits:
    global_limit: int = 8
    user_limit: int = 2
    starts_per_minute: int = 20
    timeout_seconds: float = 180
    body_bytes: int = 1_048_576

    @classmethod
    def from_environment(cls):
        values=cls(global_limit=int(os.getenv('DIJI_MAX_GENERATIONS','8')),
            user_limit=int(os.getenv('DIJI_MAX_GENERATIONS_PER_USER','2')),
            starts_per_minute=int(os.getenv('DIJI_GENERATIONS_PER_MINUTE','20')),
            timeout_seconds=float(os.getenv('DIJI_GENERATION_TIMEOUT','180')),
            body_bytes=int(os.getenv('DIJI_MAX_API_BODY_BYTES','1048576')))
        if min(values.global_limit,values.user_limit,values.starts_per_minute,values.timeout_seconds,values.body_bytes)<=0:
            raise ValueError('DIJI 工作限制必須大於零')
        return values


_WORK_PATH=re.compile(r'^/api/(?:interactions|characters/generate|conversations/[^/]+/edit|character-generations/[^/]+/(?:revise|test-interactions(?:/edit)?)|memories/[^/]+/(?:extract|backfill))$')


def is_model_work(method,path):
    return method=='POST' and _WORK_PATH.fullmatch(path) is not None


class GenerationBusy(Exception):
    pass


class ModelWorkGate:
    def __init__(self,limits):
        self.limits=limits
        self.active=0
        self.users=defaultdict(int)
        self.starts={}
        self.lock=threading.Lock()

    @contextmanager
    def lease(self,user_id):
        with self.lock:
            now=time.monotonic()
            for key in list(self.starts):
                stamps=self.starts[key]
                while stamps and stamps[0]<=now-60:stamps.popleft()
                if not stamps:del self.starts[key]
            stamps=self.starts.setdefault(user_id,deque())
            if self.active>=self.limits.global_limit or self.users.get(user_id,0)>=self.limits.user_limit or len(stamps)>=self.limits.starts_per_minute:
                raise GenerationBusy('生成請求較多，請等候目前工作完成或稍後再試')
            stamps.append(now)
            self.active+=1;self.users[user_id]+=1
        try:
            yield
        finally:
            with self.lock:
                self.active-=1;self.users[user_id]-=1
                if not self.users[user_id]:del self.users[user_id]


class RequestBodyLimitMiddleware:
    def __init__(self,app,max_bytes):
        self.app,self.max_bytes=app,max_bytes

    async def __call__(self,scope,receive,send):
        if scope['type']!='http' or not scope.get('path','').startswith('/api/') or scope['method'] not in {'POST','PUT','PATCH','DELETE'}:
            return await self.app(scope,receive,send)
        headers=dict(scope.get('headers',[]))
        try:declared=int(headers.get(b'content-length',b'0'))
        except ValueError:declared=self.max_bytes+1
        if declared<0 or declared>self.max_bytes:
            return await self.reject(scope,receive,send)
        size=0;chunks=[]
        while True:
            message=await receive()
            if message['type']=='http.disconnect':return
            body=message.get('body',b'');size+=len(body)
            if size>self.max_bytes:return await self.reject(scope,receive,send)
            chunks.append(body)
            if not message.get('more_body',False):break
        sent=False
        async def replay():
            nonlocal sent
            if not sent:
                sent=True
                return {'type':'http.request','body':b''.join(chunks),'more_body':False}
            return await receive()
        return await self.app(scope,replay,send)

    async def reject(self,scope,receive,send):
        response=JSONResponse({'detail':'送出的資料過大，請減少內容後再試'},status_code=413,headers={'Cache-Control':'no-store'})
        await response(scope,receive,send)


class ModelWorkMiddleware:
    def __init__(self,app,limits,required):
        self.app,self.limits,self.required=app,limits,required
        self.gate=ModelWorkGate(limits)

    async def __call__(self,scope,receive,send):
        user=scope.get('state',{}).get('diji_user')
        if scope['type']!='http' or not self.required or user is None or not is_model_work(scope['method'],scope.get('path','')):
            return await self.app(scope,receive,send)
        started=False
        async def track(message):
            nonlocal started
            if message['type']=='http.response.start':started=True
            await send(message)
        try:
            with self.gate.lease(user.id):
                async with asyncio.timeout(self.limits.timeout_seconds):
                    return await self.app(scope,receive,track)
        except GenerationBusy as error:
            response=JSONResponse({'detail':str(error)},status_code=429,headers={'Retry-After':'10','Cache-Control':'no-store'})
            await response(scope,receive,send)
        except TimeoutError:
            if started:raise
            response=JSONResponse({'detail':'生成逾時，請稍後確認已送出的對話或草稿狀態'},status_code=504,headers={'Cache-Control':'no-store'})
            await response(scope,receive,send)
