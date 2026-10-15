from asyncio import gather
from html import escape
from pyrogram.enums import ButtonStyle
from time import monotonic, time
from uuid import uuid4
from re import match
from os import getenv

from aiofiles import open as aiopen
from cloudscraper import create_scraper
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from .. import LOGGER, auth_chats, user_data
from ..core.config_manager import Config
from ..core.tg_client import TgClient
from ..helper.ext_utils.bot_utils import new_task, update_user_ldata
from ..helper.ext_utils.links_utils import decode_slink
from ..helper.ext_utils.status_utils import get_readable_time
from ..helper.ext_utils.db_handler import database
from ..helper.languages import Language
from ..helper.telegram_helper.bot_commands import BotCommands
from ..helper.telegram_helper.button_build import ButtonMaker
from ..helper.telegram_helper.filters import CustomFilters
from ..helper.telegram_helper.tg_utils import chat_info
from ..helper.telegram_helper.message_utils import (
    delete_message,
    edit_message,
    edit_reply_markup,
    send_file,
    send_message,
)


async def _build_start_buttons():
    buttons = ButtonMaker()
    lang = Language()

    # Allow start-menu links and labels to be customized via environment
    # variables. These values are also persisted by deploy.vps for systemd.
    repo_url = getenv("START_REPO_URL", "https://github.com/abhinai2244/CBML").strip()
    repo_label = getenv("START_REPO_BUTTON", lang.START_BUTTON1).strip() or lang.START_BUTTON1
    updates_url = getenv("START_UPDATE_URL", "https://t.me/cantarellabots").strip()
    updates_label = getenv("START_UPDATE_BUTTON", lang.START_BUTTON2).strip() or lang.START_BUTTON2
    dev_url = getenv("START_DEV_URL", "https://t.me/cantarella_wuwa").strip()
    dev_label = getenv("START_DEV_BUTTON", "TENKA IZUMO").strip() or "TENKA IZUMO"

    if repo_url:
        buttons.url_button(repo_label, repo_url, "header")
    if updates_url:
        buttons.url_button(updates_label, updates_url, "header")

    chat_ids = list(auth_chats.keys())
    if Config.AUTHORIZED_CHATS:
        for raw_id in Config.AUTHORIZED_CHATS.split():
            cid = raw_id.split("|")[0].strip()
            try:
                cid_int = int(cid)
                if cid_int not in chat_ids:
                    chat_ids.append(cid_int)
            except ValueError:
                pass

    if chat_ids:
        tasks = [chat_info(cid) for cid in chat_ids]
        chats = await gather(*tasks, return_exceptions=True)
        for idx, (cid, chat) in enumerate(zip(chat_ids, chats), 1):
            if isinstance(chat, Exception) or chat is None:
                title = f"Auth Chat {idx}"
                link = f"https://t.me/c/{str(cid)[4:]}" if str(cid).startswith("-100") else None
            else:
                title = getattr(chat, "title", None) or f"Auth Chat {idx}"
                if getattr(chat, "username", None):
                    link = f"https://t.me/{chat.username}"
                elif getattr(chat, "invite_link", None):
                    link = chat.invite_link
                elif str(cid).startswith("-100"):
                    link = f"https://t.me/c/{str(cid)[4:]}"
                else:
                    link = None

            if link:
                buttons.url_button(title, link, position="default")

    if dev_url:
        buttons.url_button(
            dev_label,
            dev_url,
            position="footer",
            style=ButtonStyle.DANGER,
        )

    return buttons.build_menu(b_cols=3, h_cols=2, f_cols=1)


