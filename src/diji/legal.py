"""Publish the reviewed repository documents and identify their exact content."""
from hashlib import sha256
from html import escape
from pathlib import Path
import re

import markdown


class LegalDocuments:
    def __init__(self,directory: Path):
        self.documents={
            'privacy':('使用者隱私條款',(directory/'privacy-policy.md').read_text(encoding='utf-8')),
            'terms':('使用者規約',(directory/'usage-notice.md').read_text(encoding='utf-8')),
        }
        self.version=sha256('\0'.join(text for _,text in self.documents.values()).encode()).hexdigest()
        dates=[re.search(r'最後更新：\s*(\d{4}-\d{2}-\d{2})',text) for _,text in self.documents.values()]
        self.updated=max((match.group(1) for match in dates if match),default='')

    def metadata(self):
        return {'version':self.version,'updated':self.updated,'privacy_url':'/legal/privacy','terms_url':'/legal/terms'}

    def page(self,document):
        title,text=self.documents[document]
        # Only the two repository-owned documents are rendered, never request input.
        body=markdown.markdown(text,extensions=['tables'])
        return f'''<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{escape(title)} — DIJI</title><link rel="icon" href="/icons/diji-192.png"><link rel="stylesheet" href="/legal.css?v=20261101-1"></head><body><main class="legal-page"><nav aria-label="條款導覽"><a href="/">DIJI 首頁</a><a href="/legal/privacy">隱私條款</a><a href="/legal/terms">使用者規約</a></nav><article>{body}</article><footer>文件更新：{escape(self.updated)} · 版本 {self.version[:12]}<br>閱讀文件不代表已同意；請返回登入視窗自行確認。</footer></main></body></html>'''
