"""
ReelsAI Bot — Telegram бот с генератором идей для Reels
Установка: pip install python-telegram-bot anthropic
"""

import logging
import asyncio
import json
import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ConversationHandler, filters, ContextTypes
)
from telegram.constants import ParseMode, ChatAction
import anthropic

# ── НАСТРОЙКИ ── замени на свои ──────────────────────────────
BOT_TOKEN     = "ВАШ_TELEGRAM_BOT_TOKEN"
ANTHROPIC_KEY = "ВАШ_ANTHROPIC_API_KEY"
CODEWORD      = "СТАРТ"          # кодовое слово из Reels
SITE_URL      = "https://neurocreator2.ru"
# ─────────────────────────────────────────────────────────────

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# Состояния диалога
ASK_NICHE, ASK_GOAL, ASK_AUD = range(3)

GOALS = ["Подписчики", "Продажи", "Охваты", "Заявки", "Доверие"]
AUDS  = ["Новички", "Средний уровень", "Профессионалы"]


# ── Генерация — sync функция в thread pool ────────────────────
def _generate_sync(niche: str, goal: str, aud: str) -> list[dict]:
    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)

    prompt = f"""Ты эксперт по вирусному контенту в Instagram Reels и TikTok.

Создай ровно 7 уникальных идей для Reels:
- Ниша: {niche}
- Цель: {goal}
- Аудитория: {aud}

Для каждой идеи укажи:
1. hook — цепляющая фраза первых 3 секунд (конкретная, без воды)
2. format — один из: Разоблачение / Инструкция / История / Провокация / Лайфхак / Топ-список / Кейс / Ошибки / Сравнение
3. structure — что происходит в ролике (2 предложения)
4. viral — одна причина виральности

ТОЛЬКО JSON массив, без markdown, без пояснений:
[{{"hook":"...","format":"...","structure":"...","viral":"..."}}]"""

    response = client.messages.create(
        model="claude-3-7-sonnet-latest",
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}]
    )
    text = response.content[0].text.strip()
    text = re.sub(r"```json|```", "", text).strip()
    return json.loads(text)


async def generate_ideas(niche: str, goal: str, aud: str) -> list[dict]:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _generate_sync, niche, goal, aud)


# ── Форматирование ────────────────────────────────────────────
def format_idea(idea: dict, num: int) -> str:
    return (
        f"✦ *ИДЕЯ {num:02d} · {idea['format'].upper()}*\n\n"
        f"🎯 *Хук:*\n_{idea['hook']}_\n\n"
        f"📹 *Структура:*\n{idea['structure']}\n\n"
        f"🔥 _{idea['viral']}_"
    )


# ── ХЭНДЛЕРЫ ─────────────────────────────────────────────────

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🔑 *Привет! Держи доступ к бесплатному уроку.*\n\n"
        "А пока — сгенерируем идеи для твоих Reels 🚀\n\n"
        "Напиши свою *нишу или тему блога*\n"
        "_Например: фитнес, психология, AI-контент..._",
        parse_mode=ParseMode.MARKDOWN,
    )
    return ASK_NICHE


async def ask_niche(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["niche"] = update.message.text.strip()
    keyboard = [[InlineKeyboardButton(g, callback_data=f"goal:{g}")] for g in GOALS]
    await update.message.reply_text(
        "🎯 *Какая цель роликов?*",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN,
    )
    return ASK_GOAL


async def ask_goal(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    ctx.user_data["goal"] = query.data.split(":")[1]
    await query.edit_message_text(f"✅ Цель: *{ctx.user_data['goal']}*", parse_mode=ParseMode.MARKDOWN)

    keyboard = [[InlineKeyboardButton(a, callback_data=f"aud:{a}")] for a in AUDS]
    await query.message.reply_text(
        "👥 *Кто твоя аудитория?*",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN,
    )
    return ASK_AUD


async def ask_aud(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    ctx.user_data["aud"] = query.data.split(":")[1]
    await query.edit_message_text(f"✅ Аудитория: *{ctx.user_data['aud']}*", parse_mode=ParseMode.MARKDOWN)

    niche   = ctx.user_data["niche"]
    goal    = ctx.user_data["goal"]
    aud     = ctx.user_data["aud"]
    chat_id = query.message.chat_id

    msg = await query.message.reply_text(
        "🤖 *Генерирую 7 идей...*\n_Обычно занимает 10–15 секунд_",
        parse_mode=ParseMode.MARKDOWN,
    )
    await ctx.bot.send_chat_action(chat_id, ChatAction.TYPING)

    try:
        ideas = await generate_ideas(niche, goal, aud)
        await msg.delete()

        await ctx.bot.send_message(
            chat_id,
            f"✨ *7 идей для Reels готовы!*\nНиша: _{niche}_ · Цель: _{goal}_",
            parse_mode=ParseMode.MARKDOWN,
        )

        for i, idea in enumerate(ideas, 1):
            await ctx.bot.send_message(chat_id, format_idea(idea, i), parse_mode=ParseMode.MARKDOWN)
            await asyncio.sleep(0.4)

        keyboard = [[
            InlineKeyboardButton("🎓 Бесплатный урок →", url=SITE_URL),
            InlineKeyboardButton("🔄 Ещё идеи", callback_data="restart"),
        ]]
        await ctx.bot.send_message(
            chat_id,
            "💡 *Хочешь систему, а не просто идеи?*\n\n"
            "Узнай как AI-контент приносит *100–300К₽ в месяц* — без рекламы и бюджета.",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN,
        )

    except json.JSONDecodeError as e:
        logger.error(f"JSON error: {e}")
        await msg.edit_text("⚠️ Ошибка формата. Попробуй /start")
    except Exception as e:
        logger.error(f"Error: {e}")
        await msg.edit_text(f"⚠️ Ошибка: {str(e)[:120]}\n\nПопробуй /start")

    return ConversationHandler.END


async def restart_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text("Напиши нишу для новых идей:")
    return ASK_NICHE


async def codeword_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip().upper()
    if CODEWORD.upper() in text:
        return await start(update, ctx)


async def cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Отменено. Напиши /start чтобы начать заново.")
    return ConversationHandler.END


# ── ЗАПУСК ───────────────────────────────────────────────────
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            MessageHandler(filters.TEXT & ~filters.COMMAND, codeword_handler),
        ],
        states={
            ASK_NICHE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_niche)],
            ASK_GOAL:  [CallbackQueryHandler(ask_goal, pattern="^goal:")],
            ASK_AUD:   [CallbackQueryHandler(ask_aud, pattern="^aud:")],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CallbackQueryHandler(restart_handler, pattern="^restart$"),
        ],
        allow_reentry=True,
    )

    app.add_handler(conv)
    logger.info("✓ Бот запущен")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
