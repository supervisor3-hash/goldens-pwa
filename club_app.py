import os
import re
import csv
import io
import secrets
import hmac
import time
from datetime import datetime, timezone
from urllib.parse import quote
from zoneinfo import ZoneInfo

import qrcode
from flask import Flask, request, redirect, url_for, session, abort, render_template_string, Response, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func, select

app = Flask(__name__)
app.secret_key = os.environ.get("CLUB_SECRET_KEY", "dev-only-secret-DO-NOT-DEPLOY")
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SECURE=os.environ.get("CLUB_PRODUCTION", "0") == "1",
    SESSION_COOKIE_SAMESITE="Lax",
    MAX_CONTENT_LENGTH=32 * 1024,
    SQLALCHEMY_TRACK_MODIFICATIONS=False,
)

database_url = os.environ.get("DATABASE_URL", "")
if database_url.startswith("postgres://"):
    database_url = "postgresql+psycopg://" + database_url[len("postgres://"):]
elif database_url.startswith("postgresql://"):
    database_url = "postgresql+psycopg://" + database_url[len("postgresql://"):]
app.config["SQLALCHEMY_DATABASE_URI"] = database_url or "sqlite:///goldens_club_local.db"
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"pool_pre_ping": True}
db = SQLAlchemy(app)
CR_TZ = ZoneInfo("America/Costa_Rica")
ADMIN_PASSWORD = os.environ.get("CLUB_ADMIN_PASSWORD", "")
CLOUD_CONFIGURED = bool(database_url and ADMIN_PASSWORD and os.environ.get("CLUB_SECRET_KEY"))
WHATSAPP = re.sub(r"\D", "", os.environ.get("GOLDENS_WHATSAPP_NUMBER", "50660158371"))
FAILED = {}

class Customer(db.Model):
    __tablename__ = "club_customer"
    id = db.Column(db.Integer, primary_key=True)
    token = db.Column(db.String(72), unique=True, nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(15), nullable=False, unique=True, index=True)
    stamps = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    events = db.relationship("StampEvent", back_populates="customer", lazy="select", cascade="all,delete-orphan")

class StampEvent(db.Model):
    __tablename__ = "club_event"
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("club_customer.id"), nullable=False, index=True)
    kind = db.Column(db.String(12), nullable=False)
    by_staff = db.Column(db.String(50), nullable=False)
    new_total = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    customer = db.relationship("Customer", back_populates="events")

with app.app_context():
    db.create_all()

def today_cr():
    return datetime.now(CR_TZ).date()

def normalize_phone(value):
    digits = re.sub(r"\D", "", value or "")
    if len(digits) == 11 and digits.startswith("506"):
        return digits[3:]
    return digits if len(digits) == 8 else ""

def short_name(name):
    parts = name.split()
    if len(parts) <= 1:
        return name
    return parts[0] + " " + parts[1][0] + "."

def csrf_token():
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(32)
    return session["csrf"]

def verify_csrf():
    given = request.form.get("csrf", "")
    if not given or not hmac.compare_digest(given, session.get("csrf", "")):
        abort(403)

def staff_only():
    if not session.get("club_admin"):
        abort(403)

@app.after_request
def protective_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Frame-Options"] = "DENY"
    if request.path.startswith("/admin"):
        response.headers["Cache-Control"] = "no-store"
    return response

