"""Telegram bot logic for BigoCuan. python-telegram-bot v21."""
import os
import logging
import base64
import uuid
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Optional, List
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.error import BadRequest
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, MessageHandler, ContextTypes, filters,
)

logger = logging.getLogger("bigocuan.bot")

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
DEFAULT_CHANNEL = os.environ["TELEGRAM_CHANNEL"]
ADMIN_TELEGRAM_ID = int(os.environ.get("ADMIN_TELEGRAM_ID", "0"))
ADMIN_TELEGRAM_USERNAME = os.environ.get("ADMIN_TELEGRAM_USERNAME", "")
REFERRAL_BONUS = int(os.environ.get("REFERRAL_BONUS", "1000"))

db = None
bot_state = {"running": False, "app": None}


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def new_id():
    return str(uuid.uuid4())


def format_idr(amount: int) -> str:
    return f"Rp {amount:,}".replace(",", ".")


def is_admin_user(user) -> bool:
    if ADMIN_TELEGRAM_ID and user.id == ADMIN_TELEGRAM_ID:
        return True
    if ADMIN_TELEGRAM_USERNAME and user.username and user.username.lower() == ADMIN_TELEGRAM_USERNAME.lower():
        return True
    return False


# ---------- Force-subscribe verification ----------
async def check_mandatory_channels(bot, telegram_id: int) -> (bool, list):
    """Check if user is member of all mandatory channels. Returns (ok, missing_channels)."""
    channels = await db.channels.find({"kind": "mandatory", "active": True}, {"_id": 0}).to_list(50)
    missing = []
    for ch in channels:
        try:
            member = await bot.get_chat_member(chat_id=ch["username"], user_id=telegram_id)
            if member.status in ("left", "kicked"):
                missing.append(ch)
        except Exception as e:
            logger.warning(f"Cannot check membership for {ch['username']}: {e}")
            # If we can't check, treat as missing (safer)
            missing.append(ch)
    return (len(missing) == 0, missing)


async def send_verify_prompt(update_or_query, missing: list, ctx):
    text = (
        "🔒 *Verifikasi Diperlukan*\n\n"
        "Sebelum menggunakan bot, silakan gabung ke channel/grup wajib berikut:\n\n"
    )
    buttons = []
    for ch in missing:
        u = ch["username"]
        link = f"https://t.me/{u.lstrip('@')}" if u.startswith("@") else "https://t.me/"
        text += f"• [{ch.get('title', u)}]({link})\n"
        buttons.append([InlineKeyboardButton(f"➡️ Gabung {ch.get('title', u)}", url=link)])
    buttons.append([InlineKeyboardButton("✅ Saya Sudah Gabung", callback_data="verify:check")])
    kb = InlineKeyboardMarkup(buttons)
    if hasattr(update_or_query, "edit_message_text"):
        try:
            await update_or_query.edit_message_text(text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN, disable_web_page_preview=True)
            return
        except Exception:
            pass
    target = update_or_query.message if hasattr(update_or_query, "message") else update_or_query
    await target.reply_text(text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN, disable_web_page_preview=True)


# ---------- Helpers ----------
async def get_or_create_user(user, ref_id: Optional[int] = None) -> dict:
    doc = await db.users.find_one({"telegram_id": user.id})
    if doc:
        upd = {}
        if doc.get("username") != user.username:
            upd["username"] = user.username
        if doc.get("first_name") != user.first_name:
            upd["first_name"] = user.first_name
        if upd:
            await db.users.update_one({"telegram_id": user.id}, {"$set": upd})
            doc.update(upd)
        return doc
    new_user = {
        "telegram_id": user.id,
        "username": user.username,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "balance": 0,
        "pending_balance": 0,
        "rejected_total": 0,
        "total_earned": 0,
        "tasks_completed": 0,
        "tasks_rejected": 0,
        "bank": None,
        "referred_by": ref_id if (ref_id and ref_id != user.id) else None,
        "referral_count": 0,
        "referral_earnings": 0,
        "verified_channels": False,
        "created_at": now_iso(),
    }
    await db.users.insert_one(dict(new_user))
    # Increment inviter's referral_count and optional signup bonus
    if ref_id and ref_id != user.id:
        inviter = await db.users.find_one({"telegram_id": ref_id})
        if inviter:
            settings = await db.settings.find_one({"id": "referral"}) or {}
            signup_bonus = int(settings.get("signup_bonus", 0))
            inc = {"referral_count": 1}
            if signup_bonus > 0:
                inc["balance"] = signup_bonus
                inc["total_earned"] = signup_bonus
                inc["referral_earnings"] = signup_bonus
            await db.users.update_one({"telegram_id": ref_id}, {"$inc": inc})
            if signup_bonus > 0:
                await db.balance_history.insert_one({
                    "id": new_id(),
                    "telegram_id": ref_id,
                    "type": "credit",
                    "amount": signup_bonus,
                    "note": f"Bonus signup referral dari @{user.username or user.first_name}",
                    "created_at": now_iso(),
                })
            try:
                msg = f"🎉 Referral Baru!\n\n{user.first_name or 'Teman'} baru saja join lewat link Anda."
                if signup_bonus > 0:
                    msg += f"\n\nBonus signup: *{format_idr(signup_bonus)}*"
                await bot_state["app"].bot.send_message(chat_id=ref_id, text=msg, parse_mode=ParseMode.MARKDOWN)
            except Exception:
                pass
    return new_user


