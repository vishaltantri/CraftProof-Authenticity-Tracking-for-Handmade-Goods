import asyncio
import logging
from contextlib import asynccontextmanager, suppress
from fastapi import FastAPI, Depends, HTTPException, Header, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import string, random

from auth import get_password_hash, verify_password, create_access_token, get_current_user_id
from database import get_db
from crypto_utils import generate_keypair, pubkey_to_hex, sign
from keystore import encrypt_private_key, is_envelope, KeyStore
from security_config import require_jwt_secret, jwt_config_error, INSECURE_DEMO_MODE
from core import verify_chain_detailed, create_checkpoint, list_checkpoints, get_inclusion_proof
from record import CustodyRecord, GENESIS_HASH
import remarket
from seed import seed as seed_demo_data
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

_DEMO_MODE_ACTIVE = False   # set at startup when running with a demo-secret JWT


def seed_demo_if_empty():
    """First boot on a fresh database (e.g. every new Render deploy, where the
    disk starts empty): fill it with the demo makers, pieces and a ledger
    checkpoint so the deployed app never opens on a blank slate."""
    conn = get_db()
    try:
        is_empty = conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"] == 0
    finally:
        conn.close()
    if is_empty:
        print("[startup] Empty database — seeding demo makers, pieces and a checkpoint")
        seed_demo_data()


async def poll_remarket_sales(interval: int):
    """Background poller for the ReMarket sales feed.

    A failed poll is logged and retried on the next tick rather than killing
    the task: the partner runs on a free host that sleeps, so transient 502s
    are expected and must not silently stop the integration for the rest of
    the process's life.
    """
    while True:
        await asyncio.sleep(interval)
        try:
            result = await asyncio.to_thread(remarket.sync_sales)
            if result["imported"]:
                print(f"[remarket] imported {result['imported']} sale(s)")
        except asyncio.CancelledError:
            raise
        except Exception:
            logging.exception("[remarket] sale sync failed; will retry next tick")


@asynccontextmanager
async def lifespan(app):
    global _DEMO_MODE_ACTIVE
    # Fail fast on a missing/weak JWT secret: this is the deployment gate.
    # (The auth helpers degrade gracefully at import so seeding and the test
    # suite can run without an environment; a real API server must not.)
    require_jwt_secret()
    if INSECURE_DEMO_MODE:
        _DEMO_MODE_ACTIVE = True
        print(
            "*** DEMO MODE: fixed demo JWT secret in use; the /admin tamper-demo "
            "endpoint is enabled for the viva demo only. ***"
        )
    seed_demo_if_empty()

    poller = None
    interval = remarket.sync_interval()
    if remarket.is_configured() and interval > 0:
        print(f"[remarket] polling {remarket.api_url()} every {interval}s")
        poller = asyncio.create_task(poll_remarket_sales(interval))
    elif not remarket.is_configured():
        print("[remarket] not configured — set REMARKET_API_URL and REMARKET_SALE_API_KEY to enable")

    try:
        yield
    finally:
        if poller:
            poller.cancel()
            with suppress(asyncio.CancelledError):
                await poller


_KEYSTORE = KeyStore(ttl=900)


def _unlock_seed(user_id: int, user_row, password: str | None) -> bytes:
    """Return the user's raw Ed25519 seed, unlocking the key envelope.

    Order of preference:
      1. the in-memory keystore cache (no KDF work)
      2. decrypt the AEAD envelope with the caller-supplied password
         (signup/fragment flows that have the plaintext password)
      3. legacy rows from before the envelope change, stored as raw hex —
         still accepted for signing, but flagged so operators know to
         re-encrypt on next password change.

    When a cached unlock is missing and no password is available, we raise
    423 Locked rather than fail open: the user must re-login (which re-arms
    the keystore) before signing custody transfers.
    """
    cached = _KEYSTORE.get(user_id)
    if cached is not None:
        return cached

    enc = user_row["encrypted_privkey"]
    if is_envelope(enc):
        if not password:
            raise HTTPException(
                status_code=423,
                detail="Your signing key is locked — please log in again to continue.",
            )
        seed_bytes = _decrypt_privkey_with_password(enc, password)
        _KEYSTORE.remember(user_id, seed_bytes)
        return seed_bytes

    # Legacy plain-hex storage (pre-envelope). Accept it, but be honest that
    # it is not protected: anything that can read the DB could have used it.
    seed_bytes = bytes.fromhex(enc)
    if len(seed_bytes) != 32:
        raise HTTPException(status_code=500, detail="Corrupt signing key in database")
    print(f"[keys] user {user_id} still uses a legacy raw-hex signing key — consider re-encrypting")
    _KEYSTORE.remember(user_id, seed_bytes)
    return seed_bytes


