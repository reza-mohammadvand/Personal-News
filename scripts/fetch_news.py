"""Collect selected RSS/Atom feeds and produce the static dashboard data."""
from __future__ import annotations

import html
import hashlib
import io
import json
import re
import shutil
import socket
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote_plus, urljoin, urlparse

import feedparser
import requests
from bs4 import BeautifulSoup
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
socket.setdefaulttimeout(18)
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
    "Gadget Flow": ["https://thegadgetflow.com/categories/tech-gadgets/"],
    "The Economist": ["https://www.economist.com/the-world-this-week/rss.xml", "https://www.economist.com/business/rss.xml", "https://www.economist.com/science-and-technology/rss.xml"],
    "Bloomberg": ["https://feeds.bloomberg.com/technology/news.rss", "https://feeds.bloomberg.com/markets/news.rss", "https://feeds.bloomberg.com/economics/news.rss"],
}

HTML_SOURCES = {
    "شهر سخت‌افزار": "https://www.shahrsakhtafzar.com/fa/",
}

TOPIC_PRIORITY = {
    "technology": 3, "space": 3, "economy": 3,
    "science": 2, "marvel": 2, "gaming": 1, "politics": 1, "other": 0,
}

TOPICS = {
    "space": ["فضا", "نجوم", "سیاره", "مریخ", "ماه", "خورشید", "ستاره", "کهکشان", "سیاه چاله", "سیاه‌چاله", "تلسکوپ", "جیمز وب", "هابل", "اسپیس ایکس", "اسپیس‌ایکس", "ماهواره", "فضانورد", "ناسا", "شهاب", "asteroid", "astronomy", "space", "spacex", "nasa", "starship", "telescope", "galaxy", "planet", "exoplanet", "black hole"],
    "economy": ["اقتصاد", "بورس", "رمزارز", "بیت کوین", "بیت‌کوین", "طلا", "سکه", "ارز", "مسکن", "تجارت", "بازار", "سرمایه", "fintech", "economy", "economic", "market", "crypto", "bitcoin", "finance", "business", "stock"],
    "marvel": ["مارول", "دنیای سینمایی مارول", "انتقام جویان", "انتقام‌جویان", "مرد عنکبوتی", "مردعنکبوتی", "ددپول", "ولورین", "چهار شگفت انگیز", "چهار شگفت‌انگیز", "دردویل", "کاپیتان آمریکا", "مرد آهنی", "marvel", "mcu", "avengers", "spider-man", "spiderman", "x-men", "fantastic four", "deadpool", "wolverine", "daredevil", "captain america", "iron man"],
    "gaming": ["بازی", "گیم", "سینما", "فیلم", "سریال", "پلی استیشن", "پلی‌استیشن", "ایکس باکس", "gaming", "game", "playstation", "movie", "cinema"],
    "science": ["علم", "پزشکی", "سلامت", "دانشمند", "science"],
    "politics": ["سیاست", "دیپلماسی", "جنگ", "بین الملل", "بین‌الملل", "politics", "government", "diplomacy", "war", "world"],
    "technology": ["فناوری", "موبایل", "گوشی", "اندروید", "آیفون", "اپل", "سامسونگ", "لپ تاپ", "لپ‌تاپ", "کامپیوتر", "سخت افزار", "سخت‌افزار", "نرم افزار", "نرم‌افزار", "هوش مصنوعی", "امنیت", "هک", "اینترنت", "گجت", "خودرو", "استارتاپ", "technology", "tech", "mobile", "android", "iphone", "apple", "google", "ai", "artificial intelligence", "security", "software", "hardware", "startup", "robot"],
}

TAG_LABELS = {
    "space": "فضا و نجوم", "economy": "اقتصاد", "marvel": "مارول", "gaming": "بازی و سرگرمی",
    "science": "علم و سلامت", "politics": "سیاست و جهان", "technology": "فناوری",
}


def clean(value: str | None, limit: int = 260) -> str:
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    elif value is not None and not isinstance(value, str):
        value = str(value)
    value = re.sub(r"<[^>]+>", " ", value or "")
    value = html.unescape(re.sub(r"\s+", " ", value)).strip()
    return value[:limit].rstrip() + ("…" if len(value) > limit else "")


def published(entry) -> datetime:
    stamp = entry.get("published_parsed") or entry.get("updated_parsed")
    if stamp:
        try:
            return datetime(*stamp[:6], tzinfo=timezone.utc)
        except (TypeError, ValueError):
            pass
    return datetime.now(timezone.utc)


def image(entry) -> str:
    base = entry.get("link", "")
    for key in ("media_content", "media_thumbnail"):
        for item in entry.get(key, []):
            if item.get("url"):
                return urljoin(base, item["url"]).replace("http://", "https://")
    for item in entry.get("enclosures", []):
        if item.get("type", "").startswith("image") and item.get("href"):
            return urljoin(base, item["href"]).replace("http://", "https://")
    match = re.search(r'<img[^>]+src=["\']([^"\']+)', entry.get("summary", ""), re.I)
    return urljoin(base, match.group(1)).replace("http://", "https://") if match else ""


