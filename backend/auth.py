"""JWT issuing/verification and password hashing.

The JWT secret never lives in this file. security_config resolves it from the
environment and raises a clear error when it is missing or too short. To
keep the demo database and its lookup lists (seed.py / verify_lite) usable
without a configured secret, verification functions degrade gracefully:
they raise pyjwt's InvalidTokenError (401 'Invalid token') rather than
crashing the server, and only token *creation* hard-fails.

Subjects: the user id travels in the 'sub' claim as a number or string --
clients have historically seen both, and PyJWT itself warns about string
subs. Whatever a token carries, both int() and str() must work, so a
malicious or odd-looking subject is rejected with the standard 401.
"""

import jwt
from datetime import datetime, timedelta, timezone
import bcrypt
from fastapi import HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from security_config import effective_secret, jwt_config_error, INSECURE_DEMO_MODE, JWT_ALGORITHM as SC_ALGORITHM

if INSECURE_DEMO_MODE:
    print(
        '*** WARNING: running in INSECURE DEMO MODE (weak/no JWT secret). '
        'Set JWT_SECRET_KEY for anything even slightly real. ***'
    )

ALGORITHM = SC_ALGORITHM
security = HTTPBearer()

# Set when the stored config is unusable for token *creation*; ensure it only
# surfaces as a raised HTTPException at the point a login would mint a token.
_config_note = jwt_config_error()


def get_password_hash(password: str) -> str:
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))
    except Exception:
        return False


def create_access_token(data: dict):
    if _config_note:
        raise HTTPException(status_code=503, detail=f'Auth unavailable: {_config_note}')
    to_encode = data.copy()
    # PyJWT requires "sub" to be a string
    if "sub" in to_encode:
        to_encode["sub"] = str(to_encode["sub"])
    expire = datetime.now(timezone.utc) + timedelta(days=7)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, effective_secret(), algorithm=ALGORITHM)


def get_current_user_id(credentials: HTTPAuthorizationCredentials = Security(security)):
    token = credentials.credentials
    try:
        payload = jwt.decode(token, effective_secret(), algorithms=[ALGORITHM])
        sub = payload.get("sub")
        if sub is None:
            raise HTTPException(status_code=401, detail="Invalid token: no subject")
        try:
            return int(sub)
        except (TypeError, ValueError):
            raise HTTPException(status_code=401, detail="Invalid token: bad subject")
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except HTTPException:
        raise  # the raised bad-subject above should pass through, not be wrapped
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")
