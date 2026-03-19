# bot.py - Cinema Plus Bot with Series Management
import asyncio
import aiohttp
import base64
import json
import os
import logging
import re
from typing import Optional, Dict, List, Tuple
from bs4 import BeautifulSoup, Comment

from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, InputMediaPhoto, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

# ----------------------------- CONFIG -----------------------------
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
REPO_OWNER = "ffrrx-2000"
REPO_NAME = "cinema-plas-bot"
BRANCH = "main"

# Files in repo
MAIN_FILE = "index.html"
DISCOVER_FILE = "discover.html"
SERIES_FOLDER = "series"  # مجلد ملفات المسلسلات

TMDB_API_KEY = os.getenv("TMDB_API_KEY")
ADMIN_ID = 5529978863

GITHUB_HEADERS = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3+json"
}

# Markers
MARKERS = {
    "LATEST": ("<!-- START_LATEST -->", "<!-- END_LATEST -->"),
    "DISCOVER": ("<!-- START_DISCOVER -->", "<!-- END_DISCOVER -->"),
    "NEW": ("<!-- START_NEW -->", "<!-- END_NEW -->"),
    "FEATURED": ("<!-- START_FEATURED -->", "<!-- END_FEATURED -->"),
    "4K": ("<!-- START_4K -->", "<!-- END_4K -->"),
    "ARABIC": ("<!-- START_ARABIC -->", "<!-- END_ARABIC -->"),
    "INDIAN": ("<!-- START_INDIAN -->", "<!-- END_INDIAN -->"),
    "OFFERS": ("<!-- START_OFFERS -->", "<!-- END_OFFERS -->"),
    "SERIES": ("<!-- START_SERIES -->", "<!-- END_SERIES -->"),
    "RECENT_EPISODES": ("<!-- START_RECENT_EPISODES -->", "<!-- END_RECENT_EPISODES -->"),
}

SECTION_MARKERS = {
    "الاضافات الأخيرة": "LATEST",
    "الاعمال الجديدة": "NEW",
    "أعمال مميزة": "FEATURED",
    "4K": "4K",
    "افلام عربية": "ARABIC",
    "افلام هندية": "INDIAN",
    "عروض مميزة": "OFFERS",
    "مسلسلات": "SERIES",
}

# ----------------------------- LANGUAGE RULES -----------------------------
# اللغات التي تُكتب بالإنجليزي فقط (كوري، ياباني، صيني، هندي)
FORCE_ENGLISH_LANGUAGES = ['ko', 'ja', 'zh', 'hi', 'ta', 'te', 'ml', 'bn']
FORCE_ENGLISH_COUNTRIES = ['KR', 'JP', 'CN', 'TW', 'HK', 'IN']

# العربية (تُكتب بلغتها الأصلية = العربي)
ARABIC_LANGUAGES = ['ar']
ARABIC_COUNTRIES = ['EG', 'SA', 'AE', 'KW', 'QA', 'BH', 'OM', 'IQ', 'SY', 'LB', 'JO', 'PS', 'YE', 'LY', 'TN', 'DZ', 'MA', 'SD']

# تركيا (تُكتب بلغتها الأصلية = التركي)
TURKISH_COUNTRIES = ['TR']
TURKISH_LANGUAGES = ['tr']

# باقي اللغات الغربية وغيرها تُكتب بلغة العمل الأصلية
WESTERN_COUNTRIES = ['US', 'GB', 'CA', 'AU', 'NZ', 'IE', 'FR', 'DE', 'IT', 'ES', 'PT', 'NL', 'BE', 'AT', 'CH', 'SE', 'NO', 'DK', 'FI', 'PL', 'CZ', 'HU', 'RO', 'GR', 'RU', 'UA', 'MX', 'BR', 'AR', 'CO', 'CL', 'PE']
WESTERN_LANGUAGES = ['en', 'fr', 'de', 'it', 'es', 'pt', 'nl', 'sv', 'no', 'da', 'fi', 'pl', 'cs', 'hu', 'ro', 'el', 'ru', 'uk']

# ----------------------------- GENRE TRANSLATIONS -----------------------------
GENRE_TRANSLATIONS = {
    "Action": "اكشن",
    "Adventure": "مغامرة",
    "Animation": "رسوم متحركة",
    "Comedy": "كوميديا",
    "Crime": "جريمة",
    "Documentary": "وثائقي",
    "Drama": "دراما",
    "Family": "عائلي",
    "Fantasy": "فانتازيا",
    "History": "تاريخي",
    "Horror": "رعب",
    "Music": "موسيقي",
    "Mystery": "غموض",
    "Romance": "رومانسي",
    "Science Fiction": "خيال علمي",
    "Sci-Fi & Fantasy": "خيال علمي وفانتازيا",
    "TV Movie": "فيلم تلفزيوني",
    "Thriller": "اثارة",
    "War": "حرب",
    "Western": "غربي",
    "Action & Adventure": "اكشن ومغامرة",
    "Kids": "اطفال",
    "News": "اخبار",
    "Reality": "واقعي",
    "Soap": "مسلسل درامي",
    "Talk": "حواري",
    "War & Politics": "حرب وسياسة"
}

def translate_genre(genre_name: str) -> str:
    """ترجمة تصنيف واحد من الإنجليزية إلى العربية"""
    return GENRE_TRANSLATIONS.get(genre_name, genre_name)

# ----------------------------- LOGGING -----------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ----------------------------- STATE -----------------------------
user_states = {}

# ----------------------------- TITLE DISPLAY LOGIC -----------------------------
def determine_title_display(data: dict) -> Dict[str, str]:
    """
    تحديد كيفية عرض العناوين بناءً على لغة العمل الأصلية
    القاعدة: كل عمل يُكتب بلغته الأصلية
    ما عدا: الكوري والياباني والصيني والهندي = يُكتب بالإنجليزي
    Returns: {"primary": "...", "secondary": "..." or None}
    """
    original_language = data.get("original_language", "")
    origin_country = data.get("origin_country", [])
    if not origin_country:
        origin_country = data.get("production_countries", [])
        if origin_country:
            origin_country = [c.get("iso_3166_1", "") for c in origin_country]
    
    # العنوان الأصلي
    original_title = data.get("original_name") or data.get("original_title") or ""
    # العنوان الإنجليزي
    english_title = data.get("name") or data.get("title") or ""
    
    result = {"primary": "", "secondary": None}
    
    # 1) الكوري والياباني والصيني والهندي: يُكتب بالإنجليزي فقط
    if original_language in FORCE_ENGLISH_LANGUAGES or any(c in FORCE_ENGLISH_COUNTRIES for c in origin_country):
        result["primary"] = english_title  # الإنجليزي فقط
        result["secondary"] = None
        return result
    
    # 2) المحتوى العربي: يُكتب بالعربي (اللغة الأصلية)
    if original_language in ARABIC_LANGUAGES or any(c in ARABIC_COUNTRIES for c in origin_country):
        result["primary"] = original_title  # العربي (اللغة الأصلية)
        if english_title and english_title != original_title:
            result["secondary"] = english_title
        return result
    
    # 3) المحتوى التركي: يُكتب بالتركي (اللغة الأصلية)
    if original_language in TURKISH_LANGUAGES or any(c in TURKISH_COUNTRIES for c in origin_country):
        result["primary"] = original_title  # التركي (اللغة الأصلية)
        if english_title and english_title != original_title:
            result["secondary"] = english_title
        return result
    
    # 4) المحتوى الإنجليزي والغربي: يُكتب بلغة العمل الأصلية (إنجليزي/فرنسي/إسباني الخ)
    if original_language in WESTERN_LANGUAGES or any(c in WESTERN_COUNTRIES for c in origin_country):
        result["primary"] = original_title  # اللغة الأصلية للعمل
        if english_title and english_title != original_title:
            result["secondary"] = english_title
        return result
    
    # 5) افتراضي: اللغة الأصلية للعمل
    result["primary"] = original_title if original_title else english_title
    if english_title and english_title != original_title and original_title:
        result["secondary"] = english_title
    return result

async def fetch_arabic_title(tmdb_id: str, media_type: str = "tv") -> Optional[str]:
    """جلب العنوان العربي من TMDB"""
    url = f"https://api.themoviedb.org/3/{media_type}/{tmdb_id}?api_key={TMDB_API_KEY}&language=ar"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=20) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("name") or data.get("title")
    except Exception as e:
        logger.exception("Error fetching Arabic title: %s", e)
    return None

# ----------------------------- TMDB HELPERS -----------------------------
async def fetch_tmdb(path: str, language: str = "en") -> Optional[dict]:
    url = f"https://api.themoviedb.org/3{path}?api_key={TMDB_API_KEY}&language={language}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=20) as resp:
                if resp.status == 200:
                    return await resp.json()
                else:
                    logger.error("TMDB returned %s for %s", resp.status, url)
                    return None
    except Exception as e:
        logger.exception("Error fetching TMDB: %s", e)
        return None

async def get_movie(tmdb_id: str):
    return await fetch_tmdb(f"/movie/{tmdb_id}")

async def get_series(tmdb_id: str):
    return await fetch_tmdb(f"/tv/{tmdb_id}")

async def get_series_season(tmdb_id: str, season_number: int):
    return await fetch_tmdb(f"/tv/{tmdb_id}/season/{season_number}")

