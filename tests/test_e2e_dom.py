import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.database import init_db

init_db()
client = TestClient(app)


def test_dashboard_template_routes_and_dom_elements():
    # 1. Verify GET / serves updated index.html
    res_root = client.get("/")
    assert res_root.status_code == 200
    html_root = res_root.text

    assert '<link rel="stylesheet" href="/static/css/style.css?v=2.0">' in html_root
    assert '<script src="/static/js/app.js?v=2.0"></script>' in html_root
    assert '<a href="/api/export/csv" class="btn btn-outline">📥 Export CSV</a>' in html_root
    assert '<a href="/api/export/json" class="btn btn-outline">📥 Export JSON</a>' in html_root
    assert '<button id="btn-refresh-async" onclick="triggerAsyncValuation()" class="btn btn-primary">⚡ Refresh Valuations</button>' in html_root
    assert '<div id="valuationProgressContainer"' in html_root

    # 2. Verify GET /static/index.html serves matching updated index.html
    res_static = client.get("/static/index.html")
    assert res_static.status_code == 200
    html_static = res_static.text
    assert '<a href="/api/export/csv" class="btn btn-outline">📥 Export CSV</a>' in html_static
    assert '<button id="btn-refresh-async" onclick="triggerAsyncValuation()" class="btn btn-primary">⚡ Refresh Valuations</button>' in html_static


def test_static_app_js_dom_wiring():
    res = client.get("/static/js/app.js?v=2.0")
    assert res.status_code == 200
    js_text = res.text

    assert "badge badge-key" in js_text
    assert "renderItemCard" in js_text
    assert "triggerAsyncValuation" in js_text
    assert "pollValuationStatus" in js_text
    assert "/api/valuation/refresh-async" in js_text
    assert "/api/valuation/status" in js_text
