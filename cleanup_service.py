"""
Cleanup Service Module - Smart Condo Backend
Handles automatic cleanup of old data (90-day retention)
"""
import datetime
from database import parcels_col, chat_history_col
from image_service import delete_image_by_url

def cleanup_old_parcels():
    """
    Delete parcels that have been received for more than 90 days
    Also deletes associated images from Cloudinary
    Returns: dict with cleanup statistics
    """
    try:
        # Calculate cutoff date (90 days ago)
        cutoff_date = datetime.datetime.utcnow() - datetime.timedelta(days=90)
        
        # Find old received parcels
        old_parcels = list(parcels_col.find({
            "status": "received",
            "received_at": {"$lt": cutoff_date}
        }))
        
        if not old_parcels:
            print("✅ No old parcels to cleanup")
            return {
                "parcels_deleted": 0,
                "images_deleted": 0
            }
        
        # Delete images from Cloudinary
        images_deleted = 0
        for parcel in old_parcels:
            # Delete parcel image
            if parcel.get('image_url'):
                if delete_image_by_url(parcel['image_url']):
                    images_deleted += 1
            
            # Delete user verification image if exists
            if parcel.get('user_verification_image'):
                if delete_image_by_url(parcel['user_verification_image']):
                    images_deleted += 1
        
        # Delete parcel records
        result = parcels_col.delete_many({
            "status": "received",
            "received_at": {"$lt": cutoff_date}
        })
        
        parcels_deleted = result.deleted_count
        
        print(f"✅ Cleanup: Deleted {parcels_deleted} parcels and {images_deleted} images")
        
        return {
            "parcels_deleted": parcels_deleted,
            "images_deleted": images_deleted
        }
        
    except Exception as e:
        print(f"❌ Cleanup Parcels Error: {e}")
        return {
            "parcels_deleted": 0,
            "images_deleted": 0,
            "error": str(e)
        }

def cleanup_old_chat_history():
    """
    Delete chat history older than 90 days
    Returns: int - Number of records deleted
    """
    try:
        cutoff_date = datetime.datetime.utcnow() - datetime.timedelta(days=90)
        
        result = chat_history_col.delete_many({
            "timestamp": {"$lt": cutoff_date}
        })
        
        deleted_count = result.deleted_count
        print(f"✅ Cleanup: Deleted {deleted_count} chat history records")
        
        return deleted_count
        
    except Exception as e:
        print(f"❌ Cleanup Chat History Error: {e}")
        return 0

def run_full_cleanup():
    """
    Run all cleanup tasks
    Returns: dict with all cleanup statistics
    """
    try:
        print("🧹 Starting full cleanup...")
        
        # Cleanup parcels
        parcel_stats = cleanup_old_parcels()
        
        # Cleanup chat history
        chat_deleted = cleanup_old_chat_history()
        
        total_stats = {
            **parcel_stats,
            "chat_history_deleted": chat_deleted,
            "timestamp": datetime.datetime.utcnow()
        }
        
        print(f"✅ Full cleanup completed: {total_stats}")
        
        return total_stats
        
    except Exception as e:
        print(f"❌ Full Cleanup Error: {e}")
        return {
            "error": str(e),
            "timestamp": datetime.datetime.utcnow()
        }