# ----------------------------- HTML TEMPLATE FOR SERIES -----------------------------
def generate_series_html(tmdb_id: str, episode_links: Dict[str, str]) -> str:
    """
    إنشاء ملف HTML للمسلسل باستخدام القالب
    episode_links: {"1-1": "token", "1-2": "token", ...}
    """
    # تحويل episode_links إلى JavaScript object
    links_js = json.dumps(episode_links, ensure_ascii=False, indent=4)
    
    html_template = f'''<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>صفحة مسلسل</title>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">
<script src="https://cdn.jsdelivr.net/npm/hls.js@latest"></script>
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body, html {{
    height: 100%;
    font-family: "Segoe UI", Tahoma, sans-serif;
    color: #fff;
    background: #000;
    overflow-x: hidden;
  }}

  .movie-page {{
    position: relative;
    width: 100%;
    height: 600px;
    background-size: contain;
    background-repeat: no-repeat;
    background-position: top center;
  }}
  .movie-page::after {{
    content: "";
    position: absolute;
    bottom: 0;
    left: 0;
    width: 100%;
    height: 400px;
    background: linear-gradient(to top, rgba(0,0,0,0.98) 50%, rgba(0,0,0,0) 90%);
    pointer-events: none;
  }}
  .content {{
    position: absolute;
    top: 60%;
    left: 20px;
    right: 20px;
    transform: translateY(-0%);
    z-index: 1;
  }}
  .meta {{
    display: flex;
    flex-direction: column;
    align-items: center;
    font-size: 0.9rem;
    opacity: 0.9;
    margin-bottom: 15px;
  }}
  .imdb {{
    display: flex;
    align-items: center;
    background: #f5c518;
    color: #000;
    padding: 2px 6px;
    border-radius: 4px;
    font-weight: bold;
    margin-bottom: 5px;
  }}
  .imdb img {{ height: 16px; margin-left: 5px; }}
  .sub-meta {{
    display: flex;
    gap: 15px;
    justify-content: center;
  }}
  .controls {{
    display: flex;
    justify-content: space-around;
    align-items: center;
    max-width: 400px;
    margin: 0 auto 20px;
  }}
  .controls .icon-btn {{
    display: flex;
    flex-direction: column;
    align-items: center;
    font-size: 1.2rem;
    cursor: pointer;
    opacity: 0.8;
  }}
  .controls .icon-btn span {{
    font-size: 0.75rem;
    margin-top: 4px;
  }}
  .controls .play-btn {{
    background: #e50914;
    color: #fff;
    padding: 8px 18px;
    border-radius: 20px;
    font-size: 1rem;
    font-weight: bold;
    display: flex;
    align-items: center;
    gap: 6px;
    cursor: pointer;
    opacity: 1;
  }}
  .description-wrapper {{
    display: flex;
    align-items: flex-start;
    gap: 10px;
    font-size: 0.9rem;
    line-height: 1.4;
    margin-bottom: 30px;
  }}
  .rating-box {{
    flex-shrink: 0;
    width: 28px;
    height: 28px;
    border: 1px solid #fff;
    display: flex;
    align-items: center;
    justify-content: center;
    font-weight: bold;
  }}
  .description {{
    flex: 1;
    opacity: 0.9;
  }}
  .cast-section {{
    margin-bottom: 20px;
  }}
  .cast-section h3 {{
    font-size: 1rem;
    margin-bottom: 8px;
    text-align: right;
  }}
  .cast-list {{
    display: flex;
    gap: 10px;
    overflow-x: auto;
    padding-bottom: 5px;
  }}
  .cast-item {{
    flex: 0 0 auto;
    width: 80px;
    text-align: center;
    font-size: 0.75rem;
  }}
  .cast-item img {{
    width: 80px;
    height: 80px;
    object-fit: cover;
    border-radius: 50%;
  }}
  .cast-item .name {{
    margin-top: 4px;
    color: #eee;
  }}

  .video-modal {{
    position: fixed;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    background-color: rgba(0, 0, 0, 0.85);
    z-index: 1000;
    display: none;
    justify-content: center;
    align-items: center;
  }}
  .video-modal.active {{
    display: flex;
  }}
  .video-container {{
    width: auto;
    max-width: 90%;
    max-height: 70vh;
    background-color: #1a1c24;
    border-radius: 8px;
    overflow: hidden;
    box-shadow: 0 0 20px rgba(0, 0, 0, 0.5);
  }}
  .video-header {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 8px 12px;
    background-color: #1a1c24;
    border-bottom: 1px solid #2c2f3a;
  }}
  .video-title {{
    font-weight: bold;
    font-size: 14px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }}
  .close-btn {{
    background: none;
    border: none;
    color: #fff;
    font-size: 20px;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    width: 24px;
    height: 24px;
    margin-right: -5px;
  }}
  .video-player-wrapper {{
    position: relative;
    width: 100%;
    background-color: #000;
  }}
  #videoPlayer {{
    display: block;
    width: 100%;
    max-height: 60vh;
  }}
  .video-controls {{
    position: absolute;
    bottom: 0;
    left: 0;
    width: 100%;
    background: linear-gradient(to top, rgba(0,0,0,0.7), transparent);
    padding: 8px;
    display: flex;
    flex-direction: column;
    direction: ltr;
    transition: opacity 0.3s ease;
    opacity: 1;
    pointer-events: auto;
    z-index: 100;
  }}
  .progress-container {{
    width: 100%;
    height: 3px;
    background-color: rgba(255, 255, 255, 0.3);
    border-radius: 1.5px;
    margin-bottom: 8px;
    cursor: pointer;
  }}
  .progress-bar {{
    height: 100%;
    background-color: #e50914;
    border-radius: 1.5px;
    width: 0%;
  }}
  .control-buttons {{
    display: flex;
    justify-content: space-between;
    align-items: center;
  }}
  .left-controls, .right-controls {{
    display: flex;
    align-items: center;
    gap: 12px;
  }}
  .control-btn {{
    background: none;
    border: none;
    color: #fff;
    cursor: pointer;
    width: 24px;
    height: 24px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 14px;
  }}
  .play-pause-btn {{
    width: 32px;
    height: 32px;
    border-radius: 50%;
    border: 1px solid #e50914;
    display: flex;
    align-items: center;
    justify-content: center;
  }}
  .time-display {{
    font-size: 11px;
    color: #fff;
  }}
  .fullscreen-btn {{
    margin-left: 8px;
  }}
  .video-player-wrapper.fullscreen {{
    position: fixed;
    top: 0;
    left: 0;
    width: 100vw !important;
    height: 100vh !important;
    background: #000;
    z-index: 2000;
  }}
  .video-player-wrapper.fullscreen #videoPlayer {{
    width: 100% !important;
    height: 100% !important;
    max-height: none !important;
    object-fit: contain !important;
  }}

  .trailers-section {{
    margin-top: 40px;
    margin-bottom: 40px;
  }}
  .trailers-section h3 {{
    font-size: 1.2rem;
    margin-bottom: 15px;
    text-align: right;
    color: #fff;
  }}
  .trailers-row {{
    display: flex;
    gap: 12px;
    overflow-x: auto;
    padding-bottom: 5px;
    scroll-behavior: smooth;
    scrollbar-width: none;
  }}
  .trailers-row::-webkit-scrollbar {{
    display: none;
  }}
  .trailer-item {{
    flex: 0 0 auto;
    width: 240px;
    position: relative;
    display: block;
    aspect-ratio: 16/9;
    background-color: #000;
    border-radius: 8px;
    overflow: hidden;
    transition: transform 0.2s;
  }}
  .trailer-item:hover {{
    transform: scale(1.05);
  }}
  .trailer-item img {{
    width: 100%;
    height: 100%;
    object-fit: cover;
  }}
  .trailer-item i.fa-play {{
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    font-size: 36px;
    color: white;
    text-shadow: 0 0 10px rgba(0, 0, 0, 0.5);
  }}

  .seasons-section {{
    margin-top: 40px;
    margin-bottom: 40px;
  }}
  .seasons-section h3 {{
    font-size: 1.3rem;
    margin-bottom: 20px;
    text-align: right;
    color: #fff;
    font-weight: bold;
  }}
  .seasons-row {{
    display: flex;
    gap: 15px;
    overflow-x: auto;
    padding: 10px 0;
    scroll-behavior: smooth;
    scrollbar-width: none;
  }}
  .seasons-row::-webkit-scrollbar {{
    display: none;
  }}
  .season-item {{
    flex: 0 0 auto;
    width: 160px;
    cursor: pointer;
    transition: transform 0.3s ease;
  }}
  .season-item:hover {{
    transform: scale(1.05);
  }}
  .season-poster {{
    width: 100%;
    height: 220px;
    object-fit: cover;
    border-radius: 12px;
    box-shadow: 0 4px 15px rgba(0,0,0,0.3);
  }}
  .season-info {{
    margin-top: 10px;
    text-align: center;
  }}
  .season-title {{
    color: #fff;
    font-size: 1rem;
    font-weight: bold;
    margin-bottom: 5px;
  }}
  .season-episodes {{
    color: #888;
    font-size: 0.85rem;
  }}

  .episodes-section {{
    margin-top: 40px;
    margin-bottom: 40px;
  }}
  .episodes-section h3 {{
    font-size: 1.3rem;
    margin-bottom: 20px;
    text-align: right;
    color: #fff;
    font-weight: bold;
  }}
  .episodes-list {{
    display: none;
  }}
  .episodes-list.active {{
    display: block;
  }}
  .episode-item {{
    display: flex;
    align-items: flex-start;
    background: transparent;
    margin-bottom: 20px;
    padding-bottom: 20px;
    border-bottom: 1px solid #333;
    position: relative;
    cursor: pointer;
    transition: background-color 0.3s ease;
  }}
  .episode-item:hover {{
    background-color: rgba(255, 255, 255, 0.05);
    border-radius: 8px;
  }}
  .episode-content {{
    flex: 1;
    padding-left: 15px;
    text-align: right;
  }}
  .episode-title {{
    color: #fff;
    font-size: 1.2rem;
    font-weight: bold;
    margin-bottom: 10px;
    line-height: 1.3;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }}
  .episode-duration {{
    color: #888;
    font-size: 0.9rem;
    margin-bottom: 10px;
  }}
  .episode-description {{
    color: #ccc;
    font-size: 0.95rem;
    line-height: 1.4;
    margin-bottom: 15px;
  }}
  .episode-description.collapsed {{
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }}
  .show-more {{
    color: #1e90ff;
    cursor: pointer;
    font-weight: bold;
    margin-top: 5px;
    display: inline-block;
  }}
  .episode-thumbnail {{
    width: 120px;
    height: 80px;
    object-fit: cover;
    border-radius: 8px;
    flex-shrink: 0;
  }}

  .recommend-section {{
    margin-top: 40px;
  }}
  .recommend-section h3 {{
    font-size: 1.2em;
    margin-bottom: 10px;
    text-align: right;
  }}
  .recommend-row {{
    display: flex;
    gap: 12px;
    overflow-x: auto;
    padding-bottom: 10px;
    scroll-behavior: smooth;
  }}
  .recommend-card {{
    flex: 0 0 auto;
    width: 140px;
    background-color: #111;
    border-radius: 8px;
    overflow: hidden;
    text-align: center;
    color: #fff;
    transition: transform 0.2s;
  }}
  .recommend-card:hover {{
    transform: scale(1.05);
  }}
  .recommend-card img {{
    width: 100%;
    height: 200px;
    object-fit: cover;
  }}

  .video-player-wrapper.fullscreen .video-controls {{
    opacity: 1;
    pointer-events: auto;
  }}
  .video-controls.hidden {{
    opacity: 0 !important;
    pointer-events: none !important;
  }}
  .controls .icon-btn.active {{
    color: #e50914;
    opacity: 1;
  }}
  .skip-btn {{
    width: 28px;
    height: 28px;
    border-radius: 50%;
    border: 1px solid rgba(255,255,255,0.3);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 12px;
  }}
  .quality-btn {{
    position: relative;
    width: 28px;
    height: 28px;
    border-radius: 50%;
    border: 1px solid rgba(255,255,255,0.3);
    display: none;
    align-items: center;
    justify-content: center;
    font-size: 14px;
  }}
  .quality-menu {{
    position: absolute;
    bottom: 40px;
    right: 0;
    background: rgba(0, 0, 0, 0.95);
    border-radius: 8px;
    padding: 8px 0;
    min-width: 120px;
    display: none;
    flex-direction: column;
    z-index: 1000;
    border: 1px solid rgba(255, 255, 255, 0.2);
  }}
  .quality-menu.active {{
    display: flex;
  }}
  .quality-option {{
    padding: 10px 16px;
    cursor: pointer;
    color: #fff;
    font-size: 13px;
    transition: background-color 0.2s;
    text-align: right;
  }}
  .quality-option:hover {{
    background-color: rgba(255, 255, 255, 0.1);
  }}
  .quality-option.selected {{
    color: #e50914;
    font-weight: bold;
  }}
  .tmdb-logo {{
    margin-bottom: 5px;
    text-align: center;
  }}
  .tmdb-logo img {{
    height: 70px;
    object-fit: contain;
  }}
  * {{
    -webkit-tap-highlight-color: transparent;
  }}
  a, button, div, span {{
    outline: none;
  }}
</style>
</head>
<body>

<div class="movie-page" id="moviePage">
<div class="content">
  <div class="meta">
    <div class="tmdb-logo" id="seriesLogo"></div>
    <div class="imdb">
      <img src="https://upload.wikimedia.org/wikipedia/commons/6/69/IMDB_Logo_2016.svg" alt="IMDb">
      <span id="imdbRating">0.0</span>
    </div>
    <div class="sub-meta">
      <div id="yearGenre"></div>
      <div id="seasons"></div>
    </div>
  </div>

  <div class="controls">
    <div class="icon-btn" title="أعجبني" id="likeBtn"><i class="fa-regular fa-heart"></i><span>أعجبني</span></div>
    <div class="icon-btn" title="مشاهدة لاحقاً" id="watchLaterBtn"><i class="fa-regular fa-bookmark"></i><span>لاحقاً</span></div>
    <div class="play-btn" title="شاهد الآن" id="watchNowBtn"><i class="fa-solid fa-play"></i><span>S1 E1</span></div>
    <div class="icon-btn" title="تحميل"><i class="fa-solid fa-download"></i><span>تحميل</span></div>
    <div class="icon-btn" title="مشاهدة الإعلان"><i class="fa-brands fa-youtube"></i><span>إعلان</span></div>
  </div>

  <div class="description-wrapper">
    <div class="rating-box">R</div>
    <div class="description" id="overview">جاري جلب التفاصيل...</div>
  </div>

  <div class="cast-section">
    <h3>الممثلون</h3>
    <div class="cast-list" id="castList"></div>
  </div>
  
  <div class="trailers-section">
    <h3>الإعلانات</h3>
    <div id="trailersList" class="trailers-row"></div>
  </div>

  <div class="seasons-section">
    <h3>المواسم</h3>
    <div id="seasonsList" class="seasons-row"></div>
  </div>

  <div class="episodes-section">
    <h3>الحلقات</h3>
    <div id="episodesList"></div>
  </div>
  
  <div class="recommend-section">
    <h3>مقترحات</h3>
    <div id="recommendations" class="recommend-row"></div>
  </div>
</div>
</div>

<div class="video-modal" id="videoModal">
<div class="video-container">
  <div class="video-header">
    <div class="video-title" id="videoTitle"></div>
    <button class="close-btn" id="closeVideoBtn">x</button>
  </div>
  <div class="video-player-wrapper" id="videoPlayerWrapper">
    <video id="videoPlayer" playsinline>
      <source src="#" type="video/mp4">
    </video>
    <div class="video-controls" id="videoControls">
      <div class="progress-container" id="progressContainer">
        <div class="progress-bar" id="progressBar"></div>
      </div>
      <div class="control-buttons">
        <div class="left-controls">
          <button class="control-btn skip-btn" id="backwardBtn"><i class="fa-solid fa-backward-step"></i></button>
          <button class="control-btn play-pause-btn" id="playPauseBtn"><i class="fa-solid fa-pause" id="playPauseIcon"></i></button>
          <button class="control-btn skip-btn" id="forwardBtn"><i class="fa-solid fa-forward-step"></i></button>
          <div class="time-display"><span id="currentTime">00:00</span> / <span id="totalTime">00:00</span></div>
        </div>
        <div class="right-controls">
          <button class="control-btn" id="aspectBtn"><i class="fa-solid fa-tv"></i></button>
          <div style="position: relative;">
            <button class="control-btn quality-btn" id="qualityBtn"><i class="fa-solid fa-gear"></i></button>
            <div class="quality-menu" id="qualityMenu"></div>
          </div>
          <button class="control-btn fullscreen-btn" id="fullscreenBtn"><i class="fa-solid fa-expand"></i></button>
        </div>
      </div>
    </div>
  </div>
</div>
</div>

<script>
const API_KEY = "06f120992cfacd7c118f6e7086d23544";
const SERIES_ID = {tmdb_id};

const episodeLinks = {links_js};

// ===== قواعد عرض العناوين =====
// اللغات التي تُكتب بالإنجليزي فقط: كوري، ياباني، صيني، هندي
const FORCE_ENGLISH_LANGUAGES = ['ko', 'ja', 'zh', 'hi', 'ta', 'te', 'ml', 'bn'];
const FORCE_ENGLISH_COUNTRIES = ['KR', 'JP', 'CN', 'TW', 'HK', 'IN'];

function determineTitleDisplay(data, arabicData) {{
  const originalLang = data.original_language || '';
  const originCountry = data.origin_country || [];
  const originalTitle = data.original_name || '';
  const englishTitle = data.name || '';
  
  let primary = '';
  let secondary = null;
  
  // كوري/ياباني/صيني/هندي = إنجليزي فقط
  if (FORCE_ENGLISH_LANGUAGES.includes(originalLang) || originCountry.some(c => FORCE_ENGLISH_COUNTRIES.includes(c))) {{
    primary = englishTitle;
    secondary = null;
  }}
  // باقي اللغات (عربي، تركي، إنجليزي، فرنسي الخ) = اللغة الأصلية
  else {{
    primary = originalTitle || englishTitle;
    if (englishTitle && englishTitle !== originalTitle && originalTitle) {{
      secondary = englishTitle;
    }}
  }}
  
  return {{ primary, secondary }};
}}

let currentSeason = 1;
  let isFullscreen = false;
  let controlsVisible = true;
  let controlsTimeout;
  let hls = null;
  let currentQualityLevels = [];
  let seriesPosterUrl = ''; // متغير لحفظ صورة البوستر
  let currentAspectMode = 0; // لتتبع وضع العرض الحالي
  const aspectModes = ['contain', 'cover', 'fill']; // أوضاع العرض المختلفة

const videoModal = document.getElementById("videoModal");
const watchNowBtn = document.getElementById("watchNowBtn");
const closeVideoBtn = document.getElementById("closeVideoBtn");
const videoPlayer = document.getElementById("videoPlayer");
const playPauseBtn = document.getElementById("playPauseBtn");
const playPauseIcon = document.getElementById("playPauseIcon");
const currentTimeDisplay = document.getElementById("currentTime");
const totalTimeDisplay = document.getElementById("totalTime");
const progressContainer = document.getElementById("progressContainer");
const progressBar = document.getElementById("progressBar");
const fullscreenBtn = document.getElementById("fullscreenBtn");
const aspectBtn = document.getElementById("aspectBtn");
const videoPlayerWrapper = document.getElementById("videoPlayerWrapper");
const videoControls = document.getElementById("videoControls");
const backwardBtn = document.getElementById("backwardBtn");
const forwardBtn = document.getElementById("forwardBtn");
const qualityBtn = document.getElementById("qualityBtn");
const qualityMenu = document.getElementById("qualityMenu");
const likeBtn = document.getElementById("likeBtn");
const watchLaterBtn = document.getElementById("watchLaterBtn");

backwardBtn.addEventListener("click", (e) => {{
  e.stopPropagation();
  videoPlayer.currentTime = Math.max(0, videoPlayer.currentTime - 10);
  resetControlsTimer();
}});

forwardBtn.addEventListener("click", (e) => {{
  e.stopPropagation();
  videoPlayer.currentTime = Math.min(videoPlayer.duration, videoPlayer.currentTime + 10);
  resetControlsTimer();
}});

// جلب بيانات المسلسل
Promise.all([
  fetch(`https://api.themoviedb.org/3/tv/${{SERIES_ID}}?api_key=${{API_KEY}}&language=en`).then(r => r.json()),
  fetch(`https://api.themoviedb.org/3/tv/${{SERIES_ID}}?api_key=${{API_KEY}}&language=ar`).then(r => r.json())
]).then(([enData, arData]) => {{
  const titles = determineTitleDisplay(enData, arData);
  
  // جلب صورة البوستر للخلفية
  fetch(`https://api.themoviedb.org/3/tv/${{SERIES_ID}}/images?api_key=${{API_KEY}}`)
  .then(res => res.json())
  .then(images => {{
  const cleanPoster = images.posters.find(p => p.iso_639_1 === null);
  const imagePath = cleanPoster ? cleanPoster.file_path : enData.poster_path;
  if (imagePath) {{
  document.getElementById("moviePage").style.backgroundImage = `url(https://image.tmdb.org/t/p/original${{imagePath}})`;
  }}
  }});

  // حفظ صورة الخلفية الأفقية (backdrop) لاستخدامها في المشغل
  const backdropPath = enData.backdrop_path;
  if (backdropPath) {{
    seriesPosterUrl = `https://image.tmdb.org/t/p/w1280${{backdropPath}}`;
  }} else if (enData.poster_path) {{
    seriesPosterUrl = `https://image.tmdb.org/t/p/w780${{enData.poster_path}}`;
  }}
  
  document.getElementById("imdbRating").textContent = enData.vote_average.toFixed(1);
  
  // ترجمة التصنيفات إلى العربية
  const genreTranslations = {{
    "Action": "اكشن",
    "Adventure": "مغامرة",
    "Animation": "رسوم متحركة",
    "Comedy": "كوميديا",
    "Crime": "جريمة",
    "Documentary": "وثائقي",
    "Drama": "دراما",
    "Family": "عائلي",
    "Fantasy": "فانتازيا",
    "History": "تاريخي",
    "Horror": "رعب",
    "Music": "موسيقي",
    "Mystery": "غموض",
    "Romance": "رومانسي",
    "Science Fiction": "خيال علمي",
    "Sci-Fi & Fantasy": "خيال علمي وفانتازيا",
    "TV Movie": "فيلم تلفزيوني",
    "Thriller": "اثارة",
    "War": "حرب",
    "Western": "غربي",
    "Action & Adventure": "اكشن ومغامرة",
    "Kids": "اطفال",
    "News": "اخبار",
    "Reality": "واقعي",
    "Soap": "مسلسل درامي",
    "Talk": "حواري",
    "War & Politics": "حرب وسياسة"
  }};
  const genres = enData.genres.map(g => genreTranslations[g.name] || g.name).join(" . ");
  document.getElementById("yearGenre").textContent = `${{enData.first_air_date.slice(0,4)}} . ${{genres}}`;
  document.getElementById("seasons").textContent = `${{enData.number_of_seasons}} مواسم . ${{enData.number_of_episodes}} حلقة`;
  document.getElementById("overview").textContent = arData.overview || enData.overview;
  document.getElementById("videoTitle").textContent = titles.primary;
  
  displaySeasons(enData.seasons);
}});

// جلب الممثلين
fetch(`https://api.themoviedb.org/3/tv/${{SERIES_ID}}/credits?api_key=${{API_KEY}}&language=ar`)
  .then(res => res.json())
  .then(credits => {{
    const castList = document.getElementById("castList");
    credits.cast.slice(0, 10).forEach(member => {{
      const div = document.createElement("div");
      div.className = "cast-item";
      div.innerHTML = `
        <img src="${{member.profile_path ? `https://image.tmdb.org/t/p/w185${{member.profile_path}}` : 'https://g.top4top.io/p_34489upmc7.jpg'}}" alt="${{member.name}}">
        <div class="name">${{member.name}}</div>
      `;
      castList.appendChild(div);
    }});
  }});

function displaySeasons(seasons) {{
  const seasonsList = document.getElementById("seasonsList");
  seasons.forEach(season => {{
    if (season.season_number === 0) return;
    if (!season.air_date) return;
    const seasonAirDate = new Date(season.air_date);
    const currentDate = new Date();
    if (seasonAirDate > currentDate) return;
    if (!season.episode_count || season.episode_count === 0) return;
    
    const seasonItem = document.createElement("div");
    seasonItem.className = "season-item";
    seasonItem.onclick = () => showEpisodes(season.season_number);
    seasonItem.innerHTML = `
      <img src="${{season.poster_path ? `https://image.tmdb.org/t/p/w500${{season.poster_path}}` : 'https://g.top4top.io/p_34489upmc7.jpg'}}" alt="الموسم ${{season.season_number}}" class="season-poster">
      <div class="season-info">
        <div class="season-title">الموسم ${{season.season_number}}</div>
        <div class="season-episodes">${{season.episode_count}} حلقة</div>
      </div>
    `;
    seasonsList.appendChild(seasonItem);
  }});
}}

function showEpisodes(seasonNumber) {{
  currentSeason = seasonNumber;
  const episodesList = document.getElementById("episodesList");
  const allEpisodeLists = episodesList.querySelectorAll('.episodes-list');
  allEpisodeLists.forEach(list => list.classList.remove('active'));
  
  let currentEpisodesList = document.getElementById(`episodes-season-${{seasonNumber}}`);
  
  if (!currentEpisodesList) {{
    currentEpisodesList = document.createElement('div');
    currentEpisodesList.id = `episodes-season-${{seasonNumber}}`;
    currentEpisodesList.className = 'episodes-list';
    
    fetch(`https://api.themoviedb.org/3/tv/${{SERIES_ID}}/season/${{seasonNumber}}?api_key=${{API_KEY}}&language=ar`)
      .then(res => res.json())
      .then(data => {{
        data.episodes.forEach(episode => {{
          const episodeElement = createEpisodeElement(episode, seasonNumber);
          currentEpisodesList.appendChild(episodeElement);
        }});
      }});
    
    episodesList.appendChild(currentEpisodesList);
  }}
  
  currentEpisodesList.classList.add('active');
}}

function createEpisodeElement(episode, seasonNumber) {{
  const episodeItem = document.createElement('div');
  episodeItem.className = 'episode-item';
  
  const stillPath = episode.still_path ? `https://image.tmdb.org/t/p/w300${{episode.still_path}}` : 'https://g.top4top.io/p_34489upmc7.jpg';
  const runtime = episode.runtime || 45;
  const episodeKey = `${{seasonNumber}}-${{episode.episode_number}}`;
  const videoUrl = episodeLinks[episodeKey] || '#';
  const durationText = `${{Math.floor(runtime)}} د`;
  const description = episode.overview || '';
  const shortDescription = description.length > 100 ? description.substring(0, 100) + '...' : description;
  
  episodeItem.innerHTML = `
    <div class="episode-content">
      <div class="episode-title">${{episode.name || `الحلقة ${{episode.episode_number}}`}} | E${{episode.episode_number}}</div>
      <div class="episode-duration">${{durationText}}</div>
      <div class="episode-description collapsed" data-full="${{description}}">
        ${{shortDescription}}
        ${{description.length > 100 ? '<span class="show-more">اظهر المزيد</span>' : ''}}
      </div>
    </div>
    <img src="${{stillPath}}" alt="الحلقة ${{episode.episode_number}}" class="episode-thumbnail">
  `;
  
  episodeItem.addEventListener('click', (e) => {{
    if (!e.target.classList.contains('show-more')) {{
      playEpisode(videoUrl, `الموسم ${{seasonNumber}} - الحلقة ${{episode.episode_number}}`);
    }}
  }});
  
  return episodeItem;
}}

function playEpisode(videoUrl, title) {{
  if (videoUrl === '#') {{
    alert('سيتم توفر الحلقة قريبا');
    return;
  }}
  
  document.getElementById("videoModal").classList.add("active");
  document.getElementById("videoTitle").textContent = title;
  
  // تعيين صورة البوستر كخلفية قبل التشغيل
  if (seriesPosterUrl) {{
    videoPlayer.poster = seriesPosterUrl;
  }}
  
  if (hls) {{
    hls.destroy();
    hls = null;
  }}
  
  if (!videoUrl.startsWith("http")) {{
    videoUrl = `https://stream.mux.com/${{videoUrl}}.m3u8`;
  }}
  
  const isHLS = videoUrl.endsWith('.m3u8');
  
  if (isHLS && Hls.isSupported()) {{
    hls = new Hls({{ enableWorker: true, lowLatencyMode: true }});
    hls.loadSource(videoUrl);
    hls.attachMedia(videoPlayer);
    hls.on(Hls.Events.MANIFEST_PARSED, function(event, data) {{
      currentQualityLevels = data.levels;
      buildQualityMenu();
      qualityBtn.style.display = 'flex';
      videoPlayer.play();
    }});
  }} else if (isHLS && videoPlayer.canPlayType('application/vnd.apple.mpegurl')) {{
    videoPlayer.src = videoUrl;
    videoPlayer.load();
    videoPlayer.play();
    qualityBtn.style.display = 'none';
  }} else {{
    videoPlayer.src = videoUrl;
    videoPlayer.load();
    videoPlayer.play();
    qualityBtn.style.display = 'none';
  }}
  
  showControls();
  resetControlsTimer();
}}

function buildQualityMenu() {{
  qualityMenu.innerHTML = '';
  const autoOption = document.createElement('div');
  autoOption.className = 'quality-option selected';
  autoOption.textContent = 'تلقائي (Auto)';
  autoOption.onclick = function() {{
    if (hls) {{
      hls.currentLevel = -1;
      updateQualitySelection(-1);
      qualityMenu.classList.remove('active');
    }}
  }};
  qualityMenu.appendChild(autoOption);
  
  currentQualityLevels.forEach((level, index) => {{
    const option = document.createElement('div');
    option.className = 'quality-option';
    const height = level.height;
    let qualityName = height + 'p';
    if (height >= 2160) qualityName = '4K';
    else if (height >= 1440) qualityName = '2K';
    else if (height >= 1080) qualityName = '1080p';
    else if (height >= 720) qualityName = '720p';
    option.textContent = qualityName;
    option.onclick = function() {{
      if (hls) {{
        hls.currentLevel = index;
        updateQualitySelection(index);
        qualityMenu.classList.remove('active');
      }}
    }};
    qualityMenu.appendChild(option);
  }});
}}

function updateQualitySelection(selectedIndex) {{
  const options = qualityMenu.querySelectorAll('.quality-option');
  options.forEach((option, index) => {{
    option.classList.remove('selected');
    if (index === selectedIndex + 1) option.classList.add('selected');
    else if (selectedIndex === -1 && index === 0) option.classList.add('selected');
  }});
}}

qualityBtn.addEventListener('click', function(e) {{
  e.stopPropagation();
  qualityMenu.classList.toggle('active');
  resetControlsTimer();
}});

// الإعلانات
fetch(`https://api.themoviedb.org/3/tv/${{SERIES_ID}}/videos?api_key=${{API_KEY}}`)
  .then(res => res.json())
  .then(data => {{
    const trailersList = document.getElementById("trailersList");
    const youtubeTrailers = data.results.filter(v => v.site === "YouTube" && (v.type === "Trailer" || v.type === "Teaser")).slice(0, 3);
    if (youtubeTrailers.length === 0) {{
      document.querySelector('.trailers-section').style.display = 'none';
      return;
    }}
    youtubeTrailers.forEach(trailer => {{
      const el = document.createElement("a");
      el.href = `https://www.youtube.com/watch?v=${{trailer.key}}`;
      el.target = "_blank";
      el.className = "trailer-item";
      el.innerHTML = `<img src="https://img.youtube.com/vi/${{trailer.key}}/maxresdefault.jpg" alt="${{trailer.name}}" onerror="this.src='https://img.youtube.com/vi/${{trailer.key}}/hqdefault.jpg'"/><i class="fa-solid fa-play"></i>`;
      trailersList.appendChild(el);
    }});
  }});

setTimeout(() => showEpisodes(1), 1000);

watchNowBtn.addEventListener("click", () => {{
  if (episodeLinks["1-1"]) {{
    playEpisode(episodeLinks["1-1"], "الموسم 1 - الحلقة 1");
  }} else {{
    alert('لا توجد حلقات متاحة للتشغيل');
  }}
}});

closeVideoBtn.addEventListener("click", () => {{
  videoModal.classList.remove("active");
  videoPlayer.pause();
  if (hls) {{ hls.destroy(); hls = null; }}
}});

videoModal.addEventListener("click", (e) => {{
  if (e.target === videoModal) {{
    videoModal.classList.remove("active");
    videoPlayer.pause();
    if (hls) {{ hls.destroy(); hls = null; }}
  }}
}});

function togglePlay(e) {{
  if (e) e.stopPropagation();
  if (videoPlayer.paused) {{
    videoPlayer.play();
    playPauseIcon.classList.remove("fa-play");
    playPauseIcon.classList.add("fa-pause");
  }} else {{
    videoPlayer.pause();
    playPauseIcon.classList.remove("fa-pause");
    playPauseIcon.classList.add("fa-play");
  }}
  resetControlsTimer();
}}

playPauseBtn.addEventListener("click", togglePlay);

videoPlayer.addEventListener("timeupdate", () => {{
  const currentTime = videoPlayer.currentTime;
  const duration = videoPlayer.duration;
  if (isNaN(duration)) return;
  progressBar.style.width = `${{(currentTime / duration) * 100}}%`;
  currentTimeDisplay.textContent = formatTime(currentTime);
  totalTimeDisplay.textContent = formatTime(duration);
}});

progressContainer.addEventListener("click", (e) => {{
  e.stopPropagation();
  const width = progressContainer.offsetWidth;
  const clickX = e.offsetX;
  videoPlayer.currentTime = (clickX / width) * videoPlayer.duration;
  resetControlsTimer();
}});

function formatTime(time) {{
  const m = Math.floor(time / 60);
  const s = Math.floor(time % 60);
  return `${{m < 10 ? '0' + m : m}}:${{s < 10 ? '0' + s : s}}`;
}}

fullscreenBtn.addEventListener("click", function(e) {{
  e.stopPropagation();
  toggleFullscreen();
}});

function toggleFullscreen() {{
  if (!isFullscreen) {{
    if (videoPlayerWrapper.requestFullscreen) {{
      videoPlayerWrapper.requestFullscreen();
    }} else if (videoPlayerWrapper.mozRequestFullScreen) {{
      videoPlayerWrapper.mozRequestFullScreen();
    }} else if (videoPlayerWrapper.webkitRequestFullscreen) {{
      videoPlayerWrapper.webkitRequestFullscreen();
    }} else if (videoPlayerWrapper.msRequestFullscreen) {{
      videoPlayerWrapper.msRequestFullscreen();
    }}
    
    videoPlayerWrapper.classList.add("fullscreen");
    fullscreenBtn.innerHTML = '<i class="fa-solid fa-compress"></i>';
    isFullscreen = true;
    
  }} else {{
    if (document.exitFullscreen) {{
      document.exitFullscreen();
    }} else if (document.mozCancelFullScreen) {{
      document.mozCancelFullScreen();
    }} else if (document.webkitExitFullscreen) {{
      document.webkitExitFullscreen();
    }} else if (document.msExitFullscreen) {{
      document.msExitFullscreen();
    }}
    
    videoPlayerWrapper.classList.remove("fullscreen");
    fullscreenBtn.innerHTML = '<i class="fa-solid fa-expand"></i>';
    isFullscreen = false;
  }}
  
  resetControlsTimer();
}}

aspectBtn.addEventListener("click", function(e) {{
  e.stopPropagation();
  if (videoPlayer.style.objectFit === "cover") {{
    videoPlayer.style.objectFit = "contain";
    aspectBtn.innerHTML = '<i class="fa-solid fa-expand"></i>';
  }} else {{
    videoPlayer.style.objectFit = "cover";
    aspectBtn.innerHTML = '<i class="fa-solid fa-tv"></i>';
  }}
  resetControlsTimer();
}});

document.addEventListener('fullscreenchange', handleFullscreenChange);
document.addEventListener('webkitfullscreenchange', handleFullscreenChange);
document.addEventListener('mozfullscreenchange', handleFullscreenChange);
document.addEventListener('MSFullscreenChange', handleFullscreenChange);

function handleFullscreenChange() {{
  if (!document.fullscreenElement && 
      !document.webkitFullscreenElement && 
      !document.mozFullScreenElement && 
      !document.msFullscreenElement) {{
    
    videoPlayerWrapper.classList.remove("fullscreen");
    fullscreenBtn.innerHTML = '<i class="fa-solid fa-expand"></i>';
    isFullscreen = false;
    showControls();
  }}
}}

function showControls() {{
  videoControls.classList.remove('hidden');
  controlsVisible = true;
  resetControlsTimer();
}}

function hideControls() {{
  if (!videoPlayer.paused) {{
    videoControls.classList.add('hidden');
    controlsVisible = false;
  }}
}}

function resetControlsTimer() {{
  clearTimeout(controlsTimeout);
  controlsTimeout = setTimeout(() => {{
    if (!videoPlayer.paused) {{
      hideControls();
    }}
  }}, 5000);
}}

videoPlayerWrapper.addEventListener('click', function(e) {{
  if (e.target.closest('.video-controls')) {{
    return;
  }}
  
  if (controlsVisible) {{
    hideControls();
  }} else {{
    showControls();
  }}
}});

videoPlayerWrapper.addEventListener('mousemove', function() {{
  showControls();
}});

videoPlayerWrapper.addEventListener('touchstart', function(e) {{
  if (e.target.closest('.video-controls')) {{
    return;
  }}
  
  if (controlsVisible) {{
    hideControls();
  }} else {{
    showControls();
  }}
}});

videoControls.addEventListener('mousemove', function(e) {{
  e.stopPropagation();
  resetControlsTimer();
}});

videoControls.addEventListener('click', function(e) {{
  e.stopPropagation();
  resetControlsTimer();
}});

videoPlayer.addEventListener('play', function() {{
  resetControlsTimer();
}});

// جلب شعار المسلسل
fetch(`https://api.themoviedb.org/3/tv/${{SERIES_ID}}/images?api_key=${{API_KEY}}`)
  .then(res => res.json())
  .then(images => {{
    const logo = images.logos.find(l => l.iso_639_1 === "en") || images.logos[0];
    const logoContainer = document.getElementById("seriesLogo");
    if (logo && logo.file_path) {{
      logoContainer.innerHTML = `<img src="https://image.tmdb.org/t/p/original${{logo.file_path}}" alt="Series Logo">`;
    }} else {{
      logoContainer.style.display = "none";
    }}
  }});

// LocalStorage للإعجاب والمشاهدة لاحقًا
function saveToLocalStorage(key, value) {{
  try {{ localStorage.setItem(key, JSON.stringify(value)); }} catch(e) {{}}
}}
function loadFromLocalStorage(key) {{
  try {{ return JSON.parse(localStorage.getItem(key)) || null; }} catch(e) {{ return null; }}
}}

likeBtn.addEventListener('click', () => {{
  const saved = loadFromLocalStorage('likedSeries') || [];
  const icon = likeBtn.querySelector('i');
  if (likeBtn.classList.contains('active')) {{
    likeBtn.classList.remove('active');
    icon.classList.replace('fa-solid', 'fa-regular');
    const idx = saved.indexOf(SERIES_ID);
    if (idx > -1) saved.splice(idx, 1);
  }} else {{
    likeBtn.classList.add('active');
    icon.classList.replace('fa-regular', 'fa-solid');
    if (!saved.includes(SERIES_ID)) saved.push(SERIES_ID);
  }}
  saveToLocalStorage('likedSeries', saved);
}});

watchLaterBtn.addEventListener('click', () => {{
  const saved = loadFromLocalStorage('watchLaterSeries') || [];
  const icon = watchLaterBtn.querySelector('i');
  if (watchLaterBtn.classList.contains('active')) {{
    watchLaterBtn.classList.remove('active');
    icon.classList.replace('fa-solid', 'fa-regular');
    const idx = saved.indexOf(SERIES_ID);
    if (idx > -1) saved.splice(idx, 1);
  }} else {{
    watchLaterBtn.classList.add('active');
    icon.classList.replace('fa-regular', 'fa-solid');
    if (!saved.includes(SERIES_ID)) saved.push(SERIES_ID);
  }}
  saveToLocalStorage('watchLaterSeries', saved);
}});

document.addEventListener('DOMContentLoaded', () => {{
  const savedLikes = loadFromLocalStorage('likedSeries') || [];
  const savedWatchLater = loadFromLocalStorage('watchLaterSeries') || [];
  if (savedLikes.includes(SERIES_ID)) {{
    likeBtn.classList.add('active');
    likeBtn.querySelector('i').classList.replace('fa-regular', 'fa-solid');
  }}
  if (savedWatchLater.includes(SERIES_ID)) {{
    watchLaterBtn.classList.add('active');
    watchLaterBtn.querySelector('i').classList.replace('fa-regular', 'fa-solid');
  }}
}});

document.addEventListener('keydown', function(e) {{
  if (videoModal.classList.contains('active')) {{
    if (e.code === 'Space') {{ e.preventDefault(); togglePlay(); }}
    else if (e.code === 'Escape' && isFullscreen) toggleFullscreen();
    else if (e.code === 'KeyF') toggleFullscreen();
    else if (e.code === 'ArrowRight') {{ videoPlayer.currentTime = Math.min(videoPlayer.duration, videoPlayer.currentTime + 10); showControls(); }}
    else if (e.code === 'ArrowLeft') {{ videoPlayer.currentTime = Math.max(0, videoPlayer.currentTime - 10); showControls(); }}
  }}
}});
</script>
</body>
</html>'''
    return html_template

