"""BigoCuan Task Bot - FastAPI backend + Telegram bot"""
from fastapi import FastAPI, APIRouter, HTTPException, Depends, UploadFile, File, Form, status
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
import bcrypt

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


# ---------- Utils ----------
def now_iso():
    return datetime.now(timezone.utc).isoformat()


def new_id():
    return str(uuid.uuid4())


def format_idr(amount: int) -> str:
    return f"Rp {amount:,}".replace(",", ".")


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
    max_slots: int = 0  # 0 means unlimited


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    reward: Optional[int] = None
    instructions: Optional[str] = None
    link: Optional[str] = None
    max_slots: Optional[int] = None
    active: Optional[bool] = None


class SubmissionAction(BaseModel):
    reason: Optional[str] = None


class WithdrawApprove(BaseModel):
    note: str = ""
    image_base64: str = Field(..., min_length=100)  # required - admin must upload proof


class BalanceAdjust(BaseModel):
    amount: int  # can be negative
    note: str = ""


class BroadcastMessage(BaseModel):
    text: str = Field(..., min_length=1)
    image_base64: Optional[str] = None


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

    pipeline = [
        {"$match": {"status": "approved"}},
        {"$group": {"_id": None, "total": {"$sum": "$amount"}}},
    ]
    payout_agg = await db.withdrawals.aggregate(pipeline).to_list(1)
    total_payout = payout_agg[0]["total"] if payout_agg else 0

    pending_wd_agg = await db.withdrawals.aggregate([
        {"$match": {"status": "pending"}},
        {"$group": {"_id": None, "total": {"$sum": "$amount"}}},
    ]).to_list(1)
    pending_wd_amount = pending_wd_agg[0]["total"] if pending_wd_agg else 0

    # wallet distribution
    wallet_dist = await db.withdrawals.aggregate([
        {"$match": {"status": "approved"}},
        {"$group": {"_id": "$method", "count": {"$sum": 1}, "total": {"$sum": "$amount"}}},
    ]).to_list(10)

    # last 7 days activity
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
        daily.append({
            "date": day,
            "submissions": subs,
            "earnings": earn_agg[0]["total"] if earn_agg else 0,
        })

    return {
        "total_users": total_users,
        "pending_submissions": pending_subs,
        "pending_withdrawals": pending_wd,
        "pending_withdrawals_amount": pending_wd_amount,
        "total_payout": total_payout,
        "wallet_distribution": wallet_dist,
        "daily": daily,
        "bot_running": bot_state.get("running", False),
        "channel": os.environ.get("TELEGRAM_CHANNEL"),
    }


