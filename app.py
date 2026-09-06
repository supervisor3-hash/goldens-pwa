
import os
import re
import json
import shutil
from pathlib import Path
from datetime import datetime, date, time, timedelta
from functools import wraps
from urllib.parse import quote
from uuid import uuid4

from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, abort, send_from_directory, make_response
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import UniqueConstraint, inspect, text
from werkzeug.utils import secure_filename
from itsdangerous import URLSafeSerializer, BadSignature

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "goldens-local-dev")
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "change-this-secret-before-production")

database_url = os.getenv("DATABASE_URL", "").strip()

# Render/PostgreSQL: force psycopg v3.
if database_url.startswith("postgres://"):
    database_url = "postgresql+psycopg://" + database_url[len("postgres://"):]
elif database_url.startswith("postgresql://"):
    database_url = "postgresql+psycopg://" + database_url[len("postgresql://"):]

if not database_url:
    database_url = "sqlite:///" + str(Path(app.instance_path) / "goldens.db")

app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

if database_url.startswith("postgresql+psycopg://"):
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "pool_pre_ping": True,
        "pool_recycle": 240,
        "pool_size": 1,
        "max_overflow": 1,
        "pool_timeout": 30,
    }
db = SQLAlchemy(app)

UPLOAD_DIR = Path(app.root_path) / "static" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# The original PWA assets are at the repository root. Copy them into Flask's
# static folder on startup so Render can serve the manifest, service worker
# and app icons even when GitHub uploads omit the static directory.
LEGACY_STATIC_FILES = [
    "goldens-192.png",
    "goldens-512.png",
    "apple-touch-icon.png",
    "manifest.webmanifest",
    "service-worker.js",
]
for _filename in LEGACY_STATIC_FILES:
    _src = Path(app.root_path) / _filename
    _dst = Path(app.static_folder) / _filename
    try:
        if _src.exists() and not _dst.exists():
            _dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(_src, _dst)
    except Exception:
        pass
ALLOWED_IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024

OPEN_HOUR = int(os.getenv("OPEN_HOUR", "10"))
CLOSE_HOUR = int(os.getenv("CLOSE_HOUR", "19"))
SLOT_MINUTES = int(os.getenv("SLOT_MINUTES", "30"))
ADMIN_USER = os.getenv("ADMIN_USER", "admin")
ADMIN_PIN = os.getenv("ADMIN_PIN", "2026")

def _load_local_config():
    try:
        cfg_path = Path(__file__).with_name("goldens_config.json")
        if cfg_path.exists():
            return json.loads(cfg_path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}

_LOCAL_CONFIG = _load_local_config()
_whatsapp_env = os.getenv("GOLDENS_WHATSAPP_NUMBER", "").strip()
_whatsapp_raw = _whatsapp_env or _LOCAL_CONFIG.get("whatsapp_number", "")
GOLDENS_WHATSAPP_NUMBER = re.sub(r"\D", "", _whatsapp_raw)



@app.route("/whatsapp")
def goldens_whatsapp():
    number = GOLDENS_WHATSAPP_NUMBER or "50660158371"
    message = "Hola Goldens, quiero información y agendar una cita."
    return redirect(f"https://wa.me/{number}?text={quote(message)}")

@app.route("/instalar")
def instalar_pwa():
    return render_template("install_pwa.html")

@app.route("/pwa-check")
def pwa_check():
    return jsonify({
        "app": "GOLDENS",
        "pwa": True,
        "manifest": "/static/manifest.webmanifest",
        "service_worker": "/service-worker.js"
    })

@app.route("/service-worker.js")
def service_worker():
    response = make_response(
        send_from_directory(app.static_folder, "service-worker.js")
    )
    response.headers["Service-Worker-Allowed"] = "/"
    response.headers["Cache-Control"] = "no-cache"
    response.headers["Content-Type"] = "application/javascript; charset=utf-8"
    return response

