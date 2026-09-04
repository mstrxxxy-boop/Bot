"""BigoCuan Task Bot - FastAPI backend + Telegram bot"""
from fastapi import FastAPI, APIRouter, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, timezone, timedelta
from pathlib import Path
import os
import uuid
import logging
import base64
import asyncio
import jwt as pyjwt

from telegram_bot import start_bot, stop_bot, send_dm, send_channel_broadcast, bot_state

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]
JWT_SECRET = os.environ["JWT_SECRET"]
ADMIN_USERNAME = os.environ["ADMIN_USERNAME"]
ADMIN_PASSWORD = os.environ["ADMIN_PASSWORD"]

client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]

# Expose db globally for the bot module
import telegram_bot as tb_module
tb_module.db = db

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("bigocuan")

app = FastAPI(title="BigoCuan Task Bot API")
api = APIRouter(prefix="/api")
security = HTTPBearer()

TASK_CATEGORIES = ["Social Media", "App Install", "Survey", "Other"]


# ---------- Utils ----------
def now_iso():
    return datetime.now(timezone.utc).isoformat()


def new_id():
    return str(uuid.uuid4())


def format_idr(amount: int) -> str:
    return f"Rp {amount:,}".replace(",", ".")


def censor_account(num: str) -> str:
    """Show first 4 and last 3 digits, mask middle. E.g. 081234567890 -> 0812*****890"""
    if not num:
        return ""
    s = str(num)
    if len(s) <= 7:
        return s[:2] + "*" * max(0, len(s) - 4) + s[-2:] if len(s) > 4 else s
    return s[:4] + "*" * 5 + s[-3:]


def make_token(sub: str) -> str:
    payload = {"sub": sub, "exp": datetime.now(timezone.utc) + timedelta(days=7)}
    return pyjwt.encode(payload, JWT_SECRET, algorithm="HS256")


def verify_admin(creds: HTTPAuthorizationCredentials = Depends(security)):
    try:
        payload = pyjwt.decode(creds.credentials, JWT_SECRET, algorithms=["HS256"])
        if payload.get("sub") != ADMIN_USERNAME:
            raise HTTPException(status_code=401, detail="Invalid token")
        return payload["sub"]
    except pyjwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")


# ---------- Models ----------
class LoginBody(BaseModel):
    username: str
    password: str


class TaskCreate(BaseModel):
    title: str
    description: str
    reward: int
    instructions: str = ""
    link: Optional[str] = None
    max_slots: int = 0
    category: str = "Other"
    code: Optional[str] = None
    example_image: Optional[str] = None
    require_photo: bool = True


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    reward: Optional[int] = None
    instructions: Optional[str] = None
    link: Optional[str] = None
    max_slots: Optional[int] = None
    active: Optional[bool] = None
    category: Optional[str] = None
    code: Optional[str] = None
    example_image: Optional[str] = None
    require_photo: Optional[bool] = None


class SubmissionAction(BaseModel):
    reason: Optional[str] = None


class WithdrawApprove(BaseModel):
    note: str = ""
    image_base64: Optional[str] = None  # OPTIONAL now


class ReferralSettings(BaseModel):
    percentage: int = Field(10, ge=0, le=100)
    welcome_text: str = ""
    signup_bonus: int = 0  # optional one-time signup bonus (0 = disabled)


class BalanceAdjust(BaseModel):
    amount: int
    note: str = ""


class BroadcastMessage(BaseModel):
    text: str = Field(..., min_length=1)
    image_base64: Optional[str] = None
    channel_ids: Optional[List[str]] = None  # if empty, broadcast to all active channels


class ChannelBody(BaseModel):
    username: str  # like @channelname or numeric -100...
    title: str = ""
    kind: str = "broadcast"  # "broadcast" or "mandatory"
    active: bool = True


class ChannelUpdate(BaseModel):
    username: Optional[str] = None
    title: Optional[str] = None
    active: Optional[bool] = None


class FAQBody(BaseModel):
    question: str
    answer: str
    order: int = 0


class FAQUpdate(BaseModel):
    question: Optional[str] = None
    answer: Optional[str] = None
    order: Optional[int] = None


class SupportBody(BaseModel):
    whatsapp: str = ""
    telegram_username: str = ""
    extra_text: str = ""


class BroadcastToggle(BaseModel):
    enabled: bool


