"""Telegram bot logic for BigoCuan. Uses python-telegram-bot v21."""
import os
import logging
import base64
import uuid
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
    ConversationHandler,
)

logger = logging.getLogger("bigocuan.bot")

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHANNEL = os.environ["TELEGRAM_CHANNEL"]

# db is injected from server.py
db = None
bot_state = {"running": False, "app": None}

# Conversation states
AWAIT_PROOF_PHOTO, AWAIT_PROOF_TEXT = range(2)
AWAIT_WD_AMOUNT = 10
AWAIT_BANK_METHOD, AWAIT_BANK_NUMBER, AWAIT_BANK_NAME = 20, 21, 22


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def new_id():
    return str(uuid.uuid4())


def format_idr(amount: int) -> str:
    return f"Rp {amount:,}".replace(",", ".")


def escape_md(text: str) -> str:
    """Basic escape for legacy Markdown parse_mode."""
    return text.replace("_", "\\_").replace("*", "\\*").replace("`", "\\`").replace("[", "\\[")


# ---------- Helpers ----------
async def get_or_create_user(user) -> dict:
    doc = await db.users.find_one({"telegram_id": user.id})
    if doc:
        # Update username if changed
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
        "total_earned": 0,
        "tasks_completed": 0,
        "bank": None,  # {method, account_number, account_name}
        "created_at": now_iso(),
    }
    await db.users.insert_one(new_user)
    new_user.pop("_id", None)
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
            InlineKeyboardButton("🏦 Info Bank/E-Wallet", callback_data="menu:bank"),
            InlineKeyboardButton("💵 Withdraw", callback_data="menu:withdraw"),
        ],
        [InlineKeyboardButton("ℹ️ Bantuan", callback_data="menu:help")],
    ])


async def show_main_menu(update_or_query, user_doc, edit=False):
    text = (
        f"🎉 *Selamat datang di BigoCuan!*\n\n"
        f"Halo *{user_doc.get('first_name') or 'User'}*!\n"
        f"Saldo Anda: *{format_idr(user_doc.get('balance', 0))}*\n\n"
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


# ---------- Handlers ----------
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_doc = await get_or_create_user(update.effective_user)
    await show_main_menu(update, user_doc)


async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "*BigoCuan Bot*\n\n"
        "/start - Menu utama\n"
        "/tasks - Lihat task tersedia\n"
        "/profile - Profil Anda\n"
        "/balance - Saldo Anda\n"
        "/withdraw - Ajukan withdraw\n"
        "/bank - Set/ubah info bank\n"
        "/cancel - Batalkan aksi\n",
        parse_mode=ParseMode.MARKDOWN,
    )


async def cmd_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data.clear()
    await update.message.reply_text("Dibatalkan. Ketik /start untuk kembali ke menu.")
    return ConversationHandler.END


async def send_task_list(update: Update, ctx: ContextTypes.DEFAULT_TYPE, edit=False):
    tasks = await db.tasks.find({"active": True}, {"_id": 0}).sort("created_at", -1).to_list(50)
    tid = update.effective_user.id
    # Filter out tasks user already submitted pending/approved
    filtered = []
    for t in tasks:
        # Check slots
        if t.get("max_slots", 0) > 0 and t.get("slots_used", 0) >= t["max_slots"]:
            continue
        existing = await db.submissions.find_one({
            "telegram_id": tid,
            "task_id": t["id"],
            "status": {"$in": ["pending", "approved"]},
        })
        if existing:
            continue
        filtered.append(t)

    if not filtered:
        text = "😔 Belum ada task tersedia saat ini.\nCek kembali nanti ya!"
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Menu Utama", callback_data="menu:home")]])
    else:
        text = f"📋 *{len(filtered)} Task Tersedia*\n\nPilih task untuk mengerjakan:"
        buttons = []
        for t in filtered[:20]:
            buttons.append([InlineKeyboardButton(
                f"💰 {format_idr(t['reward'])} - {t['title'][:35]}",
                callback_data=f"task:{t['id']}",
            )])
        buttons.append([InlineKeyboardButton("⬅️ Menu Utama", callback_data="menu:home")])
        kb = InlineKeyboardMarkup(buttons)

    q = update.callback_query
    target = q if edit else update
    if edit and q:
        try:
            await q.edit_message_text(text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)
        except Exception:
            await q.message.reply_text(text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)
    else:
        await update.message.reply_text(text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)


