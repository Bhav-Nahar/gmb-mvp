import asyncio
import os
import sys
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Add backend to sys.path
sys.path.append(os.path.join(os.getcwd(), "backend"))

from app.models.review import Review
from app.services.sentiment_service import tag_reviews_sentiment
from app.core.config import settings

DATABASE_URL = "postgresql://postgres:postgres@localhost:5435/gmb_db"
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)

async def test_sentiment():
    db = SessionLocal()
    try:
        # Get one untagged review
        review = db.query(Review).filter(Review.sentiment_tagged_at == None).first()
        if not review:
            print("No untagged reviews found.")
            return
        
        print(f"Testing sentiment for review ID: {review.id}")
        print(f"Review comment: {review.comment[:100]}...")
        print(f"Using LLM Provider: {settings.LLM_PROVIDER}")
        print(f"Using LLM Model: {settings.LLM_MODEL}")
        print(f"GROQ_API_KEY present: {bool(settings.GROQ_API_KEY)}")
        
        try:
            await tag_reviews_sentiment([review], db)
            db.refresh(review)
            print(f"Result - Sentiment: {review.sentiment}, Category: {review.issue_category}")
            if review.sentiment_tagged_at:
                print("SUCCESS: Review tagged.")
            else:
                print("FAILURE: Review still not tagged.")
        except Exception as e:
            print(f"ERROR during tagging: {e}")
            
    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(test_sentiment())
