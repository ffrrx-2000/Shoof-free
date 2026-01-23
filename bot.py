# bot.py - Cinema Plus Bot with BeautifulSoup HTML Parser
import asyncio
import aiohttp
import base64
import json
import logging
import re
from typing import Optional
from bs4 import BeautifulSoup, Comment

from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, InputMediaPhoto
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# ----------------------------- CONFIG -----------------------------
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GITHUB_TOKEN   = os.getenv("GITHUB_TOKEN")
REPO_OWNER = "ffrrx-2000"
REPO_NAME  = "cinema-plas-bot"
BRANCH     = "main"

# Files in repo
MAIN_FILE     = "index.html"
DISCOVER_FILE = "discover.html"

TMDB_API_KEY  = os.getenv("TMDB_API_KEY")
ADMIN_ID = 5529978863

GITHUB_HEADERS = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3+json"
}

# Markers - تطابق الموجودة في ملف HTML
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
}

# ربط اسماء الاقسام بالمفاتيح
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

# ----------------------------- LOGGING -----------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ----------------------------- STATE -----------------------------
user_states = {}

# ----------------------------- TMDB HELPERS -----------------------------
async def fetch_tmdb(path: str) -> Optional[dict]:
    url = f"https://api.themoviedb.org/3{path}?api_key={TMDB_API_KEY}&language=ar"
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

# ----------------------------- HTML CARD BUILDERS -----------------------------
def build_card_movie_main(m: dict, tmdb_id: str, mux_id: str = "") -> str:
    poster_w500 = f"https://image.tmdb.org/t/p/w500{m.get('poster_path')}" if m.get("poster_path") else ""
    poster_orig = f"https://image.tmdb.org/t/p/original{m.get('poster_path')}" if m.get("poster_path") else poster_w500
    title = m.get("title", "")
    rating = f"{m.get('vote_average', 0):.1f}"
    year = (m.get("release_date") or "")[:4] or ""
    
    if mux_id:
        href = f"movie.html?tmdb={tmdb_id}&mux={mux_id}"
    else:
        href = f"movie.html?tmdb={tmdb_id}"
    
    return f'''<div class="card-wrapper">
<a class="card" href="{href}">
<img class="lazy loaded" loading="lazy"
src="{poster_w500}"
data-src-original="{poster_orig}">
<div class="card-overlay">
<i class="fas fa-play play-icon"></i>
<span class="card-desc">Cinema Plus عالم من المتعة</span>
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
    title = m.get("title", "").replace('"', "&quot;")
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

def build_card_series_main(s: dict, tmdb_id: str) -> str:
    poster_w500 = f"https://image.tmdb.org/t/p/w500{s.get('poster_path')}" if s.get("poster_path") else ""
    poster_orig = f"https://image.tmdb.org/t/p/original{s.get('poster_path')}" if s.get("poster_path") else poster_w500
    title = s.get("name", "")
    rating = f"{s.get('vote_average', 0):.1f}"
    year = (s.get("first_air_date") or "")[:4] or ""
    
    href = f"series.html?tmdb={tmdb_id}"

    return f'''<div class="card-wrapper">
<a class="card" href="{href}">
<img class="lazy loaded" loading="lazy"
src="{poster_w500}"
data-src-original="{poster_orig}">
<div class="card-overlay">
<i class="fas fa-play play-icon"></i>
<span class="card-desc">Cinema Plus عالم من المتعة</span>
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

def build_card_series_discover(s: dict, tmdb_id: str) -> str:
    genres = "|".join([g.get("name", "") for g in s.get("genres", [])])
    year = (s.get("first_air_date") or "")[:4] or ""
    poster_w500 = f"https://image.tmdb.org/t/p/w500{s.get('poster_path')}" if s.get("poster_path") else ""
    poster_orig = f"https://image.tmdb.org/t/p/original{s.get('poster_path')}" if s.get("poster_path") else poster_w500
    title = s.get("name", "").replace('"', "&quot;")
    rating = f"{s.get('vote_average', 0):.1f}"
    
    href = f"series.html?tmdb={tmdb_id}"

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

