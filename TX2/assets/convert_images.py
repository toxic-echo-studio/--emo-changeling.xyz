import os
from PIL import Image

# Source directories
src_main_dir = r"C:\Users\mighn\source\repos\toxic-echo-studio\TX2 Pigeon Project -\Grafiki głowne"
src_fanart_dir = r"C:\Users\mighn\source\repos\toxic-echo-studio\TX2 Pigeon Project -\fanarty"

# Destination directory
dest_dir = r"c:\Users\mighn\source\repos\toxic-echo-studio\--emo-changeling.xyz\TX2\img"
os.makedirs(dest_dir, exist_ok=True)

print("Starting image conversion to WebP...")

# 1. Convert banner
banner_path = os.path.join(src_main_dir, "banner .png")
if os.path.exists(banner_path):
    img = Image.open(banner_path)
    img.save(os.path.join(dest_dir, "banner.webp"), "WEBP", quality=90)
    print("Converted banner .png -> banner.webp")
else:
    print(f"Error: Banner not found at {banner_path}")

# 2. Convert pentagram
pentagram_path = os.path.join(src_main_dir, "pentagram.png")
if os.path.exists(pentagram_path):
    img = Image.open(pentagram_path)
    if img.mode != 'RGBA':
        img = img.convert('RGBA')
    img.save(os.path.join(dest_dir, "pentagram.webp"), "WEBP", quality=90)
    print("Converted pentagram.png -> pentagram.webp")
else:
    print(f"Error: Pentagram not found at {pentagram_path}")

# 3. Convert fanarts
fanarts = [
    "J0n cambush art.png",
    "Kai Hannah, @kai_tx2 pigeon fanart.png",
    "Lena's Church portait.png",
    "glam ray_TX2.fan pigeons art.png",
    "tx2pigeonproject_kit_colson.png"
]

for idx, filename in enumerate(fanarts, start=1):
    filepath = os.path.join(src_fanart_dir, filename)
    if os.path.exists(filepath):
        img = Image.open(filepath)
        img.save(os.path.join(dest_dir, f"fanart_{idx}.webp"), "WEBP", quality=85)
        print(f"Converted fanart {idx}: {filename} -> fanart_{idx}.webp")
    else:
        print(f"Error: Fanart not found at {filepath}")

print("Image conversion completed successfully.")
