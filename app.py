"""
☕ Café Atlas — Full Stack Flask App
=====================================
Features:
  - JWT Authentication (Register / Login / Logout)
  - Email Confirmation  (must verify email before full access)
  - Password Reset      (forgot password flow via email)
  - Role-based Access   (user vs admin)
  - Admin Dashboard     (manage all cafés and users)
  - Full Café CRUD API

Run:
  python app.py
  Visit: http://localhost:5000
"""

from flask import Flask, jsonify, request, render_template
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from flask_jwt_extended import (
    JWTManager, create_access_token, jwt_required,
    get_jwt_identity, get_jwt
)
from flask_mail import Mail, Message
from flask_bcrypt import Bcrypt
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import Integer, String, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature
from datetime import datetime, timedelta, timezone
from functools import wraps
import random
import os

# ─────────────────────────────────────────────────────────────────────────────
#  APP & CONFIG
# ─────────────────────────────────────────────────────────────────────────────

app = Flask(__name__)

app.config.update(
    SECRET_KEY                = os.environ.get('SECRET_KEY'),
    SQLALCHEMY_DATABASE_URI   = os.environ.get('DB_URL'),
    SQLALCHEMY_TRACK_MODIFICATIONS = False,

    # ── JWT CONFIG ──────────────────────────────────────────
    # Tokens expire after 24 hours — user must log in again after that.
    # In production, use a long random string for JWT_SECRET_KEY.
    JWT_SECRET_KEY            = os.environ.get('JWT_SECRET_KEY'),
    JWT_ACCESS_TOKEN_EXPIRES  = timedelta(hours=24),

    # ── EMAIL CONFIG ────────────────────────────────────────
    # For development: use Gmail or Mailtrap (https://mailtrap.io)
    # Mailtrap is a fake inbox perfect for testing emails safely.
    #
    # To use Gmail:
    #   MAIL_USERNAME = 'your@gmail.com'
    #   MAIL_PASSWORD = 'your-app-password'  ← NOT your real password
    #   (Generate an App Password in Google Account → Security → App Passwords)
    #
    # To use Mailtrap (recommended for dev):
    #   MAIL_SERVER   = 'sandbox.smtp.mailtrap.io'
    #   MAIL_PORT     = 2525
    #   MAIL_USERNAME = 'your-mailtrap-username'
    #   MAIL_PASSWORD = 'your-mailtrap-password'
    MAIL_SERVER               = os.environ.get('MAIL_SERVER',   'smtp.gmail.com'),
    MAIL_PORT                 = int(os.environ.get('MAIL_PORT',  587)),
    MAIL_USE_TLS              = os.environ.get('MAIL_USE_TLS',  'true').lower() == 'true',
    MAIL_USE_SSL              = os.environ.get('MAIL_USE_SSL',  'false').lower() == 'true',
    MAIL_USERNAME             = os.environ.get('MAIL_USERNAME'),
    MAIL_PASSWORD             = os.environ.get('MAIL_PASSWORD'),
    MAIL_DEFAULT_SENDER       = os.environ.get('MAIL_USERNAME'),
    BASE_URL                  = os.environ.get('BASE_URL'),
)

# ─────────────────────────────────────────────────────────────────────────────
#  EXTENSIONS
# ─────────────────────────────────────────────────────────────────────────────

CORS(app)          # Allow cross-origin requests
bcrypt  = Bcrypt(app)   # Password hashing
mail    = Mail(app)     # Email sending
jwt     = JWTManager(app)  # JWT token management

# URLSafeTimedSerializer generates signed tokens for email links.
# These tokens expire and are tamper-proof — used for email confirmation
# and password reset links.
serializer = URLSafeTimedSerializer(app.config['SECRET_KEY'])

# ─────────────────────────────────────────────────────────────────────────────
#  DATABASE MODELS
# ─────────────────────────────────────────────────────────────────────────────

class Base(DeclarativeBase):
    pass

db = SQLAlchemy(model_class=Base)
db.init_app(app)


class User(db.Model):
    """
    Represents a registered user.
    role = 'user'  → can browse and add cafés
    role = 'admin' → can also delete cafés and access admin dashboard

    NEW FIELDS (added for user profiles):
      bio        — short description
      avatar_url — profile picture URL
      location   — where the user is based
      website    — personal or portfolio link

    RELATIONSHIP:
      cafes_added — list of Cafe objects this user has added
      This is a proper SQLAlchemy one-to-many relationship with ForeignKey.
      Replaces the old manual db.session.get(User, cafe.added_by) lookups.
    """
    __tablename__ = 'user'

    id:               Mapped[int]  = mapped_column(Integer,     primary_key=True)
    name:             Mapped[str]  = mapped_column(String(250), nullable=False)
    email:            Mapped[str]  = mapped_column(String(250), nullable=False, unique=True)
    password:         Mapped[str]  = mapped_column(String(500), nullable=False)
    role:             Mapped[str]  = mapped_column(String(50),  default='user')
    is_confirmed:     Mapped[bool] = mapped_column(Boolean,     default=False)
    confirmed_at:     Mapped[str]  = mapped_column(String(50),  nullable=True)
    created_at:       Mapped[str]  = mapped_column(String(50),  default=lambda: datetime.now(timezone.utc).isoformat())

    # ── Profile fields ──────────────────────────────────────
    bio:        Mapped[str] = mapped_column(String(500), nullable=True)
    avatar_url: Mapped[str] = mapped_column(String(500), nullable=True)
    location:   Mapped[str] = mapped_column(String(250), nullable=True)
    website:    Mapped[str] = mapped_column(String(500), nullable=True)

    # ── Relationship ────────────────────────────────────────
    # One user can add MANY cafés.
    # back_populates='adder' connects to Cafe.adder below.
    # lazy='select' means SQLAlchemy fetches cafés only when you access .cafes_added
    cafes_added = relationship('Cafe', back_populates='adder', lazy='select')

    def to_dict(self):
        return {
            'id':           self.id,
            'name':         self.name,
            'email':        self.email,
            'role':         self.role,
            'is_confirmed': self.is_confirmed,
            'confirmed_at': self.confirmed_at,
            'created_at':   self.created_at,
            'bio':          self.bio,
            'avatar_url':   self.avatar_url,
            'location':     self.location,
            'website':      self.website,
        }

    def to_public_dict(self):
        """Public profile — excludes email and sensitive fields."""
        return {
            'id':           self.id,
            'name':         self.name,
            'role':         self.role,
            'is_confirmed': self.is_confirmed,
            'created_at':   self.created_at,
            'bio':          self.bio,
            'avatar_url':   self.avatar_url,
            'location':     self.location,
            'website':      self.website,
            'cafes_count':  len(self.cafes_added),
        }