CSS = """
:root{--g:#e9c676;--dark:#0b0b0d;--panel:#19191b;--border:#4b3b21;--white:#faf6ee;--muted:#bcb5aa}
*{box-sizing:border-box}
body{margin:0;background:radial-gradient(ellipse 80% 40% at 50% -15%,#4b3415 0%,transparent 70%),var(--dark);color:var(--white);font:15px/1.5 system-ui,-apple-system,'Segoe UI',sans-serif;min-height:100vh}
a{color:var(--g)} h1,h2,p{margin-top:0}
.shell{width:min(1030px,calc(100% - 28px));margin:0 auto;padding:20px 0 60px}
header{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:30px}
.logo{font:26px/1.1 Georgia,serif;letter-spacing:.13em;color:var(--g)}
.small{font-size:11px;text-transform:uppercase;letter-spacing:.25em;color:#c7aa69}
.nav{display:flex;align-items:center;gap:16px}
.nav a{text-decoration:none;color:var(--g);font-size:13px}
.card{border:1px solid var(--border);border-radius:22px;background:linear-gradient(145deg,#242019,#111115 65%);padding:28px;box-shadow:0 20px 55px #0005}
.center{text-align:center}.eyebrow{text-transform:uppercase;letter-spacing:.26em;font-size:12px;color:#ceaf68;margin:0 0 12px}
.hero-title{font:clamp(32px,6vw,56px)/1.06 Georgia,serif;color:#f5db99;margin-bottom:18px}
.lead{color:#d1c8b7;font-size:16px}
.btn{border:1px solid #9e7b39;border-radius:11px;background:linear-gradient(130deg,#f4d28a,#b88d3c);color:#1c170f;padding:11px 18px;font-weight:800;cursor:pointer;text-decoration:none;display:inline-block}
.btn.secondary{background:transparent;color:var(--g)}
.btn.danger{border-color:#be7474;color:#ffd4d4}
.btn.smallbtn{padding:7px 10px;font-size:12px}
input,select{width:100%;background:#111113;color:#fff;border:1px solid #706045;border-radius:9px;padding:12px;font-size:15px}
label{display:block;font-size:12px;color:#dfc68f;margin:12px 0 5px}
form.inline{display:inline}
.stack{display:grid;gap:14px}
.two{display:grid;grid-template-columns:1fr 1fr;gap:18px}
.three{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}
.stat{background:#171717;border:1px solid #44381f;padding:14px;border-radius:14px}
.stat b{display:block;font-size:26px;color:var(--g)}.stat span{font-size:11px;color:#d2c8b6}
.stamps{display:grid;grid-template-columns:repeat(7,1fr);gap:7px;margin:28px 0}
.stamp{aspect-ratio:1;border:1px solid #a9874f;border-radius:50%;display:grid;place-items:center;font-weight:900;font-size:clamp(12px,3.7vw,21px);background:#2c2318;color:#c9aa72}
.stamp.done{background:radial-gradient(circle at 35% 25%,#fbe8b0,#c69644 77%);color:#1d180e;border-color:#ffdc8f}
.stamp.reward{background:#090a0b;color:#ebc370;border-width:2px}.stamp.reward.ready{background:#f9db91;color:#241909}
.notice{padding:13px 16px;border-radius:12px;background:#332a1a;color:#f2d99f;margin:16px 0}
.error{background:#4a2323;color:#ffe2d7}
table{border-collapse:collapse;width:100%;font-size:13px}
th,td{text-align:left;padding:12px 8px;border-bottom:1px solid #3c3325;vertical-align:middle}
th{color:#e5c77d}
.tablewrap{overflow:auto}.actions{display:flex;flex-wrap:wrap;align-items:center;gap:7px}
footer{color:#b9b2a7;font-size:12px;text-align:center;margin:35px 0}
code{color:#fce3a0} .qr{background:#fff;padding:10px;border-radius:10px;display:inline-block;margin:14px}
.subtle{color:var(--muted);font-size:13px}.wordwrap{overflow-wrap:anywhere}
@media(max-width:680px){.two,.three{grid-template-columns:1fr}.card{padding:19px}header{align-items:flex-start}.stamps{gap:4px}.stamp{font-size:13px}th,td{font-size:11px;padding:8px 4px}}
"""

