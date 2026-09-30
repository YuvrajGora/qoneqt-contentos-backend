"""
Storage Client Service — Milestone 9.
Handles uploading final generated videos to an S3-compatible cloud storage bucket.
Falls back to returning a local `/assets` URL if S3 is not configured.
"""
import logging
import os
import boto3
from botocore.exceptions import BotoCoreError, ClientError
from app.core.config import settings

logger = logging.getLogger(__name__)

class StorageUploadError(Exception):
    """Raised when uploading to cloud storage fails."""
    pass

class StorageClient:
    def __init__(self):
        self.bucket_name = settings.s3_bucket_name
        self.aws_access_key_id = settings.aws_access_key_id
        self.aws_secret_access_key = settings.aws_secret_access_key
        self.aws_region = settings.aws_region
        self.endpoint_url = settings.s3_endpoint_url

        if self.is_configured():
            try:
                self.s3_client = boto3.client(
                    "s3",
                    aws_access_key_id=self.aws_access_key_id,
                    aws_secret_access_key=self.aws_secret_access_key,
                    region_name=self.aws_region,
                    endpoint_url=self.endpoint_url,
                )
            except Exception as e:
                logger.warning(f"Failed to initialize S3 client: {e}")
                self.s3_client = None
        else:
            self.s3_client = None

    def is_configured(self) -> bool:
        return bool(self.bucket_name)

    def upload_video(self, job_id: str, local_file_path: str) -> str:
        """
        Uploads a video to S3 and returns the public URL.
        Falls back to returning a local /assets/ path if S3 is not configured.
        """
        if not os.path.exists(local_file_path):
            raise StorageUploadError(f"Local file not found: {local_file_path}")

        filename = os.path.basename(local_file_path)

        if not self.is_configured() or not self.s3_client:
            logger.info("S3 not configured. Returning local fallback URL for %s", filename)
            base = getattr(settings, "base_url", "").rstrip("/")
            if base:
                return f"{base}/assets/{filename}"
            return f"/assets/{filename}"

        logger.info("Uploading %s to S3 bucket %s", filename, self.bucket_name)

        try:
            self.s3_client.upload_file(
                local_file_path,
                self.bucket_name,
                filename,
                ExtraArgs={'ContentType': 'video/mp4'}
            )
        except (BotoCoreError, ClientError) as e:
            logger.error("Failed to upload video to S3: %s", e)
            raise StorageUploadError(f"Cloud upload failed: {e}") from e

        # Construct public URL
        if self.endpoint_url:
            # Custom endpoint (e.g. Supabase, R2, etc.)
            base_url = self.endpoint_url.rstrip("/")
            if "localhost" in base_url or "127.0.0.1" in base_url:
                # Local mock s3 path style
                return f"{base_url}/{self.bucket_name}/{filename}"
            else:
                # Typically vhost style for cloud endpoints depending on provider
                # But path-style is safer for generic endpoints
                return f"{base_url}/{self.bucket_name}/{filename}"
        else:
            # Standard AWS S3 URL
            region = self.aws_region or "us-east-1"
            return f"https://{self.bucket_name}.s3.{region}.amazonaws.com/{filename}"