# ---------- Auth ----------
@api.post("/auth/login")
async def login(body: LoginBody):
    if body.username != ADMIN_USERNAME or body.password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Kredensial salah")
    return {"token": make_token(body.username), "username": body.username}


@api.get("/auth/me")
async def me(admin: str = Depends(verify_admin)):
    return {"username": admin}


# ---------- Dashboard Stats ----------
@api.get("/stats/overview")
async def overview(admin: str = Depends(verify_admin)):
    total_users = await db.users.count_documents({})
    pending_subs = await db.submissions.count_documents({"status": "pending"})
    pending_wd = await db.withdrawals.count_documents({"status": "pending"})

    payout_agg = await db.withdrawals.aggregate([
        {"$match": {"status": "approved"}},
        {"$group": {"_id": None, "total": {"$sum": "$amount"}}},
    ]).to_list(1)
    total_payout = payout_agg[0]["total"] if payout_agg else 0

    pending_wd_agg = await db.withdrawals.aggregate([
        {"$match": {"status": "pending"}},
        {"$group": {"_id": None, "total": {"$sum": "$amount"}}},
    ]).to_list(1)
    pending_wd_amount = pending_wd_agg[0]["total"] if pending_wd_agg else 0

    # total pending balance across all users
    pending_bal_agg = await db.users.aggregate([
        {"$group": {"_id": None, "total": {"$sum": "$pending_balance"}}},
    ]).to_list(1)
    total_pending_balance = pending_bal_agg[0]["total"] if pending_bal_agg else 0

    wallet_dist = await db.withdrawals.aggregate([
        {"$match": {"status": "approved"}},
        {"$group": {"_id": "$method", "count": {"$sum": 1}, "total": {"$sum": "$amount"}}},
    ]).to_list(10)

    now = datetime.now(timezone.utc)
    daily = []
    for i in range(6, -1, -1):
        day_dt = now - timedelta(days=i)
        day = day_dt.strftime("%Y-%m-%d")
        next_day = (day_dt + timedelta(days=1)).strftime("%Y-%m-%d")
        subs = await db.submissions.count_documents({"created_at": {"$gte": f"{day}T00:00:00", "$lt": f"{next_day}T00:00:00"}})
        earn_agg = await db.balance_history.aggregate([
            {"$match": {"created_at": {"$gte": f"{day}T00:00:00", "$lt": f"{next_day}T00:00:00"}, "type": "credit"}},
            {"$group": {"_id": None, "total": {"$sum": "$amount"}}},
        ]).to_list(1)
        daily.append({"date": day, "submissions": subs, "earnings": earn_agg[0]["total"] if earn_agg else 0})

    return {
        "total_users": total_users,
        "pending_submissions": pending_subs,
        "pending_withdrawals": pending_wd,
        "pending_withdrawals_amount": pending_wd_amount,
        "total_pending_balance": total_pending_balance,
        "total_payout": total_payout,
        "wallet_distribution": wallet_dist,
        "daily": daily,
        "bot_running": bot_state.get("running", False),
        "channel": os.environ.get("TELEGRAM_CHANNEL"),
    }


# ---------- Tasks ----------
@api.get("/task-categories")
async def task_categories(admin: str = Depends(verify_admin)):
    return TASK_CATEGORIES


@api.post("/tasks")
async def create_task(body: TaskCreate, admin: str = Depends(verify_admin)):
    if body.category not in TASK_CATEGORIES:
        raise HTTPException(400, "Kategori tidak valid")
    doc = {
        "id": new_id(),
        "title": body.title,
        "description": body.description,
        "reward": body.reward,
        "instructions": body.instructions,
        "link": body.link,
        "max_slots": body.max_slots,
        "category": body.category,
        "code": body.code,
        "example_image": body.example_image,
        "require_photo": body.require_photo,
        "slots_used": 0,
        "active": True,
        "created_at": now_iso(),
    }
    await db.tasks.insert_one(doc)
    doc.pop("_id", None)
    return doc


@api.get("/tasks")
async def list_tasks(admin: str = Depends(verify_admin)):
    tasks = await db.tasks.find({}, {"_id": 0}).sort("created_at", -1).to_list(1000)
    for t in tasks:
        t["approved_count"] = await db.submissions.count_documents({"task_id": t["id"], "status": "approved"})
        t["pending_count"] = await db.submissions.count_documents({"task_id": t["id"], "status": "pending"})
        t.setdefault("category", "Other")
    return tasks


