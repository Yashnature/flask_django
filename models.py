from extensions import db


class User(db.Model):
    __tablename__ = "mobile_banking_users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    mpin_secure_hash = db.Column(db.String(255), nullable=True)
    atm_card_secure_hash = db.Column(db.String(255), nullable=True)
    atm_card_last4 = db.Column(db.String(4), nullable=True)

    def __repr__(self):
        return f"<User {self.email}>"

