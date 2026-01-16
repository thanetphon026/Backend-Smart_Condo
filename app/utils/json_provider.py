import json
import datetime
from bson import ObjectId
from flask.json.provider import DefaultJSONProvider

class MongoJSONProvider(DefaultJSONProvider):
    def default(self, obj):
        if isinstance(obj, datetime.datetime):
            # If naive (no timezone), assume UTC and add 'Z'
            if obj.tzinfo is None:
                return obj.isoformat() + "Z"
            return obj.isoformat()
        if isinstance(obj, ObjectId):
            return str(obj)
        return super().default(obj)
