"""Tests for the partner-facing public API additions.

Run with:  python3 -m unittest -v test_public_api

Covers the seller/holder check and the embeddable SVG badge. Both are served
to anonymous callers and embedded in other people's pages, so the properties
that matter are: they never overstate what CraftProof knows, and they never
hand an attacker a way to inject markup into a partner's site.
"""

import os
import tempfile
import unittest

from fastapi.testclient import TestClient
from cryptography.hazmat.primitives import serialization

import database
import remarket
from crypto_utils import generate_keypair, pubkey_to_hex, sign
from database import get_db
from record import CustodyRecord, GENESIS_HASH


class PublicApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory(prefix="craftproof-publicapi-")
        cls._old_db = database.DB_PATH
        database.DB_PATH = os.path.join(cls._tmp.name, "craftproof.db")
        os.environ.setdefault("CRAFTPROOF_ALLOW_INSECURE_DEMO", "true")
        database.init_db()

        import main
        cls.main = main
        # Drive the routes directly; lifespan would seed demo data and start
        # the ReMarket poller, neither of which these tests want.
        cls.client = TestClient(main.app)

    @classmethod
    def tearDownClass(cls):
        database.DB_PATH = cls._old_db
        cls._tmp.cleanup()

    def setUp(self):
        self.code = self._make_piece()

    def _make_piece(self, title="Speckled tea bowl set", holder_name="Maya Iyer"):
        sk, pk = generate_keypair()
        seed_hex = sk.private_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PrivateFormat.Raw,
            encryption_algorithm=serialization.NoEncryption(),
        ).hex()
        import secrets
        code = secrets.token_hex(4).upper()
        conn = get_db()
        try:
            maker_id = conn.execute(
                "INSERT INTO users (name, email, password_hash, role, public_key, encrypted_privkey) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (holder_name, f"{code}@test.local", "unused", "maker", pubkey_to_hex(pk), seed_hex),
            ).lastrowid
            piece_id = conn.execute(
                "INSERT INTO pieces (certificate_code, title, made_by, current_owner_id) "
                "VALUES (?, ?, ?, ?)",
                (code, title, maker_id, maker_id),
            ).lastrowid
            rec = CustodyRecord(piece_id, 0, maker_id, maker_id, "Self", "Piece created", GENESIS_HASH)
            h = rec.compute_hash()
            conn.execute(
                "INSERT INTO custody_records (piece_id, seq_index, from_user_id, to_user_id, "
                "to_name, note, timestamp, prev_hash, record_hash, signature) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (piece_id, 0, maker_id, maker_id, "Self", rec.note, rec.timestamp,
                 GENESIS_HASH, h, sign(sk, bytes.fromhex(h)).hex()),
            )
            conn.commit()
            return code
        finally:
            conn.close()

    # -------------------------------------------------- seller / holder check

    def test_matching_seller_name_is_reported_as_a_match(self):
        r = self.client.get(f"/api/verify/{self.code}/holder", params={"name": "Maya Iyer"})
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertTrue(body["matches"])
        self.assertTrue(body["authentic"])
        self.assertEqual(body["current_holder"], "Maya Iyer")
        self.assertIn("not an identity check", body["verdict"])

    def test_name_comparison_ignores_case_and_spacing(self):
        r = self.client.get(f"/api/verify/{self.code}/holder",
                            params={"name": "  maya   IYER "})
        self.assertTrue(r.json()["matches"])

    def test_different_seller_name_is_reported_as_a_mismatch(self):
        r = self.client.get(f"/api/verify/{self.code}/holder", params={"name": "Someone Else"})
        body = r.json()
        self.assertFalse(body["matches"])
        self.assertIn("Maya Iyer", body["verdict"])

    def test_unverifiable_chain_answers_unknown_not_mismatch(self):
        """A broken chain must not be reported as 'the seller is wrong'.

        matches=None means CraftProof cannot answer. Collapsing that to False
        would accuse a seller on the strength of a database problem.
        """
        conn = get_db()
        try:
            piece = conn.execute("SELECT id FROM pieces WHERE certificate_code = ?",
                                 (self.code,)).fetchone()
            conn.execute("UPDATE custody_records SET note = ? WHERE piece_id = ?",
                         ("FORGED", piece["id"]))
            conn.commit()
        finally:
            conn.close()

        body = self.client.get(f"/api/verify/{self.code}/holder",
                               params={"name": "Maya Iyer"}).json()
        self.assertIsNone(body["matches"])
        self.assertFalse(body["authentic"])
        self.assertIn("does not currently verify", body["verdict"])

    def test_unknown_certificate_is_a_404(self):
        r = self.client.get("/api/verify/NOSUCH00/holder", params={"name": "Anyone"})
        self.assertEqual(r.status_code, 404)

    def test_name_is_required(self):
        self.assertEqual(
            self.client.get(f"/api/verify/{self.code}/holder").status_code, 422)

    # ------------------------------------------------------------------ badge

    def test_badge_is_an_svg_image(self):
        r = self.client.get(f"/badge/{self.code}.svg")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.headers["content-type"], "image/svg+xml")
        self.assertTrue(r.text.lstrip().startswith("<svg"))
        self.assertIn("Verified by CraftProof", r.text)
        self.assertIn("Speckled tea bowl set", r.text)

    def test_badge_is_embeddable_cross_origin_and_not_cached_for_long(self):
        r = self.client.get(f"/badge/{self.code}.svg")
        self.assertEqual(r.headers["access-control-allow-origin"], "*")
        self.assertIn("max-age=60", r.headers["cache-control"])

    def test_badge_for_an_unknown_code_says_so_instead_of_erroring(self):
        r = self.client.get("/badge/NOSUCH00.svg")
        self.assertEqual(r.status_code, 200)
        self.assertIn("Not found", r.text)

    def test_badge_goes_red_when_the_record_is_altered(self):
        conn = get_db()
        try:
            piece = conn.execute("SELECT id FROM pieces WHERE certificate_code = ?",
                                 (self.code,)).fetchone()
            conn.execute("UPDATE custody_records SET note = ? WHERE piece_id = ?",
                         ("FORGED", piece["id"]))
            conn.commit()
        finally:
            conn.close()
        r = self.client.get(f"/badge/{self.code}.svg")
        self.assertIn("Not verified", r.text)
        self.assertNotIn("Verified by CraftProof", r.text)

    def test_badge_escapes_a_piece_title_that_contains_markup(self):
        """The title is user input and the badge is embedded in other sites.

        An unescaped title would let whoever registers a piece inject markup
        into every partner page that embeds its badge.
        """
        code = self._make_piece(title='</text><script>alert(1)</script>')
        body = self.client.get(f"/badge/{code}.svg").text
        self.assertNotIn("<script>", body)
        self.assertIn("&lt;", body)

    def test_compact_badge_style(self):
        r = self.client.get(f"/badge/{self.code}.svg", params={"style": "compact"})
        self.assertEqual(r.status_code, 200)
        self.assertIn("Verified", r.text)

    def test_unknown_badge_style_is_rejected(self):
        self.assertEqual(
            self.client.get(f"/badge/{self.code}.svg", params={"style": "huge"}).status_code,
            422)


if __name__ == "__main__":
    unittest.main(verbosity=2)