class Cafe(db.Model):
    """
    Café data — matches the instructor's cafes.db table structure.

    RELATIONSHIP:
      added_by — now a proper ForeignKey to user.id (was a plain Integer)
      adder    — SQLAlchemy relationship back to the User who added this café
    """
    __tablename__ = 'cafe'

    id:             Mapped[int]  = mapped_column(Integer,     primary_key=True)
    name:           Mapped[str]  = mapped_column(String(250), nullable=False, unique=True)
    map_url:        Mapped[str]  = mapped_column(String(500), nullable=False, unique=True)
    img_url:        Mapped[str]  = mapped_column(String(500), nullable=False, unique=True)
    location:       Mapped[str]  = mapped_column(String(250), nullable=False)
    seats:          Mapped[str]  = mapped_column(String(250), nullable=True)
    has_toilet:     Mapped[bool] = mapped_column(Boolean,     nullable=False)
    has_wifi:       Mapped[bool] = mapped_column(Boolean,     nullable=False)
    has_sockets:    Mapped[bool] = mapped_column(Boolean,     nullable=False)
    can_take_calls: Mapped[bool] = mapped_column(Boolean,     nullable=False)
    coffee_price:   Mapped[str]  = mapped_column(String(250), nullable=True)

    # ── Proper ForeignKey (replaces plain Integer) ──────────
    # ForeignKey('user.id') tells SQLAlchemy this column references
    # the id column in the user table. The DB enforces referential
    # integrity — you cannot set added_by to a non-existent user id.
    added_by: Mapped[int] = mapped_column(
        Integer, ForeignKey('user.id', ondelete='SET NULL'), nullable=True
    )

    # ── Relationship ────────────────────────────────────────
    # back_populates='cafes_added' connects to User.cafes_added above.
    # Now you can do: cafe.adder.name  instead of db.session.get(User, cafe.added_by)
    adder = relationship('User', back_populates='cafes_added')

    def to_dict(self):
        d = {col.name: getattr(self, col.name) for col in self.__table__.columns}
        # Include adder's name via the relationship — no extra DB query needed
        d['added_by_name'] = self.adder.name if self.adder else None
        return d


class TokenBlocklist(db.Model):
    """
    Stores invalidated JWT tokens (logged-out tokens).
    When a user logs out, their token's JTI (unique ID) is stored here.
    On every protected request, Flask checks this list — if the token's
    JTI is here, the request is rejected even if the token hasn't expired.
    This is how logout works with stateless JWTs.
    """
    __tablename__ = 'token_blocklist'

    id:         Mapped[int] = mapped_column(Integer, primary_key=True)
    jti:        Mapped[str] = mapped_column(String(36), nullable=False, unique=True)
    created_at: Mapped[str] = mapped_column(String(50), default=lambda: datetime.now(timezone.utc).isoformat())


class Subscriber(db.Model):
    """
    Stores email addresses of newsletter subscribers.
    Anyone can subscribe — no account required.
    is_confirmed: double opt-in — subscriber must click email link to confirm.
    """
    __tablename__ = 'subscriber'

    id:           Mapped[int]  = mapped_column(Integer,     primary_key=True)
    email:        Mapped[str]  = mapped_column(String(250), nullable=False, unique=True)
    is_confirmed: Mapped[bool] = mapped_column(Boolean,     default=False)
    confirmed_at: Mapped[str]  = mapped_column(String(50),  nullable=True)
    created_at:   Mapped[str]  = mapped_column(String(50),  default=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self):
        return {
            'id':           self.id,
            'email':        self.email,
            'is_confirmed': bool(self.is_confirmed),  # SQLite stores as 0/1 — force bool
            'confirmed_at': self.confirmed_at,
            'created_at':   self.created_at,
        }


with app.app_context():
    db.create_all()

    # Create a default admin account if none exists
    # Change this email/password before deploying!
    admin = db.session.execute(
        db.select(User).where(User.role == 'admin')
    ).scalar()
    if not admin:
        db.session.add(User(
            name         = 'Admin',
            email        = 'admin@cafeatlas.com',
            password     = bcrypt.generate_password_hash('Admin1234!').decode('utf-8'),
            role         = 'admin',
            is_confirmed = True,
            confirmed_at = datetime.now(timezone.utc).isoformat(),
        ))
        db.session.commit()
        print("✅ Default admin created: admin@cafeatlas.com / Admin1234!")


# ─────────────────────────────────────────────────────────────────────────────
#  JWT CALLBACKS
# ─────────────────────────────────────────────────────────────────────────────

@jwt.token_in_blocklist_loader
def check_if_token_revoked(jwt_header, jwt_payload):
    """
    Called automatically on every @jwt_required route.
    Returns True if the token has been logged out → request is rejected.
    """
    jti    = jwt_payload['jti']
    result = db.session.execute(
        db.select(TokenBlocklist).where(TokenBlocklist.jti == jti)
    ).scalar()
    return result is not None


@jwt.expired_token_loader
def expired_token_callback(jwt_header, jwt_payload):
    return jsonify(error='Token has expired. Please log in again.'), 401


