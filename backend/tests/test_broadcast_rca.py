"""RCA probe: Markdown parse failure on broadcast text (unescaped user/admin input)."""
import uuid

from conftest import API
from backend_test import make_user, make_withdrawal, TEST_IMG_B64


class TestBroadcastMarkdownRCA:
    def test_plain_text_broadcast_succeeds(self, client, mongo_db):
        """Proves bot IS channel admin and broadcast works when text has no MD specials."""
        text = f"TEST plain broadcast {uuid.uuid4().hex[:6]}"
        r = client.post(f"{API}/broadcast/manual", json={"text": text}, timeout=90)
        assert r.status_code == 200, r.text
        assert r.json()["message_id"] is not None
        mongo_db.broadcast_logs.delete_many({"text": text})

    def test_underscore_text_broadcast_ok(self, client, mongo_db):
        """FIX: unescaped '_' in admin text should be handled - fallback to plain text."""
        text = f"TEST_underscore {uuid.uuid4().hex[:6]}"
        r = client.post(f"{API}/broadcast/manual",
                        json={"text": text}, timeout=90)
        print(f"underscore broadcast -> {r.status_code} {r.text[:200]}")
        assert r.status_code == 200
        assert r.json().get("message_id") is not None
        mongo_db.broadcast_logs.delete_many({"text": text})

    def test_asterisk_text_broadcast_ok(self, client, mongo_db):
        text = f"TEST *unclosed bold {uuid.uuid4().hex[:6]}"
        r = client.post(f"{API}/broadcast/manual",
                        json={"text": text}, timeout=90)
        print(f"asterisk broadcast -> {r.status_code} {r.text[:200]}")
        assert r.status_code == 200
        assert r.json().get("message_id") is not None
        mongo_db.broadcast_logs.delete_many({"text": text})

    def test_withdraw_approve_broadcast_silently_fails_with_md_chars(self, client, mongo_db):
        """Withdraw approve returns 200 but channel_message_id is None when note has MD specials
        -> user never gets DM/channel proof, admin sees success."""
        tg_id = make_user(mongo_db, suffix=41, balance=0, username="TEST_mduser")
        wid = make_withdrawal(mongo_db, tg_id, amount=15000)
        r = client.post(f"{API}/withdrawals/{wid}/approve",
                        json={"note": "TEST_note with_underscore", "image_base64": TEST_IMG_B64}, timeout=90)
        assert r.status_code == 200, r.text
        log = mongo_db.broadcast_logs.find_one({"withdrawal_id": wid})
        assert log is not None
        print(f"withdraw approve channel_message_id = {log.get('channel_message_id')}")
        broadcast_ok = log.get("channel_message_id") is not None
        mongo_db.broadcast_logs.delete_many({"withdrawal_id": wid})
        mongo_db.withdrawals.delete_one({"id": wid})
        mongo_db.balance_history.delete_many({"telegram_id": tg_id})
        mongo_db.users.delete_one({"telegram_id": tg_id})
        assert broadcast_ok, "Channel broadcast silently failed (channel_message_id=None) due to Markdown parse error in admin note"

    def test_withdraw_approve_broadcast_ok_plain_note(self, client, mongo_db):
        tg_id = make_user(mongo_db, suffix=42, balance=0, username="TESTplainuser", first_name="TESTPlain")
        wid = make_withdrawal(mongo_db, tg_id, amount=15000)
        r = client.post(f"{API}/withdrawals/{wid}/approve",
                        json={"note": "Pembayaran sudah dikirim", "image_base64": TEST_IMG_B64}, timeout=90)
        assert r.status_code == 200, r.text
        log = mongo_db.broadcast_logs.find_one({"withdrawal_id": wid})
        msg_id = log.get("channel_message_id")
        print(f"plain-note withdraw broadcast channel_message_id = {msg_id}")
        mongo_db.broadcast_logs.delete_many({"withdrawal_id": wid})
        mongo_db.withdrawals.delete_one({"id": wid})
        mongo_db.balance_history.delete_many({"telegram_id": tg_id})
        mongo_db.users.delete_one({"telegram_id": tg_id})
        assert msg_id is not None, "Channel broadcast failed even with plain note - bot may not be channel admin"
