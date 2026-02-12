import os

from flask import Flask, render_template, request, redirect, session, send_from_directory
import re
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError
from werkzeug.security import generate_password_hash, check_password_hash

from flask_session import Session
from extensions import db

app = Flask(__name__)

# CONFIGURATION
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'secret123')
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv(
    'DATABASE_URL',
    'sqlite:///instance/users.db',
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_FILE_DIR'] = os.getenv('SESSION_FILE_DIR', '/tmp/flask_session')
os.makedirs(app.config['SESSION_FILE_DIR'], exist_ok=True)

db.init_app(app)

Session(app)

from models import User


LEGACY_ENCRYPTION_KEY = 3


def encrypt_password_with_key(password, key=LEGACY_ENCRYPTION_KEY):
    encrypted_chars = []
    for ch in password:
        encrypted_chars.append(chr((ord(ch) + key) % 0x110000))
    return "".join(encrypted_chars)


def verify_password(stored_password, provided_password):
    encrypted_input = encrypt_password_with_key(provided_password)
    if stored_password == encrypted_input:
        return True

    try:
        # Backward compatibility for older hash-based password storage.
        return check_password_hash(stored_password, provided_password)
    except (ValueError, TypeError):
        return False


def add_hash_marker(value):
    return f"#{value}"


def ensure_understandable_table_name():
    inspector = inspect(db.engine)
    table_names = set(inspector.get_table_names())
    if "mobile_banking_users" not in table_names and "user" in table_names:
        with db.engine.begin() as conn:
            conn.execute(text('ALTER TABLE "user" RENAME TO mobile_banking_users'))


def ensure_user_table_columns():
    inspector = inspect(db.engine)
    if "mobile_banking_users" not in inspector.get_table_names():
        return

    existing_columns = {col["name"] for col in inspector.get_columns("mobile_banking_users")}
    statements = []

    # Rename legacy columns to understandable names when possible.
    if "mpin_hash" in existing_columns and "mpin_secure_hash" not in existing_columns:
        statements.append('ALTER TABLE mobile_banking_users RENAME COLUMN mpin_hash TO mpin_secure_hash')
    if "card_hash" in existing_columns and "atm_card_secure_hash" not in existing_columns:
        statements.append('ALTER TABLE mobile_banking_users RENAME COLUMN card_hash TO atm_card_secure_hash')
    if "card_last4" in existing_columns and "atm_card_last4" not in existing_columns:
        statements.append('ALTER TABLE mobile_banking_users RENAME COLUMN card_last4 TO atm_card_last4')

    if "mpin_secure_hash" not in existing_columns and "mpin_hash" not in existing_columns:
        statements.append('ALTER TABLE mobile_banking_users ADD COLUMN mpin_secure_hash VARCHAR(255)')
    if "atm_card_secure_hash" not in existing_columns and "card_hash" not in existing_columns:
        statements.append('ALTER TABLE mobile_banking_users ADD COLUMN atm_card_secure_hash VARCHAR(255)')
    if "atm_card_last4" not in existing_columns and "card_last4" not in existing_columns:
        statements.append('ALTER TABLE mobile_banking_users ADD COLUMN atm_card_last4 VARCHAR(4)')

    with db.engine.begin() as conn:
        for statement in statements:
            conn.execute(text(statement))

        conn.execute(
            text(
                "UPDATE mobile_banking_users "
                "SET mpin_secure_hash = CONCAT('#', mpin_secure_hash) "
                "WHERE mpin_secure_hash IS NOT NULL AND mpin_secure_hash NOT LIKE '#%'"
            )
        )


def migrate_legacy_user_data():
    inspector = inspect(db.engine)
    table_names = set(inspector.get_table_names())
    if "user" not in table_names or "mobile_banking_users" not in table_names:
        return

    with db.engine.begin() as conn:
        legacy_rows = conn.execute(text('SELECT * FROM "user"')).mappings().all()
        existing_emails = {
            row[0]
            for row in conn.execute(text("SELECT email FROM mobile_banking_users")).all()
            if row[0]
        }

        for row in legacy_rows:
            email = row.get("email")
            if not email or email in existing_emails:
                continue

            mpin_value = row.get("mpin_secure_hash") or row.get("mpin_hash")
            if mpin_value and not str(mpin_value).startswith("#"):
                mpin_value = f"#{mpin_value}"

            card_hash_value = row.get("atm_card_secure_hash") or row.get("card_hash")
            card_last4_value = row.get("atm_card_last4") or row.get("card_last4")

            conn.execute(
                text(
                    "INSERT INTO mobile_banking_users "
                    "(name, email, password, mpin_secure_hash, atm_card_secure_hash, atm_card_last4) "
                    "VALUES (:name, :email, :password, :mpin_secure_hash, :atm_card_secure_hash, :atm_card_last4)"
                ),
                {
                    "name": row.get("name"),
                    "email": email,
                    "password": row.get("password"),
                    "mpin_secure_hash": mpin_value,
                    "atm_card_secure_hash": card_hash_value,
                    "atm_card_last4": card_last4_value,
                },
            )
            existing_emails.add(email)


def ensure_postgres_database_exists(database_uri):
    url = make_url(database_uri)
    if url.drivername.startswith("postgresql"):
        admin_url = url.set(database="postgres")
        admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
        try:
            with admin_engine.connect() as conn:
                exists = conn.execute(
                    text("SELECT 1 FROM pg_database WHERE datname = :db_name"),
                    {"db_name": url.database},
                ).scalar()
                if not exists:
                    conn.execute(text(f'CREATE DATABASE "{url.database}"'))
        finally:
            admin_engine.dispose()


# create DB tables if they don't exist
with app.app_context():
    try:
        ensure_understandable_table_name()
        db.create_all()
        ensure_user_table_columns()
        migrate_legacy_user_data()
    except OperationalError as exc:
        # Handle first-run case where PostgreSQL server is reachable but DB is missing.
        if "does not exist" in str(exc):
            try:
                ensure_postgres_database_exists(app.config['SQLALCHEMY_DATABASE_URI'])
                ensure_understandable_table_name()
                db.create_all()
                ensure_user_table_columns()
                migrate_legacy_user_data()
            except Exception as inner_exc:
                app.logger.exception("Database bootstrap failed: %s", inner_exc)
        else:
            app.logger.exception("Database init failed: %s", exc)
    except Exception as exc:
        # Avoid crashing serverless import-time initialization.
        app.logger.exception("Unexpected startup error: %s", exc)

# HOME → LOGIN
@app.route('/')
def home():
    return redirect('/login')


@app.route('/favicon.ico')
def favicon():
    static_dir = app.static_folder or 'static'
    ico_name = 'favicon.ico'
    svg_name = 'logo.svg'

    if os.path.exists(os.path.join(static_dir, ico_name)):
        return send_from_directory(static_dir, ico_name, mimetype='image/vnd.microsoft.icon')

    if os.path.exists(os.path.join(static_dir, svg_name)):
        return send_from_directory(static_dir, svg_name, mimetype='image/svg+xml')

    return ('', 204)

# REGISTER
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form['name'].strip()
        email = request.form['email'].strip().lower()
        password = request.form['password']
        mpin = request.form['mpin'].strip()
        credit_card = request.form['credit_card'].strip()

        pw_pattern = r'^(?=.*[A-Za-z])(?=.*\d)(?=.*[^A-Za-z0-9]).{8,}$'
        if not re.match(pw_pattern, password):
            error = 'Password must be at least 8 characters and include a letter, number, and special character.'
            return render_template(
                'register.html',
                error=error,
                name=name,
                email=email,
                mpin=mpin,
                credit_card=credit_card
            )

        if not re.match(r'^\d{4}$', mpin):
            error = 'MPIN must be exactly 4 digits.'
            return render_template(
                'register.html',
                error=error,
                name=name,
                email=email,
                mpin=mpin,
                credit_card=credit_card
            )

        if not re.match(r'^\d{12}$', credit_card):
            error = 'ATM card number must be exactly 12 digits.'
            return render_template(
                'register.html',
                error=error,
                name=name,
                email=email,
                mpin=mpin,
                credit_card=credit_card
            )

        if User.query.filter_by(email=email).first():
            error = 'An account with this email already exists.'
            return render_template(
                'register.html',
                error=error,
                name=name,
                email=email,
                mpin=mpin,
                credit_card=credit_card
            )

        encrypted_password = encrypt_password_with_key(password)
        mpin_secure_hash = add_hash_marker(generate_password_hash(mpin))
        atm_card_secure_hash = generate_password_hash(credit_card)

        user = User(
            name=name,
            email=email,
            password=encrypted_password,
            mpin_secure_hash=mpin_secure_hash,
            atm_card_secure_hash=atm_card_secure_hash,
            atm_card_last4=credit_card[-4:],
        )
        db.session.add(user)
        db.session.commit()

        return redirect('/login')

    return render_template('register.html')

# LOGIN
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email'].strip().lower()
        password = request.form['password']

        user = User.query.filter_by(email=email).first()

        if user and verify_password(user.password, password):
            session['user_id'] = user.id
            session['user_name'] = user.name
            return redirect('/dashboard')
        else:
            return render_template('login.html', error='Invalid email or password.')

    return render_template('login.html')

# DASHBOARD (PROTECTED)
@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect('/login')

    return render_template('dashboard.html', name=session['user_name'])

# LOGOUT
@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')

if __name__ == '__main__':
    app.run(debug=True)