def safe_image(entry) -> str:
    try:
        return image(entry)
    except Exception:
        return ""


def build_feed_article(entry, source: str, cutoff: datetime, seen: set[str]):
    """Convert one feed entry without allowing malformed publisher data to stop the run."""
    try:
        link = str(entry.get("link", "")).split("#")[0]
        title = clean(entry.get("title"), 180)
        date = published(entry)
        key = re.sub(r"\W", "", title.casefold())
        if not link or not title or key in seen or date < cutoff:
            return None
        summary = clean(entry.get("summary") or entry.get("description"))
        topic, tags = classify(title)
        if topic == "other":
            return None
        return ({"title": title, "summary": summary, "link": link,
            "source": source, "published": date.isoformat().replace("+00:00", "Z"),
            "image": safe_image(entry), "topic": topic, "tags": tags,
            "priority": TOPIC_PRIORITY[topic]}, key)
    except Exception as exc:
        print(f"Skipped malformed {source} entry: {type(exc).__name__}")
        return None


def classify(text: str) -> tuple[str, list[str]]:
    lowered = text.casefold().replace("ي", "ی").replace("ك", "ک")
    def matches(keyword: str) -> bool:
        keyword = keyword.casefold()
        if keyword.isascii():
            return bool(re.search(rf"(?<![a-z0-9]){re.escape(keyword)}(?![a-z0-9])", lowered))
        return keyword in lowered

    scores = {topic: sum(1 for word in words if matches(word)) for topic, words in TOPICS.items()}
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
        topic, tags = classify(title)
        if topic == "other":
            continue
        results.append({"title": title, "summary": summary, "link": link, "source": source,
            "published": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "image": image_url, "topic": topic, "tags": tags,
            "priority": TOPIC_PRIORITY[topic]})
        seen.add(key)
        if len(results) >= limit:
            break
    return results


def relative_product_date(value: str) -> datetime:
    now = datetime.now(timezone.utc)
    match = re.search(r"(\d+)\s*(minute|hour|day|week|month)", value.casefold())
    if not match:
        return now
    amount = int(match.group(1))
    unit = match.group(2)
    if unit == "minute":
        return now - timedelta(minutes=amount)
    if unit == "hour":
        return now - timedelta(hours=amount)
    days = amount * ({"day": 1, "week": 7, "month": 30}.get(unit, 0))
    return now - timedelta(days=days)


def scrape_gadget_flow(headers: dict[str, str], seen: set[str], limit: int = 60) -> list[dict]:
    """Collect the newest Gadget Flow catalog products without headline filtering."""
    results = []
    base = "https://thegadgetflow.com/categories/tech-gadgets/"
    for page in range(1, 4):
        url = base if page == 1 else f"{base}page/{page}/"
        response = requests.get(url, headers=headers, timeout=(5, 20))
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        for card in soup.select(".gfl-product"):
            heading = card.select_one("h2.gfl-product-title a[href]")
            if not heading:
                continue
            title = clean(heading.get_text(" ", strip=True), 180)
            link = urljoin(url, heading.get("href", "")).split("#")[0]
            key = re.sub(r"\W", "", title.casefold())
            if not title or not link or key in seen:
                continue
            picture = card.select_one("img.gfl-product-thumb-img")
            image_url = ""
            if picture:
                image_url = (picture.get("data-breeze") or picture.get("data-src")
                    or picture.get("src") or "")
                if image_url.startswith("data:"):
                    image_url = ""
            categories = [clean(item.get_text(" ", strip=True), 40)
                for item in card.select(".gfl-product-category-link")]
            price_node = card.select_one(".gfl-product-price")
            price = clean(price_node.get_text(" ", strip=True), 40) if price_node else ""
            age_node = card.select_one(".gfl-product-publisher")
            age = clean(age_node.get_text(" ", strip=True), 40) if age_node else ""
            details = []
            if categories:
                details.append("Categories: " + ", ".join(categories[:3]))
            if price:
                details.append("Price: " + price)
            results.append({"title": title, "summary": " | ".join(details), "link": link,
                "source": "Gadget Flow", "published": relative_product_date(age).isoformat().replace("+00:00", "Z"),
                "image": image_url, "topic": "technology", "tags": ["گجت‌های جدید"],
                "priority": TOPIC_PRIORITY["technology"]})
            seen.add(key)
            if len(results) >= limit:
                return results
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
            headers={"User-Agent": "Mozilla/5.0"}, timeout=(5, 10),
        )
        response.raise_for_status()
        translated = "".join(piece[0] for piece in response.json()[0] if piece[0])
        title, summary = translated.split(separator, 1)
        article["title"] = clean(title, 180)
        article["summary"] = clean(summary)
        article["translated"] = True
    except Exception as exc:
        article["translated"] = False
        article["translation_error"] = type(exc).__name__
    return article


