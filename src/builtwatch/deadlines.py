"""Take-effect dates quoted in a source passage (the server twin of web/deadlines.js).

A date is reported only with the exact phrase it came from, and only when a requirement
or lifecycle word sits right before it ("starting", "effective", "by", "deprecated on").
Publication dates are ignored. Nothing is inferred: no phrase, no date.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

_MONTHS = ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec")
_MON = (
    r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|"
    r"sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\.?"
)
_DATE = re.compile(
    rf"\b(?:{_MON}\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(\d{{4}})"
    rf"|(\d{{1,2}})(?:st|nd|rd|th)?\s+{_MON},?\s+(\d{{4}})"
    r"|(\d{4})-(\d{2})-(\d{2}))\b",
    re.IGNORECASE,
)
# Strong words may sit a few words before the date; short ones ("from", "by") must
# immediately precede it, or "from the FTC's ... Date June 16" would read as a deadline.
_STRONG = (
    r"starting|start(?:s|ing)? on|effective|takes? effect|beginning|begins?|no later than|"
    r"deadline|deprecat\w*|sunset\w*|retir\w*|remov\w*|end[- ]of[- ]life|shut(?:s|ting)? down|"
    r"discontinu\w*|will (?:stop|end|no longer|require|apply)|must|required|enforce\w*"
)
_WEAK = r"from|by|before|until|as of|after|due"
_TRIGGER = re.compile(
    rf"(?:\b(?:{_STRONG})\b[^.;:]{{0,40}}|\b(?:{_WEAK})\s+(?:the\s+)?)$", re.IGNORECASE
)
_PUBLISHED = re.compile(
    r"\b(published|posted|updated|last (?:modified|reviewed)|released|announced|written|"
    r"copyright|dated?)\b[^.;:]{0,30}$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class TakeEffect:
    on: date
    phrase: str


def _month(name: str) -> int:
    return _MONTHS.index(name.lower()[:3]) + 1


def in_text(text: str) -> list[TakeEffect]:
    """Every take-effect date in the text, each with its quoted phrase."""
    found = []
    for match in _DATE.finditer(text or ""):
        groups = match.groups()
        if groups[0]:
            month, day, year = _month(groups[0]), int(groups[1]), int(groups[2])
        elif groups[4]:
            day, month, year = int(groups[3]), _month(groups[4]), int(groups[5])
        else:
            year, month, day = int(groups[6]), int(groups[7]), int(groups[8])
        if not 2000 <= year <= 2100:  # noqa: PLR2004 - plausible regulatory years
            continue
        try:
            on = date(year, month, day)
        except ValueError:
            continue
        before = text[max(0, match.start() - 60) : match.start()]
        trigger = _TRIGGER.search(before)
        if _PUBLISHED.search(before) or not trigger:
            continue
        found.append(TakeEffect(on, " ".join((trigger.group(0) + match.group(0)).split())))
    return found