@api.patch("/tasks/{task_id}")
async def update_task(task_id: str, body: TaskUpdate, admin: str = Depends(verify_admin)):
    existing = await db.tasks.find_one({"id": task_id})
    if not existing:
        raise HTTPException(404, "Task tidak ditemukan")
    upd = {k: v for k, v in body.model_dump().items() if v is not None}
    if "category" in upd and upd["category"] not in TASK_CATEGORIES:
        raise HTTPException(400, "Kategori tidak valid")
    if upd:
        await db.tasks.update_one({"id": task_id}, {"$set": upd})
    doc = await db.tasks.find_one({"id": task_id}, {"_id": 0})
    return doc


@api.delete("/tasks/{task_id}")
async def delete_task(task_id: str, admin: str = Depends(verify_admin)):
    res = await db.tasks.delete_one({"id": task_id})
    if res.deleted_count == 0:
        raise HTTPException(404, "Task tidak ditemukan")
    return {"ok": True}


# ---------- Submissions ----------
@api.get("/submissions")
async def list_submissions(status_filter: Optional[str] = None, admin: str = Depends(verify_admin)):
    q = {}
    if status_filter and status_filter != "all":
        q["status"] = status_filter
    subs = await db.submissions.find(q, {"_id": 0}).sort("created_at", -1).to_list(2000)
    for s in subs:
        u = await db.users.find_one({"telegram_id": s["telegram_id"]}, {"_id": 0})
        t = await db.tasks.find_one({"id": s["task_id"]}, {"_id": 0})
        s["user"] = u
        s["task"] = t
    return subs


@api.post("/submissions/{sub_id}/approve")
async def approve_submission(sub_id: str, admin: str = Depends(verify_admin)):
    sub = await db.submissions.find_one({"id": sub_id})
    if not sub:
        raise HTTPException(404, "Submission not found")
    if sub["status"] != "pending":
        raise HTTPException(400, "Sudah diproses")
    task = await db.tasks.find_one({"id": sub["task_id"]})
    if not task:
        raise HTTPException(404, "Task not found")
    reward = task["reward"]
    await db.submissions.update_one({"id": sub_id}, {"$set": {"status": "approved", "reviewed_at": now_iso()}})
    # Move from pending_balance to active balance (clamp pending to 0)
    user_doc = await db.users.find_one({"telegram_id": sub["telegram_id"]})
    cur_pending = (user_doc or {}).get("pending_balance", 0)
    pending_delta = -min(cur_pending, reward)
    await db.users.update_one({"telegram_id": sub["telegram_id"]}, {
        "$inc": {
            "balance": reward,
            "pending_balance": pending_delta,
            "total_earned": reward,
            "tasks_completed": 1,
        },
    })
    await db.tasks.update_one({"id": sub["task_id"]}, {"$inc": {"slots_used": 1}})
    await db.balance_history.insert_one({
        "id": new_id(),
        "telegram_id": sub["telegram_id"],
        "type": "credit",
        "amount": reward,
        "note": f"Task disetujui: {task['title']}",
        "ref_id": sub_id,
        "created_at": now_iso(),
    })
    # Referral commission: give inviter X% of this reward
    ref_settings = await db.settings.find_one({"id": "referral"}) or {}
    ref_pct = int(ref_settings.get("percentage", 10))
    inviter_id = (user_doc or {}).get("referred_by")
    if inviter_id and ref_pct > 0:
        commission = int(reward * ref_pct / 100)
        if commission > 0:
            await db.users.update_one({"telegram_id": inviter_id}, {
                "$inc": {"balance": commission, "total_earned": commission, "referral_earnings": commission},
            })
            await db.balance_history.insert_one({
                "id": new_id(),
                "telegram_id": inviter_id,
                "type": "credit",
                "amount": commission,
                "note": f"Komisi referral {ref_pct}% dari @{(user_doc or {}).get('username') or (user_doc or {}).get('first_name', 'user')}",
                "ref_id": sub_id,
                "created_at": now_iso(),
            })
            try:
                await send_dm(
                    inviter_id,
                    f"🎉 *Komisi Referral!*\n\n"
                    f"Kamu dapat *{format_idr(commission)}* ({ref_pct}%) dari task yang diselesaikan oleh referralmu.",
                )
            except Exception:
                pass
    try:
        await send_dm(
            sub["telegram_id"],
            f"✅ *Task Disetujui*\n\n"
            f"Task: *{task['title']}*\n"
            f"Reward: *{format_idr(reward)}*\n\n"
            f"Saldo aktif Anda telah diperbarui!",
        )
    except Exception as e:
        logger.error(f"Failed to notify user: {e}")
    return {"ok": True}


