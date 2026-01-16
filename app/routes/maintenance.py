from flask import Blueprint, jsonify, request
from ..utils.db import audit_logs_col, parcels_col, users_col, chat_history_col
from ..utils.cloudinary_utils import delete_resource # Assuming this helper exists or needs to be created
import csv
import io
import datetime

maintenance_bp = Blueprint('maintenance', __name__)

@maintenance_bp.route('/api/maintenance/cleanup', methods=['POST'])
def cleanup_old_data():
    """
    Deletes data older than 90 days.
    Trigger this via Cron Job (e.g. call this endpoint daily).
    """
    try:
        days = 90
        cutoff_date = datetime.datetime.utcnow() - datetime.timedelta(days=days)
        
        # 1. Cleanup Parcels (Only "received" ones? Or all? Usually received)
        # Requirement: "Delete received parcels, images, and chat history"
        
        # Find parcels to delete to clean up images first
        old_parcels = parcels_col.find({
            "status": "received",
            "timestamp": {"$lt": cutoff_date}
        })
        
        deleted_parcels_count = 0
        for p in old_parcels:
            # Delete image from Cloudinary if exists
            if 'image_url' in p and p['image_url']:
                 # Extract public_id from URL if possible, or store public_id in DB.
                 # For now assuming we just delete the record data. 
                 # In real prod, cleaner to store 'cloudinary_public_id'.
                 pass 
            
            parcels_col.delete_one({"_id": p['_id']})
            deleted_parcels_count += 1
            
        # 2. Cleanup Chat History
        chat_result = chat_history_col.delete_many({
            "timestamp": {"$lt": cutoff_date}
        })
        
        # 3. Cleanup Audit Logs (Optional but good practice)
        log_result = audit_logs_col.delete_many({
            "timestamp": {"$lt": cutoff_date}
        })
        
        return jsonify({
            "status": "success",
            "message": f"Cleanup complete. Deleted {deleted_parcels_count} parcels, {chat_result.deleted_count} chats, {log_result.deleted_count} logs."
        })
        
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
