"""Add production MongoDB indexes."""
import asyncio
import motor.motor_asyncio
import os

async def create_indexes():
    client = motor.motor_asyncio.AsyncIOMotorClient(
        os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    )
    db = client[os.environ.get("DB_NAME", "showup")]
    
    # Users
    await db.users.create_index("email", unique=True)
    await db.users.create_index("id", unique=True)
    
    # Webinars - critical for multi-tenant isolation
    await db.webinars.create_index([("id", 1), ("owner_id", 1)], unique=True)
    await db.webinars.create_index("owner_id")
    await db.webinars.create_index("starts_at")
    await db.webinars.create_index("status")
    
    # Touches
    await db.touches.create_index([("webinar_id", 1), ("touch_num", 1)])
    await db.touches.create_index("owner_id")
    await db.touches.create_index("id", unique=True)
    await db.touches.create_index([("approval_status", 1), ("sent_status", 1), ("scheduled_at", 1)])
    
    # Registrants
    await db.registrants.create_index([("webinar_id", 1), ("email", 1)], unique=True)
    await db.registrants.create_index("owner_id")
    await db.registrants.create_index("webinar_id")
    
    # Settings
    await db.settings.create_index("owner_id", unique=True)
    
    # Social images, scores
    await db.social_images.create_index("webinar_id")
    await db.showup_scores.create_index("webinar_id")
    await db.lead_magnets.create_index("webinar_id")
    await db.waitlist.create_index("email", unique=True)
    
    print("✅ All indexes created")
    client.close()

asyncio.run(create_indexes())