# ----------------------------- HTML CARD BUILDERS -----------------------------
def build_card_movie_main(m: dict, tmdb_id: str, mux_id: str = "") -> str:
    poster_w500 = f"https://image.tmdb.org/t/p/w500{m.get('poster_path')}" if m.get("poster_path") else ""
    poster_orig = f"https://image.tmdb.org/t/p/original{m.get('poster_path')}" if m.get("poster_path") else poster_w500
    # تطبيق قاعدة اللغة: العنوان بلغة العمل الأصلية (ما عدا كوري/ياباني/صيني/هندي = إنجليزي)
    titles = determine_title_display(m)
    title = titles.get("primary", m.get("title", ""))
    rating = f"{m.get('vote_average', 0):.1f}"
    year = (m.get("release_date") or "")[:4] or ""
    
    if mux_id:
        href = f"movie.html?tmdb={tmdb_id}&mux={mux_id}"
    else:
        href = f"movie.html?tmdb={tmdb_id}"
    
    return f'''<div class="card-wrapper">
<a class="card" href="{href}">
<img class="lazy loaded" loading="lazy" src="{poster_w500}" data-src-original="{poster_orig}">
<div class="card-overlay">
<i class="fas fa-play play-icon"></i>
<span class="card-desc">Cinema Plus</span>
</div>
</a>
<div class="card-details">
<h3 class="card-details-title">{title}</h3>
<div class="card-details-meta">
<span class="year">{year}</span>
<div class="rating">
<img alt="IMDb" loading="lazy" src="https://upload.wikimedia.org/wikipedia/commons/6/69/IMDB_Logo_2016.svg">
<span>{rating}</span>
</div>
</div>
</div>
</div>'''

