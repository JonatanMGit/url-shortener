from peewee import CharField, DateTimeField, ForeignKeyField, TextField
import datetime
from app.database import BaseModel
from app.models.user import User
from app.models.url import Url

class Event(BaseModel):
    url_id = ForeignKeyField(Url, backref='events', null=True)
    user_id = ForeignKeyField(User, backref='events', null=True)
    event_type = CharField()
    timestamp = DateTimeField(default=datetime.datetime.now)
    details = TextField(null=True) 

    class Meta:
        table_name = "events"