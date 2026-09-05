#!/usr/bin/env python3
# ==============================================================================
# RSS 2.0 FEED GENERATOR FOR THE REVERSE EMO CHANGELING MAGAZINE
# Generates dual-language feeds (PL and EN) fully compliant with
# Google Publisher Center and W3C RSS 2.0 specifications.
# ==============================================================================
import os
import re
import datetime
import html

# Konfiguracja
DOMAIN = "https://reverse.emo-changeling.xyz"
MAGAZINE_DIR = os.path.dirname(os.path.abspath(__file__))
RSS_PL_PATH = os.path.join(MAGAZINE_DIR, "rss-pl.xml")
RSS_EN_PATH = os.path.join(MAGAZINE_DIR, "rss-en.xml")
RSS_DEFAULT_PATH = os.path.join(MAGAZINE_DIR, "rss.xml")

def format_rfc822(date_str):
    """
    Konwertuje YYYY-MM-DD na format RFC 822 (np. 'Thu, 27 Aug 2026 12:00:00 +0200').
    """
    days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    
    try:
        parts = date_str.split('-')
        year = int(parts[0])
        month = int(parts[1])
        day = int(parts[2])
        
        dt = datetime.date(year, month, day)
        weekday = days[dt.weekday()]
        month_name = months[month - 1]
        
        return f"{weekday}, {day:02d} {month_name} {year} 12:00:00 +0200"
    except Exception:
        now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2)))
        return now.strftime("%a, %d %b %Y %H:%M:%S %z")

def make_absolute(html_content, lang="pl"):
    """
    Przekształca ścieżki względne do zasobów i podstron na pełne adresy URL.
    """
    # Obrazy: src="../../img/xxx" lub src="../img/xxx" lub src="img/xxx" -> DOMAIN/img/xxx
    html_content = re.sub(r'src="(?:\.\./)*img/', f'src="{DOMAIN}/img/', html_content)
    html_content = re.sub(r'src="/img/', f'src="{DOMAIN}/img/', html_content)
    
    # Odnośniki do wydań w danym języku
    html_content = re.sub(r'href="(?:\.\./)*(\d+-\d{4}/)', f'href="{DOMAIN}/{lang}/\\1', html_content)
    html_content = re.sub(r'href="/(\d+-\d{4}/)', f'href="{DOMAIN}/{lang}/\\1', html_content)
    
    return html_content

def extract_articles_for_lang(lang):
    """
    Skanuje katalog /pl/ lub /en/ i wyodrębnia artykuły.
    """
    lang_dir = os.path.join(MAGAZINE_DIR, lang)
    if not os.path.exists(lang_dir):
        return []

    articles = []
    issues = sorted([d for d in os.listdir(lang_dir) if re.match(r'^\d+-\d{4}$', d)], key=lambda x: int(x.split('-')[0]))
    
    for entry in issues:
        entry_path = os.path.join(lang_dir, entry)
        for filename in sorted(os.listdir(entry_path)):
            if filename.endswith(".html"):
                filepath = os.path.join(entry_path, filename)
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Data publikacji
                date_match = re.search(r'<meta\s+name="publish-date"\s+content="([^"]*)"', content, re.IGNORECASE)
                if date_match:
                    date_str = date_match.group(1).strip()
                else:
                    mtime = os.path.getmtime(filepath)
                    date_str = datetime.date.fromtimestamp(mtime).isoformat()
                
                pub_date_rfc = format_rfc822(date_str)
                article_link = f"{DOMAIN}/{lang}/{entry}/{filename}"
                
                # Tytuł
                t_m = re.search(r'<h1\s+class="article-title">(.*?)</h1>', content, re.DOTALL)
                title = html.unescape(re.sub(r'<[^>]+>', '', t_m.group(1))).strip() if t_m else ("Artykuł" if lang == "pl" else "Article")
                
                # Autor
                a_m = re.search(r'<strong>(?:Autor|Author):</strong>\s*(?:<[^>]+>)*([^<]+)(?:<[^>]+>)*</span>', content)
                author = a_m.group(1).strip() if a_m else "Zebroid"
                
                # Treść
                b_m = re.search(r'<section\s+class="article-body[^\"]*"[^>]*>(.*?)</section>', content, re.DOTALL)
                body = b_m.group(1).strip() if b_m else ""
                body_abs = make_absolute(body, lang)
                
                # Lead
                desc_m = re.search(r'<meta\s+name="description"\s+content="([^"]*)"', content, re.IGNORECASE)
                if desc_m:
                    lead = desc_m.group(1).strip()
                else:
                    p_m = re.search(r'<p>(.*?)</p>', body, re.DOTALL)
                    lead = html.unescape(re.sub(r'<[^>]+>', '', p_m.group(1))).strip() if p_m else ""
                    if len(lead) > 280:
                        cutoff = lead[:280]
                        last_dot = cutoff.rfind(".")
                        if last_dot > 120:
                            lead = cutoff[:last_dot+1]
                        else:
                            lead = cutoff.rsplit(" ", 1)[0] + "..."
                
                articles.append({
                    "title": title,
                    "link": article_link,
                    "guid": article_link,
                    "pubDate": pub_date_rfc,
                    "author": author,
                    "description": lead,
                    "content": body_abs,
                    "date_str": date_str
                })

    articles.sort(key=lambda x: x["date_str"], reverse=True)
    return articles

