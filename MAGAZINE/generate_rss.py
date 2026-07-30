#!/usr/bin/env python3
# ==========================================================================
# RSS 2.0 FEED GENERATOR FOR THE REVERSE EMO CHANGELING MAGAZINE
# Generates a valid RSS XML compliant with Google Publisher Center.
# ==========================================================================
import os
import re
import datetime
import xml.etree.ElementTree as ET

# Configuration
DOMAIN = "https://reverse.emo-changeling.xyz"
MAGAZINE_DIR = os.path.dirname(os.path.abspath(__file__))
ARTICLES_DIR = os.path.join(MAGAZINE_DIR, "articles")
OUTPUT_PATH = os.path.join(MAGAZINE_DIR, "rss.xml")

def format_rfc822(date_str):
    """
    Converts YYYY-MM-DD to RFC 822 format (e.g. 'Tue, 28 Jul 2026 12:00:00 +0200')
    in a locale-independent manner.
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
        # Fallback to current time if parsing fails
        now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2)))
        return now.strftime("%a, %d %b %Y %H:%M:%S %z")

def make_absolute(html_content):
    """
    Converts relative image/link paths in the article body to absolute URLs.
    """
    # Replace src="../img/xxx" or src="/img/xxx" with DOMAIN/img/xxx
    html_content = re.sub(r'src="(?:\.\./)*img/', f'src="{DOMAIN}/img/', html_content)
    html_content = re.sub(r'src="/img/', f'src="{DOMAIN}/img/', html_content)
    
    # Replace href="../articles/xxx" or href="/articles/xxx" with DOMAIN/articles/xxx
    html_content = re.sub(r'href="(?:\.\./)*articles/', f'href="{DOMAIN}/articles/', html_content)
    html_content = re.sub(r'href="/articles/', f'href="{DOMAIN}/articles/', html_content)
    
    return html_content

def build_rss():
    articles = []
    
    # Scan the articles folder for HTML files
    if os.path.exists(ARTICLES_DIR):
        for filename in os.listdir(ARTICLES_DIR):
            if filename.endswith(".html") and filename != "article.html":
                filepath = os.path.join(ARTICLES_DIR, filename)
                
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Extract Title
                title_match = re.search(r'<title>(.*?)</title>', content, re.IGNORECASE | re.DOTALL)
                title = title_match.group(1).strip() if title_match else "New Article"
                title_clean = re.sub(r'\s*\|\s*.*', '', title) # Remove suffix '| Magazine | ...'
                
                # Extract Description
                desc_match = re.search(r'<meta\s+name="description"\s+content="([^"]*)"', content, re.IGNORECASE)
                description = desc_match.group(1).strip() if desc_match else ""
                
                # Extract Author (from meta or fallback)
                author_match = re.search(r'<meta\s+name="author"\s+content="([^"]*)"', content, re.IGNORECASE)
                author = author_match.group(1).strip() if author_match else "Nico Łach"
                
                # Extract Publish Date (from meta or fallback to file modified date)
                date_match = re.search(r'<meta\s+name="publish-date"\s+content="([^"]*)"', content, re.IGNORECASE)
                if date_match:
                    date_str = date_match.group(1).strip()
                else:
                    mtime = os.path.getmtime(filepath)
                    date_str = datetime.date.fromtimestamp(mtime).isoformat()
                
                # Extract Article Body
                body_match = re.search(r'<section\s+class="[^\"]*article-body[^\"]*">(.*?)</section>', content, re.DOTALL | re.IGNORECASE)
                if not body_match:
                    # Fallback to article-container if class is set directly there
                    body_match = re.search(r'<section\s+class="[^\"]*article-container[^\"]*">(.*?)</section>', content, re.DOTALL | re.IGNORECASE)
                
                body_content = body_match.group(1).strip() if body_match else ""
                body_absolute = make_absolute(body_content)
                
                articles.append({
                    "title": title_clean,
                    "link": f"{DOMAIN}/articles/{filename}",
                    "description": description,
                    "author": author,
                    "date_str": date_str,
                    "pubDate": format_rfc822(date_str),
                    "content": body_absolute
                })

    # Sort articles by date descending
    articles.sort(key=lambda x: x["date_str"], reverse=True)
    
    # Generate RSS XML structure manually to ensure perfect CDATA wrapping and formatting
    rss_lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<rss version="2.0"',
        '     xmlns:content="http://purl.org/rss/1.0/modules/content/"',
        '     xmlns:dc="http://purl.org/dc/elements/1.1/">',
        '  <channel>',
        '    <title>The Reverse Emo Changeling</title>',
        f'    <link>{DOMAIN}</link>',
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
    
    # Write output xml file
    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        f.write('\n'.join(rss_lines))
        
    print(f"-> Successfully generated RSS feed at: {OUTPUT_PATH}")

if __name__ == "__main__":
    build_rss()
