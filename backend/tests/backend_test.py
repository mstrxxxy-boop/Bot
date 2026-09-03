"""BigoCuan backend API regression suite.

Covers: auth, health, stats overview, task CRUD, submission review (approve/reject),
withdrawal approve/reject, users + balance adjust, broadcast, auth protection.

Seed data for submissions/withdrawals is inserted directly into MongoDB because real
submissions only originate from Telegram users.
"""
import uuid
from datetime import datetime, timezone

import pytest
import requests

from conftest import API

TEST_TG_ID_BASE = 990000000

# 320x320 PNG used as withdraw payment proof (image_base64 is now required).
# NOTE: a 1x1 PNG makes Telegram reject sendPhoto with BadRequest "Image_process_failed".
TEST_IMG_B64 = (
    "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAUAAAAFACAIAAABC8jL9AAACtUlEQVR42u3TQQkAAAgEwUtiZhtrB3/CwCRY2FQP8FQkAAMDBgYMDAYGDAwYGDAwGBgwMGBgMDBgYMDAgIHBwICBAQMDBgYDAwYGDAwGBgwMGBgwMBgYMDBgYMDAYGDAwICBwcCAgQEDAwYGAwMGBgwMBlYBDAwYGDAwGBgwMGBgwMBgYMDAgIHBwICBAQMDBgYDAwYGDAwYGAwMGBgwMBgYMDBgYMDAYGDAwICBAQODgQEDAwYGAwMGBgwMGBgMDBgYMDAYGDAwYGDAwGBgwMCAgQEDg4EBAwMGBgMDBgYMDBgYDAwYGDAwYGAwMGBgwMBgYMDAgIEBA4OBAQMDBgYMDAYGDAwYGAwMGBgwMGBgMDBgYMDAYGDAwICBAQODgQEDAwYGDAwGBgwMGBgMDBgYMDBgYDAwYGDAwICBwcCAgQEDg4EBAwMGBgwMBgYMDBgYDKwCGBgwMGBgMDBgYMDAgIHBwICBAQODgQEDAwYGDAwGBgwMGBgwMBgYMDBgYDAwYGDAwICBwcCAgQEDAwYGAwMGBgwMBgYMDBgYMDAYGDAwYGAwMGBgwMCAgcHAgIEBAwMGBgMDBgYMDAYGDAwYGDAwGBgwMGBgwMBgYMDAgIHBwICBAQMDBgYDAwYGDAwYGAwMGBgwMBgYMDBgYMDAYGDAwICBwcCAgQEDAwYGAwMGBgwMGBgMDBgYMDAYGDAwYGDAwGBgwMCAgQEDg4EBAwMGBgMDBgYMDBgYDAwYGDAwGFgCMDBgYMDAYGDAwICBAQODgQEDAwYGAwMGBgwMGBgMDBgYMDBgYDAwYGDAwGBgwMCAgQEDg4EBAwMGBgwMBgYMDBgYDAwYGDAwYGAwMGBgwMBgYBXAwICBAQODgQEDAwYGDAwGBgwMGBgMDBgYMDBgYDAwYGDAwICBwcCAgYGbBawed0PsMQ8oAAAAAElFTkSuQmCC"
)


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def make_user(db, suffix=1, balance=0, username="TEST_user", first_name="TEST_First"):
    tg_id = TEST_TG_ID_BASE + suffix
    db.users.delete_one({"telegram_id": tg_id})
    db.users.insert_one({
        "telegram_id": tg_id,
        "username": username,
        "first_name": first_name,
        "last_name": "TEST_Last",
        "balance": balance,
        "total_earned": 0,
        "tasks_completed": 0,
        "bank": {"method": "DANA", "account_number": "081200000000", "account_name": "TEST Holder"},
        "created_at": now_iso(),
    })
    return tg_id


