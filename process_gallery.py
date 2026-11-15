import os
import re
import json
import shutil
import subprocess
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
        with open(REGISTRY_PATH, 'w', encoding='utf-8') as f:
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
        
    ids = re.findall(r'id:\s*(\d+)', content)
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
            convert_to_webp(image_jpg, thumb_dest)
            shutil.copy(thumb_dest, full_dest)
            gpg_sign_file(full_dest)
        else:
            print(f"Error: no image.jpg in {folder_name} and no media files.")
            return None
            
        desc_url = None
        if has_description:
            desc_url = f"/graphics/{category}/{next_id}/opis.html"
            clean_html = clean_description(description_html, f"/graphics/{category}/{next_id}")
            opis_dest = os.path.join(target_dir, "opis.html")
            with open(opis_dest, 'w', encoding='utf-8') as f:
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
            convert_to_webp(image_jpg, thumb_dest)
        else:
            convert_to_webp(src_media, thumb_dest)
            
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
            desc_url = f"/graphics/{category}/{next_id}/opis.html"
            clean_html = clean_description(description_html, f"/graphics/{category}/{next_id}")
            opis_dest = os.path.join(target_dir, "opis.html")
            with open(opis_dest, 'w', encoding='utf-8') as f:
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
                convert_to_webp(image_jpg, thumb_dest)
            else:
                convert_to_webp(src_media, thumb_dest)
                
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
                desc_url = f"/graphics/{category}/{sub_id}/opis.html"
                clean_html = clean_description(description_html, f"/graphics/{category}/{sub_id}")
                opis_dest = os.path.join(target_dir, "opis.html")
                with open(opis_dest, 'w', encoding='utf-8') as f:
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

def format_gallery_data_js(items):
    js_items = []
    for item in items:
        if item.get("type") == "multi" or item.get("images"):
            lines = [
                f"                id: {item['id']}",
                f"                thumb: {repr(item['thumb'])}",
                f"                title: {repr(item['title'])}"
            ]
            if item.get("descUrl"):
                lines.append(f"                descUrl: {repr(item['descUrl'])}")
            img_lines = []
            for img in item.get("images", []):
                sub_fields = [
                    f"id: {img['id']}",
                    f"full: {repr(img['full'])}",
                    f"title: {repr(img['title'])}"
                ]
                if img.get("download_tif"):
                    sub_fields.append(f"download_tif: {repr(img['download_tif'])}")
                img_lines.append("                    { " + ", ".join(sub_fields) + " }")
            images_block = "                images: [\n" + ",\n".join(img_lines) + "\n                ]"
            lines.append(images_block)
            js_items.append("            {\n" + ",\n".join(lines) + "\n            }")
        else:
            lines = [
                f"                id: {item['id']}",
                f"                thumb: {repr(item['thumb'])}",
                f"                full: {repr(item['full'])}",
                f"                title: {repr(item['title'])}"
            ]
            if item.get("descUrl"):
                lines.append(f"                descUrl: {repr(item['descUrl'])}")
            if item.get("download_tif"):
                lines.append(f"                download_tif: {repr(item['download_tif'])}")
            js_items.append("            {\n" + ",\n".join(lines) + "\n            }")
    return "const galleryData = [\n" + ",\n".join(js_items) + "\n        ];"