@api.post("/submissions/{sub_id}/reject")
async def reject_submission(sub_id: str, body: SubmissionAction, admin: str = Depends(verify_admin)):
    sub = await db.submissions.find_one({"id": sub_id})
    if not sub:
        raise HTTPException(404, "Submission not found")
    if sub["status"] != "pending":
        raise HTTPException(400, "Sudah diproses")
    task = await db.tasks.find_one({"id": sub["task_id"]})
    reason = body.reason or "Bukti tidak valid"
    reward = task["reward"] if task else 0
    await db.submissions.update_one({"id": sub_id}, {"$set": {
        "status": "rejected", "reject_reason": reason, "reviewed_at": now_iso(),
    }})
    # Remove from pending_balance (clamp to 0), add to rejected_total
    user_doc = await db.users.find_one({"telegram_id": sub["telegram_id"]})
    cur_pending = (user_doc or {}).get("pending_balance", 0)
    pending_delta = -min(cur_pending, reward)
    await db.users.update_one({"telegram_id": sub["telegram_id"]}, {
        "$inc": {"pending_balance": pending_delta, "rejected_total": reward, "tasks_rejected": 1},
    })
    try:
        await send_dm(
            sub["telegram_id"],
            f"❌ *Task Ditolak*\n\nTask: *{task['title'] if task else '-'}*\nAlasan: {reason}",
        )
    except Exception as e:
        logger.error(f"Failed to notify user: {e}")
    return {"ok": True}


# ---------- Withdrawals ----------
@api.get("/withdrawals")
async def list_withdrawals(status_filter: Optional[str] = None, admin: str = Depends(verify_admin)):
    q = {}
    if status_filter and status_filter != "all":
        q["status"] = status_filter
    ws = await db.withdrawals.find(q, {"_id": 0}).sort("created_at", -1).to_list(2000)
    for w in ws:
        u = await db.users.find_one({"telegram_id": w["telegram_id"]}, {"_id": 0})
        w["user"] = u
    return ws


async def _broadcast_to_all_active(text: str, image_base64: Optional[str]) -> dict:
    """Broadcast to all active broadcast channels. Returns dict per channel."""
    settings = await db.broadcast_settings.find_one({"id": "default"}) or {"enabled": True}
    if not settings.get("enabled", True):
        return {"disabled": True, "channels": []}
    channels = await db.channels.find({"kind": "broadcast", "active": True}, {"_id": 0}).to_list(50)
    # Include default channel from .env if no channels configured
    if not channels:
        channels = [{"username": os.environ.get("TELEGRAM_CHANNEL"), "title": "Default"}]
    results = []
    for ch in channels:
        try:
            msg_id = await send_channel_broadcast(text, image_base64=image_base64, channel=ch["username"])
            results.append({"channel": ch["username"], "message_id": msg_id, "ok": True})
        except Exception as e:
            results.append({"channel": ch["username"], "ok": False, "error": str(e)})
    return {"disabled": False, "channels": results}


