from peewee import CharField, DateTimeField
import datetime
from app.database import BaseModel

class User(BaseModel):
    username = CharField(unique=True)
    email = CharField(unique=True)
    created_at = DateTimeField(default=datetime.datetime.now)

    class Meta:
        table_name = "users"