# ---------- Tasks ----------
@api.post("/tasks")
async def create_task(body: TaskCreate, admin: str = Depends(verify_admin)):
    doc = {
        "id": new_id(),
        "title": body.title,
        "description": body.description,
        "reward": body.reward,
        "instructions": body.instructions,
        "link": body.link,
        "max_slots": body.max_slots,
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
    return tasks


@api.patch("/tasks/{task_id}")
async def update_task(task_id: str, body: TaskUpdate, admin: str = Depends(verify_admin)):
    existing = await db.tasks.find_one({"id": task_id})
    if not existing:
        raise HTTPException(404, "Task tidak ditemukan")
    upd = {k: v for k, v in body.model_dump().items() if v is not None}
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
    # enrich
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
    await db.submissions.update_one({"id": sub_id}, {"$set": {
        "status": "approved",
        "reviewed_at": now_iso(),
    }})
    await db.users.update_one({"telegram_id": sub["telegram_id"]}, {
        "$inc": {"balance": reward, "total_earned": reward, "tasks_completed": 1},
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
    # Notify user via Telegram
    try:
        await send_dm(
            sub["telegram_id"],
            f"✅ *Task Disetujui*\n\n"
            f"Task: *{task['title']}*\n"
            f"Reward: *{format_idr(reward)}*\n\n"
            f"Saldo Anda telah diperbarui. Terima kasih!",
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
    await db.submissions.update_one({"id": sub_id}, {"$set": {
        "status": "rejected",
        "reject_reason": reason,
        "reviewed_at": now_iso(),
    }})
    try:
        await send_dm(
            sub["telegram_id"],
            f"❌ *Task Ditolak*\n\n"
            f"Task: *{task['title'] if task else '-'}*\n"
            f"Alasan: {reason}\n\n"
            f"Anda dapat mencoba lagi jika memenuhi syarat.",
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


@api.post("/withdrawals/{wd_id}/approve")
async def approve_withdraw(wd_id: str, body: WithdrawApprove, admin: str = Depends(verify_admin)):
    wd = await db.withdrawals.find_one({"id": wd_id})
    if not wd:
        raise HTTPException(404, "Withdrawal not found")
    if wd["status"] != "pending":
        raise HTTPException(400, "Sudah diproses")

    # Validate image_base64 decodes
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
        "status": "approved",
        "admin_note": body.note,
        "proof_image": body.image_base64,
        "reviewed_at": now_iso(),
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

    # Format text for user DM and channel broadcast
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
    channel_text = (
        f"💸 *BUKTI PEMBAYARAN WITHDRAW*\n\n"
        f"👤 Nama: *{display_name}*\n"
        f"🆔 Username: {username_tag}\n"
        f"💰 Nominal: *{idr}*\n"
        f"🏦 Metode: *{wd['method']}*\n\n"
        f"{body.note}\n\n"
        f"Bergabung sekarang dan dapatkan cuan dari task harian di BigoCuan!"
    )

    # Send DM to user (private)
    dm_ok = False
    dm_error = None
    try:
        await send_dm(wd["telegram_id"], user_text, image_base64=body.image_base64)
        dm_ok = True
    except Exception as e:
        dm_error = str(e)
        logger.error(f"Failed to DM user: {e}")

    # Broadcast to channel
    channel_msg_id = None
    broadcast_error = None
    try:
        channel_msg_id = await send_channel_broadcast(channel_text, image_base64=body.image_base64)
    except Exception as e:
        broadcast_error = str(e)
        logger.error(f"Failed to broadcast: {e}")

    # Log broadcast
    await db.broadcast_logs.insert_one({
        "id": new_id(),
        "type": "withdraw_proof",
        "withdrawal_id": wd_id,
        "telegram_id": wd["telegram_id"],
        "text": channel_text,
        "image_base64": body.image_base64,
        "channel_message_id": channel_msg_id,
        "status": "sent" if channel_msg_id else "failed",
        "error": broadcast_error,
        "created_at": now_iso(),
    })

    return {"ok": True, "dm_sent": dm_ok, "channel_message_id": channel_msg_id, "broadcast_error": broadcast_error, "dm_error": dm_error}


@api.post("/withdrawals/{wd_id}/reject")
async def reject_withdraw(wd_id: str, body: SubmissionAction, admin: str = Depends(verify_admin)):
    wd = await db.withdrawals.find_one({"id": wd_id})
    if not wd:
        raise HTTPException(404, "Withdrawal not found")
    if wd["status"] != "pending":
        raise HTTPException(400, "Sudah diproses")
    reason = body.reason or "Ditolak admin"
    # Refund balance
    await db.users.update_one({"telegram_id": wd["telegram_id"]}, {"$inc": {"balance": wd["amount"]}})
    await db.withdrawals.update_one({"id": wd_id}, {"$set": {
        "status": "rejected",
        "reject_reason": reason,
        "reviewed_at": now_iso(),
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
        await send_dm(
            wd["telegram_id"],
            f"❌ *Withdraw Ditolak*\n\nAlasan: {reason}\n\nSaldo Anda telah dikembalikan.",
        )
    except Exception as e:
        logger.error(f"Failed to notify user: {e}")
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
    return {"user": user, "balance_history": history, "submissions": subs, "withdrawals": wds}


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
        await send_dm(
            telegram_id,
            f"⚙️ *Penyesuaian Saldo*\n\nSaldo Anda diubah: *{sign}{format_idr(abs(body.amount))}*\nKeterangan: {body.note}",
        )
    except Exception as e:
        logger.error(e)
    return {"ok": True}


# ---------- Broadcast ----------
@api.get("/broadcast/logs")
async def broadcast_logs(admin: str = Depends(verify_admin)):
    logs = await db.broadcast_logs.find({}, {"_id": 0}).sort("created_at", -1).to_list(500)
    return logs


@api.post("/broadcast/manual")
async def manual_broadcast(body: BroadcastMessage, admin: str = Depends(verify_admin)):
    try:
        msg_id = await send_channel_broadcast(body.text, image_base64=body.image_base64)
    except Exception as e:
        await db.broadcast_logs.insert_one({
            "id": new_id(),
            "type": "manual",
            "text": body.text,
            "image_base64": body.image_base64,
            "channel_message_id": None,
            "status": "failed",
            "error": str(e),
            "created_at": now_iso(),
        })
        raise HTTPException(500, f"Gagal broadcast: {e}")
    await db.broadcast_logs.insert_one({
        "id": new_id(),
        "type": "manual",
        "text": body.text,
        "image_base64": body.image_base64,
        "channel_message_id": msg_id,
        "status": "sent",
        "created_at": now_iso(),
    })
    return {"ok": True, "message_id": msg_id}


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
    # Ensure indexes
    await db.users.create_index("telegram_id", unique=True)
    await db.tasks.create_index("id", unique=True)
    await db.submissions.create_index("id", unique=True)
    await db.withdrawals.create_index("id", unique=True)
    # Start bot in background
    asyncio.create_task(start_bot())
    logger.info("BigoCuan API started")


@app.on_event("shutdown")
async def on_shutdown():
    await stop_bot()
    client.close()
