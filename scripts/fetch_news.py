"""Collect selected RSS/Atom feeds and produce the static dashboard data."""
from __future__ import annotations

import html
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote_plus, urlparse

import feedparser
import requests
from bs4 import BeautifulSoup

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
    "اکوایران": ["https://ecoiran.com/feeds/"],
    "عصر اقتصاد": ["https://asre-eghtesad.com/feed/"],
    "The Economist": ["https://www.economist.com/the-world-this-week/rss.xml", "https://www.economist.com/business/rss.xml", "https://www.economist.com/science-and-technology/rss.xml"],
    "Bloomberg": ["https://feeds.bloomberg.com/technology/news.rss", "https://feeds.bloomberg.com/markets/news.rss", "https://feeds.bloomberg.com/economics/news.rss"],
}

HTML_SOURCES = {
    "شهر سخت‌افزار": "https://www.shahrsakhtafzar.com/fa/",
    "عصر اقتصاد": "https://asre-eghtesad.com/",
}

TOPIC_PRIORITY = {
    "technology": 3, "space": 3, "economy": 3,
    "science": 2, "gaming": 1, "politics": 1, "other": 0,
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


def scrape_homepage(source: str, url: str, headers: dict[str, str], seen: set[str], limit: int = 40) -> list[dict]:
    """Fallback for publishers whose advertised RSS URL returns an HTML page."""
    response = requests.get(url, headers=headers, timeout=35)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    domain = urlparse(url).netloc.removeprefix("www.")
    results = []
    blocked = ("/category/", "/tag/", "/author/", "/page/", "/feed/", "/wp-content/")
    for anchor in soup.select("a[href]"):
        link = anchor.get("href", "").split("#")[0]
        if link.startswith("/"):
            link = url.rstrip("/") + link
        parsed = urlparse(link)
        title = clean(anchor.get_text(" ", strip=True), 180)
        key = re.sub(r"\W", "", title.casefold())
        if (parsed.netloc.removeprefix("www.") != domain or len(title) < 25
                or any(part in parsed.path for part in blocked) or parsed.path in ("", "/")
                or key in seen):
            continue
        container = anchor.find_parent(["article", "li"]) or anchor.parent
        image_url = ""
        picture = container.find("img") if container else None
        if picture:
            image_url = picture.get("data-src") or picture.get("src") or ""
            if image_url.startswith("/"):
                image_url = url.rstrip("/") + image_url
        summary = ""
        paragraph = container.find("p") if container else None
        if paragraph:
            summary = clean(paragraph.get_text(" ", strip=True))
        topic, tags = classify(f"{title} {summary}")
        results.append({"title": title, "summary": summary, "link": link, "source": source,
            "published": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "image": image_url, "topic": topic, "tags": tags,
            "priority": TOPIC_PRIORITY[topic]})
        seen.add(key)
        if len(results) >= limit:
            break
    return results


def is_english(text: str) -> bool:
    letters = re.findall(r"[A-Za-z\u0600-\u06ff]", text)
    return bool(letters) and sum(ch.isascii() for ch in letters) / len(letters) > 0.65


def translate_article(article: dict) -> dict:
    """Translate English cards to Persian; leave the original untouched on any failure."""
    if not is_english(article["title"]):
        return article
    separator = "NABZSEPARATOR"
    original = article["title"] + f"\n\n{separator}\n\n" + article.get("summary", "")[:700]
    try:
        response = requests.get(
            "https://translate.googleapis.com/translate_a/single",
            params={"client": "gtx", "sl": "en", "tl": "fa", "dt": "t", "q": original},
            headers={"User-Agent": "Mozilla/5.0"}, timeout=18,
        )
        response.raise_for_status()
        translated = "".join(piece[0] for piece in response.json()[0] if piece[0])
        title, summary = translated.split(separator, 1)
        article["title"] = clean(title, 180)
        article["summary"] = clean(summary)
        article["translated"] = True
    except (requests.RequestException, ValueError, TypeError, IndexError):
        article["translated"] = False
    return article


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
                    "image": image(entry), "topic": topic, "tags": tags,
                    "priority": TOPIC_PRIORITY[topic]})
                seen.add(key); count += 1
                if count >= MAX_PER_SOURCE: break
        if source in HTML_SOURCES and count < MAX_PER_SOURCE:
            try:
                scraped = scrape_homepage(
                    source, HTML_SOURCES[source], headers, seen,
                    limit=MAX_PER_SOURCE - count,
                )
                articles.extend(scraped)
                count += len(scraped)
            except requests.RequestException as exc:
                print(f"HTML fallback failed for {source}: {exc}")
        status[source] = count
        print(f"{source}: {count}")
    english = [article for article in articles if is_english(article["title"])]
    if english:
        print(f"Translating {len(english)} English articles...")
        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = [pool.submit(translate_article, article) for article in english]
            for future in as_completed(futures):
                future.result()
        print(f"Translated {sum(1 for article in english if article.get('translated'))}/{len(english)} articles")
    articles.sort(key=lambda a: (a["priority"], a["published"]), reverse=True)
    payload = {"updated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"), "articles": articles, "sources": status}
    out = ROOT / "data" / "news.json"; out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved {len(articles)} articles from {len(SOURCES)} sources to {out}")


if __name__ == "__main__": main()