@api.post("/withdrawals/{wd_id}/approve")
async def approve_withdraw(wd_id: str, body: WithdrawApprove, admin: str = Depends(verify_admin)):
    wd = await db.withdrawals.find_one({"id": wd_id})
    if not wd:
        raise HTTPException(404, "Withdrawal not found")
    if wd["status"] != "pending":
        raise HTTPException(400, "Sudah diproses")

    # Image is OPTIONAL. If provided, validate.
    if body.image_base64:
        try:
            raw = body.image_base64.split(",", 1)[1] if body.image_base64.startswith("data:") else body.image_base64
            img_bytes = base64.b64decode(raw, validate=True)
            if len(img_bytes) < 500:
                raise ValueError("Image too small")
        except Exception:
            raise HTTPException(400, "Bukti pembayaran tidak valid (base64 rusak atau terlalu kecil)")

    user = await db.users.find_one({"telegram_id": wd["telegram_id"]})
    if not user:
        raise HTTPException(404, "User not found")

    await db.withdrawals.update_one({"id": wd_id}, {"$set": {
        "status": "approved", "admin_note": body.note, "proof_image": body.image_base64, "reviewed_at": now_iso(),
    }})
    await db.balance_history.insert_one({
        "id": new_id(),
        "telegram_id": wd["telegram_id"],
        "type": "withdraw",
        "amount": wd["amount"],
        "note": f"Withdraw via {wd['method']} - {wd['account_name']}",
        "ref_id": wd_id,
        "created_at": now_iso(),
    })

    idr = format_idr(wd["amount"])
    user_text = (
        f"✅ *Withdraw Berhasil*\n\n"
        f"Nominal: *{idr}*\n"
        f"Metode: *{wd['method']}*\n"
        f"Nomor: `{wd['account_number']}`\n"
        f"Atas Nama: {wd['account_name']}\n\n"
        f"{body.note}\n\n"
        f"Terima kasih sudah bergabung di BigoCuan!"
    )
    display_name = user.get("first_name") or user.get("username") or "User"
    username_tag = f"@{user['username']}" if user.get("username") else "(no username)"
    censored = censor_account(wd["account_number"])
    channel_text = (
        f"💸 *BUKTI PEMBAYARAN WITHDRAW*\n\n"
        f"👤 Nama: *{display_name}*\n"
        f"🆔 Username: {username_tag}\n"
        f"💰 Nominal: *{idr}*\n"
        f"🏦 Metode: *{wd['method']}*\n"
        f"📱 Nomor: `{censored}`\n\n"
        f"{body.note}\n\n"
        f"Bergabung sekarang dan dapatkan cuan dari task harian di BigoCuan!"
    )

    dm_ok = False
    dm_error = None
    try:
        await send_dm(wd["telegram_id"], user_text, image_base64=body.image_base64)
        dm_ok = True
    except Exception as e:
        dm_error = str(e)

    broadcast_res = await _broadcast_to_all_active(channel_text, body.image_base64)

    await db.broadcast_logs.insert_one({
        "id": new_id(),
        "type": "withdraw_proof",
        "withdrawal_id": wd_id,
        "telegram_id": wd["telegram_id"],
        "text": channel_text,
        "image_base64": body.image_base64,
        "results": broadcast_res.get("channels", []),
        "disabled": broadcast_res.get("disabled", False),
        "status": "sent" if any(r.get("ok") for r in broadcast_res.get("channels", [])) else "failed",
        "created_at": now_iso(),
    })

    return {"ok": True, "dm_sent": dm_ok, "broadcast": broadcast_res, "dm_error": dm_error}


@api.post("/withdrawals/{wd_id}/reject")
async def reject_withdraw(wd_id: str, body: SubmissionAction, admin: str = Depends(verify_admin)):
    wd = await db.withdrawals.find_one({"id": wd_id})
    if not wd:
        raise HTTPException(404, "Withdrawal not found")
    if wd["status"] != "pending":
        raise HTTPException(400, "Sudah diproses")
    reason = body.reason or "Ditolak admin"
    await db.users.update_one({"telegram_id": wd["telegram_id"]}, {"$inc": {"balance": wd["amount"]}})
    await db.withdrawals.update_one({"id": wd_id}, {"$set": {
        "status": "rejected", "reject_reason": reason, "reviewed_at": now_iso(),
    }})
    await db.balance_history.insert_one({
        "id": new_id(),
        "telegram_id": wd["telegram_id"],
        "type": "refund",
        "amount": wd["amount"],
        "note": f"Refund withdraw ditolak: {reason}",
        "ref_id": wd_id,
        "created_at": now_iso(),
    })
    try:
        await send_dm(wd["telegram_id"], f"❌ *Withdraw Ditolak*\n\nAlasan: {reason}\n\nSaldo dikembalikan.")
    except Exception as e:
        logger.error(e)
    return {"ok": True}


# ---------- Users ----------
@api.get("/users")
async def list_users(admin: str = Depends(verify_admin)):
    users = await db.users.find({}, {"_id": 0}).sort("created_at", -1).to_list(2000)
    return users