@jwt.invalid_token_loader
def invalid_token_callback(error):
    return jsonify(error='Invalid token. Please log in.'), 401


@jwt.unauthorized_loader
def missing_token_callback(error):
    return jsonify(error='No token provided. Please log in.'), 401


@jwt.revoked_token_loader
def revoked_token_callback(jwt_header, jwt_payload):
    return jsonify(error='Token has been revoked. Please log in again.'), 401


# ─────────────────────────────────────────────────────────────────────────────
#  CUSTOM DECORATORS
# ─────────────────────────────────────────────────────────────────────────────

def admin_required(fn):
    """
    Custom decorator: user must be logged in AND have role='admin'.
    Stack it BELOW @jwt_required() so JWT is verified first.

    Usage:
        @app.route('/admin/something')
        @jwt_required()
        @admin_required
        def admin_only_route():
            ...
    """
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user_id = int(get_jwt_identity())
        user    = db.session.get(User, user_id)
        if not user or user.role != 'admin':
            return jsonify(error='Admin access required.'), 403
        return fn(*args, **kwargs)
    return wrapper


def confirmed_required(fn):
    """
    Custom decorator: user must have confirmed their email.
    Unconfirmed users can log in but cannot add cafés.
    """
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user_id = int(get_jwt_identity())
        user    = db.session.get(User, user_id)
        if not user or not user.is_confirmed:
            return jsonify(
                error='Please confirm your email address before performing this action.',
                resend_url='/auth/resend-confirmation'
            ), 403
        return fn(*args, **kwargs)
    return wrapper


# ─────────────────────────────────────────────────────────────────────────────
#  EMAIL HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def send_confirmation_email(user_email, user_name):
    """
    Generates a signed token and sends a confirmation link to the user.
    The token encodes the email address and expires in 1 hour.
    """
    # Debug logging — check Render logs to verify config is loaded
    print(f"[MAIL] Sending confirmation to {user_email}")
    print(f"[MAIL] Server={app.config.get('MAIL_SERVER')} Port={app.config.get('MAIL_PORT')} User={app.config.get('MAIL_USERNAME')} BASE_URL={app.config.get('BASE_URL')}")
    token = serializer.dumps(user_email, salt='email-confirm')
    link  = f"http://localhost:5000/auth/confirm/{token}"

    msg = Message(
        subject    = '☕ Confirm your Café Atlas account',
        recipients = [user_email],
        html       = f"""
        <div style="font-family:sans-serif;max-width:480px;margin:auto;padding:32px">
          <h2 style="color:#2b1a0e">Welcome to Café Atlas, {user_name}!</h2>
          <p>Please confirm your email address by clicking the button below.
             This link expires in <strong>1 hour</strong>.</p>
          <a href="{link}"
             style="display:inline-block;background:#c0854a;color:#fff;
                    padding:12px 28px;border-radius:8px;text-decoration:none;
                    font-weight:600;margin:16px 0">
            Confirm My Email
          </a>
          <p style="color:#8a7060;font-size:.85rem">
            If you didn't create an account, you can safely ignore this email.
          </p>
        </div>
        """
    )
    mail.send(msg)


def send_password_reset_email(user_email, user_name):
    """
    Generates a signed token and sends a password reset link.
    Uses a different salt to 'email-confirm' so tokens can't be
    cross-used between flows.
    """
    token = serializer.dumps(user_email, salt='password-reset')
    link  = f"http://localhost:5000/auth/reset-password/{token}"

    msg = Message(
        subject    = '☕ Reset your Café Atlas password',
        recipients = [user_email],
        html       = f"""
        <div style="font-family:sans-serif;max-width:480px;margin:auto;padding:32px">
          <h2 style="color:#2b1a0e">Password Reset Request</h2>
          <p>Hi {user_name}, we received a request to reset your password.
             Click below to set a new password. This link expires in <strong>30 minutes</strong>.</p>
          <a href="{link}"
             style="display:inline-block;background:#c0854a;color:#fff;
                    padding:12px 28px;border-radius:8px;text-decoration:none;
                    font-weight:600;margin:16px 0">
            Reset My Password
          </a>
          <p style="color:#8a7060;font-size:.85rem">
            If you didn't request this, you can safely ignore this email.
            Your password will not change.
          </p>
        </div>
        """
    )
    mail.send(msg)


# ─────────────────────────────────────────────────────────────────────────────
#  FRONTEND ROUTES  —  serve HTML pages
# ─────────────────────────────────────────────────────────────────────────────

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/login')
def login_page():
    return render_template('login.html')

@app.route('/register')
def register_page():
    return render_template('register.html')

@app.route('/forgot-password')
def forgot_password_page():
    return render_template('forgot_password.html')

@app.route('/reset-password-page')
def reset_password_page():
    """
    This page is loaded when the user clicks the reset link in their email.
    The token is passed as a query param: /reset-password-page?token=abc123
    The page reads the token from the URL and submits it with the new password.
    """
    return render_template('reset_password.html')

@app.route('/admin')
def admin_page():
    return render_template('admin.html')

# ─────────────────────────────────────────────────────────────────────────────
#  AUTH ROUTES  —  all return JSON
# ─────────────────────────────────────────────────────────────────────────────

