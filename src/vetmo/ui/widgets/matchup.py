"""Rich-tooltip матчапов (задача B R2): HTML для QToolTip без Qt-импортов.

Контракт DraftService.get_matchup_tooltip(hero_id) -> (strong, weak),
где strong/weak — list[tuple[name, delta_percent]]. Форматтер — чистая
функция (используется и карточками оверлея, и мета-таблицей).
"""

from html import escape

_OK_COLOR = "#3FB68B"
_BAD_COLOR = "#E05661"
_MUTED = "#9AA0AC"

_LIMIT = 5


def _pct(value: object) -> str:
    """«+1,39%» / «−0,42%» / «—» (запятая как десятичный разделитель)."""
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return "—"
    sign = "+" if number >= 0 else "−"
    return f"{sign}{abs(number):.2f}".replace(".", ",") + "%"


def _line(symbol: str, color: str) -> str:
    return (
        f'<div style="color:{color}; font-weight:600; margin-top:4px;">'
        f"{symbol}</div>"
    )


def format_matchup_tooltip(
    hero_name: str | None,
    strong: list[tuple[str, float]] | None,
    weak: list[tuple[str, float]] | None,
) -> str | None:
    """HTML-тултип «Силён против / Слаб против» или None, если пусто."""
    strong = [row for row in (strong or []) if row]
    weak = [row for row in (weak or []) if row]
    if not strong and not weak:
        return None
    parts = [f"<b>{escape(str(hero_name or 'Герой'))}</b>"]
    if strong:
        parts.append(_line("Силён против:", _OK_COLOR))
        parts.extend(
            f"&nbsp;<span style='color:{_MUTED}'>•</span> "
            f"<span style='color:{_OK_COLOR}'>{escape(str(name))}</span> "
            f"<span style='color:{_MUTED}'>( {_pct(delta)} )</span>"
            for name, delta in strong[:_LIMIT]
        )
    if weak:
        parts.append(_line("Слаб против:", _BAD_COLOR))
        parts.extend(
            f"&nbsp;<span style='color:{_MUTED}'>•</span> "
            f"<span style='color:{_BAD_COLOR}'>{escape(str(name))}</span> "
            f"<span style='color:{_MUTED}'>( {_pct(delta)} )</span>"
            for name, delta in weak[:_LIMIT]
        )
    return "<div>" + "<br>".join(parts) + "</div>"