def generate_feed_xml(articles, lang_code, channel_title, channel_desc, self_feed_filename):
    """
    Buduje poprawny dokument RSS 2.0 z modułami content oraz dc,
    zgodny z wymogami Google Publisher Center.
    """
    self_url = f"{DOMAIN}/{self_feed_filename}"
    last_build_date = articles[0]["pubDate"] if articles else format_rfc822("2026-08-27")
    channel_link = f"{DOMAIN}/{lang_code}/" if lang_code in ["pl", "en"] else DOMAIN
    
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<rss version="2.0"',
        '     xmlns:content="http://purl.org/rss/1.0/modules/content/"',
        '     xmlns:dc="http://purl.org/dc/elements/1.1/"',
        '     xmlns:atom="http://www.w3.org/2005/Atom">',
        '  <channel>',
        f'    <title>{channel_title}</title>',
        f'    <link>{channel_link}</link>',
        f'    <description>{channel_desc}</description>',
        f'    <language>{lang_code}</language>',
        f'    <lastBuildDate>{last_build_date}</lastBuildDate>',
        f'    <atom:link href="{self_url}" rel="self" type="application/rss+xml"/>'
    ]
    
    for art in articles:
        lines.extend([
            '    <item>',
            f'      <title><![CDATA[{art["title"]}]]></title>',
            f'      <link>{art["link"]}</link>',
            f'      <guid isPermaLink="true">{art["guid"]}</guid>',
            f'      <pubDate>{art["pubDate"]}</pubDate>',
            f'      <dc:creator><![CDATA[{art["author"]}]]></dc:creator>',
            f'      <description><![CDATA[{art["description"]}]]></description>',
            f'      <content:encoded><![CDATA[{art["content"]}]]></content:encoded>',
            '    </item>'
        ])
        
    lines.extend([
        '  </channel>',
        '</rss>'
    ])
    
    return '\n'.join(lines) + '\n'

def main():
    print("-> Skanowanie artykułów magazynu w /pl/ oraz /en/...")
    articles_pl = extract_articles_for_lang("pl")
    articles_en = extract_articles_for_lang("en")
    print(f"-> Znaleziono artykułów: {len(articles_pl)} (PL), {len(articles_en)} (EN)")
    
    # 1. Generowanie feedu PL (rss-pl.xml)
    xml_pl = generate_feed_xml(
        articles=articles_pl,
        lang_code="pl",
        channel_title="The Reverse Emo Changeling (PL)",
        channel_desc="Niezależny nieregularnik społeczno - artystyczny. E-zin undergroundowej kultury i alternatywnego dziennikarstwa.",
        self_feed_filename="rss-pl.xml"
    )
    with open(RSS_PL_PATH, 'w', encoding='utf-8', newline='\n') as f:
        f.write(xml_pl)
    print(f"-> Zapisano poprawny feed PL: {RSS_PL_PATH}")
    
    # 2. Generowanie feedu EN (rss-en.xml)
    xml_en = generate_feed_xml(
        articles=articles_en,
        lang_code="en",
        channel_title="The Reverse Emo Changeling (EN)",
        channel_desc="Independent socio-artistic periodical. Underground counterculture and alternative journalism e-zine.",
        self_feed_filename="rss-en.xml"
    )
    with open(RSS_EN_PATH, 'w', encoding='utf-8', newline='\n') as f:
        f.write(xml_en)
    print(f"-> Zapisano poprawny feed EN: {RSS_EN_PATH}")
    
    # 3. Kopia/Domyślny ogólny feed (rss.xml) wskazujący na PL z własnym atom:link
    xml_default = generate_feed_xml(
        articles=articles_pl,
        lang_code="pl",
        channel_title="The Reverse Emo Changeling",
        channel_desc="Niezależne czasopismo społeczno-artystyczne w estetyce Modern MySpace.",
        self_feed_filename="rss.xml"
    )
    with open(RSS_DEFAULT_PATH, 'w', encoding='utf-8', newline='\n') as f:
        f.write(xml_default)
    print(f"-> Zaktualizowano domyślny feed: {RSS_DEFAULT_PATH}")

if __name__ == "__main__":
    main()