@app.route('/auth/register', methods=['POST'])
def register():
    """
    Register a new user.
    Body: { "name": "...", "email": "...", "password": "..." }

    Flow:
      1. Validate input
      2. Check email not already taken
      3. Hash the password (NEVER store plain text)
      4. Save user to DB (is_confirmed=False)
      5. Send confirmation email
      6. Return success — user must confirm email before full access
    """
    data = request.get_json()
    if not data:
        return jsonify(error='Request body must be JSON.'), 400

    name     = data.get('name', '').strip()
    email    = data.get('email', '').strip().lower()
    password = data.get('password', '')

    if not name or not email or not password:
        return jsonify(error='Name, email and password are required.'), 400

    if len(password) < 8:
        return jsonify(error='Password must be at least 8 characters.'), 400

    # Check if email already registered
    existing = db.session.execute(
        db.select(User).where(User.email == email)
    ).scalar()
    if existing:
        return jsonify(error='An account with this email already exists.'), 409

    # Hash the password — bcrypt is one-way, never reversible
    hashed_pw = bcrypt.generate_password_hash(password).decode('utf-8')

    new_user = User(name=name, email=email, password=hashed_pw)
    db.session.add(new_user)
    db.session.commit()

    # Send confirmation email
    try:
        send_confirmation_email(email, name)
    except Exception as e:
        print(f"Email error: {e}")
        # Don't fail the registration if email fails — just warn
        return jsonify(
            success='Account created! (Email sending failed — check MAIL config.)',
            warning='Could not send confirmation email.'
        ), 201

    return jsonify(
        success='Account created! Please check your email to confirm your account.',
    ), 201


@app.route('/auth/confirm/<token>', methods=['GET'])
def confirm_email(token):
    """
    Called when the user clicks the confirmation link in their email.
    The token is decoded and verified — if valid and not expired,
    the user's is_confirmed flag is set to True.
    """
    try:
        # max_age=3600 = token expires after 1 hour
        email = serializer.loads(token, salt='email-confirm', max_age=3600)
    except SignatureExpired:
        return render_template('confirm_result.html',
                               success=False,
                               message='Confirmation link has expired. Please request a new one.')
    except BadSignature:
        return render_template('confirm_result.html',
                               success=False,
                               message='Invalid confirmation link.')

    user = db.session.execute(
        db.select(User).where(User.email == email)
    ).scalar()

    if not user:
        return render_template('confirm_result.html',
                               success=False,
                               message='Account not found.')

    if user.is_confirmed:
        return render_template('confirm_result.html',
                               success=True,
                               message='Your email is already confirmed. Please log in.')

    user.is_confirmed = True
    user.confirmed_at = datetime.now(timezone.utc).isoformat()
    db.session.commit()

    return render_template('confirm_result.html',
                           success=True,
                           message='Email confirmed! Your account is now active. Please log in.')


@app.route('/auth/resend-confirmation', methods=['POST'])
def resend_confirmation():
    """
    Resend the confirmation email.
    Body: { "email": "..." }
    Used when a user hasn't confirmed yet and needs a new link.
    """
    data  = request.get_json()
    email = data.get('email', '').strip().lower()

    user = db.session.execute(
        db.select(User).where(User.email == email)
    ).scalar()

    # Always return success even if email not found (security — don't reveal)
    if user and not user.is_confirmed:
        try:
            send_confirmation_email(user.email, user.name)
        except Exception as e:
            print(f"Email error: {e}")

    return jsonify(success='If that email exists and is unconfirmed, a new link has been sent.'), 200


@app.route('/auth/login', methods=['POST'])
def login():
    """
    Log in and receive a JWT token.
    Body: { "email": "...", "password": "..." }

    Flow:
      1. Find user by email
      2. Check password with bcrypt
      3. Generate a JWT token containing the user's ID
      4. Return the token — frontend stores it and sends it on future requests

    The token payload (additional_claims) includes the user's role
    so the frontend can show/hide admin features without an extra API call.
    """
    data  = request.get_json()
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')

    user = db.session.execute(
        db.select(User).where(User.email == email)
    ).scalar()

    # Check user exists AND password matches
    if not user or not bcrypt.check_password_hash(user.password, password):
        return jsonify(error='Invalid email or password.'), 401

    # Generate JWT — identity is the user's ID (integer)
    # additional_claims adds role and name directly into the token payload
    token = create_access_token(
        identity=str(user.id),
        additional_claims={
            'role':         user.role,
            'name':         user.name,
            'is_confirmed': user.is_confirmed,
        }
    )

    return jsonify(
        token        = token,
        user         = user.to_dict(),
        is_confirmed = user.is_confirmed,
        message      = 'Login successful.' if user.is_confirmed
                       else 'Logged in, but please confirm your email for full access.'
    ), 200


@app.route('/auth/logout', methods=['DELETE'])
@jwt_required()
def logout():
    """
    Logout by adding the token's JTI to the blocklist.
    After this, the token is permanently invalid even if it hasn't expired.
    """
    jti = get_jwt()['jti']
    db.session.add(TokenBlocklist(jti=jti))
    db.session.commit()
    return jsonify(success='Logged out successfully.'), 200


@app.route('/auth/me', methods=['GET'])
@jwt_required()
def get_current_user():
    """
    Returns the currently logged-in user's profile.
    Useful for the frontend to check who is logged in on page load.
    """
    user_id = int(get_jwt_identity())
    user    = db.session.get(User, user_id)
    if not user:
        return jsonify(error='User not found.'), 404
    return jsonify(user=user.to_dict()), 200


@app.route('/auth/forgot-password', methods=['POST'])
def forgot_password():
    """
    Sends a password reset email.
    Body: { "email": "..." }
    Always returns success (never reveal if email exists — security best practice).
    """
    data  = request.get_json()
    email = data.get('email', '').strip().lower()

    user = db.session.execute(
        db.select(User).where(User.email == email)
    ).scalar()

    if user:
        try:
            send_password_reset_email(user.email, user.name)
        except Exception as e:
            print(f"Email error: {e}")

    return jsonify(
        success='If an account with that email exists, a reset link has been sent.'
    ), 200


