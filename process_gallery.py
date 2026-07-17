import os
import re
import json
import shutil
import subprocess
from PIL import Image

# Setup Paths
WORKSPACE_DIR = r"c:\Users\mighn\source\repos\toxic-echo-studio\--emo-changeling.xyz"
INPUT_DIR = r"c:\Users\mighn\source\repos\toxic-echo-studio\temp_gallery\GALLERY"
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
        "gpg", "--batch", "--yes", "--detach-sign", "-a",
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
        # CONDITION C: Multiple PNG/TIF files (Subgallery)
        slug = re.sub(r'[^a-z0-9]', '', title.lower().split()[0])
        if not slug:
            slug = "subgallery"
            
        print(f"Creating subgallery for '{title}' at /{category}/{slug}/")
        
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
            
        # Create subgallery page
        create_subgallery_page(category, slug, title, subgallery_items)
        
        # Subgallery folder thumbnail
        subgallery_thumb = subgallery_items[0]["thumb"]
        
        item_info = {
            "type": "subgallery",
            "category": category,
            "id": slug,
            "thumb": subgallery_thumb,
            "title": title,
            "link": f"{slug}/",
            "allocated_ids": [item["id"] for item in subgallery_items]
        }
        
    return item_info

def create_subgallery_page(category, slug, title, items):
    template_path = os.path.join(OUTPUT_DIR, "aviary", "nokill", "index.html")
    dest_dir = os.path.join(OUTPUT_DIR, category, slug)
    os.makedirs(dest_dir, exist_ok=True)
    dest_path = os.path.join(dest_dir, "index.html")
    
    with open(template_path, 'r', encoding='utf-8') as f:
        html = f.read()
        
    # Map category names to display names
    cat_display = "Monster Art" if category == "other" else category.capitalize()
    cat_upper = cat_display.upper()
        
    # Replace metadata
    html = re.sub(r'<title>.*?</title>', f'<title>{title} | {cat_display} | Emo-Changeling Gallery</title>', html)
    html = re.sub(r'<meta name="description" content=".*?">', f'<meta name="description" content="{title} - podgaleria w dziale {cat_display}.">', html)
    html = re.sub(r'<link rel="canonical" href=".*?">', f'<link rel="canonical" href="https://gallery.emo-changeling.xyz/{category}/{slug}/">', html)
    
    # OG and Twitter
    html = re.sub(r'<meta property="og:title" content=".*?">', f'<meta property="og:title" content="{title} | {cat_display} | Emo-Changeling Gallery">', html)
    html = re.sub(r'<meta property="og:url" content=".*?">', f'<meta property="og:url" content="https://gallery.emo-changeling.xyz/{category}/{slug}/">', html)
    html = re.sub(r'<meta name="twitter:title" content=".*?">', f'<meta name="twitter:title" content="{title} | {cat_display} | Emo-Changeling Gallery">', html)
    
    # Breadcrumbs
    breadcrumb_match = re.search(r'(<script type="application/ld\+json">[\s\S]*?</script>)', html)
    if breadcrumb_match:
        bc_block = breadcrumb_match.group(1)
        bc_block_new = bc_block.replace("Aviary", cat_display)
        bc_block_new = bc_block_new.replace("aviary", category)
        bc_block_new = bc_block_new.replace("NoKill", title)
        bc_block_new = bc_block_new.replace("nokill", slug)
        html = html.replace(bc_block, bc_block_new)
        
    # Replace header glitch title
    html = re.sub(r'<h1 class="glitch" data-text=".*?">.*?</h1>', f'<h1 class="glitch" data-text="{title.upper()}">{title.upper()}</h1>', html)
    
    # Replace description box
    html = re.sub(r'<div class="content-box aviary-box">\s*<p>.*?</p>\s*</div>', 
                  f'<div class="content-box aviary-box"><p>Podgaleria {title}. Kliknij w grafę, żeby rozwinąć pełen obraz i ukryty opis.</p></div>', html)
                  
    # Replace back button
    html = re.sub(r'<a href="\.\./" class="main-menu-btn" aria-label=".*?">.*?</a>',
                  f'<a href="../" class="main-menu-btn" aria-label="Wróć do {cat_display}">❮ WRÓĆ DO {cat_upper}</a>', html)
                  
    # Replace galleryData
    js_items = []
    for item in items:
        desc_line = f"descUrl: '{item['descUrl']}'," if item['descUrl'] else ""
        js_items.append(f"""            {{
                id: {item['id']},
                thumb: '{item['thumb']}',
                full: '{item['full']}',
                title: {repr(item['title'])},
                {desc_line}
                download_tif: '{item['download_tif']}'
            }}""")
    js_array = "const galleryData = [\n" + ",\n".join(js_items) + "\n        ];"
    
    html = re.sub(r'const galleryData\s*=\s*\[[\s\S]*?\];', js_array, html)
    
    # Versioning & Cache Busting
    html = re.sub(r'data-version="P[\d\.]+-nokill"', f'data-version="P0.2.6-{slug}"', html)
    html = re.sub(r'data-build="\d+"', 'data-build="20260712"', html)
    html = html.replace('style.css?v=20260529', 'style.css?v=20260712')
    html = html.replace('style.css?v=20260607', 'style.css?v=20260712')
    html = html.replace('style.css?v=20260613', 'style.css?v=20260712')
    html = html.replace('style.css?v=20260625', 'style.css?v=20260712')
    
    # Handle description hiding logic in JS (openModal function)
    js_details_show = """            if (item.descUrl) {
                modalDetails.style.display = 'block';
                modalDetails.removeAttribute('open');
                modalContent.classList.remove('rotated');
                descContent.innerHTML = '<span class="blink">Wczytywanie danych z serwera...</span>';
                
                if (item.download_tif) {
                    downloadBtn.href = item.download_tif;
                    downloadBtn.style.display = 'inline-block';
                    if (item.download_tif.toLowerCase().endsWith('.png')) {
                        downloadBtn.textContent = 'DOWNLOAD MAX QUALITY (.PNG)';
                    } else {
                        downloadBtn.textContent = 'DOWNLOAD MAX QUALITY (.TIF)';
                    }
                } else {
                    downloadBtn.style.display = 'none';
                }

                try {
                    const response = await fetch(item.descUrl);
                    if (!response.ok) throw new Error('Nie znaleziono pliku opisu (404).');

                    const htmlData = await response.text();

                    if (htmlData.includes('id="gallery-grid"') || htmlData.includes('data-system="Toxic Echo Studio"')) {
                        throw new Error('Serwer zwrócił stronę główną zamiast pliku opisu. Sprawdź ścieżkę!');
                    }

                    descContent.innerHTML = htmlData;
                    
                    const descImages = descContent.querySelectorAll('img');
                    descImages.forEach(img => checkAndConvertHeic(img));
                } catch (error) {
                    descContent.innerHTML = `<span style="color: #ff0000; font-weight: bold;">[ERROR] Błąd wczytywania opisu:<br>${error.message}</span>`;
                }
            } else {
                modalDetails.style.display = 'none';
                if (item.download_tif) {
                    downloadBtn.href = item.download_tif;
                    downloadBtn.style.display = 'inline-block';
                    if (item.download_tif.toLowerCase().endsWith('.png')) {
                        downloadBtn.textContent = 'DOWNLOAD MAX QUALITY (.PNG)';
                    } else {
                        downloadBtn.textContent = 'DOWNLOAD MAX QUALITY (.TIF)';
                    }
                } else {
                    downloadBtn.style.display = 'none';
                }
            }"""
            
    # Precision regex targeting the end of openModal function precisely
    open_modal_pattern = r'async function openModal\(item\) \{[\s\S]*?\}\s*(?=\/\/\s*Obracanie układu)'
    html = re.sub(open_modal_pattern, f'async function openModal(item) {{\n            modal.classList.add(\'active\');\n            modalImg.src = item.full;\n            modalImg.alt = item.title;\n\n{js_details_show}\n        }}', html)
    
    with open(dest_path, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"Created subgallery HTML file at {dest_path}")
    gpg_sign_file(dest_path)

