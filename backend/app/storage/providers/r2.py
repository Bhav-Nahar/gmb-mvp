import boto3
from botocore.exceptions import ClientError
from app.storage.base.provider import BaseStorageProvider
from app.storage.base.exceptions import FileNotFoundStorageError, StorageError, StorageConnectionError
from app.core.config import settings

class R2StorageProvider(BaseStorageProvider):
    provider_name = "r2"

    def __init__(self):
        try:
            endpoint_url = f"https://{settings.R2_ACCOUNT_ID}.r2.cloudflarestorage.com"
            self.s3_client = boto3.client(
                "s3",
                aws_access_key_id=settings.R2_ACCESS_KEY_ID,
                aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
                endpoint_url=endpoint_url,
                region_name="auto"
            )
            self.bucket_name = settings.R2_BUCKET_NAME
        except Exception as e:
            raise StorageConnectionError(f"Failed to connect to Cloudflare R2: {str(e)}")

    async def upload_file(self, file_data: bytes, key: str, mime_type: str) -> str:
        try:
            # Cloudflare R2 handles public asset exposure bucket-wide via dashboard.
            # Specifying S3-style ACL="public-read" causes 400 bad request in standard R2 configs,
            # so we omit ACL for standard R2 compliance.
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=key,
                Body=file_data,
                ContentType=mime_type
            )
            return await self.generate_public_url(key)
        except ClientError as ce:
            raise StorageError(f"Cloudflare R2 upload client error: {str(ce)}")
        except Exception as e:
            raise StorageError(f"Failed to upload file to R2: {str(e)}")

    async def read_file(self, key: str) -> bytes:
        try:
            response = self.s3_client.get_object(
                Bucket=self.bucket_name,
                Key=key
            )
            return response["Body"].read()
        except ClientError as ce:
            if ce.response["Error"]["Code"] in ["404", "NoSuchKey"]:
                raise FileNotFoundStorageError(f"File not found in R2: {key}")
            raise StorageError(f"Cloudflare R2 read client error: {str(ce)}")
        except Exception as e:
            raise StorageError(f"Failed to read file from R2: {str(e)}")

    async def delete_file(self, key: str) -> None:
        try:
            if not await self.file_exists(key):
                raise FileNotFoundStorageError(f"File not found in R2: {key}")
                
            self.s3_client.delete_object(
                Bucket=self.bucket_name,
                Key=key
            )
        except ClientError as ce:
            raise StorageError(f"Cloudflare R2 delete client error: {str(ce)}")
        except Exception as e:
            raise StorageError(f"Failed to delete file from R2: {str(e)}")

    async def generate_public_url(self, key: str) -> str:
        if settings.CDN_DOMAIN:
            return f"https://{settings.CDN_DOMAIN.rstrip('/')}/{key.lstrip('/')}"
        
        # Fallback constructs the standard endpoint mapping
        endpoint_url = f"https://{settings.R2_ACCOUNT_ID}.r2.cloudflarestorage.com"
        return f"{endpoint_url}/{self.bucket_name}/{key.lstrip('/')}"

    async def file_exists(self, key: str) -> bool:
        try:
            self.s3_client.head_object(Bucket=self.bucket_name, Key=key)
            return True
        except ClientError as ce:
            if ce.response["Error"]["Code"] in ["404", "NoSuchKey"]:
                return False
            raise StorageError(f"R2 file check failed: {str(ce)}")
        except Exception as e:
            raise StorageError(f"Failed to verify R2 file existence: {str(e)}")
