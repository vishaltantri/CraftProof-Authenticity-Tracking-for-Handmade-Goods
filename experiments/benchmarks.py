#!/usr/bin/env python3
"""CraftProof 2.0 benchmark + scaling generator (plan W7 / experiments E5+E6).

One command runs the full E5/E6 matrix and writes machine-readable results:

    cd craftproof/backend
    python3 ../experiments/benchmarks.py --tiers 1000 10000 --out ../experiments/results/e5e6.csv
    python3 ../experiments/benchmarks.py --tiers 1000 --ops timed     # E5 only
    python3 ../experiments/benchmarks.py --tiers 1000 --ops scaling   # E6 only

E5 — latency of the core operations (p50/p95) at a fixed, small DB size:
  registration (piece + genesis), transfer, certificate page render,
  fingerprint enrol, fingerprint verify, checkpoint build, anchor publish,
  independent verify (proof fetch + local re-check).

E6 — scaling with DB size: fill the database with N synthetic custody
records (seeded generator, thousands of pieces hopping maker→seller→buyer)
and measure, per tier: worst-case certificate render (a tail-of-chain
piece), Merkle proof path length + JSON size, checkpoint build time and
root, anchor publish cost, template lookup (index by piece_id vs a linear
scan ablation over a fingerprint-carrying subset).

Everything writes to one CSV: tier,op,p50_ms,p95_ms,n_bytes,extra + a
human-readable printed table. Wall time only (laptop-class machine is the
plan's stated baseline); CPU time is captured in the extra column when the
op is CPU-bound.

Deterministic: records are generated from a fixed seed (1234), same data
every run.
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from pathlib import Path
from typing import Callable

BACKEND = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND))

SEED = 1234
CSV_HEADER = "tier,op,p50_ms,p95_ms,n_bytes,extra\n"

# --------------------------------------------------------------------- helpers


class Timer:
    """p50/p95 wall-time collector for one op."""

    def __init__(self):
        self.samples_ms: list[float] = []

    def run(self, fn: Callable[[], object], times: int = 15):
        for _ in range(times):
            t0 = time.perf_counter()
            fn()
            self.samples_ms.append((time.perf_counter() - t0) * 1000)
        return self

    def row(self, tier, op: str) -> dict:
        s = sorted(self.samples_ms)
        return {
            "tier": tier,
            "op": op,
            "p50_ms": round(statistics.median(s), 3),
            "p95_ms": round(s[max(0, int(len(s) * 0.95) - 1)] if s else 0, 3),
            "n": len(s),
        }


def _fresh_db(home: Path):
    for mod in ("database", "record", "core", "merkle", "crypto_utils",
                "fingerprint", "clone_detection", "anchoring"):
        sys.modules.pop(mod, None)
    os.environ["CRAFTPROOF_DB"] = str(home / "bench.db")
    os.environ["CRAFTPROOF_TEMPLATES_DIR"] = str(home / "templates")
    os.environ["CRAFTPROOF_ANCHOR_KEY"] = str(home / "anchor_key.pem")
    os.environ["CRAFTPROOF_ANCHOR_JOURNAL"] = str(home / "journal.jsonl")
    import database
    database.init_db()
    return home


# ------------------------------------------------------- synthetic fill (E6)

def fill_database(n_records: int) -> dict:
    """Seed a synthetic custody workload: pieces each with 1–3 hops, all
    honestly signed by freshly generated (throwaway) keypairs. Fills until
    the custody_records table holds at least n_records rows; returns stats.
    """
    # Fresh seeded RNG → identical workload every run.
    import random as _r
    rng = _r.Random(SEED)

    from database import get_db
    from crypto_utils import generate_keypair, sign, pubkey_to_hex
    from cryptography.hazmat.primitives import serialization
    from record import CustodyRecord, GENESIS_HASH
    import string as _s

    conn = get_db()
    c = conn.cursor()
    # A pool of 40 makers/sellers/buyers gets reused everywhere (realistic
    # community); bulk-insert users first — user rows are cheap, records are
    # what we are scaling.
    users: list[tuple[int, object]] = []
    for i in range(40):
        sk, pk = generate_keypair()
        email = f"user{i}-{SEED}@bench"
        c.execute(
            "INSERT INTO users (name, email, password_hash, role, public_key, encrypted_privkey)"
            " VALUES (?, ?, 'x', 'maker', ?, ?)",
            (f"User{i}", email, pubkey_to_hex(pk),
             sk.private_bytes(encoding=serialization.Encoding.Raw,
                              format=serialization.PrivateFormat.Raw,
                              encryption_algorithm=serialization.NoEncryption()).hex()))
        users.append((c.lastrowid, sk))
    conn.commit()

    def mk_code():
        return "".join(rng.choices(_s.ascii_uppercase + _s.digits, k=8))

    pieces = 0
    records = conn.execute("SELECT COUNT(*) FROM custody_records").fetchone()[0]
    batch_codes: list[tuple[str, int]] = []
    while records < n_records:
        # Batch 200 pieces per transaction — SQLite commits dominate otherwise.
        for _ in range(200):
            maker_id, maker_sk = users[rng.randrange(0, 20)]
            seller_id, seller_sk = users[20 + rng.randrange(0, 20)]
            code = mk_code()
            c.execute("INSERT INTO pieces (certificate_code, title, made_by, current_owner_id)"
                      " VALUES (?, 'Bench piece', ?, ?)", (code, maker_id, maker_id))
            piece_id = c.lastrowid

            hops = rng.choice([1, 2, 2, 3])
            prev = GENESIS_HASH
            holder_id, holder_sk = maker_id, maker_sk
            buyer_name = f"Buyer {rng.randrange(10000)}"
            for seq in range(hops + 1):
                if seq < hops:
                    to_id = seller_id if seq == hops - 1 else maker_id
                    to_name = None
                    note = "Delivered to the gallery" if to_id == seller_id else "Returned for rework"
                else:
                    to_id, to_name, note = None, buyer_name, "Sold to a walk-in buyer"
                rec = CustodyRecord(piece_id, seq, holder_id, to_id, to_name, note, prev)
                h = rec.compute_hash()
                c.execute(
                    "INSERT INTO custody_records (piece_id, seq_index, from_user_id, to_user_id,"
                    " to_name, note, timestamp, prev_hash, record_hash, signature)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (piece_id, seq, holder_id, to_id, to_name, note, rec.timestamp, prev, h,
                     sign(holder_sk, bytes.fromhex(h)).hex()))
                prev = h
                if to_id is not None:
                    holder_id = to_id
            records += hops + 1
            pieces += 1
            batch_codes.append((code, piece_id))
        conn.commit()
    conn.close()
    return {"pieces": pieces, "records": records, "sample": batch_codes[:5]}


# ------------------------------------------------------------- E5 operations

def run_e5(out_rows: list[dict]) -> None:
    from database import get_db
    from core import create_checkpoint
    from merkle import MerkleTree
    import anchoring
    import fingerprint as fp
    from PIL import Image
    import numpy as np
    import base64

    t_reg, t_transfer, t_render, t_enrol, t_verify = (Timer() for _ in range(5))
    t_ckpt, t_anchor, t_iverify = (Timer() for _ in range(3))

    conn = get_db()
    conn.execute("INSERT INTO users (name, email, password_hash, role, public_key, encrypted_privkey)"
                 " VALUES ('_timer-m', 'timer-m@e5', 'x', 'maker', 'aa', 'bb')")
    conn.execute("INSERT INTO users (name, email, password_hash, role, public_key, encrypted_privkey)"
                 " VALUES ('timer-s', 'timer-s@e5', 'x', 'seller', 'aa', 'bb')")
    uid_m, uid_s = [r["id"] for r in conn.execute("SELECT id FROM users WHERE email LIKE 'timer-%'")]
    conn.commit()
    conn.close()
    # Regenerate real keypair material: registration signs with _seed_user's
    # envelope path, so manufacture the users the way fill_database does.
    from crypto_utils import generate_keypair, pubkey_to_hex
    from cryptography.hazmat.primitives import serialization
    conn = get_db()
    skm, pkm = generate_keypair()
    sks, pks = generate_keypair()
    sk_hex_s = sks.private_bytes(encoding=serialization.Encoding.Raw,
                                 format=serialization.PrivateFormat.Raw,
                                 encryption_algorithm=serialization.NoEncryption()).hex()
    conn.execute("UPDATE users SET public_key=?, encrypted_privkey=? WHERE id=?",
                 (pubkey_to_hex(pkm),
                  skm.private_bytes(encoding=serialization.Encoding.Raw,
                                    format=serialization.PrivateFormat.Raw,
                                    encryption_algorithm=serialization.NoEncryption()).hex(), uid_m))
    conn.execute("UPDATE users SET public_key=?, encrypted_privkey=? WHERE id=?",
                 (pubkey_to_hex(pks), sk_hex_s, uid_s))
    conn.commit()
    conn.close()

    from record import CustodyRecord, GENESIS_HASH
    from crypto_utils import sign
    piece_seq = [0]

    def _register():
        n = piece_seq[0]
        piece_seq[0] += 1
        conn = get_db()
        code = f"E5{n:07X}"
        c = conn.cursor()
        c.execute("INSERT INTO pieces (certificate_code, title, description, materials,"
                  " made_by, current_owner_id) VALUES (?, ?, ?, ?, ?, ?)",
                  (code, "Bench", "bench piece", "materials", uid_m, uid_m))
        rec = CustodyRecord(c.lastrowid, 0, uid_m, uid_m, "Self", "Piece created", GENESIS_HASH)
        h = rec.compute_hash()
        sig = sign(skm, bytes.fromhex(h)).hex()
        c.execute("INSERT INTO custody_records (piece_id, seq_index, from_user_id, to_user_id,"
                  " to_name, note, timestamp, prev_hash, record_hash, signature)"
                  " VALUES (?, 0, ?, ?, 'Self', ?, ?, ?, ?, ?)",
                  (c.lastrowid, uid_m, uid_m, rec.note, rec.timestamp, GENESIS_HASH, h, sig))
        conn.commit()
        conn.close()
        return code

    t_reg.run(lambda: _register(), times=30)

    # Transfer: real signed move of a piece maker → seller.
    def _transfer():
        conn = get_db()
        row = conn.execute(
            "SELECT id, certificate_code FROM pieces WHERE made_by=? ORDER BY id DESC LIMIT 1",
            (uid_m,)).fetchone()
        pid = row["id"]
        owner_row = conn.execute("SELECT current_owner_id FROM pieces WHERE id=?", (pid,)).fetchone()
        if owner_row["current_owner_id"] == uid_m:
            from_id, sk_from = uid_m, skm
        else:
            from_id, sk_from = uid_s, sks
        prev = conn.execute("SELECT record_hash FROM custody_records WHERE piece_id=?"
                            " ORDER BY seq_index DESC LIMIT 1", (pid,)).fetchone()[0]
        seq = conn.execute("SELECT COALESCE(MAX(seq_index)+1, 0) FROM custody_records"
                           " WHERE piece_id=?", (pid,)).fetchone()[0]
        rec = CustodyRecord(pid, seq, from_id, uid_s, None, "Bench transfer", prev)
        h = rec.compute_hash()
        conn.execute("INSERT INTO custody_records (piece_id, seq_index, from_user_id, to_user_id,"
                     " to_name, note, timestamp, prev_hash, record_hash, signature)"
                     " VALUES (?, ?, ?, ?, 'timer-s', ?, ?, ?, ?, ?)",
                     (pid, seq, from_id, uid_s, rec.note, rec.timestamp, prev, h,
                      sign(sk_from, bytes.fromhex(h)).hex()))
        conn.execute("UPDATE pieces SET current_owner_id=? WHERE id=?", (uid_s, pid))
        conn.commit()
        conn.close()

    t_transfer.run(_transfer, times=20)

    # Cert-page render: worst case is the deepest chains, so render the
    # piece with the most custody records.
    conn = get_db()
    deep = conn.execute(
        "SELECT piece_id, COUNT(*) c FROM custody_records GROUP BY piece_id ORDER BY c DESC LIMIT 1"
    ).fetchone()
    conn.close()
    # Reuse core logic without spinning up the HTTP layer.
    from core import verify_chain_detailed
    deep_pid = deep["piece_id"] if deep else 1

    t_render.run(lambda: verify_chain_detailed(deep_pid), times=20)

    # Fingerprint enrol / verify (synthetic 1-image template, 96px).
    rng = np.random.default_rng(7)
    img = Image.fromarray(rng.integers(0, 255, (96, 96, 3)).astype("uint8"), "RGB")
    probe = fp.build_template([img])

    def _enrol():
        conn = get_db()
        target = conn.execute("SELECT MAX(id) m FROM pieces WHERE made_by=?", (uid_m,)).fetchone()["m"]
        conn.close()
        fp.store_template(target or 1, probe)

    t_enrol.run(_enrol, times=10)

    def _fpverify():
        fp.template_similarity(probe, probe)

    t_verify.run(_fpverify, times=20)

    # Checkpoint build (an op that grows with DB size — see E6 tiers too).
    t_ckpt.run(lambda: create_checkpoint(), times=8)

    def _anchor():
        from core import list_checkpoints
        cps = list_checkpoints()
        newest = cps[0]
        anchoring.anchor_root(newest["root_hash"], newest["batch_index"], newest["record_count"])

    t_anchor.run(_anchor, times=8)

    # Independent verify: inclusion proof + Merkle re-verify, payload size.
    from core import get_inclusion_proof
    conn = get_db()
    some_hash = conn.execute("SELECT record_hash FROM custody_records LIMIT 1").fetchone()[0]
    conn.close()
    proof = get_inclusion_proof(some_hash)
    t_iverify.run(lambda: MerkleTree.verify_proof(
        some_hash, [(p["hash"], p["side"]) for p in proof["proof"]], proof["root_hash"]),
        times=20)

    rows = [
        t_reg.row("baseline", "registration"),
        t_transfer.row("baseline", "transfer"),
        t_render.row("baseline", "certificate_render"),
        t_enrol.row("baseline", "fingerprint_enrol"),
        t_verify.row("baseline", "fingerprint_verify"),
        t_ckpt.row("baseline", "checkpoint_build"),
        t_anchor.row("baseline", "anchor_publish"),
        t_iverify.row("baseline", "independent_verify"),
    ]
    out_rows.extend(rows)
    if proof:
        out_rows[-1]["n_bytes"] = len(json.dumps(proof).encode())


# ------------------------------------------------------------- E6 scaling ops

def run_e6(tier_records: int, out_rows: list[dict]) -> None:
    from database import get_db
    from core import create_checkpoint, get_inclusion_proof, verify_chain_detailed
    from merkle import MerkleTree
    import anchoring
    import fingerprint as fp
    import tempfile

    filled = fill_database(tier_records)
    tier = filled["records"]

    # (a) worst-case certificate render: deepest chain.
    conn = get_db()
    deep = conn.execute(
        "SELECT piece_id, COUNT(*) c FROM custody_records GROUP BY piece_id ORDER BY c DESC LIMIT 1"
    ).fetchone()
    conn.close()
    t = Timer().run(lambda: verify_chain_detailed(deep["piece_id"]), times=10)
    row = t.row(tier, "certificate_render")
    row["extra"] = f"max_hops={deep['c']}"
    out_rows.append(row)

    # (b) checkpoint build + root + one fresh inclusion proof on the full tree.
    t = Timer().run(lambda: create_checkpoint(), times=6)
    row = t.row(tier, "checkpoint_build")
    import core
    cps = core.list_checkpoints()
    newest = cps[0]
    conn = get_db()
    try:
        leaves = core._all_record_hashes(conn)
        tree = MerkleTree(leaves)
        proof0 = tree.get_proof(0)
        row["extra"] = f"root={newest['root_hash'][:12]}… depth={len(proof0)} leaves={len(leaves)}"
    finally:
        conn.close()
    out_rows.append(row)

    # (c) Merkle proof payload + verify at this scale.
    conn = get_db()
    tail = conn.execute("SELECT record_hash FROM custody_records ORDER BY id DESC LIMIT 1").fetchone()[0]
    conn.close()
    t = Timer().run(lambda: get_inclusion_proof(tail), times=5)
    row = t.row(tier, "inclusion_proof_fetch")
    proof = get_inclusion_proof(tail)
    ok = MerkleTree.verify_proof(tail, [(p["hash"], p["side"]) for p in proof["proof"]],
                                 proof["root_hash"])
    row["n_bytes"] = len(json.dumps(proof).encode())
    row["extra"] = f"proof_ok={ok} path_len={len(proof['proof'])}"
    out_rows.append(row)

    # (d) anchor publish on the tier-scale root.
    def _anchor():
        cps = core.list_checkpoints()
        anchoring.anchor_root(cps[0]["root_hash"], cps[0]["batch_index"], cps[0]["record_count"])

    t = Timer().run(_anchor, times=3)
    receipt = anchoring.latest_receipt_for(newest["root_hash"])
    row = t.row(tier, "anchor_publish")
    row["extra"] = f"backend={anchoring.BACKEND} verified={anchoring.verify_receipt(receipt)}"
    out_rows.append(row)

    # (e) template lookup: indexed vs linear ablation, on a small
    # fingerprint-carrying subset so the file store stays meaningful.
    t = Timer().run(lambda: fp.load_template_by_piece(1), times=10)
    out_rows.append(t.row(tier, "template_lookup_indexed"))
    # Linear scan ablation over template files (filesystem cost bound).
    import glob
    files = glob.glob(os.path.join(os.environ["CRAFTPROOF_TEMPLATES_DIR"], "*.json"))

    def _linear():
        for f in files[:50]:
            with open(f, "rb") as fh:
                fh.read(64)

    t = Timer().run(_linear, times=10)
    row = t.row(tier, "template_lookup_linear_ablation")
    row["extra"] = f"templates_dir_entries={len(files)}"
    out_rows.append(row)


# ------------------------------------------------------------------- output

def print_table(rows: list[dict]) -> None:
    print(f"\n{'tier':<10} {'op':<30} {'p50 ms':>10} {'p95 ms':>10}  {'bytes':>9}  extra")
    print("-" * 100)
    for r in rows:
        print(f"{str(r['tier']):<10} {r['op']:<30} {r['p50_ms']:>10.2f} {r['p95_ms']:>10.2f}"
              f"  {r.get('n_bytes') or '':>9}  {r.get('extra') or ''}")


def main() -> None:
    ap = argparse.ArgumentParser(description="CraftProof 2.0 benchmarks (E5/E6)")
    ap.add_argument("--tiers", type=int, nargs="+", default=[1000])
    ap.add_argument("--ops", choices=["all", "timed", "scaling"], default="all")
    ap.add_argument("--out", default=None, help="CSV path for results")
    args = ap.parse_args()

    out_rows: list[dict] = []
    import tempfile
    with tempfile.TemporaryDirectory(prefix="craftproof-bench-") as home:
        _fresh_db(Path(home))
        if args.ops in ("all", "timed"):
            run_e5(out_rows)
        if args.ops in ("all", "scaling"):
            for tier in args.tiers:
                run_e6(tier, out_rows)

    print_table(out_rows)

    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        with open(args.out, "w", encoding="utf-8", newline="") as fh:
            fh.write(CSV_HEADER)
            for r in out_rows:
                fh.write(",".join(str(r.get(k, "")) for k in
                                  ("tier", "op", "p50_ms", "p95_ms", "n_bytes", "extra")) + "\n")
        print(f"\nCSV -> {args.out}")


if __name__ == "__main__":
    main()
