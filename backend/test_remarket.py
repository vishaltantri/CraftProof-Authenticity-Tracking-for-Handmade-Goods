"""Tests for the ReMarket sale importer.

Run with:  python3 -m unittest -v test_remarket

Every test runs against a throwaway database and a mocked ReMarket transport,
so nothing here touches the partner's real service or its API key.

The properties under test are the ones that make the integration safe to point
at a live certificate store:

  * a matching sale appends exactly one signed, verifiable custody record
  * replaying the feed never duplicates it
  * a title that disagrees with the certificate changes nothing
  * an unknown certificate code changes nothing
  * a skipped sale holds the poll cursor so it is retried, not lost
  * an interrupted run repairs its missing checkpoint on the next sync
"""

import os
import tempfile
import unittest
from unittest.mock import patch

import httpx
from cryptography.hazmat.primitives import serialization

import database
import remarket
from core import create_checkpoint, get_inclusion_proof, verify_chain_detailed
from crypto_utils import generate_keypair, pubkey_to_hex, sign
from database import get_db
from record import CustodyRecord, GENESIS_HASH


def _sale(order_id="RM-000002", title="Speckled tea bowl set", code="TESTCODE",
          buyer="Asha Rao", status="completed"):
    return {
        "order_id": order_id,
        "certificate_code": code,
        "item_title": title,
        "buyer_name": buyer,
        "status": status,
        "completed_at": "2026-10-14T12:00:00+00:00",
    }


class ReMarketImportTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="craftproof-remarket-")
        self.addCleanup(self._tmp.cleanup)

        # Point both the database and the integration signing key at the
        # temporary directory, and restore them afterwards.
        self._old_db = database.DB_PATH
        database.DB_PATH = os.path.join(self._tmp.name, "craftproof.db")
        self.addCleanup(lambda: setattr(database, "DB_PATH", self._old_db))

        self._old_key = remarket._KEY_FILE
        remarket._KEY_FILE = os.path.join(self._tmp.name, "remarket_signer.key")
        self.addCleanup(lambda: setattr(remarket, "_KEY_FILE", self._old_key))

        database.init_db()
        self.piece_id = self._seed_piece()
        create_checkpoint()

    def _seed_piece(self, code="TESTCODE", title="Speckled tea bowl set"):
        sk, pk = generate_keypair()
        seed_hex = sk.private_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PrivateFormat.Raw,
            encryption_algorithm=serialization.NoEncryption(),
        ).hex()
        conn = get_db()
        try:
            maker_id = conn.execute(
                "INSERT INTO users (name, email, password_hash, role, public_key, encrypted_privkey) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                ("Maya Iyer", f"maya+{code}@test.local", "unused", "maker",
                 pubkey_to_hex(pk), seed_hex),
            ).lastrowid
            piece_id = conn.execute(
                "INSERT INTO pieces (certificate_code, title, made_by, current_owner_id) "
                "VALUES (?, ?, ?, ?)",
                (code, title, maker_id, maker_id),
            ).lastrowid
            rec = CustodyRecord(piece_id, 0, maker_id, maker_id, "Self", "Piece created", GENESIS_HASH)
            rec_hash = rec.compute_hash()
            conn.execute(
                "INSERT INTO custody_records (piece_id, seq_index, from_user_id, to_user_id, "
                "to_name, note, timestamp, prev_hash, record_hash, signature) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (piece_id, 0, maker_id, maker_id, "Self", rec.note, rec.timestamp,
                 GENESIS_HASH, rec_hash, sign(sk, bytes.fromhex(rec_hash)).hex()),
            )
            conn.commit()
            return piece_id
        finally:
            conn.close()

    @staticmethod
    def _client(sales, next_after_id=2):
        """A mock ReMarket that answers the sales endpoint with `sales`."""
        def handler(request):
            assert request.url.path == "/api/v1/sales", request.url.path
            return httpx.Response(200, json={"sales": sales, "next_after_id": next_after_id})
        return httpx.Client(base_url="http://remarket.test",
                            transport=httpx.MockTransport(handler))

    @staticmethod
    def _paging_client(sales):
        """A mock ReMarket that honours after_id, like the real service.

        The constant-response client above re-serves every sale on each poll;
        this one does not, which is what a deployed CraftProof actually sees
        once its cursor has advanced.
        """
        def handler(request):
            after = int(request.url.params.get("after_id", 0))
            page = [s for s in sales
                    if int(s["order_id"].split("-")[1]) > after]
            last = int(page[-1]["order_id"].split("-")[1]) if page else after
            return httpx.Response(200, json={"sales": page, "next_after_id": last})
        return httpx.Client(base_url="http://remarket.test",
                            transport=httpx.MockTransport(handler))

    def _sync_with(self, sales, next_after_id=2):
        with patch.object(remarket, "remarket_client",
                          return_value=self._client(sales, next_after_id)):
            return remarket.sync_sales()

    def _sync_paging(self, sales):
        with patch.object(remarket, "remarket_client",
                          return_value=self._paging_client(sales)):
            return remarket.sync_sales()

    def _count(self, sql, args=()):
        conn = get_db()
        try:
            return conn.execute(sql, args).fetchone()[0]
        finally:
            conn.close()

    def _last_record(self):
        conn = get_db()
        try:
            return conn.execute(
                "SELECT * FROM custody_records WHERE piece_id = ? ORDER BY seq_index DESC LIMIT 1",
                (self.piece_id,),
            ).fetchone()
        finally:
            conn.close()

    # ------------------------------------------------------------------ tests

    def test_matching_sale_is_imported_signed_and_verifiable(self):
        result = self._sync_with([_sale()])

        self.assertEqual(result["imported"], 1)
        self.assertEqual(result["skipped"], [])

        record = self._last_record()
        self.assertEqual(record["seq_index"], 1)
        self.assertEqual(record["to_name"], "Asha Rao")
        self.assertIsNone(record["to_user_id"], "external buyer has no CraftProof account")
        self.assertIn("RM-000002", record["note"])

        # The appended record must verify like any other link in the chain.
        valid, reason, _ = verify_chain_detailed(self.piece_id)
        self.assertTrue(valid, reason)
        self.assertIsNotNone(get_inclusion_proof(record["record_hash"]),
                             "sync should seal imported records in a checkpoint")

    def test_signer_is_the_service_account_not_the_previous_owner(self):
        self._sync_with([_sale()])
        record = self._last_record()
        conn = get_db()
        try:
            signer = conn.execute(
                "SELECT name, email, role FROM users WHERE id = ?", (record["from_user_id"],)
            ).fetchone()
        finally:
            conn.close()
        self.assertEqual(signer["email"], remarket.SERVICE_EMAIL)
        self.assertEqual(signer["role"], "integration")

    def test_service_private_key_is_not_stored_in_the_database(self):
        self._sync_with([_sale()])
        conn = get_db()
        try:
            stored = conn.execute(
                "SELECT encrypted_privkey FROM users WHERE email = ?", (remarket.SERVICE_EMAIL,)
            ).fetchone()["encrypted_privkey"]
        finally:
            conn.close()
        self.assertEqual(stored, remarket.EXTERNAL_KEY_MARKER)
        self.assertTrue(os.path.exists(remarket._KEY_FILE))

    def test_replaying_the_feed_does_not_duplicate_the_sale(self):
        first = self._sync_with([_sale()])
        again = self._sync_with([_sale()])

        self.assertEqual(first["imported"], 1)
        self.assertEqual(again["imported"], 0)
        self.assertEqual(again["already_imported"], 1)
        self.assertEqual(self._count("SELECT COUNT(*) FROM remarket_imports"), 1)
        self.assertEqual(
            self._count("SELECT COUNT(*) FROM custody_records WHERE piece_id = ?", (self.piece_id,)),
            2, "genesis plus exactly one imported transfer")

    def test_title_mismatch_cannot_touch_the_certificate(self):
        outcome = remarket.import_sale(_sale(title="iPhone 18 Pro"))
        self.assertEqual(outcome, "item_title_mismatch")
        self.assertEqual(self._count("SELECT COUNT(*) FROM remarket_imports"), 0)
        self.assertEqual(
            self._count("SELECT COUNT(*) FROM custody_records WHERE piece_id = ?", (self.piece_id,)),
            1, "only the genesis record should remain")

    def test_title_match_ignores_case_and_repeated_spaces(self):
        self.assertEqual(
            remarket.import_sale(_sale(title="  speckled   TEA bowl   set ")), "imported")

    def test_unknown_certificate_is_skipped_without_error(self):
        self.assertEqual(
            remarket.import_sale(_sale(code="NOSUCH99")), "certificate_not_found")
        self.assertEqual(self._count("SELECT COUNT(*) FROM remarket_imports"), 0)

    def test_incomplete_sale_is_rejected(self):
        for bad in (
            _sale(status="pending"),
            _sale(order_id="not-an-order"),
            _sale(buyer="   "),
            {"order_id": "RM-000009"},
        ):
            with self.assertRaises(ValueError):
                remarket.import_sale(bad)

    def test_skipped_sale_holds_the_cursor_so_it_is_retried(self):
        # Order 1 imports; order 2 names a certificate we do not have yet.
        result = self._sync_with(
            [_sale(order_id="RM-000001"), _sale(order_id="RM-000002", code="LATER999")])
        self.assertEqual(result["imported"], 1)
        self.assertEqual([s["reason"] for s in result["skipped"]], ["certificate_not_found"])

        # The cursor must stop before the skipped order, not past it.
        self.assertEqual(remarket.read_cursor(), 1)

        # Once that certificate exists, the next sync picks the sale up.
        self._seed_piece(code="LATER999", title="Walnut serving board")
        retry = self._sync_with(
            [_sale(order_id="RM-000002", code="LATER999", title="Walnut serving board")])
        self.assertEqual(retry["imported"], 1)
        self.assertEqual(remarket.read_cursor(), 2)

    def test_next_sync_repairs_a_missing_checkpoint(self):
        # Interrupt the run after the custody record is committed but before
        # its checkpoint is published.
        with patch.object(remarket, "create_checkpoint", side_effect=RuntimeError("interrupted")):
            with self.assertRaisesRegex(RuntimeError, "interrupted"):
                self._sync_with([_sale()])

        record_hash = self._last_record()["record_hash"]
        self.assertIsNone(get_inclusion_proof(record_hash), "checkpoint should be missing")

        retry = self._sync_with([_sale()])
        self.assertEqual(retry["already_imported"], 1)
        self.assertIsNotNone(get_inclusion_proof(record_hash), "retry should seal the record")

    def test_checkpoint_is_repaired_even_after_the_cursor_moved_past_the_sale(self):
        """Regression: an interrupted checkpoint must not strand a record.

        Against a feed that honours after_id, the retry sees an empty page —
        so sealing can't be conditional on this run having imported anything,
        and the cursor must not advance past an unsealed record.
        """
        sales = [_sale(order_id="RM-000001")]

        with patch.object(remarket, "create_checkpoint", side_effect=RuntimeError("interrupted")):
            with self.assertRaisesRegex(RuntimeError, "interrupted"):
                self._sync_paging(sales)

        record_hash = self._last_record()["record_hash"]
        self.assertIsNone(get_inclusion_proof(record_hash))
        self.assertEqual(remarket.read_cursor(), 0,
                         "cursor must not advance past an unsealed record")

        retry = self._sync_paging(sales)
        self.assertIsNotNone(get_inclusion_proof(record_hash),
                             "the retry must seal the stranded record")
        self.assertEqual(remarket.read_cursor(), 1)
        self.assertEqual(retry["already_imported"], 1)

        # And a third, fully quiet sync changes nothing.
        quiet = self._sync_paging(sales)
        self.assertEqual(quiet["imported"], 0)
        self.assertEqual(
            self._count("SELECT COUNT(*) FROM custody_records WHERE piece_id = ?", (self.piece_id,)),
            2)

    def test_losing_the_key_file_does_not_invalidate_earlier_imports(self):
        """A redeploy that drops the key file must not break old certificates.

        The signer is looked up by public key, so a regenerated key becomes a
        *new* signer identity instead of overwriting the old row — otherwise
        every previously imported record would start failing its signature
        check and the public certificate would read ALTERED RECORD.
        """
        self._sync_with([_sale(order_id="RM-000001")])
        first_hash = self._last_record()["record_hash"]
        valid, reason, _ = verify_chain_detailed(self.piece_id)
        self.assertTrue(valid, reason)

        # Simulate the ephemeral disk: the key file is gone, the database is not.
        os.remove(remarket._KEY_FILE)

        second = self._seed_piece(code="SECOND01", title="Oak stool")
        with patch.object(remarket, "remarket_client",
                          return_value=self._client([_sale(order_id="RM-000002",
                                                           code="SECOND01",
                                                           title="Oak stool")])):
            remarket.sync_sales()

        # The new sale imported under a fresh signer...
        valid_new, reason_new, _ = verify_chain_detailed(second)
        self.assertTrue(valid_new, reason_new)
        # ...and the earlier certificate still verifies against its own signer.
        valid_old, reason_old, _ = verify_chain_detailed(self.piece_id)
        self.assertTrue(valid_old, f"earlier import broke after key loss: {reason_old}")
        self.assertEqual(self._last_record()["record_hash"], first_hash)

        signers = self._count(
            "SELECT COUNT(*) FROM users WHERE role = 'integration'")
        self.assertEqual(signers, 2, "a new key must register as a new signer")

    def test_status_never_leaks_the_api_key(self):
        secret = "super-secret-partner-key-value"
        with patch.dict(os.environ, {"REMARKET_API_URL": "https://remarket.test",
                                     "REMARKET_SALE_API_KEY": secret}):
            status = remarket.integration_status()
        self.assertTrue(status["configured"])
        self.assertTrue(status["api_key_present"])
        self.assertNotIn(secret, repr(status))

    def test_client_sends_the_bearer_key_and_refuses_redirects(self):
        with patch.dict(os.environ, {"REMARKET_API_URL": "https://remarket.test/",
                                     "REMARKET_SALE_API_KEY": "partner-key"}):
            client = remarket.remarket_client()
        with client:
            self.assertEqual(client.headers["Authorization"], "Bearer partner-key")
            self.assertEqual(str(client.base_url).rstrip("/"), "https://remarket.test")
            # Following a redirect would hand the bearer token to whatever
            # host the partner's server points at.
            self.assertFalse(client.follow_redirects)

    def test_unconfigured_client_refuses_rather_than_calling_out(self):
        from fastapi import HTTPException
        with patch.dict(os.environ, {"REMARKET_API_URL": "", "REMARKET_SALE_API_KEY": ""}):
            with self.assertRaises(HTTPException) as caught:
                remarket.remarket_client()
        self.assertEqual(caught.exception.status_code, 503)


if __name__ == "__main__":
    unittest.main(verbosity=2)