def build_card_movie_discover(m: dict, tmdb_id: str, mux_id: str = "") -> str:
    genres = "|".join([g.get("name", "") for g in m.get("genres", [])])
    year = (m.get("release_date") or "")[:4] or ""
    poster_w500 = f"https://image.tmdb.org/t/p/w500{m.get('poster_path')}" if m.get("poster_path") else ""
    poster_orig = f"https://image.tmdb.org/t/p/original{m.get('poster_path')}" if m.get("poster_path") else poster_w500
    # تطبيق قاعدة اللغة: العنوان بلغة العمل الأصلية (ما عدا كوري/ياباني/صيني/هندي = إنجليزي)
    titles = determine_title_display(m)
    title = titles.get("primary", m.get("title", "")).replace('"', "&quot;")
    rating = f"{m.get('vote_average', 0):.1f}"
    
    if mux_id:
        href = f"movie.html?tmdb={tmdb_id}&mux={mux_id}"
    else:
        href = f"movie.html?tmdb={tmdb_id}"
    
    return f'''<div class="card-wrapper" data-genre="{genres}" data-year="{year}" data-type="افلام" data-title="{title}">
<a href="{href}" class="card">
<img class="lazy loaded" src="{poster_w500}" data-src="{poster_orig}" alt="فيلم: {title}">
</a>
<div class="card-details">
<h3 class="card-details-title">{title}</h3>
<div class="card-details-meta">
<span class="year">{year}</span>
<div class="rating">
<i class='fas fa-star' style='color:#ffcc00;'></i> <span>{rating}</span>
</div>
</div>
</div>
</div>'''

def build_card_series_main(s: dict, tmdb_id: str, titles: Dict[str, str]) -> str:
    poster_w500 = f"https://image.tmdb.org/t/p/w500{s.get('poster_path')}" if s.get("poster_path") else ""
    poster_orig = f"https://image.tmdb.org/t/p/original{s.get('poster_path')}" if s.get("poster_path") else poster_w500
    
    # استخدام العنوان الأساسي
    title = titles.get("primary", s.get("name", ""))
    rating = f"{s.get('vote_average', 0):.1f}"
    year = (s.get("first_air_date") or "")[:4] or ""
    
    href = f"series/{tmdb_id}.html"

    return f'''<div class="card-wrapper">
<a class="card" href="{href}">
<img class="lazy loaded" loading="lazy" src="{poster_w500}" data-src-original="{poster_orig}">
<div class="card-overlay">
<i class="fas fa-play play-icon"></i>
<span class="card-desc">Cinema Plus</span>
</div>
</a>
<div class="card-details">
<h3 class="card-details-title">{title}</h3>
<div class="card-details-meta">
<span class="year">{year}</span>
<div class="rating">
<img alt="IMDb" loading="lazy" src="https://upload.wikimedia.org/wikipedia/commons/6/69/IMDB_Logo_2016.svg">
<span>{rating}</span>
</div>
</div>
</div>
</div>'''

