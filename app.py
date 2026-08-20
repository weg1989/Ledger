import dataclasses
import json
import os
import queue
import sqlite3
import threading
import time
import uuid
from datetime import datetime, timezone

from flask import Flask, request, jsonify, Response, send_from_directory, g

import pipeline as P
from traced_runner import run_traced

os.environ["GROQ_API_KEY"] = "Add ypur key here"
# Add the path to your Poppler bin folder (where pdfinfo.exe and pdftoppm.exe are located)
POPPLER_BIN = r"C:\poppler\Library\bin"  # Update this to your actual path

if POPPLER_BIN not in os.environ["PATH"]:
    os.environ["PATH"] += os.pathsep + POPPLER_BIN

def json_default(obj):
    """Some pipeline objects (e.g. LineItem) are dataclasses nested inside
    plain dicts returned by to_dict(), so json.dumps needs a hook to convert
    them rather than erroring on them."""
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return dataclasses.asdict(obj)
    return str(obj)


def dumps(obj):
    return json.dumps(obj, default=json_default)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SAMPLES_DIR = os.path.join(BASE_DIR, "samples")
UPLOAD_DIR = os.path.join(BASE_DIR, "data", "uploads")
DB_PATH = os.path.join(BASE_DIR, "data", "runs.db")
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

app = Flask(__name__, static_folder="static", static_url_path="")

# ---------------------------------------------------------------------------
# Persistent-ish in-memory "procurement system" state (PO ledger + duplicate
# history + open vendor-correspondence threads). Seeded with the same demo
# data used in the notebook so every sample edge case works out of the box.
# Guarded by a lock since Flask's dev server can be multi-threaded.
# ---------------------------------------------------------------------------
STATE_LOCK = threading.Lock()


def _seed_state():
    store = P.POStore()
    store.add_po("PO-88291", "Northwind Office Supplies Ltd.", 684.72)
    store.add_po("PO-77000", "Steelwork Fabrication Inc.", 15000.00)
    store.record_invoice("INV-10499", "Steelwork Fabrication Inc.", 5313.60, po_number="PO-77000")
    store.add_po("PO-55110", "Meridian Consulting Group", 5000.00)
    store.add_po("PO-90210", "BrightPath Logistics", 2450.00)
    corr = P.VendorCorrespondenceStore()
    return store, corr


PO_STORE, CORR_STORE = _seed_state()

SAMPLE_META = [
    {"file": "clean_invoice.pdf", "label": "Happy path", "scenario": "happy_path",
     "description": "Clean digital PDF, exact PO match, amounts tie out. Stops at Tier 1 — no OCR/LLM cost."},
    {"file": "scanned_invoice.png", "label": "Edge case — scanned image", "scenario": "scanned",
     "description": "Same invoice flattened to an image. No text layer, forces Tier 2 (OCR + LLM)."},
    {"file": "split_po_invoice.pdf", "label": "Edge case — split PO", "scenario": "split_po",
     "description": "Second installment against a PO already partially billed. Checked against remaining balance."},
    {"file": "duplicate_invoice.pdf", "label": "Edge case — duplicate invoice", "scenario": "duplicate",
     "description": "Same invoice submitted twice. Second submission should be caught and held for human confirmation."},
    {"file": "missing_fields_invoice.pdf", "label": "Edge case — missing fields", "scenario": "missing_fields",
     "description": "No invoice number, no total. Every tier is tried before honestly holding for review."},
    {"file": "embedded_tax_invoice.pdf", "label": "Edge case — embedded tax", "scenario": "embedded_tax",
     "description": "Tax is stated as already included in the total, not additive. Tax-mode-aware arithmetic check."},
    {"file": "no_po_invoice.pdf", "label": "Edge case — vendor correspondence loop", "scenario": "vendor_corr",
     "description": "Every field present except a PO number. Routes to an auto-drafted vendor email instead of guessing."},
]