@api.get("/users/{telegram_id}")
async def user_detail(telegram_id: int, admin: str = Depends(verify_admin)):
    user = await db.users.find_one({"telegram_id": telegram_id}, {"_id": 0})
    if not user:
        raise HTTPException(404, "User not found")
    history = await db.balance_history.find({"telegram_id": telegram_id}, {"_id": 0}).sort("created_at", -1).to_list(500)
    subs = await db.submissions.find({"telegram_id": telegram_id}, {"_id": 0}).sort("created_at", -1).to_list(500)
    wds = await db.withdrawals.find({"telegram_id": telegram_id}, {"_id": 0}).sort("created_at", -1).to_list(500)
    referrals = await db.users.find({"referred_by": telegram_id}, {"_id": 0, "telegram_id": 1, "username": 1, "first_name": 1, "created_at": 1}).to_list(200)
    return {"user": user, "balance_history": history, "submissions": subs, "withdrawals": wds, "referrals": referrals}


@api.post("/users/{telegram_id}/adjust")
async def adjust_balance(telegram_id: int, body: BalanceAdjust, admin: str = Depends(verify_admin)):
    user = await db.users.find_one({"telegram_id": telegram_id})
    if not user:
        raise HTTPException(404, "User not found")
    new_balance = user.get("balance", 0) + body.amount
    if new_balance < 0:
        raise HTTPException(400, f"Saldo tidak boleh negatif (saldo saat ini: {user.get('balance', 0)})")
    await db.users.update_one({"telegram_id": telegram_id}, {"$inc": {"balance": body.amount}})
    await db.balance_history.insert_one({
        "id": new_id(),
        "telegram_id": telegram_id,
        "type": "credit" if body.amount > 0 else "debit",
        "amount": abs(body.amount),
        "note": f"Penyesuaian admin: {body.note}",
        "created_at": now_iso(),
    })
    try:
        sign = "+" if body.amount > 0 else "-"
        await send_dm(telegram_id, f"⚙️ *Penyesuaian Saldo*\n\nSaldo Anda diubah: *{sign}{format_idr(abs(body.amount))}*\nKeterangan: {body.note}")
    except Exception as e:
        logger.error(e)
    return {"ok": True}


# ---------- Channels (broadcast + mandatory) ----------
@api.get("/channels")
async def list_channels(kind: Optional[str] = None, admin: str = Depends(verify_admin)):
    q = {}
    if kind:
        q["kind"] = kind
    chs = await db.channels.find(q, {"_id": 0}).sort("created_at", -1).to_list(200)
    return chs


@api.post("/channels")
async def add_channel(body: ChannelBody, admin: str = Depends(verify_admin)):
    if body.kind not in ("broadcast", "mandatory"):
        raise HTTPException(400, "kind harus 'broadcast' atau 'mandatory'")
    username = body.username.strip()
    if not (username.startswith("@") or username.startswith("-100")):
        raise HTTPException(400, "Username channel harus diawali @ atau ID -100...")
    dup = await db.channels.find_one({"username": username, "kind": body.kind})
    if dup:
        raise HTTPException(400, "Channel dengan username & kind ini sudah ada")
    doc = {
        "id": new_id(),
        "username": username,
        "title": body.title or username,
        "kind": body.kind,
        "active": body.active,
        "created_at": now_iso(),
    }
    await db.channels.insert_one(doc)
    doc.pop("_id", None)
    return doc


@api.patch("/channels/{ch_id}")
async def update_channel(ch_id: str, body: ChannelUpdate, admin: str = Depends(verify_admin)):
    existing = await db.channels.find_one({"id": ch_id})
    if not existing:
        raise HTTPException(404, "Channel not found")
    upd = {k: v for k, v in body.model_dump().items() if v is not None}
    if upd:
        await db.channels.update_one({"id": ch_id}, {"$set": upd})
    doc = await db.channels.find_one({"id": ch_id}, {"_id": 0})
    return doc


@api.delete("/channels/{ch_id}")
async def delete_channel(ch_id: str, admin: str = Depends(verify_admin)):
    r = await db.channels.delete_one({"id": ch_id})
    if r.deleted_count == 0:
        raise HTTPException(404, "Channel not found")
    return {"ok": True}


# ---------- Broadcast Settings ----------
@api.get("/broadcast/settings")
async def get_broadcast_settings(admin: str = Depends(verify_admin)):
    doc = await db.broadcast_settings.find_one({"id": "default"}, {"_id": 0})
    if not doc:
        doc = {"id": "default", "enabled": True}
        await db.broadcast_settings.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