# ----------------------------- BeautifulSoup HTML HELPERS -----------------------------
def insert_card_with_bs4(html_content: str, card_html: str, start_marker: str, end_marker: str) -> Optional[str]:
    """
    ادراج كارت في HTML باستخدام BeautifulSoup
    يبحث عن التعليق START ويضيف الكارت بعده مباشرة
    """
    # التحقق من وجود الـ markers
    if start_marker not in html_content or end_marker not in html_content:
        logger.error(f"Markers not found: {start_marker}")
        return None
    
    # استخدام BeautifulSoup لتحليل HTML
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # البحث عن التعليق START
    start_comment = None
    for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
        if start_marker.replace('<!-- ', '').replace(' -->', '').strip() in comment.strip():
            start_comment = comment
            break
    
    if not start_comment:
        logger.error(f"Start comment not found: {start_marker}")
        return None
    
    # تحليل الكارت الجديد
    new_card_soup = BeautifulSoup(card_html, 'html.parser')
    new_card = new_card_soup.find('div', class_='card-wrapper')
    
    if not new_card:
        logger.error("Could not parse new card HTML")
        return None
    
    # ادراج الكارت بعد التعليق START مباشرة
    start_comment.insert_after(new_card)
    
    # اعادة تنسيق HTML
    return str(soup)

def delete_card_with_bs4(html_content: str, tmdb_id: str, start_marker: str, end_marker: str) -> Optional[str]:
    """
    حذف كارت من HTML باستخدام BeautifulSoup
    يبحث عن الكارت بناءً على TMDB ID ويحذفه بالكامل
    """
    if start_marker not in html_content or end_marker not in html_content:
        logger.error(f"Markers not found: {start_marker}")
        return None
    
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # البحث عن جميع الكاردات
    cards = soup.find_all('div', class_='card-wrapper')
    
    card_found = False
    for card in cards:
        # البحث عن الرابط داخل الكارت
        link = card.find('a', href=True)
        if link:
            href = link.get('href', '')
            # التحقق من تطابق TMDB ID
            if f'tmdb={tmdb_id}' in href or f'go:{tmdb_id}' in href:
                # حذف الكارت بالكامل
                card.decompose()
                card_found = True
                logger.info(f"Card with tmdb={tmdb_id} deleted successfully")
                break
    
    if not card_found:
        logger.error(f"Card with tmdb={tmdb_id} not found")
        return None
    
    return str(soup)

def extract_cards_with_bs4(html_content: str, start_marker: str, end_marker: str, count: int = 5) -> list:
    """
    استخراج الكاردات من HTML باستخدام BeautifulSoup
    """
    if start_marker not in html_content or end_marker not in html_content:
        return []
    
    # استخراج المحتوى بين الـ markers
    start_idx = html_content.find(start_marker) + len(start_marker)
    end_idx = html_content.find(end_marker)
    section_content = html_content[start_idx:end_idx]
    
    soup = BeautifulSoup(section_content, 'html.parser')
    cards = soup.find_all('div', class_='card-wrapper')
    
    result = []
    for card in cards[:count]:
        # استخراج العنوان
        title_elem = card.find('h3', class_='card-details-title')
        title = title_elem.get_text(strip=True) if title_elem else "بدون عنوان"
        
        # استخراج الصورة
        img_elem = card.find('img')
        img = img_elem.get('src', '') if img_elem else ""
        
        # استخراج TMDB ID من الرابط
        link = card.find('a', href=True)
        card_id = ""
        if link:
            href = link.get('href', '')
            # البحث عن tmdb=XXX او go:XXX
            tmdb_match = re.search(r'tmdb=(\d+)', href)
            go_match = re.search(r'go:(\d+)', href)
            if tmdb_match:
                card_id = tmdb_match.group(1)
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

async def github_put_file(session: aiohttp.ClientSession, path: str, content_b64: str, sha: str, message: str) -> Optional[dict]:
    url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents/{path}"
    payload = {
        "message": message,
        "content": content_b64,
        "sha": sha,
        "branch": BRANCH
    }
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
    """ارسال كارت جديد الى GitHub باستخدام BeautifulSoup"""
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
    """حذف كارت من GitHub باستخدام BeautifulSoup"""
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
    """جلب الكاردات من ملف GitHub"""
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

