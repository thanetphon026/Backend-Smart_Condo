import json
import datetime
from bson import ObjectId
from flask.json.provider import DefaultJSONProvider

class MongoJSONProvider(DefaultJSONProvider):
    def default(self, obj):
        if isinstance(obj, datetime.datetime):
            return obj.isoformat()
        if isinstance(obj, ObjectId):
            return str(obj)
        return super().default(obj)
