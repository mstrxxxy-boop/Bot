"""RCA: real users with '_' in username break the withdraw channel broadcast."""
from conftest import API
from backend_test import make_user, make_withdrawal, TEST_IMG_B64


def _first_ok_msg_id(log):
    """New multi-channel schema: log['results'] = [{channel, message_id, ok}]"""
    for r in (log.get("results") or []):
        if r.get("ok") and r.get("message_id"):
            return r["message_id"]
    return None



class TestUsernameMarkdownRCA:
    def test_username_with_underscore_breaks_channel_broadcast(self, client, mongo_db):
        """Real seed user 'Arga_0136' has an underscore -> @Arga_0136 in the Markdown
        channel text is an unclosed italic entity -> broadcast + DM silently fail."""
        # single '_' (like the real user 'Arga_0136') = unclosed italic entity
        tg_id = make_user(mongo_db, suffix=51, balance=0,
                          username="TESTArga_0136", first_name="Argaseed")
        wid = make_withdrawal(mongo_db, tg_id, amount=30000)
        r = client.post(f"{API}/withdrawals/{wid}/approve",
                        json={"note": "Pembayaran sudah dikirim", "image_base64": TEST_IMG_B64}, timeout=90)
        assert r.status_code == 200, r.text
        log = mongo_db.broadcast_logs.find_one({"withdrawal_id": wid})
        msg_id = _first_ok_msg_id(log)
        status = log.get("status")
        err = log.get("error")
        print(f"[username underscore] channel_message_id = {msg_id} status={status} error={err}")
        mongo_db.broadcast_logs.delete_many({"withdrawal_id": wid})
        mongo_db.withdrawals.delete_one({"id": wid})
        mongo_db.balance_history.delete_many({"telegram_id": tg_id})
        mongo_db.users.delete_one({"telegram_id": tg_id})
        assert msg_id is not None, (
            "Withdraw approved but channel broadcast FAILED because username contains '_' "
            "(unescaped Markdown). Existing real user 'Arga_0136' is affected."
        )

    def test_firstname_with_asterisk_breaks_channel_broadcast(self, client, mongo_db):
        tg_id = make_user(mongo_db, suffix=52, balance=0,
                          username="TESTfname", first_name="TEST *Star")
        wid = make_withdrawal(mongo_db, tg_id, amount=10000)
        r = client.post(f"{API}/withdrawals/{wid}/approve",
                        json={"note": "Sudah dikirim", "image_base64": TEST_IMG_B64}, timeout=90)
        assert r.status_code == 200, r.text
        log = mongo_db.broadcast_logs.find_one({"withdrawal_id": wid})
        msg_id = _first_ok_msg_id(log)
        print(f"[firstname asterisk] channel_message_id = {msg_id}")
        mongo_db.broadcast_logs.delete_many({"withdrawal_id": wid})
        mongo_db.withdrawals.delete_one({"id": wid})
        mongo_db.balance_history.delete_many({"telegram_id": tg_id})
        mongo_db.users.delete_one({"telegram_id": tg_id})
        assert msg_id is not None, "Channel broadcast failed due to '*' in first_name"

    def test_task_title_with_underscore_still_approves(self, client, mongo_db):
        """Approve submission must still succeed even if DM formatting fails."""
        tg_id = make_user(mongo_db, suffix=53, balance=0)
        task = client.post(f"{API}/tasks", json={
            "title": "TEST_task_with_underscores", "description": "d", "reward": 2000,
            "instructions": "", "link": None, "max_slots": 0,
        }, timeout=30).json()
        from backend_test import make_submission
        sid = make_submission(mongo_db, tg_id, task["id"])
        r = client.post(f"{API}/submissions/{sid}/approve", timeout=60)
        assert r.status_code == 200, r.text
        user = mongo_db.users.find_one({"telegram_id": tg_id})
        assert user["balance"] == 2000, "balance credit must not depend on DM success"
        client.delete(f"{API}/tasks/{task['id']}", timeout=30)
        mongo_db.submissions.delete_one({"id": sid})
        mongo_db.balance_history.delete_many({"telegram_id": tg_id})
        mongo_db.users.delete_one({"telegram_id": tg_id})
