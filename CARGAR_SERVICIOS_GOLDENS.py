from app import app, db, ensure_goldens_standard_services

with app.app_context():
    db.create_all()
    ensure_goldens_standard_services()
    print("Servicios de Goldens cargados correctamente.")
