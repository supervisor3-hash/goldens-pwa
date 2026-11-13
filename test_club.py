import os
import unittest
import tempfile

file = tempfile.NamedTemporaryFile(prefix="goldens-test-",suffix=".db",delete=True)
os.environ["DATABASE_URL"] = "sqlite:///" + file.name
os.environ["CLUB_SECRET_KEY"] = "test-secret-long-value"
os.environ["CLUB_ADMIN_PASSWORD"] = "strong-test-password"
os.environ["CLUB_PRODUCTION"] = "0"

from club_app import app, db, Customer, StampEvent

class GoldensClubTests(unittest.TestCase):
    def setUp(self):
        app.config["TESTING"] = True
        self.client = app.test_client()
        with app.app_context():
            db.drop_all()
            db.create_all()

    def csrf(self):
        with self.client.session_transaction() as s:
            s["csrf"]="test-csrf"
            return s["csrf"]

    def login(self):
        resp=self.client.post("/admin/login",data={"csrf":self.csrf(),"password":"strong-test-password"},follow_redirects=True)
        self.assertEqual(resp.status_code,200)

    def test_public_intro(self):
        self.assertEqual(self.client.get("/").status_code,200)
        self.assertIn("7.º corte",self.client.get("/").get_data(as_text=True))

    def test_admin_authentication(self):
        self.assertEqual(self.client.get("/admin/export").status_code,403)
        self.assertEqual(self.client.post("/admin/create",data={"csrf":self.csrf(),"name":"Persona","phone":"88888888"}).status_code,403)
        self.login()
        self.assertIn("Panel de sellos",self.client.get("/admin").get_data(as_text=True))

    def test_card_stamps_and_redeem(self):
        self.login()
        r=self.client.post("/admin/create", data={"csrf":self.csrf(),"name":"Cliente Ejemplo","phone":"88887777"})
        self.assertEqual(r.status_code,302)
        with app.app_context():
            c=Customer.query.filter_by(phone="88887777").first()
            self.assertIsNotNone(c)
            token=c.token
            id=c.id
        self.assertEqual(self.client.get("/t/"+token).status_code,200)
        self.assertEqual(self.client.get("/q/"+token+".png").status_code,200)
        self.assertEqual(self.client.post("/admin/stamp/"+str(id),data={"csrf":self.csrf(),"staff":"Franklin"}).status_code,302)
        self.client.post("/admin/stamp/"+str(id),data={"csrf":self.csrf(),"staff":"Franklin"})
        with app.app_context():
            c=db.session.get(Customer,id)
            self.assertEqual(c.stamps,1)
            self.assertEqual(StampEvent.query.count(),1)
            c.stamps=6
            db.session.commit()
        self.assertEqual(self.client.post("/admin/redeem/"+str(id),data={"csrf":self.csrf(),"staff":"Kevin"}).status_code,302)
        with app.app_context():
            c=db.session.get(Customer,id)
            self.assertEqual(c.stamps,0)
            self.assertEqual(StampEvent.query.filter_by(kind="redeem").count(),1)

    def test_csrf(self):
        self.login()
        self.assertEqual(self.client.post("/admin/create",data={"csrf":"bad","name":"Persona","phone":"88888888"}).status_code,403)

if __name__=="__main__":
    unittest.main()
