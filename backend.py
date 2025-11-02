from flask import Flask, request, jsonify
import aiosqlite
import asyncio

app = Flask(__name__)
DB = "earn_bot.db"
ADMIN_ID = 123456789
COMMISSION = 0.15

async def db_query(query, params=(), fetch=False):
    async with aiosqlite.connect(DB) as db:
        cursor = await db.execute(query, params)
        if fetch:
            return await cursor.fetchall()
        await db.commit()

@app.route('/get_user', methods=['POST'])
def get_user():
    data = request.json
    user_id = data['userId']
    loop = asyncio.get_event_loop()
    role = loop.run_until_complete(db_query("SELECT role, balance FROM users WHERE user_id = ?", (user_id,), True))
    if not role:
        loop.run_until_complete(db_query("INSERT INTO users (user_id, balance) VALUES (?, 0)", (user_id,)))
        return jsonify({"role": None, "balance": 0})
    return jsonify({"role": role[0][0], "balance": role[0][1]})

@app.route('/set_role', methods=['POST'])
def set_role():
    data = request.json
    loop = asyncio.get_event_loop()
    loop.run_until_complete(db_query("UPDATE users SET role = ? WHERE user_id = ?", (data['role'], data['userId'])))
    return jsonify({"ok": True})

# ... остальные маршруты (create_task, get_tasks, take_task, withdraw) — по аналогии с ботом

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