async def show_task_detail(query, task_id):
    task = await db.tasks.find_one({"id": task_id}, {"_id": 0})
    if not task:
        await query.edit_message_text("Task tidak ditemukan.")
        return
    text = (
        f"📌 *{task['title']}*\n\n"
        f"💰 Reward: *{format_idr(task['reward'])}*\n\n"
        f"📝 Deskripsi:\n{task['description']}\n\n"
    )
    if task.get("instructions"):
        text += f"📖 Instruksi:\n{task['instructions']}\n\n"
    if task.get("link"):
        text += f"🔗 Link: {task['link']}\n\n"
    text += "Klik *Kerjakan* untuk mengumpulkan bukti."

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Kerjakan", callback_data=f"do:{task_id}")],
        [InlineKeyboardButton("⬅️ Kembali", callback_data="menu:tasks")],
    ])
    try:
        await query.edit_message_text(text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN, disable_web_page_preview=True)
    except Exception:
        await query.message.reply_text(text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)


async def show_profile(query, user_doc):
    bank = user_doc.get("bank")
    bank_text = "❌ Belum diatur" if not bank else f"{bank['method']} - {bank['account_number']} ({bank['account_name']})"
    text = (
        f"👤 *Profil Anda*\n\n"
        f"Nama: *{user_doc.get('first_name') or '-'}*\n"
        f"Username: @{user_doc.get('username') or '-'}\n"
        f"ID: `{user_doc.get('telegram_id')}`\n\n"
        f"💰 Saldo: *{format_idr(user_doc.get('balance', 0))}*\n"
        f"💵 Total Dihasilkan: *{format_idr(user_doc.get('total_earned', 0))}*\n"
        f"✅ Task Selesai: *{user_doc.get('tasks_completed', 0)}*\n\n"
        f"🏦 Info Pembayaran:\n{bank_text}"
    )
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Menu Utama", callback_data="menu:home")]])
    await query.edit_message_text(text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)


async def show_task_history(query, tid):
    subs = await db.submissions.find({"telegram_id": tid}, {"_id": 0}).sort("created_at", -1).to_list(20)
    if not subs:
        text = "📜 *Riwayat Task*\n\nBelum ada riwayat."
    else:
        text = "📜 *Riwayat Task (20 terakhir)*\n\n"
        for s in subs:
            t = await db.tasks.find_one({"id": s["task_id"]}, {"_id": 0})
            title = t["title"] if t else "Task"
            emoji = {"pending": "⏳", "approved": "✅", "rejected": "❌"}.get(s["status"], "•")
            text += f"{emoji} {escape_md(title[:30])} - _{s['status']}_\n"
            if s["status"] == "rejected" and s.get("reject_reason"):
                text += f"   ↳ {escape_md(s['reject_reason'][:60])}\n"
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Menu Utama", callback_data="menu:home")]])
    await query.edit_message_text(text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)


async def show_balance_history(query, tid):
    hist = await db.balance_history.find({"telegram_id": tid}, {"_id": 0}).sort("created_at", -1).to_list(20)
    if not hist:
        text = "💸 *Riwayat Saldo*\n\nBelum ada riwayat."
    else:
        text = "💸 *Riwayat Saldo (20 terakhir)*\n\n"
        for h in hist:
            emoji = {"credit": "🟢+", "debit": "🔴-", "withdraw": "💸-", "refund": "↩️+"}.get(h["type"], "•")
            text += f"{emoji} {format_idr(h['amount'])}\n"
            text += f"   _{escape_md(h.get('note', ''))[:50]}_\n"
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Menu Utama", callback_data="menu:home")]])
    await query.edit_message_text(text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)


async def show_bank(query, user_doc):
    bank = user_doc.get("bank")
    if bank:
        text = (
            f"🏦 *Info Pembayaran*\n\n"
            f"Metode: *{bank['method']}*\n"
            f"Nomor: `{bank['account_number']}`\n"
            f"Atas Nama: *{bank['account_name']}*\n\n"
            f"Klik *Ubah* untuk mengganti info."
        )
    else:
        text = "🏦 *Info Pembayaran*\n\nBelum diatur. Klik *Atur* untuk mengisi."

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✏️ Atur / Ubah", callback_data="bank:set")],
        [InlineKeyboardButton("⬅️ Menu Utama", callback_data="menu:home")],
    ])
    await query.edit_message_text(text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)