@app.route('/auth/reset-password/<token>', methods=['POST'])
def reset_password(token):
    """
    Reset the password using the signed token from the email link.
    Body: { "password": "newpassword" }

    The token is verified (max_age=1800 = 30 minutes).
    If valid, the user's password is updated in the DB.
    """
    try:
        email = serializer.loads(token, salt='password-reset', max_age=1800)
    except SignatureExpired:
        return jsonify(error='Reset link has expired. Please request a new one.'), 400
    except BadSignature:
        return jsonify(error='Invalid reset link.'), 400

    data        = request.get_json()
    new_password = data.get('password', '')

    if len(new_password) < 8:
        return jsonify(error='Password must be at least 8 characters.'), 400

    user = db.session.execute(
        db.select(User).where(User.email == email)
    ).scalar()

    if not user:
        return jsonify(error='Account not found.'), 404

    user.password = bcrypt.generate_password_hash(new_password).decode('utf-8')
    db.session.commit()

    return jsonify(success='Password reset successfully. You can now log in.'), 200


# ─────────────────────────────────────────────────────────────────────────────
#  CAFÉ API ROUTES
# ─────────────────────────────────────────────────────────────────────────────

DEFAULT_IMG = 'https://images.unsplash.com/photo-1501339847302-ac426a4a7cbb?w=400'

def cafe_not_found(cafe_id):
    return jsonify(error=f'Café with id={cafe_id} not found.'), 404


# ── GET /cafes/random  (must be before /cafes/<id>) ──────────────────────────
@app.route('/cafes/random', methods=['GET'])
def get_random_cafe():
    cafes = db.session.execute(db.select(Cafe)).scalars().all()
    if not cafes:
        return jsonify(error='No cafés in the database.'), 404
    return jsonify(cafe=random.choice(cafes).to_dict()), 200


# ── GET /cafes/search  (must be before /cafes/<id>) ──────────────────────────
@app.route('/cafes/search', methods=['GET'])
def search_cafes():
    location = request.args.get('location')
    if not location:
        return jsonify(error='Provide a ?location= query parameter.'), 400
    cafes = db.session.execute(
        db.select(Cafe).where(Cafe.location.ilike(f'%{location}%'))
    ).scalars().all()
    if not cafes:
        return jsonify(error=f"No cafés found in '{location}'."), 404
    return jsonify(cafes=[c.to_dict() for c in cafes]), 200


