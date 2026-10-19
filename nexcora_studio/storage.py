"""Private S3 adapter. Object keys never become public URLs."""
from pathlib import Path
import boto3
from botocore.config import Config
from .runtime import blocking


class S3Storage:
    def __init__(self, settings):
        settings.require_storage()
        self.bucket = settings.s3_bucket
        self.client = boto3.client('s3', endpoint_url=settings.s3_endpoint, region_name=settings.s3_region,
                                   aws_access_key_id=settings.s3_access_key, aws_secret_access_key=settings.s3_secret_key,
                                   # One wire attempt: an earlier timed-out PUT must not
                                   # remain pending behind a later SDK retry's success.
                                   # Durable cleanup owns deletion retries.
                                   config=Config(connect_timeout=5, read_timeout=20, retries={'total_max_attempts': 1, 'mode': 'standard'}, max_pool_connections=4,
                                                 s3={'addressing_style': settings.s3_addressing_style}))

    async def put(self, key, path):
        def write():
            with Path(path).open('rb') as body:
                self.client.put_object(Bucket=self.bucket, Key=key, Body=body, ContentType='application/octet-stream')
        await blocking(write)

    async def get(self, key, path, max_bytes):
        def read():
            response = self.client.get_object(Bucket=self.bucket, Key=key)
            body = response['Body']
            try:
                count = 0
                with Path(path).open('wb') as destination:
                    while chunk := body.read(65_536):
                        count += len(chunk)
                        if count > max_bytes: raise OSError('stored object exceeds limit')
                        destination.write(chunk)
            finally:
                body.close()
        await blocking(read)

    async def delete(self, key):
        await blocking(lambda: self.client.delete_object(Bucket=self.bucket, Key=key))

    async def check(self):
        await blocking(lambda: self.client.head_bucket(Bucket=self.bucket))
