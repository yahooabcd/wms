from flask import Flask, render_template

import db
from auth import bp as auth_bp, login_manager
from config import Config
from routes import register_blueprints


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)
    login_manager.init_app(app)

    app.register_blueprint(auth_bp)
    register_blueprints(app)

    @app.errorhandler(403)
    def forbidden(e):
        return render_template('error.html', code=403,
                               message='没有权限访问该页面，请联系管理员'), 403

    @app.errorhandler(404)
    def not_found(e):
        return render_template('error.html', code=404, message='页面不存在'), 404

    return app


if __name__ == '__main__':
    app = create_app()
    app.run(host='127.0.0.1', port=5000)
