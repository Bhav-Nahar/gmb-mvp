import os
import io
import sys
import unittest
import hashlib
from unittest.mock import patch, MagicMock
from fastapi import HTTPException
from PIL import Image

# Map PostgreSQL JSONB to SQLite TEXT for in-memory test compilation compatibility
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import JSONB

@compiles(JSONB, "sqlite")
def compile_jsonb_sqlite(element, compiler, **kw):
    return "TEXT"

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session import Base
from app.models.organization import Organization
from app.models.user import User
from app.models.post import Post
from app.models.post_media import PostMedia
from app.services.media_validation_service import media_validation_service
from app.storage.factory import StorageProviderFactory
from app.storage.providers.local import LocalStorageProvider
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

class MediaPipelineTests(unittest.TestCase):
    def setUp(self):
        from app.db.session import engine, SessionLocal
        self.engine = engine
        Base.metadata.create_all(self.engine)
        self.SessionLocal = SessionLocal
        self.db = self.SessionLocal()

        # Clean up any leftover test data from previous runs to ensure idempotency
        self.db.query(PostMedia).filter(PostMedia.original_filename.in_(["valid.jpg", "large.jpg", "file.jpg", "new.jpg"])).delete(synchronize_session=False)
        self.db.query(User).filter(User.email.in_(["userA@acme.com", "userB@acme.com"])).delete(synchronize_session=False)
        self.db.query(Organization).filter(Organization.name.in_(["Organization A", "Organization B"])).delete(synchronize_session=False)
        self.db.commit()

        self.org_a = Organization(name="Organization A")
        self.org_b = Organization(name="Organization B")
        self.db.add_all([self.org_a, self.org_b])
        self.db.commit()
        self.db.refresh(self.org_a)
        self.db.refresh(self.org_b)

        self.user_a = User(
            email="userA@acme.com",
            name="User A",
            google_id="gid-a",
            role="Owner",
            is_active=True,
            organization_id=self.org_a.id,
        )
        self.user_b = User(
            email="userB@acme.com",
            name="User B",
            google_id="gid-b",
            role="Owner",
            is_active=True,
            organization_id=self.org_b.id,
        )
        self.db.add_all([self.user_a, self.user_b])
        self.db.commit()

        # Generate a valid dummy JPG image (15KB, 500x500 pixels) to pass validations
        img = Image.new("RGB", (500, 500), color="blue")
        out_buf = io.BytesIO()
        img.save(out_buf, format="JPEG")
        # Padding to exceed 10KB minimum constraint
        self.valid_jpg_bytes = out_buf.getvalue() + (b"\0" * 15000)
        self.valid_jpg_hash = hashlib.sha256(self.valid_jpg_bytes).hexdigest()

    def tearDown(self):
        self.db.close()

    def test_validation_rules_gbp_constraints(self):
        # 1. Test size constraint (<10KB should fail)
        small_img = Image.new("RGB", (300, 300), color="red")
        small_buf = io.BytesIO()
        small_img.save(small_buf, format="JPEG")
        small_bytes = small_buf.getvalue() # very small size
        
        with self.assertRaises(HTTPException) as ctx:
            media_validation_service.validate_image(small_bytes, "small.jpg")
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("File is too small", ctx.exception.detail)

        # 2. Test format constraint (GIF should fail)
        gif_img = Image.new("RGB", (300, 300), color="green")
        gif_buf = io.BytesIO()
        gif_img.save(gif_buf, format="GIF")
        gif_bytes = gif_buf.getvalue() + (b"\0" * 12000)
        
        with self.assertRaises(HTTPException) as ctx:
            media_validation_service.validate_image(gif_bytes, "test.gif")
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("Only JPG, PNG, and WEBP", ctx.exception.detail)

        # 3. Test dimension constraint (<250px on edge should fail)
        tiny_img = Image.new("RGB", (500, 100), color="blue")
        tiny_buf = io.BytesIO()
        tiny_img.save(tiny_buf, format="JPEG")
        tiny_bytes = tiny_buf.getvalue() + (b"\0" * 12000)
        
        with self.assertRaises(HTTPException) as ctx:
            media_validation_service.validate_image(tiny_bytes, "tiny.jpg")
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("Image short edge is too small", ctx.exception.detail)

        # 4. Test valid JPG passes successfully
        meta = media_validation_service.validate_image(self.valid_jpg_bytes, "valid.jpg")
        self.assertEqual(meta["mime_type"], "image/jpeg")
        self.assertEqual(meta["width"], 500)
        self.assertEqual(meta["height"], 500)

    def test_deduplication_scope_isolation(self):
        # Insert a valid file metadata into DB for Org A
        media_a = PostMedia(
            organization_id=self.org_a.id,
            storage_provider="local",
            storage_key="org_a/valid.jpg",
            media_type="PHOTO",
            original_filename="valid.jpg",
            mime_type="image/jpeg",
            file_size=len(self.valid_jpg_bytes),
            width=500,
            height=500,
            sha256_hash=self.valid_jpg_hash,
            cdn_url="http://localhost:8000/static/uploads/org_a/valid.jpg",
            upload_status="Uploaded",
            validation_status="Valid"
        )
        self.db.add(media_a)
        self.db.commit()

        # Org A uploads the identical file again -> should deduplicate (same ID)
        from app.api.media import upload_media
        
        mock_file = MagicMock()
        mock_file.filename = "valid.jpg"
        
        async def mock_read():
            return self.valid_jpg_bytes
        mock_file.read = mock_read

        # Simulate upload endpoint call for User A (Org A)
        import asyncio
        result_a = asyncio.run(upload_media(file=mock_file, db=self.db, current_user=self.user_a))
        self.assertEqual(result_a.id, media_a.id)

        # Org B uploads the same file -> must NOT deduplicate across tenant boundaries!
        with patch.object(LocalStorageProvider, "upload_file") as mock_upload, \
             patch("app.tasks.optimize_media_task.delay") as mock_opt, \
             patch("app.tasks.generate_thumbnail_task.delay") as mock_thumb:
             
            mock_upload.return_value = "http://localhost:8000/static/uploads/org_b/new.jpg"
            
            result_b = asyncio.run(upload_media(file=mock_file, db=self.db, current_user=self.user_b))
            self.assertNotEqual(result_b.id, media_a.id)
            self.assertEqual(result_b.organization_id, self.org_b.id)
            self.assertEqual(result_b.cdn_url, "http://localhost:8000/static/uploads/org_b/new.jpg")

    def test_tenant_isolation_ownership_validation(self):
        # Register a file for Org A
        media = PostMedia(
            organization_id=self.org_a.id,
            storage_provider="local",
            storage_key="org_a/file.jpg",
            media_type="PHOTO",
            sha256_hash="some-hash",
            cdn_url="http://localhost:8000/static/uploads/org_a/file.jpg",
            upload_status="Uploaded",
            validation_status="Valid"
        )
        self.db.add(media)
        self.db.commit()
        self.db.refresh(media)

        from app.api.media import get_media_details, delete_media
        
        # User B (Org B) requests User A's media -> 404 access denied
        with self.assertRaises(HTTPException) as ctx:
            get_media_details(id=media.id, db=self.db, current_user=self.user_b)
        self.assertEqual(ctx.exception.status_code, 404)

        # User B tries to delete User A's media -> 404 access denied
        with self.assertRaises(HTTPException) as ctx:
            delete_media(id=media.id, db=self.db, current_user=self.user_b)
        self.assertEqual(ctx.exception.status_code, 404)

        # User A requests own media -> succeeds
        res = get_media_details(id=media.id, db=self.db, current_user=self.user_a)
        self.assertEqual(res.id, media.id)

    @patch("app.storage.providers.local.LocalStorageProvider.read_file")
    @patch("app.storage.providers.local.LocalStorageProvider.upload_file")
    def test_celery_optimization_capping_longest_edge(self, mock_upload, mock_read):
        # Setup a very large image (3000x1500px, 15KB)
        large_img = Image.new("RGB", (3000, 1500), color="yellow")
        out_buf = io.BytesIO()
        large_img.save(out_buf, format="JPEG")
        large_bytes = out_buf.getvalue() + (b"\0" * 10000)

        # Mock storage provider outputs
        mock_read.return_value = large_bytes
        mock_upload.return_value = "http://localhost:8000/static/uploads/org_a/large_optimized.jpg"

        media = PostMedia(
            organization_id=self.org_a.id,
            storage_provider="local",
            storage_key="org_a/large.jpg",
            media_type="PHOTO",
            mime_type="image/jpeg",
            sha256_hash="large-hash",
            cdn_url="http://localhost:8000/static/uploads/org_a/large.jpg",
            upload_status="Uploaded",
            validation_status="Valid"
        )
        self.db.add(media)
        self.db.commit()
        self.db.refresh(media)

        from app.tasks import _optimize_media_async
        import asyncio
        
        asyncio.run(_optimize_media_async(media.id, self.org_a.id))
        
        # Verify db record update
        self.db.refresh(media)
        self.assertEqual(media.optimized_url, "http://localhost:8000/static/uploads/org_a/large_optimized.jpg")
        
        # Check logged metadata dimensions (capping longest edge to 2048px)
        # width = 3000 -> 2048, height = 1500 -> 1024
        self.assertEqual(media.log_metadata["optimized_width"], 2048)
        self.assertEqual(media.log_metadata["optimized_height"], 1024)

    @patch("app.storage.providers.local.LocalStorageProvider.read_file")
    @patch("app.storage.providers.local.LocalStorageProvider.upload_file")
    def test_celery_thumbnail_generation(self, mock_upload, mock_read):
        mock_read.return_value = self.valid_jpg_bytes
        mock_upload.return_value = "http://localhost:8000/static/uploads/org_a/valid_thumb.jpg"

        media = PostMedia(
            organization_id=self.org_a.id,
            storage_provider="local",
            storage_key="org_a/valid.jpg",
            media_type="PHOTO",
            mime_type="image/jpeg",
            sha256_hash=self.valid_jpg_hash,
            cdn_url="http://localhost:8000/static/uploads/org_a/valid.jpg",
            upload_status="Uploaded",
            validation_status="Valid"
        )
        self.db.add(media)
        self.db.commit()
        self.db.refresh(media)

        from app.tasks import _generate_thumbnail_async
        import asyncio
        
        asyncio.run(_generate_thumbnail_async(media.id, self.org_a.id))
        
        # Verify db record update
        self.db.refresh(media)
        self.assertEqual(media.thumbnail_url, "http://localhost:8000/static/uploads/org_a/valid_thumb.jpg")
        
        # Thumbnail maintaining aspect ratio of 500x500 -> 300x300
        self.assertEqual(media.log_metadata["thumbnail_width"], 300)
        self.assertEqual(media.log_metadata["thumbnail_height"], 300)

if __name__ == "__main__":
    unittest.main()
