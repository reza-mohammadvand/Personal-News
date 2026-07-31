"""Collect selected RSS/Atom feeds and produce the static dashboard data."""
from __future__ import annotations

import html
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote_plus, urlparse

import feedparser

ROOT = Path(__file__).resolve().parents[1]
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
MAX_AGE_DAYS = 35
MAX_PER_SOURCE = 60

SOURCES = {
    "زومیت": ["https://www.zoomit.ir/feed/"],
    "زومجی": ["https://www.zoomg.ir/feed/"],
    "تک‌فارس": ["https://techfars.com/feed/"],
    "گجت‌نیوز": ["https://gadgetnews.net/feed/"],
    "دیجیاتو": ["https://digiato.com/feed"],
    "Gadgets 360": ["https://www.gadgets360.com/rss/news"],
    "ویجیاتو": ["https://vigiato.net/feed"],
    "Engadget": ["https://www.engadget.com/rss.xml"],
    "شهر سخت‌افزار": ["https://www.shahrsakhtafzar.com/fa/?format=feed&type=rss"],
    "TechRadar": ["https://www.techradar.com/rss"],
    "Space.com": ["https://www.space.com/feeds/all"],
    "اسپاش": ["https://espash.ir/feed/"],
    "TechCrunch": ["https://techcrunch.com/feed/"],
    "Sky & Telescope": ["https://skyandtelescope.com/feed/"],
    "اکوایران": ["https://ecoiran.com/fa/rss/allnews"],
    "عصر اقتصاد": ["https://asre-eghtesad.com/feed/"],
    "The Economist": ["https://www.economist.com/the-world-this-week/rss.xml", "https://www.economist.com/business/rss.xml", "https://www.economist.com/science-and-technology/rss.xml"],
    "Bloomberg": ["https://feeds.bloomberg.com/technology/news.rss", "https://feeds.bloomberg.com/markets/news.rss", "https://feeds.bloomberg.com/economics/news.rss"],
}

TOPICS = {
    "space": ["فضا", "نجوم", "سیاره", "مریخ", "ماه", "خورشید", "ستاره", "کهکشان", "سیاه چاله", "سیاه‌چاله", "تلسکوپ", "جیمز وب", "هابل", "اسپیس ایکس", "اسپیس‌ایکس", "ماهواره", "فضانورد", "ناسا", "شهاب", "asteroid", "astronomy", "space", "spacex", "nasa", "starship", "telescope", "galaxy", "planet", "exoplanet", "black hole"],
    "economy": ["اقتصاد", "بورس", "بانک", "بیمه", "مالیات", "رمزارز", "بیت کوین", "بیت‌کوین", "طلا", "سکه", "ارز", "مسکن", "تجارت", "بازار", "سرمایه", "fintech", "economy", "economic", "market", "crypto", "bitcoin", "finance", "business", "stock"],
    "gaming": ["بازی", "گیم", "سینما", "فیلم", "سریال", "پلی استیشن", "پلی‌استیشن", "ایکس باکس", "نینتندو", "gaming", "game", "xbox", "playstation", "nintendo", "movie", "cinema"],
    "science": ["علم", "پزشکی", "سلامت", "زیست", "اقلیم", "دانشمند", "پژوهش", "science", "health", "medical", "climate", "biology", "research"],
    "politics": ["سیاست", "دیپلماسی", "دولت", "جنگ", "بین الملل", "بین‌الملل", "politics", "government", "diplomacy", "war", "world"],
    "technology": ["فناوری", "موبایل", "گوشی", "اندروید", "آیفون", "اپل", "سامسونگ", "لپ تاپ", "لپ‌تاپ", "کامپیوتر", "سخت افزار", "سخت‌افزار", "نرم افزار", "نرم‌افزار", "هوش مصنوعی", "امنیت", "هک", "اینترنت", "گجت", "خودرو", "استارتاپ", "technology", "tech", "mobile", "android", "iphone", "apple", "google", "ai", "artificial intelligence", "security", "software", "hardware", "startup", "robot"],
}

TAG_LABELS = {
    "space": "فضا و نجوم", "economy": "اقتصاد", "gaming": "بازی و سرگرمی",
    "science": "علم و سلامت", "politics": "سیاست و جهان", "technology": "فناوری",
}


def clean(value: str | None, limit: int = 260) -> str:
    value = re.sub(r"<[^>]+>", " ", value or "")
    value = html.unescape(re.sub(r"\s+", " ", value)).strip()
    return value[:limit].rstrip() + ("…" if len(value) > limit else "")


def published(entry) -> datetime:
    stamp = entry.get("published_parsed") or entry.get("updated_parsed")
    if stamp:
        return datetime(*stamp[:6], tzinfo=timezone.utc)
    return datetime.now(timezone.utc)


def image(entry) -> str:
    for key in ("media_content", "media_thumbnail"):
        for item in entry.get(key, []):
            if item.get("url"):
                return item["url"].replace("http://", "https://")
    for item in entry.get("enclosures", []):
        if item.get("type", "").startswith("image") and item.get("href"):
            return item["href"].replace("http://", "https://")
    match = re.search(r'<img[^>]+src=["\']([^"\']+)', entry.get("summary", ""), re.I)
    return match.group(1).replace("http://", "https://") if match else ""


def classify(text: str) -> tuple[str, list[str]]:
    lowered = text.casefold().replace("ي", "ی").replace("ك", "ک")
    scores = {topic: sum(1 for word in words if word in lowered) for topic, words in TOPICS.items()}
    ranked = sorted(scores, key=scores.get, reverse=True)
    topic = ranked[0] if scores[ranked[0]] else "other"
    tags = [TAG_LABELS[t] for t in ranked[:2] if scores[t] > 0]
    return topic, tags or ["تازه‌ها"]


def main() -> None:
    cutoff = datetime.now(timezone.utc) - timedelta(days=MAX_AGE_DAYS)
    articles, seen, status = [], set(), {}
    headers = {"User-Agent": "NabzNews/1.0 (+GitHub Pages RSS reader)"}
    for source, feeds in SOURCES.items():
        count = 0
        candidate_feeds = list(feeds)
        domain = urlparse(feeds[0]).netloc.removeprefix("www.")
        candidate_feeds.append(
            "https://news.google.com/rss/search?q="
            + quote_plus(f"site:{domain}")
            + "&hl=fa&gl=IR&ceid=IR:fa"
        )
        for feed_url in candidate_feeds:
            # The final candidate is only a fallback when the publisher feed is empty.
            if "news.google.com" in feed_url and count:
                break
            feed = feedparser.parse(feed_url, request_headers=headers)
            for entry in feed.entries:
                link = entry.get("link", "").split("#")[0]
                title = clean(entry.get("title"), 180)
                date = published(entry)
                key = re.sub(r"\W", "", title.casefold())
                if not link or not title or key in seen or date < cutoff:
                    continue
                summary = clean(entry.get("summary") or entry.get("description"))
                topic, tags = classify(f"{title} {summary}")
                # Keep broad-interest items from the user's hand-picked sources.
                articles.append({"title": title, "summary": summary, "link": link,
                    "source": source, "published": date.isoformat().replace("+00:00", "Z"),
                    "image": image(entry), "topic": topic, "tags": tags})
                seen.add(key); count += 1
                if count >= MAX_PER_SOURCE: break
        status[source] = count
        print(f"{source}: {count}")
    articles.sort(key=lambda a: a["published"], reverse=True)
    payload = {"updated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"), "articles": articles, "sources": status}
    out = ROOT / "data" / "news.json"; out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved {len(articles)} articles from {len(SOURCES)} sources to {out}")


if __name__ == "__main__": main()