# ----------------------------- TELEGRAM HANDLERS -----------------------------
MAIN_KEYBOARD = [["اضافة فيلم", "اضافة مسلسل"], ["حذف كارت"]]

async def show_main_menu(update: Update):
    """عرض القائمة الرئيسية"""
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
    """تنظيف اسم القسم من الايموجي"""
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

        # تحديد القسم المختار
        clean_section = clean_section_name(section_name)
        section_key = SECTION_MARKERS.get(clean_section, "LATEST")
        
        logger.info(f"Adding movie to section: {section_name} -> {clean_section} -> {section_key}")
        
        # التحقق من وجود الـ markers
        if section_key not in MARKERS:
            await update.message.reply_text(f"القسم '{section_name}' غير موجود في النظام.")
            user_states.pop(uid, None)
            await show_main_menu(update)
            return

        # الاضافة للقسم المختار
        ok_main = await push_card_to_github(card_main, MAIN_FILE, MARKERS[section_key][0], MARKERS[section_key][1])
        ok_disc = await push_card_to_github(card_disc, DISCOVER_FILE, MARKERS["DISCOVER"][0], MARKERS["DISCOVER"][1])

        if ok_main and ok_disc:
            mux_info = f"\nMUX ID: {mux_id}" if mux_id else ""
            await update.message.reply_text(
                f"تمت العملية بنجاح!\n\n"
                f"تم اضافة الفيلم: {movie.get('title')}\n"
                f"TMDB ID: {tmdb_id}{mux_info}\n"
                f"القسم: {section_name}"
            )
        elif ok_main:
            await update.message.reply_text(
                f"تم اضافة الفيلم للصفحة الرئيسية فقط.\n"
                f"فشل الاضافة لصفحة اكتشف (تحقق من وجود markers)."
            )
        elif ok_disc:
            await update.message.reply_text(
                f"فشل الاضافة للقسم '{section_name}'.\n"
                f"تحقق من وجود الـ markers في ملف HTML:\n"
                f"{MARKERS[section_key][0]}\n{MARKERS[section_key][1]}"
            )
        else:
            await update.message.reply_text(
                f"فشل الاضافة.\n"
                f"تحقق من وجود الـ markers في ملفات HTML."
            )

        user_states.pop(uid, None)
        await show_main_menu(update)
        return

    # ===== اضافة مسلسل =====
    if text == "اضافة مسلسل":
        keyboard = [
            ["🆕 الاضافات الأخيرة", "📺 مسلسلات"],
            ["⭐ أعمال مميزة"],
            ["رجوع"]
        ]
        await update.message.reply_text("اختر القسم:", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))
        user_states[uid] = {"step": "SERIES_SECTION"}
        return

    if state.get("step") == "SERIES_SECTION":
        if text == "رجوع":
            user_states.pop(uid, None)
            await show_main_menu(update)
            return
        state["section"] = text
        state["step"] = "SERIES_ID"
        user_states[uid] = state
        await update.message.reply_text("ارسل TMDB ID للمسلسل", reply_markup=ReplyKeyboardRemove())
        return

    if state.get("step") == "SERIES_ID":
        if not text.isdigit():
            await update.message.reply_text("ID غير صحيح")
            return
        tmdb_id = text
        section_name = state.get("section", "")
        
        await update.message.reply_text("جاري جلب بيانات المسلسل ورفع الكارت...")

        series = await get_series(tmdb_id)
        if not series:
            await update.message.reply_text("فشل جلب بيانات المسلسل من TMDB.")
            user_states.pop(uid, None)
            await show_main_menu(update)
            return

        card_main = build_card_series_main(series, tmdb_id)
        card_disc = build_card_series_discover(series, tmdb_id)

        # تحديد القسم المختار
        clean_section = clean_section_name(section_name)
        section_key = SECTION_MARKERS.get(clean_section, "LATEST")
        
        logger.info(f"Adding series to section: {section_name} -> {clean_section} -> {section_key}")

        # التحقق من وجود الـ markers
        if section_key not in MARKERS:
            await update.message.reply_text(f"القسم '{section_name}' غير موجود في النظام.")
            user_states.pop(uid, None)
            await show_main_menu(update)
            return

        ok_main = await push_card_to_github(card_main, MAIN_FILE, MARKERS[section_key][0], MARKERS[section_key][1])
        ok_disc = await push_card_to_github(card_disc, DISCOVER_FILE, MARKERS["DISCOVER"][0], MARKERS["DISCOVER"][1])

        if ok_main and ok_disc:
            await update.message.reply_text(
                f"تمت العملية بنجاح!\n\n"
                f"تم اضافة المسلسل: {series.get('name')}\n"
                f"TMDB ID: {tmdb_id}\n"
                f"القسم: {section_name}"
            )
        elif ok_main:
            await update.message.reply_text(
                f"تم اضافة المسلسل للصفحة الرئيسية فقط.\n"
                f"فشل الاضافة لصفحة اكتشف."
            )
        elif ok_disc:
            await update.message.reply_text(
                f"فشل الاضافة للقسم '{section_name}'.\n"
                f"تحقق من وجود الـ markers في ملف HTML."
            )
        else:
            await update.message.reply_text("فشل الاضافة. تحقق من الـ markers.")

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
            
            user_states[uid] = {"step": "DELETE_DISCOVER_SELECT", "cards": cards, "page": "discover"}
            
            keyboard = []
            for i, card in enumerate(cards, 1):
                try:
                    if card['img']:
                        await update.message.reply_photo(
                            photo=card['img'],
                            caption=f"{card['title']}\nID: {card['id']}"
                        )
                except Exception as e:
                    logger.warning(f"Failed to send photo: {e}")
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
        
        user_states[uid] = {"step": "DELETE_MAIN_SELECT", "cards": cards, "section": section_name, "section_key": section_key, "page": "main"}
        
        keyboard = []
        for i, card in enumerate(cards, 1):
            try:
                if card['img']:
                    await update.message.reply_photo(
                        photo=card['img'],
                        caption=f"{card['title']}\nID: {card['id']}"
                    )
            except Exception as e:
                logger.warning(f"Failed to send photo: {e}")
                await update.message.reply_text(f"{card['title']}\nID: {card['id']}")
            keyboard.append([f"حذف: {card['title'][:20]}... ({card['id']})"])
        
        keyboard.append(["رجوع"])
        await update.message.reply_text("اختر الكارت الذي تريد حذفه:", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))
        return

    # معالجة اختيار الحذف من الصفحة الرئيسية
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
        
        # استخراج ID من النص
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
            await update.message.reply_text(
                f"تمت العملية بنجاح!\n\n"
                f"تم حذف الكارت من الصفحة الرئيسية\n"
                f"ID: {card_id}\n"
                f"القسم: {section_name}"
            )
        else:
            await update.message.reply_text("فشل حذف الكارت. قد يكون غير موجود.")
        
        user_states.pop(uid, None)
        await show_main_menu(update)
        return

    # معالجة اختيار الحذف من صفحة اكتشف
    if state.get("step") == "DELETE_DISCOVER_SELECT":
        if text == "رجوع":
            keyboard = [["الصفحة الرئيسية", "صفحة اكتشف"], ["رجوع"]]
            await update.message.reply_text("اختر من اين تريد حذف الكارت:", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))
            user_states[uid] = {"step": "DELETE_CHOOSE_PAGE"}
            return
        
        # استخراج ID من النص
        id_match = re.search(r'\((\d+)\)$', text)
        if not id_match:
            await update.message.reply_text("لم يتم العثور على ID صحيح.")
            return
        
        card_id = id_match.group(1)
        
        await update.message.reply_text(f"جاري حذف الكارت {card_id}...")
        
        ok = await delete_card_from_github(card_id, DISCOVER_FILE, MARKERS["DISCOVER"][0], MARKERS["DISCOVER"][1])
        
        if ok:
            await update.message.reply_text(
                f"تمت العملية بنجاح!\n\n"
                f"تم حذف الكارت من صفحة اكتشف\n"
                f"ID: {card_id}"
            )
        else:
            await update.message.reply_text("فشل حذف الكارت. قد يكون غير موجود.")
        
        user_states.pop(uid, None)
        await show_main_menu(update)
        return

# ----------------------------- MAIN -----------------------------
def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    logger.info("Bot started with BeautifulSoup HTML parser")
    app.run_polling()

if __name__ == "__main__":
    main()
