import html, json, os, random, re, time
from datetime import datetime, timedelta, timezone
from telegram import (Update, InlineKeyboardButton as B, InlineKeyboardMarkup as M,
    ReplyKeyboardMarkup, ReplyParameters, ChatPermissions, BotCommand, BotCommandScopeChat, BotCommandScopeChatMember)
from telegram.ext import (ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters)

from telegram import LinkPreviewOptions
NOPREV = LinkPreviewOptions(is_disabled=True)

TOKEN = os.environ.get("TOKEN") or open("token.txt").read().strip()
OWNER = 5236679334
OWNER2 = 8478210016
N, MINES, START_BAL = 25, 6, 1000
BONUS, BONUS_CD = 500, 24 * 3600
FILE, META = "bal.json", "meta.json"

def load(f, d):
    try:
        return json.load(open(f))
    except Exception:
        return d

bal = load(FILE, {})
meta = load(META, {})
for k, v in (("bonus", {}), ("names", {}), ("admins", []), ("owners", []), ("menus", {}), ("unames", {}),
                 ("warns", {}), ("rules", {}), ("cadmins", {}), ("antilink", {}), ("welcome", {}),
                 ("nicks", {}), ("rep", {}), ("repcd", {}), ("spouse", {}), ("wed", {}), ("antiflood", {})):
    meta.setdefault(k, v)

def save():
    json.dump(bal, open(FILE, "w"))
    json.dump(meta, open(META, "w"))

def get(uid):
    return bal.setdefault(str(uid), START_BAL)

def rec(user):
    """запомнить имя и @ник пользователя (для выдачи по нику)"""
    if not user or user.is_bot:
        return False
    ch = False
    uid = str(user.id)
    nm = user.first_name or "Игрок"
    if meta["names"].get(uid) != nm:
        meta["names"][uid] = nm
        ch = True
    if user.username:
        un = user.username.lower()
        if meta["unames"].get(un) != uid:
            meta["unames"][un] = uid
            ch = True
    return ch

def touch(u):
    user = u.effective_user
    if rec(user):
        save()
    get(user.id)
    return str(user.id)

def amt_of(s, balance=None):
    """100, 1к, 1.5к, 2кк, все"""
    s = s.lower().replace(",", ".").replace("_", "")
    if s in ("все", "всё", "all") and balance is not None:
        return balance
    mul = 1
    if s.endswith(("кк", "kk")):
        mul, s = 1000000, s[:-2]
    elif s.endswith(("к", "k")):
        mul, s = 1000, s[:-1]
    if not re.fullmatch(r"\d+(\.\d+)?", s):
        return None
    return int(float(s) * mul)

def owners():
    return {str(OWNER), str(OWNER2)}

def admins():
    # монеты (Выдать/Забрать/Сброс/Статистика) — только создатели бота
    return owners()

def mult(k):
    if k == 0:
        return 1.0
    m = 1.0
    for i in range(k):
        m *= (N - i) / (N - MINES - i)
    return round(m * 0.97, 2)

def kb(g, end=False, hit=None):
    rows = []
    for r in range(5):
        row = []
        for c in range(5):
            i = r * 5 + c
            if end:
                if i == hit:
                    t = "💥"
                elif i in g["mines"]:
                    t = "💣"
                elif i in g["open"]:
                    t = "💎"
                else:
                    t = "▫️"
                row.append(B(t, callback_data="x"))
            else:
                t = "💎" if i in g["open"] else "❓"
                row.append(B(t, callback_data=f"c{i}"))
        rows.append(row)
    if not end:
        win = int(g["bet"] * mult(len(g["open"])))
        rows.append([B(f"💰 Забрать {win}", callback_data="cash")])
    return M(rows)

USER_CMDS = [("menu", "Меню с кнопками"), ("profile", "Профиль"), ("play", "Играть в мины"), ("balance", "Баланс"),
             ("bonus", "Бонус раз в сутки"), ("top", "Топ игроков"),
             ("give", "Передать монеты"), ("duel", "Дуэль на монеты"), ("roulette", "Русская рулетка"),
             ("calc", "Калькулятор"), ("timer", "Таймер"), ("id", "Мой ID"), ("help", "Помощь")]
ADMIN_CMDS = [("grant", "Выдать монеты"), ("take", "Забрать монеты"),
              ("reset", "Сбросить баланс"), ("stats", "Статистика")]
OWNER_CMDS = []

menu_seen = set()

def cmds_for(uid):
    uid = str(uid)
    c = list(USER_CMDS)
    if uid in admins():
        c += ADMIN_CMDS
    if uid in owners():
        c += OWNER_CMDS
    return [BotCommand(n, d) for n, d in c]

async def set_menu(bot, uid, chat_id=None):
    try:
        if chat_id is None:
            scope = BotCommandScopeChat(chat_id=int(uid))
        else:
            scope = BotCommandScopeChatMember(chat_id=chat_id, user_id=int(uid))
            lst = meta["menus"].setdefault(str(uid), [])
            if chat_id not in lst:
                lst.append(chat_id)
                save()
        await bot.set_my_commands(cmds_for(uid), scope=scope)
    except Exception:
        pass

async def refresh(bot, uid):
    uid = str(uid)
    for key in [k for k in menu_seen if k[0] == uid]:
        menu_seen.discard(key)
    scopes = [(None, BotCommandScopeChat(chat_id=int(uid)))]
    for cid in meta["menus"].get(uid, []):
        scopes.append((cid, BotCommandScopeChatMember(chat_id=cid, user_id=int(uid))))
    for cid, scope in scopes:
        try:
            if uid in admins():
                await bot.set_my_commands(cmds_for(uid), scope=scope)
            else:
                await bot.delete_my_commands(scope=scope)
        except Exception:
            pass
    if uid not in admins():
        meta["menus"].pop(uid, None)
        save()

async def sync(u, ctx):
    user, chat = u.effective_user, u.effective_chat
    if not user or not chat:
        return
    uid = str(user.id)
    if uid not in admins() or (uid, chat.id) in menu_seen:
        return
    menu_seen.add((uid, chat.id))
    await set_menu(ctx.bot, uid, None if chat.type == "private" else chat.id)

async def post_init(application):
    try:
        await application.bot.set_my_commands(
            [BotCommand(n, d) for n, d in USER_CMDS])
    except Exception:
        pass
    for uid in admins():
        await set_menu(application.bot, uid)

HELP = (
    "💣 Игра «Мины»: поле 5x5, 6 мин. Монеты виртуальные.\n\n"
    "Мины 100 — играть (можно 1к, 2.5к, все)\n"
    "Баланс — ваш баланс\n"
    "Бонус — бонус раз в 24 часа\n"
    "Топ — лучшие игроки\n"
    "Передать @ник 100 — перевод (или ответом на сообщение: Передать 100)\n"
    "Дуэль @ник 100 — дуэль на монеты\n"
    "Рулетка 100 — русская рулетка\n"
    "Шипперим — случайная пара из чата\n"
    "Кто <вопрос> — случайный участник\n"
    "Калькулятор 2+2*2 · Таймер 10м текст · ID чата\n"
    "Айди — ваш Telegram ID\n"
    "Помощь — это сообщение\n"
    "Меню — кнопки снизу\n"
    "Профиль — ваш профиль\n"
    "Модерация — команды для админов группы\n"
    "(команды со / тоже работают)")

ADMIN_HELP = (
    "\n\n👑 Создатель бота (монеты):\n"
    "Выдать @ник 500 — выдать монеты\n"
    "Забрать @ник 500 — забрать монеты\n"
    "Сброс @ник — сбросить баланс\n"
    "Статистика — статистика\n"
    "Игрока указывайте: @ником, ответом на сообщение (Выдать 500), по имени или по ID.")

OWNER_HELP = ""

MENU_ROWS = [["👤 Профиль", "💣 Мины"], ["💰 Баланс", "🎁 Бонус"], ["🏆 Топ", "📋 Помощь"]]

async def menu(u, ctx, a):
    touch(u)
    if u.effective_chat.type == "private":
        await u.message.reply_text("📋 Меню открыто. Кнопки снизу 👇",
                                   reply_markup=ReplyKeyboardMarkup(MENU_ROWS, resize_keyboard=True))
    else:
        # в группе кнопки видит только тот, кто вызвал меню
        await ctx.bot.send_message(
            u.effective_chat.id, "📋 Меню для вас 👇",
            reply_markup=ReplyKeyboardMarkup(MENU_ROWS, resize_keyboard=True, selective=True),
            reply_parameters=ReplyParameters(message_id=u.message.message_id))

async def profile(u, ctx, a):
    uid = touch(u)
    place = 1 + sum(1 for v in bal.values() if v > bal[uid])
    role = "👑 Владелец бота" if uid in owners() else ("🛠 Админ" if uid in admins() else "Игрок")
    await u.message.reply_text(
        f"👤 {pname(uid)}\n🆔 {uid}\n💰 Баланс: {bal[uid]}\n🏆 Место по монетам: {place}\n"
        f"⭐ Репутация: {meta['rep'].get(uid, 0)}"
        + (f"\n💍 В браке с {pname(meta['spouse'][uid])}" if uid in meta["spouse"] else "")
        + f"\n{role}")

HELP_URL = (os.environ.get("HELP_URL")
            or (os.environ["RENDER_EXTERNAL_URL"].rstrip("/") + "/help" if os.environ.get("RENDER_EXTERNAL_URL") else None)
            or "https://claude.ai/artifact/JJXuRKesfzjR7VvzUtzeDR")

