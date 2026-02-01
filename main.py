import os
from datetime import datetime

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID")  # حطه بمتغيرات Railway

# ====== إعدادات المتجر ======
STORE_NAME = "متجري 🛒"
CURRENCY = "$"

PRODUCTS = [
    {"id": "p1", "name": "تيشيرت", "price": 10},
    {"id": "p2", "name": "كاب", "price": 7},
    {"id": "p3", "name": "كوب", "price": 5},
]

# States داخل user_data
MODE_KEY = "mode"          # None / "support" / "checkout_name" / "checkout_phone" / "checkout_address"
CART_KEY = "cart"          # dict product_id -> qty
CHECKOUT_KEY = "checkout"  # dict name/phone/address


def _admin_id() -> int | None:
    try:
        return int(ADMIN_CHAT_ID) if ADMIN_CHAT_ID else None
    except:
        return None


def get_product(pid: str):
    for p in PRODUCTS:
        if p["id"] == pid:
            return p
    return None


def get_cart(context: ContextTypes.DEFAULT_TYPE) -> dict:
    cart = context.user_data.get(CART_KEY)
    if not isinstance(cart, dict):
        cart = {}
        context.user_data[CART_KEY] = cart
    return cart


def cart_totals(cart: dict):
    lines = []
    total = 0
    for pid, qty in cart.items():
        p = get_product(pid)
        if not p:
            continue
        subtotal = p["price"] * qty
        total += subtotal
        lines.append((p["name"], qty, subtotal))
    return lines, total


def main_menu_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🛍️ المنتجات", callback_data="shop")],
        [InlineKeyboardButton("🧺 السلة", callback_data="cart")],
        [InlineKeyboardButton("✅ إتمام الطلب", callback_data="checkout")],
        [InlineKeyboardButton("🆘 الدعم", callback_data="support")],
    ])


def shop_kb():
    rows = []
    for p in PRODUCTS:
        rows.append([InlineKeyboardButton(f"➕ {p['name']} - {p['price']}{CURRENCY}", callback_data=f"add:{p['id']}")])
    rows.append([InlineKeyboardButton("🧺 السلة", callback_data="cart")])
    rows.append([InlineKeyboardButton("⬅️ رجوع", callback_data="home")])
    return InlineKeyboardMarkup(rows)


def cart_kb(cart: dict):
    rows = []
    # أزرار تحكم لكل منتج بالسلة
    for pid, qty in cart.items():
        p = get_product(pid)
        if not p:
            continue
        rows.append([
            InlineKeyboardButton("➖", callback_data=f"dec:{pid}"),
            InlineKeyboardButton(f"{p['name']} x{qty}", callback_data="noop"),
            InlineKeyboardButton("➕", callback_data=f"inc:{pid}"),
            InlineKeyboardButton("🗑️", callback_data=f"del:{pid}"),
        ])

    rows += [
        [InlineKeyboardButton("🗑️ إفراغ السلة", callback_data="clearcart")],
        [InlineKeyboardButton("✅ إتمام الطلب", callback_data="checkout")],
        [InlineKeyboardButton("⬅️ رجوع", callback_data="home")],
    ]
    return InlineKeyboardMarkup(rows)


def back_home_kb():
    return InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ رجوع للقائمة", callback_data="home")]])


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data[MODE_KEY] = None
    await update.message.reply_text(
        f"أهلاً في {STORE_NAME}\nاختار من القائمة 👇",
        reply_markup=main_menu_kb()
    )


async def myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # مفيد عشان تجيب ADMIN_CHAT_ID
    uid = update.effective_user.id
    await update.message.reply_text(f"ID تبعك هو:\n{uid}")


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "أوامر الأدمن:\n"
        "/myid — يطلع ID\n"
        "/reply USER_ID نص الرد — للرد على زبون دعم\n\n"
        "مثال:\n/reply 123456789 مرحبا! كيف بقدر ساعدك؟"
    )


