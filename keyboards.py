"""Reusable inline / reply keyboards."""
from __future__ import annotations

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

import config

# Bottom menu (persistent reply keyboard) — mirrors the reference bot.
BTN_PRODUCTS = "🛍️ Products"
BTN_SUPPORT = "💬 Support"
BTN_WALLET = "👛 Wallet"
BTN_API = "🔗 API"

# Payment method identifiers.
PAY_WALLET = "wallet"
PAY_BINANCE = "binance"
PAY_USDT = "usdt"

PAY_LABELS = {
    PAY_WALLET: "💰 Wallet",
    PAY_BINANCE: "💠 Binance",
    PAY_USDT: "🪙 USDT (BEP20)",
}


def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton(BTN_PRODUCTS), KeyboardButton(BTN_SUPPORT)],
            [KeyboardButton(BTN_WALLET), KeyboardButton(BTN_API)],
        ],
        resize_keyboard=True,
    )


def products_keyboard(products) -> InlineKeyboardMarkup:
    rows = []
    for p in products:
        label = f"{p['emoji']} {p['name']}".strip()
        rows.append([InlineKeyboardButton(label, callback_data=f"prod:{p['id']}")])
    rows.append([InlineKeyboardButton("🔄 Refresh products",
                                      callback_data="refresh_products")])
    return InlineKeyboardMarkup(rows)


def product_detail_keyboard(product_id: int, in_stock: bool) -> InlineKeyboardMarkup:
    rows = []
    if in_stock:
        rows.append([InlineKeyboardButton("🛒 Buy now",
                                          callback_data=f"buy:{product_id}")])
    else:
        rows.append([InlineKeyboardButton("🚫 Out of stock",
                                          callback_data="noop")])
    rows.append([InlineKeyboardButton("⬅️ Back to products",
                                      callback_data="refresh_products")])
    return InlineKeyboardMarkup(rows)


def payment_methods_keyboard(order_code: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("💰 Pay with Wallet",
                                  callback_data=f"pay:{PAY_WALLET}:{order_code}")],
            [InlineKeyboardButton("💠 Pay with Binance",
                                  callback_data=f"pay:{PAY_BINANCE}:{order_code}")],
            [InlineKeyboardButton("🪙 Pay with USDT (BEP20)",
                                  callback_data=f"pay:{PAY_USDT}:{order_code}")],
            [InlineKeyboardButton("❌ Cancel order",
                                  callback_data=f"cancel:{order_code}")],
        ]
    )


def submit_txref_keyboard(order_code: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📝 Submit payment reference",
                                  callback_data=f"txref:{order_code}")],
            [InlineKeyboardButton("❌ Cancel order",
                                  callback_data=f"cancel:{order_code}")],
        ]
    )


def admin_review_keyboard(order_code: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ Approve & deliver",
                                     callback_data=f"approve:{order_code}"),
                InlineKeyboardButton("❌ Reject",
                                     callback_data=f"reject:{order_code}"),
            ]
        ]
    )


def wallet_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("💠 Top up via Binance",
                                  callback_data="topup:binance")],
            [InlineKeyboardButton("🪙 Top up via USDT (BEP20)",
                                  callback_data="topup:usdt")],
        ]
    )
