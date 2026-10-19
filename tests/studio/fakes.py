from pathlib import Path


class MemoryStorage:
    """Only the external storage boundary is replaced; actual bytes are retained."""
    def __init__(self):
        self.objects = {}
        self.fail_after_put = False
        self.fail_delete = False

    async def put(self, key, path):
        self.objects[key] = Path(path).read_bytes()
        if self.fail_after_put: raise OSError('simulated lost storage response')

    async def get(self, key, path, max_bytes):
        data = self.objects[key]
        if len(data) > max_bytes: raise OSError('invalid object size')
        Path(path).write_bytes(data)

    async def delete(self, key):
        if self.fail_delete: raise OSError('simulated storage outage')
        self.objects.pop(key, None)