def build_card_series_discover(s: dict, tmdb_id: str, titles: Dict[str, str]) -> str:
    genres = "|".join([g.get("name", "") for g in s.get("genres", [])])
    year = (s.get("first_air_date") or "")[:4] or ""
    poster_w500 = f"https://image.tmdb.org/t/p/w500{s.get('poster_path')}" if s.get("poster_path") else ""
    poster_orig = f"https://image.tmdb.org/t/p/original{s.get('poster_path')}" if s.get("poster_path") else poster_w500
    title = titles.get("primary", s.get("name", "")).replace('"', "&quot;")
    rating = f"{s.get('vote_average', 0):.1f}"
    
    href = f"series/{tmdb_id}.html"

    return f'''<div class="card-wrapper" data-genre="{genres}" data-year="{year}" data-type="مسلسلات" data-title="{title}">
<a href="{href}" class="card">
<img class="lazy loaded" src="{poster_w500}" data-src="{poster_orig}" alt="مسلسل: {title}">
</a>
<div class="card-details">
<h3 class="card-details-title">{title}</h3>
<div class="card-details-meta">
<span class="year">{year}</span>
<div class="rating">
<i class='fas fa-star' style='color:#ffcc00;'></i> <span>{rating}</span>
</div>
</div>
</div>
</div>'''

# ----------------------------- RECENT EPISODE CARD BUILDER -----------------------------
def build_recent_episode_card(series_data: dict, tmdb_id: str, season_number: int, episode_number: int, titles: Dict[str, str]) -> str:
    """
    إنشاء كارت حلقة مضافة حديثاً لقسم "حلقات مضافة حديثاً" في الصفحة الرئيسية
    يستخدم صورة backdrop (أفقية) بتصميم episode-card الجديد
    """
    backdrop_path = series_data.get("backdrop_path", "")
    poster_path = series_data.get("poster_path", "")
    
    if backdrop_path:
        thumb_url = f"https://image.tmdb.org/t/p/w780{backdrop_path}"
    elif poster_path:
        thumb_url = f"https://image.tmdb.org/t/p/w500{poster_path}"
    else:
        thumb_url = ""
    
    title = titles.get("primary", series_data.get("name", ""))
    rating = f"{series_data.get('vote_average', 0):.1f}"
    href = f"series/{tmdb_id}.html"
    
    import datetime
    now_iso = datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
    
    return f'''<a class="episode-card" href="{href}" style="flex: 0 0 auto; width: 220px; border-radius: 14px; background: #0a0a0a; overflow: hidden; text-decoration: none; color: inherit; scroll-snap-align: start;">
<div class="thumb" style="position: relative; aspect-ratio: 16/9; background: #111; overflow: hidden;">
<img alt="{title}" src="{thumb_url}" style="width: 100%; height: 100%; object-fit: cover;"/>
<span class="badge" style="position: absolute; z-index: 2; top: 8px; inset-inline-start: 8px; background: rgba(0,0,0,.65); color: #fff; border-radius: 999px; font-size: 10px; padding: 2px 6px;">S{season_number:02d} E{episode_number:02d}</span>
<span class="badge quality" style="position: absolute; z-index: 2; top: 8px; inset-inline-start: auto; inset-inline-end: 8px; background: linear-gradient(90deg, #0ea5e9, #3b82f6); color: #fff; border-radius: 999px; font-size: 10px; padding: 2px 6px;">HD</span>
<div class="imdb" style="position: absolute; bottom: 6px; inset-inline-start: 6px; display: flex; align-items: center; gap: 4px; background: rgba(0,0,0,.6); border-radius: 999px; padding: 2px 6px;">
<span style="color:#f5c518; font-size:11px;">★</span>
<span style="font-size:12px; font-weight:bold;">{rating}</span>
</div>
</div>
<div class="meta" style="padding: 6px 8px;">
<div class="title" style="font-size: 13px; font-weight: 700; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">{title}</div>
<div class="subtitle" style="font-size: 12px; color: #a8b3cf; margin-top: 2px;">الحلقة {episode_number} - الموسم {season_number}</div>
<div class="extra" style="margin-top: 4px; font-size: 11px; color: #a8b3cf; display: flex; align-items: center; gap: 6px;">
<span class="dot" style="width: 6px; height: 6px; border-radius: 50%; background: #3b82f6;"></span>
<span class="ep-time-ago" data-time="{now_iso}">تمت الإضافة الآن</span>
</div>
</div>
</a>'''

def insert_recent_episode_card(html_content: str, card_html: str, start_marker: str, end_marker: str, max_cards: int = 20) -> Optional[str]:
    """
    إدراج كارت حلقة جديدة في قسم الحلقات المضافة حديثاً
    يحتفظ بحد أقصى max_cards كارت ويحذف الأقدم
    يلف الكروت في حاوية flex أفقية قابلة للتمرير مع سكريبت لحساب الوقت النسبي
    """
    if start_marker not in html_content or end_marker not in html_content:
        logger.error(f"Markers not found for recent episodes: {start_marker}")
        return None
    
    start_idx = html_content.find(start_marker) + len(start_marker)
    end_idx = html_content.find(end_marker)
    section_content = html_content[start_idx:end_idx]
    
    # استخراج الكروت الموجودة فقط (بدون الحاوية والسكريبت القديم)
    soup = BeautifulSoup(section_content, 'html.parser')
    existing_cards = soup.find_all('a', class_='episode-card')
    # fallback: دعم الكروت القديمة episode-modern أيضاً
    if not existing_cards:
        existing_cards = soup.find_all('a', class_='episode-modern')
    existing_cards_html = ''.join(str(c) for c in existing_cards)
    
    # إضافة الكارت الجديد في البداية
    all_cards_html = card_html + existing_cards_html
    
    # حساب عدد الكاردات وحذف الزائد
    soup2 = BeautifulSoup(all_cards_html, 'html.parser')
    cards = soup2.find_all('a', class_='episode-card')
    if len(cards) > max_cards:
        for card in cards[max_cards:]:
            card.decompose()
    cards_final = str(soup2)
    
    # سكريبت الوقت النسبي (يحدث النص تلقائياً)
    time_script = '''<script>
(function(){
  function updateTimes(){
    document.querySelectorAll('.ep-time-ago[data-time]').forEach(function(el){
      var t=new Date(el.getAttribute('data-time')).getTime();
      var now=Date.now();
      var diff=Math.floor((now-t)/1000);
      var txt='';
      if(diff<60) txt='تمت الإضافة منذ لحظات';
      else if(diff<3600){var m=Math.floor(diff/60);txt='تمت الإضافة منذ '+m+' دقيقة';}
      else if(diff<86400){var h=Math.floor(diff/3600);var rm=Math.floor((diff%3600)/1800);if(rm>=1)txt='تمت الإضافة منذ '+h+' ساعة ونصف';else txt='تمت الإضافة منذ '+h+' ساعة';}
      else{var d=Math.floor(diff/86400);txt='تمت الإضافة منذ '+d+' يوم';}
      el.innerHTML='<span style="display:inline-block;width:6px;height:6px;background:#3b82f6;border-radius:50%;vertical-align:middle;margin-left:4px;"></span>'+txt;
    });
  }
  updateTimes();
  setInterval(updateTimes,30000);
})();
</script>'''
    
    # بناء القسم: حاوية flex أفقية قابلة للتمرير + كروت + سكريبت
    wrapper = f'''
<div style="display:flex;gap:12px;padding:0 8px;overflow-x:auto;scroll-snap-type:x mandatory;scrollbar-width:none;-webkit-overflow-scrolling:touch;">
{cards_final}
</div>
{time_script}
'''
    
    result = html_content[:html_content.find(start_marker) + len(start_marker)] + wrapper + html_content[end_idx:]
    
    return result

async def push_recent_episode_to_github(card_html: str) -> bool:
    """رفع كارت الحلقة المضافة حديثاً إلى الصفحة الرئيسية"""
    async with aiohttp.ClientSession() as session:
        data = await github_get_file(session, MAIN_FILE)
        if not data:
            return False
        
        sha = data.get("sha")
        encoded = data.get("content", "")
        try:
            decoded = base64.b64decode(encoded).decode("utf-8")
        except Exception as e:
            logger.exception("Failed to decode file content: %s", e)
            return False
        
        start_marker = MARKERS["RECENT_EPISODES"][0]
        end_marker = MARKERS["RECENT_EPISODES"][1]
        
        updated = insert_recent_episode_card(decoded, card_html, start_marker, end_marker)
        if updated is None:
            logger.error("Failed to insert recent episode card: markers not found")
            return False
        
        new_b64 = base64.b64encode(updated.encode("utf-8")).decode()
        res = await github_put_file(session, MAIN_FILE, new_b64, sha, "Add recent episode card via bot")
        return res is not None

# ----------------------------- BeautifulSoup HTML HELPERS -----------------------------
def insert_card_with_bs4(html_content: str, card_html: str, start_marker: str, end_marker: str) -> Optional[str]:
    if start_marker not in html_content or end_marker not in html_content:
        logger.error(f"Markers not found: {start_marker}")
        return None
    
    soup = BeautifulSoup(html_content, 'html.parser')
    start_comment = None
    for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
        if start_marker.replace('<!-- ', '').replace(' -->', '').strip() in comment.strip():
            start_comment = comment
            break
    
    if not start_comment:
        logger.error(f"Start comment not found: {start_marker}")
        return None
    
    new_card_soup = BeautifulSoup(card_html, 'html.parser')
    new_card = new_card_soup.find('div', class_='card-wrapper')
    
    if not new_card:
        logger.error("Could not parse new card HTML")
        return None
    
    start_comment.insert_after(new_card)
    return str(soup)

def delete_card_with_bs4(html_content: str, tmdb_id: str, start_marker: str, end_marker: str) -> Optional[str]:
    if start_marker not in html_content or end_marker not in html_content:
        logger.error(f"Markers not found: {start_marker}")
        return None
    
    soup = BeautifulSoup(html_content, 'html.parser')
    cards = soup.find_all('div', class_='card-wrapper')
    
    card_found = False
    for card in cards:
        link = card.find('a', href=True)
        if link:
            href = link.get('href', '')
            if f'tmdb={tmdb_id}' in href or f'/{tmdb_id}.html' in href or f'go:{tmdb_id}' in href:
                card.decompose()
                card_found = True
                logger.info(f"Card with tmdb={tmdb_id} deleted successfully")
                break
    
    if not card_found:
        logger.error(f"Card with tmdb={tmdb_id} not found")
        return None
    
    return str(soup)

def extract_cards_with_bs4(html_content: str, start_marker: str, end_marker: str, count: int = 5) -> list:
    if start_marker not in html_content or end_marker not in html_content:
        return []
    
    start_idx = html_content.find(start_marker) + len(start_marker)
    end_idx = html_content.find(end_marker)
    section_content = html_content[start_idx:end_idx]
    
    soup = BeautifulSoup(section_content, 'html.parser')
    cards = soup.find_all('div', class_='card-wrapper')
    
    result = []
    for card in cards[:count]:
        title_elem = card.find('h3', class_='card-details-title')
        title = title_elem.get_text(strip=True) if title_elem else "بدون عنوان"
        
        img_elem = card.find('img')
        img = img_elem.get('src', '') if img_elem else ""
        
        link = card.find('a', href=True)
        card_id = ""
        if link:
            href = link.get('href', '')
            tmdb_match = re.search(r'tmdb=(\d+)', href)
            series_match = re.search(r'/(\d+)\.html', href)
            go_match = re.search(r'go:(\d+)', href)
            if tmdb_match:
                card_id = tmdb_match.group(1)
            elif series_match:
                card_id = series_match.group(1)
            elif go_match:
                card_id = go_match.group(1)
        
        if card_id:
            result.append({
                "title": title,
                "img": img,
                "id": card_id,
                "html": str(card)
            })
    
    return result

# ----------------------------- GITHUB HELPERS -----------------------------
async def github_get_file(session: aiohttp.ClientSession, path: str) -> Optional[dict]:
    url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents/{path}?ref={BRANCH}"
    try:
        async with session.get(url, headers=GITHUB_HEADERS, timeout=30) as resp:
            if resp.status == 200:
                return await resp.json()
            else:
                logger.error("GitHub GET returned %s for %s", resp.status, url)
                return None
    except Exception as e:
        logger.exception("Error fetching file from GitHub: %s", e)
        return None

async def github_put_file(session: aiohttp.ClientSession, path: str, content_b64: str, sha: Optional[str], message: str) -> Optional[dict]:
    url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents/{path}"
    payload = {
        "message": message,
        "content": content_b64,
        "branch": BRANCH
    }
    if sha:
        payload["sha"] = sha
    
    try:
        async with session.put(url, headers=GITHUB_HEADERS, json=payload, timeout=30) as resp:
            if resp.status in (200, 201):
                logger.info("GitHub file updated: %s", path)
                return await resp.json()
            else:
                text = await resp.text()
                logger.error("GitHub PUT returned %s for %s: %s", resp.status, path, text)
                return None
    except Exception as e:
        logger.exception("Error uploading file to GitHub: %s", e)
        return None

async def push_card_to_github(card_html: str, target_file: str, start_marker: str, end_marker: str) -> bool:
    async with aiohttp.ClientSession() as session:
        data = await github_get_file(session, target_file)
        if not data:
            return False

        sha = data.get("sha")
        encoded = data.get("content", "")
        try:
            decoded = base64.b64decode(encoded).decode("utf-8")
        except Exception as e:
            logger.exception("Failed to decode file content: %s", e)
            return False

        updated = insert_card_with_bs4(decoded, card_html, start_marker, end_marker)
        if updated is None:
            logger.error("Failed to insert card: markers not found")
            return False

        new_b64 = base64.b64encode(updated.encode("utf-8")).decode()
        res = await github_put_file(session, target_file, new_b64, sha, "Add card via bot")
        return res is not None

async def delete_card_from_github(tmdb_id: str, target_file: str, start_marker: str, end_marker: str) -> bool:
    async with aiohttp.ClientSession() as session:
        data = await github_get_file(session, target_file)
        if not data:
            return False

        sha = data.get("sha")
        encoded = data.get("content", "")
        try:
            decoded = base64.b64decode(encoded).decode("utf-8")
        except Exception as e:
            logger.exception("Failed to decode file content: %s", e)
            return False

        updated = delete_card_with_bs4(decoded, tmdb_id, start_marker, end_marker)
        if updated is None:
            logger.error("Failed to delete card: card not found")
            return False

        new_b64 = base64.b64encode(updated.encode("utf-8")).decode()
        res = await github_put_file(session, target_file, new_b64, sha, f"Delete card {tmdb_id} via bot")
        return res is not None

