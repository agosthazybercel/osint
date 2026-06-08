# OpenIntel OSINT Professional Suite

Lokálisan futó, publikus-webes OSINT dashboard Python/FastAPI alapon.

## Fő funkciók

- Professional dashboard tabokkal: Overview, Identity, Social media, Evidence, Timeline, Network, Media, AI
- Social media intelligence: publikus profil URL-ek, platformeloszlás, bio/metaadat, külső linkek, témák, visibility flags
- Direct username scan: GitHub, GitLab, Reddit, Medium, Dev.to, Kaggle, HuggingFace, npm, Pinterest, TikTok, Instagram, X, YouTube, Threads, Behance, Dribbble stb.
- Identity resolution: candidate clustering, confidence score, profile completeness, false-positive kontroll
- Evidence table: szűrhető, pontozott, magyarázott bizonyítéktábla
- Timeline: dátum-hintek elfogadott forrásokból
- Network graph: célpont ↔ domainek ↔ social platformok ↔ szervezetek/helyek
- Media gallery: zajszűrt kép/videó találatok
- AI Deep Report: OpenAI API-val, alap modell `gpt-5-nano`
- Export: HTML, JSON, Markdown, CSV
- Search history, watchlist, trending local searches

## Fontos korlátok

A program csak publikus, jogszerűen elérhető webes adatokat dolgoz fel. Nem lép be fiókokba, nem kerül meg privacy beállításokat, paywallt vagy rate limitet, és nem használ kiszivárgott/privát adatbázisokat. Személykeresésnél használd saját magadra, hozzájárulással, közszereplőre, újságírói/kutatási célra vagy jogszerű céges átvilágításra.

## Windows telepítés

```bat
install_windows.bat
```

OpenAI kulcs beállítása opcionális, de AI riporthoz kell:

```bat
configure_api_key.bat
```

Indítás:

```bat
run_web.bat
```

Nyisd meg:

```text
http://127.0.0.1:8000
```

## CLI példák

```bat
python cli.py "Agostházy Bercel" --mode person --target-type self --context "Budapesti Piarista Gimnázium" --lawful-use
```

```bat
python cli.py "agosthazyb" --mode username --target-type self --lawful-use
```

```bat
python cli.py "factpress.hu" --mode domain --target-type company --lawful-use
```

## Jobb keresési eredményekhez

Személynél ne mindent egy mezőbe írj. Használd így:

- Primary query: `"Név Vezetéknév"`
- Disambiguation context: `város, iskola, cég, username, domain`
- Mode: `person`
- Target type: `self` / `consented_person` / `public_person`

## API kulcsok

`.env` fájl:

```env
OPENAI_API_KEY=
OPENAI_MODEL=gpt-5-nano
BRAVE_SEARCH_API_KEY=
SERPAPI_KEY=
```

Brave Search vagy SerpAPI kulccsal jelentősen jobb lesz a találati minőség és stabilitás, mint csak DuckDuckGo fallbackkel.