def build_modal_and_script_html(category, gallery_data_js_str):
    modal_container_html = """            <div class="modal-image-container" id="modal-image-container">
                <div class="modal-slide-title" id="modal-slide-title"></div>
                <div class="modal-slider-row" id="modal-slider-row">
                    <button type="button" class="tape-nav-btn tape-prev is-hidden" id="modal-prev-btn" aria-label="Poprzednia grafika">
                        <svg viewBox="0 0 36 24" width="28" height="18" aria-hidden="true">
                            <polygon points="18,3 4,12 18,21" fill="currentColor"></polygon>
                            <polygon points="32,3 18,12 32,21" fill="currentColor"></polygon>
                        </svg>
                    </button>
                    <div class="modal-slider-viewport" id="modal-slider-viewport">
                        <div class="modal-slider-track" id="modal-slider-track">
                            <div class="modal-slide"><img src="" alt="Pełny podgląd" class="modal-image" id="modal-image" draggable="false"></div>
                        </div>
                    </div>
                    <div class="modal-bottom-controls" id="modal-bottom-controls">
                        <button type="button" class="tape-nav-btn modal-zoom-btn" id="modal-zoom-btn" aria-label="Powiększ grafikę" title="Zoom">
                            <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                                <circle cx="11" cy="11" r="7"></circle>
                                <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
                                <line x1="11" y1="8" x2="11" y2="14"></line>
                                <line x1="8" y1="11" x2="14" y2="11"></line>
                            </svg>
                        </button>
                        <div class="modal-slide-counter is-hidden" id="modal-slide-counter" aria-live="polite">[ 1 / 1 ]</div>
                    </div>
                    <button type="button" class="tape-nav-btn tape-next is-hidden" id="modal-next-btn" aria-label="Następna grafika">
                        <svg viewBox="0 0 36 24" width="28" height="18" aria-hidden="true">
                            <polygon points="4,3 18,12 4,21" fill="currentColor"></polygon>
                            <polygon points="18,3 32,12 18,21" fill="currentColor"></polygon>
                        </svg>
                    </button>
                </div>
            </div>"""

    zoom_overlay_html = """    <!-- ZOOM_OVERLAY_START -->
    <div class="zoom-overlay" id="zoom-overlay" role="dialog" aria-modal="true" aria-label="Powiększony podgląd grafiki"><div class="zoom-badge" id="zoom-badge"><button type="button" class="zoom-scale-btn" id="zoom-scale-reset" title="Reset 1.0x">1.0x</button><span class="zoom-badge-sep">|</span><button type="button" class="zoom-exit-btn" id="zoom-exit-btn" aria-label="Wyjdź z trybu zoom"><span class="content-pl">✕ WYJDŹ</span><span class="content-en">✕ EXIT</span></button></div><div class="zoom-stage" id="zoom-stage"><img src="" alt="" class="zoom-image" id="zoom-image" draggable="false"></div></div>
    <!-- ZOOM_OVERLAY_END -->"""

    cat_label = category.capitalize()
    script_html = f"""    <script>
        {gallery_data_js_str}

        const grid = document.getElementById('gallery-grid');
        const modal = document.getElementById('gallery-modal');
        const descContent = document.getElementById('description-content');
        const modalDetails = document.getElementById('modal-details');
        const downloadBtn = document.getElementById('modal-download-btn');
        const rotateBtn = document.getElementById('modal-rotate-btn');
        const modalContent = document.querySelector('.modal-content');
        const slideTitleEl = document.getElementById('modal-slide-title');
        const sliderViewport = document.getElementById('modal-slider-viewport');
        const sliderTrack = document.getElementById('modal-slider-track');
        const prevBtn = document.getElementById('modal-prev-btn');
        const nextBtn = document.getElementById('modal-next-btn');
        const slideCounter = document.getElementById('modal-slide-counter');
        const zoomBtn = document.getElementById('modal-zoom-btn');
        const zoomOverlay = document.getElementById('zoom-overlay');
        const zoomStage = document.getElementById('zoom-stage');
        const zoomImg = document.getElementById('zoom-image');
        const zoomScaleResetBtn = document.getElementById('zoom-scale-reset');
        const zoomExitBtn = document.getElementById('zoom-exit-btn');

        const MIN_ZOOM = 1.0;
        const MAX_ZOOM = 6.0;

        let currentSlides = [];
        let currentSlideIndex = 0;
        let isDragging = false;
        let dragStartX = 0;
        let dragDeltaX = 0;
        let didDragMove = false;
        let lastTouchTimestamp = 0;

        let zoomScale = 1.0;
        let zoomPanX = 0;
        let zoomPanY = 0;
        let isZoomPanning = false;
        let zoomPanStartX = 0;
        let zoomPanStartY = 0;
        let zoomPanOriginX = 0;
        let zoomPanOriginY = 0;
        let didZoomPanMove = false;
        let pinchStartDist = 0;
        let pinchStartScale = 1.0;
        let lastTapTimestamp = 0;

        // Helper to check and convert HEIC images
        async function checkAndConvertHeic(imgElement) {{
            const src = imgElement.getAttribute('src');
            if (src && (src.toLowerCase().endsWith('.heic') || src.toLowerCase().endsWith('.heif'))) {{
                try {{
                    if (imgElement.dataset.heicConverted) {{
                        imgElement.src = imgElement.dataset.heicConverted;
                        return;
                    }}
                    imgElement.style.opacity = '0.5';
                    const response = await fetch(src);
                    if (!response.ok) throw new Error('Failed to fetch HEIC image');
                    const blob = await response.blob();
                    if (typeof heic2any !== 'undefined') {{
                        const convertedBlob = await heic2any({{
                            blob: blob,
                            toType: 'image/jpeg',
                            quality: 0.8
                        }});
                        const blobUrl = URL.createObjectURL(convertedBlob);
                        imgElement.src = blobUrl;
                        imgElement.dataset.heicConverted = blobUrl;
                    }} else {{
                        console.error('heic2any library is not loaded');
                    }}
                }} catch (e) {{
                    console.error('Error converting HEIC image:', e);
                }} finally {{
                    imgElement.style.opacity = '1';
                }}
            }}
        }}

        // Renderowanie miniatur
        galleryData.forEach(item => {{
            const cardDiv = document.createElement('div');
            cardDiv.className = 'gallery-card';

            // Czyszczenie nazwy z prefiksu np. "Gołąb #01: "
            const cleanTitle = item.title.replace(/^Gołąb\\s+#\\d+:\\s*/i, '');
            const isCyrillic = /[\\u0400-\\u04FF]/.test(cleanTitle);

            cardDiv.innerHTML = `
                <div class="gallery-item">
                    <img src="${{item.thumb}}" alt="${{cleanTitle}}" loading="lazy">
                </div>
                <div class="gallery-item-caption"${{isCyrillic ? ' lang="ru"' : ''}}>${{cleanTitle}}</div>
            `;

            const imgEl = cardDiv.querySelector('img');
            checkAndConvertHeic(imgEl);

            cardDiv.addEventListener('click', () => {{
                openModal(item);
            }});
            grid.appendChild(cardDiv);
        }});

        // Synchronizacja języka galerii z preferencją użytkownika
        function syncGalleryLanguage() {{
            try {{
                var s = null;
                var m = document.cookie.match(/(?:^|;\\s*)site_lang=([^;]+)/);
                if (m && m[1]) {{ s = m[1].toLowerCase(); }}
                else if (window.localStorage) {{ s = (localStorage.getItem('site_lang') || '').toLowerCase(); }}
                if (!s) {{
                    var l = (navigator.languages && navigator.languages[0]) || navigator.language || '';
                    s = l.toLowerCase().startsWith('pl') ? 'pl' : 'en';
                }}
                document.documentElement.lang = s === 'pl' ? 'pl' : 'en';
            }} catch(e) {{}}
        }}
        syncGalleryLanguage();

        // Lokalny przełącznik języka opisu grafiki (bez modyfikacji ciasteczek i preferencji serwisu)
        function switchOpisLang(lang, event) {{
            if (event && event.stopPropagation) event.stopPropagation();
            var dc = document.getElementById('description-content');
            if (!dc) return;
            dc.setAttribute('data-active-lang', lang);
            var btns = dc.querySelectorAll('.lang-btn, .opis-lang-btn');
            btns.forEach(function(b) {{
                if (b.getAttribute('data-lang') === lang) {{
                    b.classList.add('active');
                    b.setAttribute('aria-current', 'true');
                }} else {{
                    b.classList.remove('active');
                    b.removeAttribute('aria-current');
                }}
            }});
        }}
        window.switchOpisLang = switchOpisLang;

        function updateDownloadButton(slide) {{
            if (slide && slide.download_tif) {{
                downloadBtn.href = slide.download_tif;
                downloadBtn.setAttribute('data-asc', slide.download_tif + '.asc');
                downloadBtn.style.display = 'inline-block';
                const lower = slide.download_tif.toLowerCase();
                if (lower.endsWith('.png')) {{
                    downloadBtn.textContent = 'DOWNLOAD MAX QUALITY (.PNG)';
                }} else if (lower.endsWith('.jpg') || lower.endsWith('.jpeg')) {{
                    downloadBtn.textContent = 'DOWNLOAD MAX QUALITY (.JPG)';
                }} else {{
                    downloadBtn.textContent = 'DOWNLOAD MAX QUALITY (.TIF)';
                }}
            }} else {{
                downloadBtn.style.display = 'none';
            }}
        }}

        function updateSlide(newIndex) {{
            if (!currentSlides.length) return;
            currentSlideIndex = Math.max(0, Math.min(currentSlides.length - 1, newIndex));
            sliderTrack.style.transition = '';
            sliderTrack.style.transform = `translateX(-${{currentSlideIndex * 100}}%)`;

            const activeSlide = currentSlides[currentSlideIndex];
            if (slideTitleEl) {{
                slideTitleEl.textContent = (activeSlide.title || '').replace(/^Gołąb\\s+#\\d+:\\s*/i, '');
            }}

            updateDownloadButton(activeSlide);

            if (currentSlides.length > 1) {{
                const isAtStart = (currentSlideIndex === 0);
                const isAtEnd = (currentSlideIndex === currentSlides.length - 1);
                prevBtn.classList.remove('is-hidden');
                nextBtn.classList.remove('is-hidden');
                slideCounter.classList.remove('is-hidden');
                prevBtn.classList.toggle('is-disabled', isAtStart);
                nextBtn.classList.toggle('is-disabled', isAtEnd);
                prevBtn.setAttribute('aria-disabled', String(isAtStart));
                nextBtn.setAttribute('aria-disabled', String(isAtEnd));
                slideCounter.textContent = `[ ${{currentSlideIndex + 1}} / ${{currentSlides.length}} ]`;
                sliderViewport.classList.add('is-draggable');
            }} else {{
                prevBtn.classList.add('is-hidden');
                nextBtn.classList.add('is-hidden');
                slideCounter.classList.add('is-hidden');
                sliderViewport.classList.remove('is-draggable');
            }}
        }}

        prevBtn.addEventListener('click', (e) => {{
            e.preventDefault();
            e.stopPropagation();
            if (currentSlideIndex > 0) {{
                updateSlide(currentSlideIndex - 1);
            }}
        }});

        nextBtn.addEventListener('click', (e) => {{
            e.preventDefault();
            e.stopPropagation();
            if (currentSlideIndex < currentSlides.length - 1) {{
                updateSlide(currentSlideIndex + 1);
            }}
        }});

        // Obsługa przeciągania myszką i dotykiem na #modal-slider-viewport
        sliderViewport.addEventListener('mousedown', (e) => {{
            if (currentSlides.length <= 1) return;
            isDragging = true;
            didDragMove = false;
            dragStartX = e.clientX;
            dragDeltaX = 0;
            sliderViewport.classList.add('is-dragging');
            sliderTrack.style.transition = 'none';
            e.preventDefault();
        }});

        window.addEventListener('mousemove', (e) => {{
            if (!isDragging) return;
            dragDeltaX = e.clientX - dragStartX;
            if (Math.abs(dragDeltaX) > 5) {{
                didDragMove = true;
            }}
            sliderTrack.style.transform = `translateX(calc(-${{currentSlideIndex * 100}}% + ${{dragDeltaX}}px))`;
        }});

        function finishDrag() {{
            if (!isDragging) return;
            isDragging = false;
            sliderViewport.classList.remove('is-dragging');
            sliderTrack.style.transition = '';
            if (dragDeltaX < -40 && currentSlideIndex < currentSlides.length - 1) {{
                updateSlide(currentSlideIndex + 1);
            }} else if (dragDeltaX > 40 && currentSlideIndex > 0) {{
                updateSlide(currentSlideIndex - 1);
            }} else {{
                updateSlide(currentSlideIndex);
            }}
            dragDeltaX = 0;
            setTimeout(() => {{ didDragMove = false; }}, 50);
        }}

        window.addEventListener('mouseup', finishDrag);
        sliderViewport.addEventListener('mouseleave', finishDrag);

        sliderViewport.addEventListener('touchstart', (e) => {{
            lastTouchTimestamp = Date.now();
            if (currentSlides.length > 1 && e.touches.length === 1) {{
                isDragging = true;
                didDragMove = false;
                dragStartX = e.touches[0].clientX;
                dragDeltaX = 0;
                sliderTrack.style.transition = 'none';
            }}
        }}, {{ passive: true }});

        sliderViewport.addEventListener('touchmove', (e) => {{
            if (!isDragging || !e.touches.length) return;
            dragDeltaX = e.touches[0].clientX - dragStartX;
            if (Math.abs(dragDeltaX) > 5) {{
                didDragMove = true;
            }}
            sliderTrack.style.transform = `translateX(calc(-${{currentSlideIndex * 100}}% + ${{dragDeltaX}}px))`;
        }}, {{ passive: true }});

        sliderViewport.addEventListener('touchend', finishDrag);

        sliderViewport.addEventListener('click', (e) => {{
            if (didDragMove) return;
            if (!e.target.classList.contains('modal-image')) return;
            if (window.innerWidth > 768 && (Date.now() - lastTouchTimestamp > 600)) {{
                openZoomOverlay();
            }}
        }});

        if (zoomBtn) {{
            zoomBtn.addEventListener('click', (e) => {{
                e.preventDefault();
                e.stopPropagation();
                openZoomOverlay();
            }});
        }}

        function clampZoomPan() {{
            if (!zoomStage || !zoomImg) return;
            const stageRect = zoomStage.getBoundingClientRect();
            const scaledW = zoomImg.offsetWidth * zoomScale;
            const scaledH = zoomImg.offsetHeight * zoomScale;
            const maxPanX = Math.max(0, (scaledW - stageRect.width) / 2);
            const maxPanY = Math.max(0, (scaledH - stageRect.height) / 2);
            zoomPanX = Math.max(-maxPanX, Math.min(maxPanX, zoomPanX));
            zoomPanY = Math.max(-maxPanY, Math.min(maxPanY, zoomPanY));
        }}

        function applyZoomTransform() {{
            if (!zoomImg || !zoomOverlay) return;
            zoomImg.style.transform = `translate(${{zoomPanX}}px, ${{zoomPanY}}px) scale(${{zoomScale}})`;
            if (zoomScaleResetBtn) {{
                zoomScaleResetBtn.textContent = `${{zoomScale.toFixed(1)}}x`;
            }}
            if (zoomStage) zoomStage.classList.toggle('is-zoomed', zoomScale > 1.01);
        }}

        function zoomAtPoint(newScale, clientX, clientY) {{
            const clampedScale = Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, newScale));
            if (clampedScale === zoomScale) return;
            if (clampedScale <= 1.001) {{
                zoomScale = 1.0;
                zoomPanX = 0;
                zoomPanY = 0;
                applyZoomTransform();
                return;
            }}
            const stageRect = zoomStage.getBoundingClientRect();
            const cx = clientX - (stageRect.left + stageRect.width / 2);
            const cy = clientY - (stageRect.top + stageRect.height / 2);
            const ratio = clampedScale / zoomScale;
            zoomPanX = cx - (cx - zoomPanX) * ratio;
            zoomPanY = cy - (cy - zoomPanY) * ratio;
            zoomScale = clampedScale;
            clampZoomPan();
            applyZoomTransform();
        }}

        function openZoomOverlay() {{
            if (!zoomOverlay || !zoomImg || !currentSlides.length) return;
            const activeSlide = currentSlides[currentSlideIndex];
            if (!activeSlide || !activeSlide.full) return;
            const activeImgEl = sliderTrack.querySelectorAll('img')[currentSlideIndex];
            zoomImg.src = (activeImgEl && activeImgEl.dataset.heicConverted) ? activeImgEl.dataset.heicConverted : activeSlide.full;
            zoomImg.alt = activeSlide.title || '';
            zoomScale = 1.0;
            zoomPanX = 0;
            zoomPanY = 0;
            if (zoomStage) {{
                zoomStage.scrollTop = 0;
                zoomStage.scrollLeft = 0;
                zoomStage.classList.remove('is-panning', 'is-zoomed');
            }}
            zoomImg.style.transform = '';
            applyZoomTransform();
            zoomOverlay.classList.add('active');
        }}

        function closeZoomOverlay() {{
            if (!zoomOverlay) return;
            zoomOverlay.classList.remove('active');
            zoomScale = 1.0;
            zoomPanX = 0;
            zoomPanY = 0;
            isZoomPanning = false;
            if (zoomStage) zoomStage.classList.remove('is-panning', 'is-zoomed');
            if (zoomImg) {{
                zoomImg.style.transform = '';
                zoomImg.src = '';
            }}
        }}

        if (zoomStage) {{
            zoomStage.addEventListener('wheel', (e) => {{
                e.preventDefault();
                const factor = e.deltaY < 0 ? 1.18 : (1 / 1.18);
                zoomAtPoint(zoomScale * factor, e.clientX, e.clientY);
            }}, {{ passive: false }});

            zoomStage.addEventListener('mousedown', (e) => {{
                if (e.button !== 0 || zoomScale <= 1.01) return;
                isZoomPanning = true;
                didZoomPanMove = false;
                zoomPanStartX = e.clientX;
                zoomPanStartY = e.clientY;
                zoomPanOriginX = zoomPanX;
                zoomPanOriginY = zoomPanY;
                zoomStage.classList.add('is-panning');
                e.preventDefault();
            }});

            window.addEventListener('mousemove', (e) => {{
                if (!isZoomPanning) return;
                const dx = e.clientX - zoomPanStartX;
                const dy = e.clientY - zoomPanStartY;
                if (Math.abs(dx) > 4 || Math.abs(dy) > 4) didZoomPanMove = true;
                zoomPanX = zoomPanOriginX + dx;
                zoomPanY = zoomPanOriginY + dy;
                clampZoomPan();
                applyZoomTransform();
            }});

            window.addEventListener('mouseup', () => {{
                if (!isZoomPanning) return;
                isZoomPanning = false;
                zoomStage.classList.remove('is-panning');
                setTimeout(() => {{ didZoomPanMove = false; }}, 50);
            }});

            zoomStage.addEventListener('dblclick', (e) => {{
                e.preventDefault();
                if (zoomScale > 1.05) {{
                    zoomAtPoint(1.0, e.clientX, e.clientY);
                }} else {{
                    zoomAtPoint(2.5, e.clientX, e.clientY);
                }}
            }});

            zoomStage.addEventListener('click', (e) => {{
                if (didZoomPanMove) return;
                if (zoomScale <= 1.01 && e.target === zoomStage) {{
                    closeZoomOverlay();
                }}
            }});

            zoomStage.addEventListener('touchstart', (e) => {{
                if (e.touches.length === 2) {{
                    e.preventDefault();
                    isZoomPanning = false;
                    const dx = e.touches[0].clientX - e.touches[1].clientX;
                    const dy = e.touches[0].clientY - e.touches[1].clientY;
                    pinchStartDist = Math.hypot(dx, dy);
                    pinchStartScale = zoomScale;
                }} else if (e.touches.length === 1) {{
                    const now = Date.now();
                    if (now - lastTapTimestamp < 300) {{
                        e.preventDefault();
                        const t = e.touches[0];
                        if (zoomScale > 1.05) {{
                            zoomAtPoint(1.0, t.clientX, t.clientY);
                        }} else {{
                            zoomAtPoint(2.5, t.clientX, t.clientY);
                        }}
                        lastTapTimestamp = 0;
                        return;
                    }}
                    lastTapTimestamp = now;
                    if (zoomScale > 1.01) {{
                        isZoomPanning = true;
                        didZoomPanMove = false;
                        zoomPanStartX = e.touches[0].clientX;
                        zoomPanStartY = e.touches[0].clientY;
                        zoomPanOriginX = zoomPanX;
                        zoomPanOriginY = zoomPanY;
                    }}
                }}
            }}, {{ passive: false }});

            zoomStage.addEventListener('touchmove', (e) => {{
                if (e.touches.length === 2 && pinchStartDist > 0) {{
                    e.preventDefault();
                    const dx = e.touches[0].clientX - e.touches[1].clientX;
                    const dy = e.touches[0].clientY - e.touches[1].clientY;
                    const dist = Math.hypot(dx, dy);
                    const midX = (e.touches[0].clientX + e.touches[1].clientX) / 2;
                    const midY = (e.touches[0].clientY + e.touches[1].clientY) / 2;
                    zoomAtPoint(pinchStartScale * (dist / pinchStartDist), midX, midY);
                }} else if (e.touches.length === 1 && isZoomPanning) {{
                    e.preventDefault();
                    const dx = e.touches[0].clientX - zoomPanStartX;
                    const dy = e.touches[0].clientY - zoomPanStartY;
                    if (Math.abs(dx) > 4 || Math.abs(dy) > 4) didZoomPanMove = true;
                    zoomPanX = zoomPanOriginX + dx;
                    zoomPanY = zoomPanOriginY + dy;
                    clampZoomPan();
                    applyZoomTransform();
                }}
            }}, {{ passive: false }});

            zoomStage.addEventListener('touchend', (e) => {{
                if (e.touches.length < 2) pinchStartDist = 0;
                if (e.touches.length === 0) {{
                    isZoomPanning = false;
                    setTimeout(() => {{ didZoomPanMove = false; }}, 50);
                }}
            }});
        }}

        if (zoomScaleResetBtn) {{
            zoomScaleResetBtn.addEventListener('click', (e) => {{
                e.stopPropagation();
                zoomScale = 1.0;
                zoomPanX = 0;
                zoomPanY = 0;
                applyZoomTransform();
            }});
        }}

        if (zoomExitBtn) {{
            zoomExitBtn.addEventListener('click', (e) => {{
                e.stopPropagation();
                closeZoomOverlay();
            }});
        }}

        async function openModal(item) {{
            syncGalleryLanguage();
            modal.classList.add('active');
            currentSlides = (item.images && item.images.length > 0)
                ? item.images
                : [{{ id: item.id, full: item.full, title: item.title, download_tif: item.download_tif }}];

            sliderTrack.innerHTML = currentSlides.map((s, idx) =>
                `<div class="modal-slide" style="transform: translateX(${{idx * 100}}%)"><img src="${{s.full}}" alt="${{(s.title || '').replace(/"/g, '&quot;')}}" class="modal-image" draggable="false"></div>`
            ).join('');

            sliderTrack.querySelectorAll('img').forEach(img => checkAndConvertHeic(img));
            updateSlide(0);

            if (item.descUrl) {{
                modalDetails.style.display = 'block';
                modalDetails.removeAttribute('open');
                modalContent.classList.remove('rotated');
                descContent.innerHTML = document.documentElement.lang === 'en' ? '<span class="blink">Loading data from server...</span>' : '<span class="blink">Wczytywanie danych z serwera...</span>';

                try {{
                    const response = await fetch(item.descUrl);
                    if (!response.ok) throw new Error('Nie znaleziono pliku opisu (404).');

                    const htmlData = await response.text();

                    if (htmlData.includes('id="gallery-grid"') || htmlData.includes('data-system="Toxic Echo Studio"')) {{
                        throw new Error('Serwer zwrócił stronę główną zamiast pliku opisu. Sprawdź ścieżkę!');
                    }}

                    descContent.innerHTML = htmlData;
                    descContent.removeAttribute('data-active-lang');

                    // Synchronizacja aktywnego przycisku w przełączniku opisu z aktualnym językiem strony
                    var curLang = document.documentElement.lang === 'en' ? 'en' : 'pl';
                    var langBtns = descContent.querySelectorAll('.lang-btn, .opis-lang-btn');
                    langBtns.forEach(function(b) {{
                        if (b.getAttribute('data-lang') === curLang) {{
                            b.classList.add('active');
                            b.setAttribute('aria-current', 'true');
                        }} else {{
                            b.classList.remove('active');
                            b.removeAttribute('aria-current');
                        }}
                    }});

                    const descImages = descContent.querySelectorAll('img');
                    descImages.forEach(img => checkAndConvertHeic(img));
                }} catch (error) {{
                    descContent.innerHTML = `<span style="color: #ff0000; font-weight: bold;">[ERROR] Błąd wczytywania opisu:<br>${{error.message}}</span>`;
                }}
            }} else {{
                modalDetails.style.display = 'none';
                modalDetails.removeAttribute('open');
                modalContent.classList.remove('rotated');
            }}
        }}

        // Obracanie układu na mobilkach
        if (rotateBtn) {{
            rotateBtn.addEventListener('click', (e) => {{
                e.stopPropagation();
                modalContent.classList.toggle('rotated');
            }});
        }}

        // Funkcja zamykająca modal
        function closeModal() {{
            closeZoomOverlay();
            modal.classList.remove('active');
            sliderTrack.innerHTML = '';
            modalContent.classList.remove('rotated');
            downloadBtn.style.display = 'none';
            downloadBtn.href = '';
            downloadBtn.removeAttribute('data-asc');
        }}

        const modalCloseBtn = document.getElementById('modal-close');
        if (modalCloseBtn) {{
            modalCloseBtn.addEventListener('click', (e) => {{
                e.preventDefault();
                e.stopPropagation();
                closeModal();
            }});
        }}

        // Zamknięcie modala po kliknięciu poza obrazek (w tło)
        modal.addEventListener('click', (e) => {{
            if (didDragMove) return;
            if (e.target.closest('.tape-nav-btn') || e.target.closest('.modal-slide-counter') || e.target.closest('.modal-zoom-btn') || e.target.closest('.zoom-overlay')) return;
            if (e.target === modal || e.target.classList.contains('modal-content') || e.target.classList.contains('modal-slider-row')) {{
                closeModal();
            }}
        }});

        // Obsługa klawiatury (ArrowLeft, ArrowRight, Escape)
        document.addEventListener('keydown', (e) => {{
            if (zoomOverlay && zoomOverlay.classList.contains('active')) {{
                if (e.key === 'Escape') {{
                    e.preventDefault();
                    closeZoomOverlay();
                }}
                return;
            }}
            if (!modal.classList.contains('active')) return;
            if (e.key === 'Escape') {{
                closeModal();
            }} else if (e.key === 'ArrowLeft' && currentSlides.length > 1) {{
                if (currentSlideIndex > 0) updateSlide(currentSlideIndex - 1);
            }} else if (e.key === 'ArrowRight' && currentSlides.length > 1) {{
                if (currentSlideIndex < currentSlides.length - 1) updateSlide(currentSlideIndex + 1);
            }}
        }});

        console.log("%c {cat_label} Initialized - RAWR XD ", "color: #00ff00; background: #000; font-family: monospace; border: 1px solid #ff007f;");
    </script>"""
    return modal_container_html, zoom_overlay_html, script_html