def make_submission(db, tg_id, task_id, status="pending"):
    sid = str(uuid.uuid4())
    db.submissions.insert_one({
        "id": sid,
        "telegram_id": tg_id,
        "task_id": task_id,
        "proof_image": "data:image/png;base64,iVBORw0KGgo=",
        "proof_text": "TEST_proof",
        "status": status,
        "created_at": now_iso(),
    })
    return sid


def make_withdrawal(db, tg_id, amount=25000, status="pending"):
    wid = str(uuid.uuid4())
    db.withdrawals.insert_one({
        "id": wid,
        "telegram_id": tg_id,
        "amount": amount,
        "method": "DANA",
        "account_number": "081200000000",
        "account_name": "TEST Holder",
        "status": status,
        "created_at": now_iso(),
    })
    return wid


# ---------------- Health + Auth ----------------
class TestHealthAndAuth:
    def test_health(self, anon_client):
        r = anon_client.get(f"{API}/health", timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["status"] == "ok"
        assert data["bot_running"] is True, "Telegram bot is not running"

    def test_login_success(self, anon_client, test_credentials):
        r = anon_client.post(f"{API}/auth/login", json=test_credentials, timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert isinstance(data.get("token"), str) and len(data["token"]) > 20
        assert data["username"] == test_credentials["username"]

    def test_login_wrong_password(self, anon_client, test_credentials):
        r = anon_client.post(f"{API}/auth/login",
                             json={"username": test_credentials["username"], "password": "wrongpass"},
                             timeout=30)
        assert r.status_code == 401, r.text
        assert "detail" in r.json()

    def test_login_wrong_username(self, anon_client):
        r = anon_client.post(f"{API}/auth/login",
                             json={"username": "nobody", "password": "admin123"}, timeout=30)
        assert r.status_code == 401

    def test_login_missing_field(self, anon_client):
        r = anon_client.post(f"{API}/auth/login", json={"username": "admin"}, timeout=30)
        assert r.status_code == 422

    def test_auth_me(self, client, test_credentials):
        r = client.get(f"{API}/auth/me", timeout=30)
        assert r.status_code == 200
        assert r.json()["username"] == test_credentials["username"]


# ---------------- Auth protection ----------------
class TestAuthProtection:
    PROTECTED = [
        ("get", "/auth/me"),
        ("get", "/stats/overview"),
        ("get", "/tasks"),
        ("post", "/tasks"),
        ("get", "/submissions"),
        ("get", "/withdrawals"),
        ("get", "/users"),
        ("get", "/users/802076701"),
        ("get", "/broadcast/logs"),
        ("post", "/broadcast/manual"),
        ("patch", "/tasks/xyz"),
        ("delete", "/tasks/xyz"),
        ("post", "/submissions/xyz/approve"),
        ("post", "/submissions/xyz/reject"),
        ("post", "/withdrawals/xyz/approve"),
        ("post", "/withdrawals/xyz/reject"),
        ("post", "/users/802076701/adjust"),
    ]

    @pytest.mark.parametrize("method,path", PROTECTED)
    def test_requires_token(self, method, path):
        r = requests.request(method, f"{API}{path}", json={}, timeout=30)
        assert r.status_code in (401, 403), f"{method.upper()} {path} -> {r.status_code}"

    def test_invalid_token_rejected(self):
        r = requests.get(f"{API}/stats/overview",
                         headers={"Authorization": "Bearer not.a.jwt"}, timeout=30)
        assert r.status_code == 401

    def test_public_endpoints_open(self, anon_client):
        assert anon_client.get(f"{API}/health", timeout=30).status_code == 200


# ---------------- Stats ----------------
class TestStats:
    def test_overview_shape(self, client):
        r = client.get(f"{API}/stats/overview", timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        for key in ["total_users", "pending_submissions", "pending_withdrawals",
                    "pending_withdrawals_amount", "total_payout", "wallet_distribution",
                    "daily", "bot_running", "channel"]:
            assert key in d, f"missing key {key}"
        assert isinstance(d["total_users"], int) and d["total_users"] >= 0
        assert isinstance(d["wallet_distribution"], list)
        assert isinstance(d["daily"], list) and len(d["daily"]) == 7
        assert set(d["daily"][0].keys()) == {"date", "submissions", "earnings"}
        assert d["bot_running"] is True
        assert d["channel"] == "@BigoCuan"


# ---------------- Task CRUD ----------------
class TestTaskCRUD:
    created = []

    def test_task_full_crud(self, client):
        payload = {
            "title": "TEST_Task Follow IG",
            "description": "TEST description",
            "reward": 5000,
            "instructions": "TEST instructions",
            "link": "https://example.com/test",
            "max_slots": 10,
        }
        r = client.post(f"{API}/tasks", json=payload, timeout=30)
        assert r.status_code in (200, 201), r.text
        task = r.json()
        assert "_id" not in task, "MongoDB _id leaked in response"
        assert isinstance(task["id"], str)
        for k, v in payload.items():
            assert task[k] == v, f"{k} mismatch"
        assert task["slots_used"] == 0
        assert task["active"] is True
        tid = task["id"]
        TestTaskCRUD.created.append(tid)

        # LIST + enrichment
        r = client.get(f"{API}/tasks", timeout=60)
        assert r.status_code == 200
        tasks = r.json()
        found = [t for t in tasks if t["id"] == tid]
        assert found, "created task missing from GET /api/tasks"
        assert found[0]["approved_count"] == 0
        assert found[0]["pending_count"] == 0
        assert "_id" not in found[0]

        # PATCH
        r = client.patch(f"{API}/tasks/{tid}",
                         json={"title": "TEST_Task Updated", "reward": 7500}, timeout=30)
        assert r.status_code == 200, r.text
        upd = r.json()
        assert upd["title"] == "TEST_Task Updated"
        assert upd["reward"] == 7500
        assert upd["description"] == payload["description"]

        # GET verifies persistence
        tasks = client.get(f"{API}/tasks", timeout=60).json()
        got = [t for t in tasks if t["id"] == tid][0]
        assert got["title"] == "TEST_Task Updated" and got["reward"] == 7500

        # PATCH active=false must persist (falsy value edge case)
        r = client.patch(f"{API}/tasks/{tid}", json={"active": False}, timeout=30)
        assert r.status_code == 200
        assert r.json()["active"] is False, "active=false not persisted"

        # DELETE
        r = client.delete(f"{API}/tasks/{tid}", timeout=30)
        assert r.status_code == 200
        assert r.json().get("ok") is True
        tasks = client.get(f"{API}/tasks", timeout=60).json()
        assert not [t for t in tasks if t["id"] == tid], "task still present after delete"
        TestTaskCRUD.created.remove(tid)

    def test_create_task_validation(self, client):
        r = client.post(f"{API}/tasks", json={"title": "TEST_only title"}, timeout=30)
        assert r.status_code == 422

    def test_patch_nonexistent_task(self, client):
        # FIX #4: must be 404
        r = client.patch(f"{API}/tasks/{uuid.uuid4()}", json={"title": "TEST_x"}, timeout=30)
        assert r.status_code == 404, r.text
        assert "detail" in r.json()

    def test_delete_nonexistent_task(self, client):
        # FIX #4: must be 404
        r = client.delete(f"{API}/tasks/{uuid.uuid4()}", timeout=30)
        assert r.status_code == 404, r.text
        assert "detail" in r.json()

    @pytest.fixture(scope="class", autouse=True)
    def cleanup(self, client):
        yield
        for tid in list(TestTaskCRUD.created):
            client.delete(f"{API}/tasks/{tid}", timeout=30)


# ---------------- Submissions ----------------
class TestSubmissions:
    def test_list_submissions_filters(self, client):
        r = client.get(f"{API}/submissions", params={"status_filter": "pending"}, timeout=60)
        assert r.status_code == 200, r.text
        subs = r.json()
        assert isinstance(subs, list)
        for s in subs:
            assert s["status"] == "pending"
            assert "user" in s and "task" in s
            assert "_id" not in s
        r_all = client.get(f"{API}/submissions", params={"status_filter": "all"}, timeout=60)
        assert r_all.status_code == 200
        assert len(r_all.json()) >= len(subs)

    def test_approve_submission_credits_user(self, client, mongo_db):
        tg_id = make_user(mongo_db, suffix=11, balance=0)
        task = client.post(f"{API}/tasks", json={
            "title": "TEST_Approve Flow", "description": "d", "reward": 12000,
            "instructions": "i", "link": None, "max_slots": 5,
        }, timeout=30).json()
        sid = make_submission(mongo_db, tg_id, task["id"])

        # appears in pending list with enrichment
        subs = client.get(f"{API}/submissions", params={"status_filter": "pending"}, timeout=60).json()
        mine = [s for s in subs if s["id"] == sid]
        assert mine, "seeded submission not returned"
        assert mine[0]["user"]["telegram_id"] == tg_id
        assert mine[0]["task"]["id"] == task["id"]

        r = client.post(f"{API}/submissions/{sid}/approve", timeout=60)
        assert r.status_code == 200, r.text
        assert r.json().get("ok") is True

        sub = mongo_db.submissions.find_one({"id": sid})
        assert sub["status"] == "approved"
        assert sub.get("reviewed_at")

        user = mongo_db.users.find_one({"telegram_id": tg_id})
        assert user["balance"] == 12000
        assert user["total_earned"] == 12000
        assert user["tasks_completed"] == 1

        t = mongo_db.tasks.find_one({"id": task["id"]})
        assert t["slots_used"] == 1

        hist = list(mongo_db.balance_history.find({"telegram_id": tg_id, "ref_id": sid}))
        assert len(hist) == 1
        assert hist[0]["type"] == "credit" and hist[0]["amount"] == 12000

        # task list counts enriched
        tasks = client.get(f"{API}/tasks", timeout=60).json()
        got = [x for x in tasks if x["id"] == task["id"]][0]
        assert got["approved_count"] == 1 and got["pending_count"] == 0

        # double approve rejected
        r2 = client.post(f"{API}/submissions/{sid}/approve", timeout=30)
        assert r2.status_code == 400

        client.delete(f"{API}/tasks/{task['id']}", timeout=30)
        mongo_db.submissions.delete_one({"id": sid})
        mongo_db.balance_history.delete_many({"telegram_id": tg_id})
        mongo_db.users.delete_one({"telegram_id": tg_id})

    def test_reject_submission(self, client, mongo_db):
        tg_id = make_user(mongo_db, suffix=12, balance=0)
        task = client.post(f"{API}/tasks", json={
            "title": "TEST_Reject Flow", "description": "d", "reward": 3000,
            "instructions": "", "link": None, "max_slots": 0,
        }, timeout=30).json()
        sid = make_submission(mongo_db, tg_id, task["id"])

        r = client.post(f"{API}/submissions/{sid}/reject",
                        json={"reason": "TEST_bukti tidak valid"}, timeout=60)
        assert r.status_code == 200, r.text
        sub = mongo_db.submissions.find_one({"id": sid})
        assert sub["status"] == "rejected"
        assert sub["reject_reason"] == "TEST_bukti tidak valid"
        user = mongo_db.users.find_one({"telegram_id": tg_id})
        assert user["balance"] == 0, "balance must not change on reject"

        rejected = client.get(f"{API}/submissions", params={"status_filter": "rejected"}, timeout=60).json()
        assert any(s["id"] == sid for s in rejected)

        r2 = client.post(f"{API}/submissions/{sid}/reject", json={"reason": "again"}, timeout=30)
        assert r2.status_code == 400

        client.delete(f"{API}/tasks/{task['id']}", timeout=30)
        mongo_db.submissions.delete_one({"id": sid})
        mongo_db.users.delete_one({"telegram_id": tg_id})

    def test_approve_nonexistent_submission(self, client):
        r = client.post(f"{API}/submissions/{uuid.uuid4()}/approve", timeout=30)
        assert r.status_code == 404

    def test_approve_submission_with_missing_task(self, client, mongo_db):
        tg_id = make_user(mongo_db, suffix=13)
        sid = make_submission(mongo_db, tg_id, task_id=str(uuid.uuid4()))
        r = client.post(f"{API}/submissions/{sid}/approve", timeout=30)
        assert r.status_code == 404
        mongo_db.submissions.delete_one({"id": sid})
        mongo_db.users.delete_one({"telegram_id": tg_id})


# ---------------- Withdrawals ----------------
class TestWithdrawals:
    def test_list_withdrawals(self, client):
        r = client.get(f"{API}/withdrawals", params={"status_filter": "pending"}, timeout=60)
        assert r.status_code == 200, r.text
        ws = r.json()
        assert isinstance(ws, list)
        for w in ws:
            assert w["status"] == "pending"
            assert "user" in w
            assert "_id" not in w

    def test_approve_withdrawal_flow(self, client, mongo_db):
        tg_id = make_user(mongo_db, suffix=21, balance=0, username="TEST_wduser")
        wid = make_withdrawal(mongo_db, tg_id, amount=50000)

        ws = client.get(f"{API}/withdrawals", params={"status_filter": "pending"}, timeout=60).json()
        mine = [w for w in ws if w["id"] == wid]
        assert mine, "seeded withdrawal missing"
        assert mine[0]["user"]["telegram_id"] == tg_id
        assert mine[0]["amount"] == 50000

        body = {"note": "TEST_sudah dikirim via DANA (md chars)", "image_base64": TEST_IMG_B64}
        r = client.post(f"{API}/withdrawals/{wid}/approve", json=body, timeout=90)
        assert r.status_code == 200, r.text
        rb = r.json()
        assert rb.get("ok") is True
        # FIX #3: outcome surfaced in response
        for k in ("dm_sent", "channel_message_id", "broadcast_error", "dm_error"):
            assert k in rb, f"missing {k} in approve response"

        wd = mongo_db.withdrawals.find_one({"id": wid})
        assert wd["status"] == "approved"
        assert wd["admin_note"] == body["note"]
        assert wd["proof_image"] == body["image_base64"]
        assert wd.get("reviewed_at")

        hist = list(mongo_db.balance_history.find({"telegram_id": tg_id, "ref_id": wid}))
        assert len(hist) == 1 and hist[0]["type"] == "withdraw" and hist[0]["amount"] == 50000

        logs = mongo_db.broadcast_logs.find_one({"withdrawal_id": wid})
        assert logs is not None, "broadcast_logs entry not created"
        assert logs["type"] == "withdraw_proof"
        assert "TEST_wduser" in logs["text"] or "TEST_First" in logs["text"]
        # FIX #3: status + error fields recorded
        assert logs.get("status") in ("sent", "failed"), f"status missing/invalid: {logs.get('status')}"
        assert "error" in logs
        if logs["status"] == "failed":
            assert logs["error"], "failed broadcast must record an error message"

        # visible in API broadcast logs
        api_logs = client.get(f"{API}/broadcast/logs", timeout=60).json()
        assert any(x.get("withdrawal_id") == wid for x in api_logs)

        # balance should NOT be re-deducted (hold applied at request time by bot)
        user = mongo_db.users.find_one({"telegram_id": tg_id})
        assert user["balance"] == 0

        r2 = client.post(f"{API}/withdrawals/{wid}/approve", json=body, timeout=30)
        assert r2.status_code == 400

        mongo_db.broadcast_logs.delete_many({"withdrawal_id": wid})
        mongo_db.withdrawals.delete_one({"id": wid})
        mongo_db.balance_history.delete_many({"telegram_id": tg_id})
        mongo_db.users.delete_one({"telegram_id": tg_id})

    def test_approve_withdrawal_requires_image(self, client, mongo_db):
        """FIX #6: image_base64 is required -> 422 and withdrawal stays pending."""
        tg_id = make_user(mongo_db, suffix=22, balance=0)
        wid = make_withdrawal(mongo_db, tg_id, amount=10000)
        r = client.post(f"{API}/withdrawals/{wid}/approve",
                        json={"note": "TEST_no image"}, timeout=90)
        assert r.status_code == 422, r.text
        assert mongo_db.withdrawals.find_one({"id": wid})["status"] == "pending"
        mongo_db.broadcast_logs.delete_many({"withdrawal_id": wid})
        mongo_db.withdrawals.delete_one({"id": wid})
        mongo_db.balance_history.delete_many({"telegram_id": tg_id})
        mongo_db.users.delete_one({"telegram_id": tg_id})

    def test_reject_withdrawal_refunds(self, client, mongo_db):
        tg_id = make_user(mongo_db, suffix=23, balance=5000)
        wid = make_withdrawal(mongo_db, tg_id, amount=20000)
        r = client.post(f"{API}/withdrawals/{wid}/reject",
                        json={"reason": "TEST_data rekening salah"}, timeout=60)
        assert r.status_code == 200, r.text
        wd = mongo_db.withdrawals.find_one({"id": wid})
        assert wd["status"] == "rejected"
        assert wd["reject_reason"] == "TEST_data rekening salah"
        user = mongo_db.users.find_one({"telegram_id": tg_id})
        assert user["balance"] == 25000, "refund not applied"
        hist = list(mongo_db.balance_history.find({"telegram_id": tg_id, "ref_id": wid}))
        assert len(hist) == 1 and hist[0]["type"] == "refund" and hist[0]["amount"] == 20000

        r2 = client.post(f"{API}/withdrawals/{wid}/reject", json={"reason": "again"}, timeout=30)
        assert r2.status_code == 400

        mongo_db.withdrawals.delete_one({"id": wid})
        mongo_db.balance_history.delete_many({"telegram_id": tg_id})
        mongo_db.users.delete_one({"telegram_id": tg_id})

    def test_withdrawal_not_found(self, client):
        assert client.post(f"{API}/withdrawals/{uuid.uuid4()}/approve",
                           json={"note": "x", "image_base64": TEST_IMG_B64},
                           timeout=30).status_code == 404
        assert client.post(f"{API}/withdrawals/{uuid.uuid4()}/reject",
                           json={"reason": "x"}, timeout=30).status_code == 404

    def test_approve_withdrawal_missing_user(self, client, mongo_db):
        ghost = TEST_TG_ID_BASE + 24
        mongo_db.users.delete_one({"telegram_id": ghost})
        wid = make_withdrawal(mongo_db, ghost, amount=1000)
        r = client.post(f"{API}/withdrawals/{wid}/approve",
                        json={"note": "x", "image_base64": TEST_IMG_B64}, timeout=30)
        assert r.status_code == 404
        mongo_db.withdrawals.delete_one({"id": wid})


# ---------------- Users ----------------
class TestUsers:
    def test_list_users(self, client):
        r = client.get(f"{API}/users", timeout=60)
        assert r.status_code == 200, r.text
        users = r.json()
        assert isinstance(users, list)
        for u in users:
            assert "_id" not in u
            assert "telegram_id" in u

    def test_user_detail_and_adjust(self, client, mongo_db):
        tg_id = make_user(mongo_db, suffix=31, balance=1000)

        r = client.get(f"{API}/users/{tg_id}", timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["user"]["telegram_id"] == tg_id
        assert d["user"]["balance"] == 1000
        assert isinstance(d["balance_history"], list)
        assert isinstance(d["submissions"], list)
        assert isinstance(d["withdrawals"], list)

        # credit
        r = client.post(f"{API}/users/{tg_id}/adjust",
                        json={"amount": 4000, "note": "TEST_bonus"}, timeout=60)
        assert r.status_code == 200, r.text
        d = client.get(f"{API}/users/{tg_id}", timeout=60).json()
        assert d["user"]["balance"] == 5000
        credits = [h for h in d["balance_history"] if h["type"] == "credit"]
        assert credits and credits[0]["amount"] == 4000
        assert "TEST_bonus" in credits[0]["note"]

        # debit
        r = client.post(f"{API}/users/{tg_id}/adjust",
                        json={"amount": -1500, "note": "TEST_koreksi"}, timeout=60)
        assert r.status_code == 200
        d = client.get(f"{API}/users/{tg_id}", timeout=60).json()
        assert d["user"]["balance"] == 3500
        debits = [h for h in d["balance_history"] if h["type"] == "debit"]
        assert debits and debits[0]["amount"] == 1500

        mongo_db.balance_history.delete_many({"telegram_id": tg_id})
        mongo_db.users.delete_one({"telegram_id": tg_id})

    def test_adjust_cannot_go_negative(self, client, mongo_db):
        """FIX #5: adjustment that would make balance < 0 must be rejected with 400."""
        tg_id = make_user(mongo_db, suffix=32, balance=2000)
        r = client.post(f"{API}/users/{tg_id}/adjust",
                        json={"amount": -999999, "note": "TEST_overdraft"}, timeout=60)
        assert r.status_code == 400, r.text
        assert "detail" in r.json()
        user = mongo_db.users.find_one({"telegram_id": tg_id})
        assert user["balance"] == 2000, "balance changed despite rejection"
        assert mongo_db.balance_history.count_documents({"telegram_id": tg_id}) == 0
        mongo_db.balance_history.delete_many({"telegram_id": tg_id})
        mongo_db.users.delete_one({"telegram_id": tg_id})

    def test_adjust_exact_to_zero_allowed(self, client, mongo_db):
        tg_id = make_user(mongo_db, suffix=33, balance=3000)
        r = client.post(f"{API}/users/{tg_id}/adjust",
                        json={"amount": -3000, "note": "TEST_zero"}, timeout=60)
        assert r.status_code == 200, r.text
        assert mongo_db.users.find_one({"telegram_id": tg_id})["balance"] == 0
        mongo_db.balance_history.delete_many({"telegram_id": tg_id})
        mongo_db.users.delete_one({"telegram_id": tg_id})

    def test_user_detail_not_found(self, client):
        r = client.get(f"{API}/users/123456789012", timeout=30)
        assert r.status_code == 404

    def test_adjust_user_not_found(self, client):
        r = client.post(f"{API}/users/123456789012/adjust",
                        json={"amount": 100, "note": "x"}, timeout=30)
        assert r.status_code == 404

    def test_user_detail_invalid_id_type(self, client):
        r = client.get(f"{API}/users/not-a-number", timeout=30)
        assert r.status_code == 422


# ---------------- Broadcast ----------------
class TestBroadcast:
    def test_broadcast_logs(self, client):
        r = client.get(f"{API}/broadcast/logs", timeout=60)
        assert r.status_code == 200, r.text
        logs = r.json()
        assert isinstance(logs, list)
        for x in logs:
            assert "_id" not in x

    def test_manual_broadcast(self, client, mongo_db):
        text = f"TEST_broadcast {uuid.uuid4().hex[:8]}"
        r = client.post(f"{API}/broadcast/manual", json={"text": text}, timeout=90)
        if r.status_code == 500:
            pytest.fail(f"Manual broadcast failed (bot/channel issue): {r.text[:300]}")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("ok") is True
        assert data.get("message_id") is not None

        logs = client.get(f"{API}/broadcast/logs", timeout=60).json()
        assert any(x["text"] == text and x["type"] == "manual" for x in logs)
        mongo_db.broadcast_logs.delete_many({"text": text})

    def test_manual_broadcast_validation(self, client):
        r = client.post(f"{API}/broadcast/manual", json={}, timeout=30)
        assert r.status_code == 422