def _decrypt_privkey_with_password(envelope: str, password: str) -> bytes:
    from keystore import decrypt_private_key
    try:
        return decrypt_private_key(envelope, password)
    except ValueError:
        raise HTTPException(status_code=500, detail="Unable to unlock your signing key")


app = FastAPI(
    title="CraftProof API",
    description=(
        "Public API for CraftProof — tamper-evident authenticity certificates for "
        "handmade goods. Verification endpoints are open and need no API key; "
        "write endpoints (registering pieces, transfers) need a bearer token from "
        "POST /auth/login. Interactive docs: /docs — raw schema: /openapi.json"
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    # Auth uses bearer tokens in the Authorization header, not cookies, so
    # credentialed requests are never needed — and wildcard origin + credentials
    # is an invalid combination per the CORS spec.
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- Pydantic models ----------

class SignupRequest(BaseModel):
    name: str
    email: str
    password: str
    role: str
    shop_name: Optional[str] = None

class LoginRequest(BaseModel):
    email: str
    password: str

class PieceRequest(BaseModel):
    title: str
    description: Optional[str] = ""
    materials: Optional[str] = ""
    maker_statement: Optional[str] = ""
    fingerprint_commitment: Optional[str] = None

class TransferRequest(BaseModel):
    to_user_id: Optional[int] = None
    to_name: Optional[str] = None
    note: Optional[str] = ""

class FingerprintPieceRequest(BaseModel):
    """Piece registration carrying an enrolled physical fingerprint.

    descriptor_b64 is the serialize_template() payload of the ENROLMENT
    template (built from the registration photos). The server recomputes
    its digest and requires it to equal fingerprint_commitment, so the
    template that will later be matched IS the template the genesis record
    signed — no gap between what is committed and what is compared.
    """
    title: str
    description: Optional[str] = ""
    materials: Optional[str] = ""
    maker_statement: Optional[str] = ""
    fingerprint_commitment: str
    descriptor_b64: Optional[str] = None

class VerifyObjectRequest(BaseModel):
    """A base64(urlsafe) fingerprint template from a verification capture.

    The server never stores this payload beyond the similarity/clone-decision
    event record; only the enrollment-time template (bound to the genesis
    custody record's commitment) persists.
    """
    descriptor_b64: str

# ---------- Helpers ----------

def generate_certificate_code(conn):
    """Short, human-readable code for the QR URL. Retried until unused."""
    while True:
        code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
        if not conn.execute("SELECT 1 FROM pieces WHERE certificate_code = ?", (code,)).fetchone():
            return code


def _seed_user(conn, user_id: int, password: str | None):
    """Resolve the signing seed for user_id, arming the keystore when the
    password is known (login / signup) and deferring to the cache otherwise."""
    user = conn.execute(
        "SELECT encrypted_privkey FROM users WHERE id = ?", (user_id,)
    ).fetchone()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    enc = user["encrypted_privkey"]
    cached = _KEYSTORE.get(user_id)
    if cached is not None:
        return cached
    # Integration service accounts (remarket.py) keep their signing key in a
    # file outside the database. Nothing may sign *as* them through the user
    # API — refuse clearly rather than fall through to the hex parser below.
    if enc.startswith("external-key-file:"):
        raise HTTPException(
            status_code=403,
            detail="This is an integration service account and cannot transfer pieces",
        )
    if is_envelope(enc):
        if not password:
            raise HTTPException(
                status_code=423,
                detail="Your signing key is locked — please log in again to continue.",
            )
        from keystore import decrypt_private_key
        try:
            seed_bytes = decrypt_private_key(enc, password)
        except ValueError:
            raise HTTPException(status_code=500, detail="Unable to unlock your signing key")
        _KEYSTORE.remember(user_id, seed_bytes)
        return seed_bytes
    # Legacy raw-hex row (pre-envelope). Accepted, flagged honestly.
    seed_bytes = bytes.fromhex(enc)
    if len(seed_bytes) != 32:
        raise HTTPException(status_code=500, detail="Corrupt signing key in database")
    print(f"[keys] user {user_id} still uses a legacy raw-hex signing key — consider re-encrypting")
    _KEYSTORE.remember(user_id, seed_bytes)
    return seed_bytes

# ---------- Auth ----------

@app.post("/auth/signup")
def signup(req: SignupRequest):
    email = req.email.strip().lower()
    if not req.name.strip():
        raise HTTPException(status_code=400, detail="Name is required")
    if len(req.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
    if req.role not in ("maker", "seller"):
        raise HTTPException(status_code=400, detail="Role must be 'maker' or 'seller'")

    conn = get_db()
    try:
        existing = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
        if existing:
            raise HTTPException(status_code=400, detail="Email already registered")

        sk, pk = generate_keypair()
        sk_raw = sk.private_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PrivateFormat.Raw,
            encryption_algorithm=serialization.NoEncryption()
        )
        # AEAD envelope under the user's own password — losing the password
        # means losing the signing key, by design (no server override path).
        enc = encrypt_private_key(sk_raw, req.password)
        pk_hex = pubkey_to_hex(pk)

        hashed_pw = get_password_hash(req.password)

        c = conn.cursor()
        c.execute(
            "INSERT INTO users (name, email, password_hash, role, shop_name, public_key, encrypted_privkey) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (req.name.strip(), email, hashed_pw, req.role, req.shop_name, pk_hex, enc)
        )
        conn.commit()
        user_id = c.lastrowid
        _KEYSTORE.remember(user_id, sk_raw)

        token = create_access_token({"sub": user_id})
        return {"access_token": token, "user_id": user_id, "name": req.name, "role": req.role}
    finally:
        conn.close()

@app.post("/auth/login")
def login(req: LoginRequest):
    conn = get_db()
    try:
        user = conn.execute("SELECT id, password_hash, name, role FROM users WHERE email = ?", (req.email.strip().lower(),)).fetchone()
        if not user or not verify_password(req.password, user["password_hash"]):
            raise HTTPException(status_code=401, detail="Invalid credentials")

        token = create_access_token({"sub": user["id"]})
        # With the plaintext password in hand, arm the keystore for this
        # session so subsequent transfers can sign without re-prompting.
        try:
            _seed_user(conn, user["id"], req.password)
        except HTTPException:
            pass  # legacy/corrupt rows must not block a normal login
        return {"access_token": token, "user_id": user["id"], "name": user["name"], "role": user["role"]}
    finally:
        conn.close()

@app.get("/users")
def get_users():
    conn = get_db()
    try:
        # Integration service accounts (e.g. the ReMarket importer) are not
        # people and must never appear as a transfer destination.
        users = conn.execute(
            "SELECT id, name, role, shop_name FROM users WHERE role != 'integration'"
        ).fetchall()
        return [{"id": u["id"], "name": u["name"], "role": u["role"], "shop_name": u["shop_name"]} for u in users]
    finally:
        conn.close()

# ---------- Pieces ----------

@app.post("/pieces")
def create_piece(req: PieceRequest, user_id: int = Depends(get_current_user_id)):
    conn = get_db()
    try:
        code = generate_certificate_code(conn)
        piece_id = _insert_piece_with_genesis(
            conn,
            certificate_code=code,
            title=req.title,
            description=req.description or "",
            materials=req.materials or "",
            made_by=user_id,
            maker_statement=req.maker_statement or "",
            commitment=req.fingerprint_commitment,
        )
        conn.commit()
        return {"status": "success", "certificate_code": code, "piece_id": piece_id}
    finally:
        conn.close()


@app.post("/pieces/with-fingerprint", status_code=201)
def create_piece_with_fingerprint(
    req: FingerprintPieceRequest,
    user_id: int = Depends(get_current_user_id),
):
    """Register a piece carrying a physical-fingerprint commitment.

    The commitment is a hex SHA-256 digest over the canonical JSON summary of
    the extracted template (feature_flags + fields + quantised descriptors).
    Format is defined in fingerprint.py; nobody needs more than the digest
    here, so the API never sees the raw template.
    """
    import binascii
    try:
        bytes.fromhex(req.fingerprint_commitment)
    except (ValueError, binascii.Error):
        raise HTTPException(status_code=400, detail="fingerprint_commitment must be hex")
    if len(req.fingerprint_commitment) != 64:
        raise HTTPException(status_code=400, detail="fingerprint_commitment must be a 64-hex SHA-256 digest")
    if req.fingerprint_commitment != req.fingerprint_commitment.lower():
        raise HTTPException(status_code=400, detail="fingerprint_commitment must be lowercase hex")

    # When the enrolment template is supplied, its digest must equal the
    # commitment — this is what makes the signed 'cm' field describe the
    # template actually used for later matching.
    enrolled_template = None
    if req.descriptor_b64:
        import base64 as _b64
        import fingerprint
        try:
            enrolled_template = fingerprint.deserialize_template(
                _b64.urlsafe_b64decode(req.descriptor_b64))
        except Exception:
            raise HTTPException(status_code=400,
                                detail="descriptor_b64 is not a valid fingerprint payload")
        digest = fingerprint.template_digest(enrolled_template)
        if digest != req.fingerprint_commitment:
            raise HTTPException(
                status_code=400,
                detail=("descriptor_b64 digest does not match fingerprint_commitment "
                        f"({digest}); enroll with the same template you commit to"))

    conn = get_db()
    try:
        code = generate_certificate_code(conn)
        piece_id = _insert_piece_with_genesis(
            conn,
            certificate_code=code,
            title=req.title,
            description=req.description or "",
            materials=req.materials or "",
            made_by=user_id,
            maker_statement=req.maker_statement or "",
            commitment=req.fingerprint_commitment,
        )
        if enrolled_template is not None:
            import fingerprint
            fingerprint.store_template(piece_id, enrolled_template)
        conn.commit()
        return (
            {"status": "success", "certificate_code": code, "piece_id": piece_id,
             "fingerprint_commitment": req.fingerprint_commitment}
        )
    finally:
        conn.close()


def _insert_piece_with_genesis(
    conn,
    certificate_code: str,
    title: str,
    description: str,
    materials: str,
    made_by: int,
    maker_statement: str,
    commitment: Optional[str],
) -> int:
    c = conn.cursor()
    c.execute(
        "INSERT INTO pieces (certificate_code, title, description, materials, made_by, current_owner_id, fingerprint_commitment) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (certificate_code, title, description, materials, made_by, made_by, commitment)
    )
    piece_id = c.lastrowid
    genesis = CustodyRecord(
        piece_id, 0, made_by, made_by, "Self", maker_statement or "Piece created", GENESIS_HASH,
    )
    if commitment:
        # cm: prefix keeps the plain-record and commitment schemas unambiguous —
        # same key set, one extra deliberately-named field.
        genesis.add_field("cm", commitment)
    rec_hash = genesis.compute_hash()
    sk = Ed25519PrivateKey.from_private_bytes(_seed_user(conn, made_by, None))
    sig = sign(sk, bytes.fromhex(rec_hash)).hex()
    c.execute(
        "INSERT INTO custody_records (piece_id, seq_index, from_user_id, to_user_id, to_name, note, timestamp, prev_hash, record_hash, signature) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (piece_id, 0, made_by, made_by, "Self", genesis.note, genesis.timestamp, GENESIS_HASH, rec_hash, sig)
    )
    return piece_id


@app.get("/pieces/mine")
def get_my_pieces(user_id: int = Depends(get_current_user_id)):
    conn = get_db()
    try:
        pieces = conn.execute("SELECT * FROM pieces WHERE current_owner_id = ?", (user_id,)).fetchall()
        return [dict(p) for p in pieces]
    finally:
        conn.close()

@app.get("/pieces/made")
def get_pieces_i_made(user_id: int = Depends(get_current_user_id)):
    """Everything this user created, including pieces already handed on.

    /pieces/mine only shows current holdings; a maker still wants to follow a
    piece after it leaves the studio.
    """
    conn = get_db()
    try:
        pieces = conn.execute('''
            SELECT p.*, u.name AS current_owner_name, u.shop_name AS current_owner_shop
            FROM pieces p LEFT JOIN users u ON p.current_owner_id = u.id
            WHERE p.made_by = ? ORDER BY p.id DESC
        ''', (user_id,)).fetchall()

        out = []
        for p in pieces:
            d = dict(p)
            last = conn.execute(
                "SELECT to_name, seq_index FROM custody_records WHERE piece_id = ? ORDER BY seq_index DESC LIMIT 1",
                (p["id"],)
            ).fetchone()
            d["holder"] = (d.pop("current_owner_shop", None) or d.pop("current_owner_name", None)
                           or (last["to_name"] if last else None) or "Unknown")
            d["transfers"] = last["seq_index"] if last else 0
            d["still_held"] = p["current_owner_id"] == user_id
            out.append(d)
        return out
    finally:
        conn.close()

# ---------- Physical verification (fingerprint + clone detection) ----------

@app.post("/pieces/{code}/verify-object", tags=["Physical"],
          summary="Compare a captured physical template against the enrolled fingerprint")
def verify_object(code: str, req: VerifyObjectRequest):
    """Full physical–digital verification for a piece.

    Workflow: capture photos of the object → build a probe template locally
    (fingerprint.py) → send serialize_template(probe) as descriptor_b64.
    The server compares against the enrolled template for this certificate,
    records a verification event, and runs clone detection (same code,
    mismatching object → the tag is likely cloned). Returns ``enrolled``,
    ``match`` (None when nothing enrolled), ``similarity``, ``threshold``,
    ``clone_check`` and a plain-language ``verdict`` for UI presentation.
    """
    import base64 as _b64
    import fingerprint
    from clone_detection import detect_clone, record_event

    conn = get_db()
    try:
        piece = _load_certificate(conn, code)
        try:
            probe = fingerprint.deserialize_template(_b64.urlsafe_b64decode(req.descriptor_b64))
        except Exception:
            raise HTTPException(status_code=400, detail="descriptor_b64 is not a valid fingerprint payload")

        similarity = None
        match = None
        if piece["fingerprint_commitment"]:
            stored = fingerprint.load_template_by_piece(piece["id"])
            if stored is None:
                raise HTTPException(
                    status_code=500,
                    detail="Fingerprint committed but template missing — verification unavailable for this piece",
                )
            similarity = fingerprint.template_similarity(stored, probe)
            match = similarity >= fingerprint.match_threshold()
            verdict = (
                "The object matches this certificate's enrolled fingerprint"
                if match else
                "The object does NOT match this certificate's enrolled fingerprint"
            )
        else:
            verdict = ("No fingerprint is enrolled for this piece; "
                       "only the digital history can be verified")

        # Record the event, then run clone detection across this code's history.
        record_event(conn, piece, similarity, match, probe)
        clone = detect_clone(conn, piece, probe)
        conn.commit()
        return {
            "enrolled": bool(piece["fingerprint_commitment"]),
            "match": match,
            "similarity": similarity,
            "threshold": fingerprint.match_threshold() if piece["fingerprint_commitment"] else None,
            "clone_check": clone,
            "verdict": verdict,
        }
    finally:
        conn.close()

# ---------- ReMarket marketplace integration ----------
#
# CraftProof is the API *client* in this partnership: ReMarket exposes a
# key-protected sales feed and we poll it. The partner key is used only from
# this server — it is never sent to the browser and never stored in the DB.
# See remarket.py for the import rules and their limits.

@app.get("/integrations/remarket/status", tags=["Integrations"],
         summary="ReMarket connection and import summary")
def remarket_status():
    """Whether the ReMarket link is configured, and what it has imported.

    Reports only whether a key is *present* — never any part of its value —
    so this is safe to render in the public dashboard.
    """
    return remarket.integration_status()


@app.get("/integrations/remarket/imports", tags=["Integrations"],
         summary="Sales already imported from ReMarket")
def remarket_imports(limit: int = Query(50, ge=1, le=200)):
    return {"imports": remarket.list_imports(limit)}


@app.post("/integrations/remarket/sync", tags=["Integrations"],
          summary="Pull completed ReMarket sales now")
def remarket_sync(x_integration_key: Optional[str] = Header(default=None)):
    """Run a sync immediately instead of waiting for the next poll.

    Gated on CRAFTPROOF_REMARKET_SYNC_KEY rather than a user token: this is an
    operator/scheduler hook, and the CraftProof backend on a free host is only
    awake intermittently, so an external cron needs to be able to call it.
    """
    remarket.require_sync_key(x_integration_key)
    return remarket.sync_sales()


@app.post("/integrations/remarket/sync-as-user", tags=["Integrations"],
          summary="Pull completed ReMarket sales now (signed-in user)")
def remarket_sync_as_user(user_id: int = Depends(get_current_user_id)):
    """The dashboard's 'Sync now' button.

    Same work as /integrations/remarket/sync, authorised by a normal CraftProof
    session instead of the integration key — so the browser never needs to hold
    a shared secret. The import rules are identical either way; triggering a
    sync cannot change what gets imported, only when.
    """
    return remarket.sync_sales()


@app.get("/integrations/remarket/feed", tags=["Integrations"],
         summary="Live ReMarket sales feed (server-side proxy)")
def remarket_feed(
    after_id: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    user_id: int = Depends(get_current_user_id),
):
    """Read the partner's feed without importing anything.

    Exists so the dashboard can show what ReMarket is reporting alongside what
    CraftProof has already imported. The bearer key stays on this server; the
    browser authenticates with its own CraftProof token.
    """
    with remarket.remarket_client() as client:
        page = remarket.fetch_sales(client, after_id, limit)

    conn = get_db()
    try:
        known = {
            r["order_id"] for r in conn.execute(
                "SELECT order_id FROM remarket_imports"
            ).fetchall()
        }
    finally:
        conn.close()

    for sale in page["sales"]:
        if isinstance(sale, dict):
            sale["imported"] = sale.get("order_id") in known
    return page


# ---------- Public verification API for marketplace partners ----------

@app.get("/api/verify", tags=["Public API"],
         summary="Verify many certificates in one call")
def api_verify_batch(codes: str = Query(..., description="Comma-separated certificate codes, max 50")):
    """Batch form of /api/verify/{code}, for a marketplace listing page.

    ReMarket renders many listings at once; one request per certificate turns
    a page render into N cold-start round trips. Unknown codes come back with
    ``found: false`` rather than failing the whole batch.
    """
    wanted = [c.strip().upper() for c in codes.split(",") if c.strip()]
    if not wanted:
        raise HTTPException(status_code=400, detail="Provide at least one certificate code")
    if len(wanted) > 50:
        raise HTTPException(status_code=400, detail="At most 50 codes per request")

    results = []
    for code in dict.fromkeys(wanted):          # de-duplicate, keep order
        try:
            results.append(dict(api_verify(code), found=True))
        except HTTPException as exc:
            if exc.status_code != 404:
                raise
            results.append({"certificate_code": code, "found": False, "authentic": None})
    return {"results": results}


# ---------- Transfer ----------

@app.post("/pieces/{piece_id}/transfer")
def transfer_piece(piece_id: int, req: TransferRequest, user_id: int = Depends(get_current_user_id)):
    conn = get_db()
    try:
        piece = conn.execute("SELECT current_owner_id FROM pieces WHERE id = ?", (piece_id,)).fetchone()
        if not piece or piece["current_owner_id"] != user_id:
            raise HTTPException(status_code=403, detail="You are not the current owner of this piece")

        if req.to_user_id == user_id:
            raise HTTPException(status_code=400, detail="You already hold this piece")
        if req.to_user_id:
            recipient = conn.execute("SELECT id FROM users WHERE id = ?", (req.to_user_id,)).fetchone()
            if not recipient:
                raise HTTPException(status_code=404, detail="Recipient not found")
        elif not (req.to_name or "").strip():
            raise HTTPException(status_code=400, detail="Enter the buyer's name")

        last_rec = conn.execute(
            "SELECT seq_index, record_hash FROM custody_records WHERE piece_id = ? ORDER BY seq_index DESC LIMIT 1",
            (piece_id,)
        ).fetchone()
        seq_index = last_rec["seq_index"] + 1
        prev_hash = last_rec["record_hash"]

        sk = Ed25519PrivateKey.from_private_bytes(_seed_user(conn, user_id, None))

        to_name = req.to_name or "Unknown buyer"
        rec = CustodyRecord(piece_id, seq_index, user_id, req.to_user_id, to_name, req.note or "", prev_hash)
        rec_hash = rec.compute_hash()
        sig = sign(sk, bytes.fromhex(rec_hash)).hex()

        c = conn.cursor()
        c.execute(
            "INSERT INTO custody_records (piece_id, seq_index, from_user_id, to_user_id, to_name, note, timestamp, prev_hash, record_hash, signature) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (piece_id, seq_index, user_id, req.to_user_id, to_name, rec.note, rec.timestamp, prev_hash, rec_hash, sig)
        )

        if req.to_user_id:
            c.execute("UPDATE pieces SET current_owner_id = ? WHERE id = ?", (req.to_user_id, piece_id))
        else:
            c.execute("UPDATE pieces SET current_owner_id = NULL WHERE id = ?", (piece_id,))

        conn.commit()
        return {"status": "success"}
    finally:
        conn.close()

# ---------- Public Certificate ----------

def _load_certificate(conn, code):
    piece = conn.execute("SELECT * FROM pieces WHERE certificate_code = ?", (code.strip().upper(),)).fetchone()
    if not piece:
        raise HTTPException(status_code=404, detail="Certificate not found")
    return piece

@app.get("/c/{code}")
def get_certificate(code: str):
    conn = get_db()
    try:
        piece = _load_certificate(conn, code)

        # Get maker name
        maker = conn.execute("SELECT name FROM users WHERE id = ?", (piece["made_by"],)).fetchone()
        maker_name = maker["name"] if maker else "Unknown"

        records = conn.execute('''
            SELECT c.*, u1.name as from_name, u2.name as to_account_name, u2.shop_name as to_shop_name
            FROM custody_records c
            LEFT JOIN users u1 ON c.from_user_id = u1.id
            LEFT JOIN users u2 ON c.to_user_id = u2.id
            WHERE c.piece_id = ? ORDER BY c.seq_index ASC
        ''', (piece["id"],)).fetchall()

        valid, reason, checks = verify_chain_detailed(piece["id"])
        checks_by_seq = {c["seq_index"]: c for c in checks}

        # Which steps were written by the ReMarket importer rather than
        # signed by the outgoing custodian. The chain verdict is unchanged —
        # these records verify like any other — but the UI must not present
        # a marketplace's word as the previous owner's confirmation.
        marketplace_records = remarket.imported_record_ids(conn, piece["id"])

        timeline = []
        anchored = 0
        for r in records:
            to_display = r["to_shop_name"] or r["to_account_name"] or r["to_name"] or "Unknown"
            chk = checks_by_seq.get(r["seq_index"], {})
            inclusion = get_inclusion_proof(r["record_hash"])
            if inclusion and inclusion["included"]:
                anchored += 1
            order_id = marketplace_records.get(r["id"])
            timeline.append({
                "seq_index": r["seq_index"],
                "from_name": r["from_name"],
                "to_name": to_display,
                "note": r["note"],
                "timestamp": r["timestamp"],
                "record_hash": r["record_hash"],
                "checks": chk,
                "checkpoint": inclusion["batch_index"] if inclusion and inclusion["included"] else None,
                "marketplace": (
                    {"source": "ReMarket", "order_id": order_id} if order_id else None
                ),
            })

        piece_dict = dict(piece)
        piece_dict["maker_name"] = maker_name

        # Physical clone status (plan W5): replay the certificate's most
        # recent scan against its scan history so the PUBLIC certificate
        # page can show the red banner — not just the verify-object call.
        # Degrades to None (no banner) when there are no scans or the
        # stored event template is gone; the chain verdict is unaffected.
        clone_status = None
        try:
            from clone_detection import _load_events, _template_from_digest, detect_clone
            events = _load_events(conn, piece["id"])
            if events:
                probe = _template_from_digest(conn, events[-1]["digest"])
                if probe is not None:
                    clone_status = detect_clone(conn, piece, probe)
        except Exception:
            clone_status = None

        return {
            "piece": piece_dict,
            "timeline": timeline,
            "verified": valid,
            "reason": reason,
            "clone": clone_status,
            "ledger": {
                "anchored_records": anchored,
                "total_records": len(timeline),
                "fully_anchored": bool(timeline) and anchored == len(timeline),
            },
        }
    finally:
        conn.close()

@app.get("/c/{code}/proof")
def get_certificate_proof(code: str):
    """Everything a third party needs to re-verify this certificate themselves.

    Returns the exact signed fields, the record hashes, the signer public keys
    and the Merkle inclusion proofs — so nobody has to take the server's word
    for the green badge. See backend/verify_cli.py for a reference verifier.
    """
    conn = get_db()
    try:
        piece = _load_certificate(conn, code)
        records = conn.execute(
            "SELECT * FROM custody_records WHERE piece_id = ? ORDER BY seq_index ASC", (piece["id"],)
        ).fetchall()

        out = []
        for r in records:
            signer = conn.execute("SELECT name, public_key FROM users WHERE id = ?", (r["from_user_id"],)).fetchone()
            signed_fields = {
                "piece_id": r["piece_id"],
                "seq_index": r["seq_index"],
                "from_user_id": r["from_user_id"],
                "to_user_id": r["to_user_id"],
                "to_name": r["to_name"],
                "note": r["note"],
                "timestamp": r["timestamp"],
                "prev_hash": r["prev_hash"],
            }
            # A fingerprint-committed genesis was signed over one extra 'cm'
            # field. Include it exactly when it reproduces the stored hash so
            # pre-commitment chains (and any legacy consumer) stay verifiable.
            if r["seq_index"] == 0 and piece["fingerprint_commitment"]:
                from crypto_utils import canonical_json, sha256 as _sha256
                with_cm = dict(signed_fields, cm=piece["fingerprint_commitment"])
                if _sha256(canonical_json(with_cm)).hex() == r["record_hash"]:
                    signed_fields = with_cm
            out.append({
                # Canonical JSON of these fields is what gets hashed.
                "signed_fields": signed_fields,
                "record_hash": r["record_hash"],
                "signature": r["signature"],
                "signer": {
                    "name": signer["name"] if signer else None,
                    "public_key": signer["public_key"] if signer else None,
                },
                "merkle": get_inclusion_proof(r["record_hash"]),
            })

        valid, reason, _ = verify_chain_detailed(piece["id"])
        return {
            "certificate_code": piece["certificate_code"],
            "piece_id": piece["id"],
            "algorithms": {
                "hash": "SHA-256 over canonical JSON (sorted keys, no whitespace)",
                "signature": "Ed25519 over the raw 32-byte record hash",
                "merkle": "SHA-256 binary tree, 0x00 leaf prefix / 0x01 node prefix, last node duplicated when odd",
                "genesis_prev_hash": GENESIS_HASH,
            },
            "records": out,
            "server_verdict": {"verified": valid, "reason": reason},
        }
    finally:
        conn.close()

# ---------- Public integration API ----------

@app.get("/api/verify/{code}", tags=["Public API"], summary="Verify a certificate by code")
def api_verify(code: str):
    """One-call authenticity check for third-party sites.

    Returns a plain-language verdict plus the piece's full ownership history —
    no API key, no cryptographic internals to parse. Integrators who want to
    re-verify the cryptography themselves should use /c/{code}/proof instead.
    """
    conn = get_db()
    try:
        piece = _load_certificate(conn, code)

        maker = conn.execute("SELECT name FROM users WHERE id = ?", (piece["made_by"],)).fetchone()
        records = conn.execute(
            "SELECT * FROM custody_records WHERE piece_id = ? ORDER BY seq_index ASC", (piece["id"],)
        ).fetchall()
        valid, reason, _ = verify_chain_detailed(piece["id"])

        holder = None
        if piece["current_owner_id"]:
            h = conn.execute("SELECT name, shop_name FROM users WHERE id = ?", (piece["current_owner_id"],)).fetchone()
            if h:
                holder = h["shop_name"] or h["name"]
        elif records:
            # The piece left the CraftProof account system — sold to an
            # external buyer, including every ReMarket import. The last
            # recorded name is the holder; reporting None here would have
            # made a marketplace sale look like the piece had vanished.
            holder = records[-1]["to_name"]

        marketplace = remarket.import_for_piece(conn, piece["id"])

        history = []
        anchored = 0
        for r in records:
            frm = conn.execute("SELECT name FROM users WHERE id = ?", (r["from_user_id"],)).fetchone()
            from_name = frm["name"] if frm else "Unknown"
            to = conn.execute("SELECT name, shop_name FROM users WHERE id = ?", (r["to_user_id"],)).fetchone() if r["to_user_id"] else None
            to_name = (to["shop_name"] or to["name"]) if to else (r["to_name"] or "Unknown")
            event = f"Created by {from_name}" if r["seq_index"] == 0 else f"{from_name} → {to_name}"
            inclusion = get_inclusion_proof(r["record_hash"])
            if inclusion and inclusion["included"]:
                anchored += 1
            history.append({
                "date": r["timestamp"],
                "event": event,
                "note": r["note"] or None,
            })

        return {
            "certificate_code": piece["certificate_code"],
            "authentic": valid,
            "reason": None if valid else reason,
            "piece": {
                "title": piece["title"],
                "description": piece["description"],
                "materials": piece["materials"],
                "maker": maker["name"] if maker else None,
                "created_at": records[0]["timestamp"] if records else None,
            },
            "current_holder": holder,
            "history": history,
            "ledger": {
                "records": len(records),
                "anchored": anchored,
            },
            # Present when the latest holder came from a marketplace sale
            # rather than a custodian-confirmed handover. Partners should
            # surface the distinction rather than hide it.
            "marketplace": (
                {
                    "source": "ReMarket",
                    "order_id": marketplace["order_id"],
                    "buyer_name": marketplace["buyer_name"],
                    "sold_at": marketplace["completed_at"],
                    "recorded_at": marketplace["imported_at"],
                    "reported_by_marketplace": True,
                }
                if marketplace else None
            ),
            "verify_url": f"/c/{piece['certificate_code']}",
        }
    finally:
        conn.close()

# ---------- Public ledger (Merkle checkpoints) ----------

@app.get("/ledger/checkpoints")
def get_checkpoints():
    return list_checkpoints()

@app.post("/ledger/checkpoint")
def publish_checkpoint():
    """Seal every record so far under a single Merkle root, and anchor it.

    Anchoring (anchoring.py, plan W6) is what turns a locally stored root
    into PUBLIC evidence: the local backend signs it with an Ed25519 journal
    key whose private half never lives in the custody database; the freetsa
    backend gets an RFC 3161 token from an independent TSA. The checkpoint
    below reports whether the anchor step succeeded.
    """
    result = create_checkpoint()
    if result is None:
        raise HTTPException(status_code=400, detail="Nothing to checkpoint yet")
    if result.get("new", False):
        import anchoring
        receipt = anchoring.anchor_root(result["root_hash"], result["batch_index"],
                                       result["record_count"])
        result["anchor"] = {
            "backend": receipt["backend"],
            "anchored_at": receipt["anchored_at"],
        }
        if receipt["backend"] == "local":
            result["anchor"]["verifiable"] = anchoring.verify_receipt(receipt)
    return result

# ---------- Tamper endpoint (demo discipline) ----------

@app.post("/admin/tamper/{piece_id}/{seq_index}")
def tamper_record(piece_id: int, seq_index: int, new_note: str = "FORGED"):
    """Demo-only: directly alter a record's note without updating the hash/signature.

    Deliberately refused unless the server is running in insecure-demo mode —
    this endpoint exists for the viva tamper demonstration and would otherwise
    hand every visitor a free database-write primitive (CWE-306).
    """
    if not _DEMO_MODE_ACTIVE:
        raise HTTPException(
            status_code=403,
            detail="Demo-only endpoint — enable insecure demo mode (CRAFTPROOF_ALLOW_INSECURE_DEMO=true) to use it",
        )
    conn = get_db()
    try:
        conn.execute(
            "UPDATE custody_records SET note = ? WHERE piece_id = ? AND seq_index = ?",
            (new_note, piece_id, seq_index)
        )
        conn.commit()
        return {"status": "tampered", "message": f"Record {seq_index} of piece {piece_id} altered to: '{new_note}'"}
    finally:
        conn.close()
