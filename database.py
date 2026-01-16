"""
Database Module - Smart Condo Backend
Handles MongoDB connection, collections, and indexing
"""
from pymongo import MongoClient
from config import MONGO_URI

# ================= MONGODB CONNECTION =================
try:
    mongo_client = MongoClient(MONGO_URI)
    db = mongo_client["smart_condo"]
    
    # Collections
    users_col = db["users"]
    parcels_col = db["parcels"]
    kb_col = db["knowledge_base"]
    admins_col = db["admins"]
    audit_logs_col = db["audit_logs"]
    chat_history_col = db["chat_history"]
    
    print("✅ MongoDB Connected: smart_condo")
    
except Exception as e:
    print(f"❌ MongoDB Connection Error: {e}")
    raise

# ================= INDEX CREATION =================

def ensure_indexes():
    """Create database indexes for performance optimization"""
    try:
        # Users: Search by line_user_id (Unique), platform, room_number
        try:
            users_col.create_index([("line_user_id", 1)], unique=True)
        except:
            users_col.create_index([("line_user_id", 1)])
        
        users_col.create_index([("platform", 1)])
        users_col.create_index([("last_active", -1)])
        users_col.create_index([("room_number", 1)])
        
        # Parcels: Search by status, pin, timestamp, is_after_hours
        parcels_col.create_index([("status", 1)])
        try:
            parcels_col.create_index([("pin", 1)], unique=True)
        except:
            parcels_col.create_index([("pin", 1)])
        
        parcels_col.create_index([("timestamp", -1)])
        parcels_col.create_index([("status", 1), ("timestamp", -1)])
        parcels_col.create_index([("room_number", 1)])
        parcels_col.create_index([("is_after_hours", 1)])
        parcels_col.create_index([("status", 1), ("is_after_hours", 1)])  # Compound index
        
        # Audit Logs: Search by timestamp and actor_type
        audit_logs_col.create_index([("timestamp", -1)])
        audit_logs_col.create_index([("actor_type", 1)])
        audit_logs_col.create_index([("actor_type", 1), ("timestamp", -1)])  # Compound for filtering
        
        # Chat history
        chat_history_col.create_index([("line_user_id", 1), ("timestamp", -1)])
        
        print("✅ MongoDB Indexes ensured.")
    except Exception as e:
        print(f"⚠️ Failed to create indexes: {e}")

# Initialize indexes on import
ensure_indexes()

# Print database stats
try:
    print(f"📊 Database Stats:")
    print(f"   - Users: {users_col.count_documents({})}")
    print(f"   - Parcels: {parcels_col.count_documents({})}")
    print(f"   - Admins: {admins_col.count_documents({})}")
    print(f"   - Audit Logs: {audit_logs_col.count_documents({})}")
except Exception as e:
    print(f"⚠️ Cannot fetch database stats: {e}")