async def help_(u, ctx, a):
    touch(u)
    await u.message.reply_text(
        "📖 Справка по боту: игры, монеты, ранги чата, модерация и все команды — на сайте.",
        reply_markup=M([[B("📖 Открыть справку", url=HELP_URL)]]))

async def start_(u, ctx, a):
    touch(u)
    if a and a[0] == "bonus" and u.effective_chat.type == "private":
        return await bonus(u, ctx, [])
    if u.effective_chat.type == "private":
        await u.message.reply_text("👋 Привет! Кнопки меню снизу 👇",
                                   reply_markup=ReplyKeyboardMarkup(MENU_ROWS, resize_keyboard=True))
    await help_(u, ctx, a)

async def myid(u, ctx, a):
    await u.message.reply_text(f"Ваш ID: {u.effective_user.id}")

async def balance(u, ctx, a):
    uid = touch(u)
    await u.message.reply_text(f"💰 Баланс: {bal[uid]}")

def captcha():
    x, y = random.randint(3, 15), random.randint(3, 15)
    ans = x + y
    opts = {ans}
    while len(opts) < 4:
        opts.add(ans + random.choice([-3, -2, -1, 1, 2, 3, 10, -10]))
    opts = sorted(opts)
    random.shuffle(opts)
    return f"{x} + {y}", ans, opts

def cap_kb(opts):
    return M([[B(str(o), callback_data=f"cap:{o}") for o in opts]])

def bonus_left(uid):
    return meta["bonus"].get(uid, 0) + BONUS_CD - time.time()

