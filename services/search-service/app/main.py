"""OtterWorks Search Service - Full-text search via OpenSearch."""

import os

import structlog
from flask import Flask
from flask_cors import CORS

from app.api.health import health_bp
from app.api.search import search_bp

logger = structlog.get_logger()


def create_app() -> Flask:
    app = Flask(__name__)

    CORS(app, origins=["http://localhost:3000", "http://localhost:4200"])

    app.config["OPENSEARCH_URL"] = os.getenv("OPENSEARCH_URL", "http://localhost:9200")
    app.config["OPENSEARCH_INDEX"] = os.getenv("OPENSEARCH_INDEX", "otterworks-documents")

    app.register_blueprint(health_bp)
    app.register_blueprint(search_bp, url_prefix="/api/v1/search")

    logger.info("search_service_created")
    return app


if __name__ == "__main__":
    app = create_app()
    app.run(host="0.0.0.0", port=8087, debug=True)
