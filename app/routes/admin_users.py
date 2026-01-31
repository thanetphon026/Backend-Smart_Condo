from flask import Blueprint, jsonify, request
from ..utils.helpers import token_required
from ..utils.db import users_col
from ..utils.lookup import find_user_by_parcel_info, get_user_info_with_parcel_count

users_bp = Blueprint('users', __name__)

@users_bp.route('/api/admin/users', methods=['GET'])
@token_required
def get_users():
    users = list(users_col.find().limit(100))
    for u in users:
        u['_id'] = str(u['_id'])
        # Construct name for frontend
        first = u.get('first_name', '')
        last = u.get('last_name', '')
        if first or last:
            u['name'] = f"{first} {last}".strip()
        else:
            u['name'] = u.get('display_name', '-')
            
        if not u.get('display_name'):
            u['display_name'] = '-'
            
    return jsonify({"status": "success", "data": users})

@users_bp.route('/api/admin/users/search', methods=['POST'])
@token_required
def search_user():
    """
    Real-time user search for validation during parcel import.
    Accepts room_number and/or recipient_name and returns matching user info.
    """
    try:
        data = request.json
        room_number = data.get('room_number', '').strip()
        recipient_name = data.get('recipient_name', '').strip()
        
        # Return empty result if both fields are empty
        if not room_number and not recipient_name:
            return jsonify({
                "status": "success",
                "data": {
                    "exists": False,
                    "room_number": "",
                    "first_name": "",
                    "last_name": "",
                    "display_name": "",
                    "parcel_count": 0
                }
            })
        
        # Find user using lookup utility
        user = find_user_by_parcel_info(room_number, recipient_name)
        
        # Get formatted user info with parcel count
        user_info = get_user_info_with_parcel_count(user)
        
        return jsonify({
            "status": "success",
            "data": user_info
        })
        
    except Exception as e:
        print(f"User search error: {e}")
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500