BASE = """
<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#090909">
<title>{{ title }} | Goldens Club</title><style>{{ css|safe }}</style></head>
<body><main class="shell">
<header><div><a class="logo" href="/" style="text-decoration:none">GOLDENS</a>
<div class="small">BARBERSHOP · CLUB</div></div>
<nav class="nav"><a href="/">Inicio</a><a href="/admin">Barbería</a></nav>
</header>
{% with messages=get_flashed_messages(with_categories=true) %}{% for category,message in messages %}
<div class="notice {{ 'error' if category=='error' else '' }}">{{ message }}</div>{% endfor %}{% endwith %}
{{ body|safe }}
<footer>GOLDENS BARBERSHOP · Costado norte del parque, Moravia · Costa Rica<br>
6 cortes pagados = 7.º gratis · Válido para cortes de cabello.</footer>
</main></body></html>
"""

def page(title, body, **ctx):
    content = render_template_string(body, **ctx)
    return render_template_string(BASE, title=title, body=content, css=CSS)

@app.get("/health")
def health():
    try:
        db.session.execute(select(func.count()).select_from(Customer)).scalar()
        return jsonify({"ok": True, "app": "Goldens Club", "database": "cloud" if CLOUD_CONFIGURED else "local-test"})
    except Exception:
        return jsonify({"ok": False, "app": "Goldens Club"}), 503

@app.get("/")
def home():
    return page("Fidelidad", """
<section class="card center" style="max-width:650px;margin:auto">
<div class="eyebrow">Programa de clientes frecuentes</div>
<h1 class="hero-title">Tus cortes valen oro</h1>
<p class="lead">Acumulá <b>6 cortes pagados</b> y el <b>7.º corte es GRATIS.</b></p>
<div class="stamps">
{% for i in range(1,7) %}<div class="stamp">{{i}}</div>{% endfor %}
<div class="stamp reward">★</div>
</div>
<p>Pedí tu tarjeta digital en Goldens. Te damos un enlace personal con QR para revisar tus sellos cuando querás.</p>
<p><a class="btn" href="https://wa.me/{{wa}}?text={{msg|urlencode}}" target="_blank" rel="noopener">Pedir mi tarjeta</a></p>
<p class="subtle">Solamente la barbería puede registrar sellos o canjear premios.</p>
</section>""", wa=WHATSAPP, msg="Hola Goldens, quiero mi tarjeta virtual de Goldens Club.")

@app.get("/t/<token>")
def card(token):
    client = Customer.query.filter_by(token=token).first_or_404()
    return page("Mi tarjeta", """
<section class="card center" style="max-width:680px;margin:auto">
<p class="eyebrow">Tarjeta digital · Cliente frecuente</p><h1 class="hero-title">GOLDENS CLUB</h1>
<h2>{{name}}</h2>
<div class="stamps">{% for n in range(1,7) %}
<div class="stamp {{ 'done' if n<=client.stamps else '' }}">{{'✓' if n<=client.stamps else n}}</div>
{% endfor %}<div class="stamp reward {{'ready' if client.stamps==6 else ''}}">★</div></div>
{% if client.stamps==6 %}
<div class="notice">¡Felicidades! Tu próximo corte es GRATIS. Mostrá este QR en Goldens para canjearlo.</div>
{% else %}<p class="lead">Llevás <b>{{client.stamps}} de 6</b> sellos. Te faltan <b>{{6-client.stamps}}</b> cortes pagados para tu premio.</p>{% endif %}
<img class="qr" src="{{url_for('qr',token=client.token)}}" alt="Código QR de la tarjeta" width="205" height="205">
<p class="subtle">Mostrá este código al pagar. El personal de Goldens registra tu sello.</p>
<p><a class="btn secondary" href="/" >Sobre Goldens Club</a></p>
</section>
""", client=client, name=short_name(client.name))

@app.get("/q/<token>.png")
def qr(token):
    client = Customer.query.filter_by(token=token).first_or_404()
    link = url_for("card", token=client.token, _external=True)
    img = qrcode.make(link)
    data = io.BytesIO()
    img.save(data, format="PNG")
    return Response(data.getvalue(), mimetype="image/png", headers={"Cache-Control":"private, max-age=600"})

