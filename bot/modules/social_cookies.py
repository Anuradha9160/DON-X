from asyncio import sleep
from os import path as ospath
from contextlib import suppress

from pyrogram import filters
from pyrogram.handlers import MessageHandler
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from .. import bot_loop, user_data
from ..core.config_manager import Config
from ..helper.ext_utils.bot_utils import new_task, update_user_ldata
from ..helper.ext_utils.cookie_utils import (
    SOCIAL_COOKIE_PLATFORMS,
    describe_cookie_report,
    normalize_cookie_file,
    social_cookie_path,
)
from ..helper.ext_utils.db_handler import database
from ..helper.telegram_helper.button_build import ButtonMaker
from ..helper.telegram_helper.message_utils import delete_message, edit_message, send_message

_cookie_handlers = {}


def _menu(user_id):
    buttons = ButtonMaker()
    for key, (label, _) in SOCIAL_COOKIE_PLATFORMS.items():
        buttons.data_button(f"🍪 {label}", f"scookie {key}")
    buttons.data_button("◀️ Close", "scookie close", "footer")
    return buttons.build_menu(2)


def _status(user_id, platform):
    path = social_cookie_path(user_id, platform)
    return ospath.exists(path)


async def _render(message, user_id):
    lines = [
        "<b>🍪 Social Media Cookie Settings</b>",
        "",
        "<blockquote>Upload a Netscape-format <code>cookies.txt</code> for a platform "
        "when that site requires login.</blockquote>",
        "",
    ]
    for key, (label, _) in SOCIAL_COOKIE_PLATFORMS.items():
        state = "✅ Set" if _status(user_id, key) else "❌ Not set"
        lines.append(f"• <b>{label}:</b> {state}")
    lines.append("")
    lines.append("🔒 Cookies are stored per-user. Never share your cookie file.")
    await edit_message(message, "\n".join(lines), _menu(user_id))


async def _wait_for_cookie(client, query, user_id, platform):
    chat_id = query.message.chat.id
    prompt = await edit_message(
        query.message,
        f"<b>🍪 {SOCIAL_COOKIE_PLATFORMS[platform][0]} Cookies</b>\n\n"
        "<blockquote>Send your exported <code>cookies.txt</code> document now.\n"
        "Only Netscape-format cookie exports are accepted.\n"
        "⏱️ Time left: <code>60 sec</code></blockquote>",
        InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data=f"scookie cancel {platform}")]]),
    )

    async def pfunc(_, msg):
        if msg.chat.id != chat_id or not msg.from_user or msg.from_user.id != user_id:
            return
        if not msg.document:
            await msg.reply("❌ Please send the cookie file as a document.")
            return
        name = (msg.document.file_name or "").lower()
        if not (name.endswith(".txt") or "cookie" in name):
            await msg.reply("❌ Please send a Netscape cookies.txt file.")
            return
        path = social_cookie_path(user_id, platform)
        try:
            await msg.download(file_name=path)
            report = normalize_cookie_file(path)
            if report.get("error") or not report.get("total"):
                with suppress(Exception):
                    import os
                    os.remove(path)
                await msg.reply(
                    "❌ Cookies were not saved.\n"
                    f"{describe_cookie_report(report)}"
                )
            else:
                update_user_ldata(user_id, "SOCIAL_COOKIE_FILES", {
                    **user_data.get(user_id, {}).get("SOCIAL_COOKIE_FILES", {}),
                    platform: path,
                })
                await database.update_user_data(user_id)
                await msg.reply(
                    f"✅ <b>{SOCIAL_COOKIE_PLATFORMS[platform][0]} cookies saved.</b>\n"
                    f"{describe_cookie_report(report)}"
                )
        except Exception as e:
            await msg.reply(f"❌ Failed to save cookies: {e}")
        finally:
            _cookie_handlers.pop(user_id, None)
            with suppress(Exception):
                client.remove_handler(*handler)
            await _render(query.message, user_id)

    handler = client.add_handler(
        MessageHandler(
            pfunc,
            filters=filters.create(lambda _, __, m: True),
        ),
        group=-2,
    )
    _cookie_handlers[user_id] = (handler, platform)
    for _ in range(120):
        if user_id not in _cookie_handlers:
            return
        await sleep(0.5)
    _cookie_handlers.pop(user_id, None)
    with suppress(Exception):
        client.remove_handler(*handler)
    await _render(query.message, user_id)


@new_task
async def cookiesettings(client, message):
    if not message.from_user or not message.chat or message.chat.type.value != "private":
        await message.reply("🔒 Please use /cookiesettings in your private chat with the bot.")
        return
    user_id = message.from_user.id
    await send_message(
        message,
        "<b>🍪 Social Media Cookie Settings</b>\n\n"
        "Choose a platform below to add or replace its cookie file.\n\n"
        "Use only cookies you are authorized to provide. Never share exported cookies.",
        _menu(user_id),
    )


@new_task
async def social_cookie_callback(client, query):
    if not query.from_user:
        return
    user_id = query.from_user.id
    data = query.data.split()
    if len(data) < 2:
        return
    await query.answer()
    if len(data) >= 3 and data[1] == "cancel":
        _cookie_handlers.pop(user_id, None)
        await _render(query.message, user_id)
        return
    if data[1] == "back":
        await _render(query.message, user_id)
        return
    if data[1] == "close":
        _cookie_handlers.pop(user_id, None)
        await query.message.delete()
        return
    platform = data[1]
    if platform not in SOCIAL_COOKIE_PLATFORMS:
        return
    if len(data) >= 3 and data[2] == "remove":
        path = social_cookie_path(user_id, platform)
        with suppress(Exception):
            import os
            os.remove(path)
        d = user_data.get(user_id, {}).get("SOCIAL_COOKIE_FILES", {})
        if isinstance(d, dict):
            d.pop(platform, None)
        await database.update_user_data(user_id)
        await _render(query.message, user_id)
        return
    if len(data) >= 3 and data[2] == "upload":
        await _wait_for_cookie(client, query, user_id, platform)
        return
    if _status(user_id, platform):
        buttons = ButtonMaker()
        buttons.data_button("🔄 Replace Cookies", f"scookie {platform} upload")
        buttons.data_button("🗑️ Remove", f"scookie {platform} remove")
        buttons.data_button("◀️ Back", "scookie back", "footer")
        await edit_message(
            query.message,
            f"<b>🍪 {SOCIAL_COOKIE_PLATFORMS[platform][0]}</b>\n\n"
            "Cookie file is already configured. You can replace or remove it.",
            buttons.build_menu(2),
        )
    else:
        await _wait_for_cookie(client, query, user_id, platform)


# callback aliases handled through the same function
