"""Tests for new BigoCuan features: task categories, multi-state wallet,
channels CRUD, broadcast toggle/multi-channel/resend, FAQ, support."""
import time

import pytest
import requests

from conftest import API

FAKE_CH_1 = "@nonexistent_test_ch_xyz"
FAKE_CH_2 = "@nonexistent_test_ch_abc"


# ---------------- Task categories ----------------
class TestTaskCategories:
    created = []

    @pytest.fixture(scope="class", autouse=True)
    def cleanup(self, client):
        yield
        for tid in self.created:
            client.delete(f"{API}/tasks/{tid}", timeout=30)

    def test_list_categories(self, client):
        r = client.get(f"{API}/task-categories", timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert isinstance(data, list)
        assert data == ["Social Media", "App Install", "Survey", "Other"]

    def test_create_task_valid_category(self, client):
        payload = {
            "title": "TEST_cat_task",
            "description": "desc",
            "reward": 5000,
            "category": "Survey",
        }
        r = client.post(f"{API}/tasks", json=payload, timeout=30)
        assert r.status_code == 200, r.text
        doc = r.json()
        assert "_id" not in doc
        assert doc["category"] == "Survey"
        assert doc["reward"] == 5000
        self.created.append(doc["id"])

        # verify persisted
        lst = client.get(f"{API}/tasks", timeout=30).json()
        found = [t for t in lst if t["id"] == doc["id"]]
        assert found and found[0]["category"] == "Survey"

    def test_create_task_invalid_category(self, client):
        r = client.post(f"{API}/tasks", json={
            "title": "TEST_bad_cat", "description": "d", "reward": 1000, "category": "Bogus",
        }, timeout=30)
        assert r.status_code == 400, r.text
        assert "Kategori" in r.json().get("detail", "")

    def test_create_task_default_category(self, client):
        r = client.post(f"{API}/tasks", json={
            "title": "TEST_default_cat", "description": "d", "reward": 1000,
        }, timeout=30)
        assert r.status_code == 200, r.text
        doc = r.json()
        self.created.append(doc["id"])
        assert doc["category"] == "Other"

    def test_patch_task_category(self, client):
        r = client.post(f"{API}/tasks", json={
            "title": "TEST_patch_cat", "description": "d", "reward": 1000, "category": "Other",
        }, timeout=30)
        tid = r.json()["id"]
        self.created.append(tid)

        ok = client.patch(f"{API}/tasks/{tid}", json={"category": "App Install"}, timeout=30)
        assert ok.status_code == 200, ok.text
        assert ok.json()["category"] == "App Install"

        bad = client.patch(f"{API}/tasks/{tid}", json={"category": "Nope"}, timeout=30)
        assert bad.status_code == 400, bad.text

        # invalid patch must not have mutated the doc
        after = client.patch(f"{API}/tasks/{tid}", json={}, timeout=30).json()
        assert after["category"] == "App Install"


# ---------------- Multi-state wallet ----------------
class TestMultiStateWallet:
    TG_APPROVE = 99000801
    TG_REJECT = 99000802
    task_ids = []

    @pytest.fixture(scope="class", autouse=True)
    def cleanup(self, client, mongo_db):
        yield
        mongo_db.users.delete_many({"telegram_id": {"$in": [self.TG_APPROVE, self.TG_REJECT]}})
        mongo_db.submissions.delete_many({"telegram_id": {"$in": [self.TG_APPROVE, self.TG_REJECT]}})
        mongo_db.balance_history.delete_many({"telegram_id": {"$in": [self.TG_APPROVE, self.TG_REJECT]}})
        for tid in self.task_ids:
            client.delete(f"{API}/tasks/{tid}", timeout=30)

    def _seed(self, client, mongo_db, tg_id, reward):
        task = client.post(f"{API}/tasks", json={
            "title": "TEST_wallet_task", "description": "d", "reward": reward, "category": "Other",
        }, timeout=30).json()
        self.task_ids.append(task["id"])
        mongo_db.users.delete_one({"telegram_id": tg_id})
        mongo_db.users.insert_one({
            "telegram_id": tg_id, "username": f"TESTwallet{tg_id}", "first_name": "TEST Wallet",
            "balance": 10000, "pending_balance": reward, "total_earned": 0, "rejected_total": 0,
            "tasks_completed": 0, "tasks_rejected": 0, "created_at": "2026-01-01T00:00:00+00:00",
        })
        sub_id = f"TESTSUB-{tg_id}"
        mongo_db.submissions.delete_one({"id": sub_id})
        mongo_db.submissions.insert_one({
            "id": sub_id, "telegram_id": tg_id, "task_id": task["id"], "status": "pending",
            "proof_text": "TEST proof", "created_at": "2026-01-01T00:00:00+00:00",
        })
        return task, sub_id

    def test_approve_moves_pending_to_active(self, client, mongo_db):
        reward = 7500
        task, sub_id = self._seed(client, mongo_db, self.TG_APPROVE, reward)

        r = client.post(f"{API}/submissions/{sub_id}/approve", timeout=60)
        assert r.status_code == 200, r.text
        assert r.json().get("ok") is True

        u = mongo_db.users.find_one({"telegram_id": self.TG_APPROVE})
        assert u["pending_balance"] == 0, f"pending_balance not decremented: {u['pending_balance']}"
        assert u["balance"] == 10000 + reward
        assert u["total_earned"] == reward
        assert u["tasks_completed"] == 1
        assert u["rejected_total"] == 0

        sub = mongo_db.submissions.find_one({"id": sub_id})
        assert sub["status"] == "approved"
        assert sub.get("reviewed_at")

        hist = list(mongo_db.balance_history.find({"ref_id": sub_id}))
        assert len(hist) == 1
        assert hist[0]["type"] == "credit"
        assert hist[0]["amount"] == reward

        t = mongo_db.tasks.find_one({"id": task["id"]})
        assert t["slots_used"] == 1

        # double approve blocked
        again = client.post(f"{API}/submissions/{sub_id}/approve", timeout=60)
        assert again.status_code == 400

    def test_reject_moves_pending_to_rejected_total(self, client, mongo_db):
        reward = 4200
        task, sub_id = self._seed(client, mongo_db, self.TG_REJECT, reward)

        r = client.post(f"{API}/submissions/{sub_id}/reject",
                        json={"reason": "TEST bukti tidak valid"}, timeout=60)
        assert r.status_code == 200, r.text

        u = mongo_db.users.find_one({"telegram_id": self.TG_REJECT})
        assert u["pending_balance"] == 0
        assert u["balance"] == 10000, "balance must not change on reject"
        assert u["rejected_total"] == reward
        assert u["tasks_rejected"] == 1
        assert u["total_earned"] == 0

        sub = mongo_db.submissions.find_one({"id": sub_id})
        assert sub["status"] == "rejected"
        assert sub["reject_reason"] == "TEST bukti tidak valid"

        # no credit written on reject
        assert mongo_db.balance_history.count_documents({"ref_id": sub_id}) == 0

        t = mongo_db.tasks.find_one({"id": task["id"]})
        assert t["slots_used"] == 0

        again = client.post(f"{API}/submissions/{sub_id}/reject", json={"reason": "x"}, timeout=60)
        assert again.status_code == 400

    def test_stats_include_total_pending_balance(self, client, mongo_db):
        r = client.get(f"{API}/stats/overview", timeout=60)
        assert r.status_code == 200, r.text
        assert "total_pending_balance" in r.json()

    def test_approve_missing_submission_404(self, client):
        r = client.post(f"{API}/submissions/TEST-nope-404/approve", timeout=30)
        assert r.status_code == 404


# ---------------- Channels CRUD + Broadcast (same class => same worker) ----------------
class TestChannelsAndBroadcast:
    created_ch = []
    created_log_ids = []

    @pytest.fixture(scope="class", autouse=True)
    def cleanup(self, client, mongo_db):
        yield
        for cid in self.created_ch:
            client.delete(f"{API}/channels/{cid}", timeout=30)
        mongo_db.channels.delete_many({"username": {"$in": [FAKE_CH_1, FAKE_CH_2, "@testchan"]}})
        client.put(f"{API}/broadcast/settings", json={"enabled": True}, timeout=30)

    def _add(self, client, username, kind="broadcast", title="TEST", active=True):
        r = client.post(f"{API}/channels", json={
            "username": username, "title": title, "kind": kind, "active": active,
        }, timeout=30)
        assert r.status_code == 200, r.text
        doc = r.json()
        self.created_ch.append(doc["id"])
        return doc

    def test_channel_crud_broadcast(self, client):
        doc = self._add(client, "@testchan", "broadcast", "Test")
        assert doc["username"] == "@testchan"
        assert doc["kind"] == "broadcast"
        assert doc["active"] is True
        assert "_id" not in doc

        lst = client.get(f"{API}/channels", params={"kind": "broadcast"}, timeout=30)
        assert lst.status_code == 200
        items = lst.json()
        assert isinstance(items, list)
        assert any(c["id"] == doc["id"] for c in items)
        assert all(c["kind"] == "broadcast" for c in items)

        patched = client.patch(f"{API}/channels/{doc['id']}", json={"active": False}, timeout=30)
        assert patched.status_code == 200, patched.text
        assert patched.json()["active"] is False

        # verify persistence of toggle
        items = client.get(f"{API}/channels", params={"kind": "broadcast"}, timeout=30).json()
        assert [c for c in items if c["id"] == doc["id"]][0]["active"] is False

        d = client.delete(f"{API}/channels/{doc['id']}", timeout=30)
        assert d.status_code == 200, d.text
        items = client.get(f"{API}/channels", timeout=30).json()
        assert not any(c["id"] == doc["id"] for c in items)
        self.created_ch.remove(doc["id"])

        assert client.delete(f"{API}/channels/{doc['id']}", timeout=30).status_code == 404

    def test_channel_crud_mandatory(self, client):
        doc = self._add(client, "-1001234567890", "mandatory", "Mandatory Test")
        assert doc["kind"] == "mandatory"
        items = client.get(f"{API}/channels", params={"kind": "mandatory"}, timeout=30).json()
        assert any(c["id"] == doc["id"] for c in items)
        # mandatory must not show under broadcast filter
        b = client.get(f"{API}/channels", params={"kind": "broadcast"}, timeout=30).json()
        assert not any(c["id"] == doc["id"] for c in b)
        client.delete(f"{API}/channels/{doc['id']}", timeout=30)
        self.created_ch.remove(doc["id"])

    def test_channel_invalid_kind(self, client):
        r = client.post(f"{API}/channels", json={
            "username": "@somechan", "title": "x", "kind": "weird",
        }, timeout=30)
        assert r.status_code == 400, r.text

    @pytest.mark.parametrize("bad", ["somechan", "100123456", "https://t.me/x"])
    def test_channel_invalid_username(self, client, bad):
        r = client.post(f"{API}/channels", json={"username": bad, "kind": "broadcast"}, timeout=30)
        assert r.status_code == 400, r.text

    def test_patch_missing_channel_404(self, client):
        r2 = client.patch(f"{API}/channels/TEST-nope", json={"active": True}, timeout=30)
        assert r2.status_code == 404, r2.text

    def test_broadcast_settings_toggle_and_gate(self, client, mongo_db):
        # ensure only fake channels are active so no real messages are sent
        f1 = self._add(client, FAKE_CH_1, "broadcast", "Fake1")

        g = client.get(f"{API}/broadcast/settings", timeout=30)
        assert g.status_code == 200, g.text
        assert g.json().get("enabled") is True

        p = client.put(f"{API}/broadcast/settings", json={"enabled": False}, timeout=30)
        assert p.status_code == 200 and p.json()["enabled"] is False
        assert client.get(f"{API}/broadcast/settings", timeout=30).json()["enabled"] is False

        blocked = client.post(f"{API}/broadcast/manual", json={
            "text": "TEST should be blocked", "channel_ids": [f1["id"]],
        }, timeout=60)
        assert blocked.status_code == 400, blocked.text
        assert "dinonaktifkan" in blocked.json().get("detail", "").lower()

        # re-enable
        client.put(f"{API}/broadcast/settings", json={"enabled": True}, timeout=30)
        assert client.get(f"{API}/broadcast/settings", timeout=30).json()["enabled"] is True

    def test_manual_broadcast_specific_channel_ids(self, client, mongo_db):
        f1 = [c for c in client.get(f"{API}/channels", timeout=30).json() if c["username"] == FAKE_CH_1]
        f1 = f1[0] if f1 else self._add(client, FAKE_CH_1, "broadcast", "Fake1")
        f2 = self._add(client, FAKE_CH_2, "broadcast", "Fake2")

        before = mongo_db.broadcast_logs.count_documents({})
        r = client.post(f"{API}/broadcast/manual", json={
            "text": "TEST single-channel broadcast", "channel_ids": [f2["id"]],
        }, timeout=90)
        # all target channels are fake -> every send fails -> 500 by design
        assert r.status_code == 500, f"expected 500 all-failed, got {r.status_code}: {r.text[:300]}"
        assert mongo_db.broadcast_logs.count_documents({}) == before + 1
        log = mongo_db.broadcast_logs.find_one({"text": "TEST single-channel broadcast"})
        assert log is not None
        self.created_log_ids.append(log["id"])
        assert log["status"] == "failed"
        chans = [x["channel"] for x in log["results"]]
        assert chans == [FAKE_CH_2], f"only the requested channel should be targeted: {chans}"
        assert log["results"][0]["ok"] is False and log["results"][0].get("error")

    def test_manual_broadcast_all_active_channels(self, client, mongo_db):
        # both fakes exist and active from prior test
        actives = [c for c in client.get(f"{API}/channels", params={"kind": "broadcast"}, timeout=30).json()
                   if c["active"]]
        assert len(actives) >= 2
        text = "TEST all-active broadcast"
        r = client.post(f"{API}/broadcast/manual", json={"text": text}, timeout=120)
        assert r.status_code == 500, r.text[:300]
        log = mongo_db.broadcast_logs.find_one({"text": text})
        assert log is not None
        self.created_log_ids.append(log["id"])
        targeted = sorted(x["channel"] for x in log["results"])
        assert targeted == sorted(c["username"] for c in actives), targeted

    def test_manual_broadcast_skips_inactive_channel(self, client, mongo_db):
        chs = client.get(f"{API}/channels", params={"kind": "broadcast"}, timeout=30).json()
        f2 = [c for c in chs if c["username"] == FAKE_CH_2][0]
        client.patch(f"{API}/channels/{f2['id']}", json={"active": False}, timeout=30)
        text = "TEST inactive-skip broadcast"
        client.post(f"{API}/broadcast/manual", json={"text": text}, timeout=120)
        log = mongo_db.broadcast_logs.find_one({"text": text})
        assert log is not None
        self.created_log_ids.append(log["id"])
        targeted = [x["channel"] for x in log["results"]]
        assert FAKE_CH_2 not in targeted, targeted
        client.patch(f"{API}/channels/{f2['id']}", json={"active": True}, timeout=30)

    def test_broadcast_resend_creates_new_log(self, client, mongo_db):
        # use an existing log (fake channels only active => no real message sent)
        logs = client.get(f"{API}/broadcast/logs", timeout=30)
        assert logs.status_code == 200
        assert isinstance(logs.json(), list)
        src = mongo_db.broadcast_logs.find_one({"text": "TEST single-channel broadcast"})
        assert src is not None
        before = mongo_db.broadcast_logs.count_documents({"type": "resend"})
        r = client.post(f"{API}/broadcast/logs/{src['id']}/resend", timeout=120)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("ok") is True
        assert "results" in body
        after = mongo_db.broadcast_logs.count_documents({"type": "resend"})
        assert after == before + 1
        new_log = mongo_db.broadcast_logs.find_one(
            {"type": "resend", "original_log_id": src["id"]})
        assert new_log is not None
        assert new_log["text"] == src["text"]
        assert new_log["status"] in ("sent", "failed")
        self.created_log_ids.append(new_log["id"])

    def test_resend_missing_log_404(self, client):
        r = client.post(f"{API}/broadcast/logs/TEST-nope/resend", timeout=30)
        assert r.status_code == 404, r.text

    def test_resend_blocked_when_disabled(self, client, mongo_db):
        src = mongo_db.broadcast_logs.find_one({"text": "TEST single-channel broadcast"})
        client.put(f"{API}/broadcast/settings", json={"enabled": False}, timeout=30)
        try:
            r = client.post(f"{API}/broadcast/logs/{src['id']}/resend", timeout=60)
            assert r.status_code == 400, r.text
        finally:
            client.put(f"{API}/broadcast/settings", json={"enabled": True}, timeout=30)

    def test_manual_broadcast_real_channel_once(self, client, mongo_db):
        """One real send to the configured channel to prove the success path works."""
        real = client.post(f"{API}/channels", json={
            "username": "@BigoCuan", "title": "TEST Real", "kind": "broadcast",
        }, timeout=30)
        assert real.status_code == 200, real.text
        rid = real.json()["id"]
        try:
            text = "TEST multi-channel broadcast (ignore) - QA"
            r = client.post(f"{API}/broadcast/manual", json={
                "text": text, "channel_ids": [rid],
            }, timeout=120)
            assert r.status_code == 200, r.text[:400]
            res = r.json()["results"]
            assert len(res) == 1 and res[0]["ok"] is True
            assert res[0]["channel"] == "@BigoCuan"
            assert res[0]["message_id"]
            log = mongo_db.broadcast_logs.find_one({"text": text})
            assert log and log["status"] == "sent"
            self.created_log_ids.append(log["id"])
        finally:
            client.delete(f"{API}/channels/{rid}", timeout=30)

    def test_manual_broadcast_empty_text_rejected(self, client):
        r = client.post(f"{API}/broadcast/manual", json={"text": ""}, timeout=30)
        assert r.status_code in (400, 422), r.text


# ---------------- FAQ ----------------
class TestFAQ:
    created = []

    @pytest.fixture(scope="class", autouse=True)
    def cleanup(self, client):
        yield
        for fid in self.created:
            client.delete(f"{API}/faqs/{fid}", timeout=30)

    def test_faq_crud_and_order(self, client):
        a = client.post(f"{API}/faqs", json={
            "question": "TEST_Q2", "answer": "A2", "order": 20}, timeout=30)
        b = client.post(f"{API}/faqs", json={
            "question": "TEST_Q1", "answer": "A1", "order": 10}, timeout=30)
        assert a.status_code == 200 and b.status_code == 200, (a.text, b.text)
        fa, fb = a.json(), b.json()
        self.created += [fa["id"], fb["id"]]
        assert "_id" not in fa
        assert fa["question"] == "TEST_Q2" and fa["order"] == 20

        lst = client.get(f"{API}/faqs", timeout=30)
        assert lst.status_code == 200
        items = lst.json()
        orders = [f["order"] for f in items]
        assert orders == sorted(orders), f"FAQs not sorted by order: {orders}"
        ids = [f["id"] for f in items]
        assert ids.index(fb["id"]) < ids.index(fa["id"])

        upd = client.patch(f"{API}/faqs/{fa['id']}", json={
            "answer": "A2 updated", "order": 5}, timeout=30)
        assert upd.status_code == 200, upd.text
        assert upd.json()["answer"] == "A2 updated"
        assert upd.json()["order"] == 5
        assert upd.json()["question"] == "TEST_Q2"

        # persistence
        items = client.get(f"{API}/faqs", timeout=30).json()
        got = [f for f in items if f["id"] == fa["id"]][0]
        assert got["answer"] == "A2 updated" and got["order"] == 5

        d = client.delete(f"{API}/faqs/{fa['id']}", timeout=30)
        assert d.status_code == 200
        self.created.remove(fa["id"])
        items = client.get(f"{API}/faqs", timeout=30).json()
        assert not any(f["id"] == fa["id"] for f in items)

    def test_faq_missing_404(self, client):
        assert client.patch(f"{API}/faqs/TEST-nope", json={"answer": "x"}, timeout=30).status_code == 404
        assert client.delete(f"{API}/faqs/TEST-nope", timeout=30).status_code == 404

    def test_faq_missing_required_fields(self, client):
        r = client.post(f"{API}/faqs", json={"question": "only q"}, timeout=30)
        assert r.status_code == 422, r.text


# ---------------- Support ----------------
class TestSupport:
    def test_get_and_update_support(self, client):
        g = client.get(f"{API}/support", timeout=30)
        assert g.status_code == 200, g.text
        doc = g.json()
        for k in ("whatsapp", "telegram_username", "extra_text"):
            assert k in doc, doc
        assert "_id" not in doc
        original = {k: doc.get(k, "") for k in ("whatsapp", "telegram_username", "extra_text")}

        payload = {"whatsapp": "+628123456789", "telegram_username": "BangJarr",
                   "extra_text": "TEST support hours 09-17"}
        p = client.put(f"{API}/support", json=payload, timeout=30)
        assert p.status_code == 200, p.text

        after = client.get(f"{API}/support", timeout=30).json()
        for k, v in payload.items():
            assert after[k] == v, after

        # restore
        client.put(f"{API}/support", json=original, timeout=30)


# ---------------- Auth on new endpoints ----------------
class TestNewEndpointsAuth:
    @pytest.mark.parametrize("method,path,body", [
        ("get", "/task-categories", None),
        ("get", "/channels", None),
        ("post", "/channels", {"username": "@x", "kind": "broadcast"}),
        ("patch", "/channels/x", {"active": True}),
        ("delete", "/channels/x", None),
        ("get", "/broadcast/settings", None),
        ("put", "/broadcast/settings", {"enabled": True}),
        ("get", "/broadcast/logs", None),
        ("post", "/broadcast/logs/x/resend", None),
        ("get", "/faqs", None),
        ("post", "/faqs", {"question": "q", "answer": "a"}),
        ("patch", "/faqs/x", {"answer": "a"}),
        ("delete", "/faqs/x", None),
        ("get", "/support", None),
        ("put", "/support", {"whatsapp": "1"}),
    ])
    def test_requires_bearer_token(self, method, path, body):
        r = getattr(requests, method)(f"{API}{path}", json=body, timeout=30)
        assert r.status_code in (401, 403), f"{method.upper()} {path} -> {r.status_code}"

    def test_bad_token_rejected(self):
        r = requests.get(f"{API}/faqs", headers={"Authorization": "Bearer garbage"}, timeout=30)
        assert r.status_code == 401, r.text
