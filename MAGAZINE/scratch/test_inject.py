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

print("Robust logic completed successfully.")