STOP_WORDS = {
    "برای", "این", "آن", "یک", "در", "از", "به", "با", "که", "شد", "شده", "است",
    "های", "روی", "خود", "جدید", "خبر", "the", "and", "for", "with", "from", "this",
    "that", "new", "its", "into", "about", "after", "will", "has", "have",
}


def title_tokens(title: str) -> set[str]:
    normalized = title.casefold().replace("ي", "ی").replace("ك", "ک")
    return {word for word in re.findall(r"[\w\u0600-\u06ff]+", normalized)
            if len(word) > 2 and word not in STOP_WORDS}


def deduplicate_articles(articles: list[dict]) -> list[dict]:
    """Keep one card when translated headlines describe the same story."""
    ordered = sorted(articles, key=lambda a: (a["priority"], a["published"]), reverse=True)
    kept: list[dict] = []
    token_sets: list[set[str]] = []
    links: set[str] = set()
    for article in ordered:
        canonical_link = article["link"].split("?")[0].rstrip("/")
        tokens = title_tokens(article["title"])
        duplicate = canonical_link in links
        if article["source"] != "Gadget Flow" and not duplicate and len(tokens) >= 3:
            for previous in token_sets:
                shared = len(tokens & previous)
                union = len(tokens | previous)
                if shared >= 3 and union and shared / union >= 0.58:
                    duplicate = True
                    break
        if duplicate:
            continue
        kept.append(article)
        token_sets.append(tokens)
        links.add(canonical_link)
    return kept


def cache_image(article: dict, directory: Path, headers: dict[str, str]) -> bool:
    """Cache and optimize an image so publisher hotlink rules cannot break cards."""
    image_url = article.get("image", "")
    if not image_url or image_url.startswith("data:"):
        article["image"] = ""
        return False
    try:
        request_headers = dict(headers)
        request_headers["Referer"] = article["link"]
        response = requests.get(image_url, headers=request_headers, timeout=(4, 7))
        response.raise_for_status()
        if len(response.content) > 8_000_000:
            raise ValueError("image too large")
        with Image.open(io.BytesIO(response.content)) as picture:
            picture.seek(0)
            picture = picture.convert("RGB")
            picture.thumbnail((960, 600), Image.Resampling.LANCZOS)
            name = hashlib.sha1(image_url.encode()).hexdigest()[:20] + ".webp"
            picture.save(directory / name, "WEBP", quality=74, method=4)
        article["image"] = f"data/images/{name}"
        return True
    except Exception:
        article["image"] = ""
        return False


def main() -> None:
    cutoff = datetime.now(timezone.utc) - timedelta(days=MAX_AGE_DAYS)
    articles, seen, status = [], set(), {}
    headers = {"User-Agent": "PersonalNewsDashboard/1.0 (+GitHub Pages reader)"}
    for source, feeds in SOURCES.items():
        if source == "Gadget Flow":
            try:
                products = scrape_gadget_flow(headers, seen, MAX_PER_SOURCE)
                articles.extend(products)
                status[source] = len(products)
                print(f"{source}: {len(products)}")
            except Exception as exc:
                status[source] = 0
                print(f"Gadget Flow failed: {type(exc).__name__}: {exc}")
            continue
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
            try:
                feed = feedparser.parse(feed_url, request_headers=headers)
            except Exception as exc:
                print(f"Feed failed for {source}: {type(exc).__name__}")
                continue
            for entry in feed.entries:
                built = build_feed_article(entry, source, cutoff, seen)
                if not built:
                    continue
                article, key = built
                articles.append(article)
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
            except Exception as exc:
                print(f"HTML fallback failed for {source}: {exc}")
        status[source] = count
        print(f"{source}: {count}")
    english = [article for article in articles if is_english(article["title"])]
    if english:
        print(f"Translating {len(english)} English articles...")
        with ThreadPoolExecutor(max_workers=16) as pool:
            futures = [pool.submit(translate_article, article) for article in english]
            for future in as_completed(futures):
                future.result()
        print(f"Translated {sum(1 for article in english if article.get('translated'))}/{len(english)} articles")
    before = len(articles)
    articles = deduplicate_articles(articles)
    print(f"Removed {before - len(articles)} duplicate stories")

    image_dir = ROOT / "data" / "images"
    if image_dir.exists():
        shutil.rmtree(image_dir)
    image_dir.mkdir(parents=True)
    with ThreadPoolExecutor(max_workers=24) as pool:
        image_jobs = [pool.submit(cache_image, article, image_dir, headers) for article in articles]
        cached = sum(1 for future in as_completed(image_jobs) if future.result())
    print(f"Cached {cached}/{len(articles)} article images")

    articles.sort(key=lambda a: (a["priority"], a["published"]), reverse=True)
    payload = {"updated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"), "articles": articles, "sources": status}
    out = ROOT / "data" / "news.json"; out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved {len(articles)} articles from {len(SOURCES)} sources to {out}")


if __name__ == "__main__": main()
