"""Small helpers for native Telegram Rich Messages.

Kept separate so normal HTML/Markdown messages remain untouched. Requires
wzgram/pyrogram Rich Message support already used by bot_settings.py.
"""
from pyrogram import raw
from pyrogram.types import (
    InputRichBlockDetails,
    InputRichBlockDivider,
    InputRichBlockList,
    InputRichBlockListItem,
    InputRichBlockParagraph,
    InputRichBlockSectionHeading,
    InputRichBlockTable,
    InputRichBlockTableCell,
    InputRichMessage,
)

RICH_STYLES = {
    "b": raw.types.TextBold,
    "i": raw.types.TextItalic,
    "u": raw.types.TextUnderline,
    "c": raw.types.TextFixed,
    "m": raw.types.TextMarked,
    "s": raw.types.TextStrike,
}


def rich_text(*parts):
    texts = []
    for part in parts:
        if isinstance(part, str):
            texts.append(raw.types.TextPlain(text=part))
        else:
            style, value = part
            style_cls = RICH_STYLES.get(style, raw.types.TextPlain)
            texts.append(style_cls(text=raw.types.TextPlain(text=str(value))))
    return raw.types.TextConcat(texts=texts)


def heading(text, size=3):
    return InputRichBlockSectionHeading(text=rich_text(("b", text)), size=size)


def paragraph(*parts):
    return InputRichBlockParagraph(text=rich_text(*parts))


def divider():
    return InputRichBlockDivider()


def bullet_list(items):
    return InputRichBlockList(
        items=[InputRichBlockListItem(text=rich_text(*item) if isinstance(item, tuple) else rich_text(item))
               for item in items]
    )


def details(summary, blocks):
    return InputRichBlockDetails(summary=rich_text(("b", summary)), blocks=blocks)


def table(headers, rows, title=None):
    table_rows = [
        [InputRichBlockTableCell(text=rich_text(("b", str(cell)))) for cell in headers]
    ]
    table_rows.extend(
        [[InputRichBlockTableCell(text=rich_text(str(cell))) for cell in row] for row in rows]
    )
    return InputRichBlockTable(
        title=rich_text(("b", title)) if title else None,
        rows=table_rows,
        bordered=True,
        striped=True,
        compact=True,
    )


def message(*blocks):
    return InputRichMessage(blocks=list(blocks))