def block_if_not_configured():
    if not CLOUD_CONFIGURED:
        return page("Configuración", """
<div class="card center" style="max-width:590px;margin:auto">
<h2>Sistema pendiente de activar</h2>
<p>La aplicación está publicada, pero falta conectar el almacenamiento persistente y las credenciales de administración.</p>
<p>Configuración requerida: <code>DATABASE_URL</code>, <code>CLUB_SECRET_KEY</code> y <code>CLUB_ADMIN_PASSWORD</code>.</p>
</div>"""), 503
    return None

@app.route("/admin", methods=["GET"])
def admin():
    blocked = block_if_not_configured()
    if blocked:
        return blocked
    if not session.get("club_admin"):
        return page("Acceso de barbería", """
<section class="card" style="max-width:460px;margin:auto">
<h1 style="color:var(--g)">Acceso Goldens</h1>
<p class="subtle">Solo personal autorizado. Los clientes nunca pueden añadir sellos.</p>
<form action="/admin/login" method="post">
<input type="hidden" name="csrf" value="{{csrf}}">
<label>Contraseña de la barbería</label><input type="password" name="password" required autocomplete="current-password" minlength="10">
<p><button class="btn" type="submit">Entrar al sistema</button></p>
</form></section>
""", csrf=csrf_token())
    q = request.args.get("q", "").strip()[:70]
    query = Customer.query
    if q:
        query = query.filter(db.or_(Customer.name.ilike("%"+q+"%"),Customer.phone.like("%"+q+"%")))
    clients = query.order_by(Customer.id.desc()).limit(150).all()
    stats = [Customer.query.count(), db.session.query(func.count(StampEvent.id)).filter_by(kind="stamp").scalar(), db.session.query(func.count(StampEvent.id)).filter_by(kind="redeem").scalar()]
    return page("Administrar", """
<div class="actions" style="justify-content:space-between;margin-bottom:16px">
<h1 style="color:var(--g);margin:0">Panel de sellos</h1><div class="actions">
<a class="btn secondary smallbtn" href="/admin/export">Descargar respaldo CSV</a>
<form class="inline" action="/admin/logout" method="post"><input type="hidden" name="csrf" value="{{csrf}}"><button class="btn secondary smallbtn">Salir</button></form>
</div></div>
<div class="three">
<div class="stat"><b>{{stats[0]}}</b><span>Clientes</span></div>
<div class="stat"><b>{{stats[1]}}</b><span>Sellos acumulados</span></div>
<div class="stat"><b>{{stats[2]}}</b><span>Cortes gratis canjeados</span></div>
</div>
<div class="two" style="margin-top:20px">
<section class="card"><h2>Registrar cliente</h2>
<form action="/admin/create" method="post">
<input type="hidden" name="csrf" value="{{csrf}}">
<label>Nombre completo</label><input name="name" maxlength="120" required placeholder="Nombre del cliente">
<label>WhatsApp (8 dígitos)</label><input name="phone" type="tel" inputmode="tel" maxlength="18" placeholder="8888-8888" required>
<p><button class="btn">Crear tarjeta digital</button></p>
</form>
</section>
<section class="card"><h2>Consultar cliente</h2>
<form method="get" action="/admin">
<label>Nombre o teléfono</label><input name="q" value="{{q}}" placeholder="Buscar">
<p><button class="btn secondary">Buscar</button></p>
</form>
<p class="subtle">Para cada cliente podés añadir un sello al cobrar o canjear el séptimo corte gratis. Se conserva un historial.</p>
</section></div>
<section class="card" style="margin-top:20px"><h2>Clientes y tarjetas</h2>
<div class="tablewrap"><table><thead><tr><th>Cliente</th><th>WhatsApp</th><th>Sellos</th><th>Acciones</th></tr></thead><tbody>
{% for c in clients %}<tr>
<td><b>{{c.name}}</b><br><a href="{{url_for('card',token=c.token)}}" target="_blank">Ver tarjeta / QR</a></td>
<td>{{c.phone}}</td><td><b>{{c.stamps}}/6</b></td>
<td><div class="actions">
{% if c.stamps<6 %}<form class="inline" action="/admin/stamp/{{c.id}}" method="post" onsubmit="return confirm('¿Confirmar corte pagado y agregar 1 sello?');">
<input type="hidden" name="csrf" value="{{csrf}}"><select name="staff" aria-label="Barbero" style="width:auto;padding:7px"><option>Franklin</option><option>José Chamo</option><option>Kevin</option><option>Goldens</option></select>
<button class="btn smallbtn">+1 sello</button></form>
{% else %}<form class="inline" action="/admin/redeem/{{c.id}}" method="post" onsubmit="return confirm('¿Confirmar el 7.º corte GRATIS? Esto reinicia los 6 sellos.');">
<input type="hidden" name="csrf" value="{{csrf}}"><select name="staff" aria-label="Barbero" style="width:auto;padding:7px"><option>Franklin</option><option>José Chamo</option><option>Kevin</option><option>Goldens</option></select>
<button class="btn smallbtn">Canjear gratis</button></form>{% endif %}
<a class="btn secondary smallbtn" target="_blank" rel="noopener" href="https://wa.me/506{{c.phone}}?text={{('Hola '+c.name+', esta es tu tarjeta Goldens Club: '+url_for('card',token=c.token,_external=True))|urlencode}}">WhatsApp</a>
<a class="btn secondary smallbtn" href="/admin/history/{{c.id}}">Historial</a>
</div></td></tr>{% else %}
<tr><td colspan="4" class="subtle">Todavía no hay clientes en esta búsqueda.</td></tr>
{% endfor %}
</tbody></table></div></section>
""", clients=clients, stats=stats, csrf=csrf_token(), q=q)