def main_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 Task Tersedia", callback_data="menu:tasks")],
        [
            InlineKeyboardButton("👤 Profil", callback_data="menu:profile"),
            InlineKeyboardButton("💰 Saldo", callback_data="menu:balance"),
        ],
        [
            InlineKeyboardButton("📜 Riwayat Task", callback_data="menu:history"),
            InlineKeyboardButton("💸 Riwayat Saldo", callback_data="menu:balhist"),
        ],
        [
            InlineKeyboardButton("🏦 Bank/E-Wallet", callback_data="menu:bank"),
            InlineKeyboardButton("💵 Withdraw", callback_data="menu:withdraw"),
        ],
        [
            InlineKeyboardButton("👥 Ajak Teman", callback_data="menu:referral"),
            InlineKeyboardButton("❓ Bantuan", callback_data="menu:help"),
        ],
    ])


def admin_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 Kelola Tasks", callback_data="adm:tasks")],
        [InlineKeyboardButton("➕ Buat Task Baru", callback_data="adm:new_task")],
        [InlineKeyboardButton("📢 Kirim Broadcast", callback_data="adm:broadcast")],
        [InlineKeyboardButton("📊 Statistik", callback_data="adm:stats")],
        [InlineKeyboardButton("⬅️ Menu User", callback_data="menu:home")],
    ])


async def show_main_menu(update_or_query, user_doc, edit=False):
    text = (
        f"🎉 *Selamat datang di BigoCuan!*\n\n"
        f"Halo *{user_doc.get('first_name') or 'User'}*!\n"
        f"💰 Saldo Aktif: *{format_idr(user_doc.get('balance', 0))}*\n"
        f"⏳ Saldo Pending: *{format_idr(user_doc.get('pending_balance', 0))}*\n\n"
        f"Pilih menu di bawah:"
    )
    kb = main_menu_keyboard()
    if edit and hasattr(update_or_query, "edit_message_text"):
        try:
            await update_or_query.edit_message_text(text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)
        except Exception:
            await update_or_query.message.reply_text(text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)
    else:
        await update_or_query.message.reply_text(text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)


# ---------- Command Handlers ----------
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    # Parse ref payload
    ref_id = None
    if ctx.args and ctx.args[0].startswith("ref"):
        try:
            ref_id = int(ctx.args[0].replace("ref", ""))
        except ValueError:
            ref_id = None

    user_doc = await get_or_create_user(user, ref_id=ref_id)

    # Admin: show admin panel directly on /start via /admin command instead
    # Verify mandatory channels
    ok, missing = await check_mandatory_channels(ctx.bot, user.id)
    if not ok and missing:
        await send_verify_prompt(update, missing, ctx)
        return

    if not user_doc.get("verified_channels"):
        await db.users.update_one({"telegram_id": user.id}, {"$set": {"verified_channels": True}})

    await show_main_menu(update, user_doc)


async def cmd_admin(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin_user(update.effective_user):
        await update.message.reply_text("⛔ Akses ditolak. Command ini hanya untuk admin.")
        return
    await update.message.reply_text(
        "🛠️ *Panel Admin BigoCuan*\n\nPilih aksi:",
        reply_markup=admin_menu_keyboard(),
        parse_mode=ParseMode.MARKDOWN,
    )


async def cmd_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data.clear()
    await update.message.reply_text("Dibatalkan. /start untuk kembali.")


async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "*BigoCuan Bot*\n\n"
        "/start - Menu utama\n"
        "/admin - Panel admin (khusus admin)\n"
        "/cancel - Batalkan aksi\n",
        parse_mode=ParseMode.MARKDOWN,
    )


# ---------- User views ----------
async def show_task_list(q, tid):
    tasks = await db.tasks.find({"active": True}, {"_id": 0}).sort("created_at", -1).to_list(50)
    filtered = []
    for t in tasks:
        if t.get("max_slots", 0) > 0 and t.get("slots_used", 0) >= t["max_slots"]:
            continue
        existing = await db.submissions.find_one({
            "telegram_id": tid, "task_id": t["id"], "status": {"$in": ["pending", "approved"]},
        })
        if existing:
            continue
        filtered.append(t)

    if not filtered:
        text = "😔 Belum ada task tersedia.\nCek nanti ya!"
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Menu Utama", callback_data="menu:home")]])
    else:
        # Group by category
        text = f"📋 *{len(filtered)} Task Tersedia*\n\nPilih kategori atau task:"
        cats = sorted(set(t.get("category", "Other") for t in filtered))
        buttons = []
        for c in cats:
            count = sum(1 for t in filtered if t.get("category", "Other") == c)
            buttons.append([InlineKeyboardButton(f"📁 {c} ({count})", callback_data=f"cat:{c}")])
        buttons.append([InlineKeyboardButton("📄 Semua Task", callback_data="cat:__all")])
        buttons.append([InlineKeyboardButton("⬅️ Menu Utama", callback_data="menu:home")])
        kb = InlineKeyboardMarkup(buttons)

    try:
        await q.edit_message_text(text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)
    except Exception:
        await q.message.reply_text(text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)