# ---------- Callback query handler ----------
async def on_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data
    user_doc = await get_or_create_user(update.effective_user)

    if data == "menu:home":
        await show_main_menu(q, user_doc, edit=True)
    elif data == "menu:tasks":
        await send_task_list(update, ctx, edit=True)
    elif data == "menu:profile":
        await show_profile(q, user_doc)
    elif data == "menu:balance":
        text = (
            f"💰 *Saldo Anda*\n\n"
            f"*{format_idr(user_doc.get('balance', 0))}*\n\n"
            f"Total dihasilkan: {format_idr(user_doc.get('total_earned', 0))}\n"
            f"Task selesai: {user_doc.get('tasks_completed', 0)}"
        )
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("💵 Withdraw", callback_data="menu:withdraw")],
            [InlineKeyboardButton("⬅️ Menu Utama", callback_data="menu:home")],
        ])
        await q.edit_message_text(text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)
    elif data == "menu:history":
        await show_task_history(q, update.effective_user.id)
    elif data == "menu:balhist":
        await show_balance_history(q, update.effective_user.id)
    elif data == "menu:bank":
        await show_bank(q, user_doc)
    elif data == "menu:help":
        text = (
            "*Bantuan BigoCuan*\n\n"
            "1️⃣ Pilih task yang tersedia\n"
            "2️⃣ Kerjakan sesuai instruksi\n"
            "3️⃣ Upload bukti (foto + keterangan)\n"
            "4️⃣ Tunggu verifikasi admin\n"
            "5️⃣ Setelah disetujui, saldo bertambah\n"
            "6️⃣ Withdraw kapan saja via DANA/GoPay/ShopeePay\n\n"
            f"📢 Channel: {CHANNEL}"
        )
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Menu Utama", callback_data="menu:home")]])
        await q.edit_message_text(text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)
    elif data == "menu:withdraw":
        await start_withdraw(update, ctx)
    elif data.startswith("task:"):
        await show_task_detail(q, data.split(":", 1)[1])
    elif data.startswith("do:"):
        await start_do_task(update, ctx, data.split(":", 1)[1])
    elif data == "bank:set":
        await start_set_bank(update, ctx)
    elif data.startswith("bank_method:"):
        method = data.split(":", 1)[1]
        ctx.user_data["bank_method"] = method
        await q.edit_message_text(
            f"Metode: *{method}*\n\nSekarang kirimkan *nomor {method}* Anda (angka saja):",
            parse_mode=ParseMode.MARKDOWN,
        )
        ctx.user_data["state"] = "await_bank_number"


# ---------- Task submission flow ----------
async def start_do_task(update: Update, ctx: ContextTypes.DEFAULT_TYPE, task_id: str):
    task = await db.tasks.find_one({"id": task_id})
    if not task:
        await update.callback_query.edit_message_text("Task tidak ditemukan.")
        return
    ctx.user_data["submitting_task_id"] = task_id
    ctx.user_data["state"] = "await_proof_photo"
    await update.callback_query.edit_message_text(
        f"📸 *Kirim Bukti Task*\n\nTask: *{task['title']}*\n\n"
        f"Silakan *kirim foto bukti* Anda mengerjakan task ini.\n"
        f"Ketik /cancel untuk membatalkan.",
        parse_mode=ParseMode.MARKDOWN,
    )


# ---------- Withdraw flow ----------
async def start_withdraw(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_doc = await get_or_create_user(update.effective_user)
    q = update.callback_query
    if not user_doc.get("bank"):
        text = "⚠️ Anda belum mengatur info pembayaran.\n\nSilakan atur dulu di menu *Info Bank/E-Wallet*."
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🏦 Atur Info", callback_data="bank:set")],
            [InlineKeyboardButton("⬅️ Menu Utama", callback_data="menu:home")],
        ])
        await q.edit_message_text(text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)
        return
    if user_doc.get("balance", 0) <= 0:
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Menu Utama", callback_data="menu:home")]])
        await q.edit_message_text("💰 Saldo Anda 0. Selesaikan task dulu ya!", reply_markup=kb)
        return

    bank = user_doc["bank"]
    ctx.user_data["state"] = "await_wd_amount"
    await q.edit_message_text(
        f"💵 *Ajukan Withdraw*\n\n"
        f"Saldo: *{format_idr(user_doc['balance'])}*\n"
        f"Ke: *{bank['method']}* - `{bank['account_number']}` ({bank['account_name']})\n\n"
        f"Kirim *nominal* yang ingin di-withdraw (angka saja):\n"
        f"Ketik /cancel untuk batal.",
        parse_mode=ParseMode.MARKDOWN,
    )


# ---------- Bank set flow ----------
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


# ---------- Text/Photo router (state-based) ----------
async def on_photo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    state = ctx.user_data.get("state")
    if state != "await_proof_photo":
        return
    photo = update.message.photo[-1]
    file = await ctx.bot.get_file(photo.file_id)
    buf = BytesIO()
    await file.download_to_memory(buf)
    b64 = base64.b64encode(buf.getvalue()).decode()
    ctx.user_data["proof_image"] = f"data:image/jpeg;base64,{b64}"
    ctx.user_data["state"] = "await_proof_text"
    await update.message.reply_text(
        "✅ Foto diterima!\n\nSekarang kirim *keterangan/deskripsi* singkat sebagai pelengkap bukti.\n"
        "Ketik /skip untuk lewati keterangan.",
        parse_mode=ParseMode.MARKDOWN,
    )