@new_task
async def start(_, message):
    # Telegram normally supplies from_user for /start, but guard malformed or
    # channel-originated updates so one unusual update cannot break the handler.
    if not message or not getattr(message, "from_user", None):
        return
    userid = message.from_user.id
    user_name = message.from_user.first_name or "User"
    # Some synthetic, edited, or non-command updates can reach this handler
    # without Pyrogram's parsed command list. Normalize it once to avoid
    # TypeError: object of type 'NoneType' has no len().
    command = getattr(message, "command", None) or []
    try:
        reply_markup = await _build_start_buttons()
    except Exception as exc:
        LOGGER.exception("Could not build /start menu: %s", exc)
        reply_markup = None

    # Deep link used by the API manager's group-to-DM button. Accept the
    # plain payload and future api_* payloads, and always open the manager in DM.
    if len(command) > 1 and command[1].split("_", 1)[0].lower() == "api":
        from .api_manager import api_command
        return await api_command(_, message)

    if len(command) > 1 and command[1] in ("wzmlx", "htrx"):
        await delete_message(message)
    elif len(command) > 1 and command[1] != "start":
        decrypted_url = decode_slink(command[1])
        if Config.MEDIA_STORE and decrypted_url.startswith("file"):
            decrypted_url = decrypted_url.replace("file", "")
            chat_id, msg_id = decrypted_url.split("&&")
            LOGGER.info(f"Copying message from {chat_id} & {msg_id} to {userid}")
            return await TgClient.bot.copy_message(
                chat_id=userid,
                from_chat_id=int(chat_id) if match(r"\d+", chat_id) else chat_id,
                message_id=int(msg_id),
                disable_notification=True,
            )
        elif Config.VERIFY_TIMEOUT:
            input_token, pre_uid = decrypted_url.split("&&")
            if int(pre_uid) != userid:
                return await send_message(
                    message,
                    "<blockquote><b>Access Token is not yours!</b>\nPlease generate your own token.</blockquote>",
                )
            data = user_data.get(userid, {})
            if "VERIFY_TOKEN" not in data or data["VERIFY_TOKEN"] != input_token:
                return await send_message(
                    message,
                    "<blockquote><b>Access Token already used!</b>\nPlease generate a new one.</blockquote>",
                )
            elif (
                Config.LOGIN_PASS
                and data["VERIFY_TOKEN"].casefold() == Config.LOGIN_PASS.casefold()
            ):
                return await send_message(
                    message,
                    "<blockquote><b>Bot Already Logged In via Password</b>\nNo need to accept temporary tokens.</blockquote>",
                )
            btn = ButtonMaker()
            btn.data_button(
                "Activate Access Token", f"start pass {input_token}", "header"
            )
            token_markup = btn.build_menu(1)
            msg = f"""<b>🔑 Access Login Token</b>

<blockquote>• <b>Status:</b> Generated Successfully
• <b>Access Token:</b> <code>{input_token}</code>
• <b>Validity:</b> {get_readable_time(int(Config.VERIFY_TIMEOUT))}</blockquote>"""
            return await send_message(message, msg, token_markup)

    help_cmd = BotCommands.HelpCommand[0] if isinstance(BotCommands.HelpCommand, list) else BotCommands.HelpCommand
    if await CustomFilters.authorized(_, message):
        start_string = (
            f"<b>✨ 👋 WELCOME, {escape(user_name)}!</b>\n"
            f"<blockquote>💎 <b>CANTARELLABOTS PREMIUM EXPERIENCE</b>\n"
            f"⚡ Mirror and leech files, torrents, and cloud links with a clean, fast workflow.\n"
            f"🎬 Media • 📁 Documents • ☁️ Cloud Storage</blockquote>\n"
            f"<b>🚀 QUICK START</b>\n"
            f"🧭 Help & commands: /{help_cmd}\n"
            f"💬 Choose an authorized chat button below to get started.\n\n"
            f"<i>🌟 Built for a smoother file-transfer experience.</i>"
        )
        await send_message(message, start_string, reply_markup, photo="IMAGES")
    elif Config.BOT_PM:
        start_string = (
            f"<b>✨ 👋 WELCOME, {escape(user_name)}!</b>\n"
            f"<blockquote>💎 <b>CANTARELLABOTS</b>\n"
            f"📥 Your completed files and links will arrive here in this private chat.\n"
            f"⚡ Ready for your next transfer?</blockquote>\n"
            f"<b>🚀 GET STARTED</b>\n"
            f"🧭 Send /{help_cmd} to explore commands.\n"
            f"💬 Join an authorized chat below to start a task.\n\n"
            f"<i>🌟 Fast, simple, organized.</i>"
        )
        await send_message(
            message,
            start_string,
            reply_markup,
            photo="IMAGES",
        )
    else:
        start_string = (
            f"<b>✨ 👋 WELCOME TO CANTARELLABOTS, {escape(user_name)}!</b>\n"
            f"<blockquote>💎 Mirror and leech files, torrents, and links to Telegram or cloud storage.\n"
            f"🔒 <b>Private access is currently restricted</b> for this bot instance.</blockquote>\n"
            f"<b>🌐 HOW TO CONTINUE</b>\n"
            f"💬 Join one of the authorized chats below, then start your task there.\n"
            f"🧭 Use /{help_cmd} for command guidance.\n\n"
            f"<i>✨ Thanks for stopping by!</i>"
        )
        await send_message(
            message,
            start_string,
            reply_markup,
            photo="IMAGES",
        )
    await database.set_pm_users(userid)


@new_task
async def start_cb(_, query):
    user_id = query.from_user.id
    data = query.data.split()
    if len(data) < 3 or data[0] != "start":
        return await query.answer("Invalid request!", show_alert=True)
    input_token = data[2]
    u_data = user_data.get(user_id, {})

    if input_token == "activated":
        return await query.answer("Already activated!", show_alert=True)
    elif "VERIFY_TOKEN" not in u_data or u_data["VERIFY_TOKEN"] != input_token:
        return await query.answer("Already used! Please generate a new one.", show_alert=True)

    update_user_ldata(user_id, "VERIFY_TOKEN", str(uuid4()))
    update_user_ldata(user_id, "VERIFY_TIME", time())
    if Config.DATABASE_URL:
        await database.update_user_data(user_id)
    await query.answer("Access token activated successfully!", show_alert=True)

    if query.message and query.message.reply_markup and len(query.message.reply_markup.inline_keyboard) > 1:
        kb = query.message.reply_markup.inline_keyboard[1:]
        kb.insert(
            0,
            [InlineKeyboardButton("✅ Activated", callback_data="start pass activated", style=ButtonStyle.SUCCESS)],
        )
        await edit_reply_markup(query.message, InlineKeyboardMarkup(kb))