async def get_cards_from_file(target_file: str, start_marker: str, end_marker: str, count: int = 5) -> list:
    async with aiohttp.ClientSession() as session:
        data = await github_get_file(session, target_file)
        if not data:
            return []

        encoded = data.get("content", "")
        try:
            decoded = base64.b64decode(encoded).decode("utf-8")
        except Exception as e:
            logger.exception("Failed to decode file content: %s", e)
            return []

        return extract_cards_with_bs4(decoded, start_marker, end_marker, count)

async def upload_series_html(tmdb_id: str, episode_links: Dict[str, str]) -> bool:
    """رفع ملف HTML للمسلسل إلى GitHub"""
    html_content = generate_series_html(tmdb_id, episode_links)
    file_path = f"{SERIES_FOLDER}/{tmdb_id}.html"
    
    async with aiohttp.ClientSession() as session:
        # التحقق من وجود الملف
        existing = await github_get_file(session, file_path)
        sha = existing.get("sha") if existing else None
        
        content_b64 = base64.b64encode(html_content.encode("utf-8")).decode()
        res = await github_put_file(session, file_path, content_b64, sha, f"Add/Update series {tmdb_id}")
        return res is not None

async def get_series_html(tmdb_id: str) -> Optional[str]:
    """جلب محتوى ملف HTML للمسلسل"""
    file_path = f"{SERIES_FOLDER}/{tmdb_id}.html"
    
    async with aiohttp.ClientSession() as session:
        data = await github_get_file(session, file_path)
        if not data:
            return None
        
        encoded = data.get("content", "")
        try:
            return base64.b64decode(encoded).decode("utf-8")
        except Exception as e:
            logger.exception("Failed to decode series file: %s", e)
            return None

async def update_series_episodes(tmdb_id: str, episode_links: Dict[str, str]) -> bool:
    """تحديث روابط الحلقات في ملف المسلسل"""
    html_content = await get_series_html(tmdb_id)
    if not html_content:
        # إنشاء ملف جديد
        return await upload_series_html(tmdb_id, episode_links)
    
    # استخراج الروابط الحالية وإضافة الجديدة
    current_links = extract_episode_links(html_content)
    current_links.update(episode_links)
    
    # إعادة إنشاء الملف
    return await upload_series_html(tmdb_id, current_links)

def extract_episode_links(html_content: str) -> Dict[str, str]:
    """استخراج روابط الحلقات من ملف HTML"""
    match = re.search(r'const episodeLinks = ({[\s\S]*?});', html_content)
    if match:
        try:
            # تنظيف JSON
            json_str = match.group(1)
            # إزالة التعليقات
            json_str = re.sub(r'//.*', '', json_str)
            return json.loads(json_str)
        except:
            pass
    return {}

async def list_series_files() -> List[dict]:
    """جلب قائمة ملفات المسلسلات من GitHub"""
    url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents/{SERIES_FOLDER}?ref={BRANCH}"
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, headers=GITHUB_HEADERS, timeout=30) as resp:
                if resp.status == 200:
                    files = await resp.json()
                    series_list = []
                    for f in files:
                        if f.get("name", "").endswith(".html"):
                            tmdb_id = f["name"].replace(".html", "")
                            series_list.append({"id": tmdb_id, "name": f["name"]})
                    return series_list
                return []
        except Exception as e:
            logger.exception("Error listing series files: %s", e)
            return []

# ----------------------------- TELEGRAM HANDLERS -----------------------------
MAIN_KEYBOARD = [["اضافة فيلم", "اضافة مسلسل"], ["مراجعة المسلسلات", "تعديل المسلسلات"], ["حذف كارت"]]

async def show_main_menu(update: Update):
    await update.message.reply_text(
        "لوحة تحكم Cinema Plus",
        reply_markup=ReplyKeyboardMarkup(MAIN_KEYBOARD, resize_keyboard=True)
    )

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("غير مصرح لك.")
        return
    await show_main_menu(update)

