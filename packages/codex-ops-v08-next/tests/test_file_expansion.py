import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import files


def docx(path):
    parts = {
        '[Content_Types].xml': '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>',
        '_rels/.rels': '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="r1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>',
        'word/document.xml': '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>完整 DOCX</w:t></w:r></w:p><w:p><w:r><w:t>Second paragraph</w:t></w:r></w:p></w:body></w:document>'}
    with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, body in parts.items():
            archive.writestr(name, body.encode('utf-8'))


def pdf(path, font='Helvetica'):
    content = b'BT /F1 12 Tf 20 20 Td (Hello PDF) Tj ET\n'
    objects = [b'<< /Type /Catalog /Pages 2 0 R >>',
               b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
               b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 300] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>',
               b'<< /Length ' + str(len(content)).encode() + b' >>\nstream\n' + content + b'endstream',
               f'<< /Type /Font /Subtype /Type1 /BaseFont /{font} >>'.encode()]
    data = bytearray(b'%PDF-1.4\n%\xe2\xe3\xcf\xd3\n')
    offsets = []
    for index, body in enumerate(objects, 1):
        offsets.append(len(data))
        data.extend(f'{index} 0 obj\n'.encode() + body + b'\nendobj\n')
    xref = len(data)
    data.extend(f'xref\n0 {len(objects) + 1}\n0000000000 65535 f \n'.encode())
    for offset in offsets:
        data.extend(f'{offset:010} 00000 n \n'.encode())
    data.extend(f'trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n'.encode())
    path.write_bytes(data)


class FileExpansionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='codex-ops-documents-')
        self.root = Path(self.temp.name)
        (self.root / 'a.txt').write_text('one\ntwo\nthree\n', encoding='utf-8')
        (self.root / 'table.csv').write_text('name,value\n完整,001\nsecond,false\n', encoding='utf-8')
        docx(self.root / 'document.docx')
        pdf(self.root / 'document.pdf')

    def tearDown(self):
        self.temp.cleanup()

    def call(self, operation, args):
        return files.run(str(self.root), operation, args)

    def test_native_inspection_preserves_range_and_hex_scope(self):
        text = self.call('inspect', {'path': 'a.txt', 'offset': 2, 'limit': 1})
        self.assertEqual(text['items'][0]['text'], 'two')
        self.assertFalse(text['complete'])
        self.assertEqual(text['nextOffset'], 3)
        binary = self.call('inspect', {'path': 'document.pdf', 'view': 'hex', 'offset': 1, 'limit': 1})
        self.assertEqual(binary['items'][0]['view'], 'hex')
        self.assertEqual(binary['items'][0]['offset'], 0)
        self.assertFalse(binary['complete'])

    def test_native_table_keeps_strings_and_forward_page_metadata(self):
        first = self.call('read_table', {'path': 'table.csv', 'offset': 1, 'limit': 1})
        self.assertEqual(first['columns'], ['name', 'value'])
        self.assertEqual(first['items'][0]['cells'], ['完整', '001'])
        self.assertEqual(first['nextOffset'], 2)
        self.assertTrue(first['scanComplete'])
        self.assertTrue(first['pageComplete'])
        self.assertFalse(first['complete'])
        second = self.call('read_table', {'path': 'table.csv', 'offset': 2, 'limit': 1})
        self.assertEqual(second['items'][0]['cells'], ['second', 'false'])
        self.assertEqual(first['revision'], second['revision'])
        self.assertTrue(second['complete'])

    def test_native_docx_and_pdf_report_their_actual_scopes(self):
        word = self.call('read_docx', {'path': 'document.docx', 'limit': 1})
        self.assertEqual(word['scope'], 'main-body-paragraphs')
        self.assertEqual(word['items'][0]['text'], '完整 DOCX')
        self.assertIn('excludedContent', word)
        self.assertFalse(word['complete'])
        self.assertEqual(word['nextOffset'], 2)
        document = self.call('read_pdf', {'path': 'document.pdf'})
        self.assertEqual(document['scope'], 'page-text-layer-content-order')
        self.assertEqual(document['items'][0]['text'], 'Hello PDF')
        self.assertTrue(document['complete'])
        self.assertIn('excludedContent', document)

    def test_unsupported_pdf_is_not_claimed_complete(self):
        pdf(self.root / 'unsupported.pdf', font='CustomFont')
        value = self.call('read_pdf', {'path': 'unsupported.pdf'})
        self.assertFalse(value.get('complete', False))
        self.assertIn(value['status'], ('partial', 'error'))

    def test_document_paths_keep_root_and_credential_fences(self):
        (self.root / '.env').write_text('fixture')
        for operation in ('inspect', 'read_table', 'read_docx', 'read_pdf'):
            escaped = self.call(operation, {'path': '../outside'})
            self.assertEqual(escaped['error']['code'], 'PATH_RESTRICTED')
            denied = self.call(operation, {'path': '.env'})
            self.assertEqual(denied['error']['code'], 'CREDENTIAL_DENIED')

    def test_batch_native_results_are_ordered_and_keep_partial_failures(self):
        args = {'requests': [
            {'operation': 'read_table', 'args': {'path': 'table.csv'}},
            {'operation': 'read_docx', 'args': {'path': 'document.docx'}},
            {'operation': 'read_pdf', 'args': {'path': 'document.pdf'}},
            {'operation': 'stat', 'args': {'path': '../outside'}}]}
        original = copy.deepcopy(args)
        result = self.call('batch', args)
        self.assertEqual(args, original)
        self.assertEqual(result['status'], 'partial')
        self.assertTrue(result['requestResultsComplete'])
        self.assertEqual(result['sourceCompleteness'], 'per-result')
        self.assertEqual([row['index'] for row in result['items']], [0, 1, 2, 3])
        self.assertEqual(result['items'][2]['result']['items'][0]['text'], 'Hello PDF')
        self.assertEqual(result['items'][3]['result']['error']['code'], 'PATH_RESTRICTED')

    def test_batch_validates_all_requests_before_any_execution(self):
        invalid = [None, {}, {'requests': []}, {'requests': [{}] * 5}, {'requests': 'bad'},
                   {'requests': [], 'extra': True}, {'requests': [None]},
                   {'requests': [{'operation': 'stat'}]},
                   {'requests': [{'operation': 'batch', 'args': {}}]},
                   {'requests': [{'operation': 'write', 'args': {}}]},
                   {'requests': [{'operation': 'stat', 'args': []}]},
                   {'requests': [{'operation': 'stat', 'args': {}}, {'operation': 'remove', 'args': {}}]}]
        with patch.object(files, '_invoke_worker') as invoke:
            for args in invalid:
                self.assertEqual(self.call('batch', args)['error']['code'], 'INVALID_ARGUMENT')
            invoke.assert_not_called()

    def test_batch_runs_workers_concurrently_with_stable_order(self):
        barrier = threading.Barrier(4)
        gates = [threading.Event() for _ in range(4)]
        gates[3].set()
        completed = []
        def worker(base, operation, args):
            barrier.wait(timeout=3)
            index = args['index']
            self.assertTrue(gates[index].wait(timeout=3))
            completed.append(index)
            if index:
                gates[index - 1].set()
            return {'status': 'completed', 'value': index}
        args = {'requests': [{'operation': 'stat', 'args': {'index': index}} for index in range(4)]}
        with patch.object(files, '_invoke_worker', side_effect=worker):
            result = self.call('batch', args)
        self.assertEqual(completed, [3, 2, 1, 0])
        self.assertEqual([row['result']['value'] for row in result['items']], [0, 1, 2, 3])
        self.assertEqual(result['status'], 'completed')

    def test_worker_timeout_and_unknown_result_stay_visible_per_request(self):
        args = {'requests': [{'operation': 'stat', 'args': {'path': 'a.txt'}}]}
        with patch.object(files.native_process, 'run', side_effect=subprocess.TimeoutExpired('worker', 32)):
            result = self.call('batch', args)
        self.assertEqual(result['items'][0]['result']['error']['code'], 'WORKER_TIMEOUT')
        with patch.object(files, '_invoke_worker', return_value=None):
            result = self.call('batch', args)
        self.assertEqual(result['status'], 'partial')
        self.assertIsNone(result['items'][0]['result'])


if __name__ == '__main__':
    unittest.main()