async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "noop":
        return

    cart = get_cart(context)

    if data == "home":
        context.user_data[MODE_KEY] = None
        await query.edit_message_text("اختار من القائمة 👇", reply_markup=main_menu_kb())

    elif data == "shop":
        context.user_data[MODE_KEY] = None
        await query.edit_message_text("🛍️ المنتجات المتوفرة:", reply_markup=shop_kb())

    elif data.startswith("add:"):
        pid = data.split(":", 1)[1]
        p = get_product(pid)
        if not p:
            await query.edit_message_text("المنتج غير موجود.", reply_markup=main_menu_kb())
            return
        cart[pid] = cart.get(pid, 0) + 1
        await query.edit_message_text(f"✅ تمت إضافة {p['name']} للسلة.", reply_markup=shop_kb())

    elif data == "cart":
        context.user_data[MODE_KEY] = None
        if not cart:
            await query.edit_message_text("سلتك فاضية 😄", reply_markup=back_home_kb())
        else:
            lines, total = cart_totals(cart)
            text = "🧺 سلتك:\n"
            for name, qty, subtotal in lines:
                text += f"- {name} x{qty} = {subtotal}{CURRENCY}\n"
            text += f"\n💰 المجموع: {total}{CURRENCY}\n\n(استعمل الأزرار للتعديل)"
            await query.edit_message_text(text, reply_markup=cart_kb(cart))

    elif data.startswith("inc:"):
        pid = data.split(":", 1)[1]
        if pid in cart:
            cart[pid] += 1
        await query.edit_message_text("🧺 تعديل السلة:", reply_markup=cart_kb(cart))

    elif data.startswith("dec:"):
        pid = data.split(":", 1)[1]
        if pid in cart:
            cart[pid] -= 1
            if cart[pid] <= 0:
                cart.pop(pid, None)
        if not cart:
            await query.edit_message_text("سلتك فاضية 😄", reply_markup=back_home_kb())
        else:
            await query.edit_message_text("🧺 تعديل السلة:", reply_markup=cart_kb(cart))

    elif data.startswith("del:"):
        pid = data.split(":", 1)[1]
        cart.pop(pid, None)
        if not cart:
            await query.edit_message_text("سلتك فاضية 😄", reply_markup=back_home_kb())
        else:
            await query.edit_message_text("🧺 تعديل السلة:", reply_markup=cart_kb(cart))

    elif data == "clearcart":
        cart.clear()
        await query.edit_message_text("🗑️ تم إفراغ السلة.", reply_markup=main_menu_kb())

    elif data == "support":
        # وضع الدعم: أي رسالة يكتبها المستخدم تُرسل للأدمن
        context.user_data[MODE_KEY] = "support"
        await query.edit_message_text(
            "🆘 الدعم الفني\nاكتب رسالتك هون، وأنا رح أوصلها لصاحب المتجر مباشرة.\n\n"
            "للرجوع للقائمة اضغط زر الرجوع 👇",
            reply_markup=back_home_kb()
        )

    elif data == "checkout":
        if not cart:
            await query.edit_message_text("❗ ما في منتجات بالسلة. روح على المنتجات أولاً.", reply_markup=main_menu_kb())
            return
        context.user_data[CHECKOUT_KEY] = {}
        context.user_data[MODE_KEY] = "checkout_name"
        await query.edit_message_text("✅ إتمام الطلب\nاكتب اسمك الكامل:", reply_markup=back_home_kb())

    else:
        await query.edit_message_text("أمر غير معروف.", reply_markup=main_menu_kb())


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mode = context.user_data.get(MODE_KEY)
    text = (update.message.text or "").strip()
    uid = update.effective_user.id
    username = update.effective_user.username or ""
    name = update.effective_user.full_name or ""

    # الرجوع بالقائمة إذا المستخدم كتب /start أو ضغط رجوع يتم التعامل عبر أوامر/أزرار

    # ====== دعم ======
    if mode == "support":
        admin = _admin_id()
        if not admin:
            await update.message.reply_text("في مشكلة بإعدادات المتجر (ADMIN_CHAT_ID). تواصل مع صاحب البوت.")
            return

        msg = (
            "🆘 رسالة دعم جديدة\n"
            f"من: {name} (@{username})\n"
            f"USER_ID: {uid}\n"
            f"الرسالة:\n{text}\n\n"
            "للرد:\n"
            f"/reply {uid} <اكتب ردك>"
        )
        await context.bot.send_message(chat_id=admin, text=msg)
        await update.message.reply_text("✅ وصلت رسالتك للدعم. رح يردّ عليك صاحب المتجر قريباً.")
        return

    # ====== Checkout (إتمام الطلب) ======
    if mode in ("checkout_name", "checkout_phone", "checkout_address"):
        checkout = context.user_data.get(CHECKOUT_KEY, {})
        if mode == "checkout_name":
            checkout["name"] = text
            context.user_data[MODE_KEY] = "checkout_phone"
            context.user_data[CHECKOUT_KEY] = checkout
            await update.message.reply_text("تمام ✅\nهلا اكتب رقمك (واتساب/موبايل):")
            return

        if mode == "checkout_phone":
            checkout["phone"] = text
            context.user_data[MODE_KEY] = "checkout_address"
            context.user_data[CHECKOUT_KEY] = checkout
            await update.message.reply_text("ممتاز ✅\nهلا اكتب العنوان للتوصيل:")
            return

        if mode == "checkout_address":
            checkout["address"] = text
            context.user_data[CHECKOUT_KEY] = checkout
            context.user_data[MODE_KEY] = None

            cart = get_cart(context)
            lines, total = cart_totals(cart)

            order_id = f"ORD-{uid}-{int(datetime.utcnow().timestamp())}"
            order_text_user = (
                f"✅ تم استلام طلبك!\n"
                f"رقم الطلب: {order_id}\n\n"
                "🧾 التفاصيل:\n"
            )
            for n, q, sub in lines:
                order_text_user += f"- {n} x{q} = {sub}{CURRENCY}\n"
            order_text_user += f"\n💰 المجموع: {total}{CURRENCY}\n\n"
            "رح يتواصل معك صاحب المتجر للتأكيد 👌"

            await update.message.reply_text(order_text_user, reply_markup=main_menu_kb())

            # أرسل للأدمن
            admin = _admin_id()
            if admin:
                order_text_admin = (
                    "🛒 طلب جديد\n"
                    f"ORDER_ID: {order_id}\n"
                    f"من: {checkout.get('name')} | {name} (@{username})\n"
                    f"USER_ID: {uid}\n"
                    f"هاتف: {checkout.get('phone')}\n"
                    f"عنوان: {checkout.get('address')}\n\n"
                    "🧾 الطلب:\n"
                )
                for n, q, sub in lines:
                    order_text_admin += f"- {n} x{q} = {sub}{CURRENCY}\n"
                order_text_admin += f"\n💰 المجموع: {total}{CURRENCY}\n\n"
                "للرد على الزبون:\n"
                f"/reply {uid} <نص>"
                await context.bot.send_message(chat_id=admin, text=order_text_admin)

            # فَرّغ السلة بعد الطلب
            cart.clear()
            return

    # إذا ما في مود خاص
    await update.message.reply_text("اكتب /start ليفتح معك المتجر 👇")


async def reply_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # /reply USER_ID message...
    admin = _admin_id()
    if not admin or update.effective_chat.id != admin:
        await update.message.reply_text("هذا الأمر للأدمن فقط.")
        return

    if not context.args or len(context.args) < 2:
        await update.message.reply_text("استخدمها هيك:\n/reply USER_ID نص الرد")
        return

    try:
        target_id = int(context.args[0])
    except:
        await update.message.reply_text("USER_ID لازم يكون رقم.")
        return

    msg = " ".join(context.args[1:]).strip()
    if not msg:
        await update.message.reply_text("اكتب نص الرد.")
        return

    await context.bot.send_message(chat_id=target_id, text=f"💬 رد الدعم:\n{msg}")
    await update.message.reply_text("✅ تم إرسال الرد للزبون.")


def main():
    if not TOKEN:
        raise RuntimeError("BOT_TOKEN is missing")

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("myid", myid))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("reply", reply_cmd))

    app.add_handler(CallbackQueryHandler(on_button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

    app.run_polling()


if __name__ == "__main__":
    main()
