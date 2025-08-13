import os

MAX_HORAS = int(os.getenv("MAX_HORAS", "24"))
MAX_TOTAL_ITEMS = int(os.getenv("MAX_TOTAL_ITEMS", "200"))

REDDIT_SUBREDDITS = ["technology", "Futurology", "gaming", "es", "Latinoamerica"]
REDDIT_LIMIT = int(os.getenv("REDDIT_LIMIT", "25"))
MAX_ITEMS_REDDIT = int(os.getenv("MAX_ITEMS_REDDIT", "200"))

YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "")
YT_REGIONS = ["ES", "MX", "AR"]
MAX_YT_RESULTS = int(os.getenv("MAX_YT_RESULTS", "10"))

RSS_FEEDS = [
    ("TECNOLOGIA", "Xataka", "https://www.xataka.com/tag/feeds/rss2.xml"),
    ("TECNOLOGIA", "MIT Tech Review", "https://www.technologyreview.com/feed/"),
    ("CIENCIA", "NASA", "https://www.nasa.gov/rss/dyn/breaking_news.rss"),
    ("CULTURA", "Aeon", "https://aeon.co/feed.rss")
]

EXCLUIR_POLITICA = [
    "presidente", "elecciones", "gobierno", "ministro", "candidato", "partido",
    "congreso", "senador", "alcalde", "diputado", "manifestación", "protesta",
    "conflicto armado", "guerra", "bombardeo", "ataque militar", "misil"
]
