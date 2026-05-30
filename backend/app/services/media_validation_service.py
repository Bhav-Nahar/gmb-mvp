import io
import filetype
from PIL import Image
from fastapi import HTTPException, status

class MediaValidationService:
    ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}
    MIN_SIZE_BYTES = 10 * 1024  # 10 KB
    MIN_EDGE_PX = 250

    @classmethod
    def validate_image(cls, file_bytes: bytes, filename: str = None) -> dict:
        """
        Validates the uploaded file bytes according to GBP constraints.
        Returns resolved metadata (mime_type, width, height, file_size) on success.
        Raises HTTPException on validation failure.
        """
        file_size = len(file_bytes)
        
        # 1. Size Check
        if file_size < cls.MIN_SIZE_BYTES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File is too small ({file_size / 1024:.2f} KB). Minimum size is 10 KB."
            )

        # 2. MIME Check via pure-Python filetype
        kind = filetype.guess(file_bytes)
        if not kind or kind.mime not in cls.ALLOWED_MIME_TYPES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Unsupported or invalid file type. Only JPG, PNG, and WEBP images are allowed."
            )

        mime_type = kind.mime

        # 3. Pillow Dimension & Corruption Check
        try:
            image = Image.open(io.BytesIO(file_bytes))
            # Verify image is intact (raises an exception if file structure is corrupt)
            image.verify()
            
            # Re-open because verify() invalidates the image state for further reading
            image = Image.open(io.BytesIO(file_bytes))
            width, height = image.size
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Corrupt or invalid image file."
            )

        # 4. Dimension Check: Short edge >= 250px
        if min(width, height) < cls.MIN_EDGE_PX:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Image short edge is too small ({min(width, height)}px). Minimum required is {cls.MIN_EDGE_PX}px."
            )

        return {
            "mime_type": mime_type,
            "width": width,
            "height": height,
            "file_size": file_size
        }

media_validation_service = MediaValidationService()
