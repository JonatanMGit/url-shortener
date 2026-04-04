from peewee import CharField, BooleanField, DateTimeField, ForeignKeyField, TextField
import datetime
from app.database import BaseModel
from app.models.user import User

class Url(BaseModel):
    user_id = ForeignKeyField(User, backref='urls')
    short_code = CharField(unique=True)
    original_url = TextField()
    title = CharField()
    is_active = BooleanField(default=True)
    created_at = DateTimeField(default=datetime.datetime.now)
    updated_at = DateTimeField(default=datetime.datetime.now)

    def save(self, *args, **kwargs):
        self.updated_at = datetime.datetime.now()
        return super().save(*args, **kwargs)

    class Meta:
        table_name = "urls"