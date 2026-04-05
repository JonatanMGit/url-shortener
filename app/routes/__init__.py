def register_routes(app):
    from app.routes.users import users_bp
    from app.routes.urls import urls_bp
    from app.routes.events import events_bp
    from app.routes.errors import errors_bp
    from app.routes.resolve import resolve_bp
    from app.routes.observability import observability_bp
    
    app.register_blueprint(users_bp)
    app.register_blueprint(urls_bp)
    app.register_blueprint(events_bp)
    app.register_blueprint(errors_bp)
    app.register_blueprint(resolve_bp)
    app.register_blueprint(observability_bp)