@api.put("/broadcast/settings")
async def set_broadcast_settings(body: BroadcastToggle, admin: str = Depends(verify_admin)):
    await db.broadcast_settings.update_one(
        {"id": "default"}, {"$set": {"enabled": body.enabled}}, upsert=True,
    )
    return {"ok": True, "enabled": body.enabled}


@api.get("/broadcast/logs")
async def broadcast_logs(admin: str = Depends(verify_admin)):
    logs = await db.broadcast_logs.find({}, {"_id": 0}).sort("created_at", -1).to_list(500)
    return logs


@api.post("/broadcast/manual")
async def manual_broadcast(body: BroadcastMessage, admin: str = Depends(verify_admin)):
    settings = await db.broadcast_settings.find_one({"id": "default"}) or {"enabled": True}
    if not settings.get("enabled", True):
        raise HTTPException(400, "Broadcast dinonaktifkan (master toggle OFF)")

    # If channel_ids provided, use those specific channels; otherwise all active
    if body.channel_ids:
        channels = await db.channels.find({"id": {"$in": body.channel_ids}, "kind": "broadcast", "active": True}, {"_id": 0}).to_list(50)
    else:
        channels = await db.channels.find({"kind": "broadcast", "active": True}, {"_id": 0}).to_list(50)
    if not channels:
        channels = [{"username": os.environ.get("TELEGRAM_CHANNEL"), "title": "Default"}]

    results = []
    for ch in channels:
        try:
            msg_id = await send_channel_broadcast(body.text, image_base64=body.image_base64, channel=ch["username"])
            results.append({"channel": ch["username"], "message_id": msg_id, "ok": True})
        except Exception as e:
            results.append({"channel": ch["username"], "ok": False, "error": str(e)})

    await db.broadcast_logs.insert_one({
        "id": new_id(),
        "type": "manual",
        "text": body.text,
        "image_base64": body.image_base64,
        "results": results,
        "status": "sent" if any(r.get("ok") for r in results) else "failed",
        "created_at": now_iso(),
    })
    if not any(r.get("ok") for r in results):
        raise HTTPException(500, f"Semua channel gagal: {results}")
    return {"ok": True, "results": results}


@api.post("/broadcast/logs/{log_id}/resend")
async def resend_broadcast(log_id: str, admin: str = Depends(verify_admin)):
    """Resend a failed broadcast."""
    log = await db.broadcast_logs.find_one({"id": log_id})
    if not log:
        raise HTTPException(404, "Log tidak ditemukan")
    settings = await db.broadcast_settings.find_one({"id": "default"}) or {"enabled": True}
    if not settings.get("enabled", True):
        raise HTTPException(400, "Broadcast dinonaktifkan")
    res = await _broadcast_to_all_active(log["text"], log.get("image_base64"))
    await db.broadcast_logs.insert_one({
        "id": new_id(),
        "type": "resend",
        "original_log_id": log_id,
        "text": log["text"],
        "image_base64": log.get("image_base64"),
        "results": res.get("channels", []),
        "status": "sent" if any(r.get("ok") for r in res.get("channels", [])) else "failed",
        "created_at": now_iso(),
    })
    return {"ok": True, "results": res}


# ---------- FAQ ----------
@api.get("/faqs")
async def list_faqs(admin: str = Depends(verify_admin)):
    return await db.faqs.find({}, {"_id": 0}).sort("order", 1).to_list(200)


@api.post("/faqs")
async def create_faq(body: FAQBody, admin: str = Depends(verify_admin)):
    doc = {"id": new_id(), "question": body.question, "answer": body.answer, "order": body.order, "created_at": now_iso()}
    await db.faqs.insert_one(doc)
    doc.pop("_id", None)
    return doc


@api.patch("/faqs/{fid}")
async def update_faq(fid: str, body: FAQUpdate, admin: str = Depends(verify_admin)):
    existing = await db.faqs.find_one({"id": fid})
    if not existing:
        raise HTTPException(404, "FAQ not found")
    upd = {k: v for k, v in body.model_dump().items() if v is not None}
    if upd:
        await db.faqs.update_one({"id": fid}, {"$set": upd})
    return await db.faqs.find_one({"id": fid}, {"_id": 0})


@api.delete("/faqs/{fid}")
async def delete_faq(fid: str, admin: str = Depends(verify_admin)):
    r = await db.faqs.delete_one({"id": fid})
    if r.deleted_count == 0:
        raise HTTPException(404, "FAQ not found")
    return {"ok": True}


