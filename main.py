from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
import os

TOKEN = os.environ.get("BOT_TOKEN")

# منتجات تجريبية (غيّرها على كيفك)
PRODUCTS = [
    {"id": "p1", "name": "تيشيرت", "price": 10},
    {"id": "p2", "name": "كاب", "price": 7},
    {"id": "p3", "name": "كوب", "price": 5},
]

def get_product(pid: str):
    for p in PRODUCTS:
        if p["id"] == pid:
            return p
    return None

def get_cart(context: ContextTypes.DEFAULT_TYPE):
    # سلة لكل مستخدم
    if "cart" not in context.user_data:
        context.user_data["cart"] = {}  # {product_id: qty}
    return context.user_data["cart"]

def main_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🛍️ عرض المنتجات", callback_data="shop")],
        [InlineKeyboardButton("🧺 السلة", callback_data="cart")],
        [InlineKeyboardButton("📞 تواصل معنا", callback_data="contact")],
    ])

def products_keyboard():
    rows = []
    for p in PRODUCTS:
        rows.append([InlineKeyboardButton(f"➕ {p['name']} - ${p['price']}", callback_data=f"add:{p['id']}")])
    rows.append([InlineKeyboardButton("🧺 السلة", callback_data="cart")])
    rows.append([InlineKeyboardButton("⬅️ رجوع", callback_data="home")])
    return InlineKeyboardMarkup(rows)

def cart_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🧾 إظهار السلة", callback_data="showcart")],
        [InlineKeyboardButton("🗑️ إفراغ السلة", callback_data="clearcart")],
        [InlineKeyboardButton("🛍️ متابعة التسوق", callback_data="shop")],
        [InlineKeyboardButton("⬅️ رجوع", callback_data="home")],
    ])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "أهلاً في المتجر 🤖🛒\nاختار من القائمة:",
        reply_markup=main_menu_keyboard()
    )

async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    cart = get_cart(context)

    if data == "home":
        await query.edit_message_text("اختار من القائمة:", reply_markup=main_menu_keyboard())

    elif data == "shop":
        await query.edit_message_text("🛍️ المنتجات المتوفرة:", reply_markup=products_keyboard())

    elif data.startswith("add:"):
        pid = data.split(":", 1)[1]
        p = get_product(pid)
        if not p:
            await query.edit_message_text("المنتج غير موجود.")
            return
        cart[pid] = cart.get(pid, 0) + 1
        await query.edit_message_text(
            f"✅ تمت إضافة {p['name']} للسلة.\n\nبدك تضيف كمان؟",
            reply_markup=products_keyboard()
        )

    elif data == "cart":
        await query.edit_message_text("🧺 إدارة السلة:", reply_markup=cart_keyboard())

    elif data == "showcart":
        if not cart:
            await query.edit_message_text("سلتك فاضية 😄", reply_markup=cart_keyboard())
            return

        lines = []
        total = 0
        for pid, qty in cart.items():
            p = get_product(pid)
            if not p:
                continue
            subtotal = p["price"] * qty
            total += subtotal
            lines.append(f"- {p['name']} x{qty} = ${subtotal}")

        text = "🧾 محتوى السلة:\n" + "\n".join(lines) + f"\n\n💰 المجموع: ${total}"
        await query.edit_message_text(text, reply_markup=cart_keyboard())

    elif data == "clearcart":
        cart.clear()
        await query.edit_message_text("🗑️ تم إفراغ السلة.", reply_markup=cart_keyboard())

    elif data == "contact":
        await query.edit_message_text(
            "📞 للتواصل:\nاكتب رسالتك هنا أو حط رقم/يوزر دعم.\n\nمثال: @SupportUsername",
            reply_markup=main_menu_keyboard()
        )

    else:
        await query.edit_message_text("أمر غير معروف.")

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(on_button))
    app.run_polling()

if __name__ == "__main__":
    main()
