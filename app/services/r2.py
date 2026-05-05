import asyncio
from typing import Final

import boto3

from app.config import settings

CONTENT_TYPE_EXTENSION: Final[dict[str, str]] = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}

_r2_client = boto3.client(
    "s3",
    endpoint_url=(f"https://{settings.R2_ACCOUNT_ID}.r2.cloudflarestorage.com"),
    aws_access_key_id=settings.R2_ACCESS_KEY_ID,
    aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
    region_name="auto",
)


def _get_extension(content_type: str) -> str:
    extension = CONTENT_TYPE_EXTENSION.get(content_type)
    if extension is None:
        raise ValueError(f"Unsupported content type: {content_type}")
    return extension


async def upload_receipt(
    file_bytes: bytes,
    content_type: str,
    user_id: str,
    transaction_id: str,
) -> str:
    """Upload a receipt to R2 and return the object key."""
    extension = _get_extension(content_type)
    object_key = f"receipts/{user_id}/{transaction_id}.{extension}"

    await asyncio.to_thread(
        _r2_client.put_object,
        Bucket=settings.R2_BUCKET_NAME,
        Key=object_key,
        Body=file_bytes,
        ContentType=content_type,
    )

    return object_key


async def get_receipt_signed_url(object_key: str, expires_in: int = 3600) -> str:
    """Generate a signed URL for a receipt object key."""
    return await asyncio.to_thread(
        _r2_client.generate_presigned_url,
        "get_object",
        Params={
            "Bucket": settings.R2_BUCKET_NAME,
            "Key": object_key,
        },
        ExpiresIn=expires_in,
    )


async def delete_receipt(object_key: str) -> None:
    """Delete a receipt from the R2 bucket."""
    await asyncio.to_thread(
        _r2_client.delete_object,
        Bucket=settings.R2_BUCKET_NAME,
        Key=object_key,
    )
