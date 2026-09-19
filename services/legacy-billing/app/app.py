from flask import Flask, jsonify, redirect, render_template, request, url_for

from backends import get_backend
from facade import facade, internal
from reports import reports

app = Flask(__name__)
app.register_blueprint(reports)
app.register_blueprint(facade)
app.register_blueprint(internal)


@app.get("/health")
def health():
    backend = get_backend()
    try:
        backend.health()
    except Exception:
        return jsonify(status="DOWN", service="legacy-billing", backend=backend.NAME), 503
    return jsonify(status="UP", service="legacy-billing", backend=backend.NAME)


@app.get("/")
def index():
    return render_template("index.html", plans=get_backend().list_plans())


@app.get("/plans")
def plans():
    return jsonify(get_backend().list_plans())


@app.get("/plans/<tenant_id>/entitlement")
def entitlement(tenant_id):
    return jsonify(get_backend().entitlement(tenant_id, request.args.get("on", "2026-02-28")))


@app.post("/plans/<tenant_id>/change")
def change_plan(tenant_id):
    get_backend().change_plan(tenant_id, request.form["plan_id"], request.form["effective_on"])
    return redirect(url_for("entitlement", tenant_id=tenant_id, on=request.form["effective_on"]))


@app.post("/api/rating/preview")
def rating_preview():
    payload = request.get_json(force=True)
    return jsonify(get_backend().usage_rating(payload["tenant_id"], payload["period_start"], payload["period_end"]))


@app.post("/api/rating/finalize")
def rating_finalize():
    payload = request.get_json(force=True)
    get_backend().finalize_rating(payload["tenant_id"], payload["period_start"], payload["period_end"])
    return jsonify(status="finalized")


@app.get("/api/invoices/<tenant_id>/preview")
def invoice_preview(tenant_id):
    return jsonify(get_backend().invoice_preview(
        tenant_id,
        request.args.get("period_start", "2026-02-01"),
        request.args.get("period_end", "2026-02-28"),
    ))


@app.post("/api/invoices/<tenant_id>/issue")
def invoice_issue(tenant_id):
    get_backend().issue_invoice(
        tenant_id,
        request.form["period_start"],
        request.form["period_end"],
    )
    return jsonify(status="issued")


@app.get("/api/invoices/<invoice_id>/lines")
def invoice_lines(invoice_id):
    return jsonify(get_backend().invoice_lines(invoice_id))


@app.get("/api/dunning/overdue")
def overdue():
    return jsonify(get_backend().overdue(request.args.get("as_of", "2026-02-28")))


@app.post("/api/dunning/schedule")
def schedule_dunning():
    get_backend().schedule_dunning(request.form["as_of"])
    return jsonify(status="scheduled")


@app.post("/api/dunning/suspend")
def suspend_overdue():
    get_backend().suspend_overdue(request.form["as_of"])
    return jsonify(status="suspended")
