"""Search API endpoints."""

import structlog
from flask import Blueprint, current_app, jsonify, request

logger = structlog.get_logger()

search_bp = Blueprint("search", __name__)


@search_bp.route("/", methods=["GET"])
def search_documents():
    """Full-text search across documents and files."""
    query = request.args.get("q", "")
    try:
        page = max(1, int(request.args.get("page", 1)))
        page_size = max(1, min(100, int(request.args.get("page_size", 20))))
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid page or page_size parameter"}), 400
    doc_type = request.args.get("type")  # document, file, or None for all
    owner_id = request.args.get("owner_id")

    if not query:
        return jsonify({"error": "Query parameter 'q' is required"}), 400

    service = current_app.opensearch_service
    results = service.search(
        query=query,
        doc_type=doc_type,
        owner_id=owner_id,
        page=page,
        page_size=page_size,
    )

    logger.info("search_executed", query=query, result_count=results["total"])
    return jsonify(results)


@search_bp.route("/suggest", methods=["GET"])
def suggest():
    """Autocomplete suggestions."""
    prefix = request.args.get("q", "")
    if not prefix or len(prefix) < 2:
        return jsonify({"suggestions": []})

    service = current_app.opensearch_service
    suggestions = service.suggest(prefix)
    return jsonify({"suggestions": suggestions})


@search_bp.route("/index", methods=["POST"])
def index_document():
    """Index a document for search (called by other services via events)."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "Request body is required"}), 400

    service = current_app.opensearch_service
    service.index_document(data)

    logger.info("document_indexed", document_id=data.get("id"))
    return jsonify({"status": "indexed"}), 201


@search_bp.route("/index/<document_id>", methods=["DELETE"])
def remove_document(document_id: str):
    """Remove a document from the search index."""
    service = current_app.opensearch_service
    service.delete_document(document_id)

    logger.info("document_removed_from_index", document_id=document_id)
    return "", 204