async def show_tasks_by_category(q, tid, category):
    tasks = await db.tasks.find({"active": True}, {"_id": 0}).sort("created_at", -1).to_list(50)
    filtered = []
    for t in tasks:
        if category != "__all" and t.get("category", "Other") != category:
            continue
        if t.get("max_slots", 0) > 0 and t.get("slots_used", 0) >= t["max_slots"]:
            continue
        existing = await db.submissions.find_one({
            "telegram_id": tid, "task_id": t["id"], "status": {"$in": ["pending", "approved"]},
        })
        if existing:
            continue
        filtered.append(t)

    title = "Semua Task" if category == "__all" else category
    if not filtered:
        text = f"📁 *{title}*\n\nTidak ada task tersedia di kategori ini."
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Kategori", callback_data="menu:tasks")]])
    else:
        text = f"📁 *{title}* — {len(filtered)} task\n\nPilih task:"
        buttons = []
        for t in filtered[:25]:
            buttons.append([InlineKeyboardButton(
                f"💰 {format_idr(t['reward'])} · {t['title'][:32]}",
                callback_data=f"task:{t['id']}",
            )])
        buttons.append([InlineKeyboardButton("⬅️ Kategori", callback_data="menu:tasks")])
        kb = InlineKeyboardMarkup(buttons)

    try:
        await q.edit_message_text(text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)
    except Exception:
        pass


async def show_task_detail(q, task_id):
    task = await db.tasks.find_one({"id": task_id}, {"_id": 0})
    if not task:
        await q.edit_message_text("Task tidak ditemukan.")
        return
    text = (
        f"📌 *{task['title']}*\n"
        f"📁 Kategori: _{task.get('category', 'Other')}_\n\n"
        f"💰 Reward: *{format_idr(task['reward'])}*\n\n"
        f"📝 Deskripsi:\n{task['description']}\n\n"
    )
    if task.get("instructions"):
        text += f"📖 Instruksi:\n{task['instructions']}\n\n"
    if task.get("link"):
        text += f"🔗 Link: {task['link']}\n\n"
    if task.get("code"):
        text += f"🔑 *Kode (tap untuk salin):*\n`{task['code']}`\n\n"
    req_photo = task.get("require_photo", True)
    text += f"📸 Bukti foto: *{'WAJIB' if req_photo else 'Opsional (boleh kirim teks saja)'}*\n\n"
    text += "Klik *Kerjakan* untuk kirim bukti."

    buttons = []
    if task.get("example_image"):
        buttons.append([InlineKeyboardButton("🖼️ Lihat Contoh Bukti", callback_data=f"eximg:{task_id}")])
    buttons.append([InlineKeyboardButton("✅ Kerjakan", callback_data=f"do:{task_id}")])
    buttons.append([InlineKeyboardButton("⬅️ Kembali", callback_data="menu:tasks")])
    kb = InlineKeyboardMarkup(buttons)
    try:
        await q.edit_message_text(text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN, disable_web_page_preview=True)
    except Exception:
        await q.message.reply_text(text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)


async def send_example_image(q, task_id):
    task = await db.tasks.find_one({"id": task_id}, {"_id": 0})
    if not task or not task.get("example_image"):
        await q.answer("Contoh tidak tersedia", show_alert=True)
        return
    try:
        img_bytes = _decode_image(task["example_image"])
        await q.message.reply_photo(photo=img_bytes, caption=f"Contoh bukti untuk task: {task['title']}")
    except Exception as e:
        await q.answer(f"Gagal load contoh: {e}", show_alert=True)


async def show_profile(q, user_doc):
    bank = user_doc.get("bank")
    bank_text = "❌ Belum diatur" if not bank else f"{bank['method']} · {bank['account_number']}"
    text = (
        f"👤 *Profil Anda*\n\n"
        f"Nama: *{user_doc.get('first_name') or '-'}*\n"
        f"Username: @{user_doc.get('username') or '-'}\n"
        f"ID: `{user_doc.get('telegram_id')}`\n\n"
        f"💰 Saldo Aktif: *{format_idr(user_doc.get('balance', 0))}*\n"
        f"⏳ Saldo Pending: *{format_idr(user_doc.get('pending_balance', 0))}*\n"
        f"❌ Total Ditolak: *{format_idr(user_doc.get('rejected_total', 0))}*\n\n"
        f"💵 Total Dihasilkan: {format_idr(user_doc.get('total_earned', 0))}\n"
        f"✅ Task Selesai: {user_doc.get('tasks_completed', 0)} · ❌ Ditolak: {user_doc.get('tasks_rejected', 0)}\n"
        f"👥 Referral: {user_doc.get('referral_count', 0)}\n\n"
        f"🏦 Bank: {bank_text}"
    )
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Menu Utama", callback_data="menu:home")]])
    await q.edit_message_text(text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)


async def show_task_history(q, tid):
    subs = await db.submissions.find({"telegram_id": tid}, {"_id": 0}).sort("created_at", -1).to_list(20)
    if not subs:
        text = "📜 *Riwayat Task*\n\nBelum ada."
    else:
        text = "📜 *Riwayat Task (20 terakhir)*\n\n"
        for s in subs:
            t = await db.tasks.find_one({"id": s["task_id"]}, {"_id": 0})
            title = (t["title"] if t else "Task")[:30]
            emoji = {"pending": "⏳", "approved": "✅", "rejected": "❌"}.get(s["status"], "•")
            text += f"{emoji} {title} - {s['status']}\n"
            if s["status"] == "rejected" and s.get("reject_reason"):
                text += f"   ↳ {s['reject_reason'][:60]}\n"
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Menu Utama", callback_data="menu:home")]])
    await q.edit_message_text(text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)


