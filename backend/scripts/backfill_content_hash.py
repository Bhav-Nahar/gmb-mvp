import sys
import os
import hashlib
from dotenv import load_dotenv

# Add backend directory to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv()

from app.db.session import SessionLocal
from app.models.review import Review

import datetime

def generate_content_hash(rating: int, comment: str, reply_text: str, updated_at) -> str:
    if updated_at:
        # Convert to UTC and strip timezone info so that both aware and naive datetimes are hashed consistently as naive UTC strings
        if updated_at.tzinfo is not None:
            updated_at = updated_at.astimezone(datetime.timezone.utc).replace(tzinfo=None)
        updated_at_str = updated_at.isoformat()
    else:
        updated_at_str = ''
    hash_str = f"{rating or 0}:{comment or ''}:{reply_text or ''}:{updated_at_str}"
    return hashlib.sha256(hash_str.encode('utf-8')).hexdigest()

def backfill_content_hashes():
    db = SessionLocal()
    try:
        print("Starting content_hash backfill...")
        total_reviews = db.query(Review).count()
        print(f"Total reviews to process: {total_reviews}")

        batch_size = 1000
        offset = 0

        while True:
            # Fetch reviews sequentially using offset to update all hashes
            reviews = db.query(Review).order_by(Review.id).offset(offset).limit(batch_size).all()
            if not reviews:
                break

            for review in reviews:
                review.content_hash = generate_content_hash(
                    review.rating,
                    review.comment,
                    review.reply_text,
                    review.review_updated_at
                )

            db.commit()
            offset += len(reviews)
            print(f"Processed {offset} / {total_reviews} reviews")

        print("Backfill complete.")
    except Exception as e:
        db.rollback()
        print(f"Error during backfill: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    backfill_content_hashes()
