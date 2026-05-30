import boto3
from botocore.exceptions import ClientError
from app.storage.base.provider import BaseStorageProvider
from app.storage.base.models import StorageFileMetadata
from app.storage.base.exceptions import FileNotFoundStorageError, StorageError, StorageConnectionError
from app.core.config import settings

class S3StorageProvider(BaseStorageProvider):
    provider_name = "s3"

    def __init__(self):
        try:
            client_kwargs = {
                "aws_access_key_id": settings.AWS_ACCESS_KEY_ID,
                "aws_secret_access_key": settings.AWS_SECRET_ACCESS_KEY,
                "region_name": settings.AWS_REGION
            }
            if settings.S3_ENDPOINT_URL:
                client_kwargs["endpoint_url"] = settings.S3_ENDPOINT_URL
                
            self.s3_client = boto3.client("s3", **client_kwargs)
            self.bucket_name = settings.S3_BUCKET_NAME
        except Exception as e:
            raise StorageConnectionError(f"Failed to connect to AWS S3: {str(e)}")

    async def upload_file(self, file_data: bytes, key: str, mime_type: str) -> str:
        try:
            # Google Business Profile requires public HTTPS URL access to fetch local post media
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=key,
                Body=file_data,
                ContentType=mime_type,
                ACL="public-read"
            )
            return await self.generate_public_url(key)
        except ClientError as ce:
            raise StorageError(f"AWS S3 upload client error: {str(ce)}")
        except Exception as e:
            raise StorageError(f"Failed to upload file to S3: {str(e)}")

    async def read_file(self, key: str) -> bytes:
        try:
            response = self.s3_client.get_object(
                Bucket=self.bucket_name,
                Key=key
            )
            return response["Body"].read()
        except ClientError as ce:
            if ce.response["Error"]["Code"] in ["404", "NoSuchKey"]:
                raise FileNotFoundStorageError(f"File not found in S3: {key}")
            raise StorageError(f"AWS S3 read client error: {str(ce)}")
        except Exception as e:
            raise StorageError(f"Failed to read file from S3: {str(e)}")

    async def delete_file(self, key: str) -> None:
        try:
            if not await self.file_exists(key):
                raise FileNotFoundStorageError(f"File not found in S3: {key}")
                
            self.s3_client.delete_object(
                Bucket=self.bucket_name,
                Key=key
            )
        except ClientError as ce:
            raise StorageError(f"AWS S3 delete client error: {str(ce)}")
        except Exception as e:
            raise StorageError(f"Failed to delete file from S3: {str(e)}")

    async def generate_public_url(self, key: str) -> str:
        if settings.CDN_DOMAIN:
            return f"https://{settings.CDN_DOMAIN.rstrip('/')}/{key.lstrip('/')}"
            
        endpoint = settings.S3_ENDPOINT_URL or f"https://{self.bucket_name}.s3.{settings.AWS_REGION}.amazonaws.com"
        return f"{endpoint.rstrip('/')}/{key.lstrip('/')}"

    async def file_exists(self, key: str) -> bool:
        try:
            self.s3_client.head_object(Bucket=self.bucket_name, Key=key)
            return True
        except ClientError as ce:
            if ce.response["Error"]["Code"] in ["404", "NoSuchKey"]:
                return False
            raise StorageError(f"S3 file check failed: {str(ce)}")
        except Exception as e:
            raise StorageError(f"Failed to verify S3 file existence: {str(e)}")

    async def get_metadata(self, key: str) -> StorageFileMetadata:
        try:
            response = self.s3_client.head_object(Bucket=self.bucket_name, Key=key)
            return StorageFileMetadata(
                key=key,
                size_bytes=response.get("ContentLength", 0),
                mime_type=response.get("ContentType", "application/octet-stream")
            )
        except ClientError as ce:
            if ce.response["Error"]["Code"] in ["404", "NoSuchKey"]:
                raise FileNotFoundStorageError(f"File not found in S3: {key}")
            raise StorageError(f"Failed to fetch S3 file metadata: {str(ce)}")
        except Exception as e:
            raise StorageError(f"Failed to retrieve S3 metadata: {str(e)}")