def update_category_index(category, new_items):
    index_path = os.path.join(OUTPUT_DIR, category, "index.html")
    if not os.path.exists(index_path):
        print(f"Error: {index_path} not found")
        return []
        
    with open(index_path, 'r', encoding='utf-8') as f:
        html = f.read()
        
    # Inject missing download button HTML element if not present
    if 'id="modal-download-btn"' not in html:
        html = html.replace(
            '</details>\n            </div>',
            '</details>\n                <a href="" id="modal-download-btn" class="main-menu-btn modal-download-btn" download>DOWNLOAD MAX QUALITY (.TIF)</a>\n            </div>'
        )
        html = html.replace(
            '</details>\r\n            </div>',
            '</details>\r\n                <a href="" id="modal-download-btn" class="main-menu-btn modal-download-btn" download>DOWNLOAD MAX QUALITY (.TIF)</a>\r\n            </div>'
        )
        print(f"Injected download button HTML into {index_path}")
        
    replace_mockups = "Gołąb #01: Start" in html or "Gołąb #02: Neon" in html
    
    migrated_subgallery_dirs = []
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
                            "category": category,
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
                        migrated_subgallery_dirs.append(os.path.join(OUTPUT_DIR, category, slug))
                        print(f"Migrated subgallery {category}/{slug}/ ({len(sub_items)} slides) into parent modal")
                        continue
            item["category"] = category
            existing_items.append(item)
            
    all_items = existing_items + new_items
    js_array = format_gallery_data_js(all_items)
    
    modal_container_html, zoom_overlay_html, script_html = build_modal_and_script_html(category, js_array)
    
    # Replace modal-image-container block
    html = re.sub(
        r'<div class="modal-image-container"[\s\S]*?</div>\s*(?=<div class="modal-description">)',
        lambda _: modal_container_html + "\n\n            ",
        html
    )
    
    # Idempotently inject or replace zoom overlay right before galleryData script block
    if "<!-- ZOOM_OVERLAY_START -->" in html and "<!-- ZOOM_OVERLAY_END -->" in html:
        html = re.sub(
            r'<!-- ZOOM_OVERLAY_START -->[\s\S]*?<!-- ZOOM_OVERLAY_END -->',
            lambda _: zoom_overlay_html.strip(),
            html
        )
        html = re.sub(
            r'<script>\s*const galleryData\s*=\s*\[[\s\S]*?</script>',
            lambda _: script_html,
            html
        )
    else:
        html = re.sub(
            r'<script>\s*const galleryData\s*=\s*\[[\s\S]*?</script>',
            lambda _: zoom_overlay_html + "\n\n" + script_html,
            html
        )
    
    # Update version and build metadata only when new items or migrated subgalleries exist
    if new_items or migrated_subgallery_dirs:
        html = re.sub(r'data-version="[^"]*"', 'data-version="3.1.4"', html)
        html = re.sub(r'data-build="\d+"', 'data-build="20261115"', html)
        html = re.sub(r'style\.css\?v=\d+', 'style.css?v=20261115', html)
    
    with open(index_path, 'w', encoding='utf-8') as f:
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
            
    # Update sitemap.xml
    if os.path.exists(SITEMAP_PATH):
        with open(SITEMAP_PATH, 'r', encoding='utf-8') as f:
            xml = f.read()
        # Remove <url> blocks pointing to subgalleries (two segments after domain)
        xml = re.sub(
            r'\s*<url>\s*<loc>https://gallery\.emo-changeling\.xyz/(?:aviary|digiart|photo|other)/[^/<]+/</loc>[\s\S]*?</url>',
            '',
            xml
        )
        xml = re.sub(r'<lastmod>.*?</lastmod>', '<lastmod>2026-11-15</lastmod>', xml)
        with open(SITEMAP_PATH, 'w', encoding='utf-8') as f:
            f.write(xml)
        print("Cleaned up and updated sitemap.xml")
        gpg_sign_file(SITEMAP_PATH)
        
    # Update main index files and category files
    html_targets = [
        os.path.join(OUTPUT_DIR, "index.html"),
        os.path.join(OUTPUT_DIR, "en", "index.html"),
        os.path.join(OUTPUT_DIR, "aviary", "index.html"),
        os.path.join(OUTPUT_DIR, "digiart", "index.html"),
        os.path.join(OUTPUT_DIR, "photo", "index.html"),
        os.path.join(OUTPUT_DIR, "other", "index.html"),
    ]
    for hpath in html_targets:
        if os.path.exists(hpath):
            with open(hpath, 'r', encoding='utf-8') as f:
                hcontent = f.read()
            hcontent = re.sub(r'data-version="[^"]*"', 'data-version="3.1.4"', hcontent)
            hcontent = re.sub(r'data-build="\d+"', 'data-build="20261115"', hcontent)
            hcontent = re.sub(r'style\.css\?v=\d+', 'style.css?v=20261115', hcontent)
            with open(hpath, 'w', encoding='utf-8') as f:
                f.write(hcontent)
            gpg_sign_file(hpath)
            
    # Update llms.txt, .well-known/llms.txt, humans.txt
    meta_files = [
        os.path.join(OUTPUT_DIR, "llms.txt"),
        os.path.join(OUTPUT_DIR, ".well-known", "llms.txt"),
        os.path.join(OUTPUT_DIR, "humans.txt"),
    ]
    for mpath in meta_files:
        if os.path.exists(mpath):
            with open(mpath, 'r', encoding='utf-8') as f:
                mcontent = f.read()
            mcontent = re.sub(r'2026-\d{2}-\d{2}', '2026-11-15', mcontent)
            mcontent = re.sub(r'2026/\d{2}/\d{2}', '2026/11/15', mcontent)
            mcontent = re.sub(r'2026\d{4}', '20261115', mcontent)
            with open(mpath, 'w', encoding='utf-8') as f:
                f.write(mcontent)
            gpg_sign_file(mpath)
            
    # Sign style.css if present
    style_css_path = os.path.join(OUTPUT_DIR, "css", "style.css")
    if os.path.exists(style_css_path):
        gpg_sign_file(style_css_path)

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
        
    # Save registry
    if processed_this_run:
        save_registry(registry + processed_this_run)
        print(f"Processed {len(processed_this_run)} folders in this run.")
    else:
        print("No new folders to process.")

if __name__ == "__main__":
    main()
