# 🛍️ Telegram Auto-Order Bot

A self-serve digital-goods store for Telegram — buyers browse products, pick a
quantity, pay (Wallet / Binance / USDT BEP20) and receive their items
**automatically**. Inspired by stores like `GPTCheap_bot`.

![menu](https://img.shields.io/badge/menu-Products%20%C2%B7%20Support%20%C2%B7%20Wallet%20%C2%B7%20API-blue)

## ✨ Features

- **Product catalog** with emoji, image, price, live stock & sold counts
- **Buy flow**: pick product → enter quantity (1–N) → choose payment method
- **Payments**:
  - 💰 **Wallet** — instant, auto-delivered from balance
  - 💠 **Binance** — shows Binance ID, buyer submits reference, admin approves
  - 🪙 **USDT (BEP20)** — shows deposit address, same review flow
- **Automatic delivery** of stock (one stock line = one delivered unit)
- **Wallet** with balance + transaction history and top-up instructions
- **Order tracking** with unique order codes (e.g. `ORDERZOQZ8QCCP9Q`)
- **Admin panel**: add/list/disable products, add stock, review payments,
  set balances, broadcast
- **SQLite** storage — zero external services required

## 🚀 Quick start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure
cp .env.example .env
# edit .env: set BOT_TOKEN (from @BotFather) and ADMIN_IDS (your Telegram ID)

# 3. (optional) Load demo products
python seed.py

# 4. Run
python bot.py
```

## ⚙️ Configuration (`.env`)

| Variable             | Description                                   |
|----------------------|-----------------------------------------------|
| `BOT_TOKEN`          | Bot token from @BotFather (**required**)      |
| `ADMIN_IDS`          | Comma-separated admin user IDs (**required**) |
| `STORE_NAME`         | Store name shown in messages                  |
| `SUPPORT_USERNAME`   | Support contact handle                        |
| `BINANCE_ID`         | Binance Pay ID shown to buyers                |
| `USDT_BEP20_ADDRESS` | USDT BEP20 deposit address                    |
| `CURRENCY`           | Currency symbol (default `$`)                 |
| `MAX_QUANTITY_PER_ORDER` | Max units per order (default `3`)         |
| `DB_PATH`            | SQLite file path (default `data/store.db`)    |

## 👤 Buyer experience

The bottom menu mirrors the reference bot: **🛍️ Products · 💬 Support · 👛 Wallet · 🔗 API**.

1. Tap **🛍️ Products** → choose a product → **🛒 Buy now**
2. Enter quantity → choose **Wallet / Binance / USDT**
3. Wallet pays instantly; off-chain methods show payment details and a
   **Submit payment reference** button. After review, items are delivered.

## 🛠️ Admin commands

| Command | Purpose |
|---------|---------|
| `/admin` | Dashboard + command reference |
| `/addproduct Emoji \| Name \| Price \| Description \| ImageURL` | Add a product |
| `/addstock <product_id>` | Then send stock items, one per line |
| `/products` | List products with stock & sold |
| `/delproduct <id>` | Deactivate a product |
| `/orders [pending]` | Recent orders (or those awaiting review) |
| `/approve <ORDER_CODE>` / `/reject <ORDER_CODE>` | Confirm/decline off-chain payments |
| `/setbalance <user_id> <amount>` | Set a user's wallet balance |
| `/broadcast <message>` | Message all users |

Admins also get inline **✅ Approve & deliver / ❌ Reject** buttons on each
payment-review notification.

## 🧱 Project layout

```
bot.py        # handlers, flows, admin commands, app bootstrap
database.py   # SQLite schema + data access (users, products, stock, orders)
keyboards.py  # reply & inline keyboards
config.py     # env-based configuration
seed.py       # optional demo data
```

## 📝 Notes

- Off-chain payments use a manual review step (buyer submits a reference,
  admin approves) — no third-party payment API keys are required. You can wire
  a real Binance / on-chain verification into `handle_txref_input` later.
- All amounts are stored as plain floats; for high-volume production use,
  consider integer minor-units.
