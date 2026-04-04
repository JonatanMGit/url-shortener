from dotenv import load_dotenv
from flask import Flask, jsonify

from app.cache import init_cache
from app.database import init_db
from app.routes import register_routes


def create_app():
    load_dotenv()

    app = Flask(__name__)

    init_db(app)
    init_cache(app)

    from app import models  # noqa: F401 - registers models with Peewee
    from app.database import db

    db.create_tables([models.User, models.Url, models.Event])

    register_routes(app)

    @app.route("/health")
    def health():
        return jsonify(status="ok")

    return app
