from flask import Blueprint, jsonify
from ..utils.helpers import token_required
from ..utils.db import users_col

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
