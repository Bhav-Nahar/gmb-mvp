import asyncio
from app.db.session import SessionLocal
from app.models.review import Review
from app.models.location import Location
from app.services.ai_reply_service import generate_reply

async def test():
    db = SessionLocal()
    try:
        review = db.query(Review).filter(Review.id == 31838).first()
        if not review:
            print("Review 31838 not found")
            return
        location = db.query(Location).filter(Location.id == review.location_id).first()
        
        print("Testing generate_reply for review", review.id)
        result = await generate_reply(review, location)
        print("Success:", result)
    except Exception as e:
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(test())
