from motor.motor_asyncio import AsyncIOMotorClient
from config import MONGO_URI, DB_NAME

client = AsyncIOMotorClient(MONGO_URI)
db = client[DB_NAME]
user_collection = db["users"]
session_collection = db["sessions"]
account_collection = db["accounts"]
