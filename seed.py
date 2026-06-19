"""Populate the store with sample products & stock for a quick demo.

Run once after configuring .env:  python seed.py
Safe to run multiple times — it skips products that already exist by name.
"""
import database as db

SAMPLE_PRODUCTS = [
    {
        "emoji": "🚀",
        "name": "Admin Ultra Antigravity X20 5slot 25000 Credit 30D 5D warranty",
        "price": 80.0,
        "description": "Higher agent limits, multi-model access, AI credits, fast workflows.",
        "image_url": "",
        "stock": [
            "login: ultra1@mail.com | pass: Ax93kLp02",
            "login: ultra2@mail.com | pass: Bz71mQr48",
            "login: ultra3@mail.com | pass: Cy55nTs19",
        ],
    },
    {
        "emoji": "❌",
        "name": "GPT PLUS 30D has full warranty",
        "price": 8.75,
        "description": "ChatGPT Plus 30 days, full warranty.",
        "image_url": "",
        "stock": ["gptplus-key-AAA111", "gptplus-key-BBB222"],
    },
    {
        "emoji": "🌟",
        "name": "SLOT CLAUDE PRO 1 MONTH full warranty",
        "price": 12.0,
        "description": "Claude Pro slot, 1 month, full warranty.",
        "image_url": "",
        "stock": ["claudepro-slot-001", "claudepro-slot-002"],
    },
    {
        "emoji": "🌟",
        "name": "SLOT CLAUDE MAX X5 1 MONTH full warranty",
        "price": 35.0,
        "description": "Claude Max x5 slot, 1 month, full warranty.",
        "image_url": "",
        "stock": ["claudemax-slot-001"],
    },
    {
        "emoji": "🤖",
        "name": "API DeepSeek V4 Pro-1B Token 30 days full warranty",
        "price": 15.0,
        "description": "DeepSeek V4 Pro API, 1B tokens, 30 days.",
        "image_url": "",
        "stock": ["deepseek-api-key-XYZ987"],
    },
]


def main() -> None:
    db.init_db()
    existing = {p["name"] for p in db.list_products(active_only=False)}
    for item in SAMPLE_PRODUCTS:
        if item["name"] in existing:
            print(f"• Skipping existing: {item['name'][:40]}…")
            continue
        pid = db.add_product(
            name=item["name"],
            price=item["price"],
            emoji=item["emoji"],
            description=item["description"],
            image_url=item["image_url"],
        )
        added = db.add_stock_items(pid, item["stock"])
        print(f"✓ Added #{pid} {item['emoji']} {item['name'][:40]}… (+{added} stock)")
    print("\nDone. Start the bot with: python bot.py")


if __name__ == "__main__":
    main()