# ---------- Support ----------
@api.get("/support")
async def get_support(admin: str = Depends(verify_admin)):
    doc = await db.support.find_one({"id": "default"}, {"_id": 0})
    if not doc:
        doc = {"id": "default", "whatsapp": "", "telegram_username": "", "extra_text": ""}
        await db.support.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


@api.put("/support")
async def set_support(body: SupportBody, admin: str = Depends(verify_admin)):
    await db.support.update_one(
        {"id": "default"},
        {"$set": {"whatsapp": body.whatsapp, "telegram_username": body.telegram_username, "extra_text": body.extra_text}},
        upsert=True,
    )
    return {"ok": True}


# ---------- Referral Settings ----------
@api.get("/referral/settings")
async def get_referral_settings(admin: str = Depends(verify_admin)):
    doc = await db.settings.find_one({"id": "referral"}, {"_id": 0})
    if not doc:
        doc = {
            "id": "referral",
            "percentage": 10,
            "signup_bonus": 0,
            "welcome_text": (
                "👥 *Ajak Teman & Dapat Komisi*\n\n"
                "Ajak teman join BigoCuan dan dapatkan *10%* dari setiap task yang mereka selesaikan!\n\n"
                "Komisi otomatis masuk ke saldo Anda saat teman Anda menyelesaikan task."
            ),
        }
        await db.settings.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


@api.put("/referral/settings")
async def set_referral_settings(body: ReferralSettings, admin: str = Depends(verify_admin)):
    await db.settings.update_one(
        {"id": "referral"},
        {"$set": {
            "percentage": body.percentage,
            "welcome_text": body.welcome_text,
            "signup_bonus": body.signup_bonus,
        }},
        upsert=True,
    )
    return {"ok": True}


@api.get("/users/{telegram_id}/referrals")
async def user_referrals(telegram_id: int, admin: str = Depends(verify_admin)):
    """Detailed referral dashboard for a specific user."""
    user = await db.users.find_one({"telegram_id": telegram_id}, {"_id": 0})
    if not user:
        raise HTTPException(404, "User not found")
    refs = await db.users.find({"referred_by": telegram_id}, {"_id": 0}).to_list(500)
    enriched = []
    for r in refs:
        tasks_done = await db.submissions.count_documents({"telegram_id": r["telegram_id"], "status": "approved"})
        enriched.append({
            "telegram_id": r["telegram_id"],
            "username": r.get("username"),
            "first_name": r.get("first_name"),
            "balance": r.get("balance", 0),
            "total_earned": r.get("total_earned", 0),
            "tasks_completed": tasks_done,
            "created_at": r.get("created_at"),
        })
    return {
        "referral_count": len(enriched),
        "referral_earnings": user.get("referral_earnings", 0),
        "referrals": enriched,
    }


@api.get("/health")
async def health():
    return {"status": "ok", "bot_running": bot_state.get("running", False)}


app.include_router(api)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def on_startup():
    await db.users.create_index("telegram_id", unique=True)
    await db.tasks.create_index("id", unique=True)
    await db.submissions.create_index("id", unique=True)
    await db.withdrawals.create_index("id", unique=True)
    await db.channels.create_index("id", unique=True)
    await db.faqs.create_index("id", unique=True)
    # Migrate existing users: ensure new fields exist
    await db.users.update_many({"pending_balance": {"$exists": False}}, {"$set": {"pending_balance": 0}})
    await db.users.update_many({"rejected_total": {"$exists": False}}, {"$set": {"rejected_total": 0}})
    await db.users.update_many({"tasks_rejected": {"$exists": False}}, {"$set": {"tasks_rejected": 0}})
    await db.users.update_many({"referred_by": {"$exists": False}}, {"$set": {"referred_by": None}})
    await db.users.update_many({"referral_count": {"$exists": False}}, {"$set": {"referral_count": 0}})
    await db.users.update_many({"verified_channels": {"$exists": False}}, {"$set": {"verified_channels": False}})
    await db.users.update_many({"referral_earnings": {"$exists": False}}, {"$set": {"referral_earnings": 0}})
    asyncio.create_task(start_bot())
    logger.info("BigoCuan API started")


@app.on_event("shutdown")
async def on_shutdown():
    await stop_bot()
    client.close()
