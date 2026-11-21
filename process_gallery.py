import os
import re
import json
import shutil
import subprocess
from datetime import date
from html import escape as html_escape
from pathlib import Path
try:
    from PIL import Image
except ImportError:
    Image = None

# Setup Paths
WORKSPACE_DIR = str(Path(__file__).resolve().parent)
INPUT_DIR = str(Path(__file__).resolve().parent.parent / "temp_gallery" / "GALLERY")
OUTPUT_DIR = os.path.join(WORKSPACE_DIR, "GALLERY")
GRAPHICS_DIR = os.path.join(OUTPUT_DIR, "graphics")

REGISTRY_PATH = os.path.join(OUTPUT_DIR, "processed_folders.json")
SITEMAP_PATH = os.path.join(OUTPUT_DIR, "sitemap.xml")

# Category mapping
CAT_MAP = {
    "inne": "other",
    "art": "digiart",
    "aviary": "aviary",
    "ptaki": "aviary",
    "photo": "photo"
}

def load_registry():
    if os.path.exists(REGISTRY_PATH):
        try:
            with open(REGISTRY_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading registry: {e}")
            return []
    return []

def save_registry(registry):
    try:
        with open(REGISTRY_PATH, 'w', encoding='utf-8', newline='\n') as f:
            json.dump(registry, f, indent=2, ensure_ascii=False)
        gpg_sign_file(REGISTRY_PATH)
    except Exception as e:
        print(f"Error saving registry: {e}")

def get_next_id(category):
    index_path = os.path.join(OUTPUT_DIR, category, "index.html")
    if not os.path.exists(index_path):
        return 1
    
    with open(index_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # If placeholders are present, start at 1 (replacing them)
    if "Gołąb #01: Start" in content or "Gołąb #02: Neon" in content:
        return 1

    items = parse_gallery_data_from_html(content)
    if items:
        all_ids = []
        for item in items:
            if isinstance(item.get("id"), int):
                all_ids.append(item["id"])
            for sub in item.get("images") or []:
                if isinstance(sub.get("id"), int):
                    all_ids.append(sub["id"])
        if all_ids:
            return max(all_ids) + 1
        
    ids = re.findall(r'["\']?\bid["\']?\s*:\s*(\d+)', content)
    if not ids:
        return 1
    return max(map(int, ids)) + 1

def gpg_sign_file(filepath):
    cmd = [
        "gpg", "--compliance=gnupg", "--batch", "--yes", "--detach-sign", "-a",
        "-u", "55B1F5E9342F388E6F06483C34A85D454D1FD3BC",
        filepath
    ]
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        print(f"Signed file: {os.path.basename(filepath)}")
    except subprocess.CalledProcessError as e:
        print(f"Error signing file {filepath}: {e.stderr.decode('utf-8', errors='ignore')}")

def convert_to_webp(src, dest, quality=85):
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with Image.open(src) as img:
        img.save(dest, "WEBP", quality=quality)
    print(f"Converted {os.path.basename(src)} -> {os.path.basename(dest)}")
    gpg_sign_file(dest)

def create_thumbnail_webp(src, dest, max_size=600, quality=80):
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with Image.open(src) as img:
        img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
        img.save(dest, "WEBP", quality=quality, method=6)
    print(f"Created thumbnail {os.path.basename(src)} -> {os.path.basename(dest)}")
    gpg_sign_file(dest)

def clean_description(html_content, target_img_dir_url):
    # Strip Polish comment from Emo shrimp gallery helper
    html_content = re.sub(r'\[Dwie grafiki[\s\S]*?$', '', html_content)
    html_content = html_content.strip()
    
    # Replace relative image sources with absolute paths in the gallery
    def replace_src(match):
        src_val = match.group(2)
        if src_val.startswith('/') or src_val.startswith('http'):
            return match.group(0)
        return f'{match.group(1)}="{target_img_dir_url}/{src_val}"'
        
    html_content = re.sub(r'(src|href)\s*=\s*["\']([^"\']+)["\']', replace_src, html_content)
    
    # Strip borders and border-radius around sketch images in style attributes (for future descriptions)
    def clean_sketch_styles(match):
        img_tag = match.group(0)
        if 'sketch' in img_tag.lower():
            # Remove border/border-radius properties from style attribute
            img_tag = re.sub(r'border\s*:\s*[^;"]+;?', '', img_tag)
            img_tag = re.sub(r'border-radius\s*:\s*[^;"]+;?', '', img_tag)
            # Clean up empty style attributes if any remain
            img_tag = re.sub(r'style\s*=\s*["\']\s*["\']', '', img_tag)
        return img_tag
        
    html_content = re.sub(r'<img[^>]+>', clean_sketch_styles, html_content)

    # Strip inline onclick=switchOpisLang(...) attributes
    html_content = re.sub(
        r'\s+onclick\s*=\s*(?:"[^"]*switchOpisLang\([^)]*\)[^"]*"|\'[^\']*switchOpisLang\([^)]*\)[^\']*\')',
        '',
        html_content,
        flags=re.IGNORECASE
    )
    return html_content

def process_folder(folder_name, next_ids):
    folder_path = os.path.join(INPUT_DIR, folder_name)
    if not os.path.isdir(folder_path):
        return None
        
    # Read galeria.txt
    galeria_txt_path = os.path.join(folder_path, "galeria.txt")
    if not os.path.exists(galeria_txt_path):
        print(f"Skipping {folder_name}: galeria.txt not found")
        return None
        
    with open(galeria_txt_path, 'r', encoding='utf-8') as f:
        raw_cat = f.read().strip()
        
    category = CAT_MAP.get(raw_cat)
    if not category:
        print(f"Skipping {folder_name}: unknown category '{raw_cat}'")
        return None
        
    # Read miniaturka.txt (short description)
    miniaturka_txt_path = os.path.join(folder_path, "miniaturka.txt")
    title = "Graphic"
    if os.path.exists(miniaturka_txt_path):
        with open(miniaturka_txt_path, 'r', encoding='utf-8') as f:
            title = f.read().strip()
            
    # Read opis.html
    opis_html_path = os.path.join(folder_path, "opis.html")
    has_description = False
    description_html = ""
    if os.path.exists(opis_html_path):
        with open(opis_html_path, 'r', encoding='utf-8') as f:
            description_html = f.read().strip()
        if len(description_html) > 5: # not empty/newline only
            has_description = True
            
    # Identify image files
    all_files = os.listdir(folder_path)
    image_jpg = os.path.join(folder_path, "image.jpg")
    
    # PNGs, JPGs (exclude draft sketches and inline images)
    main_files = [
        f for f in all_files 
        if (f.lower().endswith('.png') or f.lower().endswith('.jpg') or f.lower().endswith('.jpeg')) 
        and not f.lower().startswith('sketch') 
        and not f.lower().startswith('img_inline')
    ]
    # TIFs
    tif_files = [f for f in all_files if f.lower().endswith('.tif') or f.lower().endswith('.tiff')]
    
    media_files = main_files + tif_files
    media_count = len(media_files)
    
    print(f"Processing folder: {folder_name} | Category: {category} | Title: {title} | Media Count: {media_count}")
    
    # We will return the item info to be added to the category's galleryData
    item_info = {}
    
    if media_count == 0:
        # CONDITION A: Only image.jpg
        next_id = next_ids[category]
        next_ids[category] += 1
        
        target_dir = os.path.join(GRAPHICS_DIR, category, str(next_id))
        os.makedirs(target_dir, exist_ok=True)
        
        thumb_dest = os.path.join(target_dir, "thumb.webp")
        full_dest = os.path.join(target_dir, "full.webp")
        
        if os.path.exists(image_jpg):
            convert_to_webp(image_jpg, full_dest, quality=85)
            create_thumbnail_webp(image_jpg, thumb_dest, max_size=600, quality=80)
        else:
            print(f"Error: no image.jpg in {folder_name} and no media files.")
            return None
            
        desc_url = None
        if has_description:
            desc_url = f"/graphics/{category}/{next_id}/opis"
            clean_html = clean_description(description_html, f"/graphics/{category}/{next_id}")
            opis_dest = os.path.join(target_dir, "opis.html")
            with open(opis_dest, 'w', encoding='utf-8', newline='\n') as f:
                f.write(clean_html)
            gpg_sign_file(opis_dest)
                
        item_info = {
            "type": "single",
            "category": category,
            "id": next_id,
            "thumb": f"/graphics/{category}/{next_id}/thumb.webp",
            "full": f"/graphics/{category}/{next_id}/full.webp",
            "title": title,
            "descUrl": desc_url
        }
        
    elif media_count == 1:
        # CONDITION B: Exactly one PNG or TIF file
        next_id = next_ids[category]
        next_ids[category] += 1
        
        target_dir = os.path.join(GRAPHICS_DIR, category, str(next_id))
        os.makedirs(target_dir, exist_ok=True)
        
        src_media = os.path.join(folder_path, media_files[0])
        media_ext = os.path.splitext(media_files[0])[1].lower()
        
        thumb_dest = os.path.join(target_dir, "thumb.webp")
        full_dest = os.path.join(target_dir, "full.webp")
        original_dest = os.path.join(target_dir, f"original{media_ext}")
        
        # 1. Generate thumbnail
        if os.path.exists(image_jpg):
            create_thumbnail_webp(image_jpg, thumb_dest, max_size=600, quality=80)
        else:
            create_thumbnail_webp(src_media, thumb_dest, max_size=600, quality=80)
            
        # 2. Generate full (lossy webp 85% compression)
        convert_to_webp(src_media, full_dest, quality=85)
        
        # 3. Copy original file and sign it
        shutil.copy(src_media, original_dest)
        gpg_sign_file(original_dest)
        
        # 4. Copy and sign all other draft/extra files (sketches, inline images)
        for f in all_files:
            f_lower = f.lower()
            if f_lower in ["galeria.txt", "miniaturka.txt", "opis.html", "image.jpg", "image.png"] or f in media_files:
                continue
            if f_lower.startswith("sketch") or f_lower.startswith("img_inline"):
                extra_dest = os.path.join(target_dir, f)
                shutil.copy(os.path.join(folder_path, f), extra_dest)
                gpg_sign_file(extra_dest)
            
        desc_url = None
        if has_description:
            desc_url = f"/graphics/{category}/{next_id}/opis"
            clean_html = clean_description(description_html, f"/graphics/{category}/{next_id}")
            opis_dest = os.path.join(target_dir, "opis.html")
            with open(opis_dest, 'w', encoding='utf-8', newline='\n') as f:
                f.write(clean_html)
            gpg_sign_file(opis_dest)
                
        item_info = {
            "type": "single",
            "category": category,
            "id": next_id,
            "thumb": f"/graphics/{category}/{next_id}/thumb.webp",
            "full": f"/graphics/{category}/{next_id}/full.webp",
            "title": title,
            "descUrl": desc_url,
            "download_tif": f"/graphics/{category}/{next_id}/original{media_ext}"
        }
        
    else:
        # CONDITION C: Multiple PNG/TIF files (Multi-image modal)
        print(f"Creating multi-image item for '{title}' in /{category}/")
        
        subgallery_items = []
        media_files.sort()
        
        for i, media_name in enumerate(media_files):
            sub_id = next_ids[category]
            next_ids[category] += 1
            
            target_dir = os.path.join(GRAPHICS_DIR, category, str(sub_id))
            os.makedirs(target_dir, exist_ok=True)
            
            src_media = os.path.join(folder_path, media_name)
            media_ext = os.path.splitext(media_name)[1].lower()
            
            thumb_dest = os.path.join(target_dir, "thumb.webp")
            full_dest = os.path.join(target_dir, "full.webp")
            original_dest = os.path.join(target_dir, f"original{media_ext}")
            
            # Thumbnail
            if i == 0 and os.path.exists(image_jpg):
                create_thumbnail_webp(image_jpg, thumb_dest, max_size=600, quality=80)
            else:
                create_thumbnail_webp(src_media, thumb_dest, max_size=600, quality=80)
                
            # Full webp lossy 85%
            convert_to_webp(src_media, full_dest, quality=85)
            
            # Original file
            shutil.copy(src_media, original_dest)
            gpg_sign_file(original_dest)
            
            # Copy and sign all other draft/extra files (sketches, inline images)
            for f in all_files:
                f_lower = f.lower()
                if f_lower in ["galeria.txt", "miniaturka.txt", "opis.html", "image.jpg", "image.png"] or f in media_files:
                    continue
                if f_lower.startswith("sketch") or f_lower.startswith("img_inline"):
                    extra_dest = os.path.join(target_dir, f)
                    shutil.copy(os.path.join(folder_path, f), extra_dest)
                    gpg_sign_file(extra_dest)
                
            # Custom title mapping for shrimp_20260624_133609
            if folder_name == "shrimp_20260624_133609":
                if media_name == "image.png":
                    sub_title = "Ronnie Radkie (noise)"
                elif media_name == "ronie-radkie-clear.png":
                    sub_title = "Ronie Radkie no noise"
                else:
                    sub_title = f"{title} ({media_name})"
            else:
                # Variation name
                prefix_match = re.match(r'^([a-zA-Z0-9]+)', media_name)
                prefix = prefix_match.group(1) if prefix_match else ""
                var_name = os.path.splitext(media_name)[0]
                if prefix and var_name.lower().startswith(prefix.lower()):
                    var_name = var_name[len(prefix):].strip()
                sub_title = f"{title} ({var_name})" if var_name else title
            
            desc_url = None
            if has_description:
                desc_url = f"/graphics/{category}/{sub_id}/opis"
                clean_html = clean_description(description_html, f"/graphics/{category}/{sub_id}")
                opis_dest = os.path.join(target_dir, "opis.html")
                with open(opis_dest, 'w', encoding='utf-8', newline='\n') as f:
                    f.write(clean_html)
                gpg_sign_file(opis_dest)
                    
            subgallery_items.append({
                "id": sub_id,
                "thumb": f"/graphics/{category}/{sub_id}/thumb.webp",
                "full": f"/graphics/{category}/{sub_id}/full.webp",
                "title": sub_title,
                "descUrl": desc_url,
                "download_tif": f"/graphics/{category}/{sub_id}/original{media_ext}"
            })
            
        item_info = {
            "type": "multi",
            "category": category,
            "id": subgallery_items[0]["id"],
            "thumb": subgallery_items[0]["thumb"],
            "title": title,
            "descUrl": subgallery_items[0]["descUrl"],
            "images": [
                {
                    "id": item["id"],
                    "full": item["full"],
                    "title": item["title"],
                    "download_tif": item["download_tif"]
                }
                for item in subgallery_items
            ]
        }
        
    return item_info

def _extract_js_field(obj_str, field):
    m = re.search(r'\b' + field + r'\s*:\s*([\'"])((?:\\.|(?!\1).)*)\1', obj_str)
    if m:
        val = m.group(2)
        val = val.replace("\\'", "'").replace('\\"', '"')
        return val
    return None

def _extract_js_id(obj_str):
    m = re.search(r'\bid\s*:\s*([\'"]?)([^\'",\s\}]+)\1', obj_str)
    if m:
        val = m.group(2)
        if val.isdigit() and not m.group(1):
            return int(val)
        return val
    return None

def parse_gallery_data_from_html(html):
    json_m = re.search(r'<script\b[^>]*\bid=["\']gallery-data["\'][^>]*>([\s\S]*?)</script>', html)
    if json_m:
        raw_json = json_m.group(1).strip().replace('\\/', '/')
        try:
            items = json.loads(raw_json)
            if isinstance(items, list):
                for item in items:
                    if isinstance(item, dict):
                        if item.get("images"):
                            item["type"] = "multi"
                        elif item.get("link"):
                            item["type"] = "subgallery"
                        else:
                            item["type"] = "single"
                return items
        except Exception as e:
            print(f"Error parsing #gallery-data JSON: {e}")

    m = re.search(r'const\s+galleryData\s*=\s*\[([\s\S]*?)\];', html)
    if not m:
        return []
    content = m.group(1)
    items = []
    depth = 0
    start_idx = None
    in_str = None
    escape = False
    for idx, ch in enumerate(content):
        if escape:
            escape = False
            continue
        if ch == '\\':
            escape = True
            continue
        if in_str:
            if ch == in_str:
                in_str = None
            continue
        if ch in ('"', "'"):
            in_str = ch
            continue
        if ch == '{':
            if depth == 0:
                start_idx = idx
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0 and start_idx is not None:
                obj_str = content[start_idx:idx+1]
                start_idx = None
                item = {}
                
                images_m = re.search(r'\bimages\s*:\s*\[([\s\S]*?)\]', obj_str)
                top_part = obj_str[:images_m.start()] + obj_str[images_m.end():] if images_m else obj_str
                
                item["id"] = _extract_js_id(top_part)
                item["thumb"] = _extract_js_field(top_part, "thumb")
                item["full"] = _extract_js_field(top_part, "full")
                item["title"] = _extract_js_field(top_part, "title")
                item["descUrl"] = _extract_js_field(top_part, "descUrl")
                item["download_tif"] = _extract_js_field(top_part, "download_tif")
                item["link"] = _extract_js_field(top_part, "link")
                
                if images_m:
                    images_content = images_m.group(1)
                    sub_objs = re.findall(r'\{([\s\S]*?)\}', images_content)
                    imgs = []
                    for sub_str in sub_objs:
                        imgs.append({
                            "id": _extract_js_id(sub_str),
                            "full": _extract_js_field(sub_str, "full"),
                            "title": _extract_js_field(sub_str, "title"),
                            "download_tif": _extract_js_field(sub_str, "download_tif")
                        })
                    item["images"] = imgs
                    item["type"] = "multi"
                elif item.get("link"):
                    item["type"] = "subgallery"
                else:
                    item["type"] = "single"
                items.append(item)
    return items

def render_ssr_cards_html(items):
    lines = []
    for item in items:
        item_id = item.get("id", "")
        raw_title = item.get("title") or ""
        clean_title = re.sub(r'^(?:Gołąb|Pigeon)\s+#\d+:\s*', '', raw_title, flags=re.IGNORECASE)
        alt_esc = html_escape(clean_title, quote=False).replace('"', '&quot;')
        caption_esc = html_escape(clean_title, quote=False)
        thumb_url = item.get("thumb") or ""
        thumb_esc = html_escape(thumb_url, quote=False).replace('"', '&quot;')

        width, height = 300, 300
        if Image is not None and thumb_url:
            thumb_fs_path = os.path.join(OUTPUT_DIR, thumb_url.lstrip('/'))
            if os.path.exists(thumb_fs_path):
                try:
                    with Image.open(thumb_fs_path) as im:
                        width, height = im.size
                except Exception as e:
                    print(f"Error reading dimensions for {thumb_fs_path}: {e}")

        lang_attr = ' lang="ru"' if re.search(r'[\u0400-\u04FF]', clean_title) else ''

        lines.append(f'            <button type="button" class="gallery-card" data-item-id="{item_id}">')
        lines.append('                <div class="gallery-item">')
        lines.append(f'                    <img src="{thumb_esc}" alt="{alt_esc}" width="{width}" height="{height}" loading="lazy" decoding="async">')
        lines.append('                </div>')
        lines.append(f'                <div class="gallery-item-caption"{lang_attr}>{caption_esc}</div>')
        lines.append('            </button>')
    return "\n".join(lines)

def replace_gallery_grid_html(html_text, cards_html):
    open_m = re.search(r'<div\b[^>]*\bid=["\']gallery-grid["\'][^>]*>', html_text)
    if not open_m:
        return html_text
    start_content = open_m.end()
    depth = 1
    for tag_m in re.finditer(r'<(/?)div\b[^>]*>', html_text[start_content:], re.IGNORECASE):
        if tag_m.group(1) == '/':
            depth -= 1
            if depth == 0:
                end_content = start_content + tag_m.start()
                inner = f"\n{cards_html}\n        " if cards_html else "\n        "
                return html_text[:start_content] + inner + html_text[end_content:]
        else:
            depth += 1
    return html_text

def update_category_jsonld(html, items, is_en, category):
    ld_m = re.search(
        r'(<script\s+type=["\']application/ld\+json["\']\s*>)([\s\S]*?)(</script>)',
        html,
        re.IGNORECASE
    )
    if not ld_m:
        return html
    try:
        data = json.loads(ld_m.group(2))
    except Exception as e:
        print(f"Error parsing JSON-LD: {e}")
        return html

    base_url = "https://gallery.emo-changeling.xyz"
    license_page = f"{base_url}/en/#manifest-footer" if is_en else f"{base_url}/#manifest-footer"
    credit_text = "Vikasiek / The Reverse Emo Changeling" if category == "digiart" else "Nico Łach / The Reverse Emo Changeling"

    list_elements = []
    for pos, item in enumerate(items, start=1):
        raw_title = item.get("title") or ""
        clean_name = re.sub(r'^(?:Gołąb|Pigeon)\s+#\d+:\s*', '', raw_title, flags=re.IGNORECASE)
        thumb_path = item.get("thumb") or ""
        if item.get("images"):
            full_path = item["images"][0].get("full") or thumb_path
        else:
            full_path = item.get("full") or item.get("link") or thumb_path

        content_url = full_path if full_path.startswith("http") else f"{base_url}{full_path}"
        thumb_url = thumb_path if thumb_path.startswith("http") else f"{base_url}{thumb_path}"

        list_elements.append({
            "@type": "ListItem",
            "position": pos,
            "item": {
                "@type": "ImageObject",
                "name": clean_name,
                "contentUrl": content_url,
                "thumbnailUrl": thumb_url,
                "creator": {
                    "@type": "Person",
                    "@id": "https://emo-changeling.xyz/#nico",
                    "name": "Nico Łach"
                },
                "copyrightHolder": {
                    "@id": "https://emo-changeling.xyz/#nico"
                },
                "license": "https://creativecommons.org/licenses/by-nd/4.0/",
                "acquireLicensePage": license_page,
                "creditText": credit_text,
                "copyrightNotice": "© Nico Łach"
            }
        })

    target_node = None
    if isinstance(data, dict):
        if isinstance(data.get("@graph"), list):
            for node in data["@graph"]:
                if isinstance(node, dict) and ("mainEntity" in node or "ImageGallery" in (node.get("@type") or [])):
                    target_node = node
                    break
        elif "mainEntity" in data or "ImageGallery" in (data.get("@type") or []):
            target_node = data

    if target_node is not None:
        main_entity = target_node.get("mainEntity")
        if not isinstance(main_entity, dict):
            main_entity = {"@type": "ItemList"}
            target_node["mainEntity"] = main_entity
        main_entity["numberOfItems"] = len(list_elements)
        main_entity["itemListElement"] = list_elements

        if isinstance(data, dict) and isinstance(data.get("@graph"), list):
            is_part_of = target_node.get("isPartOf")
            parent_id = is_part_of.get("@id") if isinstance(is_part_of, dict) else None
            if isinstance(parent_id, str) and parent_id:
                has_parent = any(
                    isinstance(node, dict) and node.get("@id") == parent_id
                    for node in data["@graph"]
                )
                if not has_parent:
                    data["@graph"].append({
                        "@type": ["CollectionPage", "ImageGallery"],
                        "@id": parent_id,
                        "url": parent_id.split("#")[0],
                        "name": "The Reverse Emo Changeling Gallery" if is_en else "Galeria The Reverse Emo Changeling"
                    })

    formatted_json = json.dumps(data, indent=2, ensure_ascii=False)
    indented_json = "\n".join(f"        {line}" for line in formatted_json.splitlines())
    return (
        html[:ld_m.start()]
        + f"{ld_m.group(1)}\n{indented_json}\n    {ld_m.group(3)}"
        + html[ld_m.end():]
    )

def _strip_internal_item_keys(items):
    cleaned = []
    for item in items:
        clean_item = {
            k: v for k, v in item.items()
            if k not in ("category", "type") and v is not None
        }
        cleaned.append(clean_item)
    return cleaned

def update_category_index(category, new_items):
    targets = [
        (os.path.join(OUTPUT_DIR, category, "index.html"), False),
        (os.path.join(OUTPUT_DIR, "en", category, "index.html"), True),
    ]
    migrated_subgallery_dirs = []
    today_compact = date.today().strftime("%Y%m%d")

    for index_path, is_en in targets:
        if not os.path.exists(index_path):
            print(f"Error: {index_path} not found")
            continue

        with open(index_path, 'r', encoding='utf-8') as f:
            html = f.read()

        replace_mockups = "Gołąb #01: Start" in html or "Gołąb #02: Neon" in html

        existing_items = []
        if not replace_mockups:
            parsed_items = parse_gallery_data_from_html(html)
            for item in parsed_items:
                if item.get("link"):
                    slug = item["link"].strip("/")
                    sub_index_path = os.path.join(OUTPUT_DIR, category, slug, "index.html")
                    if os.path.exists(sub_index_path):
                        with open(sub_index_path, 'r', encoding='utf-8') as sf:
                            sub_html = sf.read()
                        sub_items = parse_gallery_data_from_html(sub_html)
                        if sub_items:
                            migrated_item = {
                                "type": "multi",
                                "id": sub_items[0]["id"],
                                "thumb": item["thumb"],
                                "title": item["title"],
                                "descUrl": sub_items[0].get("descUrl"),
                                "images": [
                                    {
                                        "id": s["id"],
                                        "full": s["full"],
                                        "title": s["title"],
                                        "download_tif": s.get("download_tif")
                                    }
                                    for s in sub_items
                                ]
                            }
                            existing_items.append(migrated_item)
                            sub_dir = os.path.join(OUTPUT_DIR, category, slug)
                            if sub_dir not in migrated_subgallery_dirs:
                                migrated_subgallery_dirs.append(sub_dir)
                                print(f"Migrated subgallery {category}/{slug}/ ({len(sub_items)} slides) into parent modal")
                            continue
                existing_items.append(item)

        all_items = existing_items + new_items

        # 1. Update SSR gallery grid cards
        cards_html = render_ssr_cards_html(all_items)
        html = replace_gallery_grid_html(html, cards_html)

        # 2. Update #gallery-data JSON block (without internal category/type keys)
        serializable_items = _strip_internal_item_keys(all_items)
        gallery_json_str = json.dumps(serializable_items, indent=2, ensure_ascii=False)
        html = re.sub(
            r'(<script\b[^>]*\bid=["\']gallery-data["\'][^>]*>)[\s\S]*?(</script>)',
            lambda m: f"{m.group(1)}\n{gallery_json_str}\n    {m.group(2)}",
            html,
            count=1
        )

        # 3. Update JSON-LD ItemList
        html = update_category_jsonld(html, all_items, is_en, category)

        # 4. Update build numbers for style.css?v= and gallery.js?v= when new_items exist
        if new_items:
            html = re.sub(r'data-build="\d+"', f'data-build="{today_compact}"', html)
            html = re.sub(r'style\.css\?v=\d+', f'style.css?v={today_compact}', html)
            html = re.sub(r'gallery\.js\?v=\d+', f'gallery.js?v={today_compact}', html)

        with open(index_path, 'w', encoding='utf-8', newline='\n') as f:
            f.write(html)
        print(f"Updated index HTML file at {index_path}")
        gpg_sign_file(index_path)

    return migrated_subgallery_dirs

def cleanup_old_subgalleries_and_metadata(migrated_dirs=None):
    known_subgalleries = [
        ("aviary", "nokill"),
        ("aviary", "ronnie"),
        ("aviary", "corky"),
        ("digiart", "cindy"),
        ("digiart", "i"),
        ("digiart", "shrimp"),
        ("digiart", "glitchy"),
        ("photo", "ultimate"),
        ("photo", "25072025"),
    ]
    dirs_to_remove = set(migrated_dirs or [])
    for cat, slug in known_subgalleries:
        dirs_to_remove.add(os.path.join(OUTPUT_DIR, cat, slug))
        
    for d in sorted(dirs_to_remove):
        if os.path.exists(d) and os.path.isdir(d):
            shutil.rmtree(d)
            print(f"Removed old subgallery directory: {d}")
            
    today_iso = date.today().strftime("%Y-%m-%d")
    today_slash = date.today().strftime("%Y/%m/%d")
    today_compact = date.today().strftime("%Y%m%d")

    # Update sitemap.xml (preserving xhtml:link tags)
    if os.path.exists(SITEMAP_PATH):
        with open(SITEMAP_PATH, 'r', encoding='utf-8') as f:
            xml = f.read()
        # Remove <url> blocks pointing to subgalleries (two segments after domain)
        xml = re.sub(
            r'\s*<url>\s*<loc>https://gallery\.emo-changeling\.xyz/(?:en/)?(?:aviary|digiart|photo|other)/[^/<]+/</loc>[\s\S]*?</url>',
            '',
            xml
        )
        xml = re.sub(r'<lastmod>.*?</lastmod>', f'<lastmod>{today_iso}</lastmod>', xml)
        with open(SITEMAP_PATH, 'w', encoding='utf-8', newline='\n') as f:
            f.write(xml)
        print("Cleaned up and updated sitemap.xml")
        gpg_sign_file(SITEMAP_PATH)
        
    # Update all 10 index.html files (root PL+EN and 4 category pairs PL+EN)
    html_targets = [
        os.path.join(OUTPUT_DIR, "index.html"),
        os.path.join(OUTPUT_DIR, "en", "index.html"),
        os.path.join(OUTPUT_DIR, "aviary", "index.html"),
        os.path.join(OUTPUT_DIR, "en", "aviary", "index.html"),
        os.path.join(OUTPUT_DIR, "digiart", "index.html"),
        os.path.join(OUTPUT_DIR, "en", "digiart", "index.html"),
        os.path.join(OUTPUT_DIR, "photo", "index.html"),
        os.path.join(OUTPUT_DIR, "en", "photo", "index.html"),
        os.path.join(OUTPUT_DIR, "other", "index.html"),
        os.path.join(OUTPUT_DIR, "en", "other", "index.html"),
    ]
    for hpath in html_targets:
        if os.path.exists(hpath):
            with open(hpath, 'r', encoding='utf-8') as f:
                hcontent = f.read()
            hcontent = re.sub(r'data-build="\d+"', f'data-build="{today_compact}"', hcontent)
            hcontent = re.sub(r'style\.css\?v=\d+', f'style.css?v={today_compact}', hcontent)
            hcontent = re.sub(r'gallery\.js\?v=\d+', f'gallery.js?v={today_compact}', hcontent)
            with open(hpath, 'w', encoding='utf-8', newline='\n') as f:
                f.write(hcontent)
            gpg_sign_file(hpath)
            
    # Update metadata files
    meta_files = [
        os.path.join(OUTPUT_DIR, "llms.txt"),
        os.path.join(OUTPUT_DIR, ".well-known", "llms.txt"),
        os.path.join(OUTPUT_DIR, "humans.txt"),
        os.path.join(OUTPUT_DIR, "ai-catalog.json"),
        os.path.join(OUTPUT_DIR, ".well-known", "ai-catalog.json"),
        os.path.join(OUTPUT_DIR, "ai.json"),
        os.path.join(OUTPUT_DIR, ".well-known", "ai.json"),
        os.path.join(OUTPUT_DIR, ".well-known", "agent.json"),
    ]
    for mpath in meta_files:
        if os.path.exists(mpath):
            with open(mpath, 'r', encoding='utf-8') as f:
                mcontent = f.read()
            mcontent = re.sub(r'20\d{2}-\d{2}-\d{2}', today_iso, mcontent)
            mcontent = re.sub(r'20\d{2}/\d{2}/\d{2}', today_slash, mcontent)
            mcontent = re.sub(r'\b20\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\b', today_compact, mcontent)
            with open(mpath, 'w', encoding='utf-8', newline='\n') as f:
                f.write(mcontent)
            gpg_sign_file(mpath)
            
    # Sign style.css and gallery.js if present
    style_css_path = os.path.join(OUTPUT_DIR, "css", "style.css")
    if os.path.exists(style_css_path):
        gpg_sign_file(style_css_path)
    gallery_js_path = os.path.join(OUTPUT_DIR, "js", "gallery.js")
    if os.path.exists(gallery_js_path):
        gpg_sign_file(gallery_js_path)

def main():
    registry = load_registry()
    print(f"Loaded registry with {len(registry)} already processed folders.")
    
    folders = []
    if os.path.exists(INPUT_DIR):
        folders = [f for f in os.listdir(INPUT_DIR) if f.startswith("shrimp_") and os.path.isdir(os.path.join(INPUT_DIR, f))]
        folders.sort()
    
    processed_this_run = []
    
    category_items = {
        "other": [],
        "digiart": [],
        "aviary": [],
        "photo": []
    }
    
    # Initialize next ID counters to prevent duplication in the same run
    next_ids = {
        "other": get_next_id("other"),
        "digiart": get_next_id("digiart"),
        "aviary": get_next_id("aviary"),
        "photo": get_next_id("photo")
    }
    
    for folder in folders:
        if folder in registry:
            print(f"Folder {folder} is already processed. Skipping.")
            continue
            
        res = process_folder(folder, next_ids)
        if res:
            category = res["category"]
            category_items[category].append(res)
            processed_this_run.append(folder)
                
    # Update all 4 category indexes (migrating any legacy subgalleries and applying slider modal)
    migrated_dirs = []
    for category in ["aviary", "digiart", "photo", "other"]:
        dirs = update_category_index(category, category_items[category])
        if dirs:
            migrated_dirs.extend(dirs)
            
    # Cleanup old subgallery directories and update metadata / signatures only when changes occurred
    if processed_this_run or migrated_dirs:
        cleanup_old_subgalleries_and_metadata(migrated_dirs)
    else:
        style_css_path = os.path.join(OUTPUT_DIR, "css", "style.css")
        if os.path.exists(style_css_path):
            gpg_sign_file(style_css_path)
        gallery_js_path = os.path.join(OUTPUT_DIR, "js", "gallery.js")
        if os.path.exists(gallery_js_path):
            gpg_sign_file(gallery_js_path)
        
    # Save registry
    if processed_this_run:
        save_registry(registry + processed_this_run)
        print(f"Processed {len(processed_this_run)} folders in this run.")
    else:
        print("No new folders to process.")

if __name__ == "__main__":
    main()