async def show_balance_history(q, tid):
    hist = await db.balance_history.find({"telegram_id": tid}, {"_id": 0}).sort("created_at", -1).to_list(20)
    if not hist:
        text = "💸 *Riwayat Saldo*\n\nBelum ada."
    else:
        text = "💸 *Riwayat Saldo (20 terakhir)*\n\n"
        for h in hist:
            emoji = {"credit": "🟢+", "debit": "🔴-", "withdraw": "💸-", "refund": "↩️+"}.get(h["type"], "•")
            text += f"{emoji} {format_idr(h['amount'])}\n"
            text += f"   _{(h.get('note', ''))[:50]}_\n"
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Menu Utama", callback_data="menu:home")]])
    await q.edit_message_text(text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)


async def show_bank(q, user_doc):
    bank = user_doc.get("bank")
    if bank:
        text = (
            f"🏦 *Info Pembayaran*\n\n"
            f"Metode: *{bank['method']}*\n"
            f"Nomor: `{bank['account_number']}`\n"
            f"Atas Nama: *{bank['account_name']}*"
        )
    else:
        text = "🏦 *Info Pembayaran*\n\nBelum diatur."
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✏️ Atur / Ubah", callback_data="bank:set")],
        [InlineKeyboardButton("⬅️ Menu Utama", callback_data="menu:home")],
    ])
    await q.edit_message_text(text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)


async def show_referral(q, user_doc, bot_username):
    tid = user_doc["telegram_id"]
    link = f"https://t.me/{bot_username}?start=ref{tid}"
    text = (
        f"👥 *Ajak Teman & Dapat Bonus*\n\n"
        f"Ajak teman join BigoCuan dan dapatkan *{format_idr(REFERRAL_BONUS)}* untuk setiap teman yang berhasil daftar!\n\n"
        f"🔗 Link Referral Anda:\n`{link}`\n\n"
        f"👥 Referral Anda: *{user_doc.get('referral_count', 0)}*\n"
        f"💰 Total Bonus: *{format_idr(user_doc.get('referral_count', 0) * REFERRAL_BONUS)}*"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📤 Bagikan Link", switch_inline_query=f"Yuk join BigoCuan dan dapatkan cuan dari task harian!\n\n{link}")],
        [InlineKeyboardButton("⬅️ Menu Utama", callback_data="menu:home")],
    ])
    await q.edit_message_text(text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)


async def show_help_menu(q):
    faqs = await db.faqs.find({}, {"_id": 0}).sort("order", 1).to_list(50)
    support = await db.support.find_one({"id": "default"}, {"_id": 0}) or {}
    text = "❓ *Bantuan & FAQ*\n\nPilih pertanyaan di bawah, atau hubungi admin:"
    buttons = []
    for f in faqs[:15]:
        buttons.append([InlineKeyboardButton(f["question"][:60], callback_data=f"faq:{f['id']}")])
    if support.get("whatsapp"):
        wa = support["whatsapp"].replace("+", "").replace(" ", "")
        buttons.append([InlineKeyboardButton("📱 Hubungi WhatsApp", url=f"https://wa.me/{wa}")])
    if support.get("telegram_username"):
        tg = support["telegram_username"].lstrip("@")
        buttons.append([InlineKeyboardButton("💬 Chat Admin Telegram", url=f"https://t.me/{tg}")])
    buttons.append([InlineKeyboardButton("⬅️ Menu Utama", callback_data="menu:home")])
    kb = InlineKeyboardMarkup(buttons)
    try:
        await q.edit_message_text(text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)
    except Exception:
        await q.message.reply_text(text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)


async def show_faq_answer(q, fid):
    f = await db.faqs.find_one({"id": fid}, {"_id": 0})
    if not f:
        return
    text = f"❓ *{f['question']}*\n\n{f['answer']}"
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Kembali ke Bantuan", callback_data="menu:help")]])
    await q.edit_message_text(text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)


# ---------- Callback handler ----------
async def on_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data
    user = update.effective_user
    user_doc = await get_or_create_user(user)

    # verify:check works regardless of state
    if data == "verify:check":
        ok, missing = await check_mandatory_channels(ctx.bot, user.id)
        if ok:
            await db.users.update_one({"telegram_id": user.id}, {"$set": {"verified_channels": True}})
            await show_main_menu(q, user_doc, edit=True)
        else:
            await send_verify_prompt(q, missing, ctx)
        return

    # Gate for non-admins - require verification
    if not is_admin_user(user):
        ok, missing = await check_mandatory_channels(ctx.bot, user.id)
        if not ok and missing:
            await send_verify_prompt(q, missing, ctx)
            return

    # Admin callbacks
    if data.startswith("adm:") and is_admin_user(user):
        await handle_admin_callback(q, ctx, data)
        return

    if data == "menu:home":
        await show_main_menu(q, user_doc, edit=True)
    elif data == "menu:tasks":
        await show_task_list(q, user.id)
    elif data.startswith("cat:"):
        await show_tasks_by_category(q, user.id, data.split(":", 1)[1])
    elif data == "menu:profile":
        await show_profile(q, user_doc)
    elif data == "menu:balance":
        text = (
            f"💰 *Saldo*\n\n"
            f"Saldo Aktif: *{format_idr(user_doc.get('balance', 0))}* (siap withdraw)\n"
            f"Saldo Pending: *{format_idr(user_doc.get('pending_balance', 0))}* (menunggu review)\n"
            f"Total Ditolak: *{format_idr(user_doc.get('rejected_total', 0))}*\n\n"
            f"Total Dihasilkan: {format_idr(user_doc.get('total_earned', 0))}"
        )
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("💵 Withdraw", callback_data="menu:withdraw")],
            [InlineKeyboardButton("⬅️ Menu Utama", callback_data="menu:home")],
        ])
        await q.edit_message_text(text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)
    elif data == "menu:history":
        await show_task_history(q, user.id)
    elif data == "menu:balhist":
        await show_balance_history(q, user.id)
    elif data == "menu:bank":
        await show_bank(q, user_doc)
    elif data == "menu:referral":
        me = await ctx.bot.get_me()
        await show_referral(q, user_doc, me.username)
    elif data == "menu:help":
        await show_help_menu(q)
    elif data.startswith("faq:"):
        await show_faq_answer(q, data.split(":", 1)[1])
    elif data == "menu:withdraw":
        await start_withdraw(update, ctx)
    elif data.startswith("task:"):
        await show_task_detail(q, data.split(":", 1)[1])
    elif data.startswith("eximg:"):
        await send_example_image(q, data.split(":", 1)[1])
    elif data.startswith("do:"):
        await start_do_task(update, ctx, data.split(":", 1)[1])
    elif data == "bank:set":
        await start_set_bank(update, ctx)
    elif data.startswith("bank_method:"):
        method = data.split(":", 1)[1]
        ctx.user_data["bank_method"] = method
        await q.edit_message_text(
            f"Metode: *{method}*\n\nKirim *nomor {method}* Anda (angka saja):",
            parse_mode=ParseMode.MARKDOWN,
        )
        ctx.user_data["state"] = "await_bank_number"


