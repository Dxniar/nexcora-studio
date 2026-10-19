import asyncio
import io
from pathlib import Path
import tempfile
import unittest
import zipfile
from nexcora_studio.file_validation import validate_file
from nexcora_studio.errors import DomainError


class FileValidationTests(unittest.IsolatedAsyncioTestCase):
    async def check(self, content, extension):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'payload'
            path.write_bytes(content)
            return await validate_file(path, extension)

    async def test_utf8_and_binary_or_mismatched_formats(self):
        self.assertEqual(await self.check('Текст задачи'.encode(), '.txt'), 'text/plain')
        for content, extension in [(b'a\x00b', '.txt'), (b'not an image', '.png'), (b'%PDF fake', '.pdf'), (b'not a word file', '.doc')]:
            with self.subTest(extension=extension):
                with self.assertRaises(DomainError):
                    await self.check(content, extension)

    async def test_docx_requires_word_structure_and_rejects_traversal_vba_and_dtd(self):
        content_types = b'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>'
        doc = b'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body/></w:document>'
        def package(extra=None, document=doc):
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, 'w') as archive:
                archive.writestr('[Content_Types].xml', content_types)
                archive.writestr('word/document.xml', document)
                if extra: archive.writestr(*extra)
            return buffer.getvalue()
        self.assertIn('wordprocessingml', await self.check(package(), '.docx'))
        for data in [package(('../escape.txt', 'bad')), package(('word/vbaProject.bin', 'macro')), package(document=b'<!DOCTYPE x [<!ENTITY y "value">]><x>&y;</x>')]:
            with self.assertRaises(DomainError): await self.check(data, '.docx')
