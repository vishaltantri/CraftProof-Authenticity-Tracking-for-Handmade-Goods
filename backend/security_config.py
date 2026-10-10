"""Fail-fast security configuration for the CraftProof backend.

Loads JWT_SECRET_KEY / JWT_ALGORITHM from the environment and refuses to
issue or accept tokens with a weak or missing secret, so an operator cannot
silently run the old hard-coded credential.

Design note — fail *late*, not at import: `seed.py` and the test suite import
`auth` only for bcrypt helpers and must keep working with no environment set.
The configuration problem is therefore recorded at import time and enforced
whenever a token is actually created or verified (`jwt_config_error()`), and
again at server boot (`main.lifespan` → `require_jwt_secret()`), which is the
fail-fast gate for deployments.

Demo-only escape hatch: with CRAFTPROOF_ALLOW_INSECURE_DEMO=true a fixed
demo secret is used so local try-it-out runs keep working, with a prominent
warning exposed via INSECURE_DEMO_MODE. The deployed demo also sets this to
keep its viva-demo tamper endpoint available (see render.yaml).
"""

from __future__ import annotations

import os
import secrets

_ALLOWED_ALGOS = {'HS256', 'HS384', 'HS512'}
_MIN_SECRET_LEN = 32  # HS256 wants >= 256 bits of key material

JWT_ALGORITHM = os.environ.get('JWT_ALGORITHM', 'HS256').strip()
if JWT_ALGORITHM not in _ALLOWED_ALGOS:  # pragma: no cover - config error path
    JWT_CONFIG_ERROR: str | None = (
        f"JWT_ALGORITHM {JWT_ALGORITHM!r} not supported; pick one of {sorted(_ALLOWED_ALGOS)}"
    )
else:
    JWT_CONFIG_ERROR = None

_allow_demo = os.environ.get('CRAFTPROOF_ALLOW_INSECURE_DEMO', '').strip().lower() in ('1', 'true', 'yes')

_jwt_secret = os.environ.get('JWT_SECRET_KEY', '').strip()

if JWT_CONFIG_ERROR is None:
    if _jwt_secret and len(_jwt_secret) >= _MIN_SECRET_LEN:
        JWT_SECRET_KEY: str = _jwt_secret
    elif _jwt_secret and _allow_demo:
        JWT_SECRET_KEY = _jwt_secret
    elif _jwt_secret:
        JWT_CONFIG_ERROR = (
            f'JWT_SECRET_KEY is too short ({len(_jwt_secret)} < {_MIN_SECRET_LEN} chars).'
        )
    elif _allow_demo:
        JWT_SECRET_KEY = 'demo-mode-not-production-please-do-not-expose-0000'
    else:
        JWT_CONFIG_ERROR = (
            'JWT_SECRET_KEY is not set. Set a strong secret (>= 32 chars) in the '
            'environment; for throwaway local demo runs you may instead set '
            'CRAFTPROOF_ALLOW_INSECURE_DEMO=true.'
        )

# INSECURE_DEMO_MODE is True whenever we are running with anything less than a
# proper production secret — it gates the deploy's tamper-demo endpoint and
# prints a boot warning.
INSECURE_DEMO_MODE = bool(
    _allow_demo and (not _jwt_secret or len(_jwt_secret) < _MIN_SECRET_LEN)
)

_DEMO_SECRET = 'demo-mode-not-production-please-do-not-expose-0000'


def jwt_config_error() -> str | None:
    """Human-readable config problem, or None when tokens may be issued."""
    return JWT_CONFIG_ERROR


def require_jwt_secret() -> str:
    """Return the configured secret or raise the stored config error."""
    if JWT_CONFIG_ERROR:
        raise RuntimeError(f'Refusing to run: {JWT_CONFIG_ERROR}')
    assert JWT_SECRET_KEY or _allow_demo
    return JWT_SECRET_KEY or _DEMO_SECRET


def effective_secret() -> str:
    """The secret actually used for signing/verification (demo-aware)."""
    if JWT_CONFIG_ERROR:
        raise RuntimeError(f'Refusing to run: {JWT_CONFIG_ERROR}')
    return JWT_SECRET_KEY or _DEMO_SECRET


def demo_secret() -> str:
    """The fixed demo secret (import-only; never used unless demo allowed)."""
    return _DEMO_SECRET


def random_secret() -> str:
    """Convenience for deploy tooling: a properly random secret."""
    return secrets.token_urlsafe(48)
