import os, io, csv, sqlite3, secrets
from datetime import datetime
from functools import wraps
from flask import Flask, render_template, request, jsonify, session, send_from_directory, send_file, abort
from werkzeug.utils import secure_filename

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(APP_DIR, "civic_help.db")
UPLOAD_DIR = os.path.join(APP_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
ADMIN_PIN = os.environ.get("CIVIC_ADMIN_PIN", "2422")
ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}
MAX_CONTENT_LENGTH = 8 * 1024 * 1024

app = Flask(__name__)

# Keep the same secret key across server restarts
app.secret_key = os.environ.get(
    "FLASK_SECRET_KEY",
    "neighborhood-civic-help-local-demo-key-change-before-deployment"
)

app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = False
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with db() as con:
        con.execute("""CREATE TABLE IF NOT EXISTS reports(
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, phone TEXT NOT NULL,
            area TEXT NOT NULL, problem TEXT NOT NULL, photo TEXT, latitude REAL, longitude REAL,
            created_at TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'New')""")
        con.execute("""CREATE TABLE IF NOT EXISTS feedback(
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, phone TEXT NOT NULL,
            kind TEXT NOT NULL, message TEXT NOT NULL, created_at TEXT NOT NULL)""")

def login_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if not session.get("user"):
            return jsonify(error="Please log in first."), 401
        return fn(*args, **kwargs)
    return wrapped

def admin_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if not session.get("is_admin"):
            return jsonify(error="Admin PIN required."), 403
        return fn(*args, **kwargs)
    return wrapped

def clean(value, limit=2000):
    return (value or "").strip()[:limit]

@app.route("/")
def index():
    return render_template("index.html")

@app.get("/api/session")
def session_info():
    return jsonify(user=session.get("user"), is_admin=bool(session.get("is_admin")))

@app.post("/api/login")
def login():
    data = request.get_json(silent=True) or {}
    name, phone = clean(data.get("name"), 100), clean(data.get("phone"), 10)
    if not name or not phone.isdigit() or len(phone) != 10:
        return jsonify(error="Enter your name and a valid 10-digit mobile number."), 400
    session.clear()
    session["user"] = {"name": name, "phone": phone}
    return jsonify(ok=True, user=session["user"])

@app.post("/api/logout")
def logout():
    session.clear()
    return jsonify(ok=True)

@app.post("/api/admin/login")
def admin_login():
    data = request.get_json(silent=True) or {}
    if clean(data.get("pin"), 20) != ADMIN_PIN:
        return jsonify(error="Incorrect admin PIN."), 403
    session["is_admin"] = True
    session.pop("user", None)
    return jsonify(ok=True)

@app.post("/api/report")
@login_required
def create_report():
    name = session["user"]["name"]
    phone = session["user"]["phone"]
    area = clean(request.form.get("area"), 180)
    problem = clean(request.form.get("problem"), 3000)
    if not area or not problem:
        return jsonify(error="Please enter your area and describe the problem."), 400
    lat = request.form.get("latitude", "").strip()
    lng = request.form.get("longitude", "").strip()
    try:
        lat = float(lat) if lat else None
        lng = float(lng) if lng else None
        if lat is not None and not (-90 <= lat <= 90): raise ValueError()
        if lng is not None and not (-180 <= lng <= 180): raise ValueError()
    except ValueError:
        return jsonify(error="Invalid location coordinates."), 400
    photo_name = None
    file = request.files.get("photo")
    if file and file.filename:
        safe_name = secure_filename(file.filename)
        ext = safe_name.rsplit(".", 1)[-1].lower() if "." in safe_name else ""
        if ext not in ALLOWED_EXTENSIONS:
            return jsonify(error="Upload a JPG, PNG, or WEBP photo."), 400
        photo_name = f"{secrets.token_hex(12)}.{ext}"
        file.save(os.path.join(UPLOAD_DIR, photo_name))
    created = datetime.now().astimezone().isoformat(timespec="seconds")
    with db() as con:
        cur = con.execute("INSERT INTO reports(name,phone,area,problem,photo,latitude,longitude,created_at) VALUES(?,?,?,?,?,?,?,?)",
                          (name, phone, area, problem, photo_name, lat, lng, created))
        rid = cur.lastrowid
    return jsonify(ok=True, id=rid)

