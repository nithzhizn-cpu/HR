"""
Telegram Bot — AI HR Psychologist (Multi-tests, extended)
---------------------------------------------------------
Можливості:
  - /start — реєстрація кандидата, збереження ПІБ
  - /tests — вибір тестів (Big Five, MBTI, Белбін, EQ, Пономаренко)
  - проходження тестів (розширені, 10–16 питань)
  - /voice — голосовий аналіз стресу
  - /photo — аналіз фото (настрій/втома)
  - /help — довідка
"""

import os
import logging
from io import BytesIO
from typing import Dict, Any

import aiohttp
from aiogram import Bot, Dispatcher, executor, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup

API_TOKEN = os.getenv("BOT_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN")
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot, storage=MemoryStorage())

tg_to_candidate: Dict[int, int] = {}


TESTS: Dict[str, Dict[str, Any]] = {
    "bigfive": {
        "title": "Big Five (OCEAN, розширений)",
        "description": "5-факторна модель особистості. Відповідай 1–5.",
        "questions": [
            "Я люблю пробувати нове, мені цікаві незнайомі ідеї.",
            "Я відповідальний(а), доводжу справи до кінця.",
            "Я легко знайомлюсь, мені подобається бути серед людей.",
            "Я зазвичай ввічливий(а) і враховую почуття інших.",
            "Мене часто важко вивести з рівноваги.",
            "Мені подобається планувати наперед і все організовувати.",
            "Я охоче висловлюю свої думки в компанії.",
            "Я можу відчувати тривогу через дрібниці.",
            "Я люблю творчі, нестандартні задачі.",
            "Я схильний(а) довіряти людям.",
            "Я відчуваю себе комфортно у незнайомих місцях.",
            "Мені важливо, щоб усе було зроблено якісно та без помилок.",
            "Я люблю бути в центрі уваги.",
            "Я намагаюся уникати конфліктів і зберігати гарні стосунки.",
            "Мені важко швидко заспокоїтися після стресу.",
            "Я часто шукаю нові враження та досвід.",
        ],
    },
    "mbti": {
        "title": "MBTI (скорочений, розширений)",
        "description": "Орієнтовний тип за 4 дихотоміями. Відповідай 1–5.",
        "questions": [
            "Мені комфортніше в гучних компаніях, ніж наодинці.",
            "Я радше спираюсь на факти, ніж на інтуїцію.",
            "У конфліктах я більше керуюсь логікою, ніж почуттями.",
            "Я люблю чітко планувати та дотримуватися плану.",
            "Я швидко заводжу нові знайомства.",
            "Я часто покладаюся на внутрішні відчуття, а не тільки на досвід.",
            "Я боюся образити інших, навіть якщо треба сказати неприємну правду.",
            "Мені комфортно, коли плани можуть змінюватись спонтанно.",
            "Я заряджаюсь енергією від спілкування з людьми.",
            "Мені важко працювати без конкретних інструкцій.",
            "Я часто аналізую, чому люди поводяться певним чином.",
            "Я радше виконаю задачу за схемою, ніж імпровізуватиму.",
        ],
    },
    "belbin": {
        "title": "Командні ролі Белбіна (короткий профіль)",
        "description": "Які ролі тобі ближчі в команді. 1–5.",
        "questions": [
            "Я часто пропоную нові, нестандартні ідеї на роботі.",
            "Я люблю організовувати людей і розподіляти задачі.",
            "Я отримую задоволення від того, що доводжу проєкти до кінця.",
            "Я намагаюся підтримувати добру атмосферу в колективі.",
            "Я можу побачити ризики та слабкі місця в плані.",
            "Я легко знаходжу контакти та ресурси для команди.",
            "Я люблю працювати з деталями та інструкціями.",
            "Я часто виступаю посередником у конфліктах між колегами.",
            "Я можу довго працювати над реалізацією, навіть якщо задача рутинна.",
            "Я уважно слухаю інших та враховую їхні думки.",
        ],
    },
    "eq": {
        "title": "Емоційний інтелект (EQ, короткий профіль)",
        "description": "Оціни своє ставлення до емоцій. 1–5.",
        "questions": [
            "Я добре розумію, що саме зараз відчуваю.",
            "Мені вдається стримувати емоції, коли це потрібно.",
            "Я зауважую, коли іншим некомфортно, навіть якщо вони мовчать.",
            "Мені легко зав’язувати та підтримувати стосунки з людьми.",
            "Я можу пояснити, чому я так відреагував(ла) у тій чи іншій ситуації.",
            "Навіть у конфлікті я здатен(на) контролювати свій тон та поведінку.",
            "Я намагаюсь подивитись на ситуацію очима іншої людини.",
            "Я комфортно почуваюся у великих соціальних подіях.",
            "Я швидко помічаю зміни у своєму настрої.",
            "Я вмію заспокоїти себе, коли відчуваю сильні емоції.",
        ],
    },
    "ponomarenko": {
        "title": "Радикали (Пономаренко, дуже скорочено)",
        "description": "Оціни своє типове поводження. 1–5.",
        "questions": [
            "Я часто беру на себе керівну роль, навіть якщо мене про це не просять.",
            "Якщо мене зачепили, я можу різко відреагувати.",
            "Я часто хвилююся за майбутнє та можливі проблеми.",
            "Мені важливо, щоб люди мене схвалювали та приймали.",
            "Я люблю, коли все під контролем і за правилами.",
            "Я можу різко сказати правду, не думаючи, як це сприймуть.",
            "Я легко заводжу знайомства, люблю бути “в центрі подій”.",
            "Я гостро переживаю невдачі та критику.",
            "Я не люблю, коли мною керують, віддаю перевагу самостійності.",
            "Я можу бути дуже емоційним(ою) у напружених ситуаціях.",
        ],
    },
}