@app.post("/admin/login")
def admin_login():
    blocked = block_if_not_configured()
    if blocked:
        return blocked
    verify_csrf()
    ip = request.remote_addr or "unknown"
    attempts = [t for t in FAILED.get(ip, []) if time.monotonic()-t < 900]
    if len(attempts) >= 8:
        abort(429)
    if not hmac.compare_digest(request.form.get("password",""), ADMIN_PASSWORD):
        attempts.append(time.monotonic())
        FAILED[ip] = attempts
        flash("Contraseña incorrecta.", "error")
        return redirect("/admin")
    session.clear()
    session["club_admin"] = True
    session["csrf"] = secrets.token_urlsafe(32)
    FAILED.pop(ip, None)
    return redirect("/admin")

@app.post("/admin/logout")
def admin_logout():
    staff_only()
    verify_csrf()
    session.clear()
    return redirect("/")

@app.post("/admin/create")
def create():
    staff_only()
    verify_csrf()
    name = " ".join(request.form.get("name","").split())[:120]
    phone = normalize_phone(request.form.get("phone",""))
    if len(name)<2 or not phone:
        flash("Revisá el nombre y el número de 8 dígitos.", "error")
        return redirect("/admin")
    existing = Customer.query.filter_by(phone=phone).first()
    if existing:
        flash("Ese teléfono ya tiene tarjeta. Abrí su registro para continuar.")
        return redirect("/admin?q="+quote(phone))
    record = Customer(name=name,phone=phone,token=secrets.token_urlsafe(24))
    db.session.add(record)
    try:
        db.session.commit()
        flash("Tarjeta creada. Enviásela al cliente por WhatsApp.")
    except Exception:
        db.session.rollback()
        flash("No se pudo crear el registro.", "error")
    return redirect("/admin?q="+quote(phone))

def staff_value():
    staff = request.form.get("staff","Goldens")
    return staff if staff in {"Franklin","José Chamo","Kevin","Goldens"} else "Goldens"

