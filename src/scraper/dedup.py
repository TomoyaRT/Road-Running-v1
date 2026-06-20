from __future__ import annotations

from src.scraper.running_biji import RaceEvent, extract_city


def _norm(value: str | None) -> str:
    """正規化字串供比對：繁簡台統一、移除空白。"""
    return (value or "").replace("臺", "台").replace(" ", "").strip()


def _url_key(event: RaceEvent) -> str | None:
    """報名連結正規化（去除 #錨點與結尾斜線）。優先用官方報名站連結。"""
    raw = (event.official_url or event.url or "").split("#")[0].rstrip("/")
    return raw or None


def _triple_key(event: RaceEvent) -> tuple[str, str, object] | None:
    """主辦 + 城市 + 日期；主辦或城市缺漏時回 None（太弱不做模糊合併）。"""
    org = _norm(event.organizer)
    city = _norm(event.city or extract_city(event.location))
    if not org or not city:
        return None
    return (org, city, event.race_date)


def _completeness(event: RaceEvent) -> int:
    """資料完整度分數，重複時保留分數較高者。"""
    return sum(
        bool(x)
        for x in (
            event.image_url,
            event.official_url,
            event.organizer,
            event.categories,
        )
    )


class _Group:
    __slots__ = ("event",)

    def __init__(self, event: RaceEvent) -> None:
        self.event = event


def merge_events(events: list[RaceEvent]) -> list[RaceEvent]:
    """跨來源合併去重。

    主鍵：報名連結 URL（精確）；輔鍵：主辦+城市+日期（URL 不互通時的後備）。
    名稱在各平台常不一致，故不以名稱比對。重複時保留最完整者，保留首次出現順序。

    已知取捨（刻意選擇 URL 主鍵 + 三欄輔鍵）：
    - 輔鍵可能誤併同主辦/同城市/同日的不同賽事（例：同日同地的 5K 與全馬若 URL 不同），
      但這正是 URL 主鍵存在的理由——不同報名連結會先以主鍵區分；只有 URL 無法判定時才退到輔鍵。
    - 單一事件只會歸入一個既有群組（URL 優先），不做傳遞式 union；
      跨群組的傳遞合併情境極罕見，暫不處理（如需嚴格正確可改用 union-find）。
    """
    groups: list[_Group] = []
    by_url: dict[str, _Group] = {}
    by_triple: dict[tuple[str, str, object], _Group] = {}

    for event in events:
        url_key = _url_key(event)
        triple_key = _triple_key(event)
        group = None
        if url_key is not None and url_key in by_url:
            group = by_url[url_key]
        elif triple_key is not None and triple_key in by_triple:
            group = by_triple[triple_key]

        if group is None:
            group = _Group(event)
            groups.append(group)
        elif _completeness(event) > _completeness(group.event):
            group.event = event

        if url_key is not None:
            by_url[url_key] = group
        if triple_key is not None:
            by_triple[triple_key] = group

    return [g.event for g in groups]