class RegisterState(StatesGroup):
    waiting_for_name = State()


class TestFlow(StatesGroup):
    choosing_test = State()
    answering = State()


class VoiceState(StatesGroup):
    waiting_for_voice = State()


class PhotoState(StatesGroup):
    waiting_for_photo = State()


async def backend_start_candidate(user: types.User, full_name: str) -> int:
    async with aiohttp.ClientSession() as session:
        payload = {"tg_id": user.id, "full_name": full_name}
        async with session.post(f"{BACKEND_URL}/api/candidate/start_test", json=payload) as resp:
            data = await resp.json()
            if resp.status != 200:
                raise RuntimeError(f"Backend error: {data}")
    return int(data["candidate_id"])


async def backend_submit_test(candidate_id: int, test_type: str, answers: list[int]) -> dict:
    async with aiohttp.ClientSession() as session:
        payload = {
            "candidate_id": candidate_id,
            "test_type": test_type,
            "answers": answers,
        }
        async with session.post(f"{BACKEND_URL}/api/candidate/submit_test", json=payload) as resp:
            data = await resp.json()
            if resp.status != 200:
                raise RuntimeError(f"Backend error: {data}")
    return data


@dp.message_handler(commands=["start"])
async def cmd_start(message: types.Message, state: FSMContext):
    await state.finish()
    await message.answer(
        "Привіт! Я AI-помічник для психологічного аналізу.\n\n"
        "Напиши, будь ласка, своє ім'я та прізвище (як тебе буде бачити HR)."
    )
    await RegisterState.waiting_for_name.set()


@dp.message_handler(state=RegisterState.waiting_for_name)
async def process_name(message: types.Message, state: FSMContext):
    full_name = message.text.strip()
    if not full_name:
        await message.answer("Будь ласка, напиши хоча б ім'я.")
        return

    try:
        candidate_id = await backend_start_candidate(message.from_user, full_name)
    except Exception as e:
        logger.exception("start_candidate failed: %s", e)
        await message.answer("Помилка підключення до сервера. Спробуй пізніше.")
        await state.finish()
        return

    tg_to_candidate[message.from_user.id] = candidate_id
    await state.finish()

    await message.answer(
        f"Дякую, {full_name}.\n\n"
        "Тепер ти можеш обрати, які тести пройти, командою /tests.\n"
        "Також доступні /voice (голосовий аналіз) та /photo (аналіз фото)."
    )


