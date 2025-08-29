from flask import Flask
from flask_cors import CORS
from dotenv import load_dotenv
from infrastructure.logger import setup_logger
from routes.web import web_bp
from routes.corpus import corpus_bp
import routes.database as db


setup_logger()

def create_app():
    app = Flask(__name__)
    CORS(app)
    load_dotenv()
    app.config.from_object("config.Config")

    app.register_blueprint(web_bp)
    app.register_blueprint(corpus_bp)

    @app.teardown_appcontext
    def _close_db(exception):
        db.close_db()
    
    with app.app_context():
        db.init_db()

    return app

if __name__ == "__main__":
    app = create_app()
    app.run(host="0.0.0.0", port=8080)