@new_task
async def login(_, message):
    if Config.LOGIN_PASS is None:
        return await send_message(message, "<blockquote>Login password feature is not enabled.</blockquote>")
    elif len(message.command) > 1:
        user_id = message.from_user.id
        input_pass = message.command[1]

        if user_data.get(user_id, {}).get("VERIFY_TOKEN", "") == Config.LOGIN_PASS:
            return await send_message(
                message, "<blockquote>Already logged in! No need to login again.</blockquote>"
            )

        if input_pass.casefold() != Config.LOGIN_PASS.casefold():
            return await send_message(
                message, "<blockquote>Incorrect password! Please try again.</blockquote>"
            )

        update_user_ldata(user_id, "VERIFY_TOKEN", Config.LOGIN_PASS)
        if Config.DATABASE_URL:
            await database.update_user_data(user_id)
        return await send_message(
            message, "<blockquote><b>Logged in successfully!</b> You can now use the bot.</blockquote>"
        )
    else:
        await send_message(
            message, "<b>🔑 Bot Login Usage Guide</b>\n\n<blockquote><code>/login [password]</code></blockquote>"
        )


@new_task
async def ping(_, message):
    start_time = monotonic()
    reply = await send_message(message, "<b>Pinging bot server...</b>")
    end_time = monotonic()
    await edit_message(
        reply, f"<b>🏓 Pong!</b>\n<blockquote><b>Latency:</b> <code>{int((end_time - start_time) * 1000)} ms</code></blockquote>"
    )


@new_task
async def log(_, message):
    uid = message.from_user.id
    buttons = ButtonMaker()
    buttons.data_button("Log Disp", f"log {uid} disp")
    buttons.data_button("Web Log", f"log {uid} web")
    buttons.data_button("Close", f"log {uid} close", style=ButtonStyle.DANGER)
    await send_file(message, "log.txt", buttons=buttons.build_menu(2))


@new_task
async def log_cb(_, query):
    data = query.data.split()
    message = query.message
    user_id = query.from_user.id
    if user_id != int(data[1]):
        await query.answer("This menu is not for you!", show_alert=True)
    elif data[2] == "close":
        await query.answer()
        await delete_message(message, message.reply_to_message)
    elif data[2] == "disp":
        await query.answer("Fetching log file...")
        async with aiopen("log.txt", "r") as f:
            content = await f.read()

        def parse(line):
            parts = line.split("] [", 1)
            return f"[{parts[1]}" if len(parts) > 1 else line

        try:
            res, total = [], 0
            for line in reversed(content.splitlines()):
                line = parse(line)
                res.append(line)
                total += len(line) + 1
                if total > 3500:
                    break
            log_content = escape("\n".join(reversed(res)))
            text = f"<b>📜 Recent Log Entries ({len(res)} lines)</b>\n\n<blockquote expandable>{log_content}</blockquote>"

            btn = ButtonMaker()
            btn.data_button("Close", f"log {user_id} close", style=ButtonStyle.DANGER)
            await send_message(message, text, btn.build_menu(1))
            await edit_reply_markup(message, None)
        except Exception as err:
            LOGGER.error(f"TG Log Display Error: {str(err)}")
    elif data[2] == "web":
        boundary = "R1eFDeaC554BUkLF"
        headers = {
            "Content-Type": f"multipart/form-data; boundary=----WebKitFormBoundary{boundary}",
            "Origin": "https://spaceb.in",
            "Referer": "https://spaceb.in/",
            "sec-ch-ua": '"Not-A.Brand";v="99", "Chromium";v="124"',
            "sec-ch-ua-mobile": "?1",
            "sec-ch-ua-platform": '"Android"',
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
            "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36",
        }

        async with aiopen("log.txt", "r") as f:
            content = await f.read()

        data = (
            f"------WebKitFormBoundary{boundary}\r\n"
            f'Content-Disposition: form-data; name="content"\r\n\r\n'
            f"{content}\r\n"
            f"------WebKitFormBoundary{boundary}--\r\n"
        )

        cget = create_scraper().request
        resp = cget("POST", "https://spaceb.in/", headers=headers, data=data)
        if resp.status_code == 200:
            await query.answer("Generating web paste...")
            btn = ButtonMaker()
            btn.url_button("📨 Open Web Log (Spacebin)", resp.url, style=ButtonStyle.PRIMARY)
            await edit_reply_markup(message, btn.build_menu(1))
        else:
            await query.answer("Web paste failed! Check logs.", show_alert=True)