# ---------- Admin bot handlers ----------
async def handle_admin_callback(q, ctx, data):
    if data == "adm:tasks":
        tasks = await db.tasks.find({}, {"_id": 0}).sort("created_at", -1).to_list(50)
        if not tasks:
            text = "📋 *Kelola Tasks*\n\nBelum ada task."
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("➕ Buat Task Baru", callback_data="adm:new_task")],
                [InlineKeyboardButton("⬅️ Kembali", callback_data="adm:home")],
            ])
        else:
            text = f"📋 *Kelola Tasks* ({len(tasks)})\n\nPilih task:"
            buttons = []
            for t in tasks[:20]:
                status = "🟢" if t.get("active") else "⏸️"
                buttons.append([InlineKeyboardButton(
                    f"{status} {format_idr(t['reward'])} · {t['title'][:30]}",
                    callback_data=f"adm:task:{t['id']}",
                )])
            buttons.append([InlineKeyboardButton("➕ Buat Task Baru", callback_data="adm:new_task")])
            buttons.append([InlineKeyboardButton("⬅️ Kembali", callback_data="adm:home")])
            kb = InlineKeyboardMarkup(buttons)
        await q.edit_message_text(text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)

    elif data.startswith("adm:task:"):
        tid = data.split(":", 2)[2]
        t = await db.tasks.find_one({"id": tid}, {"_id": 0})
        if not t:
            await q.edit_message_text("Task tidak ada.")
            return
        text = (
            f"📌 *{t['title']}*\n\n"
            f"📁 Kategori: {t.get('category', 'Other')}\n"
            f"💰 Reward: *{format_idr(t['reward'])}*\n"
            f"Status: {'🟢 AKTIF' if t.get('active') else '⏸️ PAUSE'}\n"
            f"Slot: {t.get('slots_used', 0)}/{t.get('max_slots', 0) or '∞'}\n\n"
            f"📝 {t['description']}"
        )
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(
                "⏸️ Pause" if t.get("active") else "▶️ Aktifkan",
                callback_data=f"adm:toggle:{tid}",
            )],
            [InlineKeyboardButton("🗑️ Hapus", callback_data=f"adm:del:{tid}")],
            [InlineKeyboardButton("⬅️ Daftar Tasks", callback_data="adm:tasks")],
        ])
        await q.edit_message_text(text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)

    elif data.startswith("adm:toggle:"):
        tid = data.split(":", 2)[2]
        t = await db.tasks.find_one({"id": tid})
        if t:
            await db.tasks.update_one({"id": tid}, {"$set": {"active": not t.get("active", True)}})
            await q.answer("Status task diubah!")
            # Re-show
            await handle_admin_callback(q, ctx, f"adm:task:{tid}")

    elif data.startswith("adm:del:"):
        tid = data.split(":", 2)[2]
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("⚠️ Ya, Hapus", callback_data=f"adm:delc:{tid}")],
            [InlineKeyboardButton("❌ Batal", callback_data=f"adm:task:{tid}")],
        ])
        await q.edit_message_text("⚠️ Yakin hapus task ini?", reply_markup=kb)

    elif data.startswith("adm:delc:"):
        tid = data.split(":", 2)[2]
        await db.tasks.delete_one({"id": tid})
        await q.answer("Task dihapus!", show_alert=True)
        await handle_admin_callback(q, ctx, "adm:tasks")

    elif data == "adm:new_task":
        ctx.user_data["adm_state"] = "await_task_title"
        ctx.user_data["adm_task"] = {}
        await q.edit_message_text(
            "➕ *Buat Task Baru (1/4)*\n\nKirim *judul task*:\n(/cancel untuk batal)",
            parse_mode=ParseMode.MARKDOWN,
        )

    elif data == "adm:broadcast":
        ctx.user_data["adm_state"] = "await_broadcast_text"
        await q.edit_message_text(
            "📢 *Kirim Broadcast*\n\nKirim *teks pesan* yang mau di-broadcast:\n(/cancel untuk batal)",
            parse_mode=ParseMode.MARKDOWN,
        )

    elif data == "adm:stats":
        total = await db.users.count_documents({})
        pend_s = await db.submissions.count_documents({"status": "pending"})
        pend_w = await db.withdrawals.count_documents({"status": "pending"})
        approved_w = await db.withdrawals.aggregate([
            {"$match": {"status": "approved"}},
            {"$group": {"_id": None, "total": {"$sum": "$amount"}}},
        ]).to_list(1)
        payout = approved_w[0]["total"] if approved_w else 0
        text = (
            f"📊 *Statistik BigoCuan*\n\n"
            f"👥 Total User: *{total}*\n"
            f"⏳ Task Pending: *{pend_s}*\n"
            f"⏳ Withdraw Pending: *{pend_w}*\n"
            f"💸 Total Payout: *{format_idr(payout)}*"
        )
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Kembali", callback_data="adm:home")]])
        await q.edit_message_text(text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)

    elif data == "adm:home":
        await q.edit_message_text(
            "🛠️ *Panel Admin BigoCuan*\n\nPilih aksi:",
            reply_markup=admin_menu_keyboard(),
            parse_mode=ParseMode.MARKDOWN,
        )


