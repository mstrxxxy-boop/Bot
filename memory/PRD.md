# BigoCuan Telegram Task Bot - PRD

## Original Problem Statement
Bot Telegram untuk otomasi task (task-to-earn platform). Multi-user. Admin input task manual via dashboard web. User via bot Telegram bisa: lihat task tersedia, profil user, saldo, riwayat task (valid/reject), history balance, dan withdraw. Verifikasi task & pembayaran manual oleh admin. Admin input bukti transaksi (teks + foto) → dikirim ke user + broadcast otomatis ke channel `@BigoCuan` dengan nama & username user.

## User Personas
1. **Admin (Operator)**: Login web dashboard, buat task, verifikasi bukti, proses withdraw
2. **User (Pengguna Task)**: Interaksi via Telegram bot untuk kerjakan task & dapat Rupiah

## Tech Stack
- Backend: FastAPI + Motor (MongoDB) + python-telegram-bot 21.6 (long polling)
- Frontend: React 19 + Tailwind + Sonner toasts + Lucide icons
- Auth: JWT (7-day) for admin dashboard
- Database: MongoDB (`bigocuan_db`)
- Currency: IDR (Rupiah)

## Architecture
- FastAPI backend (`/app/backend/server.py`) exposes REST API prefixed `/api/*`
- Telegram bot runs as background asyncio task (`/app/backend/telegram_bot.py`), starts on FastAPI startup
- Bot uses long polling (drop_pending_updates=True)
- Withdraw approval: admin uploads photo+text → DM to user + auto-broadcast to `@BigoCuan` channel

## Core Features Implemented (2026-09-03)
### Admin Dashboard (`/`)
- Login (admin/admin123 - JWT auth)
- Overview: 4 KPI cards, 7-day activity chart, e-wallet distribution, quick approval queue
- Tasks Management: CRUD, active/pause toggle, slot tracking
- Submissions Review: filter (pending/approved/rejected/all), photo preview, approve → auto credit balance
- Withdrawals: filter, approve modal with mandatory image upload + note, auto DM + broadcast preview
- Users Management: table with balance, search, detail modal with history, manual balance adjust
- Broadcast: manual channel post + full broadcast log with status (sent/failed)

### Telegram Bot (@BigoCuan_bot)
- /start - Main menu with inline keyboard
- Task list (filters out already-submitted/quota-full tasks)
- Task detail + Submit proof flow (photo → text/skip)
- Profile view
- Balance view
- Task history (last 20) with reject reasons
- Balance history (last 20)
- Bank/E-wallet setup (DANA / GoPay / ShopeePay) - editable
- Withdraw request flow (nominal input → auto-deduct balance → pending)
- Auto DM notifications on approve/reject/withdraw

### Auto Broadcast
- On withdraw approve, sends photo+caption to `@BigoCuan` channel with user name & username
- User also gets private DM with same proof
- Markdown-safe (auto-fallback to plain text on parse errors)
- Full status logging (sent/failed + error)

## Fixes Applied Post-Testing
- Markdown escape fallback in Telegram sends (previously broke on usernames with `_`)
- image_base64 required + base64 validation on withdraw approve
- PATCH/DELETE task returns 404 for non-existent
- Balance adjust prevents negative balance
- Broadcast text validation (min_length=1)
- Broadcast_logs records status + error field
- Daily stats bucket uses next-day boundary (no last-second drop)

## Backend Testing Results
- 59/59 pytest tests passed (100%)
- All 6 fixes verified
- Bot confirmed running as admin in @BigoCuan (real broadcast messages sent)

## Backlog / Future Improvements (P1/P2)
- P1: Resend button for failed broadcasts (surface undelivered proofs in dashboard)
- P1: Rate limiting on /api/auth/login (currently unlimited attempts)
- P2: Migrate to FastAPI lifespan (from deprecated @app.on_event)
- P2: N+1 query optimization on GET /api/tasks|submissions|withdrawals (use $lookup)
- P2: Category tags on tasks + filter in bot
- P2: Referral system (invite bonus)
- P2: Multi-admin support with roles

## Files
- `/app/backend/server.py` - FastAPI + all API routes
- `/app/backend/telegram_bot.py` - Bot handlers + send helpers
- `/app/backend/.env` - Bot token, JWT secret, admin creds, channel
- `/app/frontend/src/App.js` - Full admin dashboard (single file, 6 pages)
- `/app/frontend/src/index.css` - Design system (dark fintech emerald+gold)
- `/app/memory/test_credentials.md` - Admin login credentials