class Barber(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    specialty = db.Column(db.String(200), default="")
    photo_url = db.Column(db.String(500), default="")
    active = db.Column(db.Boolean, default=True)

class Service(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    price = db.Column(db.Integer, nullable=False, default=0)
    duration = db.Column(db.Integer, nullable=False, default=30)
    active = db.Column(db.Boolean, default=True)

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(160), nullable=False)
    price = db.Column(db.Integer, nullable=False, default=0)
    stock = db.Column(db.Integer, nullable=False, default=0)
    active = db.Column(db.Boolean, default=True)

class Media(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    entity_type = db.Column(db.String(30), nullable=False)
    entity_id = db.Column(db.Integer, nullable=False)
    path = db.Column(db.String(500), nullable=False)

    __table_args__ = (
        UniqueConstraint("entity_type", "entity_id", name="uq_media_entity"),
    )

class Client(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(160), nullable=False)
    phone = db.Column(db.String(40), nullable=False, unique=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Appointment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey("client.id"), nullable=False)
    barber_id = db.Column(db.Integer, db.ForeignKey("barber.id"), nullable=False)
    service_id = db.Column(db.Integer, db.ForeignKey("service.id"), nullable=False)
    appointment_date = db.Column(db.Date, nullable=False)
    appointment_time = db.Column(db.Time, nullable=False)
    price = db.Column(db.Integer, nullable=False, default=0)
    status = db.Column(db.String(40), nullable=False, default="Confirmada")
    notes = db.Column(db.Text, default="")
    source = db.Column(db.String(30), default="Web")
    payment_method = db.Column(db.String(30), nullable=False, default="")
    whatsapp_message_id = db.Column(db.String(250), default="")
    reminder_30_sent = db.Column(db.Boolean, default=False)
    reminder_10_sent = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    client = db.relationship("Client")
    barber = db.relationship("Barber")
    service = db.relationship("Service")

    __table_args__ = (
        UniqueConstraint("barber_id", "appointment_date", "appointment_time", name="uq_barber_slot"),
    )

PAYMENT_METHODS = {"Efectivo", "SINPE Móvil"}

def ensure_schema_updates():
    """Aplica cambios pequeños de esquema sin borrar la base existente."""
    inspector = inspect(db.engine)
    table_name = Appointment.__tablename__
    columns = {col["name"] for col in inspector.get_columns(table_name)}
    if "payment_method" not in columns:
        db.session.execute(text(
            f"ALTER TABLE \"{table_name}\" ADD COLUMN payment_method VARCHAR(30) DEFAULT ''"
        ))
        db.session.commit()

GOLDENS_STANDARD_SERVICES = [
    ("Corte una peineta", 4000, 30),
    ("Corte cabello", 5000, 30),
    ("Corte + Barba", 8000, 45),
    ("Rapado + Barba", 6000, 35),
    ("Corte Goldens", 10000, 60),
    ("Cejas", 1000, 10),
    ("Diseño", 2000, 15),
    ("Decoloración + Corte", 15000, 90),
    ("Exfoliación", 3000, 20),
]

def ensure_goldens_standard_services():
    existing = {s.name.strip().lower(): s for s in Service.query.all()}
    changed = False
    for name, price, duration in GOLDENS_STANDARD_SERVICES:
        key = name.strip().lower()
        if key in existing:
            svc = existing[key]
            # Keep service visible and align price/duration to the Goldens menu.
            svc.price = price
            svc.duration = duration
            svc.active = True
            changed = True
        else:
            db.session.add(Service(
                name=name,
                price=price,
                duration=duration,
                active=True,
            ))
            changed = True
    if changed:
        db.session.commit()

def seed():
    if Barber.query.count() == 0:
        db.session.add(Barber(name="Fernando", specialty="Cortes clásicos, fade y barba"))
    if Service.query.count() == 0:
        db.session.add_all([
            Service(name="Corte", price=5000, duration=30),
            Service(name="Corte + Barba", price=8000, duration=45),
            Service(name="Barba", price=4000, duration=30),
            Service(name="Cejas / Perfilado", price=2000, duration=15),
        ])
    db.session.commit()

def _photo_url(entity_type, entity_id):
    media = Media.query.filter_by(entity_type=entity_type, entity_id=entity_id).first()
    if media:
        return "/static/" + media.path.replace("\\", "/")
    return ""

def _photo_map(entity_type):
    return {
        m.entity_id: "/static/" + m.path.replace("\\", "/")
        for m in Media.query.filter_by(entity_type=entity_type).all()
    }

def _valid_image(file):
    if not file or not file.filename:
        return False
    filename = secure_filename(file.filename)
    if "." not in filename:
        return False
    return filename.rsplit(".", 1)[1].lower() in ALLOWED_IMAGE_EXTENSIONS

def _save_photo(file, entity_type, entity_id):
    if not file or not file.filename:
        return True
    if not _valid_image(file):
        flash("La foto debe ser JPG, JPEG, PNG o WEBP.", "error")
        return False

    ext = secure_filename(file.filename).rsplit(".", 1)[1].lower()
    filename = f"{entity_type}_{entity_id}_{uuid4().hex[:12]}.{ext}"
    target = UPLOAD_DIR / filename
    file.save(target)

    old = Media.query.filter_by(entity_type=entity_type, entity_id=entity_id).first()
    if old:
        try:
            old_file = Path(app.root_path) / "static" / old.path
            if old_file.exists():
                old_file.unlink()
        except Exception:
            pass
        old.path = f"uploads/{filename}"
    else:
        db.session.add(Media(
            entity_type=entity_type,
            entity_id=entity_id,
            path=f"uploads/{filename}"
        ))
    return True

def _remove_photo(entity_type, entity_id):
    media = Media.query.filter_by(entity_type=entity_type, entity_id=entity_id).first()
    if not media:
        return
    try:
        target = Path(app.root_path) / "static" / media.path
        if target.exists():
            target.unlink()
    except Exception:
        pass
    db.session.delete(media)

def normalize_phone(phone):
    digits = re.sub(r"\D", "", phone or "")
    if len(digits) == 8:
        digits = "506" + digits
    return digits

def money(n):
    return "₡{:,.0f}".format(n or 0)

app.jinja_env.filters["money"] = money

def admin_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if not session.get("admin"):
            return redirect(url_for("admin_login"))
        return fn(*args, **kwargs)
    return wrapped

def slot_times(for_date, barber_id):
    slots = []
    cursor = datetime.combine(for_date, time(OPEN_HOUR, 0))
    end = datetime.combine(for_date, time(CLOSE_HOUR, 0))
    taken = {
        a.appointment_time.strftime("%H:%M")
        for a in Appointment.query.filter_by(
            barber_id=barber_id,
            appointment_date=for_date
        ).filter(~Appointment.status.in_(["Cancelada", "No llegó"])).all()
    }

    now = datetime.now()
    while cursor < end:
        label = cursor.strftime("%H:%M")
        if label not in taken and (for_date != date.today() or cursor > now):
            slots.append(label)
        cursor += timedelta(minutes=SLOT_MINUTES)
    return slots

def booking_message(ap):
    return (
        "GOLDENS BARBERSHOP\n"
        "NUEVA RESERVA\n\n"
        f"Cliente: {ap.client.name}\n"
        f"WhatsApp: {ap.client.phone}\n"
        f"Servicio: {ap.service.name}\n"
        f"Barbero: {ap.barber.name}\n"
        f"Fecha: {ap.appointment_date.strftime('%d/%m/%Y')}\n"
        f"Hora: {ap.appointment_time.strftime('%H:%M')}\n"
        f"Precio: {money(ap.price)}\n"
        f"Método de pago: {ap.payment_method or 'No indicado'}\n\n"
        "Quiero confirmar mi reserva."
    )

def confirmation_message(ap):
    return (
        "GOLDENS BARBERSHOP\n"
        "✅ CITA CONFIRMADA\n\n"
        f"Hola {ap.client.name}.\n"
        f"Servicio: {ap.service.name}\n"
        f"Barbero: {ap.barber.name}\n"
        f"Fecha: {ap.appointment_date.strftime('%d/%m/%Y')}\n"
        f"Hora: {ap.appointment_time.strftime('%H:%M')}\n"
        f"Precio: {money(ap.price)}\n"
        f"Método de pago: {ap.payment_method or 'No indicado'}\n\n"
        f"Cancelar cita: {appointment_cancel_url(ap)}\n\n"
        "Te esperamos en Goldens Barbershop."
    )

def appointment_cancel_token(ap):
    s = URLSafeSerializer(app.config["SECRET_KEY"], salt="goldens-appointment-cancel")
    return s.dumps({"appointment_id": ap.id, "phone": ap.client.phone})

def appointment_cancel_url(ap):
    return url_for("client_cancel_appointment", token=appointment_cancel_token(ap), _external=True)

def wa_link(phone, message):
    number = normalize_phone(phone)
    if not number:
        return ""
    return f"https://wa.me/{number}?text={quote(message)}"

@app.route("/")
def public_home():
    appointments = []
    if session.get("admin"):
        appointments = Appointment.query.order_by(
            Appointment.appointment_date.desc(),
            Appointment.appointment_time.desc()
        ).limit(250).all()

    all_barbers = Barber.query.order_by(Barber.name).all()
    all_services = Service.query.order_by(Service.name).all()
    all_products = Product.query.order_by(Product.name).all()

    return render_template(
        "unified.html",
        admin_mode=bool(session.get("admin")),
        barbers=[b for b in all_barbers if b.active],
        services=[s for s in all_services if s.active],
        products=[p for p in all_products if p.active and p.stock > 0],
        admin_barbers=all_barbers,
        admin_services=all_services,
        admin_products=all_products,
        barber_photos=_photo_map("barber"),
        service_photos=_photo_map("service"),
        product_photos=_photo_map("product"),
        appointments=appointments,
        clients_count=Client.query.count(),
        today_count=Appointment.query.filter_by(appointment_date=date.today()).count(),
        today=date.today().isoformat(),
    )

@app.route("/api/slots")
def api_slots():
    try:
        d = datetime.strptime(request.args.get("date", ""), "%Y-%m-%d").date()
        barber_id = int(request.args.get("barber_id", "0"))
    except Exception:
        return jsonify({"slots": []}), 400
    if d < date.today():
        return jsonify({"slots": []})
    return jsonify({"slots": slot_times(d, barber_id)})

@app.route("/reservar", methods=["POST"])
def reserve():
    name = request.form.get("name", "").strip()
    phone = normalize_phone(request.form.get("phone", ""))
    notes = request.form.get("notes", "").strip()
    payment_method = request.form.get("payment_method", "").strip()

    try:
        barber_id = int(request.form["barber_id"])
        service_id = int(request.form["service_id"])
        ap_date = datetime.strptime(request.form["appointment_date"], "%Y-%m-%d").date()
        ap_time = datetime.strptime(request.form["appointment_time"], "%H:%M").time()
    except Exception:
        flash("Datos de reserva inválidos.", "error")
        return redirect(url_for("public_home"))

    if not name or len(phone) < 11 or ap_date < date.today():
        flash("Revisá tu nombre, teléfono y fecha.", "error")
        return redirect(url_for("public_home"))

    if payment_method not in PAYMENT_METHODS:
        flash("Seleccioná si vas a pagar en Efectivo o por SINPE Móvil.", "error")
        return redirect(url_for("public_home"))

    barber = Barber.query.filter_by(id=barber_id, active=True).first_or_404()
    service = Service.query.filter_by(id=service_id, active=True).first_or_404()

    valid_slots = slot_times(ap_date, barber_id)
    if ap_time.strftime("%H:%M") not in valid_slots:
        flash("Ese horario ya no está disponible. Elegí otro.", "error")
        return redirect(url_for("public_home"))

    client = Client.query.filter_by(phone=phone).first()
    if not client:
        client = Client(name=name, phone=phone)
        db.session.add(client)
        db.session.flush()
    else:
        client.name = name

    ap = Appointment(
        client_id=client.id,
        barber_id=barber.id,
        service_id=service.id,
        appointment_date=ap_date,
        appointment_time=ap_time,
        price=service.price,
        status="Confirmada",
        notes=notes,
        source="Web",
        payment_method=payment_method,
    )
    db.session.add(ap)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        flash("Ese espacio acaba de ocuparse. Elegí otra hora.", "error")
        return redirect(url_for("public_home"))

    client_to_goldens = wa_link(GOLDENS_WHATSAPP_NUMBER, booking_message(ap)) if GOLDENS_WHATSAPP_NUMBER else ""
    return render_template("ticket.html", ap=ap, client_to_goldens=client_to_goldens, cancel_url=appointment_cancel_url(ap))

@app.route("/cancelar-cita/<token>", methods=["POST"])
def client_cancel_appointment(token):
    s = URLSafeSerializer(app.config["SECRET_KEY"], salt="goldens-appointment-cancel")
    try:
        data = s.loads(token)
    except BadSignature:
        flash("El enlace para cancelar la cita no es válido.", "error")
        return redirect(url_for("public_home"))

    ap = Appointment.query.get_or_404(int(data.get("appointment_id", 0)))
    if ap.client.phone != data.get("phone"):
        abort(403)

    if ap.status == "Cancelada":
        flash("Esta cita ya estaba cancelada.", "ok")
    elif ap.status == "Atendida":
        flash("Esta cita ya fue atendida y no se puede cancelar.", "error")
    else:
        ap.status = "Cancelada"
        db.session.commit()
        flash("Tu cita fue cancelada. El horario quedó disponible nuevamente.", "ok")
    return redirect(url_for("public_home"))

@app.route("/admin/login", methods=["POST"])
def admin_login():
    if request.form.get("user") == ADMIN_USER and request.form.get("pin") == ADMIN_PIN:
        session["admin"] = True
        return redirect(url_for("public_home"))
    flash("Usuario o PIN incorrecto.", "error")
    return redirect(url_for("public_home"))

@app.route("/admin/logout")
def admin_logout():
    session.clear()
    return redirect(url_for("public_home"))

@app.route("/admin")
@admin_required
def admin_dashboard():
    return redirect(url_for("public_home"))

@app.route("/admin/appointment/<int:ap_id>/status", methods=["POST"])
@admin_required
def admin_status(ap_id):
    ap = Appointment.query.get_or_404(ap_id)
    status = request.form.get("status", "")
    if status not in ["Confirmada", "Pendiente", "Atendida", "Cancelada", "No llegó"]:
        abort(400)
    ap.status = status
    db.session.commit()
    return redirect(url_for("admin_dashboard"))

@app.route("/admin/appointment/<int:ap_id>/whatsapp")
@admin_required
def admin_whatsapp(ap_id):
    ap = Appointment.query.get_or_404(ap_id)
    return redirect(wa_link(ap.client.phone, confirmation_message(ap)))

@app.route("/admin/appointment/<int:ap_id>/delete", methods=["POST"])
@admin_required
def admin_appointment_delete(ap_id):
    ap = Appointment.query.get_or_404(ap_id)
    client_name = ap.client.name if ap.client else "Cliente"
    db.session.delete(ap)
    db.session.commit()
    flash(f"Cita de {client_name} eliminada.", "ok")
    return redirect(url_for("public_home") + "#agenda")

@app.route("/admin/barber", methods=["POST"])
@admin_required
def admin_barber_add():
    name = request.form.get("name", "").strip()
    if not name:
        flash("Escribí el nombre del barbero.", "error")
        return redirect(url_for("public_home"))

    barber = Barber(
        name=name,
        specialty=request.form.get("specialty", "").strip(),
        active=True,
    )
    db.session.add(barber)
    db.session.flush()
    if not _save_photo(request.files.get("photo"), "barber", barber.id):
        db.session.rollback()
        return redirect(url_for("public_home"))
    db.session.commit()
    flash("Barbero agregado.", "ok")
    return redirect(url_for("public_home"))

@app.route("/admin/barber/<int:barber_id>/update", methods=["POST"])
@admin_required
def admin_barber_update(barber_id):
    barber = Barber.query.get_or_404(barber_id)
    barber.name = request.form.get("name", barber.name).strip() or barber.name
    barber.specialty = request.form.get("specialty", "").strip()
    barber.active = request.form.get("active", "true") == "true"
    if not _save_photo(request.files.get("photo"), "barber", barber.id):
        db.session.rollback()
        return redirect(url_for("public_home"))
    db.session.commit()
    flash("Barbero actualizado.", "ok")
    return redirect(url_for("public_home"))

@app.route("/admin/barber/<int:barber_id>/remove", methods=["POST"])
@admin_required
def admin_barber_remove(barber_id):
    barber = Barber.query.get_or_404(barber_id)
    has_history = Appointment.query.filter_by(barber_id=barber.id).first() is not None
    if has_history:
        barber.active = False
        db.session.commit()
        flash("Barbero ocultado. Se conserva el historial de citas.", "ok")
    else:
        _remove_photo("barber", barber.id)
        db.session.delete(barber)
        db.session.commit()
        flash("Barbero eliminado.", "ok")
    return redirect(url_for("public_home"))

@app.route("/admin/service", methods=["POST"])
@admin_required
def admin_service_add():
    name = request.form.get("name", "").strip()
    if not name:
        flash("Escribí el nombre del servicio.", "error")
        return redirect(url_for("public_home"))
    service = Service(
        name=name,
        price=int(request.form.get("price", "0") or 0),
        duration=int(request.form.get("duration", "30") or 30),
        active=True,
    )
    db.session.add(service)
    db.session.flush()
    if not _save_photo(request.files.get("photo"), "service", service.id):
        db.session.rollback()
        return redirect(url_for("public_home"))
    db.session.commit()
    flash("Servicio agregado.", "ok")
    return redirect(url_for("public_home"))

@app.route("/admin/service/<int:service_id>/update", methods=["POST"])
@admin_required
def admin_service_update(service_id):
    service = Service.query.get_or_404(service_id)
    service.name = request.form.get("name", service.name).strip() or service.name
    service.price = int(request.form.get("price", service.price) or 0)
    service.duration = int(request.form.get("duration", service.duration) or 30)
    service.active = request.form.get("active", "true") == "true"
    if not _save_photo(request.files.get("photo"), "service", service.id):
        db.session.rollback()
        return redirect(url_for("public_home"))
    db.session.commit()
    flash("Servicio actualizado.", "ok")
    return redirect(url_for("public_home"))

@app.route("/admin/service/<int:service_id>/remove", methods=["POST"])
@admin_required
def admin_service_remove(service_id):
    service = Service.query.get_or_404(service_id)
    has_history = Appointment.query.filter_by(service_id=service.id).first() is not None
    if has_history:
        service.active = False
        db.session.commit()
        flash("Servicio ocultado. Se conserva el historial de citas.", "ok")
    else:
        _remove_photo("service", service.id)
        db.session.delete(service)
        db.session.commit()
        flash("Servicio eliminado.", "ok")
    return redirect(url_for("public_home"))

@app.route("/admin/product", methods=["POST"])
@admin_required
def admin_product_add():
    name = request.form.get("name", "").strip()
    if not name:
        flash("Escribí el nombre del producto.", "error")
        return redirect(url_for("public_home"))
    product = Product(
        name=name,
        price=int(request.form.get("price", "0") or 0),
        stock=int(request.form.get("stock", "0") or 0),
        active=True,
    )
    db.session.add(product)
    db.session.flush()
    if not _save_photo(request.files.get("photo"), "product", product.id):
        db.session.rollback()
        return redirect(url_for("public_home"))
    db.session.commit()
    flash("Producto agregado.", "ok")
    return redirect(url_for("public_home"))

@app.route("/admin/product/<int:product_id>/update", methods=["POST"])
@admin_required
def admin_product_update(product_id):
    product = Product.query.get_or_404(product_id)
    product.name = request.form.get("name", product.name).strip() or product.name
    product.price = int(request.form.get("price", product.price) or 0)
    product.stock = int(request.form.get("stock", product.stock) or 0)
    product.active = request.form.get("active", "true") == "true"
    if not _save_photo(request.files.get("photo"), "product", product.id):
        db.session.rollback()
        return redirect(url_for("public_home"))
    db.session.commit()
    flash("Producto actualizado.", "ok")
    return redirect(url_for("public_home"))

@app.route("/admin/product/<int:product_id>/remove", methods=["POST"])
@admin_required
def admin_product_remove(product_id):
    product = Product.query.get_or_404(product_id)
    _remove_photo("product", product.id)
    db.session.delete(product)
    db.session.commit()
    flash("Producto eliminado.", "ok")
    return redirect(url_for("public_home"))

@app.route("/health")
def health():
    return jsonify({"ok": True, "service": "goldens-pro-v9-media-manager"})

@app.cli.command("init-db")
def init_db():
    db.create_all()
    seed()
    print("Database initialized.")

with app.app_context():
    db.create_all()
    ensure_schema_updates()
    seed()
    ensure_goldens_standard_services()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=os.getenv("FLASK_DEBUG") == "1")