def update_category_index(category, new_items):
    index_path = os.path.join(OUTPUT_DIR, category, "index.html")
    if not os.path.exists(index_path):
        print(f"Error: {index_path} not found")
        return
        
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
        
    # Inject downloadBtn variable declaration in JavaScript if not present
    if 'const downloadBtn =' not in html:
        html = html.replace(
            "const modalDetails = document.getElementById('modal-details');",
            "const modalDetails = document.getElementById('modal-details');\n        const downloadBtn = document.getElementById('modal-download-btn');"
        )
        print(f"Injected downloadBtn declaration in JavaScript of {index_path}")
        
    # Update the cardDiv event listener to support redirections (item.link)
    html = html.replace(
        "cardDiv.addEventListener('click', () => openModal(item));",
        """cardDiv.addEventListener('click', () => {
                if (item.link) {
                    window.location.href = item.link;
                } else {
                    openModal(item);
                }
            });"""
    )
    print(f"Injected redirection support into event listeners of {index_path}")
        
    # Bump version and build date
    version_match = re.search(r'data-version="P(\d+)\.(\d+)\.(\d+)"', html)
    if version_match:
        maj, min_v, pat = map(int, version_match.groups())
        new_ver = f"P{maj}.{min_v}.{pat+1}"
        html = html.replace(version_match.group(0), f'data-version="{new_ver}"')
        
    html = re.sub(r'data-build="\d+"', 'data-build="20260712"', html)
    html = html.replace('style.css?v=20260529', 'style.css?v=20260712')
    html = html.replace('style.css?v=20260607', 'style.css?v=20260712')
    html = html.replace('style.css?v=20260613', 'style.css?v=20260712')
    html = html.replace('style.css?v=20260625', 'style.css?v=20260712')
    
    replace_mockups = "Gołąb #01: Start" in html or "Gołąb #02: Neon" in html
    
    existing_items = []
    if not replace_mockups:
        match = re.search(r'const galleryData\s*=\s*\[([\s\S]*?)\];', html)
        if match:
            js_array_content = match.group(1)
            obj_matches = re.findall(r'\{([\s\S]*?)\}', js_array_content)
            for obj_str in obj_matches:
                item = {}
                id_match = re.search(r'id:\s*([\'"]?)(.*?)\1\s*,', obj_str)
                if id_match:
                    val = id_match.group(2)
                    item["id"] = int(val) if val.isdigit() and not id_match.group(1) else val
                
                title_match = re.search(r'title:\s*([\'"])(.*?)\1\s*,?', obj_str)
                if title_match:
                    item["title"] = title_match.group(2)
                    
                for field in ["thumb", "full", "descUrl", "download_tif", "link"]:
                    field_match = re.search(r'' + field + r':\s*([\'"])(.*?)\1\s*,?', obj_str)
                    if field_match:
                        item[field] = field_match.group(2)
                    else:
                        item[field] = None
                        
                if item.get("link"):
                    item["type"] = "subgallery"
                else:
                    item["type"] = "single"
                item["category"] = category
                existing_items.append(item)
        
    all_items = existing_items + new_items
    
    # Format JavaScript array
    js_items = []
    for item in all_items:
        if item.get("type") == "subgallery":
            js_items.append(f"""            {{
                id: '{item['id']}',
                thumb: '{item['thumb']}',
                title: {repr(item['title'])},
                link: '{item['link']}'
            }}""")
        else:
            desc_line = f"descUrl: '{item['descUrl']}'" if item['descUrl'] else ""
            download_line = f"download_tif: '{item['download_tif']}'" if item.get('download_tif') else ""
            lines = [
                f"                id: {item['id']}",
                f"                thumb: '{item['thumb']}'",
                f"                full: '{item['full']}'",
                f"                title: {repr(item['title'])}"
            ]
            if desc_line:
                lines.append("                " + desc_line)
            if download_line:
                lines.append("                " + download_line)
            
            formatted_item = "            {\n" + ",\n".join(lines) + "\n            }"
            js_items.append(formatted_item)
            
    js_array = "const galleryData = [\n" + ",\n".join(js_items) + "\n        ];"
    
    html = re.sub(r'const galleryData\s*=\s*\[[\s\S]*?\];', js_array, html)
    
    # Handle description hiding logic in JS (openModal function)
    js_details_show = """            if (item.descUrl) {
                modalDetails.style.display = 'block';
                modalDetails.removeAttribute('open');
                modalContent.classList.remove('rotated');
                descContent.innerHTML = '<span class="blink">Wczytywanie danych z serwera...</span>';
                
                if (item.download_tif) {
                    downloadBtn.href = item.download_tif;
                    downloadBtn.style.display = 'inline-block';
                    if (item.download_tif.toLowerCase().endsWith('.png')) {
                        downloadBtn.textContent = 'DOWNLOAD MAX QUALITY (.PNG)';
                    } else {
                        downloadBtn.textContent = 'DOWNLOAD MAX QUALITY (.TIF)';
                    }
                } else {
                    downloadBtn.style.display = 'none';
                }

                try {
                    const response = await fetch(item.descUrl);
                    if (!response.ok) throw new Error('Nie znaleziono pliku opisu (404).');

                    const htmlData = await response.text();

                    if (htmlData.includes('id="gallery-grid"') || htmlData.includes('data-system="Toxic Echo Studio"')) {
                        throw new Error('Serwer zwrócił stronę główną zamiast pliku opisu. Sprawdź ścieżkę!');
                    }

                    descContent.innerHTML = htmlData;
                    
                    const descImages = descContent.querySelectorAll('img');
                    descImages.forEach(img => checkAndConvertHeic(img));
                } catch (error) {
                    descContent.innerHTML = `<span style="color: #ff0000; font-weight: bold;">[ERROR] Błąd wczytywania opisu:<br>${error.message}</span>`;
                }
            } else {
                modalDetails.style.display = 'none';
                if (item.download_tif) {
                    downloadBtn.href = item.download_tif;
                    downloadBtn.style.display = 'inline-block';
                    if (item.download_tif.toLowerCase().endsWith('.png')) {
                        downloadBtn.textContent = 'DOWNLOAD MAX QUALITY (.PNG)';
                    } else {
                        downloadBtn.textContent = 'DOWNLOAD MAX QUALITY (.TIF)';
                    }
                } else {
                    downloadBtn.style.display = 'none';
                }
            }"""
            
    # Precision regex targeting the end of openModal function precisely
    open_modal_pattern = r'async function openModal\(item\) \{[\s\S]*?\}\s*(?=\/\/\s*Obracanie układu)'
    html = re.sub(open_modal_pattern, f'async function openModal(item) {{\n            modal.classList.add(\'active\');\n            modalImg.src = item.full;\n            modalImg.alt = item.title;\n\n{js_details_show}\n        }}', html)
    
    with open(index_path, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"Updated index HTML file at {index_path}")
    gpg_sign_file(index_path)