RUN_QUEUES = {}   # run_id -> queue.Queue of SSE events, cleared once consumed


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS runs (
            id TEXT PRIMARY KEY,
            parent_run_id TEXT,
            created_at TEXT,
            source_name TEXT,
            scenario_label TEXT,
            decision TEXT,
            requires_review INTEGER,
            action_required TEXT,
            tier_used TEXT,
            confidence REAL,
            match_status TEXT,
            duration_ms INTEGER,
            result_json TEXT
        )
    """)
    conn.commit()
    conn.close()


init_db()


def _save_run(run_id, parent_run_id, source_name, scenario_label, result, duration_ms):
    conn = db()
    conn.execute(
        "INSERT INTO runs (id, parent_run_id, created_at, source_name, scenario_label, decision, "
        "requires_review, action_required, tier_used, confidence, match_status, duration_ms, result_json) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            run_id, parent_run_id, datetime.now(timezone.utc).isoformat(), source_name, scenario_label,
            result["decision"]["decision"], int(result["decision"]["requires_human_review"]),
            result["decision"].get("action_required"), result["extraction"]["extraction_tier"],
            result["validation"]["confidence_score"], result["match"]["match_status"],
            duration_ms, dumps(result),
        ),
    )
    conn.commit()
    conn.close()


def _emit_factory(run_id):
    q = RUN_QUEUES[run_id]

    def emit(event):
        q.put({"type": "stage", **event})

    return emit


def _background_run(run_id, file_path, source_name, scenario_label, corrected_fields=None,
                     reply_body=None, reprocess_of=None, parent_run_id=None):
    emit = _emit_factory(run_id)
    q = RUN_QUEUES[run_id]
    started = time.time()
    try:
        with STATE_LOCK:
            result = run_traced(
                file_path, PO_STORE, CORR_STORE, emit,
                corrected_fields=corrected_fields, reply_body=reply_body, reprocess_of=reprocess_of,
            )
        duration_ms = int((time.time() - started) * 1000)
        _save_run(run_id, parent_run_id, source_name, scenario_label, result, duration_ms)
        q.put({"type": "result", "run_id": run_id, "payload": result})
    except Exception as exc:  # surface pipeline errors to the live view instead of hanging it
        q.put({"type": "error", "message": str(exc)})
    finally:
        q.put({"type": "end"})


@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.route("/samples/<path:filename>")
def samples(filename):
    return send_from_directory(SAMPLES_DIR, filename)


@app.route("/api/apikey-status")
def api_apikey_status():
    return jsonify({"live": bool(os.environ.get("GROQ_API_KEY"))})


@app.route("/api/samples")
def api_samples():
    return jsonify(SAMPLE_META)


@app.route("/api/state")
def api_state():
    """Current PO ledger + open correspondence threads, so the UI can show
    'the system' the pipeline is reasoning against, not just raw file output."""
    with STATE_LOCK:
        pos = list(PO_STORE.pos.values())
        threads = [t.to_dict() for t in CORR_STORE.threads.values()]
    return jsonify({"purchase_orders": pos, "correspondence_threads": threads})


@app.route("/api/state/reset", methods=["POST"])
def api_state_reset():
    global PO_STORE, CORR_STORE
    with STATE_LOCK:
        PO_STORE, CORR_STORE = _seed_state()
    return jsonify({"ok": True})


@app.route("/api/run", methods=["POST"])
def api_run():
    run_id = str(uuid.uuid4())
    RUN_QUEUES[run_id] = queue.Queue()

    sample = request.form.get("sample")
    if sample:
        meta = next((s for s in SAMPLE_META if s["file"] == sample), None)
        if not meta:
            return jsonify({"error": "unknown sample"}), 400
        file_path = os.path.join(SAMPLES_DIR, sample)
        source_name = sample
        scenario_label = meta["label"]
    else:
        f = request.files.get("file")
        if not f or not f.filename:
            return jsonify({"error": "no file provided"}), 400
        ext = os.path.splitext(f.filename)[1].lower()
        safe_name = f"{run_id}{ext}"
        file_path = os.path.join(UPLOAD_DIR, safe_name)
        f.save(file_path)
        source_name = f.filename
        scenario_label = "Custom upload"

    threading.Thread(
        target=_background_run,
        args=(run_id, file_path, source_name, scenario_label),
        daemon=True,
    ).start()
    return jsonify({"run_id": run_id})


@app.route("/api/vendor-reply", methods=["POST"])
def api_vendor_reply():
    payload = request.get_json(force=True)
    source_file = payload["source_file"]
    corrected_fields = payload.get("corrected_fields", {})
    reply_body = payload.get("reply_body", "")
    parent_run_id = payload.get("parent_run_id")

    run_id = str(uuid.uuid4())
    RUN_QUEUES[run_id] = queue.Queue()

    threading.Thread(
        target=_background_run,
        args=(run_id, source_file, os.path.basename(source_file), "Vendor reply — reprocessed"),
        kwargs=dict(corrected_fields=corrected_fields, reply_body=reply_body,
                    reprocess_of=source_file, parent_run_id=parent_run_id),
        daemon=True,
    ).start()
    return jsonify({"run_id": run_id})


@app.route("/api/stream/<run_id>")
def api_stream(run_id):
    q = RUN_QUEUES.get(run_id)
    if q is None:
        return jsonify({"error": "unknown run_id"}), 404

    def gen():
        while True:
            event = q.get()
            yield f"data: {dumps(event)}\n\n"
            if event.get("type") == "end":
                RUN_QUEUES.pop(run_id, None)
                break

    return Response(gen(), mimetype="text/event-stream",
                     headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.route("/api/runs")
def api_runs():
    conn = db()
    rows = conn.execute("SELECT id, parent_run_id, created_at, source_name, scenario_label, decision, "
                         "requires_review, action_required, tier_used, confidence, match_status, duration_ms "
                         "FROM runs ORDER BY created_at DESC LIMIT 200").fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/runs/<run_id>")
def api_run_detail(run_id):
    conn = db()
    row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
    conn.close()
    if not row:
        return jsonify({"error": "not found"}), 404
    d = dict(row)
    d["result"] = json.loads(d.pop("result_json"))
    return jsonify(d)


@app.route("/api/stats")
def api_stats():
    conn = db()
    total = conn.execute("SELECT COUNT(*) c FROM runs").fetchone()["c"]
    by_decision = conn.execute("SELECT decision, COUNT(*) c FROM runs GROUP BY decision").fetchall()
    by_tier = conn.execute("SELECT tier_used, COUNT(*) c FROM runs GROUP BY tier_used").fetchall()
    avg_conf = conn.execute("SELECT AVG(confidence) a FROM runs").fetchone()["a"]
    avg_dur = conn.execute("SELECT AVG(duration_ms) a FROM runs").fetchone()["a"]
    conn.close()
    return jsonify({
        "total": total,
        "by_decision": {r["decision"]: r["c"] for r in by_decision},
        "by_tier": {r["tier_used"]: r["c"] for r in by_tier},
        "avg_confidence": avg_conf,
        "avg_duration_ms": avg_dur,
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5050))
    print(f"\nSmart Invoice Processing — running at http://127.0.0.1:{port}\n")
    if not os.environ.get("GROQ_API_KEY"):
        print("NOTE: GROQ_API_KEY not set — Tier 2/3 will use offline deterministic fallbacks.\n")
    app.run(host="0.0.0.0", port=port, threaded=True, debug=False)
