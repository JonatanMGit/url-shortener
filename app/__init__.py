from dotenv import load_dotenv
from flask import Flask, jsonify

from app.cache import init_cache
from app.database import init_db
from app.observability import configure_logging, register_request_logging
from app.routes import register_routes


def create_app():
    load_dotenv()

    app = Flask(__name__)

    configure_logging(app)
    register_request_logging(app)

    init_db(app)
    init_cache(app)

    from app import models  # noqa: F401 - registers models with Peewee
    from app.database import db

    try:
        db.create_tables([models.User, models.Url, models.Event])
    except Exception:
        app.logger.exception("db_table_init_failed", extra={"component": "database"})
        raise

    register_routes(app)

    @app.route("/health")
    def health():
        return jsonify(status="ok")

    return app
