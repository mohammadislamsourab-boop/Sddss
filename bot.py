"""Telegram auto-order store bot.

A self-serve digital-goods shop: buyers browse products, pick a quantity,
pay with their wallet balance / Binance / USDT (BEP20), and receive the
stock automatically. Admins manage products, stock and payment reviews.

Run with:  python bot.py
"""
from __future__ import annotations

import logging

from telegram import InputMediaPhoto, Update
from telegram.constants import ParseMode
from telegram.error import BadRequest
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

import config
import database as db
import keyboards as kb

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("store-bot")

# Keys used inside context.user_data to track a multi-step interaction.
AWAIT_KEY = "await"  # value: (action, payload)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _clear_state(context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop(AWAIT_KEY, None)


def product_caption(product, in_stock: int) -> str:
    name = f"{product['emoji']} {product['name']}".strip()
    lines = [f"<b>{name}</b>"]
    if product["description"]:
        lines.append(product["description"])
    lines += [
        "",
        f"💵 Price: <b>{config.money(product['price'])}</b>",
        f"🟢 Stock: <b>{in_stock} accounts</b>",
        f"📊 Sold: <b>{product['sold']} accounts</b>",
    ]
    return "\n".join(lines)


async def deliver_order(order_row, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Reserve stock and send the goods to the buyer. Returns True on success."""
    contents = db.reserve_and_deliver_stock(
        order_row["product_id"],
        order_row["quantity"],
        order_row["user_id"],
        order_row["id"],
    )
    if contents is None:
        return False

    delivered_text = "\n".join(contents)
    db.set_order_status(order_row["id"], db.STATUS_COMPLETED, delivered=delivered_text)

    body = "\n".join(f"<code>{c}</code>" for c in contents)
    message = (
        f"✅ <b>Order delivered!</b>\n\n"
        f"🧾 Order: <code>{order_row['code']}</code>\n"
        f"📦 {order_row['product_name']} ×{order_row['quantity']}\n\n"
        f"Your item(s):\n{body}\n\n"
        f"Thank you for your purchase! 🎉"
    )
    await context.bot.send_message(
        chat_id=order_row["user_id"], text=message, parse_mode=ParseMode.HTML
    )
    return True


async def notify_admins(context: ContextTypes.DEFAULT_TYPE, text: str,
                        reply_markup=None) -> None:
    for admin_id in config.ADMIN_IDS:
        try:
            await context.bot.send_message(
                chat_id=admin_id, text=text,
                parse_mode=ParseMode.HTML, reply_markup=reply_markup,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not notify admin %s: %s", admin_id, exc)


# --------------------------------------------------------------------------- #
# /start & menu
# --------------------------------------------------------------------------- #
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    db.upsert_user(user.id, user.username, user.first_name)
    _clear_state(context)
    text = (
        f"👋 Welcome to <b>{config.STORE_NAME}</b>, {user.first_name}!\n\n"
        "Buy digital products instantly with automatic delivery.\n\n"
        "Use the menu below to get started 👇"
    )
    await update.message.reply_text(
        text, parse_mode=ParseMode.HTML, reply_markup=kb.main_menu()
    )


async def show_products(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    products = db.list_products(active_only=True)
    if not products:
        await update.effective_message.reply_text(
            "🛒 No products are available right now. Please check back soon!"
        )
        return
    await update.effective_message.reply_text(
        "🛍️ <b>Products</b>\n\nSelect a product to view details:",
        parse_mode=ParseMode.HTML,
        reply_markup=kb.products_keyboard(products),
    )


async def show_wallet(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    db.upsert_user(user.id, user.username, user.first_name)
    balance = db.get_balance(user.id)
    txs = db.list_transactions(user.id, limit=5)
    lines = [
        "👛 <b>Your Wallet</b>",
        "",
        f"Balance: <b>{config.money(balance)}</b>",
    ]
    if txs:
        lines.append("\n<b>Recent activity:</b>")
        for t in txs:
            sign = "＋" if t["amount"] >= 0 else "－"
            lines.append(
                f"{sign}{config.money(abs(t['amount']))} · {t['type']}"
                + (f" · {t['note']}" if t["note"] else "")
            )
    lines.append("\nTo add funds, use one of the options below:")
    await update.effective_message.reply_text(
        "\n".join(lines), parse_mode=ParseMode.HTML, reply_markup=kb.wallet_keyboard()
    )


async def show_support(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "💬 <b>Support</b>\n\n"
        f"Need help with an order or payment?\n"
        f"Contact us: {config.SUPPORT_USERNAME}\n\n"
        "Please include your <b>order ID</b> when reaching out."
    )
    await update.effective_message.reply_text(text, parse_mode=ParseMode.HTML)


async def show_api(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "🔗 <b>API Access</b>\n\n"
        "Reseller / automation API keys are available for verified buyers.\n"
        f"Contact {config.SUPPORT_USERNAME} to request access and pricing."
    )
    await update.effective_message.reply_text(text, parse_mode=ParseMode.HTML)


# --------------------------------------------------------------------------- #
# Text router (menu buttons + pending input states)
# --------------------------------------------------------------------------- #
async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (update.message.text or "").strip()

    # 1) Pending multi-step input takes priority.
    pending = context.user_data.get(AWAIT_KEY)
    if pending:
        action, payload = pending
        if action == "quantity":
            await handle_quantity_input(update, context, payload, text)
            return
        if action == "txref":
            await handle_txref_input(update, context, payload, text)
            return
        if action == "admin_addstock":
            await handle_admin_addstock_input(update, context, payload, text)
            return

    # 2) Menu buttons.
    if text == kb.BTN_PRODUCTS:
        await show_products(update, context)
    elif text == kb.BTN_WALLET:
        await show_wallet(update, context)
    elif text == kb.BTN_SUPPORT:
        await show_support(update, context)
    elif text == kb.BTN_API:
        await show_api(update, context)
    else:
        await update.message.reply_text(
            "Please use the menu below 👇", reply_markup=kb.main_menu()
        )


# --------------------------------------------------------------------------- #
# Product browsing callbacks
# --------------------------------------------------------------------------- #
async def cb_refresh_products(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer("Refreshed")
    products = db.list_products(active_only=True)
    markup = kb.products_keyboard(products)
    try:
        # If the message was a product photo, we can't edit text — send fresh.
        if query.message.photo:
            await query.message.reply_text(
                "🛍️ <b>Products</b>\n\nSelect a product to view details:",
                parse_mode=ParseMode.HTML, reply_markup=markup,
            )
        else:
            await query.edit_message_text(
                "🛍️ <b>Products</b>\n\nSelect a product to view details:",
                parse_mode=ParseMode.HTML, reply_markup=markup,
            )
    except BadRequest:
        pass


async def cb_product_detail(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    product_id = int(query.data.split(":")[1])
    product = db.get_product(product_id)
    if not product or not product["is_active"]:
        await query.answer("Product unavailable", show_alert=True)
        return
    await query.answer()
    in_stock = db.stock_count(product_id)
    caption = product_caption(product, in_stock)
    markup = kb.product_detail_keyboard(product_id, in_stock > 0)
    if product["image_url"]:
        try:
            await query.message.reply_photo(
                photo=product["image_url"], caption=caption,
                parse_mode=ParseMode.HTML, reply_markup=markup,
            )
            return
        except BadRequest:
            pass  # Fall back to a text message if the image URL is invalid.
    await query.message.reply_text(
        caption, parse_mode=ParseMode.HTML, reply_markup=markup
    )


async def cb_buy(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    product_id = int(query.data.split(":")[1])
    product = db.get_product(product_id)
    if not product or not product["is_active"]:
        await query.answer("Product unavailable", show_alert=True)
        return
    in_stock = db.stock_count(product_id)
    if in_stock <= 0:
        await query.answer("Out of stock", show_alert=True)
        return
    await query.answer()
    limit = min(in_stock, config.MAX_QUANTITY_PER_ORDER)
    context.user_data[AWAIT_KEY] = ("quantity", product_id)
    await query.message.reply_text(
        f"🧨 Enter quantity to buy (1-{limit}):"
    )


async def handle_quantity_input(update: Update, context: ContextTypes.DEFAULT_TYPE,
                                product_id: int, text: str) -> None:
    product = db.get_product(product_id)
    if not product or not product["is_active"]:
        _clear_state(context)
        await update.message.reply_text("Product is no longer available.")
        return

    in_stock = db.stock_count(product_id)
    limit = min(in_stock, config.MAX_QUANTITY_PER_ORDER)
    if not text.isdigit():
        await update.message.reply_text(f"Please enter a number between 1 and {limit}.")
        return
    quantity = int(text)
    if quantity < 1 or quantity > limit:
        await update.message.reply_text(
            f"Quantity must be between 1 and {limit}. Try again."
        )
        return

    _clear_state(context)
    total = round(product["price"] * quantity, 2)
    order = db.create_order(
        user_id=update.effective_user.id,
        product_id=product_id,
        product_name=f"{product['emoji']} {product['name']}".strip(),
        quantity=quantity,
        total=total,
        method="",
        status=db.STATUS_AWAITING_PAYMENT,
    )
    await update.message.reply_text(
        f"💳 <b>Choose payment method</b>\n"
        f"Order: <code>{order['code']}</code>\n"
        f"Item: {order['product_name']} ×{quantity}\n"
        f"Total: <b>{config.money(total)}</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=kb.payment_methods_keyboard(order["code"]),
    )


# --------------------------------------------------------------------------- #
# Payment callbacks
# --------------------------------------------------------------------------- #
async def cb_pay(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    _, method, order_code = query.data.split(":", 2)
    order = db.get_order_by_code(order_code)
    if not order or order["user_id"] != update.effective_user.id:
        await query.answer("Order not found", show_alert=True)
        return
    if order["status"] != db.STATUS_AWAITING_PAYMENT:
        await query.answer("This order can no longer be paid.", show_alert=True)
        return

    if method == kb.PAY_WALLET:
        await pay_with_wallet(update, context, order)
    elif method == kb.PAY_BINANCE:
        await pay_offchain(update, context, order, kb.PAY_BINANCE)
    elif method == kb.PAY_USDT:
        await pay_offchain(update, context, order, kb.PAY_USDT)
    else:
        await query.answer("Unknown method", show_alert=True)


async def pay_with_wallet(update: Update, context: ContextTypes.DEFAULT_TYPE,
                          order) -> None:
    query = update.callback_query
    user_id = update.effective_user.id
    balance = db.get_balance(user_id)
    if balance < order["total"]:
        await query.answer()
        await query.message.reply_text(
            f"❌ Insufficient wallet balance.\n"
            f"Balance: {config.money(balance)} · Needed: {config.money(order['total'])}\n"
            f"Top up your wallet and try again.",
            reply_markup=kb.wallet_keyboard(),
        )
        return

    # Verify stock is still available before charging.
    if db.stock_count(order["product_id"]) < order["quantity"]:
        await query.answer("Out of stock", show_alert=True)
        db.set_order_status(order["id"], db.STATUS_CANCELLED)
        return

    db.adjust_balance(user_id, -order["total"], db.TX_PURCHASE,
                      note=f"Order {order['code']}")
    db.set_order_status(order["id"], db.STATUS_AWAITING_PAYMENT, tx_ref="wallet")
    await query.answer("Paid with wallet ✅")

    delivered = await deliver_order(db.get_order(order["id"]), context)
    if not delivered:
        # Refund if delivery failed for any reason.
        db.adjust_balance(user_id, order["total"], db.TX_REFUND,
                          note=f"Refund {order['code']}")
        db.set_order_status(order["id"], db.STATUS_CANCELLED)
        await query.message.reply_text(
            "⚠️ Delivery failed (stock changed). You have been refunded."
        )
        return

    new_balance = db.get_balance(user_id)
    await query.message.reply_text(
        f"💰 Paid with wallet for order <code>{order['code']}</code>.\n"
        f"New balance: <b>{config.money(new_balance)}</b>",
        parse_mode=ParseMode.HTML,
    )
    await notify_admins(
        context,
        f"💰 <b>Wallet sale</b>\nOrder <code>{order['code']}</code>\n"
        f"{order['product_name']} ×{order['quantity']} · {config.money(order['total'])}",
    )


async def pay_offchain(update: Update, context: ContextTypes.DEFAULT_TYPE,
                       order, method: str) -> None:
    query = update.callback_query
    await query.answer()
    db.set_order_status(order["id"], db.STATUS_AWAITING_PAYMENT)
    # Persist the chosen method on the order.
    with db.get_conn() as conn:
        conn.execute("UPDATE orders SET method = ? WHERE id = ?",
                     (method, order["id"]))

    if method == kb.PAY_BINANCE:
        detail = (
            f"💠 <b>Binance Pay</b>\n"
            f"Binance ID (tap to copy): <code>{config.BINANCE_ID}</code>\n"
        )
    else:
        detail = (
            f"🪙 <b>USDT (BEP20)</b>\n"
            f"Address (tap to copy): <code>{config.USDT_BEP20_ADDRESS}</code>\n"
        )

    await query.message.reply_text(
        f"{detail}"
        f"Amount to transfer: <b>{config.money(order['total'])}</b>\n\n"
        f"After paying, send the <b>order ID or transaction reference</b> for "
        f"verification using the button below.\n\n"
        f"Order: <code>{order['code']}</code>",
        parse_mode=ParseMode.HTML,
        reply_markup=kb.submit_txref_keyboard(order["code"]),
    )


async def cb_txref(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    order_code = query.data.split(":", 1)[1]
    order = db.get_order_by_code(order_code)
    if not order or order["user_id"] != update.effective_user.id:
        await query.answer("Order not found", show_alert=True)
        return
    if order["status"] != db.STATUS_AWAITING_PAYMENT:
        await query.answer("This order is not awaiting payment.", show_alert=True)
        return
    await query.answer()
    context.user_data[AWAIT_KEY] = ("txref", order_code)
    await query.message.reply_text(
        "📝 Send the order ID or transaction reference for your payment:"
    )


async def handle_txref_input(update: Update, context: ContextTypes.DEFAULT_TYPE,
                             order_code: str, text: str) -> None:
    order = db.get_order_by_code(order_code)
    if not order or order["status"] != db.STATUS_AWAITING_PAYMENT:
        _clear_state(context)
        await update.message.reply_text("This order can no longer be updated.")
        return
    if len(text) < 4:
        await update.message.reply_text("That reference looks too short. Try again.")
        return

    _clear_state(context)
    db.set_order_status(order["id"], db.STATUS_AWAITING_REVIEW, tx_ref=text)
    await update.message.reply_text(
        f"✅ Reference received for order <code>{order['code']}</code>.\n"
        f"Your payment is being verified — you'll get your items shortly. ⏳",
        parse_mode=ParseMode.HTML,
    )
    await notify_admins(
        context,
        f"🔔 <b>Payment to verify</b>\n"
        f"Order <code>{order['code']}</code>\n"
        f"{order['product_name']} ×{order['quantity']} · "
        f"{config.money(order['total'])} via {order['method'] or 'off-chain'}\n"
        f"Buyer: <code>{order['user_id']}</code>\n"
        f"Reference: <code>{text}</code>",
        reply_markup=kb.admin_review_keyboard(order["code"]),
    )


async def cb_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    order_code = query.data.split(":", 1)[1]
    order = db.get_order_by_code(order_code)
    if not order or order["user_id"] != update.effective_user.id:
        await query.answer("Order not found", show_alert=True)
        return
    if order["status"] in (db.STATUS_COMPLETED, db.STATUS_CANCELLED):
        await query.answer("Order already finalised.", show_alert=True)
        return
    db.set_order_status(order["id"], db.STATUS_CANCELLED)
    _clear_state(context)
    await query.answer("Order cancelled")
    await query.message.reply_text(
        f"❌ Order <code>{order['code']}</code> cancelled.",
        parse_mode=ParseMode.HTML,
    )


async def cb_noop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.callback_query.answer()


async def cb_topup(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    method = query.data.split(":", 1)[1]
    await query.answer()
    if method == "binance":
        detail = (f"💠 <b>Binance Pay</b>\nBinance ID (tap to copy): "
                  f"<code>{config.BINANCE_ID}</code>")
    else:
        detail = (f"🪙 <b>USDT (BEP20)</b>\nAddress (tap to copy): "
                  f"<code>{config.USDT_BEP20_ADDRESS}</code>")
    await query.message.reply_text(
        f"{detail}\n\nSend any amount, then forward the transaction reference to "
        f"{config.SUPPORT_USERNAME} and your wallet will be credited.",
        parse_mode=ParseMode.HTML,
    )


# --------------------------------------------------------------------------- #
# Admin: review approval/rejection callbacks
# --------------------------------------------------------------------------- #
async def cb_approve(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not config.is_admin(update.effective_user.id):
        await query.answer("Admins only", show_alert=True)
        return
    order_code = query.data.split(":", 1)[1]
    order = db.get_order_by_code(order_code)
    if not order:
        await query.answer("Order not found", show_alert=True)
        return
    if order["status"] != db.STATUS_AWAITING_REVIEW:
        await query.answer(f"Order is '{order['status']}', not awaiting review.",
                           show_alert=True)
        return
    delivered = await deliver_order(order, context)
    if not delivered:
        await query.answer("Not enough stock to deliver!", show_alert=True)
        return
    await query.answer("Approved & delivered ✅")
    await query.edit_message_text(
        f"✅ Approved & delivered order <code>{order['code']}</code>.",
        parse_mode=ParseMode.HTML,
    )


async def cb_reject(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not config.is_admin(update.effective_user.id):
        await query.answer("Admins only", show_alert=True)
        return
    order_code = query.data.split(":", 1)[1]
    order = db.get_order_by_code(order_code)
    if not order:
        await query.answer("Order not found", show_alert=True)
        return
    db.set_order_status(order["id"], db.STATUS_CANCELLED)
    await query.answer("Rejected")
    await query.edit_message_text(
        f"❌ Rejected order <code>{order['code']}</code>.",
        parse_mode=ParseMode.HTML,
    )
    try:
        await context.bot.send_message(
            chat_id=order["user_id"],
            text=(f"❌ Your payment for order <code>{order['code']}</code> could not "
                  f"be verified. Contact {config.SUPPORT_USERNAME} for help."),
            parse_mode=ParseMode.HTML,
        )
    except Exception:  # noqa: BLE001
        pass


# --------------------------------------------------------------------------- #
# Admin commands
# --------------------------------------------------------------------------- #
def _admin_only(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not config.is_admin(update.effective_user.id):
            await update.message.reply_text("⛔ This command is for admins only.")
            return
        return await func(update, context)
    return wrapper


@_admin_only
async def cmd_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    s = db.stats()
    text = (
        "🛠️ <b>Admin Panel</b>\n\n"
        f"👥 Users: <b>{s['users']}</b>\n"
        f"📦 Active products: <b>{s['products']}</b>\n"
        f"✅ Completed orders: <b>{s['completed_orders']}</b>\n"
        f"💵 Revenue: <b>{config.money(s['revenue'])}</b>\n"
        f"🔔 Pending review: <b>{s['pending_review']}</b>\n\n"
        "<b>Commands</b>\n"
        "/addproduct <code>Emoji | Name | Price | Description | ImageURL</code>\n"
        "/addstock <code>&lt;product_id&gt;</code> — then send items (one per line)\n"
        "/products — list products &amp; stock\n"
        "/delproduct <code>&lt;id&gt;</code>\n"
        "/orders [pending] — recent orders\n"
        "/approve <code>&lt;ORDER_CODE&gt;</code> · /reject <code>&lt;ORDER_CODE&gt;</code>\n"
        "/setbalance <code>&lt;user_id&gt; &lt;amount&gt;</code>\n"
        "/broadcast <code>&lt;message&gt;</code>"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


@_admin_only
async def cmd_addproduct(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    raw = update.message.text.partition(" ")[2].strip()
    if not raw or "|" not in raw:
        await update.message.reply_text(
            "Usage:\n/addproduct Emoji | Name | Price | Description | ImageURL\n\n"
            "Example:\n/addproduct 🚀 | Admin Ultra X20 | 80 | 25000 Credit 30D | "
            "https://example.com/img.jpg"
        )
        return
    parts = [p.strip() for p in raw.split("|")]
    emoji = parts[0] if len(parts) > 0 else ""
    name = parts[1] if len(parts) > 1 else ""
    try:
        price = float(parts[2]) if len(parts) > 2 else 0.0
    except ValueError:
        await update.message.reply_text("Price must be a number.")
        return
    description = parts[3] if len(parts) > 3 else ""
    image_url = parts[4] if len(parts) > 4 else ""
    if not name:
        await update.message.reply_text("Product name is required.")
        return
    pid = db.add_product(name=name, price=price, emoji=emoji,
                         description=description, image_url=image_url)
    await update.message.reply_text(
        f"✅ Product #{pid} added: {emoji} {name} — {config.money(price)}\n"
        f"Add stock with: /addstock {pid}"
    )


@_admin_only
async def cmd_addstock(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    arg = update.message.text.partition(" ")[2].strip()
    if not arg.isdigit():
        await update.message.reply_text("Usage: /addstock <product_id>")
        return
    product_id = int(arg)
    product = db.get_product(product_id)
    if not product:
        await update.message.reply_text("No product with that ID.")
        return
    context.user_data[AWAIT_KEY] = ("admin_addstock", product_id)
    await update.message.reply_text(
        f"Send the stock items for <b>{product['name']}</b>, one per line.\n"
        f"Each line becomes one deliverable unit.",
        parse_mode=ParseMode.HTML,
    )


async def handle_admin_addstock_input(update: Update,
                                      context: ContextTypes.DEFAULT_TYPE,
                                      product_id: int, text: str) -> None:
    if not config.is_admin(update.effective_user.id):
        _clear_state(context)
        return
    _clear_state(context)
    items = [line for line in text.splitlines() if line.strip()]
    added = db.add_stock_items(product_id, items)
    total = db.stock_count(product_id)
    await update.message.reply_text(
        f"✅ Added {added} item(s). In-stock now: {total}."
    )


@_admin_only
async def cmd_products(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    products = db.list_products(active_only=False)
    if not products:
        await update.message.reply_text("No products yet. Use /addproduct.")
        return
    lines = ["📦 <b>Products</b>"]
    for p in products:
        flag = "🟢" if p["is_active"] else "🔴"
        lines.append(
            f"{flag} #{p['id']} {p['emoji']} {p['name']} — "
            f"{config.money(p['price'])} · stock {db.stock_count(p['id'])} · "
            f"sold {p['sold']}"
        )
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


@_admin_only
async def cmd_delproduct(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    arg = update.message.text.partition(" ")[2].strip()
    if not arg.isdigit():
        await update.message.reply_text("Usage: /delproduct <id>")
        return
    pid = int(arg)
    if not db.get_product(pid):
        await update.message.reply_text("No product with that ID.")
        return
    db.update_product(pid, is_active=0)
    await update.message.reply_text(f"🔴 Product #{pid} deactivated.")


@_admin_only
async def cmd_orders(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    arg = update.message.text.partition(" ")[2].strip().lower()
    status = db.STATUS_AWAITING_REVIEW if arg in ("pending", "review") else None
    orders = db.list_orders(status=status, limit=15)
    if not orders:
        await update.message.reply_text("No orders found.")
        return
    lines = ["🧾 <b>Orders</b>"]
    for o in orders:
        lines.append(
            f"<code>{o['code']}</code> · {o['product_name']} ×{o['quantity']} · "
            f"{config.money(o['total'])} · {o['status']}"
        )
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


@_admin_only
async def cmd_approve(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    code = update.message.text.partition(" ")[2].strip()
    if not code:
        await update.message.reply_text("Usage: /approve <ORDER_CODE>")
        return
    order = db.get_order_by_code(code)
    if not order:
        await update.message.reply_text("Order not found.")
        return
    if order["status"] != db.STATUS_AWAITING_REVIEW:
        await update.message.reply_text(
            f"Order is '{order['status']}', not awaiting review."
        )
        return
    if await deliver_order(order, context):
        await update.message.reply_text(f"✅ Delivered order {code}.")
    else:
        await update.message.reply_text("Not enough stock to deliver.")


@_admin_only
async def cmd_reject(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    code = update.message.text.partition(" ")[2].strip()
    order = db.get_order_by_code(code)
    if not order:
        await update.message.reply_text("Order not found.")
        return
    db.set_order_status(order["id"], db.STATUS_CANCELLED)
    await update.message.reply_text(f"❌ Rejected order {code}.")
    try:
        await context.bot.send_message(
            chat_id=order["user_id"],
            text=f"❌ Payment for order {code} could not be verified.",
        )
    except Exception:  # noqa: BLE001
        pass


@_admin_only
async def cmd_setbalance(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    parts = update.message.text.split()
    if len(parts) != 3 or not parts[1].isdigit():
        await update.message.reply_text("Usage: /setbalance <user_id> <amount>")
        return
    target = int(parts[1])
    try:
        amount = float(parts[2])
    except ValueError:
        await update.message.reply_text("Amount must be a number.")
        return
    current = db.get_balance(target)
    delta = round(amount - current, 2)
    new_balance = db.adjust_balance(target, delta, db.TX_ADMIN, note="admin set")
    await update.message.reply_text(
        f"✅ Balance for {target} set to {config.money(new_balance)}."
    )
    try:
        await context.bot.send_message(
            chat_id=target,
            text=f"👛 Your wallet balance is now {config.money(new_balance)}.",
        )
    except Exception:  # noqa: BLE001
        pass


@_admin_only
async def cmd_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.message.text.partition(" ")[2].strip()
    if not msg:
        await update.message.reply_text("Usage: /broadcast <message>")
        return
    with db.get_conn() as conn:
        rows = conn.execute("SELECT user_id FROM users").fetchall()
    sent = 0
    for r in rows:
        try:
            await context.bot.send_message(chat_id=r["user_id"], text=msg)
            sent += 1
        except Exception:  # noqa: BLE001
            continue
    await update.message.reply_text(f"📣 Broadcast sent to {sent} user(s).")


# --------------------------------------------------------------------------- #
# Error handler
# --------------------------------------------------------------------------- #
async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.exception("Unhandled error", exc_info=context.error)


# --------------------------------------------------------------------------- #
# Application bootstrap
# --------------------------------------------------------------------------- #
def build_application() -> Application:
    if not config.BOT_TOKEN:
        raise SystemExit(
            "BOT_TOKEN is not set. Copy .env.example to .env and fill it in."
        )
    if not config.ADMIN_IDS:
        logger.warning("ADMIN_IDS is empty — no one can manage the store!")

    db.init_db()
    app = Application.builder().token(config.BOT_TOKEN).build()

    # User commands
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_start))

    # Admin commands
    app.add_handler(CommandHandler("admin", cmd_admin))
    app.add_handler(CommandHandler("addproduct", cmd_addproduct))
    app.add_handler(CommandHandler("addstock", cmd_addstock))
    app.add_handler(CommandHandler("products", cmd_products))
    app.add_handler(CommandHandler("delproduct", cmd_delproduct))
    app.add_handler(CommandHandler("orders", cmd_orders))
    app.add_handler(CommandHandler("approve", cmd_approve))
    app.add_handler(CommandHandler("reject", cmd_reject))
    app.add_handler(CommandHandler("setbalance", cmd_setbalance))
    app.add_handler(CommandHandler("broadcast", cmd_broadcast))

    # Callback queries
    app.add_handler(CallbackQueryHandler(cb_refresh_products, pattern=r"^refresh_products$"))
    app.add_handler(CallbackQueryHandler(cb_product_detail, pattern=r"^prod:"))
    app.add_handler(CallbackQueryHandler(cb_buy, pattern=r"^buy:"))
    app.add_handler(CallbackQueryHandler(cb_pay, pattern=r"^pay:"))
    app.add_handler(CallbackQueryHandler(cb_txref, pattern=r"^txref:"))
    app.add_handler(CallbackQueryHandler(cb_cancel, pattern=r"^cancel:"))
    app.add_handler(CallbackQueryHandler(cb_approve, pattern=r"^approve:"))
    app.add_handler(CallbackQueryHandler(cb_reject, pattern=r"^reject:"))
    app.add_handler(CallbackQueryHandler(cb_topup, pattern=r"^topup:"))
    app.add_handler(CallbackQueryHandler(cb_noop, pattern=r"^noop$"))

    # Free text (menu buttons + pending inputs)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

    app.add_error_handler(on_error)
    return app


def main() -> None:
    app = build_application()
    logger.info("Starting %s bot…", config.STORE_NAME)
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