def clean_section_name(section_name: str) -> str:
    emojis = ["🆕 ", "🔥 ", "⭐ ", "🎞️ ", "🇮🇶 ", "🇮🇳 ", "🎁 ", "📺 "]
    result = section_name
    for emoji in emojis:
        result = result.replace(emoji, "")
    return result.strip()

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid != ADMIN_ID:
        await update.message.reply_text("غير مصرح لك.")
        return

    text = update.message.text.strip()
    state = user_states.get(uid, {})

    # ===== اضافة فيلم =====
    if text == "اضافة فيلم":
        keyboard = [
            ["🆕 الاضافات الأخيرة", "🔥 الاعمال الجديدة"],
            ["⭐ أعمال مميزة", "🎞️ 4K"],
            ["🇮🇶 افلام عربية", "🇮🇳 افلام هندية"],
            ["🎁 عروض مميزة"],
            ["رجوع"]
        ]
        await update.message.reply_text("اختر القسم:", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))
        user_states[uid] = {"step": "MOVIE_SECTION"}
        return

    if state.get("step") == "MOVIE_SECTION":
        if text == "رجوع":
            user_states.pop(uid, None)
            await show_main_menu(update)
            return
        state["section"] = text
        state["step"] = "MOVIE_ID"
        user_states[uid] = state
        await update.message.reply_text("ارسل TMDB ID للفيلم", reply_markup=ReplyKeyboardRemove())
        return

    if state.get("step") == "MOVIE_ID":
        if not text.isdigit():
            await update.message.reply_text("ID غير صحيح")
            return
        state["tmdb"] = text
        state["step"] = "MOVIE_MUX"
        user_states[uid] = state
        await update.message.reply_text("ارسل MUX ID (او اكتب none اذا لا يوجد)")
        return

    if state.get("step") == "MOVIE_MUX":
        mux_id = text if text.lower() != "none" else ""
        tmdb_id = state.get("tmdb")
        section_name = state.get("section", "")
        
        await update.message.reply_text("جاري جلب بيانات الفيلم ورفع الكارت...")

        movie = await get_movie(tmdb_id)
        if not movie:
            await update.message.reply_text("فشل جلب بيانات الفيلم من TMDB.")
            user_states.pop(uid, None)
            await show_main_menu(update)
            return

        card_main = build_card_movie_main(movie, tmdb_id, mux_id)
        card_disc = build_card_movie_discover(movie, tmdb_id, mux_id)

        clean_section = clean_section_name(section_name)
        section_key = SECTION_MARKERS.get(clean_section, "LATEST")
        
        if section_key not in MARKERS:
            await update.message.reply_text(f"القسم '{section_name}' غير موجود في النظام.")
            user_states.pop(uid, None)
            await show_main_menu(update)
            return

        ok_main = await push_card_to_github(card_main, MAIN_FILE, MARKERS[section_key][0], MARKERS[section_key][1])
        ok_disc = await push_card_to_github(card_disc, DISCOVER_FILE, MARKERS["DISCOVER"][0], MARKERS["DISCOVER"][1])

        # اضافة تلقائية في قسم الاضافات الأخيرة إذا لم يكن القسم المختار هو نفسه
        ok_latest = True
        if section_key != "LATEST":
            ok_latest = await push_card_to_github(card_main, MAIN_FILE, MARKERS["LATEST"][0], MARKERS["LATEST"][1])

        if ok_main and ok_disc:
            mux_info = f"\nMUX ID: {mux_id}" if mux_id else ""
            latest_info = ""
            if section_key != "LATEST":
                latest_info = f"\n- الاضافات الأخيرة: {'نعم' if ok_latest else 'لا'}"
            await update.message.reply_text(
                f"تمت العملية بنجاح!\n\n"
                f"تم اضافة الفيلم: {movie.get('title')}\n"
                f"TMDB ID: {tmdb_id}{mux_info}\n"
                f"القسم: {section_name}{latest_info}"
            )
        else:
            await update.message.reply_text("فشل الاضافة. تحقق من الـ markers.")

        user_states.pop(uid, None)
        await show_main_menu(update)
        return

    # ===== اضافة مسلسل =====
    if text == "اضافة مسلسل":
        user_states[uid] = {"step": "SERIES_ID"}
        await update.message.reply_text("ارسل TMDB ID للمسلسل:", reply_markup=ReplyKeyboardRemove())
        return

    if state.get("step") == "SERIES_ID":
        if not text.isdigit():
            await update.message.reply_text("ID غير صحيح")
            return
        tmdb_id = text
        
        await update.message.reply_text("جاري جلب بيانات المسلسل...")
        
        series = await get_series(tmdb_id)
        if not series:
            await update.message.reply_text("فشل جلب بيانات المسلسل من TMDB.")
            user_states.pop(uid, None)
            await show_main_menu(update)
            return
        
        # تحديد العناوين
        titles = determine_title_display(series)
        if titles.get("secondary") == "FETCH_ARABIC":
            arabic_title = await fetch_arabic_title(tmdb_id, "tv")
            if arabic_title and arabic_title != titles["primary"]:
                titles["secondary"] = arabic_title
            else:
                titles["secondary"] = None
        
        # جلب معلومات المواسم المتاحة
        available_seasons = []
        for season in series.get("seasons", []):
            if season.get("season_number", 0) > 0:  # تجاهل الموسم 0 (الخاص)
                available_seasons.append({
                    "number": season.get("season_number"),
                    "episodes": season.get("episode_count", 0),
                    "name": season.get("name", f"الموسم {season.get('season_number')}")
                })
        
        state["tmdb"] = tmdb_id
        state["series"] = series
        state["titles"] = titles
        state["available_seasons"] = available_seasons
        state["step"] = "SERIES_SELECT_SEASON"
        user_states[uid] = state
        
        # عرض معلومات المسلسل
        poster = f"https://image.tmdb.org/t/p/w500{series.get('poster_path')}" if series.get('poster_path') else None
        
        title_display = titles["primary"]
        if titles.get("secondary"):
            title_display += f"\n{titles['secondary']}"
        
        seasons_text = "\n".join([f"  الموسم {s['number']}: {s['episodes']} حلقة" for s in available_seasons])
        
        info_text = (
            f"المسلسل: {title_display}\n"
            f"التقييم: {series.get('vote_average', 0):.1f}\n"
            f"اللغة الأصلية: {series.get('original_language', '-')}\n"
            f"البلد: {', '.join(series.get('origin_country', []))}\n\n"
            f"المواسم المتاحة:\n{seasons_text}\n\n"
            f"اختر رقم الموسم الذي تريد إضافته:"
        )
        
        # إنشاء أزرار المواسم
        keyboard = []
        row = []
        for s in available_seasons:
            row.append(f"الموسم {s['number']}")
            if len(row) == 3:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)
        keyboard.append(["رجوع"])
        
        if poster:
            await update.message.reply_photo(
                photo=poster, 
                caption=info_text,
                reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            )
        else:
            await update.message.reply_text(
                info_text,
                reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            )
        
        return

    if state.get("step") == "SERIES_SELECT_SEASON":
        if text == "رجوع":
            user_states.pop(uid, None)
            await show_main_menu(update)
            return
        
        # استخراج رقم الموسم
        season_match = re.search(r'(\d+)', text)
        if not season_match:
            await update.message.reply_text("اختر موسم صحيح")
            return
        
        season_number = int(season_match.group(1))
        available_seasons = state.get("available_seasons", [])
        
        # التحقق من وجود الموسم
        season_info = next((s for s in available_seasons if s["number"] == season_number), None)
        if not season_info:
            await update.message.reply_text("الموسم غير موجود")
            return
        
        state["selected_season"] = season_number
        state["season_episodes_count"] = season_info["episodes"]
        state["episode_links"] = state.get("episode_links", {})
        state["step"] = "SERIES_BULK_LINKS"
        user_states[uid] = state
        
        await update.message.reply_text(
            f"الموسم {season_number} يحتوي على {season_info['episodes']} حلقة\n\n"
            f"ارسل روابط/Tokens الحلقات (كل سطر = حلق�� واحدة بالترتيب):\n"
            f"مثال:\n"
            f"token1\n"
            f"token2\n"
            f"token3\n\n"
            f"او اكتب 'skip' لتخطي هذا الموسم",
            reply_markup=ReplyKeyboardRemove()
        )
        return

    if state.get("step") == "SERIES_BULK_LINKS":
        season_number = state.get("selected_season")
        episodes_count = state.get("season_episodes_count", 0)
        
        if text.lower() == "skip":
            # الانتقال لسؤال عن موسم آخر أو الانتهاء
            state["step"] = "SERIES_MORE_SEASONS"
            user_states[uid] = state
            
            keyboard = [["نعم", "لا"]]
            await update.message.reply_text(
                "تم تخطي الموسم.\nهل تريد إضافة موسم آخر؟",
                reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            )
            return
        
        # تقسيم الروابط حسب الأسطر
        links = [link.strip() for link in text.strip().split('\n') if link.strip()]
        
        if len(links) == 0:
            await update.message.reply_text("لم يتم إرسال أي روابط. حاول م��ة أخرى.")
            return
        
        # حفظ الروابط
        for i, link in enumerate(links, 1):
            episode_key = f"{season_number}-{i}"
            state["episode_links"][episode_key] = link
        
        episodes_added = len(links)
        state["step"] = "SERIES_MORE_SEASONS"
        user_states[uid] = state
        
        keyboard = [["نعم", "لا"]]
        await update.message.reply_text(
            f"تم إضافة {episodes_added} حلقة للموسم {season_number}\n\n"
            f"هل تريد إضافة موسم آخر؟",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        return

    if state.get("step") == "SERIES_MORE_SEASONS":
        if text == "نعم":
            # العودة لاختيار موسم
            available_seasons = state.get("available_seasons", [])
            
            keyboard = []
            row = []
            for s in available_seasons:
                row.append(f"الموسم {s['number']}")
                if len(row) == 3:
                    keyboard.append(row)
                    row = []
            if row:
                keyboard.append(row)
            keyboard.append(["رجوع"])
            
            state["step"] = "SERIES_SELECT_SEASON"
            user_states[uid] = state
            
            await update.message.reply_text(
                "اختر رقم الموسم:",
                reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            )
            return
        
        # الانتهاء وحفظ المسلسل
        episode_links = state.get("episode_links", {})
        
        if not episode_links:
            await update.message.reply_text("لم يتم إضافة أي حلقات. تم إلغاء العملية.")
            user_states.pop(uid, None)
            await show_main_menu(update)
            return
        
        await update.message.reply_text("جاري إنشاء صفحة المسلسل ورفعها...")
        
        tmdb_id = state.get("tmdb")
        series = state.get("series")
        titles = state.get("titles")
        
        # إنشاء ورفع ملف HTML
        ok_html = await upload_series_html(tmdb_id, episode_links)
        
        # إنشاء الكارت وإضافته لقسمين: الإضافات الأخيرة + المسلسلات
        card_main = build_card_series_main(series, tmdb_id, titles)
        card_disc = build_card_series_discover(series, tmdb_id, titles)
        
        # إضافة الكارت في قسم الإضافات الأخيرة
        ok_latest = await push_card_to_github(card_main, MAIN_FILE, MARKERS["LATEST"][0], MARKERS["LATEST"][1])
        
        # إضافة الكارت في قسم المسلسلات
        ok_series = await push_card_to_github(card_main, MAIN_FILE, MARKERS["SERIES"][0], MARKERS["SERIES"][1])
        
        # إضافة الكارت في صفحة اكتشف
        ok_disc = await push_card_to_github(card_disc, DISCOVER_FILE, MARKERS["DISCOVER"][0], MARKERS["DISCOVER"][1])
        
        if ok_html and (ok_latest or ok_series):
            title_display = titles["primary"]
            if titles.get("secondary"):
                title_display += f" / {titles['secondary']}"
            
            # حساب المواسم والحلقات المضافة
            seasons_added = set()
            for key in episode_links.keys():
                s, e = key.split('-')
                seasons_added.add(int(s))
            
            await update.message.reply_text(
                f"تمت العملية بنجاح!\n\n"
                f"المسلسل: {title_display}\n"
                f"TMDB ID: {tmdb_id}\n"
                f"المواسم المضافة: {', '.join(map(str, sorted(seasons_added)))}\n"
                f"عدد الحلقات المضافة: {len(episode_links)}\n"
                f"الرابط: series/{tmdb_id}.html\n\n"
                f"تم إضافة الكارت في:\n"
                f"- الإضاف��ت الأخيرة: {'نعم' if ok_latest else 'لا'}\n"
                f"- قسم المسلسلات: {'نعم' if ok_series else 'لا'}\n"
                f"- صفحة اكتشف: {'نعم' if ok_disc else 'لا'}"
            )
        else:
            await update.message.reply_text("فشل في بعض العمليات. تحقق من السجلات.")
        
        user_states.pop(uid, None)
        await show_main_menu(update)
        return

    # ===== مراجعة المسلسلات (المستمرة فقط) =====
    if text == "مراجعة المسلسلات":
        await update.message.reply_text("جاري جلب قائمة المسلسلات المستمرة...")
        
        series_list = await list_series_files()
        
        if not series_list:
            await update.message.reply_text("لا توجد مسلسلات مضافة حاليًا.")
            await show_main_menu(update)
            return
        
        # جلب معلومات كل مسلسل من TMDB وفلترة المستمرة فقط
        enriched_list = []
        for s in series_list[:20]:  # حد أقصى 20
            series_data = await get_series(s["id"])
            if series_data:
                # فلترة: فقط المسلسلات المستمرة (غير المنتهية)
                status = series_data.get("status", "")
                # استبعاد المسلسلات المنتهية صراحة
                # Ended = انتهى، Canceled = ملغي
                if status not in ["Ended", "Canceled", "Cancelled"]:
                    # استخدام اللغة الأصلية للعرض
                    titles = determine_title_display(series_data)
                    display_name = titles.get("primary") or series_data.get("name", "بدون اسم")
                    enriched_list.append({
                        "id": s["id"],
                        "name": display_name,
                        "poster": f"https://image.tmdb.org/t/p/w500{series_data.get('poster_path')}" if series_data.get('poster_path') else None,
                        "status": status
                    })
        
        if not enriched_list:
            await update.message.reply_text("لا توجد مسلسلات مستمرة تحتاج مراجعة.\nجميع المسلسلات المضافة منتهية.")
            await show_main_menu(update)
            return
        
        state["series_list"] = enriched_list
        state["step"] = "REVIEW_SELECT"
        user_states[uid] = state
        
        # عرض المسلسلات مع الصور
        keyboard = []
        for s in enriched_list:
            try:
                if s['poster']:
                    await update.message.reply_photo(
                        photo=s['poster'],
                        caption=f"{s['name']}\nID: {s['id']}\nالحالة: مستمر"
                    )
                else:
                    await update.message.reply_text(f"{s['name']}\nID: {s['id']}\nالحالة: مستمر")
            except Exception as e:
                await update.message.reply_text(f"{s['name']}\nID: {s['id']}")
            
            # إضافة زر للاختيار
            keyboard.append([f"{s['name'][:25]} ({s['id']})"])
        
        keyboard.append(["رجوع"])
        
        await update.message.reply_text(
            "اختر المسلسل المستمر لمراجعته:",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        return

    # ===== تعديل المسلسلات (جميع المسلسلات) =====
    if text == "تعديل المسلسلات":
        await update.message.reply_text("جاري جلب قائمة جميع المسلسلات...")
        
        series_list = await list_series_files()
        
        if not series_list:
            await update.message.reply_text("لا توجد مسلسلات مضافة حاليًا.")
            await show_main_menu(update)
            return
        
        # جلب معلومات كل مسلسل من TMDB (جميعها)
        enriched_list = []
        for s in series_list[:20]:  # حد أقصى 20
            series_data = await get_series(s["id"])
            if series_data:
                status = series_data.get("status", "")
                status_ar = "مستمر" if status in ["Returning Series", "In Production"] else "منتهي"
                # استخدام اللغة الأصلية للعرض
                titles = determine_title_display(series_data)
                display_name = titles.get("primary") or series_data.get("name", "بدون اسم")
                enriched_list.append({
                    "id": s["id"],
                    "name": display_name,
                    "poster": f"https://image.tmdb.org/t/p/w500{series_data.get('poster_path')}" if series_data.get('poster_path') else None,
                    "status_ar": status_ar
                })
            else:
                enriched_list.append({
                    "id": s["id"],
                    "name": f"مسلسل {s['id']}",
                    "poster": None,
                    "status_ar": "غير معروف"
                })
        
        state["series_list"] = enriched_list
        state["step"] = "REVIEW_SELECT"
        user_states[uid] = state
        
        # عرض المسلسلات مع الصور
        keyboard = []
        for s in enriched_list:
            try:
                if s['poster']:
                    await update.message.reply_photo(
                        photo=s['poster'],
                        caption=f"{s['name']}\nID: {s['id']}\nالحالة: {s['status_ar']}"
                    )
                else:
                    await update.message.reply_text(f"{s['name']}\nID: {s['id']}\nالحالة: {s['status_ar']}")
            except Exception as e:
                await update.message.reply_text(f"{s['name']}\nID: {s['id']}")
            
            # إضافة زر للاختيار
            keyboard.append([f"{s['name'][:25]} ({s['id']})"])
        
        keyboard.append(["رجوع"])
        
        await update.message.reply_text(
            "اختر المسلسل للتعديل:",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        return

    if state.get("step") == "REVIEW_SELECT":
        if text == "رجوع":
            user_states.pop(uid, None)
            await show_main_menu(update)
            return
        
        # استخراج ID من النص (قد يكون بصيغة "اسم المسلسل (ID)")
        id_match = re.search(r'\((\d+)\)$', text)
        if id_match:
            tmdb_id = id_match.group(1)
        else:
            tmdb_id = text.strip()
        
        await update.message.reply_text("جاري جلب معلومات المسلسل...")
        
        series = await get_series(tmdb_id)
        if not series:
            await update.message.reply_text("فشل جلب بيانات المسلسل.")
            return
        
        # جلب الروابط الحالية
        html_content = await get_series_html(tmdb_id)
        current_links = extract_episode_links(html_content) if html_content else {}
        
        state["review_tmdb"] = tmdb_id
        state["review_series"] = series
        state["review_links"] = current_links
        state["step"] = "REVIEW_ACTION"
        user_states[uid] = state
        
        poster = f"https://image.tmdb.org/t/p/w500{series.get('poster_path')}" if series.get('poster_path') else None
        
        info_text = (
            f"المسلسل: {series.get('name')}\n"
            f"TMDB ID: {tmdb_id}\n"
            f"عدد الحلقات المضافة: {len(current_links)}\n\n"
            f"الحلقات الموجودة:\n"
        )
        
        for key in sorted(current_links.keys(), key=lambda x: (int(x.split('-')[0]), int(x.split('-')[1]))):
            s, e = key.split('-')
            info_text += f"S{s} E{e}: موجود\n"
        
        keyboard = [
            ["اضافة حلقة جديدة", "اضافة حلقات متعددة"],
            ["اضافة موسم جديد", "تعديل رابط حلقة"],
            ["حذف حلقة", "رجوع"]
        ]
        
        if poster:
            await update.message.reply_photo(
                photo=poster,
                caption=info_text[:1000],
                reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            )
        else:
            await update.message.reply_text(
                info_text,
                reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            )
        return

    if state.get("step") == "REVIEW_ACTION":
        if text == "رجوع":
            user_states.pop(uid, None)
            await show_main_menu(update)
            return
        
        if text == "اضافة حلقة جديدة":
            state["step"] = "ADD_EPISODE_SEASON"
            user_states[uid] = state
            await update.message.reply_text("ارسل رقم الموسم:", reply_markup=ReplyKeyboardRemove())
            return
        
        if text == "اضافة حلقات متعددة":
            state["step"] = "ADD_BULK_EPISODES_SEASON"
            user_states[uid] = state
            await update.message.reply_text("ارسل رقم الموسم:", reply_markup=ReplyKeyboardRemove())
            return
        
        if text == "اضافة موسم جديد":
            state["step"] = "ADD_SEASON_NUMBER"
            user_states[uid] = state
            await update.message.reply_text("ارسل رقم الموسم الجديد:", reply_markup=ReplyKeyboardRemove())
            return
        
        if text == "تعديل رابط حلقة":
            state["step"] = "EDIT_EPISODE_KEY"
            user_states[uid] = state
            await update.message.reply_text(
                "ارسل مفتاح الحلقة (مثال: 1-5 للموسم 1 الحلقة 5):",
                reply_markup=ReplyKeyboardRemove()
            )
            return
        
        if text == "حذف حلقة":
            state["step"] = "DELETE_EPISODE_KEY"
            user_states[uid] = state
            await update.message.reply_text(
                "ارسل مفتاح الحلقة للحذف (مثال: 1-5):",
                reply_markup=ReplyKeyboardRemove()
            )
            return

    # اضافة حلقة جديدة
    if state.get("step") == "ADD_EPISODE_SEASON":
        if not text.isdigit():
            await update.message.reply_text("ارسل رقم صحيح")
            return
        state["add_season"] = int(text)
        state["step"] = "ADD_EPISODE_NUMBER"
        user_states[uid] = state
        await update.message.reply_text("ارسل رقم الحلقة:")
        return

    if state.get("step") == "ADD_EPISODE_NUMBER":
        if not text.isdigit():
            await update.message.reply_text("ارسل رقم صحيح")
            return
        state["add_episode"] = int(text)
        state["step"] = "ADD_EPISODE_LINK"
        user_states[uid] = state
        await update.message.reply_text("ارسل رابط المشاهدة أو Token:")
        return

    if state.get("step") == "ADD_EPISODE_LINK":
        season = state.get("add_season")
        episode = state.get("add_episode")
        tmdb_id = state.get("review_tmdb")
        
        episode_key = f"{season}-{episode}"
        new_links = {episode_key: text}
        
        await update.message.reply_text("جاري تحديث الملف...")
        
        ok = await update_series_episodes(tmdb_id, new_links)
        
        if ok:
            # إضافة كارت في قسم "حلقات مضافة حديثاً" تلقائياً
            series_data = state.get("review_series")
            if series_data:
                # تحديد العناوين
                titles = determine_title_display(series_data)
                if titles.get("secondary") == "FETCH_ARABIC":
                    arabic_title = await fetch_arabic_title(tmdb_id, "tv")
                    if arabic_title and arabic_title != titles["primary"]:
                        titles["secondary"] = arabic_title
                    else:
                        titles["secondary"] = None
                
                recent_card = build_recent_episode_card(series_data, tmdb_id, season, episode, titles)
                ok_recent = await push_recent_episode_to_github(recent_card)
                
                recent_info = ""
                if ok_recent:
                    recent_info = "\n✨ تمت الإضافة في قسم 'حلقات مضافة حديثاً' في الصفحة الرئيسية"
                # لا نعرض رسالة الخطأ إذا فشل - فقط نتجاهل
                
                await update.message.reply_text(f"✅ تمت اضافة الحلقة S{season} E{episode} بنجاح!{recent_info}")
            else:
                await update.message.reply_text(f"✅ تمت اضافة الحلقة S{season} E{episode} بنجاح!")
        else:
            await update.message.reply_text("فشل في تحديث الملف.")
        
        user_states.pop(uid, None)
        await show_main_menu(update)
        return

    # اضافة حلقات متعددة - الخطوة 1: رقم الموسم
    if state.get("step") == "ADD_BULK_EPISODES_SEASON":
        if not text.isdigit():
            await update.message.reply_text("ارسل رقم صحيح")
            return
        state["bulk_season"] = int(text)
        state["step"] = "ADD_BULK_EPISODES_START"
        user_states[uid] = state
        await update.message.reply_text("ارسل رقم الحلقة الأولى (البداية):")
        return

    # اضافة حلقات متعددة - الخطوة 2: رقم الحلقة الأولى
    if state.get("step") == "ADD_BULK_EPISODES_START":
        if not text.isdigit():
            await update.message.reply_text("ارسل رقم صحيح")
            return
        state["bulk_start"] = int(text)
        state["step"] = "ADD_BULK_EPISODES_LINKS"
        user_states[uid] = state
        season = state.get("bulk_season")
        start_ep = state.get("bulk_start")
        await update.message.reply_text(
            f"الموسم {season} - بدءاً من الحلقة {start_ep}:\n\n"
            f"ارسل روابط/Tokens الحلقات (كل سطر = حلقة واحدة بالترتيب):\n"
            f"الحلقة {start_ep}: السطر الأول\n"
            f"الحلقة {start_ep + 1}: السطر الثاني\n"
            f"وهكذا..."
        )
        return

    # اضافة حلقات متعددة - الخطوة 3: الروابط
    if state.get("step") == "ADD_BULK_EPISODES_LINKS":
        season = state.get("bulk_season")
        start_ep = state.get("bulk_start")
        tmdb_id = state.get("review_tmdb")
        
        # تقسيم الروابط حسب الأسطر
        links = [link.strip() for link in text.strip().split('\n') if link.strip()]
        
        if len(links) == 0:
            await update.message.reply_text("لم يتم إرسال أي روابط. حاول مرة أخرى.")
            return
        
        # حفظ الروابط بدءاً من رقم الحلقة المحدد
        new_links = {}
        for i, link in enumerate(links):
            episode_num = start_ep + i
            episode_key = f"{season}-{episode_num}"
            new_links[episode_key] = link
        
        await update.message.reply_text("جاري تحديث الملف...")
        
        ok = await update_series_episodes(tmdb_id, new_links)
        
        if ok:
            # إضافة آخر حلقة في قسم "حلقات مضافة حديثاً"
            series_data = state.get("review_series")
            recent_info = ""
            if series_data:
                titles = determine_title_display(series_data)
                if titles.get("secondary") == "FETCH_ARABIC":
                    arabic_title = await fetch_arabic_title(tmdb_id, "tv")
                    if arabic_title and arabic_title != titles["primary"]:
                        titles["secondary"] = arabic_title
                    else:
                        titles["secondary"] = None
                
                # إضافة كارت لآخر حلقة مضافة
                last_ep = start_ep + len(links) - 1
                recent_card = build_recent_episode_card(series_data, tmdb_id, season, last_ep, titles)
                ok_recent = await push_recent_episode_to_github(recent_card)
                
                if ok_recent:
                    recent_info = "\n✨ تمت الإضافة في قسم 'حلقات مضافة حديثاً'"
            
            episodes_range = f"E{start_ep}-E{start_ep + len(links) - 1}" if len(links) > 1 else f"E{start_ep}"
            await update.message.reply_text(f"✅ تمت اضافة {len(links)} حلقات S{season} {episodes_range} بنجاح!{recent_info}")
        else:
            await update.message.reply_text("فشل في تحديث الملف.")
        
        user_states.pop(uid, None)
        await show_main_menu(update)
        return

    # اضافة موسم جديد
    if state.get("step") == "ADD_SEASON_NUMBER":
        if not text.isdigit():
            await update.message.reply_text("ارسل رقم صحيح")
            return
        state["new_season"] = int(text)
        state["step"] = "ADD_SEASON_BULK_LINKS"
        user_states[uid] = state
        
        season = state.get("new_season")
        await update.message.reply_text(
            f"الموسم {season}:\n\n"
            f"ارسل روابط/Tokens الحلقات (كل سطر = حلقة واحدة بالترتيب):\n"
            f"مثال:\n"
            f"token1\n"
            f"token2\n"
            f"token3"
        )
        return

    if state.get("step") == "ADD_SEASON_BULK_LINKS":
        season = state.get("new_season")
        tmdb_id = state.get("review_tmdb")
        
        # تقسيم الروابط حسب الأسطر
        links = [link.strip() for link in text.strip().split('\n') if link.strip()]
        
        if len(links) == 0:
            await update.message.reply_text("لم يتم إرسال أي روابط. حاول مرة أخرى.")
            return
        
        # حفظ الروابط
        new_links = {}
        for i, link in enumerate(links, 1):
            episode_key = f"{season}-{i}"
            new_links[episode_key] = link
        
        await update.message.reply_text("جاري تحديث الملف...")
        
        ok = await update_series_episodes(tmdb_id, new_links)
        
        if ok:
            # إضافة آخر حلقة في قسم "حلقات مضافة حديثاً"
            series_data = state.get("review_series")
            recent_info = ""
            if series_data:
                titles = determine_title_display(series_data)
                if titles.get("secondary") == "FETCH_ARABIC":
                    arabic_title = await fetch_arabic_title(tmdb_id, "tv")
                    if arabic_title and arabic_title != titles["primary"]:
                        titles["secondary"] = arabic_title
                    else:
                        titles["secondary"] = None
                
                # إضافة كارت لآخر حلقة من الموسم المضاف
                last_ep = len(links)
                recent_card = build_recent_episode_card(series_data, tmdb_id, season, last_ep, titles)
                ok_recent = await push_recent_episode_to_github(recent_card)
                
                if ok_recent:
                    recent_info = "\n✨ تمت الإضافة في قسم 'حلقات مضافة حديثاً'"
                # لا نعرض رسالة الخطأ إذا فشل
            
            await update.message.reply_text(f"✅ تمت اضافة الموسم {season} بنجاح! ({len(new_links)} حلقة){recent_info}")
        else:
            await update.message.reply_text("فشل في تحديث الملف.")
        
        user_states.pop(uid, None)
        await show_main_menu(update)
        return

    # تعديل رابط حلقة
    if state.get("step") == "EDIT_EPISODE_KEY":
        if not re.match(r'^\d+-\d+$', text):
            await update.message.reply_text("صيغة غير صحيحة. استخدم: رقم_الموسم-رقم_الحلقة")
            return
        state["edit_key"] = text
        state["step"] = "EDIT_EPISODE_LINK"
        user_states[uid] = state
        await update.message.reply_text("ارسل الرابط الجديد:")
        return

    if state.get("step") == "EDIT_EPISODE_LINK":
        edit_key = state.get("edit_key")
        tmdb_id = state.get("review_tmdb")
        
        await update.message.reply_text("جاري تحديث الملف...")
        
        ok = await update_series_episodes(tmdb_id, {edit_key: text})
        
        if ok:
            await update.message.reply_text(f"تم تحديث رابط الحلقة {edit_key} بنجاح!")
        else:
            await update.message.reply_text("فشل في تحديث الملف.")
        
        user_states.pop(uid, None)
        await show_main_menu(update)
        return

    # حذف حلقة
    if state.get("step") == "DELETE_EPISODE_KEY":
        if not re.match(r'^\d+-\d+$', text):
            await update.message.reply_text("صيغة غير صحيحة. استخدم: رقم_الموسم-رقم_الحلقة")
            return
        
        delete_key = text
        tmdb_id = state.get("review_tmdb")
        
        # جلب الروابط الحالية وحذف الحلقة
        html_content = await get_series_html(tmdb_id)
        current_links = extract_episode_links(html_content) if html_content else {}
        
        if delete_key in current_links:
            del current_links[delete_key]
            
            await update.message.reply_text("جاري تحديث الملف...")
            
            ok = await upload_series_html(tmdb_id, current_links)
            
            if ok:
                await update.message.reply_text(f"تم حذف الحلقة {delete_key} بنجاح!")
            else:
                await update.message.reply_text("فشل في تحديث الملف.")
        else:
            await update.message.reply_text(f"الحلقة {delete_key} غير موجودة.")
        
        user_states.pop(uid, None)
        await show_main_menu(update)
        return

    # ===== حذف كارت =====
    if text == "حذف كارت":
        keyboard = [["الصفحة الرئيسية", "صفحة اكتشف"], ["رجوع"]]
        await update.message.reply_text("اختر من اين تريد حذف الكارت:", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))
        user_states[uid] = {"step": "DELETE_CHOOSE_PAGE"}
        return

    if text == "رجوع":
        user_states.pop(uid, None)
        await show_main_menu(update)
        return

    if state.get("step") == "DELETE_CHOOSE_PAGE":
        if text == "الصفحة الرئيسية":
            keyboard = [
                ["🆕 الاضافات الأخيرة", "🔥 الاعمال الجديدة"],
                ["⭐ أعمال مميزة", "🎞️ 4K"],
                ["🇮🇶 افلام عربية", "🇮🇳 افلام هندية"],
                ["🎁 عروض مميزة", "📺 مسلسلات"],
                ["رجوع"]
            ]
            await update.message.reply_text("اختر القسم:", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))
            user_states[uid] = {"step": "DELETE_MAIN_SECTION"}
            return
        elif text == "صفحة اكتشف":
            await update.message.reply_text("جاري جلب اخر 5 كاردات من صفحة اكتشف...")
            cards = await get_cards_from_file(DISCOVER_FILE, MARKERS["DISCOVER"][0], MARKERS["DISCOVER"][1], 5)
            
            if not cards:
                await update.message.reply_text("لا توجد كاردات في صفحة اكتشف.")
                user_states.pop(uid, None)
                await show_main_menu(update)
                return
            
            user_states[uid] = {"step": "DELETE_DISCOVER_SELECT", "cards": cards}
            
            keyboard = []
            for card in cards:
                try:
                    if card['img']:
                        await update.message.reply_photo(photo=card['img'], caption=f"{card['title']}\nID: {card['id']}")
                except Exception as e:
                    await update.message.reply_text(f"{card['title']}\nID: {card['id']}")
                keyboard.append([f"حذف: {card['title'][:20]}... ({card['id']})"])
            
            keyboard.append(["رجوع"])
            await update.message.reply_text("اختر الكارت الذي تريد حذفه:", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))
            return

    if state.get("step") == "DELETE_MAIN_SECTION":
        if text == "رجوع":
            keyboard = [["الصفحة الرئيسية", "صفحة اكتشف"], ["رجوع"]]
            await update.message.reply_text("اختر من اين تريد حذف الكارت:", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))
            user_states[uid] = {"step": "DELETE_CHOOSE_PAGE"}
            return
        
        section_name = text
        clean_section = clean_section_name(section_name)
        section_key = SECTION_MARKERS.get(clean_section, "LATEST")
        
        if section_key not in MARKERS:
            await update.message.reply_text(f"القسم '{section_name}' غير موجود.")
            return
        
        await update.message.reply_text(f"جاري جلب اخر 5 كاردات من قسم {section_name}...")
        cards = await get_cards_from_file(MAIN_FILE, MARKERS[section_key][0], MARKERS[section_key][1], 5)
        
        if not cards:
            await update.message.reply_text(f"لا توجد كاردات في قسم {section_name}.")
            user_states.pop(uid, None)
            await show_main_menu(update)
            return
        
        user_states[uid] = {"step": "DELETE_MAIN_SELECT", "cards": cards, "section": section_name, "section_key": section_key}
        
        keyboard = []
        for card in cards:
            try:
                if card['img']:
                    await update.message.reply_photo(photo=card['img'], caption=f"{card['title']}\nID: {card['id']}")
            except Exception as e:
                await update.message.reply_text(f"{card['title']}\nID: {card['id']}")
            keyboard.append([f"حذف: {card['title'][:20]}... ({card['id']})"])
        
        keyboard.append(["رجوع"])
        await update.message.reply_text("اختر الكارت الذي تريد حذفه:", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))
        return

    if state.get("step") == "DELETE_MAIN_SELECT":
        if text == "رجوع":
            keyboard = [
                ["🆕 الاضافات الأخيرة", "🔥 الاعمال الجديدة"],
                ["⭐ أعمال مميزة", "🎞️ 4K"],
                ["🇮🇶 افلام عربية", "🇮🇳 افلام هندية"],
                ["🎁 عروض مميزة", "📺 مسلسلات"],
                ["رجوع"]
            ]
            await update.message.reply_text("اختر القسم:", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))
            user_states[uid] = {"step": "DELETE_MAIN_SECTION"}
            return
        
        id_match = re.search(r'\((\d+)\)$', text)
        if not id_match:
            await update.message.reply_text("لم يتم العثور على ID صحيح.")
            return
        
        card_id = id_match.group(1)
        section_key = state.get("section_key", "LATEST")
        section_name = state.get("section", "")
        
        await update.message.reply_text(f"جاري حذف الكارت {card_id}...")
        
        ok = await delete_card_from_github(card_id, MAIN_FILE, MARKERS[section_key][0], MARKERS[section_key][1])
        
        if ok:
            await update.message.reply_text(f"تم حذف ��لكارت من {section_name}\nID: {card_id}")
        else:
            await update.message.reply_text("فشل حذف الكارت.")
        
        user_states.pop(uid, None)
        await show_main_menu(update)
        return

    if state.get("step") == "DELETE_DISCOVER_SELECT":
        if text == "رجوع":
            keyboard = [["الصفحة الرئيسية", "صفحة اكتشف"], ["رجوع"]]
            await update.message.reply_text("اختر من اين تريد حذف الكارت:", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))
            user_states[uid] = {"step": "DELETE_CHOOSE_PAGE"}
            return
        
        id_match = re.search(r'\((\d+)\)$', text)
        if not id_match:
            await update.message.reply_text("لم يتم العثور على ID صحيح.")
            return
        
        card_id = id_match.group(1)
        
        await update.message.reply_text(f"جاري حذف الكارت {card_id}...")
        
        ok = await delete_card_from_github(card_id, DISCOVER_FILE, MARKERS["DISCOVER"][0], MARKERS["DISCOVER"][1])
        
        if ok:
            await update.message.reply_text(f"تم حذف الكارت من صفحة اكتشف\nID: {card_id}")
        else:
            await update.message.reply_text("فشل حذف الكارت.")
        
        user_states.pop(uid, None)
        await show_main_menu(update)
        return

# ----------------------------- MAIN -----------------------------
def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    logger.info("Bot started with Series Management")
    app.run_polling()

if __name__ == "__main__":
    main()
