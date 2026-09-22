"""MongoDB and scheduler globals."""
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorGridFSBucket
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from config import MONGO_URL, DB_NAME

client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]
scheduler = AsyncIOScheduler(timezone="UTC")

# GridFS buckets — separated by purpose for clean lifecycle / indexing
social_images_fs = AsyncIOMotorGridFSBucket(db, bucket_name="social_images_fs")
showup_scores_fs = AsyncIOMotorGridFSBucket(db, bucket_name="showup_scores_fs")
