"""No rendering, macros, network fetching or document execution."""
import json
from pathlib import Path, PurePosixPath
import sys

_job = None


def bound_resources():
    global _job
    if sys.platform == 'win32':
        import ctypes
        from ctypes import wintypes
        class Basic(ctypes.Structure):
            _fields_ = [('process_time', ctypes.c_longlong), ('job_time', ctypes.c_longlong), ('flags', wintypes.DWORD),
                        ('min_ws', ctypes.c_size_t), ('max_ws', ctypes.c_size_t), ('processes', wintypes.DWORD),
                        ('affinity', ctypes.c_size_t), ('priority', wintypes.DWORD), ('scheduling', wintypes.DWORD)]
        class IO(ctypes.Structure):
            _fields_ = [(name, ctypes.c_ulonglong) for name in ('read_ops', 'write_ops', 'other_ops', 'read_bytes', 'write_bytes', 'other_bytes')]
        class Extended(ctypes.Structure):
            _fields_ = [('basic', Basic), ('io', IO), ('process_memory', ctypes.c_size_t), ('job_memory', ctypes.c_size_t), ('peak_process', ctypes.c_size_t), ('peak_job', ctypes.c_size_t)]
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.CreateJobObjectW.restype = wintypes.HANDLE
        kernel.GetCurrentProcess.restype = wintypes.HANDLE
        kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        _job = kernel.CreateJobObjectW(None, None)
        limits = Extended()
        limits.basic.flags = 0x100  # JOB_OBJECT_LIMIT_PROCESS_MEMORY
        limits.process_memory = 256 * 1024 * 1024
        if not _job or not kernel.SetInformationJobObject(_job, 9, ctypes.byref(limits), ctypes.sizeof(limits)) or not kernel.AssignProcessToJobObject(_job, kernel.GetCurrentProcess()):
            raise RuntimeError('Unable to constrain validator')
    else:
        import resource
        resource.setrlimit(resource.RLIMIT_AS, (256 * 1024 * 1024, 256 * 1024 * 1024))
        resource.setrlimit(resource.RLIMIT_CPU, (10, 10))


def validate_docx(path):
    from zipfile import ZipFile, ZIP_DEFLATED, ZIP_STORED
    from defusedxml.ElementTree import fromstring
    with ZipFile(path) as archive:
        parts = archive.infolist()
        if len(parts) > 1000: raise ValueError('too many parts')
        names, total, document, types = set(), 0, None, None
        for part in parts:
            name = part.filename
            lower = name.lower()
            pure = PurePosixPath(name)
            if name.startswith('/') or '\\' in name or '..' in pure.parts or ':' in name or lower in names or part.flag_bits & 1 or part.compress_type not in (ZIP_DEFLATED, ZIP_STORED):
                raise ValueError('invalid package path')
            names.add(lower)
            if any(value in lower for value in ('vbaproject', 'activex/', 'embeddings/')): raise ValueError('active content')
            data = bytearray()
            with archive.open(part) as stream:
                while block := stream.read(65_536):
                    total += len(block)
                    if len(data) + len(block) > 10_485_760 or total > 52_428_800: raise ValueError('expanded package too large')
                    data.extend(block)
            if name.endswith(('.xml', '.rels')):
                root = fromstring(bytes(data), forbid_dtd=True, forbid_entities=True, forbid_external=True)
                if name == '[Content_Types].xml': types = root
                if name == 'word/document.xml': document = root
        if types is None or document is None: raise ValueError('not a Word document')
        main_type = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml'
        if not any(item.attrib.get('PartName') == '/word/document.xml' and item.attrib.get('ContentType') == main_type for item in types): raise ValueError('invalid Word main part')
        if any('macroenabled' in str(item.attrib).lower() or 'vba' in str(item.attrib).lower() for item in types): raise ValueError('macro content')
        if document.tag not in ('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}document', '{http://purl.oclc.org/ooxml/wordprocessingml/main}document'): raise ValueError('invalid document root')
    return 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'


def inspect(path, extension):
    if not 0 < path.stat().st_size <= 10_485_760: raise ValueError('invalid size')
    if extension == '.txt':
        text = path.read_bytes().decode('utf-8-sig')
        if '\x00' in text: raise ValueError('binary text')
        return 'text/plain'
    if extension == '.docx': return validate_docx(path)
    if extension == '.doc':
        import olefile
        with olefile.OleFileIO(path) as document:
            if not document.exists('WordDocument') or not (document.exists('0Table') or document.exists('1Table')): raise ValueError('not a Word compound file')
        return 'application/msword'
    if extension == '.pdf':
        from pypdf import PdfReader
        reader = PdfReader(path, strict=True)
        if reader.is_encrypted or not 0 < len(reader.pages) <= 1000: raise ValueError('invalid PDF')
        return 'application/pdf'
    if extension in ('.jpg', '.jpeg', '.png', '.webp'):
        import warnings
        from PIL import Image
        Image.MAX_IMAGE_PIXELS = 25_000_000
        expected = {'.jpg': 'JPEG', '.jpeg': 'JPEG', '.png': 'PNG', '.webp': 'WEBP'}[extension]
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(path) as image:
                if image.format != expected or getattr(image, 'n_frames', 1) != 1 or image.width > 10_000 or image.height > 10_000 or image.width * image.height > 25_000_000: raise ValueError('image limits')
                image.verify()
            with Image.open(path) as image: image.load()
        return Image.MIME[expected]
    raise ValueError('unsupported extension')


def main():
    try:
        bound_resources()
        mime = inspect(Path(sys.argv[1]), sys.argv[2])
        print(json.dumps({'ok': True, 'mime': mime}))
    except Exception:
        print('{"ok":false}')
        raise SystemExit(1)


if __name__ == '__main__': main()