def update_sitemap(new_urls):
    if not os.path.exists(SITEMAP_PATH):
        print(f"Sitemap not found at {SITEMAP_PATH}")
        return
        
    with open(SITEMAP_PATH, 'r', encoding='utf-8') as f:
        xml = f.read()
        
    today = "2026-07-12T00:00:00+00:00"
    
    # Update modified date for other/, digiart/, and aviary/, photo/
    for loc_name in ["other/", "digiart/", "aviary/", "photo/"]:
        pattern = r'(<loc>https://gallery\.emo-changeling\.xyz/' + loc_name + r'</loc>\s*<lastmod>).*?(</lastmod>)'
        xml = re.sub(pattern, r'\g<1>' + today + r'\g<2>', xml)
        
    # Check if we need to add new URLs
    for url in new_urls:
        if url not in xml:
            new_entry = f"""  <url>
    <loc>{url}</loc>
    <lastmod>{today}</lastmod>
    <priority>0.8</priority>
  </url>\n\n"""
            xml = xml.replace("</urlset>", new_entry + "</urlset>")
            print(f"Added {url} to sitemap")
            
    with open(SITEMAP_PATH, 'w', encoding='utf-8') as f:
        f.write(xml)
    print("Sitemap updated successfully")
    gpg_sign_file(SITEMAP_PATH)

def main():
    registry = load_registry()
    print(f"Loaded registry with {len(registry)} already processed folders.")
    
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
    
    sitemap_additions = []
    
    for folder in folders:
        if folder in registry:
            print(f"Folder {folder} is already processed. Skipping.")
            continue
            
        res = process_folder(folder, next_ids)
        if res:
            category = res["category"]
            category_items[category].append(res)
            processed_this_run.append(folder)
            
            if res.get("type") == "subgallery":
                sitemap_additions.append(f"https://gallery.emo-changeling.xyz/{category}/{res['id']}/")
                
    # Update indexes
    for category, items in category_items.items():
        if items:
            update_category_index(category, items)
            
    # Update sitemap
    if sitemap_additions or any(len(items) > 0 for items in category_items.values()):
        update_sitemap(sitemap_additions)
        
    # Save registry
    if processed_this_run:
        save_registry(registry + processed_this_run)
        print(f"Processed {len(processed_this_run)} folders in this run.")
    else:
        print("No new folders to process.")

if __name__ == "__main__":
    main()
