import asyncio
import aiosqlite
from aiogram import Bot, Dispatcher, Router
from aiogram.filters import Command
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardRemove, WebAppInfo
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from dotenv import load_dotenv
from urllib.parse import urlencode
import os

# === .ENV ===
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
WEBAPP_URL = os.getenv("WEBAPP_URL")
COMMISSION = float(os.getenv("COMMISSION", "0.15"))
DB_NAME = os.getenv("DB_NAME", "earn_bot.db")
MIN_WITHDRAW = float(os.getenv("MIN_WITHDRAW", "50"))

if not BOT_TOKEN or not ADMIN_ID or not WEBAPP_URL:
    raise ValueError("BOT_TOKEN, ADMIN_ID и WEBAPP_URL обязательны в .env!")

# === ИНИЦИАЛИЗАЦИЯ ===
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
router = Router()
dp.include_router(router)

# === FSM ===
class TaskStates(StatesGroup):
    waiting_text = State()
    waiting_link = State()
    waiting_price = State()

class WithdrawStates(StatesGroup):
    waiting_wallet = State()
    waiting_amount = State()

# === БД ===
async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                role TEXT,
                balance REAL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                employer_id INTEGER,
                text TEXT,
                link TEXT,
                price REAL,
                status TEXT DEFAULT 'active',
                executor_id INTEGER,
                proof_photo TEXT
            );
            CREATE TABLE IF NOT EXISTS withdrawals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                amount REAL,
                wallet TEXT,
                status TEXT DEFAULT 'pending'
            );
        """)
        await db.commit()

# === УТИЛИТЫ ===
async def get_role(user_id):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT role FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None

async def set_role(user_id, role):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT OR REPLACE INTO users (user_id, role) VALUES (?, ?)", (user_id, role))
        await db.commit()

async def add_balance(user_id, amount):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
        await db.commit()

async def get_balance(user_id):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0.0

# === /start — ПЕРЕДАЁТ user_id и role В ПРИЛОЖЕНИЕ ===
@router.message(Command("start"))
async def start(message: Message):
    user_id = message.from_user.id
    role = await get_role(user_id)

    # Передаём user_id и role в URL
    params = {
        "user_id": user_id,
        "role": role or "none"
    }
    webapp_url = f"{WEBAPP_URL}?{urlencode(params)}"

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text="Открыть ReviewCash",
                web_app=WebAppInfo(url=webapp_url)
            )]
        ]
    )

    await message.answer(
        "Нажми, чтобы открыть приложение:",
        reply_markup=keyboard
    )

# === УСТАНОВКА РОЛИ ИЗ ПРИЛОЖЕНИЯ (опционально) ===
@router.message(Command(commands=["setrole_employer", "setrole_executor"]))
async def set_role_from_webapp(message: Message):
    role = message.text.split("_")[1]
    await set_role(message.from_user.id, role)
    await message.answer("Роль сохранена!")

# === Создание задания ===
@router.message(Command("newtask"))
async def newtask(message: Message, state: FSMContext):
    if await get_role(message.from_user.id) != "employer":
        await message.answer("Только работодатели!")
        return
    await message.answer("Опиши задание:")
    await state.set_state(TaskStates.waiting_text)

@router.message(TaskStates.waiting_text)
async def task_text(message: Message, state: FSMContext):
    await state.update_data(text=message.text)
    await message.answer("Ссылка:")
    await state.set_state(TaskStates.waiting_link)

@router.message(TaskStates.waiting_link)
async def task_link(message: Message, state: FSMContext):
    await state.update_data(link=message.text)
    await message.answer("Цена (в рублях):")
    await state.set_state(TaskStates.waiting_price)

@router.message(TaskStates.waiting_price)
async def task_price(message: Message, state: FSMContext):
    try:
        price = float(message.text)
        if price < 1:
            raise ValueError
    except:
        await message.answer("Цена должна быть числом > 1")
        return

    data = await state.get_data()
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "INSERT INTO tasks (employer_id, text, link, price) VALUES (?, ?, ?, ?)",
            (message.from_user.id, data['text'], data['link'], price)
        )
        await db.commit()

    await message.answer(f"Задание создано! Цена: {price} ₽")
    await state.clear()

# === Список заданий ===
@router.message(Command("tasks"))
async def tasks_list(message: Message):
    if await get_role(message.from_user.id) != "executor":
        await message.answer("Только исполнители!")
        return

    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT id, text, price FROM tasks WHERE status = 'active'") as cursor:
            rows = await cursor.fetchall()

    if not rows:
        await message.answer("Нет заданий")
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[])
    for task_id, text, price in rows:
        short = (text[:40] + "...") if len(text) > 40 else text
        keyboard.inline_keyboard.append([
            InlineKeyboardButton(text=f"{short} — {price} ₽", callback_data=f"take_{task_id}")
        ])

    await message.answer("Доступные задания:", reply_markup=keyboard)

@router.callback_query(lambda c: c.data and c.data.startswith("take_"))
async def take_task(callback: CallbackQuery):
    task_id = int(callback.data.split("_")[1])
    user_id = callback.from_user.id

    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT status, executor_id FROM tasks WHERE id = ?", (task_id,)) as cursor:
            row = await cursor.fetchone()
        if not row or row[0] != "active":
            await callback.answer("Задание уже взято!", show_alert=True)
            return
        if row[1]:
            await callback.answer("Кто-то быстрее!", show_alert=True)
            return

        await db.execute("UPDATE tasks SET status = 'in_progress', executor_id = ? WHERE id = ?", (user_id, task_id))
        await db.commit()

    await callback.message.edit_text(f"Ты взял задание #{task_id}\nПришли фото:")
    await callback.answer()

# === Фото-доказательство ===
@router.message(lambda m: m.photo)
async def proof_photo(message: Message):
    user_id = message.from_user.id
    photo = message.photo[-1].file_id

    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT id FROM tasks WHERE executor_id = ? AND status = 'in_progress'", (user_id,)) as cursor:
            row = await cursor.fetchone()
        if not row:
            return
        task_id = row[0]
        await db.execute("UPDATE tasks SET status = 'checking', proof_photo = ? WHERE id = ?", (photo, task_id))
        await db.commit()

    await message.answer("Доказательство отправлено!")
    await bot.send_photo(
        ADMIN_ID, photo,
        caption=f"Задание #{task_id}\nИсполнитель: {user_id}\n\n"
                f"Одобрить: /approve_{task_id}\nОтклонить: /reject_{task_id}"
    )

# === Админка ===
@router.message(Command("admin"))
async def admin_panel(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer("Админка: жди фото")

@router.message(Command(commands=["approve_", "reject_"]))
async def admin_decision(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    cmd = message.text.split("_")[0][1:]
    task_id = int(message.text.split("_")[1])

    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT executor_id, price FROM tasks WHERE id = ?", (task_id,)) as cursor:
            row = await cursor.fetchone()
        if not row:
            await message.answer("Не найдено")
            return
        executor_id, price = row

        if cmd == "approve":
            reward = price * (1 - COMMISSION)
            await add_balance(executor_id, reward)
            await db.execute("UPDATE tasks SET status = 'done' WHERE id = ?", (task_id,))
            await message.answer(f"Одобрено! +{reward:.2f} ₽")
            await bot.send_message(executor_id, f"Задание #{task_id} одобрено!\n+{reward:.2f} ₽")
        else:
            await db.execute("UPDATE tasks SET status = 'rejected' WHERE id = ?", (task_id,))
            await message.answer("Отклонено")
            await bot.send_message(executor_id, f"Задание #{task_id} отклонено.")

        await db.commit()

# === Баланс и вывод ===
@router.message(Command("balance"))
async def balance_cmd(message: Message):
    bal = await get_balance(message.from_user.id)
    await message.answer(f"Баланс: *{bal:.2f} ₽*")

@router.message(Command("withdraw"))
async def withdraw_cmd(message: Message, state: FSMContext):
    if await get_role(message.from_user.id) != "executor":
        await message.answer("Только исполнители!")
        return
    bal = await get_balance(message.from_user.id)
    if bal < MIN_WITHDRAW:
        await message.answer(f"Минимум {MIN_WITHDRAW} ₽")
        return
    await message.answer("Кошелёк (Qiwi):")
    await state.set_state(WithdrawStates.waiting_wallet)

@router.message(WithdrawStates.waiting_wallet)
async def withdraw_wallet(message: Message, state: FSMContext):
    await state.update_data(wallet=message.text)
    await message.answer("Сумма:")
    await state.set_state(WithdrawStates.waiting_amount)

@router.message(WithdrawStates.waiting_amount)
async def withdraw_amount(message: Message, state: FSMContext):
    try:
        amount = float(message.text)
    except:
        await message.answer("Только число")
        return
    bal = await get_balance(message.from_user.id)
    if amount > bal or amount < MIN_WITHDRAW:
        await message.answer(f"От {MIN_WITHDRAW} до {bal}")
        return

    data = await state.get_data()
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT INTO withdrawals (user_id, amount, wallet) VALUES (?, ?, ?)",
                        (message.from_user.id, amount, data['wallet']))
        await db.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (amount, message.from_user.id))
        await db.commit()

    await message.answer(f"Заявка: {amount} ₽ → {data['wallet']}")
    await bot.send_message(ADMIN_ID, f"Вывод: {amount} ₽\nКошелёк: {data['wallet']}\nID: {message.from_user.id}")
    await state.clear()

# === ЗАПУСК ===
async def main():
    await init_db()
    print(f"Бот запущен | Админ: {ADMIN_ID}")
    print(f"Мини-приложение: {WEBAPP_URL}")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