# ---------- Task/Withdraw/Bank flows ----------
async def start_do_task(update: Update, ctx: ContextTypes.DEFAULT_TYPE, task_id: str):
    task = await db.tasks.find_one({"id": task_id})
    if not task:
        await update.callback_query.edit_message_text("Task tidak ditemukan.")
        return
    ctx.user_data["submitting_task_id"] = task_id
    require_photo = task.get("require_photo", True)
    if require_photo:
        ctx.user_data["state"] = "await_proof_photo"
        await update.callback_query.edit_message_text(
            f"📸 *Kirim Bukti*\n\nTask: *{task['title']}*\n\n"
            f"Kirim *foto bukti* Anda mengerjakan task.\n"
            f"/cancel untuk batal.",
            parse_mode=ParseMode.MARKDOWN,
        )
    else:
        # No photo required, jump straight to text
        ctx.user_data["state"] = "await_proof_text"
        ctx.user_data["proof_image"] = None
        await update.callback_query.edit_message_text(
            f"✍️ *Kirim Bukti*\n\nTask: *{task['title']}*\n\n"
            f"Task ini tidak wajib foto. Kirim *keterangan/bukti teks* Anda.\n"
            f"Bisa juga kirim foto (opsional).\n"
            f"/cancel untuk batal.",
            parse_mode=ParseMode.MARKDOWN,
        )


async def start_withdraw(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_doc = await get_or_create_user(update.effective_user)
    q = update.callback_query
    if not user_doc.get("bank"):
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🏦 Atur Info", callback_data="bank:set")],
            [InlineKeyboardButton("⬅️ Menu Utama", callback_data="menu:home")],
        ])
        await q.edit_message_text("⚠️ Info pembayaran belum diatur.", reply_markup=kb)
        return
    if user_doc.get("balance", 0) <= 0:
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Menu Utama", callback_data="menu:home")]])
        await q.edit_message_text("💰 Saldo aktif 0. Selesaikan task dulu!", reply_markup=kb)
        return

    bank = user_doc["bank"]
    ctx.user_data["state"] = "await_wd_amount"
    await q.edit_message_text(
        f"💵 *Ajukan Withdraw*\n\n"
        f"Saldo Aktif: *{format_idr(user_doc['balance'])}*\n"
        f"Ke: *{bank['method']}* `{bank['account_number']}`\n\n"
        f"Kirim *nominal* (angka saja):\n/cancel untuk batal.",
        parse_mode=ParseMode.MARKDOWN,
    )


async def start_set_bank(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("DANA", callback_data="bank_method:DANA")],
        [InlineKeyboardButton("GoPay", callback_data="bank_method:GoPay")],
        [InlineKeyboardButton("ShopeePay", callback_data="bank_method:ShopeePay")],
        [InlineKeyboardButton("⬅️ Batal", callback_data="menu:home")],
    ])
    await update.callback_query.edit_message_text(
        "🏦 *Pilih Metode Pembayaran*", reply_markup=kb, parse_mode=ParseMode.MARKDOWN,
    )


# ---------- Photo / Text state router ----------
async def on_photo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    state = ctx.user_data.get("state")
    adm_state = ctx.user_data.get("adm_state")

    if state not in ("await_proof_photo", "await_proof_text") and adm_state not in ("await_broadcast_image",):
        return

    photo = update.message.photo[-1]
    file = await ctx.bot.get_file(photo.file_id)
    buf = BytesIO()
    await file.download_to_memory(buf)
    b64 = base64.b64encode(buf.getvalue()).decode()
    img = f"data:image/jpeg;base64,{b64}"

    if state == "await_proof_photo":
        ctx.user_data["proof_image"] = img
        ctx.user_data["state"] = "await_proof_text"
        await update.message.reply_text(
            "✅ Foto diterima!\n\nKirim *keterangan* singkat atau /skip.",
            parse_mode=ParseMode.MARKDOWN,
        )
    elif state == "await_proof_text":
        # Optional photo, user sent one
        ctx.user_data["proof_image"] = img
        await update.message.reply_text(
            "📸 Foto tambahan diterima. Sekarang kirim *keterangan* atau /skip.",
            parse_mode=ParseMode.MARKDOWN,
        )
    elif adm_state == "await_broadcast_image":
        ctx.user_data["broadcast_image"] = img
        await do_broadcast(update, ctx)