async def bonus(u, ctx, a):
    uid = touch(u)
    left = bonus_left(uid)
    if left > 0:
        h, m = int(left // 3600), int(left % 3600 // 60)
        await u.message.reply_text(f"⏳ Бонус будет доступен через {h} ч {m} мин.")
        return
    if u.effective_chat.type != "private":
        url = f"https://t.me/{ctx.bot.username}?start=bonus"
        await u.message.reply_text("🎁 Бонус выдаётся в личных сообщениях с ботом (там нужно пройти капчу).",
                                   reply_markup=M([[B("🎁 Получить бонус", url=url)]]))
        return
    expr, ans, opts = captcha()
    ctx.user_data["cap"] = {"ans": ans, "t": time.time()}
    await u.message.reply_text(f"🤖 Капча: сколько будет {expr}?", reply_markup=cap_kb(opts))

async def cap_press(q, ctx, uid):
    cap = ctx.user_data.get("cap")
    if not cap or time.time() - cap["t"] > 180:
        ctx.user_data["cap"] = None
        await q.answer("Капча устарела. Напишите: Бонус", show_alert=True)
        return
    if int(q.data[4:]) != cap["ans"]:
        expr, ans, opts = captcha()
        ctx.user_data["cap"] = {"ans": ans, "t": time.time()}
        await q.answer("❌ Неверно, попробуйте ещё раз", show_alert=True)
        await q.edit_message_text(f"🤖 Капча: сколько будет {expr}?", reply_markup=cap_kb(opts))
        return
    ctx.user_data["cap"] = None
    if bonus_left(uid) > 0:
        await q.answer("Бонус уже получен", show_alert=True)
        return
    get(uid)
    meta["bonus"][uid] = time.time()
    bal[uid] += BONUS
    save()
    await q.answer("✅ Капча пройдена")
    await q.edit_message_text(f"🎁 Бонус +{BONUS}! Баланс: {bal[uid]}")

async def top_coins(u, ctx, a):
    touch(u)
    best = sorted(bal.items(), key=lambda x: -x[1])[:10]
    lines = [f"{MEDAL.get(i, str(i) + '.')} {men(k)} — {v}"
             for i, (k, v) in enumerate(best, 1)]
    await u.message.reply_text("🏆 Топ игроков:\n" + "\n".join(lines),
                               parse_mode="HTML", link_preview_options=NOPREV)

async def give(u, ctx, a):
    uid = touch(u)
    res = await resolve(u, ctx, a, "Передать @ник 100 (или ответом на сообщение: Передать 100)")
    if not res:
        return
    to, amt = res
    if amt is None:
        await u.message.reply_text("Укажите сумму: Передать @ник 100")
        return
    if to == uid or amt < 1 or amt > bal[uid]:
        await u.message.reply_text("Неверная сумма или получатель.")
        return
    get(to)
    bal[uid] -= amt
    bal[to] += amt
    save()
    await u.message.reply_text(f"✅ Переведено {amt}. Ваш баланс: {bal[uid]}")

async def target(u, ctx, a):
    m = u.message
    a = list(a)
    r = m.reply_to_message
    if r and r.from_user and not r.from_user.is_bot:
        rec(r.from_user)
        return str(r.from_user.id), a
    for e in m.entities or []:
        if e.type == "text_mention" and e.user:
            rec(e.user)
            words = set(m.parse_entity(e).split())
            return str(e.user.id), [x for x in a if x not in words]
    for i, x in enumerate(a):
        if x.startswith("@") and len(x) > 1:
            un = x[1:].lower()
            t = meta["unames"].get(un)
            if not t:
                try:
                    c = await ctx.bot.get_chat(x)
                    t = str(c.id)
                    meta["unames"][un] = t
                    meta["names"].setdefault(t, c.first_name or c.title or "Игрок")
                except Exception:
                    t = None
            return (t or "?"), a[:i] + a[i + 1:]
    for i, x in enumerate(a):
        if x.isdigit() and len(x) >= 8:
            return x, a[:i] + a[i + 1:]
    for i, x in enumerate(a):
        if amt_of(x) is None:
            for k, v in meta["names"].items():
                if v.lower() == x.lower():
                    return k, a[:i] + a[i + 1:]
    return None, a

async def resolve(u, ctx, a, usage, need_amt=True):
    """-> (id, сумма|None) или None (ответ об ошибке уже отправлен)"""
    t, rest = await target(u, ctx, a)
    if t == "?":
        await u.message.reply_text("Не знаю такого игрока. Пусть он напишет в чат хоть раз, "
                                   "или ответьте на его сообщение.")
        return None
    if not t:
        await u.message.reply_text("Кому? " + usage)
        return None
    amt = None
    for x in rest:
        amt = amt_of(x)
        if amt is not None:
            break
    return t, amt

def pname(t):
    return meta["nicks"].get(t) or meta["names"].get(t, t)

async def deny(u):
    await u.message.reply_text("⛔ Нет доступа.")

async def grant(u, ctx, a):
    uid = touch(u)
    if uid not in admins():
        return await deny(u)
    res = await resolve(u, ctx, a, "Выдать @ник 500 (или ответом: Выдать 500)")
    if not res:
        return
    t, amt = res
    if not amt:
        await u.message.reply_text("Укажите сумму: Выдать @ник 500")
        return
    get(t)
    bal[t] += amt
    save()
    await u.message.reply_text(f"✅ {pname(t)}: +{amt}. Баланс: {bal[t]}")

async def take(u, ctx, a):
    uid = touch(u)
    if uid not in admins():
        return await deny(u)
    res = await resolve(u, ctx, a, "Забрать @ник 500 (или ответом: Забрать 500)")
    if not res:
        return
    t, amt = res
    if not amt:
        await u.message.reply_text("Укажите сумму: Забрать @ник 500")
        return
    get(t)
    bal[t] = max(0, bal[t] - amt)
    save()
    await u.message.reply_text(f"✅ {pname(t)}: -{amt}. Баланс: {bal[t]}")

async def reset(u, ctx, a):
    uid = touch(u)
    if uid not in admins():
        return await deny(u)
    res = await resolve(u, ctx, a, "Сброс @ник (или ответом на сообщение)")
    if not res:
        return
    t = res[0]
    bal[t] = START_BAL
    save()
    await u.message.reply_text(f"✅ Баланс {pname(t)} сброшен до {START_BAL}.")

async def stats(u, ctx, a):
    uid = touch(u)
    if uid not in admins():
        return await deny(u)
    await u.message.reply_text(
        f"📊 Игроков: {len(bal)}\nВсего монет: {sum(bal.values())}\n"
        f"Создателей бота: {len(owners())}\nЧатов с админами: {len(meta['cadmins'])}")

RN = {1: "Мл. модератор", 2: "Модератор", 3: "Мл. админ", 4: "Админ", 5: "Владелец"}

def ranks_of(cid):
    d = meta["cadmins"].get(str(cid), {})
    if isinstance(d, list):  # старый формат: просто админы -> ранг 4
        d = {str(x): 4 for x in d}
        meta["cadmins"][str(cid)] = d
    return d

async def set_rank(u, ctx, a, forced=None):
    if u.effective_chat.type not in GROUP:
        await u.message.reply_text("Ранги выдают в группе.")
        return
    me = await actor_rank(u, ctx)
    if me < 2:
        return await u.message.reply_text("⛔ Выдавать ранги можно с 2 ранга и выше.")
    res = await resolve(u, ctx, a, "Ранг @ник 3 (0 — снять) или ответом на сообщение")
    if not res:
        return
    t, amt = res
    r = forced if forced is not None else amt
    if r is None or r < 0 or r > 4:
        await u.message.reply_text("Укажите ранг от 0 до 4: Ранг @ник 3 (0 — снять).")
        return
    cid = u.effective_chat.id
    tid = int(t)
    if tid == ctx.bot.id or (u.effective_user and tid == u.effective_user.id):
        await u.message.reply_text("⛔ Себе или боту ранг выдать нельзя.")
        return
    cur = await rank_of(ctx, cid, tid)
    if cur == 5:
        await u.message.reply_text("Это владелец чата.")
        return
    if r >= me or cur >= me:
        await u.message.reply_text(f"⛔ Выдавать и менять можно только ранги ниже вашего (у вас {me}).")
        return
    d = ranks_of(cid)
    if r == 0:
        d.pop(t, None)
        save()
        await say(u, f"✅ {men(t)} больше не в штате чата (ранг 0).")
    else:
        d[t] = r
        meta["cadmins"][str(cid)] = d
        save()
        await say(u, f"🎖 {men(t)} получил ранг {r} — {RN[r]}.")

async def rank_cmd(u, ctx, a):
    await set_rank(u, ctx, a)

async def addadmin(u, ctx, a):
    await set_rank(u, ctx, a, 4)

async def addjradmin(u, ctx, a):
    await set_rank(u, ctx, a, 3)

async def addmod(u, ctx, a):
    await set_rank(u, ctx, a, 2)

async def addjrmod(u, ctx, a):
    await set_rank(u, ctx, a, 1)

async def rmadmin(u, ctx, a):
    await set_rank(u, ctx, a, 0)

async def chat_admins(u, ctx, a):
    touch(u)
    if u.effective_chat.type not in GROUP:
        await u.message.reply_text("Команда работает в группах.")
        return
    cid = u.effective_chat.id
    lines = []
    try:
        for m in await ctx.bot.get_chat_administrators(cid):
            if m.status == "creator":
                rec(m.user)
                lines.append(f"5 · Владелец: {men(m.user.id)}")
    except Exception:
        pass
    d = ranks_of(cid)
    for r in (4, 3, 2, 1):
        for x, rr in d.items():
            if rr == r:
                lines.append(f"{r} · {RN[r]}: {men(x)}")
    await say(u, "🎖 Штат чата:\n" + "\n".join(lines) if lines else "Штат пока пуст.")

def new_game(uid, bet):
    bal[uid] -= bet
    save()
    return {"bet": bet, "mines": set(random.sample(range(N), MINES)), "open": set()}

async def play(u, ctx, a):
    uid = touch(u)
    if ctx.user_data.get("g"):
        await u.message.reply_text("Сначала закончите текущую игру.")
        return
    if not a:
        row = [B(str(x), callback_data=f"bet:{uid}:{x}") for x in (5, 50, 100, 500)]
        row2 = [B("1000", callback_data=f"bet:{uid}:1000"), B("Всё", callback_data=f"bet:{uid}:all")]
        await u.message.reply_text(f"💣 Выберите ставку (баланс: {bal[uid]})\nили напишите: Мины 100",
                                   reply_markup=M([row, row2]))
        return
    bet = amt_of(a[0], bal[uid])
    if bet is None:
        await u.message.reply_text("Пример: Мины 100")
        return
    if bet < 5 or bet > bal[uid]:
        await u.message.reply_text(f"Неверная ставка (минимум 5). Баланс: {bal[uid]}")
        return
    g = new_game(uid, bet)
    ctx.user_data["g"] = g
    await u.message.reply_text(
        f"Ставка: {bet} | x1.0\nОткрывайте клетки, избегайте 💣",
        reply_markup=kb(g))

async def press(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query
    uid = str(q.from_user.id)
    g = ctx.user_data.get("g")
    if q.data == "x":
        await q.answer()
        return
    if q.data.startswith("duel:"):
        return await duel_press(q, ctx, uid)
    if q.data.startswith("mar:"):
        return await mar_press(q, ctx, uid)
    if q.data.startswith("cap:"):
        return await cap_press(q, ctx, uid)
    if q.data.startswith("bet:"):
        _, owner, v = q.data.split(":")
        if owner != uid:
            await q.answer("Это не ваша игра. Напишите: Мины", show_alert=True)
            return
        if g:
            await q.answer("Сначала закончите текущую игру.", show_alert=True)
            return
        get(uid)
        bet = bal[uid] if v == "all" else int(v)
        if bet < 5 or bet > bal[uid]:
            await q.answer(f"Неверная ставка (минимум 5). Баланс: {bal[uid]}", show_alert=True)
            return
        g = new_game(uid, bet)
        ctx.user_data["g"] = g
        await q.answer()
        await q.edit_message_text(f"Ставка: {bet} | x1.0\nОткрывайте клетки, избегайте 💣",
                                  reply_markup=kb(g))
        return
    if not g:
        await q.answer("Игра не найдена. Начните: Мины ставка", show_alert=True)
        return
    await q.answer()

    async def cashout(prefix):
        win = int(g["bet"] * mult(len(g["open"])))
        bal[uid] += win
        save()
        ctx.user_data["g"] = None
        await q.edit_message_text(
            f"{prefix} Выигрыш: {win}\nБаланс: {bal[uid]}",
            reply_markup=kb(g, True))

    if q.data == "cash":
        await cashout("💰 Забрали!")
        return
    i = int(q.data[1:])
    if i in g["open"]:
        return
    if i in g["mines"]:
        ctx.user_data["g"] = None
        await q.edit_message_text(
            f"💥 Мина! Потеряно: {g['bet']}\nБаланс: {bal[uid]}",
            reply_markup=kb(g, True, i))
        return
    g["open"].add(i)
    if len(g["open"]) == N - MINES:
        await cashout("🏆 Все клетки открыты!")
        return
    k = len(g["open"])
    await q.edit_message_text(
        f"Ставка: {g['bet']} | x{mult(k)}\nОткрыто: {k}",
        reply_markup=kb(g))

# ================= МОДЕРАЦИЯ =================
GROUP = ("group", "supergroup")
WARN_LIMIT = 3
_st = {}

async def status(ctx, cid, uid):
    k, now = (cid, uid), time.time()
    c = _st.get(k)
    if c and now - c[0] < 60:
        return c[1]
    try:
        s = (await ctx.bot.get_chat_member(cid, uid)).status
    except Exception:
        s = "member"
    _st[k] = (now, s)
    return s

async def rank_of(ctx, cid, uid):
    """5 — владелец чата (создатель группы), 1–4 — ранги, выданные в чате, 0 — участник"""
    if await status(ctx, cid, uid) == "creator":
        return 5
    return ranks_of(cid).get(str(uid), 0)

async def actor_rank(u, ctx):
    ch, m = u.effective_chat, u.message
    if m and m.sender_chat and m.sender_chat.id == ch.id:  # анонимный админ группы
        return 3
    if not u.effective_user:
        return 0
    return await rank_of(ctx, ch.id, u.effective_user.id)

async def is_mod(u, ctx):
    return await actor_rank(u, ctx) >= 1

def needs(n):
    def deco(fn):
        async def w(u, ctx, a):
            if u.effective_chat.type not in GROUP:
                await u.message.reply_text("Эта команда работает только в группах.")
                return
            if await actor_rank(u, ctx) < n:
                return await u.message.reply_text(f"⛔ Нужен ранг {n}+ ({RN[n]}).")
            await fn(u, ctx, a)
        return w
    return deco

modonly = needs(1)

def cap_dur(d, limit):
    return limit if limit and (d == 0 or d > limit) else d

UNITS = {"с": 1, "сек": 1, "s": 1, "м": 60, "мин": 60, "m": 60, "ч": 3600, "час": 3600, "h": 3600,
         "д": 86400, "дн": 86400, "d": 86400, "н": 604800, "нед": 604800, "w": 604800}

def dur_of(s):
    s = s.lower()
    if s in ("навсегда", "forever", "inf"):
        return 0
    m = re.fullmatch(r"(\d+)([a-zа-я]+)", s)
    if not m or m.group(2) not in UNITS:
        return None
    return max(60, int(m.group(1)) * UNITS[m.group(2)])

def split_dur(rest, default):
    if rest:
        d = dur_of(rest[0])
        if d is not None:
            return d, " ".join(rest[1:])
    return default, " ".join(rest)

def until(d):
    return None if d == 0 else datetime.now(timezone.utc) + timedelta(seconds=d)

def fmt_dur(d):
    if d == 0:
        return "навсегда"
    if d >= 86400:
        return f"{d // 86400} д"
    if d >= 3600:
        return f"{d // 3600} ч"
    return f"{d // 60} мин"

def men(uid):
    return f'<a href="tg://user?id={uid}">{html.escape(pname(str(uid)))}</a>'

def why(r):
    return f"\nПричина: {html.escape(r)}" if r else ""

async def say(u, text):
    await u.message.reply_text(text, parse_mode="HTML")

async def fail(u, e):
    await u.message.reply_text("⚠️ Не получилось: " + str(e)[:120] +
                               "\nПроверьте, что бот админ группы с нужными правами.")

async def victim(u, ctx, a, usage, protect=True):
    t, rest = await target(u, ctx, a)
    if t == "?":
        await u.message.reply_text("Не знаю такого игрока. Пусть напишет в чат хоть раз, "
                                   "или ответьте на его сообщение.")
        return None
    if not t:
        await u.message.reply_text("Кого? " + usage)
        return None
    tid = int(t)
    if protect:
        me = await actor_rank(u, ctx)
        if (tid == ctx.bot.id or await rank_of(ctx, u.effective_chat.id, tid) >= me
                or (me < 5 and await status(ctx, u.effective_chat.id, tid) == "administrator")):
            await u.message.reply_text("⛔ Нельзя применить к админу или владельцу.")
            return None
    return tid, rest

def full_perms(chat):
    p = getattr(chat, "permissions", None)
    if p and p.can_send_messages:
        return p
    return ChatPermissions(
        can_send_messages=True, can_send_audios=True, can_send_documents=True,
        can_send_photos=True, can_send_videos=True, can_send_video_notes=True,
        can_send_voice_notes=True, can_send_polls=True, can_send_other_messages=True,
        can_add_web_page_previews=True, can_invite_users=True)

@needs(1)
async def mute(u, ctx, a):
    v = await victim(u, ctx, a, "Мут @ник 30м причина (или ответом на сообщение)")
    if not v:
        return
    tid, rest = v
    d, reason = split_dur(rest, 3600)
    d = cap_dur(d, {1: 86400, 2: 604800}.get(await actor_rank(u, ctx), 0))
    try:
        await ctx.bot.restrict_chat_member(u.effective_chat.id, tid,
                                           ChatPermissions(can_send_messages=False), until_date=until(d))
    except Exception as e:
        return await fail(u, e)
    await say(u, f"🔇 {men(tid)} в муте: {fmt_dur(d)}.{why(reason)}")

@needs(2)
async def unmute(u, ctx, a):
    v = await victim(u, ctx, a, "Размут @ник", protect=False)
    if not v:
        return
    try:
        chat = await ctx.bot.get_chat(u.effective_chat.id)
        await ctx.bot.restrict_chat_member(u.effective_chat.id, v[0], full_perms(chat))
    except Exception as e:
        return await fail(u, e)
    await say(u, f"🔊 {men(v[0])} размучен.")

@needs(2)
async def ban(u, ctx, a):
    v = await victim(u, ctx, a, "Бан @ник 1д причина (или ответом на сообщение)")
    if not v:
        return
    tid, rest = v
    d, reason = split_dur(rest, 0)
    d = cap_dur(d, {2: 604800}.get(await actor_rank(u, ctx), 0))
    try:
        await ctx.bot.ban_chat_member(u.effective_chat.id, tid, until_date=until(d))
    except Exception as e:
        return await fail(u, e)
    await say(u, f"⛔ {men(tid)} забанен: {fmt_dur(d)}.{why(reason)}")

@needs(3)
async def unban(u, ctx, a):
    v = await victim(u, ctx, a, "Разбан @ник (или ID)", protect=False)
    if not v:
        return
    try:
        await ctx.bot.unban_chat_member(u.effective_chat.id, v[0], only_if_banned=True)
    except Exception as e:
        return await fail(u, e)
    await say(u, f"✅ {men(v[0])} разбанен.")

@needs(2)
async def kick(u, ctx, a):
    v = await victim(u, ctx, a, "Кик @ник причина")
    if not v:
        return
    tid, rest = v
    try:
        await ctx.bot.ban_chat_member(u.effective_chat.id, tid)
        await ctx.bot.unban_chat_member(u.effective_chat.id, tid, only_if_banned=True)
    except Exception as e:
        return await fail(u, e)
    await say(u, f"👢 {men(tid)} исключён.{why(' '.join(rest))}")

@needs(1)
async def warn(u, ctx, a):
    v = await victim(u, ctx, a, "Варн @ник причина (или ответом на сообщение)")
    if not v:
        return
    tid, rest = v
    cid = str(u.effective_chat.id)
    w = meta["warns"].setdefault(cid, {})
    n = w.get(str(tid), 0) + 1
    reason = " ".join(rest)
    if n >= WARN_LIMIT:
        w[str(tid)] = 0
        save()
        try:
            await ctx.bot.ban_chat_member(u.effective_chat.id, tid)
        except Exception as e:
            return await fail(u, e)
        await say(u, f"⛔ {men(tid)} получил {WARN_LIMIT}/{WARN_LIMIT} варнов и забанен.{why(reason)}")
        return
    w[str(tid)] = n
    save()
    await say(u, f"⚠️ {men(tid)}: варн {n}/{WARN_LIMIT}.{why(reason)}")

@needs(1)
async def unwarn(u, ctx, a):
    v = await victim(u, ctx, a, "Снятьварн @ник", protect=False)
    if not v:
        return
    w = meta["warns"].setdefault(str(u.effective_chat.id), {})
    w[str(v[0])] = max(0, w.get(str(v[0]), 0) - 1)
    save()
    await say(u, f"✅ {men(v[0])}: варнов {w[str(v[0])]}/{WARN_LIMIT}.")

@needs(1)
async def warns(u, ctx, a):
    v = await victim(u, ctx, a, "Варны @ник", protect=False)
    if not v:
        return
    n = meta["warns"].get(str(u.effective_chat.id), {}).get(str(v[0]), 0)
    await say(u, f"⚠️ {men(v[0])}: варнов {n}/{WARN_LIMIT}.")

@needs(1)
async def purge(u, ctx, a):
    m = u.message
    r = m.reply_to_message
    if r:
        ids = list(range(r.message_id, m.message_id + 1))
        if await actor_rank(u, ctx) < 2:
            ids = ids[-50:]
    else:
        n = amt_of(a[0]) if a else None
        if not n:
            await m.reply_text("Чистка 20 — удалить последние 20 сообщений\nили ответом: Чистка")
            return
        ids = [i for i in range(m.message_id - min(n, 50 if await actor_rank(u, ctx) < 2 else 500), m.message_id + 1) if i > 0]
    for i in range(0, len(ids), 100):
        try:
            await ctx.bot.delete_messages(m.chat_id, ids[i:i + 100])
        except Exception:
            pass
    await ctx.bot.send_message(m.chat_id, "🧹 Чистка выполнена.")

@needs(1)
async def delmsg(u, ctx, a):
    m = u.message
    if not m.reply_to_message:
        await m.reply_text("Ответьте на сообщение: Удалить")
        return
    try:
        await m.reply_to_message.delete()
        await m.delete()
    except Exception as e:
        await fail(u, e)

@needs(2)
async def pin(u, ctx, a):
    r = u.message.reply_to_message
    if not r:
        await u.message.reply_text("Ответьте на сообщение: Закреп")
        return
    try:
        await ctx.bot.pin_chat_message(u.effective_chat.id, r.message_id)
    except Exception as e:
        await fail(u, e)

@needs(2)
async def unpin(u, ctx, a):
    r = u.message.reply_to_message
    try:
        await ctx.bot.unpin_chat_message(u.effective_chat.id, r.message_id if r else None)
    except Exception as e:
        await fail(u, e)

@needs(3)
async def silence(u, ctx, a):
    on = a and a[0].lower() in ("вкл", "on", "1")
    off = a and a[0].lower() in ("выкл", "off", "0")
    if not (on or off):
        await u.message.reply_text("Тишина вкл — писать могут только админы\nТишина выкл — вернуть чат")
        return
    try:
        if on:
            await ctx.bot.set_chat_permissions(u.effective_chat.id, ChatPermissions(can_send_messages=False))
            await u.message.reply_text("🤫 Режим тишины включён. Пишут только админы.")
        else:
            chat = await ctx.bot.get_chat(u.effective_chat.id)
            await ctx.bot.set_chat_permissions(u.effective_chat.id, full_perms(chat))
            await u.message.reply_text("🔊 Режим тишины выключен.")
    except Exception as e:
        await fail(u, e)

@needs(4)
async def antilink_cmd(u, ctx, a):
    cid = str(u.effective_chat.id)
    if a and a[0].lower() in ("вкл", "on"):
        meta["antilink"][cid] = True
        save()
        await u.message.reply_text("🔗 Антиссылки включены: ссылки от обычных участников удаляются.")
    elif a and a[0].lower() in ("выкл", "off"):
        meta["antilink"].pop(cid, None)
        save()
        await u.message.reply_text("🔗 Антиссылки выключены.")
    else:
        st = "включены" if meta["antilink"].get(cid) else "выключены"
        await u.message.reply_text(f"Антиссылки {st}. Команда: Антиссылки вкл / выкл")

async def antilink(u, ctx):
    m, c = u.message, u.effective_chat
    if not m or c.type not in GROUP or not meta["antilink"].get(str(c.id)):
        return
    ents = list(m.entities or []) + list(m.caption_entities or [])
    if not any(e.type in ("url", "text_link") for e in ents):
        return
    if await is_mod(u, ctx):
        return
    try:
        await m.delete()
    except Exception:
        pass

async def rules(u, ctx, a):
    touch(u)
    r = meta["rules"].get(str(u.effective_chat.id))
    await u.message.reply_text("📜 Правила:\n" + r if r else "Правила не заданы. Админ: Установитьправила текст")

@needs(3)
async def setrules(u, ctx, a):
    try:
        text = u.message.text.split(None, 1)[1].strip()
    except Exception:
        text = ""
    if not text:
        await u.message.reply_text("Установитьправила текст правил")
        return
    meta["rules"][str(u.effective_chat.id)] = text
    save()
    await u.message.reply_text("✅ Правила сохранены. Показать: Правила")

async def info(u, ctx, a):
    uid = touch(u)
    t, rest = await target(u, ctx, a)
    if t == "?":
        await u.message.reply_text("Не знаю такого игрока.")
        return
    t = t or uid
    get(t)
    role = "👑 Владелец бота" if t in owners() else ("🛠 Админ бота" if t in admins() else "Игрок")
    n = meta["warns"].get(str(u.effective_chat.id), {}).get(t, 0)
    if u.effective_chat.type in GROUP:
        rr = await rank_of(ctx, u.effective_chat.id, int(t))
        if rr:
            role += f"\n🎖 Ранг в чате: {rr} — {RN[rr]}"
    await say(u, f"👤 {men(t)}\n🆔 {t}\n💰 Баланс: {bal[t]}\n⚠️ Варнов: {n}/{WARN_LIMIT}\n{role}")

WELCOME_DEF = "👋 Добро пожаловать, {имя}, в {группа}!\nПравила чата: напишите «Правила»."

@needs(3)
async def welcome_cmd(u, ctx, a):
    cid = str(u.effective_chat.id)
    arg = a[0].lower() if a else ""
    if arg in ("выкл", "off") and len(a) == 1:
        meta["welcome"].pop(cid, None)
        save()
        await u.message.reply_text("👋 Приветствие выключено.")
    elif arg in ("вкл", "on") and len(a) == 1:
        meta["welcome"][cid] = meta["welcome"].get(cid) or WELCOME_DEF
        save()
        await u.message.reply_text("👋 Приветствие включено.")
    elif a:
        try:
            text = u.message.text.split(None, 1)[1].strip()
        except Exception:
            text = ""
        meta["welcome"][cid] = text[:1000]
        save()
        await u.message.reply_text("✅ Приветствие сохранено. Проверить: зайдите в чат новым аккаунтом.")
    else:
        w = meta["welcome"].get(cid)
        await u.message.reply_text(
            ("Сейчас: " + w if w else "Приветствие выключено.") +
            "\n\nПриветствие текст — задать (можно {имя} и {группа})\n"
            "Приветствие вкл / выкл")

async def welcome(u, ctx):
    m, c = u.message, u.effective_chat
    if not m or not m.new_chat_members:
        return
    ch = False
    for x in m.new_chat_members:
        ch = rec(x) or ch
    if ch:
        save()
    w = meta["welcome"].get(str(c.id))
    if not w:
        return
    for x in m.new_chat_members:
        if x.is_bot:
            continue
        t = html.escape(w).replace("{имя}", men(x.id)).replace("{группа}", html.escape(c.title or ""))
        try:
            await ctx.bot.send_message(c.id, t, parse_mode="HTML")
        except Exception:
            pass

MOD_HELP = (
    "🛡 Модерация и ранги (в каждом чате свои)\n\n"
    "🎖 Ранги:\n"
    "1 Мл. модератор — Мут (до 1 дня), Варн, Снятьварн, Удалить, Чистка до 50\n"
    "2 Модератор — + Размут, Кик, Бан до 7 дней, Закреп, выдача ранга 1\n"
    "3 Мл. админ — + Бан навсегда, Разбан, Тишина, Правила, Приветствие, выдача рангов до 2\n"
    "4 Админ — + Антиссылки, выдача рангов до 3\n"
    "5 Владелец — создатель группы в Telegram, выдаёт ранги до 4\n\n"
    "Выдать: Ранг @ник 3 · Админ @ник (4) · Младмин @ник (3) · Модер @ник (2) · "
    "Ммодер @ник (1) · Разжаловать @ник (снять)\n"
    "Выдавать и менять можно только ранги ниже своего. Список: Ранги / Кто админ\n\n"
    "Команды:\n"
    "Мут @ник 30м причина (м/ч/д/н, без срока 1 час) · Размут @ник\n"
    "Бан @ник 1д причина (без срока — навсегда) · Разбан @ник · Кик @ник\n"
    "Варн @ник причина (3 варна = бан) · Снятьварн @ник · Варны @ник\n"
    "Чистка 20 · Удалить (ответом) · Закреп / Открепить (ответом)\n"
    "Тишина вкл/выкл · Антиссылки вкл/выкл\n"
    "Установитьправила текст · Правила · Приветствие текст · Инфо @ник\n\n"
    "Игрока можно указать: ответом на сообщение, @ником, именем или ID.")

async def modhelp(u, ctx, a):
    touch(u)
    await u.message.reply_text(MOD_HELP)

# ================= АКТИВНОСТЬ, ТОПЫ, РАЗВЛЕЧЕНИЯ =================
import atexit

ACT_FILE = "act.json"
act = load(ACT_FILE, {"d": {}, "all": {}})
act.setdefault("d", {})
act.setdefault("all", {})
_act_last = [0.0]

def msk(back=0):
    return (datetime.now(timezone.utc) + timedelta(hours=3) - timedelta(days=back)).strftime("%Y-%m-%d")

def save_act():
    keep = {msk(i) for i in range(366)}
    for cid in list(act["d"]):
        for k in [k for k in act["d"][cid] if k not in keep]:
            del act["d"][cid][k]
    try:
        json.dump(act, open(ACT_FILE, "w"))
    except Exception:
        pass
    _act_last[0] = time.time()

atexit.register(save_act)

def count_msg(m):
    c = m.chat
    if c.type not in GROUP or not m.from_user or m.from_user.is_bot:
        return
    cid, uid = str(c.id), str(m.from_user.id)
    day = act["d"].setdefault(cid, {}).setdefault(msk(), {})
    day[uid] = day.get(uid, 0) + 1
    t = act["all"].setdefault(cid, {})
    t[uid] = t.get(uid, 0) + 1
    if time.time() - _act_last[0] > 30:
        save_act()

def act_sum(cid, period):
    cid = str(cid)
    if period == "all":
        return dict(act["all"].get(cid, {}))
    tot = {}
    for i in range({"day": 1, "week": 7, "month": 30}[period]):
        for uid, c in act["d"].get(cid, {}).get(msk(i), {}).items():
            tot[uid] = tot.get(uid, 0) + c
    return tot

PERIODS = {"день": "day", "сегодня": "day", "дня": "day", "неделя": "week", "неделю": "week",
           "недели": "week", "нед": "week", "месяц": "month", "мес": "month",
           "вся": "all", "все": "all", "всё": "all", "всего": "all", "всю": "all"}
PNAME = {"day": "за сегодня", "week": "за 7 дней", "month": "за 30 дней", "all": "за всё время"}
COINW = ("монет", "монеты", "богачи", "деньги", "баланс", "монетам")
MEDAL = {1: "🥇", 2: "🥈", 3: "🥉"}

async def top(u, ctx, a):
    touch(u)
    ws = [x.lower().strip(",.") for x in a]
    if u.effective_chat.type not in GROUP or any(w in COINW for w in ws):
        return await top_coins(u, ctx, a)
    period, lim = "day", 10
    for w in ws:
        if w in PERIODS:
            period = PERIODS[w]
        elif w.isdigit():
            lim = max(1, min(int(w), 30))
    best = sorted(act_sum(u.effective_chat.id, period).items(), key=lambda x: -x[1])[:lim]
    if not best:
        await u.message.reply_text("Пока нет данных: бот считает сообщения с момента добавления в чат.")
        return
    lines = [f"{MEDAL.get(i, str(i) + '.')} {men(k)} — {v}" for i, (k, v) in enumerate(best, 1)]
    await u.message.reply_text(f"🏆 Топ активности {PNAME[period]}:\n" + "\n".join(lines) +
                               "\n\nЕщё: Топ неделя · Топ месяц · Топ вся · Топ 3 · Топ монет",
                               parse_mode="HTML", link_preview_options=NOPREV)

async def stat(u, ctx, a):
    uid = touch(u)
    if u.effective_chat.type not in GROUP:
        return await profile(u, ctx, a)
    t, rest = await target(u, ctx, a)
    if t == "?":
        await u.message.reply_text("Не знаю такого игрока.")
        return
    t = t or uid
    get(t)
    cid = u.effective_chat.id
    n = {p: act_sum(cid, p).get(t, 0) for p in ("day", "week", "month", "all")}
    allt = sorted(act_sum(cid, "all").items(), key=lambda x: -x[1])
    place = next((i for i, (k, _) in enumerate(allt, 1) if k == t), None)
    rr = await rank_of(ctx, cid, int(t))
    lines = [f"📊 {pname(t)}",
             f"Сообщений: сегодня {n['day']} · неделя {n['week']} · месяц {n['month']} · всего {n['all']}"]
    if place:
        lines.append(f"🏆 Место в топе чата: {place}")
    if rr:
        lines.append(f"🎖 Ранг: {rr} — {RN[rr]}")
    lines.append(f"💰 Баланс: {bal[t]} · ⭐ Репутация: {meta['rep'].get(t, 0)}")
    sp = meta["spouse"].get(t)
    if sp:
        lines.append(f"💍 В браке с {pname(sp)}")
    await u.message.reply_text("\n".join(lines))

async def chat_info(u, ctx, a):
    touch(u)
    if u.effective_chat.type not in GROUP:
        await u.message.reply_text("Команда работает в группах.")
        return
    c = u.effective_chat
    try:
        cnt = await ctx.bot.get_chat_member_count(c.id)
    except Exception:
        cnt = "?"
    d, w, mo, al = (sum(act_sum(c.id, p).values()) for p in ("day", "week", "month", "all"))
    cid = str(c.id)
    top3 = sorted(act_sum(c.id, "day").items(), key=lambda x: -x[1])[:3]
    text = (f"📊 <b>Статистика чата «{html.escape(c.title or '')}»</b>\n\n"
            f"👥 Участников: {cnt}\n"
            f"✉️ Сообщений: сегодня {d} · 7 дней {w} · 30 дней {mo} · всего {al}\n"
            f"🎖 В штате: {len(ranks_of(c.id))}\n"
            f"🔗 Антиссылки: {'вкл' if meta['antilink'].get(cid) else 'выкл'} · "
            f"🌊 Антифлуд: {'вкл' if meta['antiflood'].get(cid) else 'выкл'} · "
            f"👋 Приветствие: {'вкл' if meta['welcome'].get(cid) else 'выкл'}")
    if top3:
        text += "\n\n🔥 Топ сегодня: " + " · ".join(f"{MEDAL[i]} {men(k)} {v}" for i, (k, v) in enumerate(top3, 1))
    png = None
    try:
        png = await asyncio.to_thread(make_chart, c.id)
    except Exception:
        pass
    if png:
        await u.message.reply_photo(png, caption=text, parse_mode="HTML")
    else:
        await u.message.reply_text(text, parse_mode="HTML", link_preview_options=NOPREV)

def make_chart(cid):
    """столбчатый график активности чата, как в Ирис (до 365 дней)"""
    import io
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import FuncFormatter
    days = act["d"].get(str(cid), {})
    if not days:
        return None
    first = min(days)
    span = (datetime.strptime(msk(), "%Y-%m-%d") - datetime.strptime(first, "%Y-%m-%d")).days + 1
    n = max(14, min(365, span))
    keys = [msk(i) for i in range(n - 1, -1, -1)]
    vals = [sum(days.get(k, {}).values()) for k in keys]
    fig, ax = plt.subplots(figsize=(10, 4.2), dpi=110)
    fig.patch.set_facecolor("white")
    cols = ["#c5e233"] * n
    for i in range(max(0, n - 8), n - 1):
        cols[i] = "#7ea03c"
    ax.bar(range(n), vals, width=0.88, color=cols)
    # сегодняшний день: рамка = обычный уровень (среднее за прошлые 7 дней), заливка = уже написано
    prev = vals[max(0, n - 8):n - 1]
    usual = max(vals[-1], int(sum(prev) / len(prev))) if prev else vals[-1]
    ax.bar([n - 1], [usual], width=0.88, color="white", edgecolor="#9bb52a", linewidth=1.2)
    ax.bar([n - 1], [vals[-1]], width=0.88, color="#7ea03c")
    ax.yaxis.tick_right()
    ax.yaxis.set_label_position("right")
    ax.set_ylabel("Сообщений", color="#8a8f9c", fontsize=9)
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v / 1000:g}k" if v >= 1000 else f"{v:g}"))
    ax.grid(axis="y", color="#eceef2", linewidth=0.8)
    ax.set_axisbelow(True)
    for sp in ax.spines.values():
        sp.set_visible(False)
    step = max(1, n // 11)
    ticks = list(range(0, n, step))
    labs = []
    for i in ticks:
        y, m, dd = keys[i].split("-")
        labs.append(f"{dd}.{m}" + (f"\n{y}" if i == 0 else ""))
    ax.set_xticks(ticks)
    ax.set_xticklabels(labs, fontsize=8, color="#8a8f9c")
    ax.tick_params(axis="y", labelsize=8, colors="#8a8f9c", length=0)
    ax.tick_params(axis="x", length=0)
    ax.set_xlim(-0.8, n - 0.2)
    ax.set_title(f"Статистика активности за {n} {'день' if n % 10 == 1 and n != 11 else 'дней'}",
                 fontsize=10, color="#5b6070")
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor="white")
    plt.close(fig)
    buf.seek(0)
    return buf

# ---- ники
async def nick_cmd(u, ctx, a):
    uid = touch(u)
    if not a:
        await u.message.reply_text(f"Ваш ник: {pname(uid)}\nСменить: Установитьник Новый ник (сброс — «Установитьник сброс»)")
        return
    n = " ".join(a)[:32].strip()
    if n.lower() == "сброс":
        meta["nicks"].pop(uid, None)
        save()
        await u.message.reply_text("✅ Ник сброшен.")
        return
    meta["nicks"][uid] = n
    save()
    await u.message.reply_text(f"✅ Теперь вы: {n}")

# ---- репутация
async def rep_change(u, ctx, a, delta):
    uid = touch(u)
    res = await resolve(u, ctx, a, "Ответьте на сообщение: +реп")
    if not res:
        return
    t = res[0]
    if t == uid or int(t) == ctx.bot.id:
        await u.message.reply_text("Себе и боту репутацию менять нельзя.")
        return
    left = meta["repcd"].get(uid, 0) + 3600 - time.time()
    if left > 0:
        await u.message.reply_text(f"⏳ Репутацию можно менять раз в час. Ещё {int(left // 60) + 1} мин.")
        return
    meta["repcd"][uid] = time.time()
    meta["rep"][t] = meta["rep"].get(t, 0) + delta
    save()
    await u.message.reply_text(f"{'👍' if delta > 0 else '👎'} Репутация {pname(t)}: {meta['rep'][t]}")

async def rep_plus(u, ctx, a):
    await rep_change(u, ctx, a, 1)

async def rep_minus(u, ctx, a):
    await rep_change(u, ctx, a, -1)

async def rep_show(u, ctx, a):
    uid = touch(u)
    t, _ = await target(u, ctx, a)
    t = uid if not t or t == "?" else t
    await u.message.reply_text(f"⭐ Репутация {pname(t)}: {meta['rep'].get(t, 0)}")

# ---- браки
async def marry(u, ctx, a):
    uid = touch(u)
    t, rest = await target(u, ctx, a)
    if t == "?":
        await u.message.reply_text("Не знаю такого игрока.")
        return
    if not t:
        if rest:  # обычная фраза, не команда
            return
        sp = meta["spouse"].get(uid)
        if sp:
            await u.message.reply_text(f"💍 Вы в браке с {pname(sp)} с {meta['wed'].get(uid, '?')}")
        else:
            await u.message.reply_text("Вы не в браке. Предложить: ответом на сообщение «Брак»")
        return
    if t == uid or int(t) == ctx.bot.id:
        await u.message.reply_text("Выберите другого человека 🙂")
        return
    if uid in meta["spouse"] or t in meta["spouse"]:
        await u.message.reply_text("Кто-то из вас уже в браке. Развод: «Развод».")
        return
    await u.message.reply_text(
        f"💍 {pname(uid)} предлагает брак {pname(t)}!",
        reply_markup=M([[B("💖 Согласиться", callback_data=f"mar:y:{uid}:{t}"),
                         B("💔 Отказаться", callback_data=f"mar:n:{uid}:{t}")]]))

async def divorce(u, ctx, a):
    uid = touch(u)
    sp = meta["spouse"].pop(uid, None)
    if not sp:
        await u.message.reply_text("Вы не в браке.")
        return
    meta["spouse"].pop(sp, None)
    meta["wed"].pop(uid, None)
    meta["wed"].pop(sp, None)
    save()
    await u.message.reply_text(f"💔 {pname(uid)} и {pname(sp)} развелись.")

async def mar_press(q, ctx, uid):
    _, ans, p, t = q.data.split(":")
    if uid != t:
        await q.answer("Это предложение не для вас.", show_alert=True)
        return
    if ans == "n":
        await q.answer()
        await q.edit_message_text(f"💔 {pname(t)} отказал(а) {pname(p)}.")
        return
    if p in meta["spouse"] or t in meta["spouse"]:
        await q.answer("Кто-то уже в браке.", show_alert=True)
        return
    meta["spouse"][p], meta["spouse"][t] = t, p
    meta["wed"][p] = meta["wed"][t] = msk()
    save()
    await q.answer()
    await q.edit_message_text(f"💒 {pname(p)} и {pname(t)} теперь в браке! Совет да любовь 💖")

# ---- развлечения
async def coin(u, ctx, a):
    await u.message.reply_text(random.choice(["🪙 Орёл", "🪙 Решка"]))

async def dice(u, ctx, a):
    await u.message.reply_text(f"🎲 Выпало: {random.randint(1, 6)}")

async def rnd(u, ctx, a):
    nums = [int(x) for x in a if x.lstrip("-").isdigit()][:2]
    lo, hi = (1, nums[0]) if len(nums) == 1 else (min(nums), max(nums)) if len(nums) == 2 else (1, 100)
    if len(nums) == 1 and nums[0] < 1:
        lo, hi = nums[0], 1
    await u.message.reply_text(f"🎰 Число от {lo} до {hi}: {random.randint(lo, hi)}")

async def chance(u, ctx, a):
    if not a:
        return
    await u.message.reply_text(f"🔮 Вероятность того, что {' '.join(a)}: {random.randint(0, 100)}%")

async def choose(u, ctx, a):
    opts = [x.strip() for x in re.split(r"\s+или\s+|,", " ".join(a)) if x.strip()]
    if len(opts) < 2:
        await u.message.reply_text("Пример: Выбери чай или кофе")
        return
    await u.message.reply_text(f"🎯 Я выбираю: {random.choice(opts)}")

BALL = ["Да", "Нет", "Скорее да", "Скорее нет", "Без сомнений", "Даже не думай", "Спроси позже",
        "Знаки говорят «да»", "Перспективы так себе", "Определённо да", "Сомневаюсь"]

async def ball(u, ctx, a):
    if not a:
        return
    await u.message.reply_text(f"🎱 {random.choice(BALL)}")

async def ping(u, ctx, a):
    await u.message.reply_text("🏓 Понг! Бот на связи.")

# ---- антифлуд
_flood = {}

@needs(4)
async def antiflood_cmd(u, ctx, a):
    cid = str(u.effective_chat.id)
    if a and a[0].lower() in ("вкл", "on"):
        meta["antiflood"][cid] = True
        save()
        await u.message.reply_text("🌊 Антифлуд включён: 7 сообщений за 6 секунд = мут на 5 минут.")
    elif a and a[0].lower() in ("выкл", "off"):
        meta["antiflood"].pop(cid, None)
        save()
        await u.message.reply_text("🌊 Антифлуд выключен.")
    else:
        st = "включён" if meta["antiflood"].get(cid) else "выключен"
        await u.message.reply_text(f"Антифлуд {st}. Команда: Антифлуд вкл / выкл")

async def flood(u, ctx):
    m, c = u.message, u.effective_chat
    if not m or c.type not in GROUP or not m.from_user or not meta["antiflood"].get(str(c.id)):
        return
    k, now = (c.id, m.from_user.id), time.time()
    q = [x for x in _flood.get(k, []) if now - x < 6] + [now]
    _flood[k] = q
    if len(q) < 7:
        return
    _flood[k] = []
    if await actor_rank(u, ctx) >= 1:
        return
    try:
        await ctx.bot.restrict_chat_member(c.id, m.from_user.id, ChatPermissions(can_send_messages=False),
                                           until_date=until(300))
        await say(u, f"🌊 {men(m.from_user.id)} в муте на 5 минут за флуд.")
    except Exception:
        pass

# ================= НОВЫЕ КОМАНДЫ (по списку Ирис) =================
import ast, asyncio, operator

# ---- Дуэль на монеты
async def duel(u, ctx, a):
    uid = touch(u)
    res = await resolve(u, ctx, a, "Дуэль @ник 100 (или ответом на сообщение: Дуэль 100)")
    if not res:
        return
    t, amt = res
    if amt is None or amt < 1:
        await u.message.reply_text("Укажите ставку: Дуэль @ник 100")
        return
    if t == uid or int(t) == ctx.bot.id:
        await u.message.reply_text("Выберите другого соперника 🙂")
        return
    get(t)
    if amt > bal[uid]:
        await u.message.reply_text(f"У вас недостаточно монет. Баланс: {bal[uid]}")
        return
    if amt > bal[t]:
        await u.message.reply_text(f"У соперника недостаточно монет (у него {bal[t]}).")
        return
    await u.message.reply_text(
        f"⚔️ {pname(uid)} вызывает {pname(t)} на дуэль!\nСтавка: {amt} 💰",
        reply_markup=M([[B("⚔️ Принять", callback_data=f"duel:y:{uid}:{t}:{amt}"),
                         B("🏳 Отказаться", callback_data=f"duel:n:{uid}:{t}:{amt}")]]))

async def duel_press(q, ctx, uid):
    _, ans, p, t, amt = q.data.split(":")
    amt = int(amt)
    if uid not in (p, t) or (ans == "y" and uid != t):
        await q.answer("Это не ваша дуэль.", show_alert=True)
        return
    if ans == "n":
        await q.answer()
        who = "отказался(ась)" if uid == t else "отозвал(а) вызов"
        await q.edit_message_text(f"🏳 {pname(uid)} {who}.")
        return
    get(p), get(t)
    if bal[p] < amt or bal[t] < amt:
        await q.answer("У кого-то не хватает монет.", show_alert=True)
        await q.edit_message_text("⚠️ Дуэль отменена: не хватает монет.")
        return
    w, l = random.sample([p, t], 2)
    bal[w] += amt
    bal[l] -= amt
    save()
    await q.answer()
    await q.edit_message_text(
        f"⚔️ Дуэль: {pname(p)} vs {pname(t)}\n🏆 Победил {pname(w)} и забирает {amt} 💰\n"
        f"Баланс: {pname(w)} — {bal[w]}, {pname(l)} — {bal[l]}")

# ---- Шипперим
async def ship(u, ctx, a):
    touch(u)
    if u.effective_chat.type not in GROUP:
        await u.message.reply_text("Команда работает в группах.")
        return
    cid = str(u.effective_chat.id)
    pool = [k for k in act["all"].get(cid, {}) if k in meta["names"]]
    if len(pool) < 2:
        await u.message.reply_text("Мало активных участников для шиппинга.")
        return
    x, y = random.sample(pool, 2)
    pct = random.randint(0, 100)
    bar = "❤️" * (pct // 20) + "🖤" * (5 - pct // 20)
    await u.message.reply_text(f"💞 Шипперим: {men(x)} + {men(y)}\nСовместимость: {pct}% {bar}",
                               parse_mode="HTML", link_preview_options=NOPREV)

# ---- Кто (случайный участник)
async def who(u, ctx, a):
    touch(u)
    if u.effective_chat.type not in GROUP:
        await u.message.reply_text("Команда работает в группах.")
        return
    if not a:
        await u.message.reply_text("Пример: Кто сегодня самый умный?")
        return
    cid = str(u.effective_chat.id)
    pool = [k for k in act["all"].get(cid, {}) if k in meta["names"]]
    if not pool:
        await u.message.reply_text("Пока некого выбирать.")
        return
    q = html.escape(" ".join(a).rstrip("?"))
    await u.message.reply_text(f"🎯 Я думаю, что {q} — {men(random.choice(pool))}",
                               parse_mode="HTML", link_preview_options=NOPREV)

# ---- Калькулятор
_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
        ast.Mod: operator.mod, ast.Pow: operator.pow, ast.FloorDiv: operator.floordiv}

def _ev(n):
    if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)):
        return n.value
    if isinstance(n, ast.UnaryOp) and isinstance(n.op, (ast.USub, ast.UAdd)):
        v = _ev(n.operand)
        return -v if isinstance(n.op, ast.USub) else v
    if isinstance(n, ast.BinOp) and type(n.op) in _OPS:
        l, r = _ev(n.left), _ev(n.right)
        if isinstance(n.op, ast.Pow) and (abs(r) > 100 or abs(l) > 1e6):
            raise ValueError("слишком большая степень")
        return _OPS[type(n.op)](l, r)
    raise ValueError("не понял выражение")

