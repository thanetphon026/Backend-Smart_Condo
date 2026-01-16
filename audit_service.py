"""
Audit Service Module - Smart Condo Backend
Handles activity logging for both admins and users
"""
import datetime
from database import audit_logs_col
import csv
import io

def log_admin_action(action, performed_by, target=None, details=None):
    """
    Log admin actions to audit trail
    Args:
        action: Action name (e.g., "Scan Parcel", "Confirm Receipt")
        performed_by: Admin name or email
        target: Target of action (e.g., room number, parcel ID)
        details: Additional details
    Returns:
        bool: Success status
    """
    try:
        log_entry = {
            "actor_type": "admin",
            "action": action,
            "performed_by": performed_by,
            "target": target,
            "timestamp": datetime.datetime.utcnow(),
            "details": details or ""
        }
        audit_logs_col.insert_one(log_entry)
        print(f"📝 Admin Log: {action} by {performed_by} → {target}")
        return True
    except Exception as e:
        print(f"❌ Admin Audit Log Error: {e}")
        return False

def log_user_action(action, line_user_id, room_number, target=None, result="success", details=None):
    """
    Log user actions to audit trail
    Args:
        action: Action name (e.g., "After-hours registration", "Self-pickup scan")
        line_user_id: LINE User ID
        room_number: User's room number
        target: Target of action (e.g., parcel ID)
        result: "success" or "failure"
        details: Additional details (e.g., "Correct room" or "Wrong room detected")
    Returns:
        bool: Success status
    """
    try:
        log_entry = {
            "actor_type": "user",
            "action": action,
            "performed_by": f"Room {room_number}",
            "line_user_id": line_user_id,
            "room_number": room_number,
            "target": target,
            "result": result,
            "timestamp": datetime.datetime.utcnow(),
            "details": details or ""
        }
        audit_logs_col.insert_one(log_entry)
        print(f"📝 User Log: {action} by Room {room_number} → {result}")
        return True
    except Exception as e:
        print(f"❌ User Audit Log Error: {e}")
        return False

def get_admin_logs(limit=20):
    """
    Get latest admin action logs
    Args:
        limit: Number of records to return
    Returns:
        list: Log entries
    """
    try:
        logs = list(audit_logs_col.find(
            {"actor_type": "admin"}
        ).sort("timestamp", -1).limit(limit))
        
        # Convert ObjectId to string for JSON serialization
        for log in logs:
            log['_id'] = str(log['_id'])
        
        return logs
    except Exception as e:
        print(f"❌ Get Admin Logs Error: {e}")
        return []

def get_user_logs(limit=20):
    """
    Get latest user action logs
    Args:
        limit: Number of records to return
    Returns:
        list: Log entries
    """
    try:
        logs = list(audit_logs_col.find(
            {"actor_type": "user"}
        ).sort("timestamp", -1).limit(limit))
        
        # Convert ObjectId to string for JSON serialization
        for log in logs:
            log['_id'] = str(log['_id'])
        
        return logs
    except Exception as e:
        print(f"❌ Get User Logs Error: {e}")
        return []

def export_admin_logs_csv():
    """
    Export all admin logs to CSV format
    Returns:
        str: CSV content
    """
    try:
        logs = list(audit_logs_col.find(
            {"actor_type": "admin"}
        ).sort("timestamp", -1))
        
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Header
        writer.writerow([
            "วันที่-เวลา", "ผู้ดำเนินการ", "กิจกรรม", "เป้าหมาย", "รายละเอียด"
        ])
        
        # Data rows
        for log in logs:
            writer.writerow([
                log.get('timestamp', '').strftime('%Y-%m-%d %H:%M:%S') if log.get('timestamp') else '-',
                log.get('performed_by', '-'),
                log.get('action', '-'),
                log.get('target', '-'),
                log.get('details', '-')
            ])
        
        return output.getvalue()
    except Exception as e:
        print(f"❌ Export Admin Logs CSV Error: {e}")
        return ""

def export_user_logs_csv():
    """
    Export all user logs to CSV format
    Returns:
        str: CSV content
    """
    try:
        logs = list(audit_logs_col.find(
            {"actor_type": "user"}
        ).sort("timestamp", -1))
        
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Header
        writer.writerow([
            "วันที่-เวลา", "ห้อง", "กิจกรรม", "เป้าหมาย", "ผลลัพธ์", "รายละเอียด"
        ])
        
        # Data rows
        for log in logs:
            writer.writerow([
                log.get('timestamp', '').strftime('%Y-%m-%d %H:%M:%S') if log.get('timestamp') else '-',
                log.get('room_number', '-'),
                log.get('action', '-'),
                log.get('target', '-'),
                log.get('result', '-'),
                log.get('details', '-')
            ])
        
        return output.getvalue()
    except Exception as e:
        print(f"❌ Export User Logs CSV Error: {e}")
        return ""