# ── GET /cafes ────────────────────────────────────────────────────────────────
@app.route('/cafes', methods=['GET'])
def get_all_cafes():
    """
    Public route — anyone can view cafés (no login required).
    Supports pagination via ?page= and ?per_page= query params.

    Query params:
      ?page=1          — which page to return (default: 1)
      ?per_page=9      — how many cafés per page (default: 9, max: 50)
      ?location=X      — filter by location (optional)

    Response includes pagination metadata:
    {
      "cafes":       [...],
      "total":       42,       <- total cafés matching the filter
      "page":        1,        <- current page
      "per_page":    9,        <- items per page
      "total_pages": 5,        <- total number of pages
      "has_next":    true,     <- is there a next page?
      "has_prev":    false     <- is there a previous page?
    }
    """
    # Read pagination params from the URL query string
    page     = request.args.get('page',     1,  type=int)
    per_page = request.args.get('per_page', 9,  type=int)
    location = request.args.get('location', '', type=str).strip()

    # Clamp per_page to a safe range — never let a client request 10,000 rows
    per_page = min(max(per_page, 1), 50)
    page     = max(page, 1)

    # Build the base query
    query = db.select(Cafe)
    if location:
        query = query.where(Cafe.location.ilike(f'%{location}%'))

    # Count total BEFORE applying pagination (needed for total_pages)
    total = db.session.execute(
        db.select(db.func.count()).select_from(query.subquery())
    ).scalar()

    # Apply pagination: OFFSET skips rows, LIMIT takes only per_page rows
    # e.g. page=2, per_page=9 → OFFSET 9 LIMIT 9
    cafes = db.session.execute(
        query.offset((page - 1) * per_page).limit(per_page)
    ).scalars().all()

    total_pages = max(1, -(-total // per_page))  # ceiling division

    return jsonify(
        cafes       = [c.to_dict() for c in cafes],
        total       = total,
        page        = page,
        per_page    = per_page,
        total_pages = total_pages,
        has_next    = page < total_pages,
        has_prev    = page > 1,
    ), 200


# ── GET /cafes/<id> ───────────────────────────────────────────────────────────
@app.route('/cafes/<int:cafe_id>', methods=['GET'])
def get_cafe(cafe_id):
    """Public route — anyone can view a single café."""
    cafe = db.session.get(Cafe, cafe_id)
    if not cafe:
        return cafe_not_found(cafe_id)
    return jsonify(cafe=cafe.to_dict()), 200


# ── POST /cafes ───────────────────────────────────────────────────────────────
@app.route('/cafes', methods=['POST'])
@jwt_required()          # must be logged in
@confirmed_required      # must have confirmed email
def add_cafe():
    """
    Add a new café. Requires login + confirmed email.
    Records which user added the café via added_by.
    """
    data = request.get_json()
    if not data:
        return jsonify(error='Request body must be JSON.'), 400

    required = ['name', 'map_url', 'img_url', 'location',
                'has_wifi', 'has_sockets', 'has_toilet', 'can_take_calls']
    missing = [f for f in required if f not in data]
    if missing:
        return jsonify(error=f'Missing fields: {missing}'), 400

    existing = db.session.execute(
        db.select(Cafe).where(Cafe.name == data['name'])
    ).scalar()
    if existing:
        return jsonify(error=f"'{data['name']}' already exists."), 409

    user_id  = int(get_jwt_identity())
    new_cafe = Cafe(
        name           = data['name'],
        map_url        = data['map_url'],
        img_url        = data['img_url'] or DEFAULT_IMG,
        location       = data['location'],
        seats          = data.get('seats', 'Unknown'),
        has_wifi       = bool(data['has_wifi']),
        has_sockets    = bool(data['has_sockets']),
        has_toilet     = bool(data['has_toilet']),
        can_take_calls = bool(data['can_take_calls']),
        coffee_price   = data.get('coffee_price', 'N/A'),
        added_by       = user_id,
    )
    db.session.add(new_cafe)
    db.session.commit()

    return jsonify(
        success = f"'{new_cafe.name}' added!",
        id      = new_cafe.id,
        cafe    = new_cafe.to_dict()
    ), 201


# ── PATCH /cafes/<id>/price ───────────────────────────────────────────────────
@app.route('/cafes/<int:cafe_id>/price', methods=['PATCH'])
@jwt_required()
@confirmed_required
def update_price(cafe_id):
    """Update coffee price. Requires login + confirmed email."""
    cafe = db.session.get(Cafe, cafe_id)
    if not cafe:
        return cafe_not_found(cafe_id)

    data = request.get_json()
    if not data or 'coffee_price' not in data:
        return jsonify(error="Provide {'coffee_price': '£X.XX'} in body."), 400

    cafe.coffee_price = data['coffee_price']
    db.session.commit()

    return jsonify(success=f"Price updated for '{cafe.name}'.", cafe=cafe.to_dict()), 200


# ── DELETE /cafes/<id> ────────────────────────────────────────────────────────
@app.route('/cafes/<int:cafe_id>', methods=['DELETE'])
@jwt_required()
@admin_required          # only admins can delete
def delete_cafe(cafe_id):
    """Delete a café. Admin only."""
    cafe = db.session.get(Cafe, cafe_id)
    if not cafe:
        return cafe_not_found(cafe_id)

    name = cafe.name
    db.session.delete(cafe)
    db.session.commit()

    return jsonify(success=f"'{name}' has been deleted."), 200


# ─────────────────────────────────────────────────────────────────────────────
#  ADMIN API ROUTES
# ─────────────────────────────────────────────────────────────────────────────

@app.route('/admin/cafes', methods=['GET'])
@jwt_required()
@admin_required
def get_all_cafes_admin():
    """
    Admin-only enriched café list.
    Joins added_by (user ID) with the User table to return the adder's name.
    The public GET /cafes only returns raw data including added_by as an integer.
    This route replaces that integer with a human-readable name for the dashboard.
    """
    cafes = db.session.execute(db.select(Cafe)).scalars().all()

    # to_dict() now includes added_by_name via the relationship
    return jsonify(cafes=[c.to_dict() for c in cafes]), 200


@app.route('/admin/users', methods=['GET'])
@jwt_required()
@admin_required
def get_all_users():
    """Admin only — get all registered users."""
    users = db.session.execute(db.select(User)).scalars().all()
    return jsonify(users=[u.to_dict() for u in users]), 200


@app.route('/admin/users/<int:user_id>/role', methods=['PATCH'])
@jwt_required()
@admin_required
def update_user_role(user_id):
    """
    Admin only — promote or demote a user.
    Body: { "role": "admin" }  or  { "role": "user" }
    """
    user = db.session.get(User, user_id)
    if not user:
        return jsonify(error='User not found.'), 404

    data = request.get_json()
    role = data.get('role')
    if role not in ('user', 'admin'):
        return jsonify(error="Role must be 'user' or 'admin'."), 400

    user.role = role
    db.session.commit()

    return jsonify(
        success=f"{user.name}'s role updated to '{role}'.",
        user=user.to_dict()
    ), 200


@app.route('/admin/users/<int:user_id>', methods=['DELETE'])
@jwt_required()
@admin_required
def delete_user(user_id):
    """Admin only — delete a user account."""
    user = db.session.get(User, user_id)
    if not user:
        return jsonify(error='User not found.'), 404

    # Prevent admin from deleting themselves
    current_admin_id = int(get_jwt_identity())
    if user_id == current_admin_id:
        return jsonify(error='You cannot delete your own account.'), 400

    name = user.name
    db.session.delete(user)
    db.session.commit()

    return jsonify(success=f"User '{name}' deleted."), 200


@app.route('/admin/stats', methods=['GET'])
@jwt_required()
@admin_required
def get_stats():
    """Admin dashboard stats."""
    total_cafes    = db.session.execute(db.select(Cafe)).scalars().all()
    total_users    = db.session.execute(db.select(User)).scalars().all()
    confirmed      = [u for u in total_users if u.is_confirmed]
    wifi_cafes     = [c for c in total_cafes if c.has_wifi]
    socket_cafes   = [c for c in total_cafes if c.has_sockets]

    return jsonify(
        total_cafes    = len(total_cafes),
        total_users    = len(total_users),
        confirmed_users= len(confirmed),
        wifi_cafes     = len(wifi_cafes),
        socket_cafes   = len(socket_cafes),
    ), 200




# ─────────────────────────────────────────────────────────────────────────────
#  NEWSLETTER / SUBSCRIBER ROUTES
# ─────────────────────────────────────────────────────────────────────────────

@app.route('/newsletter/subscribe', methods=['POST'])
def newsletter_subscribe():
    """
    Subscribe to the newsletter.
    Body: { "email": "..." }

    Uses double opt-in — sends a confirmation email before adding to the list.
    This prevents people from subscribing others without their consent.
    """
    data  = request.get_json()
    email = data.get('email', '').strip().lower()

    if not email or '@' not in email:
        return jsonify(error='Please provide a valid email address.'), 400

    # Check if already subscribed
    existing = db.session.execute(
        db.select(Subscriber).where(Subscriber.email == email)
    ).scalar()

    if existing and existing.is_confirmed:
        return jsonify(message='This email is already subscribed.'), 200

    if not existing:
        new_sub = Subscriber(
            email        = email,
            is_confirmed = False,  # explicit — don't rely on DB default
            created_at   = datetime.now(timezone.utc).isoformat()
        )
        db.session.add(new_sub)
        db.session.commit()

    # Send confirmation email
    try:
        token = serializer.dumps(email, salt='newsletter-confirm')
        link  = f"{app.config['BASE_URL']}/newsletter/confirm/{token}"

        msg = Message(
            subject    = '☕ Confirm your Café Atlas subscription',
            recipients = [email],
            html       = f"""
            <div style="font-family:sans-serif;max-width:480px;margin:auto;padding:32px">
              <h2 style="color:#2b1a0e">Almost there!</h2>
              <p>Click the button below to confirm your subscription to Café Atlas updates.
                 You'll be notified when new cafés are added.</p>
              <a href="{link}"
                 style="display:inline-block;background:#c0854a;color:#fff;
                        padding:12px 28px;border-radius:8px;text-decoration:none;
                        font-weight:600;margin:16px 0">
                Confirm Subscription
              </a>
              <p style="color:#8a7060;font-size:.85rem">
                If you didn't request this, ignore this email.
              </p>
            </div>"""
        )
        mail.send(msg)
    except Exception as e:
        print(f"Newsletter email error: {e}")
        return jsonify(
            success='Subscribed! (Email sending failed — check MAIL config.)',
            warning='Could not send confirmation email.'
        ), 201

    return jsonify(
        success='Thanks! Please check your email to confirm your subscription.'
    ), 201


@app.route('/newsletter/confirm/<token>', methods=['GET'])
def newsletter_confirm(token):
    """
    Confirms a newsletter subscription via the signed token in the email link.
    """
    try:
        email = serializer.loads(token, salt='newsletter-confirm', max_age=86400)  # 24h
    except SignatureExpired:
        return render_template('confirm_result.html',
                               success=False,
                               message='Subscription link has expired. Please subscribe again.')
    except BadSignature:
        return render_template('confirm_result.html',
                               success=False,
                               message='Invalid subscription link.')

    sub = db.session.execute(
        db.select(Subscriber).where(Subscriber.email == email)
    ).scalar()

    if not sub:
        return render_template('confirm_result.html',
                               success=False,
                               message='Subscription not found.')

    sub.is_confirmed = True
    sub.confirmed_at = datetime.now(timezone.utc).isoformat()
    db.session.commit()

    return render_template('confirm_result.html',
                           success=True,
                           message="You're subscribed! You'll be notified when new cafés are added.")


@app.route('/newsletter/unsubscribe/<token>', methods=['GET'])
def newsletter_unsubscribe(token):
    """
    Unsubscribe using a signed token (sent in every notification email).
    One-click unsubscribe — no login required.
    """
    try:
        email = serializer.loads(token, salt='newsletter-unsub', max_age=None)  # never expires
    except BadSignature:
        return render_template('confirm_result.html',
                               success=False,
                               message='Invalid unsubscribe link.')

    sub = db.session.execute(
        db.select(Subscriber).where(Subscriber.email == email)
    ).scalar()

    if sub:
        db.session.delete(sub)
        db.session.commit()

    return render_template('confirm_result.html',
                           success=True,
                           message='You have been unsubscribed. Sorry to see you go!')


@app.route('/admin/newsletter/notify', methods=['POST'])
@jwt_required()
@admin_required
def send_newsletter_notification():
    """
    Admin only — send a notification email to all confirmed subscribers.

    Two modes:
      1. notify_new_cafes=true  → auto-builds an email of recently added cafés
      2. custom subject + body  → admin writes a custom message

    Body:
    {
        "notify_new_cafes": true,
        "subject": "Custom subject (optional)",
        "body":    "Custom HTML body (optional)"
    }
    """
    data = request.get_json()

    # Fetch all confirmed subscribers
    subscribers = db.session.execute(
        db.select(Subscriber).where(Subscriber.is_confirmed == True)
    ).scalars().all()

    if not subscribers:
        return jsonify(error='No confirmed subscribers found.'), 404

    notify_new = data.get('notify_new_cafes', False)
    sent_count = 0
    errors     = []

    if notify_new:
        # Get cafés added in the last 7 days
        from datetime import timedelta
        week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
        new_cafes = db.session.execute(
            db.select(Cafe).where(Cafe.added_by.isnot(None))
        ).scalars().all()

        if not new_cafes:
            return jsonify(error='No new cafés to notify about.'), 400

        cafe_cards = ''.join([f"""
            <div style="border:1px solid #ede5d4;border-radius:12px;padding:16px;margin-bottom:12px">
              <h3 style="color:#2b1a0e;margin:0 0 4px">{c.name}</h3>
              <p style="color:#8a7060;margin:0 0 8px;font-size:.9rem">
                📍 {c.location}
                {'· 📶 WiFi' if c.has_wifi else ''}
                {'· 🔌 Sockets' if c.has_sockets else ''}
              </p>
              {f'<p style="color:#c0854a;font-weight:600;margin:0">{c.coffee_price}</p>' if c.coffee_price else ''}
            </div>
        """ for c in new_cafes[:5]])  # limit to 5 cafés per email

        subject = f"☕ {len(new_cafes)} New Café{'s' if len(new_cafes)>1 else ''} on Café Atlas!"

        for sub in subscribers:
            try:
                unsub_token = serializer.dumps(sub.email, salt='newsletter-unsub')
                unsub_link  = f"{app.config['BASE_URL']}/newsletter/unsubscribe/{unsub_token}"

                msg = Message(
                    subject    = subject,
                    recipients = [sub.email],
                    html       = f"""
                    <div style="font-family:sans-serif;max-width:560px;margin:auto;padding:32px">
                      <h2 style="color:#2b1a0e">New cafés just added! ☕</h2>
                      <p style="color:#5c3317">Here are the latest spots added to Café Atlas:</p>
                      {cafe_cards}
                      <a href="{app.config['BASE_URL']}"
                         style="display:inline-block;background:#c0854a;color:#fff;
                                padding:12px 28px;border-radius:8px;text-decoration:none;
                                font-weight:600;margin:16px 0">
                        View All Cafés →
                      </a>
                      <hr style="border-color:#ede5d4;margin:24px 0"/>
                      <p style="color:#8a7060;font-size:.78rem">
                        You're receiving this because you subscribed to Café Atlas updates.
                        <a href="{unsub_link}" style="color:#c0854a">Unsubscribe</a>
                      </p>
                    </div>"""
                )
                mail.send(msg)
                sent_count += 1
            except Exception as e:
                errors.append(sub.email)
                print(f"Failed to send to {sub.email}: {e}")

    else:
        # Custom message
        subject = data.get('subject', '☕ Update from Café Atlas')
        body    = data.get('body',    '<p>Hello from Café Atlas!</p>')

        for sub in subscribers:
            try:
                unsub_token = serializer.dumps(sub.email, salt='newsletter-unsub')
                unsub_link  = f"{app.config['BASE_URL']}/newsletter/unsubscribe/{unsub_token}"

                msg = Message(
                    subject    = subject,
                    recipients = [sub.email],
                    html       = f"""
                    <div style="font-family:sans-serif;max-width:560px;margin:auto;padding:32px">
                      {body}
                      <hr style="border-color:#ede5d4;margin:24px 0"/>
                      <p style="color:#8a7060;font-size:.78rem">
                        You're receiving this because you subscribed to Café Atlas updates.
                        <a href="{unsub_link}" style="color:#c0854a">Unsubscribe</a>
                      </p>
                    </div>"""
                )
                mail.send(msg)
                sent_count += 1
            except Exception as e:
                errors.append(sub.email)

    return jsonify(
        success      = f"Notification sent to {sent_count} subscriber(s).",
        sent         = sent_count,
        failed       = len(errors),
        failed_emails= errors
    ), 200


@app.route('/admin/newsletter/subscribers', methods=['GET'])
@jwt_required()
@admin_required
def get_subscribers():
    """Admin only — list all subscribers with their confirmation status."""
    subscribers = db.session.execute(
        db.select(Subscriber).order_by(Subscriber.created_at.desc())
    ).scalars().all()

    confirmed   = [s for s in subscribers if bool(s.is_confirmed)]
    unconfirmed = [s for s in subscribers if not bool(s.is_confirmed)]

    print(f"DEBUG subscribers: total={len(subscribers)}, confirmed={len(confirmed)}")

    return jsonify(
        total       = len(subscribers),
        confirmed   = len(confirmed),
        unconfirmed = len(unconfirmed),
        subscribers = [s.to_dict() for s in subscribers]
    ), 200

# ─────────────────────────────────────────────────────────────────────────────
#  PROFILE ROUTES
# ─────────────────────────────────────────────────────────────────────────────

@app.route('/profile')
def profile_page():
    """Serves the user profile page (frontend handles the rest via JS + API)."""
    return render_template('profile.html')


@app.route('/api/profile', methods=['GET'])
@jwt_required()
def get_own_profile():
    """
    Returns the logged-in user's full profile including their added cafés.
    Uses the relationship: user.cafes_added loads all linked cafés automatically.
    """
    user_id = int(get_jwt_identity())
    user    = db.session.get(User, user_id)
    if not user:
        return jsonify(error='User not found.'), 404

    # user.cafes_added uses the SQLAlchemy relationship —
    # no manual loop or extra query needed
    return jsonify(
        user  = user.to_dict(),
        cafes = [c.to_dict() for c in user.cafes_added]
    ), 200


@app.route('/api/profile', methods=['PATCH'])
@jwt_required()
def update_profile():
    """
    Update the logged-in user's profile fields.
    Only allows updating: name, bio, avatar_url, location, website.
    Email and password have separate routes for security.

    Body (all fields optional — only send what you want to change):
    {
        "name":       "New Name",
        "bio":        "I love finding hidden café gems...",
        "avatar_url": "https://...",
        "location":   "Lagos, Nigeria",
        "website":    "https://mysite.com"
    }
    """
    user_id = int(get_jwt_identity())
    user    = db.session.get(User, user_id)
    if not user:
        return jsonify(error='User not found.'), 404

    data = request.get_json()
    if not data:
        return jsonify(error='Request body must be JSON.'), 400

    # Only update allowed fields — never let users update role, password, etc.
    allowed = ['name', 'bio', 'avatar_url', 'location', 'website']
    updated = []

    for field in allowed:
        if field in data:
            value = data[field].strip() if isinstance(data[field], str) else data[field]
            setattr(user, field, value or None)  # empty string → None
            updated.append(field)

    if not updated:
        return jsonify(error='No valid fields to update.'), 400

    db.session.commit()

    return jsonify(
        success = f"Profile updated: {', '.join(updated)}.",
        user    = user.to_dict()
    ), 200


@app.route('/api/profile/password', methods=['PATCH'])
@jwt_required()
def change_password():
    """
    Change the logged-in user's password.
    Requires the current password for verification.

    Body: { "current_password": "...", "new_password": "..." }
    """
    user_id = int(get_jwt_identity())
    user    = db.session.get(User, user_id)
    if not user:
        return jsonify(error='User not found.'), 404

    data             = request.get_json()
    current_password = data.get('current_password', '')
    new_password     = data.get('new_password', '')

    # Verify current password before allowing change
    if not bcrypt.check_password_hash(user.password, current_password):
        return jsonify(error='Current password is incorrect.'), 401

    if len(new_password) < 8:
        return jsonify(error='New password must be at least 8 characters.'), 400

    if current_password == new_password:
        return jsonify(error='New password must be different from current password.'), 400

    user.password = bcrypt.generate_password_hash(new_password).decode('utf-8')
    db.session.commit()

    return jsonify(success='Password changed successfully.'), 200


@app.route('/api/profile/public/<int:user_id>', methods=['GET'])
def get_public_profile(user_id):
    """
    Public profile — anyone can view.
    Returns safe fields only (no email) plus the cafés this user added.
    """
    user = db.session.get(User, user_id)
    if not user:
        return jsonify(error='User not found.'), 404

    return jsonify(
        user  = user.to_public_dict(),
        cafes = [c.to_dict() for c in user.cafes_added]
    ), 200

# ─────────────────────────────────────────────────────────────────────────────
#  RUN
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    app.run(debug=True, port=5000)