async def on_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    state = ctx.user_data.get("state")
    text = update.message.text.strip()

    if state == "await_proof_photo":
        await update.message.reply_text("Silakan kirim *foto* bukti terlebih dahulu, atau /cancel.", parse_mode=ParseMode.MARKDOWN)
        return

    if state == "await_proof_text":
        note = text if text != "/skip" else ""
        task_id = ctx.user_data.get("submitting_task_id")
        image = ctx.user_data.get("proof_image")
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
        ctx.user_data.clear()
        task = await db.tasks.find_one({"id": task_id})
        await update.message.reply_text(
            f"✅ *Bukti Terkirim!*\n\nTask: *{task['title'] if task else '-'}*\n"
            f"Status: *pending* - menunggu verifikasi admin.\n\n"
            f"Anda akan mendapat notifikasi setelah diproses. Ketik /start untuk menu utama.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    if state == "await_wd_amount":
        try:
            amount = int(text.replace(".", "").replace(",", "").replace("Rp", "").strip())
        except ValueError:
            await update.message.reply_text("Nominal tidak valid. Kirim angka saja, contoh: 25000")
            return
        user = await db.users.find_one({"telegram_id": update.effective_user.id})
        if amount <= 0:
            await update.message.reply_text("Nominal harus lebih dari 0.")
            return
        if amount > user.get("balance", 0):
            await update.message.reply_text(f"Saldo tidak cukup. Saldo: {format_idr(user['balance'])}")
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
        # Deduct balance (hold)
        await db.users.update_one({"telegram_id": update.effective_user.id}, {"$inc": {"balance": -amount}})
        ctx.user_data.clear()
        await update.message.reply_text(
            f"✅ *Withdraw Diajukan!*\n\n"
            f"Nominal: *{format_idr(amount)}*\n"
            f"Ke: *{bank['method']}* {bank['account_number']}\n"
            f"Status: *pending*\n\n"
            f"Admin akan segera memproses. Bukti pembayaran akan dikirim ke Anda dan diumumkan di {CHANNEL}.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    if state == "await_bank_number":
        if not text.replace(" ", "").isdigit():
            await update.message.reply_text("Nomor harus berupa angka. Coba lagi:")
            return
        ctx.user_data["bank_number"] = text.replace(" ", "")
        ctx.user_data["state"] = "await_bank_name"
        await update.message.reply_text("Sekarang kirim *nama pemilik rekening*:", parse_mode=ParseMode.MARKDOWN)
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
            f"✅ Info pembayaran tersimpan!\n\n"
            f"Metode: *{bank['method']}*\n"
            f"Nomor: `{bank['account_number']}`\n"
            f"Nama: *{bank['account_name']}*\n\n"
            f"Ketik /start untuk menu utama.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    # Default: show menu
    user_doc = await get_or_create_user(update.effective_user)
    await show_main_menu(update, user_doc)


# ---------- External send functions (called from FastAPI) ----------
async def _safe_send_message(bot, chat_id, text: str):
    """Try MARKDOWN, fallback to plain text on BadRequest."""
    from telegram.error import BadRequest
    try:
        return await bot.send_message(chat_id=chat_id, text=text, parse_mode=ParseMode.MARKDOWN)
    except BadRequest as e:
        if "parse" in str(e).lower() or "entit" in str(e).lower():
            return await bot.send_message(chat_id=chat_id, text=text, parse_mode=None)
        raise


async def _safe_send_photo(bot, chat_id, photo_bytes, caption: str):
    from telegram.error import BadRequest
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


async def send_channel_broadcast(text: str, image_base64: Optional[str] = None) -> Optional[int]:
    app = bot_state.get("app")
    if not app:
        raise RuntimeError("Bot not running")
    bot = app.bot
    if image_base64:
        img_bytes = _decode_image(image_base64)
        msg = await _safe_send_photo(bot, CHANNEL, img_bytes, text)
    else:
        msg = await _safe_send_message(bot, CHANNEL, text)
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
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("tasks", lambda u, c: send_task_list(u, c, edit=False)))
    app.add_handler(CommandHandler("profile", cmd_start))  # reuse
    app.add_handler(CommandHandler("balance", cmd_start))
    app.add_handler(CommandHandler("cancel", cmd_cancel))
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
