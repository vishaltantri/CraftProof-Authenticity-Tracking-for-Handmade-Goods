"""Run with: python -m unittest -v test_remarket"""

import os
import tempfile
import unittest
from unittest.mock import patch

import httpx
from cryptography.hazmat.primitives import serialization

import database
from core import create_checkpoint, get_inclusion_proof, verify_chain_detailed
from crypto_utils import generate_keypair, sign
from database import get_db
from record import CustodyRecord, GENESIS_HASH
from remarket import import_sale, sync_sales


class ReMarketImportTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="craftproof-remarket-test-")
        self.original_path = database.DB_PATH
        database.DB_PATH = os.path.join(self.temporary.name, "craftproof.db")
        database.init_db()

        private_key, public_key = generate_keypair()
        private_hex = private_key.private_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PrivateFormat.Raw,
            encryption_algorithm=serialization.NoEncryption(),
        ).hex()
        public_hex = public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        ).hex()
        conn = get_db()
        try:
            maker_id = conn.execute(
                """INSERT INTO users (name, email, password_hash, role, public_key, encrypted_privkey)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                ("Maker", "maker@test.local", "unused", "maker", public_hex, private_hex),
            ).lastrowid
            self.piece_id = conn.execute(
                """INSERT INTO pieces (certificate_code, title, made_by, current_owner_id)
                   VALUES (?, ?, ?, ?)""",
                ("TESTCODE", "mackbook", maker_id, maker_id),
            ).lastrowid
            record = CustodyRecord(self.piece_id, 0, maker_id, maker_id,
                                   "Self", "Piece created", GENESIS_HASH)
            record_hash = record.compute_hash()
            conn.execute(
                """INSERT INTO custody_records
                   (piece_id, seq_index, from_user_id, to_user_id, to_name, note,
                    timestamp, prev_hash, record_hash, signature)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (self.piece_id, 0, maker_id, maker_id, "Self", "Piece created",
                 record.timestamp, GENESIS_HASH, record_hash,
                 sign(private_key, bytes.fromhex(record_hash)).hex()),
            )
            conn.commit()
        finally:
            conn.close()
        create_checkpoint()

    def tearDown(self):
        database.DB_PATH = self.original_path
        self.temporary.cleanup()

    @staticmethod
    def sale(title="mackbook"):
        return {
            "order_id": "RM-000002",
            "certificate_code": "TESTCODE",
            "item_title": title,
            "buyer_name": "Sample Buyer",
            "status": "completed",
        }

    @staticmethod
    def client_for(sale):
        def respond(request):
            assert request.url.path == "/api/v1/sales"
            return httpx.Response(200, json={"sales": [sale], "next_after_id": 2})
        return httpx.Client(base_url="http://remarket.test",
                            transport=httpx.MockTransport(respond))

    def test_matching_sale_is_signed_and_imported_once(self):
        sale = self.sale()
        with patch("remarket.remarket_client", return_value=self.client_for(sale)):
            first = sync_sales()
        with patch("remarket.remarket_client", return_value=self.client_for(sale)):
            repeat = sync_sales()
        self.assertEqual(first["imported"], 1)
        self.assertEqual(repeat["already_imported"], 1)

        conn = get_db()
        try:
            imports = conn.execute("SELECT COUNT(*) FROM remarket_imports").fetchone()[0]
            record = conn.execute(
                "SELECT to_name, record_hash FROM custody_records WHERE piece_id=? ORDER BY seq_index DESC LIMIT 1",
                (self.piece_id,),
            ).fetchone()
        finally:
            conn.close()
        self.assertEqual(imports, 1)
        self.assertEqual(record["to_name"], "Sample Buyer")
        self.assertTrue(verify_chain_detailed(self.piece_id)[0])
        self.assertIsNotNone(get_inclusion_proof(record["record_hash"]))

    def test_mismatched_title_cannot_change_certificate(self):
        self.assertEqual(import_sale(self.sale("iPhone 18 pro")), "item_title_mismatch")
        conn = get_db()
        try:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM remarket_imports").fetchone()[0], 0)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM custody_records WHERE piece_id=?",
                                          (self.piece_id,)).fetchone()[0], 1)
        finally:
            conn.close()

    def test_next_sync_repairs_missing_checkpoint(self):
        sale = self.sale()
        with patch("remarket.remarket_client", return_value=self.client_for(sale)):
            with patch("remarket.create_checkpoint", side_effect=RuntimeError("interrupted")):
                with self.assertRaisesRegex(RuntimeError, "interrupted"):
                    sync_sales()

        conn = get_db()
        try:
            record_hash = conn.execute(
                "SELECT record_hash FROM custody_records WHERE piece_id=? ORDER BY seq_index DESC LIMIT 1",
                (self.piece_id,),
            ).fetchone()[0]
        finally:
            conn.close()
        self.assertIsNone(get_inclusion_proof(record_hash))

        with patch("remarket.remarket_client", return_value=self.client_for(sale)):
            retry = sync_sales()
        self.assertEqual(retry["already_imported"], 1)
        self.assertIsNotNone(get_inclusion_proof(record_hash))


if __name__ == "__main__":
    unittest.main()