async def on_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    state = ctx.user_data.get("state")
    adm_state = ctx.user_data.get("adm_state")
    text = update.message.text.strip()

    # Admin state machine
    if adm_state and is_admin_user(update.effective_user):
        await handle_admin_state(update, ctx, text)
        return

    if state == "await_proof_photo":
        await update.message.reply_text("Kirim *foto* dulu, atau /cancel.", parse_mode=ParseMode.MARKDOWN)
        return

    if state == "await_proof_text":
        note = text if text != "/skip" else ""
        task_id = ctx.user_data.get("submitting_task_id")
        image = ctx.user_data.get("proof_image")
        task = await db.tasks.find_one({"id": task_id})
        if not task:
            ctx.user_data.clear()
            await update.message.reply_text("Task tidak ditemukan.")
            return
        sub = {
            "id": new_id(),
            "telegram_id": update.effective_user.id,
            "task_id": task_id,
            "proof_image": image,
            "proof_text": note,
            "status": "pending",
            "created_at": now_iso(),
        }
        await db.submissions.insert_one(sub)
        # Move reward to pending_balance
        await db.users.update_one(
            {"telegram_id": update.effective_user.id},
            {"$inc": {"pending_balance": task["reward"]}},
        )
        ctx.user_data.clear()
        await update.message.reply_text(
            f"✅ *Bukti Terkirim!*\n\n"
            f"Task: *{task['title']}*\n"
            f"Reward: *{format_idr(task['reward'])}* (menunggu review)\n\n"
            f"Status: *pending* — akan diverifikasi admin.\n/start untuk menu.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    if state == "await_wd_amount":
        try:
            amount = int(text.replace(".", "").replace(",", "").replace("Rp", "").strip())
        except ValueError:
            await update.message.reply_text("Nominal tidak valid. Kirim angka saja.")
            return
        user = await db.users.find_one({"telegram_id": update.effective_user.id})
        if amount <= 0:
            await update.message.reply_text("Nominal harus > 0.")
            return
        if amount > user.get("balance", 0):
            await update.message.reply_text(f"Saldo aktif tidak cukup. Saldo: {format_idr(user['balance'])}")
            return
        bank = user["bank"]
        wd = {
            "id": new_id(),
            "telegram_id": update.effective_user.id,
            "amount": amount,
            "method": bank["method"],
            "account_number": bank["account_number"],
            "account_name": bank["account_name"],
            "status": "pending",
            "created_at": now_iso(),
        }
        await db.withdrawals.insert_one(wd)
        await db.users.update_one({"telegram_id": update.effective_user.id}, {"$inc": {"balance": -amount}})
        ctx.user_data.clear()
        await update.message.reply_text(
            f"✅ *Withdraw Diajukan!*\n\nNominal: *{format_idr(amount)}*\nStatus: pending",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    if state == "await_bank_number":
        if not text.replace(" ", "").isdigit():
            await update.message.reply_text("Nomor harus angka.")
            return
        ctx.user_data["bank_number"] = text.replace(" ", "")
        ctx.user_data["state"] = "await_bank_name"
        await update.message.reply_text("Kirim *nama pemilik*:", parse_mode=ParseMode.MARKDOWN)
        return

    if state == "await_bank_name":
        bank = {
            "method": ctx.user_data["bank_method"],
            "account_number": ctx.user_data["bank_number"],
            "account_name": text,
        }
        await db.users.update_one({"telegram_id": update.effective_user.id}, {"$set": {"bank": bank}})
        ctx.user_data.clear()
        await update.message.reply_text(
            f"✅ Info pembayaran tersimpan!\n\n{bank['method']} · {bank['account_number']} · {bank['account_name']}\n/start untuk menu.",
        )
        return

    # Default
    user_doc = await get_or_create_user(update.effective_user)
    await show_main_menu(update, user_doc)


# ---------- Admin state machine (bot) ----------
async def handle_admin_state(update: Update, ctx, text):
    state = ctx.user_data.get("adm_state")
    t = ctx.user_data.get("adm_task", {})

    if state == "await_task_title":
        t["title"] = text
        ctx.user_data["adm_state"] = "await_task_desc"
        await update.message.reply_text("*(2/4)* Kirim *deskripsi task*:", parse_mode=ParseMode.MARKDOWN)
    elif state == "await_task_desc":
        t["description"] = text
        ctx.user_data["adm_state"] = "await_task_reward"
        await update.message.reply_text("*(3/4)* Kirim *reward (Rp)* dalam angka:", parse_mode=ParseMode.MARKDOWN)
    elif state == "await_task_reward":
        try:
            t["reward"] = int(text.replace(".", "").replace(",", "").strip())
        except ValueError:
            await update.message.reply_text("Reward harus angka. Coba lagi:")
            return
        ctx.user_data["adm_state"] = "await_task_category"
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("Social Media", callback_data="adm:cat:Social Media")],
            [InlineKeyboardButton("App Install", callback_data="adm:cat:App Install")],
            [InlineKeyboardButton("Survey", callback_data="adm:cat:Survey")],
            [InlineKeyboardButton("Other", callback_data="adm:cat:Other")],
        ])
        # Store t
        ctx.user_data["adm_task"] = t
        await update.message.reply_text("*(4/4)* Pilih kategori:", reply_markup=kb, parse_mode=ParseMode.MARKDOWN)
    elif state == "await_broadcast_text":
        ctx.user_data["broadcast_text"] = text
        ctx.user_data["adm_state"] = "await_broadcast_image"
        await update.message.reply_text("Kirim *foto* untuk broadcast, atau ketik /skip untuk broadcast text-only.", parse_mode=ParseMode.MARKDOWN)
    elif state == "await_broadcast_image" and text == "/skip":
        await do_broadcast(update, ctx)