@app.post("/admin/stamp/<int:id>")
def stamp(id):
    staff_only()
    verify_csrf()
    c = db.session.execute(select(Customer).where(Customer.id==id).with_for_update()).scalar_one_or_none()
    if not c:
        abort(404)
    if c.stamps >= 6:
        flash("Ya completó los 6 sellos. Corresponde canjear el corte gratis.", "error")
        return redirect("/admin?q="+quote(c.phone))
    # One loyalty stamp per client per Costa Rica calendar day avoids repeated clicks.
    last = db.session.execute(select(StampEvent).where(StampEvent.customer_id==c.id,StampEvent.kind=="stamp").order_by(StampEvent.id.desc()).limit(1)).scalar_one_or_none()
    if last and last.created_at.replace(tzinfo=last.created_at.tzinfo or timezone.utc).astimezone(CR_TZ).date()==today_cr():
        flash("Este cliente ya recibió un sello hoy. No se duplicó.", "error")
        return redirect("/admin?q="+quote(c.phone))
    c.stamps += 1
    db.session.add(StampEvent(customer_id=c.id,kind="stamp",by_staff=staff_value(),new_total=c.stamps))
    db.session.commit()
    flash("¡Sello registrado! Progreso: "+str(c.stamps)+"/6")
    return redirect("/admin?q="+quote(c.phone))

@app.post("/admin/redeem/<int:id>")
def redeem(id):
    staff_only()
    verify_csrf()
    c = db.session.execute(select(Customer).where(Customer.id==id).with_for_update()).scalar_one_or_none()
    if not c:
        abort(404)
    if c.stamps!=6:
        flash("El cliente todavía no reúne 6 sellos.", "error")
        return redirect("/admin?q="+quote(c.phone))
    c.stamps=0
    db.session.add(StampEvent(customer_id=c.id,kind="redeem",by_staff=staff_value(),new_total=0))
    db.session.commit()
    flash("Corte gratis canjeado. La tarjeta inicia un nuevo ciclo.")
    return redirect("/admin?q="+quote(c.phone))

@app.get("/admin/history/<int:id>")
def history(id):
    staff_only()
    c=Customer.query.get_or_404(id)
    events=StampEvent.query.filter_by(customer_id=id).order_by(StampEvent.id.desc()).limit(100).all()
    return page("Historial", """
<a href="/admin" class="btn secondary smallbtn">← Volver</a>
<section class="card" style="margin-top:15px"><h1 style="color:var(--g)">Historial · {{c.name}}</h1>
<p>Teléfono {{c.phone}} · Sellos actuales {{c.stamps}}/6</p>
<div class="tablewrap"><table><tr><th>Fecha</th><th>Movimiento</th><th>Barbero</th><th>Nuevo total</th></tr>
{% for e in events %}<tr><td>{{e.created_at.strftime('%d/%m/%Y %H:%M')}} UTC</td>
<td>{{'Corte pagado (+1 sello)' if e.kind=='stamp' else 'Corte gratis canjeado'}}</td><td>{{e.by_staff}}</td><td>{{e.new_total}}</td></tr>
{% endfor %}</table></div></section>""",c=c,events=events)

@app.get("/admin/export")
def export():
    staff_only()
    output=io.StringIO()
    writer=csv.writer(output)
    writer.writerow(["cliente","telefono","sellos_actuales","tipo_movimiento","barbero","fecha_utc"])
    for customer in Customer.query.order_by(Customer.id).all():
        history=StampEvent.query.filter_by(customer_id=customer.id).order_by(StampEvent.id).all()
        if not history:
            writer.writerow([customer.name, customer.phone, customer.stamps,"","",""])
        for e in history:
            writer.writerow([customer.name,customer.phone,customer.stamps,e.kind,e.by_staff,e.created_at.isoformat()])
    return Response("\ufeff"+output.getvalue(), mimetype="text/csv; charset=utf-8",headers={"Content-Disposition":"attachment; filename=goldens-club-respaldo.csv"})

if __name__=="__main__":
    app.run(port=int(os.environ.get("PORT",5000)),debug=False)
