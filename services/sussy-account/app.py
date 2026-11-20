"""Self-hostable Sussy Account API.

This is an authentication/profile/device service, not a hosted OpenAI account.
Production deployments must set a random secret, HTTPS reverse proxy and SMTP.
"""
from __future__ import annotations

from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import parseaddr
import hashlib
import hmac
import os
import re
import secrets
import smtplib
import sqlite3
import ssl
from typing import Generator

import jwt
from argon2 import PasswordHasher, exceptions as argon2_exceptions
from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
from pydantic import BaseModel, Field

APP_NAME = "Sussy Account"
ISSUER = "sussy-account"
AUDIENCE = "sussy-baka-os"
TOKEN_TTL_MINUTES = 15
REFRESH_TTL_DAYS = 30
VERIFY_TTL_HOURS = 24
RESET_TTL_MINUTES = 30
COLORS = {"red", "cyan", "purple", "yellow", "pink", "green", "blue", "black", "white"}
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{3,32}$")
PASSWORD_HASHER = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def ts(value: datetime | None = None) -> str:
    return (value or utcnow()).isoformat()


def parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value)


def setting(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def database_path() -> str:
    return setting("SUSSY_ACCOUNT_DB", "/var/lib/sussy-account/accounts.sqlite3")


def secret_key() -> str:
    key = setting("SUSSY_ACCOUNT_SECRET")
    if len(key.encode("utf-8")) < 32:
        raise RuntimeError("SUSSY_ACCOUNT_SECRET must contain at least 32 characters")
    return key


@contextmanager
def db_conn(path: str | None = None) -> Generator[sqlite3.Connection, None, None]:
    db_path = path or database_path()
    if db_path != ":memory:":
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), mode=0o700, exist_ok=True)
    previous_umask = os.umask(0o077)
    try:
        conn = sqlite3.connect(db_path, timeout=15)
    finally:
        os.umask(previous_umask)
    if db_path != ":memory:":
        os.chmod(db_path, 0o600)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def initialize_database(path: str | None = None) -> None:
    with db_conn(path) as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS accounts (
            id TEXT PRIMARY KEY,
            username TEXT NOT NULL COLLATE NOCASE UNIQUE,
            email TEXT NOT NULL COLLATE NOCASE UNIQUE,
            display_name TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            email_verified INTEGER NOT NULL DEFAULT 0,
            verify_hash TEXT,
            verify_expires TEXT,
            reset_hash TEXT,
            reset_expires TEXT,
            crewmate_color TEXT NOT NULL DEFAULT 'red',
            avatar_url TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
            refresh_hash TEXT NOT NULL UNIQUE,
            device_name TEXT NOT NULL,
            created_at TEXT NOT NULL,
            last_used_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            revoked_at TEXT
        );
        CREATE TABLE IF NOT EXISTS rate_limits (
            bucket TEXT PRIMARY KEY,
            count INTEGER NOT NULL,
            window_start TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_sessions_account ON sessions(account_id);
        """)


def token_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def rate_bucket(key: str) -> str:
    return hmac.new(secret_key().encode(), key.encode(), hashlib.sha256).hexdigest()


def allow_attempt(key: str, limit: int = 8, minutes: int = 15) -> bool:
    now = utcnow()
    bucket = rate_bucket(key)
    with db_conn() as db:
        row = db.execute("SELECT count, window_start FROM rate_limits WHERE bucket=?", (bucket,)).fetchone()
        if row is None or now - parse_ts(row["window_start"]) >= timedelta(minutes=minutes):
            db.execute("INSERT OR REPLACE INTO rate_limits(bucket,count,window_start) VALUES(?,?,?)", (bucket, 1, ts(now)))
            return True
        if row["count"] >= limit:
            return False
        db.execute("UPDATE rate_limits SET count=count+1 WHERE bucket=?", (bucket,))
        return True


def smtp_configured() -> bool:
    return bool(setting("SMTP_HOST") and setting("SMTP_FROM"))


def send_email(recipient: str, subject: str, body: str) -> None:
    host, sender = setting("SMTP_HOST"), setting("SMTP_FROM")
    if not host or not sender:
        raise RuntimeError("SMTP_HOST and SMTP_FROM are required to send account emails")
    message = EmailMessage()
    message["From"] = sender
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(body)
    port = int(setting("SMTP_PORT", "587"))
    username, password = setting("SMTP_USER"), setting("SMTP_PASSWORD")
    timeout = 15
    if setting("SMTP_SSL", "false").lower() == "true":
        with smtplib.SMTP_SSL(host, port, timeout=timeout, context=ssl.create_default_context()) as smtp:
            if username: smtp.login(username, password)
            smtp.send_message(message)
    else:
        with smtplib.SMTP(host, port, timeout=timeout) as smtp:
            smtp.ehlo(); smtp.starttls(context=ssl.create_default_context()); smtp.ehlo()
            if username: smtp.login(username, password)
            smtp.send_message(message)


def send_or_dev(recipient: str, subject: str, body: str, token: str) -> str | None:
    if smtp_configured():
        send_email(recipient, subject, body)
        return None
    if setting("SUSSY_ACCOUNT_DEV_MODE", "false").lower() == "true":
        return token
    raise HTTPException(503, "Account email delivery is not configured. Set SMTP_HOST/SMTP_FROM or enable development mode only for local testing.")


def access_token(account_id: str) -> str:
    now = utcnow()
    payload = {"sub": account_id, "iss": ISSUER, "aud": AUDIENCE,
               "iat": now, "exp": now + timedelta(minutes=TOKEN_TTL_MINUTES),
               "jti": secrets.token_urlsafe(12)}
    return jwt.encode(payload, secret_key(), algorithm="HS256")


def refresh_pair(account_id: str, device_name: str, session_id: str | None = None) -> dict:
    raw_refresh = secrets.token_urlsafe(48)
    sid = session_id or secrets.token_urlsafe(18)
    now = utcnow()
    with db_conn() as db:
        db.execute("""INSERT INTO sessions(id,account_id,refresh_hash,device_name,created_at,last_used_at,expires_at,revoked_at)
                      VALUES(?,?,?,?,?,?,?,NULL)""", (sid, account_id, token_hash(raw_refresh), device_name[:100],
                        ts(now), ts(now), ts(now + timedelta(days=REFRESH_TTL_DAYS))))
    return {"access_token": access_token(account_id), "token_type": "bearer",
            "expires_in": TOKEN_TTL_MINUTES * 60, "refresh_token": raw_refresh,
            "refresh_expires_in": REFRESH_TTL_DAYS * 86400, "device_id": sid}


class RegisterBody(BaseModel):
    username: str = Field(min_length=3, max_length=32)
    email: str = Field(min_length=6, max_length=254)
    password: str = Field(min_length=12, max_length=128)
    display_name: str | None = Field(default=None, max_length=60)
    device_name: str = Field(default="Sussy Baka OS device", max_length=100)

class LoginBody(BaseModel):
    email: str = Field(min_length=6, max_length=254)
    password: str = Field(min_length=1, max_length=128)
    device_name: str = Field(default="Sussy Baka OS device", max_length=100)

class TokenBody(BaseModel):
    token: str = Field(min_length=32, max_length=256)

class RefreshBody(BaseModel):
    refresh_token: str = Field(min_length=32, max_length=256)

class ResetBody(BaseModel):
    email: str = Field(min_length=6, max_length=254)

class ResetPasswordBody(BaseModel):
    token: str = Field(min_length=32, max_length=256)
    new_password: str = Field(min_length=12, max_length=128)

class ProfileBody(BaseModel):
    display_name: str | None = Field(default=None, max_length=60)
    crewmate_color: str | None = None
    avatar_url: str | None = Field(default=None, max_length=500)


@asynccontextmanager
async def lifespan(_: FastAPI):
    secret_key()
    initialize_database()
    yield

app = FastAPI(title=APP_NAME, version="1.0.0", docs_url="/docs" if setting("SUSSY_ACCOUNT_DEV_MODE") == "true" else None, lifespan=lifespan)


def current_account(authorization: str | None = Header(default=None)) -> sqlite3.Row:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Authentication required", headers={"WWW-Authenticate": "Bearer"})
    raw = authorization[7:].strip()
    try:
        data = jwt.decode(raw, secret_key(), algorithms=["HS256"], issuer=ISSUER, audience=AUDIENCE,
                          options={"require": ["sub", "iss", "aud", "iat", "exp", "jti"]})
    except jwt.PyJWTError:
        raise HTTPException(401, "Invalid or expired access token", headers={"WWW-Authenticate": "Bearer"})
    with db_conn() as db:
        account = db.execute("SELECT * FROM accounts WHERE id=?", (data["sub"],)).fetchone()
    if not account:
        raise HTTPException(401, "Account no longer exists")
    return account


def public_account(row: sqlite3.Row) -> dict:
    return {"id": row["id"], "username": row["username"], "email": row["email"],
            "display_name": row["display_name"], "email_verified": bool(row["email_verified"]),
            "crewmate_color": row["crewmate_color"], "avatar_url": row["avatar_url"],
            "created_at": row["created_at"]}

@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": APP_NAME, "email_configured": smtp_configured()}

@app.post("/v1/accounts/register", status_code=201)
def register(body: RegisterBody, request: Request) -> dict:
    username, email = body.username.strip(), body.email.strip().lower()
    if not USERNAME_RE.fullmatch(username): raise HTTPException(422, "Username must be 3–32 characters: letters, numbers, dot, underscore or hyphen")
    if not EMAIL_RE.fullmatch(email) or parseaddr(email)[1] != email: raise HTTPException(422, "Enter a valid email address")
    if not allow_attempt(f"register:{request.client.host if request.client else 'unknown'}"):
        raise HTTPException(429, "Too many registration attempts")
    if not smtp_configured() and setting("SUSSY_ACCOUNT_DEV_MODE", "false").lower() != "true":
        raise HTTPException(503, "Account email delivery is not configured. Set SMTP_HOST/SMTP_FROM before enabling registration.")
    verify = secrets.token_urlsafe(36)
    account_id = secrets.token_urlsafe(18)
    now = utcnow()
    with db_conn() as db:
        try:
            db.execute("""INSERT INTO accounts(id,username,email,display_name,password_hash,email_verified,verify_hash,verify_expires,created_at,updated_at)
                          VALUES(?,?,?,?,?,0,?,?,?,?)""", (account_id, username, email,
                            (body.display_name or username).strip()[:60], PASSWORD_HASHER.hash(body.password),
                            token_hash(verify), ts(now + timedelta(hours=VERIFY_TTL_HOURS)), ts(now), ts(now)))
        except sqlite3.IntegrityError:
            raise HTTPException(409, "Username or email is already registered")
    debug_token = send_or_dev(email, "Verify your Sussy Account",
        f"Your Sussy Account verification token is:\n\n{verify}\n\nIt expires in {VERIFY_TTL_HOURS} hours. If you did not register, ignore this email.", verify)
    out = {"message": "Account created. Verify your email before signing in.", "verification_required": True}
    if debug_token: out["development_verification_token"] = debug_token
    return out

@app.post("/v1/accounts/verify")
def verify_email(body: TokenBody) -> dict:
    now = utcnow()
    with db_conn() as db:
        row = db.execute("SELECT id,verify_expires FROM accounts WHERE verify_hash=?", (token_hash(body.token),)).fetchone()
        if not row or not row["verify_expires"] or parse_ts(row["verify_expires"]) < now:
            raise HTTPException(400, "Verification token is invalid or expired")
        db.execute("UPDATE accounts SET email_verified=1,verify_hash=NULL,verify_expires=NULL,updated_at=? WHERE id=?", (ts(now), row["id"]))
    return {"message": "Email verified. You can now sign in."}

@app.post("/v1/accounts/login")
def login(body: LoginBody, request: Request) -> dict:
    email = body.email.strip().lower()
    bucket = request.client.host if request.client else "unknown"
    if not allow_attempt(f"login:{bucket}:{email}"):
        raise HTTPException(429, "Too many sign-in attempts. Try again later.")
    with db_conn() as db:
        account = db.execute("SELECT * FROM accounts WHERE email=?", (email,)).fetchone()
    # Constant-ish behavior for nonexistent users; password hashes remain the authoritative verifier.
    if not account:
        PASSWORD_HASHER.hash(secrets.token_urlsafe(24))
        raise HTTPException(401, "Email or password is incorrect")
    try:
        valid = PASSWORD_HASHER.verify(account["password_hash"], body.password)
    except argon2_exceptions.VerifyMismatchError:
        valid = False
    if not valid: raise HTTPException(401, "Email or password is incorrect")
    if not account["email_verified"]: raise HTTPException(403, "Verify your email before signing in")
    return {"account": public_account(account), **refresh_pair(account["id"], body.device_name)}

@app.post("/v1/accounts/refresh")
def refresh(body: RefreshBody) -> dict:
    digest, now = token_hash(body.refresh_token), utcnow()
    with db_conn() as db:
        session = db.execute("SELECT * FROM sessions WHERE refresh_hash=?", (digest,)).fetchone()
        if not session or session["revoked_at"] or parse_ts(session["expires_at"]) < now:
            raise HTTPException(401, "Refresh token is invalid, expired or revoked")
        db.execute("UPDATE sessions SET revoked_at=? WHERE id=?", (ts(now), session["id"]))
        account = db.execute("SELECT * FROM accounts WHERE id=?", (session["account_id"],)).fetchone()
    if not account: raise HTTPException(401, "Account no longer exists")
    return {"account": public_account(account), **refresh_pair(account["id"], session["device_name"])}

@app.post("/v1/accounts/logout", status_code=204)
def logout(body: RefreshBody) -> Response:
    with db_conn() as db:
        db.execute("UPDATE sessions SET revoked_at=? WHERE refresh_hash=? AND revoked_at IS NULL", (ts(), token_hash(body.refresh_token)))
    return Response(status_code=204)

@app.post("/v1/accounts/password-reset/request")
def password_reset_request(body: ResetBody, request: Request) -> dict:
    email = body.email.strip().lower()
    if not allow_attempt(f"reset:{request.client.host if request.client else 'unknown'}:{email}"):
        raise HTTPException(429, "Too many reset attempts")
    with db_conn() as db:
        account = db.execute("SELECT id,email FROM accounts WHERE email=?", (email,)).fetchone()
        if account:
            reset = secrets.token_urlsafe(36)
            now = utcnow()
            db.execute("UPDATE accounts SET reset_hash=?,reset_expires=?,updated_at=? WHERE id=?",
                       (token_hash(reset), ts(now + timedelta(minutes=RESET_TTL_MINUTES)), ts(now), account["id"]))
        else:
            reset = ""
    # Never disclose whether an email exists. Debug tokens exist only in explicit development mode.
    out = {"message": "When an account exists, password-reset instructions will be sent."}
    if account and reset:
        if smtp_configured():
            send_email(email, "Reset your Sussy Account password",
                       f"Use this one-time reset token:\n\n{reset}\n\nIt expires in {RESET_TTL_MINUTES} minutes.")
        elif setting("SUSSY_ACCOUNT_DEV_MODE", "false").lower() == "true":
            out["development_reset_token"] = reset
    return out

@app.post("/v1/accounts/password-reset/complete")
def password_reset_complete(body: ResetPasswordBody) -> dict:
    now = utcnow()
    with db_conn() as db:
        account = db.execute("SELECT id,reset_expires FROM accounts WHERE reset_hash=?", (token_hash(body.token),)).fetchone()
        if not account or not account["reset_expires"] or parse_ts(account["reset_expires"]) < now:
            raise HTTPException(400, "Password-reset token is invalid or expired")
        db.execute("UPDATE accounts SET password_hash=?,reset_hash=NULL,reset_expires=NULL,updated_at=? WHERE id=?",
                   (PASSWORD_HASHER.hash(body.new_password), ts(now), account["id"]))
        db.execute("UPDATE sessions SET revoked_at=? WHERE account_id=? AND revoked_at IS NULL", (ts(now), account["id"]))
    return {"message": "Password changed. Sign in again on your devices."}

@app.get("/v1/me")
def get_profile(account: sqlite3.Row = Depends(current_account)) -> dict:
    return public_account(account)

@app.patch("/v1/me")
def update_profile(body: ProfileBody, account: sqlite3.Row = Depends(current_account)) -> dict:
    changes, params = [], []
    if body.display_name is not None:
        name = body.display_name.strip()
        if not name: raise HTTPException(422, "Display name cannot be empty")
        changes.append("display_name=?"); params.append(name)
    if body.crewmate_color is not None:
        color = body.crewmate_color.lower()
        if color not in COLORS: raise HTTPException(422, "Unsupported crewmate color")
        changes.append("crewmate_color=?"); params.append(color)
    if body.avatar_url is not None:
        if body.avatar_url and not body.avatar_url.startswith("https://"):
            raise HTTPException(422, "Avatar URL must use HTTPS")
        changes.append("avatar_url=?"); params.append(body.avatar_url or None)
    if changes:
        params.extend([ts(), account["id"]])
        with db_conn() as db:
            db.execute(f"UPDATE accounts SET {','.join(changes)},updated_at=? WHERE id=?", params)
    with db_conn() as db:
        refreshed = db.execute("SELECT * FROM accounts WHERE id=?", (account["id"],)).fetchone()
    return public_account(refreshed)

@app.get("/v1/devices")
def list_devices(account: sqlite3.Row = Depends(current_account)) -> list[dict]:
    with db_conn() as db:
        rows = db.execute("SELECT id,device_name,created_at,last_used_at,expires_at,revoked_at FROM sessions WHERE account_id=? ORDER BY created_at DESC", (account["id"],)).fetchall()
    return [dict(row) for row in rows]

@app.delete("/v1/devices/{device_id}", status_code=204)
def revoke_device(device_id: str, account: sqlite3.Row = Depends(current_account)) -> Response:
    with db_conn() as db:
        changed = db.execute("UPDATE sessions SET revoked_at=? WHERE id=? AND account_id=? AND revoked_at IS NULL", (ts(), device_id, account["id"]))
    if changed.rowcount == 0: raise HTTPException(404, "Active device not found")
    return Response(status_code=204)
