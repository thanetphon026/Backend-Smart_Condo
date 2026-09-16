import datetime
import pytz
from flask import request, jsonify
from functools import wraps
from ..config import Config

def get_bkk_time():
    """Returns current time in Bangkok timezone."""
    tz = pytz.timezone('Asia/Bangkok')
    return datetime.datetime.now(tz)

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        # Check Authorization header
        if 'Authorization' in request.headers:
            token = request.headers['Authorization']
            if token.startswith('Bearer '):
                token = token.split(' ')[1]
        
        # Check Custom header
        if not token and 'X-API-Token' in request.headers:
            token = request.headers['X-API-Token']
            
        # Check Query String (for Export URLs)
        if not token:
            token = request.args.get('token')

        if not token or token != Config.API_TOKEN:
            return jsonify({
                "status": "error", 
                "message": "Unauthorized: Invalid or missing API Token"
            }), 401
            
        return f(*args, **kwargs)
    return decorated

def get_operating_hours():
    """Fetch current operating hours settings from MongoDB or return default 08:30 - 17:30."""
    try:
        from .db import settings_col
        doc = settings_col.find_one({"_id": "operating_hours"})
        if doc:
            return {
                "registration_start": doc.get("registration_start", "08:30"),
                "registration_end": doc.get("registration_end", "17:30")
            }
    except Exception as e:
        print(f"⚠️ Error fetching operating hours: {e}")
    return {
        "registration_start": "08:30",
        "registration_end": "17:30"
    }

def is_registration_open(now=None):
    """
    Check if current Bangkok time is within registration window.
    Returns: (bool is_open, dict operating_hours)
    """
    if now is None:
        now = get_bkk_time()
    op_hours = get_operating_hours()
    try:
        start_h, start_m = map(int, op_hours["registration_start"].split(':'))
        end_h, end_m = map(int, op_hours["registration_end"].split(':'))
        
        current_minutes = now.hour * 60 + now.minute
        start_minutes = start_h * 60 + start_m
        end_minutes = end_h * 60 + end_m
        
        is_open = start_minutes <= current_minutes <= end_minutes
        return is_open, op_hours
    except Exception as e:
        print(f"⚠️ Error calculating registration hours: {e}")
        current_minutes = now.hour * 60 + now.minute
        return (8 * 60 + 30) <= current_minutes <= (17 * 60 + 30), op_hours

def is_self_pickup_open(now=None):
    """
    Check if self-pickup scan is open (when office registration is closed).
    Returns: (bool is_pickup_open, dict operating_hours)
    """
    if now is None:
        now = get_bkk_time()
    is_reg_open, op_hours = is_registration_open(now)
    # Self-pickup is open outside office hours (when office registration is closed)
    is_pickup_open = not is_reg_open
    return is_pickup_open, op_hours

