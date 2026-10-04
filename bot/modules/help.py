import re

from ..helper.ext_utils.bot_utils import COMMAND_USAGE, new_task
from ..helper.ext_utils.help_messages import (
    MIRROR_HELP_DICT,
    CLONE_HELP_DICT,
)
from ..helper.telegram_helper.button_build import ButtonMaker
from ..helper.telegram_helper.message_utils import (
    edit_message,
    delete_message,
    send_message,
)
from ..helper.telegram_helper.rich_utils import (
    bullet_list,
    details,
    divider,
    heading,
    message as rich_message,
    paragraph,
    rich_text,
)
from ..helper.ext_utils.help_messages import help_string


@new_task
async def arg_usage(_, query):
    data = query.data.split()
    message = query.message
    await query.answer()
    if data[1] == "close":
        return await delete_message(message, message.reply_to_message)
    pg_no = int(data[3])
    key = {"m": "mirror", "y": "yt", "c": "clone"}.get(data[2], data[2])

    if data[1] in ("nex", "pre", "back"):
        pages = COMMAND_USAGE.get(key)
        if not pages:
            return
        btn_idx = pg_no + 1
        if 1 <= btn_idx < len(pages):
            await edit_message(message, pages[0], pages[btn_idx])
    elif data[1] in COMMAND_USAGE:
        info = {
            "mirror": ("m", MIRROR_HELP_DICT),
            "clone": ("c", CLONE_HELP_DICT),
        }
        back_key, help_dict = info[data[1]]
        button = ButtonMaker()
        button.data_button("Back", f"help back {back_key} {pg_no}")
        await edit_message(message, help_dict[data[2]], button.build_menu())


@new_task
async def bot_help(_, message):
    # Rich UI is intentionally used only for the main help landing page.
    # Detailed command pages keep their existing HTML formatting.
    lines = []
    for raw_line in help_string.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("<blockquote>"):
            continue
        clean = re.sub(r"</?b>", "", line)
        clean = re.sub(r"<[^>]+>", "", clean)
        if ":" in clean and clean.startswith("/"):
            command, description = clean.split(":", 1)
            lines.append((("c", command.strip()), f":{description}"))
        elif clean:
            lines.append(clean)

    blocks = [
        heading("🚀 HTR-X Help", 2),
        paragraph(
            "Fast command reference. ",
            ("b", "Detailed command pages"),
            " keep the existing interactive navigation.",
        ),
        divider(),
        bullet_list(lines),
        divider(),
        details(
            "💡 Tip",
            [
                paragraph(
                    "Run a command without arguments to open its detailed options."
                )
            ],
        ),
    ]
    try:
        await send_message(message, rich_message(*blocks))
    except Exception:
        # Defensive fallback for older Telegram client builds.
        await send_message(message, help_string)