async def do_broadcast(update: Update, ctx):
    text = ctx.user_data.get("broadcast_text", "")
    image = ctx.user_data.get("broadcast_image")
    settings = await db.broadcast_settings.find_one({"id": "default"}) or {"enabled": True}
    if not settings.get("enabled", True):
        await update.message.reply_text("❌ Broadcast dinonaktifkan (master toggle OFF).")
        ctx.user_data.clear()
        return
    channels = await db.channels.find({"kind": "broadcast", "active": True}, {"_id": 0}).to_list(50)
    if not channels:
        channels = [{"username": DEFAULT_CHANNEL, "title": "Default"}]
    results = []
    for ch in channels:
        try:
            msg_id = await send_channel_broadcast(text, image_base64=image, channel=ch["username"])
            results.append(f"✅ {ch['username']}")
        except Exception as e:
            results.append(f"❌ {ch['username']}: {e}")
    await db.broadcast_logs.insert_one({
        "id": new_id(),
        "type": "bot_admin",
        "text": text,
        "image_base64": image,
        "results": [{"channel": ch["username"], "ok": True} for ch in channels],
        "status": "sent",
        "created_at": now_iso(),
    })
    ctx.user_data.clear()
    await update.message.reply_text("📢 Hasil broadcast:\n" + "\n".join(results))


# ---------- Admin category selection callback ----------
async def on_admin_cat_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not is_admin_user(update.effective_user):
        await q.answer("Akses ditolak", show_alert=True)
        return
    await q.answer()
    if not q.data.startswith("adm:cat:"):
        return
    category = q.data.split(":", 2)[2]
    t = ctx.user_data.get("adm_task", {})
    t["category"] = category
    doc = {
        "id": new_id(),
        "title": t["title"],
        "description": t["description"],
        "reward": t["reward"],
        "category": category,
        "instructions": "",
        "link": None,
        "max_slots": 0,
        "slots_used": 0,
        "active": True,
        "created_at": now_iso(),
    }
    await db.tasks.insert_one(doc)
    ctx.user_data.clear()
    await q.edit_message_text(
        f"✅ Task berhasil dibuat!\n\n"
        f"*{doc['title']}*\n"
        f"Kategori: {category}\n"
        f"Reward: {format_idr(doc['reward'])}",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Panel Admin", callback_data="adm:home")]]),
    )


# ---------- Send helpers ----------
async def _safe_send_message(bot, chat_id, text: str):
    try:
        return await bot.send_message(chat_id=chat_id, text=text, parse_mode=ParseMode.MARKDOWN)
    except BadRequest as e:
        if "parse" in str(e).lower() or "entit" in str(e).lower():
            return await bot.send_message(chat_id=chat_id, text=text, parse_mode=None)
        raise


async def _safe_send_photo(bot, chat_id, photo_bytes, caption: str):
    try:
        return await bot.send_photo(chat_id=chat_id, photo=photo_bytes, caption=caption[:1024], parse_mode=ParseMode.MARKDOWN)
    except BadRequest as e:
        if "parse" in str(e).lower() or "entit" in str(e).lower():
            return await bot.send_photo(chat_id=chat_id, photo=photo_bytes, caption=caption[:1024], parse_mode=None)
        raise


async def send_dm(telegram_id: int, text: str, image_base64: Optional[str] = None):
    app = bot_state.get("app")
    if not app:
        raise RuntimeError("Bot not running")
    bot = app.bot
    if image_base64:
        img_bytes = _decode_image(image_base64)
        await _safe_send_photo(bot, telegram_id, img_bytes, text)
    else:
        await _safe_send_message(bot, telegram_id, text)


async def send_channel_broadcast(text: str, image_base64: Optional[str] = None, channel: Optional[str] = None) -> Optional[int]:
    app = bot_state.get("app")
    if not app:
        raise RuntimeError("Bot not running")
    bot = app.bot
    target = channel or DEFAULT_CHANNEL
    if image_base64:
        img_bytes = _decode_image(image_base64)
        msg = await _safe_send_photo(bot, target, img_bytes, text)
    else:
        msg = await _safe_send_message(bot, target, text)
    return msg.message_id


def _decode_image(b64: str) -> bytes:
    if b64.startswith("data:"):
        b64 = b64.split(",", 1)[1]
    return base64.b64decode(b64)


# ---------- Startup / shutdown ----------
async def start_bot():
    if bot_state.get("running"):
        return
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("admin", cmd_admin))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("cancel", cmd_cancel))
    # Admin category select (specific pattern first)
    app.add_handler(CallbackQueryHandler(on_admin_cat_callback, pattern=r"^adm:cat:"))
    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(MessageHandler(filters.PHOTO, on_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

    bot_state["app"] = app
    try:
        await app.initialize()
        await app.start()
        await app.updater.start_polling(drop_pending_updates=True)
        bot_state["running"] = True
        logger.info("Telegram bot started (polling)")
    except Exception as e:
        logger.error(f"Failed to start bot: {e}")
        bot_state["running"] = False


async def stop_bot():
    app = bot_state.get("app")
    if app:
        try:
            if app.updater and app.updater.running:
                await app.updater.stop()
            await app.stop()
            await app.shutdown()
        except Exception as e:
            logger.error(f"Error stopping bot: {e}")
    bot_state["running"] = False