async def calc(u, ctx, a):
    touch(u)
    e = " ".join(a).replace("^", "**").replace(",", ".").replace("×", "*").replace("÷", "/").replace(":", "/")
    if not e:
        await u.message.reply_text("Пример: Калькулятор 2+2*2")
        return
    try:
        r = _ev(ast.parse(e, mode="eval").body)
        r = round(r, 10)
        r = int(r) if float(r).is_integer() else r
        await u.message.reply_text(f"🧮 {' '.join(a)} = {r}")
    except ZeroDivisionError:
        await u.message.reply_text("🧮 На ноль делить нельзя 😏")
    except Exception:
        await u.message.reply_text("🧮 Не смог посчитать. Пример: Калькулятор (2+3)*4")

# ---- Русская рулетка на монеты
async def roulette(u, ctx, a):
    uid = touch(u)
    amt = amt_of(a[0], bal[uid]) if a else None
    if amt is None or amt < 1:
        await u.message.reply_text("🔫 Русская рулетка: Рулетка 100\nШанс проиграть 1 из 6, выигрыш +20% от ставки.")
        return
    if amt > bal[uid]:
        await u.message.reply_text(f"Не хватает монет. Баланс: {bal[uid]}")
        return
    if random.randint(1, 6) == 1:
        bal[uid] -= amt
        save()
        await u.message.reply_text(f"💥 Бах! {pname(uid)} проиграл(а) {amt}. Баланс: {bal[uid]}")
    else:
        win = max(1, amt // 5)
        bal[uid] += win
        save()
        await u.message.reply_text(f"😮‍💨 Щёлк... повезло! +{win}. Баланс: {bal[uid]}")

# ---- Таймер
async def timer(u, ctx, a):
    touch(u)
    m = re.fullmatch(r"(\d+)([a-zа-я]+)", a[0].lower()) if a else None
    if not m or m.group(2) not in UNITS:
        await u.message.reply_text("⏱ Пример: Таймер 10м Выключить плиту\nЕдиницы: с, м, ч")
        return
    sec = int(m.group(1)) * UNITS[m.group(2)]
    if not 1 <= sec <= 86400:
        await u.message.reply_text("⏱ Таймер от 1 секунды до 24 часов.")
        return
    note = html.escape(" ".join(a[1:])) or "время вышло"
    mid = u.message.message_id
    await u.message.reply_text(f"⏱ Таймер на {a[0]} запущен.")

    async def fire():
        await asyncio.sleep(sec)
        try:
            await ctx.bot.send_message(u.effective_chat.id, f"⏰ {men(u.effective_user.id)}, {note}!",
                                       parse_mode="HTML", reply_parameters=ReplyParameters(mid, allow_sending_without_reply=True))
        except Exception:
            pass
    t = asyncio.create_task(fire())
    _tasks.add(t)
    t.add_done_callback(_tasks.discard)

_tasks = set()

# ---- ID чата
async def chat_id(u, ctx, a):
    touch(u)
    await u.message.reply_text(f"🆔 ID чата: {u.effective_chat.id}")

NEWCMDS = {"дуэль": duel, "шипперим": ship, "кто": who, "калькулятор": calc, "калк": calc,
           "рулетка": roulette, "таймер": timer, "айдичата": chat_id}

def wrap(fn):
    async def w(u, ctx):
        await sync(u, ctx)
        await fn(u, ctx, ctx.args or [])
    return w

EN = {"stat": stat, "nick": nick_cmd, "marry": marry, "divorce": divorce, "coin": coin,
      "dice": dice, "rand": rnd, "ping": ping, "chatinfo": chat_info, "antiflood": antiflood_cmd,
      "rich": top_coins, "staff": chat_admins, "welcome": welcome_cmd, "mute": mute, "unmute": unmute, "ban": ban, "unban": unban, "kick": kick,
      "warn": warn, "unwarn": unwarn, "warns": warns, "purge": purge, "del": delmsg,
      "pin": pin, "unpin": unpin, "silence": silence, "antilink": antilink_cmd,
      "rules": rules, "setrules": setrules, "info": info, "modhelp": modhelp,
      "menu": menu, "profile": profile, "start": start_, "help": help_, "id": myid, "balance": balance,
      "bonus": bonus, "top": top, "play": play, "give": give,
      "grant": grant, "take": take, "reset": reset, "stats": stats,
      "addadmin": addadmin, "rmadmin": rmadmin,
      "duel": duel, "ship": ship, "who": who, "calc": calc, "roulette": roulette,
      "timer": timer, "chatid": chat_id, "chatstat": chat_info,
}
RU = {"админы": chat_admins, "приветствие": welcome_cmd, "мут": mute, "размут": unmute, "бан": ban, "разбан": unban, "кик": kick,
       "варн": warn, "снятьварн": unwarn, "унварн": unwarn, "варны": warns,
       "чистка": purge, "удалить": delmsg, "закреп": pin, "открепить": unpin,
       "тишина": silence, "антиссылки": antilink_cmd, "правила": rules,
       "установитьправила": setrules, "инфо": info, "модерация": modhelp,
       "меню": menu, "профиль": profile, "старт": start_, "помощь": help_, "айди": myid, "баланс": balance,
      "бонус": bonus, "топ": top, "игра": play, "передать": give,
      "выдать": grant, "забрать": take, "сброс": reset,
      "статистика": stats, "админ": addadmin, "разжаловать": rmadmin}

async def ru(u, ctx):
    p = u.message.text.split()
    f = RU.get(p[0][1:].split("@")[0].lower())
    if f:
        await sync(u, ctx)
        await f(u, ctx, p[1:])

TXT = {"админы": chat_admins, "приветствие": welcome_cmd, "мут": mute, "размут": unmute, "бан": ban, "разбан": unban, "кик": kick,
       "варн": warn, "снятьварн": unwarn, "унварн": unwarn, "варны": warns,
       "чистка": purge, "удалить": delmsg, "закреп": pin, "открепить": unpin,
       "тишина": silence, "антиссылки": antilink_cmd, "правила": rules,
       "установитьправила": setrules, "инфо": info, "модерация": modhelp,
       "меню": menu, "menu": menu, "профиль": profile, "старт": start_, "помощь": help_, "хелп": help_, "айди": myid, "id": myid,
       "баланс": balance, "бонус": bonus, "топ": top, "мины": play, "игра": play,
       "передать": give, "выдать": grant, "забрать": take, "сброс": reset,
       "статистика": stats, "админ": addadmin, "разжаловать": rmadmin}
NEED = {"снять тишину": "g", "приветствие": "g", "мут": "g", "размут": "g", "бан": "g", "разбан": "g", "кик": "g", "варн": "g",
        "снятьварн": "g", "унварн": "g", "варны": "g", "чистка": "g", "удалить": "g",
        "закреп": "g", "открепить": "g", "тишина": "g", "антиссылки": "g", "установитьправила": "g",
        "выдать": "a", "забрать": "a", "сброс": "a", "статистика": "a",
        "админ": "c", "разжаловать": "c"}

async def warns_me(u, ctx, a):
    touch(u)
    n = meta["warns"].get(str(u.effective_chat.id), {}).get(str(u.effective_user.id), 0)
    await u.message.reply_text(f"⚠️ У вас варнов: {n}/{WARN_LIMIT}")

async def silence_off(u, ctx, a):
    await silence(u, ctx, ["выкл"])

TXT2 = {"кто админ": chat_admins, "кто админы": chat_admins, "кто тут": chat_admins,
        "кто я": profile, "кто ты": info, "мой баланс": balance, "мой профиль": profile,
        "мои варны": warns_me, "снять тишину": silence_off}

FUNCMDS = {"топ": top, "актив": top, "богачи": top_coins, "стата": stat, "установитьник": nick_cmd,
           "сменитьник": nick_cmd, "реп": rep_show, "+реп": rep_plus, "-реп": rep_minus,
           "брак": marry, "развод": divorce, "монетка": coin, "кубик": dice, "рандом": rnd,
           "шанс": chance, "выбери": choose, "шар": ball, "пинг": ping, "инфочата": chat_info,
           "антифлуд": antiflood_cmd}
FUNCMDS.update(NEWCMDS)
RU.update(FUNCMDS)
RU.update({"ник": nick_cmd})
TXT.update(FUNCMDS)
TXT2.update({"id чата": chat_id, "ид чата": chat_id, "русская рулетка": roulette, "моя стата": stat, "стата чата": chat_info, "инфо чата": chat_info, "мой брак": marry,
             "мой ник": nick_cmd})
RANKCMDS = {"ранг": rank_cmd, "админ": addadmin, "младмин": addjradmin, "мл.админ": addjradmin,
            "модер": addmod, "модератор": addmod, "ммодер": addjrmod, "млмодер": addjrmod,
            "мл.модер": addjrmod, "разжаловать": rmadmin, "ранги": chat_admins}
RU.update(RANKCMDS)
TXT.update(RANKCMDS)
RANK_NEED = {"антифлуд": 4, "мут": 1, "варн": 1, "снятьварн": 1, "унварн": 1, "варны": 1, "удалить": 1, "чистка": 1,
             "размут": 2, "бан": 2, "кик": 2, "закреп": 2, "открепить": 2,
             "разбан": 3, "тишина": 3, "снять тишину": 3, "установитьправила": 3, "приветствие": 3,
             "антиссылки": 4, "ранг": 2, "админ": 2, "младмин": 2, "мл.админ": 2, "модер": 2,
             "модератор": 2, "ммодер": 2, "млмодер": 2, "мл.модер": 2, "разжаловать": 2}

async def record(u, ctx):
    m = u.message
    if not m:
        return
    ch = rec(m.from_user)
    if m.reply_to_message:
        ch = rec(m.reply_to_message.from_user) or ch
    for e in m.entities or []:
        if e.type == "text_mention" and e.user:
            ch = rec(e.user) or ch
    if ch:
        save()
    count_msg(m)
    await antilink(u, ctx)
    await flood(u, ctx)

async def txt(u, ctx):
    m = u.message
    if not m or not m.text or not u.effective_user:
        return
    p = re.sub(r"^[^\w@+\-]+", "", m.text).split()
    if not p:
        return
    w = p[0].lower().strip("!.,:;")
    f, args = TXT.get(w), p[1:]
    two = " ".join(p[:2]).lower().strip("!?.,:;")
    if two in TXT2:  # команды из двух слов: «кто админ», «кто я»...
        f, args, w = TXT2[two], p[2:], two
    if not f:
        return
    uid = str(u.effective_user.id)
    need = NEED.get(w)
    # без прав — молча игнорируем, чтобы не спамить в обычной переписке
    rn = RANK_NEED.get(w)
    if rn and (u.effective_chat.type not in GROUP or await actor_rank(u, ctx) < rn):
        return
    if need == "g" and (u.effective_chat.type not in GROUP or not await is_mod(u, ctx)):
        return
    if (need == "a" and uid not in admins()) or (need == "o" and uid not in owners()):
        return
    await sync(u, ctx)
    await f(u, ctx, args)

# ---- мини-сайт: /help отдаёт help.html, /health для проверок Render
import threading, http.server

class _Web(http.server.BaseHTTPRequestHandler):
    def _send(self, head=False):
        p = self.path.split("?")[0].rstrip("/")
        ctype, code = "text/html; charset=utf-8", 200
        if p in ("", "/help", "/help.html", "/index.html"):
            try:
                body = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "help.html"), "rb").read()
            except Exception:
                body, code = b"help.html not found", 404
        elif p == "/health":
            body, ctype = b"ok", "text/plain"
        else:
            body, code = b"not found", 404
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if not head:
            self.wfile.write(body)

    def do_GET(self):
        self._send()

    def do_HEAD(self):
        self._send(head=True)

    def log_message(self, *a):
        pass

if os.environ.get("PORT"):
    threading.Thread(target=http.server.ThreadingHTTPServer(("0.0.0.0", int(os.environ["PORT"])), _Web).serve_forever,
                     daemon=True).start()

app = ApplicationBuilder().token(TOKEN).post_init(post_init).build()
for name, fn in EN.items():
    app.add_handler(CommandHandler(name, wrap(fn)))
app.add_handler(MessageHandler(filters.ALL, record), group=-1)
app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome))
app.add_handler(MessageHandler(filters.Regex(r"^/[а-яА-ЯёЁ]"), ru))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, txt))
app.add_handler(CallbackQueryHandler(press))
app.run_polling()