@dp.message_handler(commands=["tests"])
async def cmd_tests(message: types.Message, state: FSMContext):
    if message.from_user.id not in tg_to_candidate:
        await message.answer("Спочатку виконай /start, щоб зареєструватись.")
        return

    kb = types.InlineKeyboardMarkup()
    for code, meta in TESTS.items():
        kb.add(
            types.InlineKeyboardButton(
                text=meta["title"],
                callback_data=f"test:{code}",
            )
        )

    await message.answer(
        "Оберіть тест, який хочете пройти (можна кілька по черзі):",
        reply_markup=kb,
    )
    await TestFlow.choosing_test.set()


@dp.callback_query_handler(lambda c: c.data.startswith("test:"), state=TestFlow.choosing_test)
async def on_test_chosen(callback: types.CallbackQuery, state: FSMContext):
    code = callback.data.split(":", 1)[1]
    if code not in TESTS:
        await callback.answer("Невідомий тест.")
        return

    if callback.from_user.id not in tg_to_candidate:
        await callback.message.answer("Спочатку виконай /start.")
        await callback.answer()
        return

    meta = TESTS[code]
    await state.update_data(
        test_type=code,
        answers=[],
        idx=0,
    )

    await callback.message.answer(
        f"Тест: <b>{meta['title']}</b>\n"
        f"{meta['description']}\n\n"
        "Відповідай числом від 1 до 5, де 1 — зовсім не про мене, 5 — повністю про мене.\n\n"
        f"1/{len(meta['questions'])}. {meta['questions'][0]}",
        parse_mode="HTML",
    )
    await TestFlow.answering.set()
    await callback.answer()


@dp.message_handler(state=TestFlow.answering)
async def handle_test_answer(message: types.Message, state: FSMContext):
    data = await state.get_data()
    test_type = data.get("test_type")
    idx = data.get("idx", 0)
    answers = data.get("answers", [])

    if not test_type or test_type not in TESTS:
        await message.answer("Сталася помилка з вибором тесту. Почни з /tests.")
        await state.finish()
        return

    text = message.text.strip()
    if text not in ["1", "2", "3", "4", "5"]:
        await message.answer("Будь ласка, відповідай лише числом від 1 до 5.")
        return

    answers.append(int(text))
    idx += 1
    await state.update_data(answers=answers, idx=idx)

    questions = TESTS[test_type]["questions"]
    total = len(questions)

    if idx < total:
        await message.answer(
            f"{idx+1}/{total}. {questions[idx]}"
        )
        return

    candidate_id = tg_to_candidate.get(message.from_user.id)
    if not candidate_id:
        await message.answer("Не знайдено кандидата. Почни з /start.")
        await state.finish()
        return

    await message.answer("Обробляю результати тесту...")

    try:
        resp = await backend_submit_test(candidate_id, test_type, answers)
    except Exception as e:
        logger.exception("submit_test failed: %s", e)
        await message.answer("Помилка при збереженні результатів. Спробуй пізніше.")
        await state.finish()
        return

    report = resp.get("report") or {}
    summary = report.get("summary", "Немає короткого опису.")
    recs = report.get("recommendations", [])
    risk = report.get("risk_level", "невідомо")
    rec_text = "\n- ".join(recs) if recs else "Немає рекомендацій."

    await message.answer(
        f"✅ Тест <b>{TESTS[test_type]['title']}</b> завершено.\n\n"
        f"<b>Короткий опис:</b> {summary}\n\n"
        f"<b>Ризик-профіль:</b> {risk}\n\n"
        f"<b>Рекомендації для HR:</b>\n- {rec_text}\n\n"
        "Можеш обрати інший тест командою /tests або скористатися /voice чи /photo.",
        parse_mode="HTML",
    )
    await state.finish()


@dp.message_handler(commands=["voice"])
async def cmd_voice(message: types.Message, state: FSMContext):
    if message.from_user.id not in tg_to_candidate:
        await message.answer("Спочатку виконай /start.")
        return
    await state.finish()
    await message.answer(
        "Надішли, будь ласка, голосове повідомлення (20–30 секунд), "
        "і я оціниму рівень стресу за голосом."
    )
    await VoiceState.waiting_for_voice.set()