@app.post("/api/feedback")
@login_required
def create_feedback():
    data = request.get_json(silent=True) or {}
    kind, message = clean(data.get("kind"), 30), clean(data.get("message"), 3000)
    if kind not in ("good", "not_solved", "suggestion") or not message:
        return jsonify(error="Choose a feedback type and enter a message."), 400
    user = session["user"]
    with db() as con:
        cur = con.execute("INSERT INTO feedback(name,phone,kind,message,created_at) VALUES(?,?,?,?,?)",
                          (user["name"], user["phone"], kind, message, datetime.now().astimezone().isoformat(timespec="seconds")))
        fid = cur.lastrowid
    return jsonify(ok=True, id=fid)

@app.post("/api/admin/reports")
@admin_required
def get_reports():
    with db() as con:
        rows = con.execute("SELECT * FROM reports ORDER BY id DESC").fetchall()
    return jsonify(items=[dict(r) for r in rows])

@app.post("/api/admin/feedback")
@admin_required
def get_feedback():
    with db() as con:
        rows = con.execute("SELECT * FROM feedback ORDER BY id DESC").fetchall()
    return jsonify(items=[dict(r) for r in rows])

@app.post("/api/admin/delete")
@admin_required
def delete_item():
    data = request.get_json(silent=True) or {}
    table, item_id = data.get("table"), data.get("id")
    if table not in ("reports", "feedback"):
        return jsonify(error="Invalid item type."), 400
    try: item_id = int(item_id)
    except (TypeError, ValueError): return jsonify(error="Invalid item ID."), 400
    with db() as con:
        row = con.execute(f"SELECT photo FROM {table} WHERE id=?" if table == "reports" else f"SELECT id FROM {table} WHERE id=?", (item_id,)).fetchone()
        if not row: return jsonify(error="Item not found."), 404
        if table == "reports" and row["photo"]:
            try: os.remove(os.path.join(UPLOAD_DIR, row["photo"]))
            except FileNotFoundError: pass
        con.execute(f"DELETE FROM {table} WHERE id=?", (item_id,))
    return jsonify(ok=True)

@app.get("/uploads/<path:filename>")
def uploaded_photo(filename):
    # Photos are only served after admin authentication to avoid exposing residents' photos.
    if not session.get("is_admin"):
        abort(403)
    return send_from_directory(UPLOAD_DIR, filename)

@app.get("/api/admin/download.csv")
@admin_required
def download_csv():
    output = io.StringIO()
    writer = csv.writer(output)
    with db() as con:
        reports = con.execute("SELECT id,name,phone,area,problem,photo,latitude,longitude,created_at,status FROM reports ORDER BY id DESC").fetchall()
        feedback = con.execute("SELECT id,name,phone,kind,message,created_at FROM feedback ORDER BY id DESC").fetchall()
    writer.writerow(["REPORTS"])
    writer.writerow(["ID","Name","Contact Number","Area","Problem","Photo filename","Latitude","Longitude","Created at","Status"])
    writer.writerows([list(r) for r in reports])
    writer.writerow([])
    writer.writerow(["FEEDBACK"])
    writer.writerow(["ID","Name","Contact Number","Type","Message","Created at"])
    writer.writerows([list(r) for r in feedback])
    memory = io.BytesIO(output.getvalue().encode("utf-8-sig"))
    memory.seek(0)
    return send_file(memory, mimetype="text/csv; charset=utf-8", as_attachment=True, download_name="civic_reports_and_feedback.csv")

@app.get("/api/admin/download-photo/<int:report_id>")
@admin_required
def download_photo(report_id):
    with db() as con:
        row = con.execute("SELECT photo FROM reports WHERE id=?", (report_id,)).fetchone()
    if not row or not row["photo"]:
        abort(404)
    return send_from_directory(UPLOAD_DIR, row["photo"], as_attachment=True)

@app.errorhandler(413)
def too_large(_):
    return jsonify(error="Photo is too large. Maximum size is 8 MB."), 413

init_db()
if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
