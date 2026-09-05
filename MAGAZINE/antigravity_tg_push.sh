#!/bin/bash
# ==========================================================================
# ANTIGRAVITY TELEGRAM & RSS PUBLISHING PIPELINE
# Automates pre-flight checks, language injection, Telegram posting,
# iframe widget patching, RSS feed compilation, and git amend push.
# ==========================================================================
set -e

# Load local environment file if present in the script's directory
ENV_FILE="$(dirname "$0")/.env"
if [ -f "$ENV_FILE" ]; then
    while IFS= read -r line || [ -n "$line" ]; do
        if [[ ! "$line" =~ ^# ]] && [[ ! -z "$line" ]]; then
            export "$line"
        fi
    done < "$ENV_FILE"
fi

TARGET_FILE="$1"
LANG_CODE="$2"

if [ -z "$TARGET_FILE" ] || [ -z "$LANG_CODE" ]; then
    echo "Błąd: Brak argumentów."
    echo "Użycie: ./antigravity_tg_push.sh <ścieżka_do_pliku> <kod_języka>"
    exit 1
fi

if [ -z "$TG_BOT_TOKEN" ]; then
    echo "Błąd: Brak zmiennej środowiskowej TG_BOT_TOKEN."
    echo "Zdefiniuj ją w swoim środowisku systemowym lub w pliku .env w katalogu MAGAZINE."
    exit 1
fi

# Resolve absolute path of TARGET_FILE before changing directory
if [[ "$TARGET_FILE" != /* ]] && [[ "$TARGET_FILE" != [A-Za-z]:* ]]; then
    TARGET_FILE="$(pwd)/$TARGET_FILE"
fi

# Change directory to the script's directory to ensure relative path consistency
cd "$(dirname "$0")"

CHAT_ID="${TG_CHAT_ID:-@emochangeling}"
DOMENA="${DOMAIN:-https://reverse.emo-changeling.xyz}"

# 0. Pre-flight Check
echo "-> Sprawdzanie autoryzacji z repozytorium..."
if ! git ls-remote origin HEAD &>/dev/null; then
    echo "[ERR] Brak połączenia z repozytorium. Zaloguj się lub upewnij się, że git działa."
    exit 1
fi

# 1. Wstrzyknięcie języka do kontenera publicystyki
python3 - "$TARGET_FILE" "$LANG_CODE" "inject_lang" << 'EOF'
import sys
import re

target_file = sys.argv[1]
lang_code = sys.argv[2]

with open(target_file, 'r', encoding='utf-8') as f:
    content = f.read()

article_tag_match = re.search(r'<article([^>]*)>', content, re.IGNORECASE)
if article_tag_match:
    attrs = article_tag_match.group(1)
    if 'lang=' in attrs:
        new_attrs = re.sub(r'lang="[^"]*"', f'lang="{lang_code}"', attrs)
        content = content.replace(article_tag_match.group(0), f'<article{new_attrs}>', 1)
    else:
        content = content.replace(article_tag_match.group(0), f'<article lang="{lang_code}"{attrs}>', 1)

with open(target_file, 'w', encoding='utf-8') as f:
    f.write(content)
print(f"-> Injected lang='{lang_code}' into <article> tag.")
EOF

# 2. Pierwszy PUSH (Żeby strona fizycznie zaistniała w sieci przed postem na TG)
echo "-> Pierwszy push artykułu..."
antigravity push "$TARGET_FILE" </dev/tty >/dev/tty 2>&1

# 3. Interakcja z Telegramem i wstrzyknięcie widgetu z Message ID
python3 - "$TARGET_FILE" "$CHAT_ID" "$DOMENA" << 'EOF'
import sys
import os
import re
import json
import urllib.request

target_file = sys.argv[1]
chat_id = sys.argv[2]
domain = sys.argv[3]

token = os.environ.get("TG_BOT_TOKEN")
if not token:
    print("Error: TG_BOT_TOKEN environment variable not set.", file=sys.stderr)
    sys.exit(1)

with open(target_file, 'r', encoding='utf-8') as f:
    content = f.read()

# Extract Title
title_match = re.search(r'<title>(.*?)</title>', content, re.IGNORECASE | re.DOTALL)
title = title_match.group(1).strip() if title_match else "New Article"
title_clean = re.sub(r'\s*\|\s*.*', '', title)

# Extract Description
desc_match = re.search(r'<meta\s+name="description"\s+content="([^"]*)"', content, re.IGNORECASE)
desc = desc_match.group(1).strip() if desc_match else ""

# Extract relative path to compute absolute URL
abs_target = os.path.abspath(target_file)
parts = re.split(r'[/\\]MAGAZINE[/\\]', abs_target)
if len(parts) > 1:
    rel_path = parts[-1].replace('\\', '/')
else:
    rel_path = os.path.basename(abs_target)

url = f"{domain}/{rel_path}"

# Format Telegram message
tg_message = f"<b>{title_clean}</b>\n\n{desc}\n\nRead more: {url}"

# Send POST request to Telegram API
tg_url = f"https://api.telegram.org/bot{token}/sendMessage"
payload = {
    "chat_id": chat_id,
    "text": tg_message,
    "parse_mode": "HTML"
}
data = json.dumps(payload).encode('utf-8')
req = urllib.request.Request(
    tg_url,
    data=data,
    headers={"Content-Type": "application/json"}
)

try:
    with urllib.request.urlopen(req) as response:
        res = json.loads(response.read().decode('utf-8'))
        if res.get("ok"):
            message_id = res["result"]["message_id"]
            print(f"-> Telegram post created. Message ID: {message_id}")
        else:
            print(f"Telegram API error: {res}", file=sys.stderr)
            sys.exit(1)
except Exception as e:
    print(f"Error posting to Telegram: {e}", file=sys.stderr)
    sys.exit(1)

# Build Telegram embed widget code
channel_name = chat_id.lstrip('@')
widget_html = f'<div translate="no" class="notranslate" style="margin-top: 30px;"><iframe src="https://t.me/{channel_name}/{message_id}?embed=1" translate="no" class="notranslate" style="border: none; width: 100%; height: 400px; background: #000;"></iframe></div>'

# Replaces the marker with the widget code
if "<!-- TELEGRAM_WIDGET_HERE -->" in content:
    content = content.replace("<!-- TELEGRAM_WIDGET_HERE -->", widget_html)
    with open(target_file, 'w', encoding='utf-8') as f:
        f.write(content)
    print("-> Patched HTML with Telegram iframe widget.")
else:
    print("Warning: <!-- TELEGRAM_WIDGET_HERE --> marker not found in HTML.", file=sys.stderr)
EOF

# 4. Generowanie / Aktualizacja RSS 2.0
python3 - "$DOMENA" << 'EOF'
import sys
import os
import re
import datetime

domain = sys.argv[1]
magazine_dir = os.getcwd()
articles_dir = os.path.join(magazine_dir, "articles")
output_path = os.path.join(magazine_dir, "rss.xml")

def format_rfc822(date_str):
    days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    try:
        parts = date_str.split('-')
        year, month, day = int(parts[0]), int(parts[1]), int(parts[2])
        dt = datetime.date(year, month, day)
        weekday = days[dt.weekday()]
        month_name = months[month - 1]
        return f"{weekday}, {day:02d} {month_name} {year} 12:00:00 +0200"
    except Exception:
        now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2)))
        return now.strftime("%a, %d %b %Y %H:%M:%S %z")

def make_absolute(html_content):
    html_content = re.sub(r'src="(?:\.\./)*img/', f'src="{domain}/img/', html_content)
    html_content = re.sub(r'src="/img/', f'src="{domain}/img/', html_content)
    html_content = re.sub(r'href="(?:\.\./)*(\d+-\d{4}/)', f'href="{domain}/\\1', html_content)
    html_content = re.sub(r'href="/(\d+-\d{4}/)', f'href="{domain}/\\1', html_content)
    html_content = re.sub(r'href="(?:\.\./)*articles/', f'href="{domain}/articles/', html_content)
    html_content = re.sub(r'href="/articles/', f'href="{domain}/articles/', html_content)
    return html_content

articles = []
for entry in sorted(os.listdir(magazine_dir)):
    entry_path = os.path.join(magazine_dir, entry)
    if os.path.isdir(entry_path) and (re.match(r'^\d+-\d{4}$', entry) or entry == "articles"):
        for filename in sorted(os.listdir(entry_path)):
            if filename.endswith(".html") and filename != "article.html":
                filepath = os.path.join(entry_path, filename)
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                title_match = re.search(r'<title>(.*?)</title>', content, re.IGNORECASE | re.DOTALL)
                title = title_match.group(1).strip() if title_match else "New Article"
                title_clean = re.sub(r'\s*\|\s*.*', '', title)
                
                desc_match = re.search(r'<meta\s+name="description"\s+content="([^"]*)"', content, re.IGNORECASE)
                description = desc_match.group(1).strip() if desc_match else ""
                
                author_match = re.search(r'<meta\s+name="author"\s+content="([^"]*)"', content, re.IGNORECASE)
                author = author_match.group(1).strip() if author_match else "Nico Łach"
                
                date_match = re.search(r'<meta\s+name="publish-date"\s+content="([^"]*)"', content, re.IGNORECASE)
                if date_match:
                    date_str = date_match.group(1).strip()
                else:
                    mtime = os.path.getmtime(filepath)
                    date_str = datetime.date.fromtimestamp(mtime).isoformat()
                
                body_match = re.search(r'<section\s+class="[^\"]*article-body[^\"]*">(.*?)</section>', content, re.DOTALL | re.IGNORECASE)
                if not body_match:
                    body_match = re.search(r'<section\s+class="[^\"]*article-container[^\"]*">(.*?)</section>', content, re.DOTALL | re.IGNORECASE)
                
                body_content = body_match.group(1).strip() if body_match else ""
                body_absolute = make_absolute(body_content)
                
                articles.append({
                    "title": title_clean,
                    "link": f"{domain}/{entry}/{filename}",
                    "description": description,
                    "author": author,
                    "date_str": date_str,
                    "pubDate": format_rfc822(date_str),
                    "content": body_absolute
                })

articles.sort(key=lambda x: x["date_str"], reverse=True)

rss_lines = [
    '<?xml version="1.0" encoding="UTF-8"?>',
    '<rss version="2.0"',
    '     xmlns:content="http://purl.org/rss/1.0/modules/content/"',
    '     xmlns:dc="http://purl.org/dc/elements/1.1/">',
    '  <channel>',
    '    <title>The Reverse Emo Changeling</title>',
    f'    <link>{domain}</link>',
    '    <description>Nieregularnik społeczno - artystyczny</description>',
    '    <language>pl</language>'
]

for art in articles:
    rss_lines.extend([
        '    <item>',
        f'      <title>{art["title"]}</title>',
        f'      <link>{art["link"]}</link>',
        f'      <guid isPermaLink="true">{art["link"]}</guid>',
        f'      <pubDate>{art["pubDate"]}</pubDate>',
        f'      <dc:creator><![CDATA[{art["author"]}]]></dc:creator>',
        f'      <description><![CDATA[{art["description"]}]]></description>',
        f'      <content:encoded><![CDATA[{art["content"]}]]></content:encoded>',
        '    </item>'
    ])

rss_lines.extend([
    '  </channel>',
    '</rss>'
])

with open(output_path, 'w', encoding='utf-8') as f:
    f.write('\n'.join(rss_lines))
print(f"-> Generated RSS 2.0 at {output_path}")
EOF

# 5. Nadpisanie commita i ostateczny push z kompletnym plikiem i aktualnym RSS
echo "-> Aktualizacja repozytorium (amend) i finalny push..."
git add "$TARGET_FILE" rss.xml
git commit --amend --no-edit
antigravity push "$TARGET_FILE" </dev/tty >/dev/tty 2>&1
echo "-> Pipeline finished successfully."