@dp.message_handler(content_types=[types.ContentType.VOICE], state=VoiceState.waiting_for_voice)
async def handle_voice(message: types.Message, state: FSMContext):
    candidate_id = tg_to_candidate.get(message.from_user.id)
    if not candidate_id:
        await message.answer("Не знайдено кандидата. Почни з /start.")
        await state.finish()
        return

    voice = message.voice
    try:
        file = await bot.get_file(voice.file_id)
        buf = BytesIO()
        await bot.download_file(file.file_path, destination=buf)
        buf.seek(0)
    except Exception as e:
        logger.exception("download voice failed: %s", e)
        await message.answer("Не вдалося завантажити голосове. Спробуй ще раз.")
        await state.finish()
        return

    await message.answer("Обробляю голос...")

    form = aiohttp.FormData()
    form.add_field("candidate_id", str(candidate_id))
    form.add_field("file", buf.getvalue(), filename="voice.ogg", content_type="audio/ogg")

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{BACKEND_URL}/api/voice/analyze", data=form) as resp:
                data = await resp.json()
                if resp.status != 200:
                    raise RuntimeError(f"Backend error: {data}")
    except Exception as e:
        logger.exception("voice analyze failed: %s", e)
        await message.answer("Сталася помилка при аналізі голосу.")
        await state.finish()
        return

    voice_info = data.get("voice", {})
    stress = voice_info.get("stress_score", 0)
    level = voice_info.get("level", "невідомо")

    await message.answer(
        "🎙 <b>Результат голосового аналізу</b>\n\n"
        f"Оцінка стресу: <b>{stress}/100</b>\n"
        f"Рівень: <b>{level}</b>\n\n"
        "Ці дані доступні HR у дашборді.",
        parse_mode="HTML",
    )
    await state.finish()


@dp.message_handler(commands=["photo"])
async def cmd_photo(message: types.Message, state: FSMContext):
    if message.from_user.id not in tg_to_candidate:
        await message.answer("Спочатку виконай /start.")
        return
    await state.finish()
    await message.answer(
        "Надішли своє фото (селфі — бажано чітке), і я оціниму загальний настрій та рівень втоми."
    )
    await PhotoState.waiting_for_photo.set()


@dp.message_handler(content_types=[types.ContentType.PHOTO], state=PhotoState.waiting_for_photo)
async def handle_photo(message: types.Message, state: FSMContext):
    candidate_id = tg_to_candidate.get(message.from_user.id)
    if not candidate_id:
        await message.answer("Не знайдено кандидата. Почни з /start.")
        await state.finish()
        return

    photo = message.photo[-1]
    try:
        file = await bot.get_file(photo.file_id)
        buf = BytesIO()
        await bot.download_file(file.file_path, destination=buf)
        buf.seek(0)
    except Exception as e:
        logger.exception("download photo failed: %s", e)
        await message.answer("Не вдалося завантажити фото. Спробуй ще раз.")
        await state.finish()
        return

    await message.answer("Обробляю фото...")

    form = aiohttp.FormData()
    form.add_field("candidate_id", str(candidate_id))
    form.add_field("file", buf.getvalue(), filename="photo.jpg", content_type="image/jpeg")

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{BACKEND_URL}/api/photo/analyze", data=form) as resp:
                data = await resp.json()
                if resp.status != 200:
                    raise RuntimeError(f"Backend error: {data}")
    except Exception as e:
        logger.exception("photo analyze failed: %s", e)
        await message.answer("Сталася помилка при аналізі фото.")
        await state.finish()
        return

    photo_info = data.get("photo", {})
    mood = photo_info.get("mood", "невідомо")
    fatigue = photo_info.get("fatigue_level", "невідомо")

    await message.answer(
        "📷 <b>Результат фотоаналізу</b>\n\n"
        f"Настрій: <b>{mood}</b>\n"
        f"Рівень втоми: <b>{fatigue}</b>\n\n"
        "Ця інформація також відображається у HR-дашборді.",
        parse_mode="HTML",
    )
    await state.finish()


@dp.message_handler(commands=["help"])
async def cmd_help(message: types.Message):
    await message.answer(
        "/start — реєстрація кандидата\n"
        "/tests — обрати та пройти психологічні тести\n"
        "/voice — голосовий аналіз стресу\n"
        "/photo — аналіз фото (настрій / втома)\n"
    )


if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
