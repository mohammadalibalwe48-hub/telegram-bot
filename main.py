import os
import asyncpg
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, MessageHandler,
    ContextTypes, filters
)

TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_CHAT_ID = int(os.environ.get("ADMIN_CHAT_ID", "0"))
DATABASE_URL = os.environ.get("DATABASE_URL")

CURRENCY = "$"
STORE_NAME = "متجر الأكواد 🛒"

# ---------- DB ----------
async def db() -> asyncpg.Pool:
    return app.bot_data["db_pool"]

async def init_db(app: Application):
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=5)
    app.bot_data["db_pool"] = pool

    async with pool.acquire() as conn:
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id SERIAL PRIMARY KEY,
            sku TEXT UNIQUE NOT NULL,              -- مثال: psn_10
            name TEXT NOT NULL,
            price INT NOT NULL,
            kind TEXT NOT NULL DEFAULT 'code'      -- 'code' أو 'normal'
        );
        """)
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS codes (
            id SERIAL PRIMARY KEY,
            sku TEXT NOT NULL,
            code TEXT UNIQUE NOT NULL,
            is_sold BOOLEAN NOT NULL DEFAULT FALSE,
            sold_to BIGINT,
            sold_at TIMESTAMP
        );
        """)
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS balances (
            user_id BIGINT PRIMARY KEY,
            balance INT NOT NULL DEFAULT 0
        );
        """)

async def close_db(app: Application):
    pool = app.bot_data.get("db_pool")
    if pool:
        await pool.close()

# ---------- Helpers ----------
def is_admin(update: Update) -> bool:
    return update.effective_user and update.effective_user.id == ADMIN_CHAT_ID

def home_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🛍️ المنتجات", callback_data="shop")],
        [InlineKeyboardButton("💳 رصيدي", callback_data="balance")],
        [InlineKeyboardButton("🆘 الدعم", callback_data="support")],
    ])

async def get_balance(pool, user_id: int) -> int:
    row = await pool.fetchrow("SELECT balance FROM balances WHERE user_id=$1", user_id)
    return int(row["balance"]) if row else 0

async def add_balance(pool, user_id: int, amount: int):
    await pool.execute("""
    INSERT INTO balances(user_id, balance) VALUES($1, $2)
    ON CONFLICT (user_id) DO UPDATE SET balance = balances.balance + $2
    """, user_id, amount)

# ---------- UI ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["mode"] = None
    await update.message.reply_text(f"أهلاً في {STORE_NAME} 👇", reply_markup=home_kb())

async def shop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pool = await db()
    products = await pool.fetch("SELECT sku,name,price,kind FROM products ORDER BY id DESC")

    if not products:
        await update.effective_message.reply_text("ما في منتجات حالياً.", reply_markup=home_kb())
        return

    rows = []
    for p in products:
        rows.append([InlineKeyboardButton(
            f"{p['name']} — {p['price']}{CURRENCY}",
            callback_data=f"buy:{p['sku']}"
        )])
    rows.append([InlineKeyboardButton("⬅️ رجوع", callback_data="home")])
    await update.effective_message.reply_text("🛍️ المنتجات:", reply_markup=InlineKeyboardMarkup(rows))

async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data
    pool = await db()

    if data == "home":
        context.user_data["mode"] = None
        await q.edit_message_text("القائمة الرئيسية 👇", reply_markup=home_kb())
        return

    if data == "shop":
        await q.delete_message()
        await shop(update, context)
        return

    if data == "balance":
        b = await get_balance(pool, update.effective_user.id)
        await q.edit_message_text(f"💳 رصيدك الحالي: {b}{CURRENCY}", reply_markup=home_kb())
        return

    if data == "support":
        context.user_data["mode"] = "support"
        await q.edit_message_text("🆘 اكتب رسالتك للدعم الآن، وسأوصلها للأدمن.", reply_markup=home_kb())
        return

    if data.startswith("buy:"):
        sku = data.split(":", 1)[1]
        user_id = update.effective_user.id

        # Transaction: خصم + تسليم كود + تعليم الكود مباع (ذرّي / آمن ضد التزامن)
        async with pool.acquire() as conn:
            async with conn.transaction():
                prod = await conn.fetchrow("SELECT sku,name,price,kind FROM products WHERE sku=$1", sku)
                if not prod:
                    await q.edit_message_text("المنتج غير موجود.", reply_markup=home_kb())
                    return

                bal = await get_balance(pool, user_id)
                price = int(prod["price"])
                if bal < price:
                    await q.edit_message_text(
                        f"❗ رصيدك غير كافي.\nرصيدك: {bal}{CURRENCY}\nالسعر: {price}{CURRENCY}",
                        reply_markup=home_kb()
                    )
                    return

                # لو المنتج من نوع "code": نجيب أول كود غير مباع ونقفله
                if prod["kind"] == "code":
                    code_row = await conn.fetchrow("""
                        SELECT id, code FROM codes
                        WHERE sku=$1 AND is_sold=FALSE
                        ORDER BY id
                        FOR UPDATE SKIP LOCKED
                        LIMIT 1
                    """, sku)

                    if not code_row:
                        await q.edit_message_text("❗ نفدت الأكواد لهذا المنتج.", reply_markup=home_kb())
                        return

                    # خصم الرصيد
                    await conn.execute("""
                        INSERT INTO balances(user_id,balance) VALUES($1, $2)
                        ON CONFLICT (user_id) DO UPDATE SET balance = balances.balance - $2
                    """, user_id, price)

                    # علّم الكود مباع
                    await conn.execute("""
                        UPDATE codes
                        SET is_sold=TRUE, sold_to=$1, sold_at=NOW()
                        WHERE id=$2
                    """, user_id, int(code_row["id"]))

                    await q.edit_message_text(
                        f"✅ تمت العملية بنجاح!\n\n🎫 كودك:\n`{code_row['code']}`\n\nشكراً لشرائك ❤️",
                        parse_mode="Markdown",
                        reply_markup=home_kb()
                    )
                    return

                # منتجات عادية (بدون كود) — بس خصم وتأكيد
                await conn.execute("""
                    INSERT INTO balances(user_id,balance) VALUES($1, $2)
                    ON CONFLICT (user_id) DO UPDATE SET balance = balances.balance - $2
                """, user_id, price)

                await q.edit_message_text(
                    f"✅ تم شراء {prod['name']}.\n(هذا منتج عادي بدون كود حالياً)",
                    reply_markup=home_kb()
                )
                return

# ---------- Support messages ----------
async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("mode") != "support":
        return

    msg = (update.message.text or "").strip()
    uid = update.effective_user.id
    name = update.effective_user.full_name
    username = update.effective_user.username or ""

    await context.bot.send_message(
        chat_id=ADMIN_CHAT_ID,
        text=(
            "🆘 رسالة دعم جديدة\n"
            f"من: {name} (@{username})\n"
            f"USER_ID: {uid}\n\n"
            f"{msg}\n\n"
            f"للرد:\n/reply {uid} <نص>"
        )
    )
    await update.message.reply_text("✅ وصلت رسالتك للأدمن. رح يرد عليك قريباً.", reply_markup=home_kb())

# ---------- Admin commands ----------
async def addproduct(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return

    # /addproduct sku "name" price kind
    # مثال: /addproduct psn_10 "PSN 10$" 10 code
    if len(context.args) < 4:
        await update.message.reply_text('استخدم:\n/addproduct sku "الاسم" السعر kind\nمثال:\n/addproduct psn_10 "PSN 10$" 10 code')
        return

    sku = context.args[0]
    # الاسم بين علامات اقتباس على الأغلب، بس نخليها بسيطة: نجمع حتى قبل السعر
    # آخر رقم قبل kind
    kind = context.args[-1]
    price = int(context.args[-2])
    name = " ".join(context.args[1:-2]).strip('"')

    pool = await db()
    await pool.execute("""
        INSERT INTO products(sku,name,price,kind)
        VALUES($1,$2,$3,$4)
        ON CONFLICT (sku) DO UPDATE SET name=$2, price=$3, kind=$4
    """, sku, name, price, kind)

    await update.message.reply_text(f"✅ تم حفظ المنتج: {name} ({sku})")

async def addcode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return

    # /addcode sku CODE
    # مثال: /addcode psn_10 ABCD-1234-EFGH
    if len(context.args) < 2:
        await update.message.reply_text("استخدم:\n/addcode sku CODE\nمثال:\n/addcode psn_10 ABCD-1234-EFGH")
        return

    sku = context.args[0]
    code = " ".join(context.args[1:]).strip()

    pool = await db()
    # تأكد المنتج موجود
    prod = await pool.fetchrow("SELECT sku FROM products WHERE sku=$1", sku)
    if not prod:
        await update.message.reply_text("❗ sku غير موجود. أضف المنتج أولاً بـ /addproduct")
        return

    await pool.execute("INSERT INTO codes(sku,code) VALUES($1,$2)", sku, code)
    await update.message.reply_text("✅ تم إضافة الكود للمخزون.")

async def stock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    # /stock sku
    if len(context.args) < 1:
        await update.message.reply_text("استخدم:\n/stock sku\nمثال:\n/stock psn_10")
        return
    sku = context.args[0]
    pool = await db()
    n = await pool.fetchval("SELECT COUNT(*) FROM codes WHERE sku=$1 AND is_sold=FALSE", sku)
    await update.message.reply_text(f"📦 المخزون المتبقي لـ {sku}: {int(n)} كود")

async def topup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    # /topup USER_ID amount
    if len(context.args) < 2:
        await update.message.reply_text("استخدم:\n/topup USER_ID amount\nمثال:\n/topup 123456789 50")
        return
    user_id = int(context.args[0])
    amount = int(context.args[1])

    pool = await db()
    await add_balance(pool, user_id, amount)
    await update.message.reply_text("✅ تم شحن الرصيد.")
    await context.bot.send_message(chat_id=user_id, text=f"💳 تم شحن رصيدك: +{amount}{CURRENCY}")

async def reply_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    if len(context.args) < 2:
        await update.message.reply_text("استخدم:\n/reply USER_ID نص الرد")
        return
    target = int(context.args[0])
    msg = " ".join(context.args[1:])
    await context.bot.send_message(chat_id=target, text=f"💬 رد الدعم:\n{msg}")
    await update.message.reply_text("✅ تم إرسال الرد.")

# ---------- App ----------
app = Application.builder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("addproduct", addproduct))
app.add_handler(CommandHandler("addcode", addcode))
app.add_handler(CommandHandler("stock", stock))
app.add_handler(CommandHandler("topup", topup))
app.add_handler(CommandHandler("reply", reply_cmd))

app.add_handler(CallbackQueryHandler(on_button))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

async def on_startup(app_: Application):
    await init_db(app_)

async def on_shutdown(app_: Application):
    await close_db(app_)

app.post_init = on_startup
app.post_shutdown = on_shutdown

if __name__ == "__main__":
    app.run_polling()
