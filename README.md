# Nabz — Personal News Dashboard

Nabz is a lightweight, mobile-friendly Persian news dashboard that follows 18 selected publishers across technology, economy, science, space, astronomy, gaming, entertainment, politics, and Marvel.

The website is fully static. A scheduled GitHub Actions workflow collects the latest stories once a day, translates English titles and summaries into Persian, removes duplicate stories, optimizes article images, and deploys the result to GitHub Pages. No server or database is required.

News and images are not committed to the repository or kept as a permanent archive. They are generated only inside each Pages deployment and replace the previous daily version.

## Features

- Persian RTL interface with responsive mobile layout
- Dark and light themes
- Topic, publisher, date-range, and text filters
- Strict title-only curation: a story is included only when its headline contains a configured topic keyword
- Technology, space, and economy as high-priority topics
- Science, health, and Marvel as medium-priority topics
- Gaming, entertainment, politics, and world news as normal-priority topics
- Automatic English-to-Persian translation with graceful fallback
- Cross-publisher duplicate story removal
- Locally cached and optimized WebP images to avoid broken publisher hotlinks
- RSS feeds with homepage extraction fallbacks for publishers such as Shahr Sakhtafzar and Asr-e Eqtesad

## Deploying to GitHub Pages

1. Push the project to a GitHub repository.
2. Open **Settings → Pages** in the repository.
3. Under **Build and deployment**, set **Source** to **GitHub Actions**.
4. Open the **Actions** tab and run the news deployment workflow once manually.
5. After the workflow finishes, the public URL will appear in the workflow summary and under **Settings → Pages**.

The site will then refresh automatically once per day. Its default date filter shows stories from the last 24 hours.

## Running locally

```powershell
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python scripts\fetch_news.py
python -m http.server 8000
```

Open `http://localhost:8000` in a browser. Sources, headline keywords, and priority levels can be edited in `scripts/fetch_news.py`. Summaries and full article bodies are not used for topic selection.

## Notes

Publishers may change their feeds, restrict automated requests, or place articles behind paywalls. A card always links to the original publisher, and per-source collection counts are available in the GitHub Actions log. Translation and image caching are fault-tolerant: an unavailable third-party response will not prevent the remaining news from being published.
