"""
Телеграм-бот: расписание 10а + домашнее задание.

Запуск:
  pip install "python-telegram-bot[job-queue]"
  export BOT_TOKEN="токен от @BotFather"     (Windows: set BOT_TOKEN=токен)
  python bot.py

Потом открой бота в Телеграме и нажми /start.
Каждый день в 16:00 бот пришлёт расписание на завтра вместе с ДЗ.
"""
import json
import os
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from telegram import (InlineKeyboardButton, InlineKeyboardMarkup,
                      ReplyKeyboardMarkup, Update)
from telegram.ext import (Application, CallbackQueryHandler, CommandHandler,
                          ContextTypes, MessageHandler, filters)

TOKEN = os.environ["BOT_TOKEN"]
TZ = ZoneInfo("Asia/Yekaterinburg")
SEND_TIME = time(16, 0, tzinfo=TZ)
DB_FILE = "data.json"

# 0 = понедельник ... 4 = пятница. (время, предмет, кабинет)
SCHEDULE = {
    0: [("7:50", "Разговоры о важном", ""), ("8:30", "Химия", "304"),
        ("9:20–10:55", "Информатика", "216/218"), ("11:10", "Англ.яз", ""),
        ("12:00–13:45", "Рус.яз", "217"), ("14:10", "Литература", "217")],
    1: [("8:30", "Обществознание", "303"), ("9:20", "Физика", "311"),
        ("10:15–11:50", "Информатика", "216/218"),
        ("12:00–13:45", "Математика", "315"),
        ("14:10", "Инд.проект", "208")],
    2: [("8:30", "Обществознание", "303"), ("9:20", "Англ.яз", ""),
        ("10:15–11:50", "Математика", "315"),
        ("12:00–13:45", "Литература", "217"),
        ("14:10", "Родной язык / Гос.башкирский", "")],
    3: [("7:50", "Профминимум", ""), ("8:30", "Инд.проект", "208"),
        ("9:20", "Родная литература", ""),
        ("10:15–11:50", "История", "303"), ("12:00", "Физика", "311"),
        ("13:05–14:50", "Математика", "317")],
    4: [("8:30–10:00", "Математика", "315"), ("10:15", "ОБЗР", "303"),
        ("11:10", "География", "208"), ("12:00", "Англ.яз", ""),
        ("13:05", "Биология", "305"), ("14:10", "Физкультура", "спортзал"),
        ("15:00", "Внеурочная физра", "")],
}
NO_HW = {"Разговоры о важном", "Профминимум", "Внеурочная физра"}
SUBJECTS = sorted({l[1] for day in SCHEDULE.values() for l in day} - NO_HW)
DAYS = ["понедельник", "вторник", "среда", "четверг", "пятница",
        "суббота", "воскресенье"]

MENU = ReplyKeyboardMarkup(
    [["📅 Сегодня", "📅 Завтра"], ["➕ Добавить ДЗ", "📚 Всё ДЗ"]],
    resize_keyboard=True)


# ---------- хранилище ----------
def load():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {"chats": [], "hw": []}


def save(db):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=1)


def today():
    return datetime.now(TZ).date()


def next_lesson_date(subject):
    """Ближайший день (начиная с завтра), когда есть этот предмет."""
    for i in range(1, 15):
        d = today() + timedelta(days=i)
        if any(l[1] == subject for l in SCHEDULE.get(d.weekday(), [])):
            return d


# ---------- текст расписания ----------
def day_text(d: date):
    lessons = SCHEDULE.get(d.weekday(), [])
    head = f"📅 {DAYS[d.weekday()].capitalize()}, {d:%d.%m}"
    if not lessons:
        return head + "\nУроков нет 🎉"
    hw = [h for h in load()["hw"] if h["date"] == d.isoformat()]
    lines = [head]
    for t, subj, room in lessons:
        lines.append(f"{t} — {subj}" + (f" ({room})" if room else ""))
        for h in hw:
            if h["subject"] == subj:
                lines.append(f"   📝 {h['text']}")
    return "\n".join(lines)


def all_hw_text():
    items = [h for h in load()["hw"] if h["date"] >= today().isoformat()]
    if not items:
        return "ДЗ пока нет ✅"
    items.sort(key=lambda h: h["date"])
    lines, cur = ["📚 Всё домашнее задание"], None
    for h in items:
        if h["date"] != cur:
            cur = h["date"]
            d = date.fromisoformat(cur)
            lines.append(f"\n{DAYS[d.weekday()].capitalize()}, {d:%d.%m}:")
        lines.append(f"• {h['subject']}: {h['text']}")
    return "\n".join(lines)


# ---------- обработчики ----------
def schedule_daily(app, chat_id):
    for j in app.job_queue.get_jobs_by_name(str(chat_id)):
        j.schedule_removal()
    app.job_queue.run_daily(send_tomorrow, SEND_TIME, chat_id=chat_id,
                            name=str(chat_id))


async def send_tomorrow(ctx: ContextTypes.DEFAULT_TYPE):
    d = today() + timedelta(days=1)
    if SCHEDULE.get(d.weekday()):
        await ctx.bot.send_message(ctx.job.chat_id, day_text(d))


async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    db = load()
    cid = update.effective_chat.id
    if cid not in db["chats"]:
        db["chats"].append(cid)
        save(db)
    schedule_daily(ctx.application, cid)
    await update.message.reply_text(
        "Привет! Каждый день в 16:00 пришлю расписание на завтра с ДЗ.",
        reply_markup=MENU)


async def on_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    t = update.message.text
    if t == "📅 Сегодня":
        await update.message.reply_text(day_text(today()))
    elif t == "📅 Завтра":
        await update.message.reply_text(day_text(today() + timedelta(days=1)))
    elif t == "📚 Всё ДЗ":
        await update.message.reply_text(all_hw_text())
    elif t == "➕ Добавить ДЗ":
        ctx.user_data.pop("subj", None)
        rows = [SUBJECTS[i:i + 2] for i in range(0, len(SUBJECTS), 2)]
        kb = [[InlineKeyboardButton(s, callback_data=f"s{SUBJECTS.index(s)}")
               for s in row] for row in rows]
        await update.message.reply_text(
            "Выбери предмет:", reply_markup=InlineKeyboardMarkup(kb))
    elif "subj" in ctx.user_data:
        subj = ctx.user_data.pop("subj")
        d = next_lesson_date(subj)
        db = load()
        db["hw"].append({"subject": subj, "text": t, "date": d.isoformat()})
        save(db)
        await update.message.reply_text(
            f"Записал: {subj} на {DAYS[d.weekday()]}, {d:%d.%m} ✅",
            reply_markup=MENU)
    else:
        await update.message.reply_text("Выбери действие в меню 👇",
                                        reply_markup=MENU)


async def on_subject(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    subj = SUBJECTS[int(q.data[1:])]
    ctx.user_data["subj"] = subj
    await q.edit_message_text(f"{subj}. Напиши, что задали:")


def main():
    app = Application.builder().token(TOKEN).build()
    for cid in load()["chats"]:
        schedule_daily(app, cid)
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(on_subject, pattern=r"^s\d+$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    app.run_polling()


if __name__ == "__main__":
    main()
