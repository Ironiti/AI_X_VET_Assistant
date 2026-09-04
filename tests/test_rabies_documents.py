"""Offline regression tests: execute the real sender without starting a bot."""
import ast
import asyncio
from contextlib import contextmanager
import os
import importlib.util
import logging
from pathlib import Path
import tempfile
import textwrap
from types import SimpleNamespace, ModuleType
from typing import List, Tuple
import unittest
from unittest.mock import AsyncMock, patch

@contextmanager
def chdir(path):
    previous = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('document_files', REPO / 'utils/document_files.py')
resolver = importlib.util.module_from_spec(spec)
spec.loader.exec_module(resolver)
PDF = 'БЕШЕНСТВО_Преаналитические_требования_к_тесту_AN239RAB_и_AN239RABCT.pdf'
FORM = 'Сопроводительное письмо от врача на бешенство.xlsx'


class DocumentsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.folder = self.root / 'data/documents'
        self.folder.mkdir(parents=True)
        (self.folder/PDF).write_bytes(b'%PDF-rabies-test')
        (self.folder/FORM).write_bytes(b'PK-xlsx-test')

    def test_displayed_title_resolves_pdf_and_excel(self):
        for title, filename in [(PDF[:-4].replace('_', ' '), PDF), (FORM[:-5], FORM), (FORM, FORM)]:
            self.assertEqual(resolver.blank_file_name(title,self.folder),filename)

    def test_cache_only_pdf_and_no_substring_match(self):
        self.assertEqual(resolver.blank_file_name('Общий',self.folder),'Общий.pdf')
        self.assertEqual(resolver.blank_file_name('БЕШЕНСТВО',self.folder),'БЕШЕНСТВО.pdf')
        with self.assertRaises(ValueError):
            resolver.blank_file_name('../Общий',self.folder)

    def execute_sender(self, mode='local', callback=False):
        db=SimpleNamespace(find_blank_document_by_title=AsyncMock(return_value=None),
            get_blank_file_id=AsyncMock(return_value=None),save_blank_file_id=AsyncMock())
        uploader=SimpleNamespace(upload=AsyncMock(return_value='doc_uploaded'))
        if mode=='admin':
            db.find_blank_document_by_title.return_value={'file_id':'admin_current','title':'current'}
        if mode=='expired':
            db.get_blank_file_id.return_value={'file_id':'expired','vk_attachment':'expired'}
        sent=[]
        async def answer(*args,**kwargs):
            value=kwargs.get('attachment',args[0] if args else None)
            if value=='expired':
                raise RuntimeError('expired attachment')
            sent.append(value)
            return SimpleNamespace(message_id=len(sent),document=SimpleNamespace(file_id='new_id'))
        message=SimpleNamespace(peer_id=1,answer=answer,answer_document=answer)
        fake_api=SimpleNamespace(messages=SimpleNamespace(send=answer))
        fake_tools=ModuleType('vkbottle.tools')
        fake_tools.DocMessagesUploader=lambda api:uploader
        fake_bot=ModuleType('bot')
        fake_bot.bot=SimpleNamespace(api=fake_api)
        modules={'bot':fake_bot,'vkbottle.tools':fake_tools,'utils.document_files':resolver}
        ns={'List':List,'Tuple':Tuple,'Message':object,'db':db,'os':__import__('os'),
            'logger':logging.getLogger('test'),'asyncio':SimpleNamespace(sleep=AsyncMock()),
            'FSInputFile':Path,'BLANKS_PATH':str(self.folder),
            'blank_file_name':resolver.blank_file_name}
        if callback:
            source=(REPO/'bot/handlers/questions.py').read_text(encoding='utf-8-sig')
            start=source.index('                import random as _rnd',source.index('elif action == "show_blanks"'))
            end=source.index('                if sent_messages:',start)
            body=textwrap.dedent(source[start:end])
            program='async def callback_sender():\n'+textwrap.indent(body,'    ')+'\n    return sent_messages\n'
            ns.update(api=fake_api,peer_id=1,all_blank_names=[FORM[:-5],PDF[:-4].replace('_',' ')])
            exec(compile(program,'callback_sender','exec'),ns)
            coro=ns['callback_sender']()
        else:
            source=ast.parse((REPO/'bot/handlers/sending_style.py').read_text(encoding='utf-8-sig'))
            node=next(n for n in source.body if isinstance(n,ast.AsyncFunctionDef) and n.name=='send_blank_files_by_names')
            exec(compile(ast.Module(body=[node],type_ignores=[]),'sender','exec'),ns)
            coro=ns['send_blank_files_by_names'](message,[FORM[:-5],PDF[:-4].replace('_',' ')])
        with patch.dict('sys.modules',modules), chdir(self.root):
            result=asyncio.run(coro)
        self.assertEqual(len(sent),2,result)
        if mode=='admin':
            self.assertEqual(sent,['admin_current','admin_current'])
            uploader.upload.assert_not_called()
        elif uploader.upload.call_count:
            self.assertEqual([c.kwargs['title'] for c in uploader.upload.call_args_list],[FORM,PDF])
            self.assertEqual([c.args[0] for c in uploader.upload.call_args_list],[b'PK-xlsx-test',b'%PDF-rabies-test'])
        else:
            self.assertEqual([Path(p).name for p in sent],[FORM,PDF])

    def test_real_sender_sends_both_files(self):
        self.execute_sender()

    def test_admin_file_still_has_priority(self):
        self.execute_sender('admin')

    def test_expired_cached_file_falls_back_to_disk(self):
        self.execute_sender('expired')

    def test_vk_callback_sends_both_files_with_extensions(self):
        if 'vkbottle' not in (REPO/'bot/handlers/sending_style.py').read_text(encoding='utf-8-sig'):
            self.skipTest('VK callback only')
        self.execute_sender(callback=True)


if __name__=='__main__':
    unittest.main()
