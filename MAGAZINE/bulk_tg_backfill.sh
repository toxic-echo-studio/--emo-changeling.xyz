#!/usr/bin/env bash
# ==============================================================================
# Skrypt: bulk_tg_backfill.sh
# Rola: Narzędzie masowej migracji i backfillu wątków dyskusyjnych Telegram
#       w modelu dwujęzycznych par publikacyjnych (Bilingual Thread Pairing).
# Filozofia: The Reverse Emo Changeling / --emo-changeling.xyz
# Standard:
#   - Idempotencja i rygor powłoki (set -Eeuo pipefail)
#   - Bilingual Thread Pairing: jeden wspólny wpis TG i jeden message_id dla pary PL + EN
#   - 100% Read-Only preflight: faza raportu kwalifikacji bez dotykania plików na dysku
#   - Detekcja asymetrii i konfliktów wątków w parach (pl_mid != en_mid)
#   - Twarda weryfikacja prywatnego klucza GPG (list-secret-keys) w preflight
#   - Ścisłe dopasowanie tagu iframe (ochrona przed linkami <a> w treści)
#   - Anti-Flood Protection (sleep 3.5s + obsługa HTTP 429 retry_after)
#   - Bezpieczny odczyt .env bez source i pełne maskowanie sekretów
#   - DOKŁADNIE JEDEN zbiorczy commit Git + podpisy GPG + push + HTTP polling
# ==============================================================================

set -Eeuo pipefail
export PYTHONIOENCODING=utf-8

# Kontekst etapu wykonania do bezpiecznego logowania w pułapce ERR
CURRENT_STAGE="Inicjalizacja środowiska i preflight"


PAYLOAD_FILE=""
cleanup_temp() {
    if [ -n "${PAYLOAD_FILE:-}" ] && [ -f "${PAYLOAD_FILE:-}" ]; then
        rm -f "$PAYLOAD_FILE"
    fi
}
trap 'echo >&2 "[FATAL ERR] Awaria w linii $LINENO podczas etapu: '\''$CURRENT_STAGE'\''. Przerywam procedurę masowej migracji."; cleanup_temp' ERR
trap cleanup_temp EXIT



# ==============================================================================
# 1. PARSOWANIE ARGUMENTÓW I POMOC
# ==============================================================================

AUTO_CONFIRM=false

show_help() {
    cat << 'EOF'
Użycie: ./bulk_tg_backfill.sh [OPCJE]

Narzędzie masowej migracji artykułów magazynu do Telegram Bot API w modelu
dwujęzycznych par publikacyjnych (Bilingual Thread Pairing). Artykuły PL i EN
dzielą dokładnie jeden wspólny wątek dyskusji na kanale Telegram.

Opcje:
  --yes, -y    Pominięcie pytania o potwierdzenie [t/N] przed startem przetwarzania.
  --help, -h   Wyświetlenie niniejszego komunikatu pomocy.
EOF
}

for arg in "$@"; do
    case "$arg" in
        --yes|-y)
            AUTO_CONFIRM=true
            ;;
        --help|-h)
            show_help
            exit 0
            ;;
        *)
            echo >&2 "[BŁĄD] Nieznany argument: '$arg'"
            show_help
            exit 1
            ;;
    esac
done

# ==============================================================================
# 2. RYGOR ŚRODOWISKA I PREFLIGHT
# ==============================================================================

CURRENT_STAGE="Weryfikacja narzędzi systemowych"
for cmd in git curl python3 gpg; do
    if ! command -v "$cmd" &> /dev/null; then
        echo >&2 "[BŁĄD] Wymagane narzędzie '$cmd' nie jest zainstalowane w systemie."
        exit 1
    fi
done

CURRENT_STAGE="Weryfikacja środowiska Git"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if ! git -C "$SCRIPT_DIR" rev-parse --is-inside-work-tree &> /dev/null; then
    echo >&2 "[BŁĄD] Skrypt nie znajduje się wewnątrz repozytorium Git."
    exit 1
fi

REPO_ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel)"
MAGAZINE_DIR="$SCRIPT_DIR"
CURRENT_BRANCH="$(git -C "$REPO_ROOT" rev-parse --abbrev-ref HEAD)"

if [ -z "$CURRENT_BRANCH" ] || [ "$CURRENT_BRANCH" = "HEAD" ]; then
    echo >&2 "[BŁĄD] Brak aktywnej gałęzi Git (detached HEAD)."
    exit 1
fi

if ! git -C "$REPO_ROOT" remote get-url origin &> /dev/null; then
    echo >&2 "[BŁĄD] Remote 'origin' nie jest skonfigurowany w repozytorium."
    exit 1
fi

# Ochrona przed zanieczyszczeniem indeksu stagingu
if ! git -C "$REPO_ROOT" diff --cached --quiet; then
    echo >&2 "[BŁĄD] W indeksie Git (staging) znajdują się już inne zmiany. Oczyść staging przed startem."
    exit 1
fi

CURRENT_STAGE="Bezpieczny odczyt konfiguracji środowiskowej"
ENV_PATH=""
if [ -f "$MAGAZINE_DIR/.env" ]; then
    ENV_PATH="$MAGAZINE_DIR/.env"
elif [ -f "$REPO_ROOT/.env" ]; then
    ENV_PATH="$REPO_ROOT/.env"
fi

# Bezpieczny odczyt zmiennych bez użycia source
parse_env_var() {
    local file="$1"
    local var_name="$2"
    if [ ! -f "$file" ]; then
        return
    fi
    local line
    line=$(grep -E "^[[:space:]]*${var_name}=" "$file" 2>/dev/null | tail -n 1 || true)
    if [ -n "$line" ]; then
        local val
        val="${line#*=}"
        val=$(echo "$val" | sed -E 's/[[:space:]]+#.*$//')
        val=$(echo "$val" | tr -d '\r' | sed -E 's/^[[:space:]]+//; s/[[:space:]]+$//')
        if [[ "$val" =~ ^\"(.*)\"$ ]] || [[ "$val" =~ ^\'(.*)\'$ ]]; then
            val="${BASH_REMATCH[1]}"
            val=$(echo "$val" | sed -E 's/^[[:space:]]+//; s/[[:space:]]+$//')
        fi
        echo "$val"
    fi
}

TG_BOT_TOKEN="${TG_BOT_TOKEN:-}"
TG_CHAT_ID="${TG_CHAT_ID:-}"
DOMAIN="${DOMAIN:-}"

if [ -n "$ENV_PATH" ]; then
    if [ -z "$TG_BOT_TOKEN" ]; then
        TG_BOT_TOKEN=$(parse_env_var "$ENV_PATH" "TG_BOT_TOKEN")
    fi
    if [ -z "$TG_CHAT_ID" ]; then
        TG_CHAT_ID=$(parse_env_var "$ENV_PATH" "TG_CHAT_ID")
    fi
    if [ -z "$DOMAIN" ]; then
        DOMAIN=$(parse_env_var "$ENV_PATH" "DOMAIN")
    fi
fi

TG_BOT_TOKEN=$(echo "$TG_BOT_TOKEN" | tr -d '\r' | sed -E 's/^[[:space:]]+//; s/[[:space:]]+$//')
TG_CHAT_ID=$(echo "$TG_CHAT_ID" | tr -d '\r' | sed -E 's/^[[:space:]]+//; s/[[:space:]]+$//')
DOMAIN=$(echo "$DOMAIN" | tr -d '\r' | sed -E 's/^[[:space:]]+//; s/[[:space:]]+$//')

TG_CHAT_ID="${TG_CHAT_ID:-@emochangeling}"
TG_CHANNEL_NAME="${TG_CHAT_ID#@}"
BASE_URL="${DOMAIN:-https://reverse.emo-changeling.xyz}"

if [ -z "$TG_BOT_TOKEN" ]; then
    echo >&2 "[BŁĄD] Zmienna TG_BOT_TOKEN nie została zdefiniowana lub jest pusta."
    exit 1
fi

# Funkcja maskowania sekretu w logach i komunikatach błędów
mask_secret() {
    local text="$1"
    if [ -n "$TG_BOT_TOKEN" ]; then
        text="${text//$TG_BOT_TOKEN/[MASKED_TOKEN]}"
    fi
    echo "$text"
}

CURRENT_STAGE="Weryfikacja prywatnego klucza kryptograficznego GPG"
GPG_KEY_ID="55B1F5E9342F388E6F06483C34A85D454D1FD3BC"
# Interoperacyjność Windows / Linux: priorytet dla dedykowanej instalacji GnuPG przed MSYS2 gpg
GPG_BIN="gpg"
if [ -x "/c/Program Files/GnuPG/bin/gpg.exe" ]; then
    GPG_BIN="/c/Program Files/GnuPG/bin/gpg.exe"
elif [ -x "/c/Program Files (x86)/GnuPG/bin/gpg.exe" ]; then
    GPG_BIN="/c/Program Files (x86)/GnuPG/bin/gpg.exe"
fi

# Twarda weryfikacja obecności klucza PRYWATNEGO (secret key) przed wykonaniem jakichkolwiek operacji
if ! "$GPG_BIN" --batch --list-secret-keys "$GPG_KEY_ID" &> /dev/null; then
    echo >&2 "[BŁĄD KRYTYCZNY] Prywatny klucz GPG $GPG_KEY_ID (secret key) nie został odnaleziony w pęku kluczy ($GPG_BIN)."
    echo >&2 "Przerywam przed wysyłką do Telegrama, aby zapobiec awarii przy końcowym podpisywaniu."
    exit 1
fi

CURRENT_STAGE="Weryfikacja generatora kanałów RSS"
RSS_SCRIPT=""
if [ -f "$MAGAZINE_DIR/generate_rss.py" ]; then
    RSS_SCRIPT="$MAGAZINE_DIR/generate_rss.py"
elif [ -f "$REPO_ROOT/MAGAZINE/generate_rss.py" ]; then
    RSS_SCRIPT="$REPO_ROOT/MAGAZINE/generate_rss.py"
fi

if [ -z "$RSS_SCRIPT" ] || [ ! -f "$RSS_SCRIPT" ]; then
    echo >&2 "[BŁĄD] Nie odnaleziono generatora RSS (generate_rss.py)."
    exit 1
fi

python3 -m py_compile "$RSS_SCRIPT"

RSS_DIR="$(dirname "$RSS_SCRIPT")"
RSS_FILE_DEFAULT="$RSS_DIR/rss.xml"
RSS_FILE_PL="$RSS_DIR/rss-pl.xml"
RSS_FILE_EN="$RSS_DIR/rss-en.xml"

# ==============================================================================
# 3. SILNIK GRUPOWANIA I KWALIFIKACJI PAR (PAIRING ENGINE - 100% READ-ONLY)
# ==============================================================================

CURRENT_STAGE="Skanowanie, detekcja par i kwalifikacja (Read-Only)"

WIDGET_PLACEHOLDER="<!-- TELEGRAM_WIDGET_HERE -->"
WIDGET_ANCHOR="<!-- Navigation Links and License under Article -->"

# Skanowanie w trybie WYŁĄCZNIE ODCZYT (Zero Write)
SCAN_RESULT_JSON="$(python3 -c '
import glob, os, re, sys, json

mag_dir = sys.argv[1]
channel = sys.argv[2]
placeholder = sys.argv[3]
anchor = sys.argv[4]

pl_dir = os.path.join(mag_dir, "pl")
en_dir = os.path.join(mag_dir, "en")

keys = set()
for lang_dir in [pl_dir, en_dir]:
    if not os.path.isdir(lang_dir):
        continue
    for p in glob.glob(os.path.join(lang_dir, "*-[0-9][0-9][0-9][0-9]", "*.html")):
        rel = os.path.relpath(p, lang_dir).replace("\\", "/")
        if re.match(r"^[0-9]+-[0-9]{4}/[^/]+\.html$", rel):
            keys.add(rel)

# Naturalne sortowanie kluczy wydań
def sort_key(k):
    parts = k.split("/", 1)
    issue_parts = parts[0].split("-")
    try:
        return (int(issue_parts[0]), int(issue_parts[1]), parts[1])
    except Exception:
        return (999, 999, k)

sorted_keys = sorted(keys, key=sort_key)

packages = []
skipped_pairs_count = 0
skipped_invalid_count = 0
conflict_pairs = []

# Ścisła, wyłącznie odczytująca weryfikacja pliku (Read-Only)
def inspect_file_read_only(path):
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    # Rygorystyczne dopasowanie widgetu t.me (script telegram-widget.js lub fallback iframe)
    widget_pattern = rf"""(?:data-telegram-discussion=[\"\x27](?:{re.escape(channel)}|emochangeling)/([0-9]+)[\"\x27]|<iframe[^>]+src=[\"\x27]https://t\.me/(?:{re.escape(channel)}|emochangeling)/([0-9]+))"""
    widget_m = re.search(widget_pattern, content, re.IGNORECASE)
    existing_id = (widget_m.group(1) or widget_m.group(2)) if widget_m else ""
    has_widget = bool(widget_m)

    if has_widget:
        return True, existing_id, True


    if placeholder in content:
        return False, "", True

    anc_count = content.count(anchor)
    if anc_count != 1:
        sys.stderr.write(f"[OSTRZEŻENIE] Kotwica nawigacji nie jest unikalna w {path} (liczba wystąpień: {anc_count}).\n")
        return False, "", False

    return False, "", True

for k in sorted_keys:
    pl_path = os.path.join(pl_dir, k).replace("\\", "/")
    en_path = os.path.join(en_dir, k).replace("\\", "/")
    has_pl = os.path.isfile(pl_path)
    has_en = os.path.isfile(en_path)

    if has_pl and has_en:
        pl_has_if, pl_mid, pl_ok = inspect_file_read_only(pl_path)
        en_has_if, en_mid, en_ok = inspect_file_read_only(en_path)

        if not pl_ok or not en_ok:
            skipped_invalid_count += 1
            continue

        # Sprawdzenie sytuacji, gdy OBA pliki mają już iframe
        if pl_has_if and en_has_if:
            if pl_mid == en_mid:
                # Spójna, w pełni wdrożona para
                skipped_pairs_count += 1
                continue
            else:
                # Rozbieżność / konflikt wątków dyskusji
                conflict_pairs.append({
                    "key": k,
                    "pl_mid": pl_mid,
                    "en_mid": en_mid
                })
                sys.stderr.write(
                    f"[CONFLICT_THREAD_ID] Wykryto konflikt ID wątków Telegram dla pary '\''{k}'\'': "
                    f"PL message_id={pl_mid} != EN message_id={en_mid}. "
                    f"Wymaga ręcznej weryfikacji — pomijam parę bez modyfikacji.\n"
                )
                continue

        # Reużycie ID, jeżeli jeden z plików pary posiada już poprawną ramkę
        reused_id = pl_mid or en_mid
        packages.append({
            "key": k,
            "type": "PAIR",
            "pl_path": pl_path,
            "en_path": en_path,
            "need_pl": not pl_has_if,
            "need_en": not en_has_if,
            "reused_msg_id": reused_id
        })
    elif has_pl:
        pl_has_if, pl_mid, pl_ok = inspect_file_read_only(pl_path)
        if not pl_ok:
            skipped_invalid_count += 1
            continue
        if pl_has_if:
            skipped_pairs_count += 1
            continue
        packages.append({
            "key": k,
            "type": "ORPHAN_PL",
            "pl_path": pl_path,
            "en_path": "",
            "need_pl": True,
            "need_en": False,
            "reused_msg_id": ""
        })
    elif has_en:
        en_has_if, en_mid, en_ok = inspect_file_read_only(en_path)
        if not en_ok:
            skipped_invalid_count += 1
            continue
        if en_has_if:
            skipped_pairs_count += 1
            continue
        packages.append({
            "key": k,
            "type": "ORPHAN_EN",
            "pl_path": "",
            "en_path": en_path,
            "need_pl": False,
            "need_en": True,
            "reused_msg_id": ""
        })

print(json.dumps({
    "total_keys": len(sorted_keys),
    "skipped_pairs": skipped_pairs_count,
    "skipped_invalid": skipped_invalid_count,
    "conflict_pairs": conflict_pairs,
    "packages": packages
}, ensure_ascii=False))
' "$MAGAZINE_DIR" "$TG_CHANNEL_NAME" "$WIDGET_PLACEHOLDER" "$WIDGET_ANCHOR")"

TOTAL_SCANNED_KEYS=$(python3 -c "import json, sys; print(json.loads(sys.argv[1])['total_keys'])" "$SCAN_RESULT_JSON")
SKIPPED_PAIRS=$(python3 -c "import json, sys; print(json.loads(sys.argv[1])['skipped_pairs'])" "$SCAN_RESULT_JSON")
SKIPPED_INVALID=$(python3 -c "import json, sys; print(json.loads(sys.argv[1])['skipped_invalid'])" "$SCAN_RESULT_JSON")
COUNT_CONFLICTS=$(python3 -c "import json, sys; print(len(json.loads(sys.argv[1]).get('conflict_pairs', [])))" "$SCAN_RESULT_JSON")
TOTAL_PACKAGES=$(python3 -c "import json, sys; print(len(json.loads(sys.argv[1])['packages']))" "$SCAN_RESULT_JSON")

COUNT_PAIRS=$(python3 -c "import json, sys; pkgs = json.loads(sys.argv[1])['packages']; print(sum(1 for p in pkgs if p['type'] == 'PAIR'))" "$SCAN_RESULT_JSON")
COUNT_ORPHANS=$(python3 -c "import json, sys; pkgs = json.loads(sys.argv[1])['packages']; print(sum(1 for p in pkgs if p['type'] != 'PAIR'))" "$SCAN_RESULT_JSON")

echo "=============================================================================="
echo " RAPORT KWALIFIKACJI DWUJĘZYCZNYCH PAR (BILINGUAL THREAD PAIRING)"
echo " [TRYB AUDYTU: 100% READ-ONLY — ŻADEN PLIK NIE ZOSTAŁ ZMODYFIKOWANY]"
echo "=============================================================================="
echo " Przeskanowane unikalne klucze wydań: $TOTAL_SCANNED_KEYS"
echo " Pominięte pełne pary (oba z iframe):  $SKIPPED_PAIRS"
echo " Pominięte (konflikt message_id):     $COUNT_CONFLICTS"
echo " Pominięte (błędna/brak kotwicy):      $SKIPPED_INVALID"
echo " Pakiety zakwalifikowane do wdrożenia: $TOTAL_PACKAGES"
echo "   - Pełne pary (PL + EN):              $COUNT_PAIRS"
echo "   - Pojedyncze artykuły (orphans):     $COUNT_ORPHANS"
echo " Kanał docelowy Telegram:              $TG_CHAT_ID"
echo "=============================================================================="

if [ "$COUNT_CONFLICTS" -gt 0 ]; then
    echo >&2 "UWAGA: Wykryto $COUNT_CONFLICTS par z konfliktem identyfikatorów wątków:"
    python3 -c '
import json, sys
conflicts = json.loads(sys.argv[1]).get("conflict_pairs", [])
for c in conflicts:
    print(f"  - [CONFLICT_THREAD_ID] {c[\"key\"]}: PL={c[\"pl_mid\"]} vs EN={c[\"en_mid\"]}", file=sys.stderr)
' "$SCAN_RESULT_JSON"
    echo >&2 "------------------------------------------------------------------------------"
fi

if [ "$TOTAL_PACKAGES" -eq 0 ]; then
    echo "Brak artykułów wymagających aktualizacji. Wszystkie pary posiadają już ramki iframe lub zostały pominięte."
    exit 0
fi

echo "Lista zakwalifikowanych pakietów publikacyjnych:"
python3 -c '
import json, sys
pkgs = json.loads(sys.argv[1])["packages"]
for i, p in enumerate(pkgs, 1):
    p_type = p.get("type", "")
    tag = "[PARA PL+EN]" if p_type == "PAIR" else f"[{p_type}]"
    key = p.get("key", "")
    reused = p.get("reused_msg_id", "")
    suffix = f" (re-use TG #{reused})" if reused else ""
    print(f"  {i:2d}. {tag} {key}{suffix}")
' "$SCAN_RESULT_JSON"
echo "------------------------------------------------------------------------------"

if [ "$AUTO_CONFIRM" = false ]; then
    USER_CONFIRM=""
    read -r -p "Czy chcesz rozpocząć masową migrację dla $TOTAL_PACKAGES pakietów publikacyjnych? [t/N]: " USER_CONFIRM || true
    case "$USER_CONFIRM" in
        [tT]|[tT][aA][kK]|[yY]|[yY][eE][sS])
            echo "Rozpoczynam procedurę publikacji i osadzania wątków..."
            ;;
        *)
            echo "Operacja anulowana przez użytkownika."
            exit 0
            ;;
    esac
fi

# ==============================================================================
# 4. PRZETWARZANIE WSADOWE PAR I WYSYŁKA TELEGRAM
# ==============================================================================

CURRENT_STAGE="Przetwarzanie wsadowe dwujęzycznych par"
MODIFIED_ARTICLES=()
LAST_CANONICAL_URL=""
LAST_MESSAGE_ID=""

PAYLOAD_FILE=""


for (( idx=0; idx<TOTAL_PACKAGES; idx++ )); do
    PACKAGE_NUM=$((idx + 1))

    # Odczyt danych pakietu
    PKG_DATA="$(python3 -c '
import json, sys
idx = int(sys.argv[2])
pkg = json.loads(sys.argv[1])["packages"][idx]
print(json.dumps(pkg, ensure_ascii=False))
' "$SCAN_RESULT_JSON" "$idx")"

    PKG_KEY="$(python3 -c "import json, sys; print(json.loads(sys.argv[1])['key'])" "$PKG_DATA")"
    PKG_TYPE="$(python3 -c "import json, sys; print(json.loads(sys.argv[1])['type'])" "$PKG_DATA")"
    PL_PATH="$(python3 -c "import json, sys; print(json.loads(sys.argv[1])['pl_path'])" "$PKG_DATA")"
    EN_PATH="$(python3 -c "import json, sys; print(json.loads(sys.argv[1])['en_path'])" "$PKG_DATA")"
    NEED_PL="$(python3 -c "import json, sys; print(str(json.loads(sys.argv[1])['need_pl']).lower())" "$PKG_DATA")"
    NEED_EN="$(python3 -c "import json, sys; print(str(json.loads(sys.argv[1])['need_en']).lower())" "$PKG_DATA")"
    REUSED_MSG_ID="$(python3 -c "import json, sys; print(json.loads(sys.argv[1])['reused_msg_id'])" "$PKG_DATA")"

    CURRENT_STAGE="Przetwarzanie pakietu [$PACKAGE_NUM/$TOTAL_PACKAGES]: $PKG_KEY"

    MESSAGE_ID="$REUSED_MSG_ID"

    if [ -n "$MESSAGE_ID" ]; then
        echo "==> [$PACKAGE_NUM/$TOTAL_PACKAGES] Wykryto istniejący message_id ($MESSAGE_ID) w parze dla $PKG_KEY. Pomijam nowe żądanie POST."
    else
        # Anti-Flood Protection: sztywna pauza 3.5s przed kolejnym żądaniem POST do Telegram API
        if [ "$idx" -gt 0 ]; then
            sleep 3.5
        fi

        # Przygotowanie sformatowanego payloadu JSON w UTF-8 z obsługą BASE_URL jako fallback
        PAYLOAD_FILE="$(mktemp)"
        CANONICAL_PRIMARY_URL=""

        CANONICAL_PRIMARY_URL="$(python3 -c '
import sys, os, re, html, json
from html import unescape

payload_path = sys.argv[1]
chat_id = sys.argv[2]
pkg_type = sys.argv[3]
pl_path = sys.argv[4]
en_path = sys.argv[5]
base_url = sys.argv[6]

def parse_article(path, default_base):
    if not path or not os.path.isfile(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    t_m = re.search(r"<title>(.*?)</title>", content, re.IGNORECASE | re.DOTALL)
    raw_t = t_m.group(1).strip() if t_m else ""
    raw_title = re.sub(r"\s*\|\s*The Reverse Emo Changeling.*$", "", raw_t, flags=re.IGNORECASE).strip()
    title = html.escape(unescape(raw_title), quote=True)

    d_m = re.search(r"<meta\s+name=[\"'"'"']description[\"'"'"']\s+content=[\"'"'"'](.*?)[\"'"'"']", content, re.IGNORECASE | re.DOTALL)
    raw_lead = d_m.group(1).strip() if d_m else ""
    desc = html.escape(unescape(raw_lead), quote=True)

    c_m = re.search(r"<link\s+rel=[\"'"'"']canonical[\"'"'"']\s+href=[\"'"'"'](.*?)[\"'"'"']", content, re.IGNORECASE)
    canonical_url = c_m.group(1).strip() if c_m else ""

    # Użycie BASE_URL jako bezpiecznego fallbacku przy braku taga canonical
    if not canonical_url:
        rel_match = re.search(r"(pl|en)/[0-9]+-[0-9]{4}/[^/]+\.html$", path.replace("\\", "/"))
        rel_path = rel_match.group(0) if rel_match else os.path.basename(path)
        clean_base = default_base.rstrip("/")
        canonical_url = f"{clean_base}/{rel_path}"

    return {"title": title, "desc": desc, "url": canonical_url}

pl_info = parse_article(pl_path, base_url)
en_info = parse_article(en_path, base_url)

if pkg_type == "PAIR" and pl_info and en_info:
    s_t_pl = pl_info["title"]
    s_d_pl = pl_info["desc"]
    s_u_pl = html.escape(pl_info["url"], quote=True)

    s_t_en = en_info["title"]
    s_d_en = en_info["desc"]
    s_u_en = html.escape(en_info["url"], quote=True)

    header_pl = f"🇵🇱 <b>{s_t_pl}</b>"
    link_pl = f"🔗 <a href=\"{s_u_pl}\">Czytaj po polsku</a>"

    header_en = f"🇬🇧 <b>{s_t_en}</b>"
    link_en = f"🔗 <a href=\"{s_u_en}\">Read in English</a>"

    overhead = len(header_pl) + len(link_pl) + len(header_en) + len(link_en) + 20
    max_desc_total = 3500 - overhead

    desc_total = len(s_d_pl) + len(s_d_en)
    if desc_total > max_desc_total and desc_total > 0:
        ratio_pl = len(s_d_pl) / desc_total
        target_pl = max(50, int(max_desc_total * ratio_pl) - 3)
        target_en = max(50, (max_desc_total - target_pl) - 6)
        if len(s_d_pl) > target_pl:
            s_d_pl = s_d_pl[:target_pl].rsplit(" ", 1)[0] + "..."
        if len(s_d_en) > target_en:
            s_d_en = s_d_en[:target_en].rsplit(" ", 1)[0] + "..."

    msg = f"{header_pl}\n{s_d_pl}\n{link_pl}\n\n{header_en}\n{s_d_en}\n{link_en}"
    primary_url = pl_info["url"]

elif pl_info:
    s_t = pl_info["title"]
    s_d = pl_info["desc"]
    s_u = html.escape(pl_info["url"], quote=True)
    header = f"<b>{s_t}</b>"
    link = f"🔗 <a href=\"{s_u}\">Czytaj artykuł</a>"
    overhead = len(header) + len(link) + 20
    max_desc = 3500 - overhead
    if len(s_d) > max_desc:
        s_d = s_d[:max_desc].rsplit(" ", 1)[0] + "..."
    msg = f"{header}\n\n{s_d}\n\n{link}"
    primary_url = pl_info["url"]

elif en_info:
    s_t = en_info["title"]
    s_d = en_info["desc"]
    s_u = html.escape(en_info["url"], quote=True)
    header = f"<b>{s_t}</b>"
    link = f"🔗 <a href=\"{s_u}\">Read article</a>"
    overhead = len(header) + len(link) + 20
    max_desc = 3500 - overhead
    if len(s_d) > max_desc:
        s_d = s_d[:max_desc].rsplit(" ", 1)[0] + "..."
    msg = f"{header}\n\n{s_d}\n\n{link}"
    primary_url = en_info["url"]

else:
    sys.exit(1)

payload = {
    "chat_id": chat_id,
    "text": msg,
    "parse_mode": "HTML",
    "disable_web_page_preview": False
}

with open(payload_path, "w", encoding="utf-8") as f:
    json.dump(payload, f, ensure_ascii=False)

print(primary_url)
' "$PAYLOAD_FILE" "$TG_CHAT_ID" "$PKG_TYPE" "$PL_PATH" "$EN_PATH" "$BASE_URL")"


        # Wysyłka do Telegram Bot API z ochroną przed HTTP 429 i mechanizmem ponawiania (do 3 prób)
        MAX_ATTEMPTS=3
        ATTEMPT=1
        SEND_SUCCESS=false

        while [ "$ATTEMPT" -le "$MAX_ATTEMPTS" ]; do
            set +e
            TG_RESPONSE=$(curl -sS --max-time 20 -X POST "https://api.telegram.org/bot${TG_BOT_TOKEN}/sendMessage" \
                -H "Content-Type: application/json; charset=utf-8" \
                --data-binary @"$PAYLOAD_FILE" 2>&1)
            CURL_STATUS=$?
            set -e

            if [ "$CURL_STATUS" -ne 0 ]; then
                echo >&2 "[BŁĄD] curl zgłosił błąd połączenia z Telegram API (kod $CURL_STATUS): $(mask_secret "$TG_RESPONSE")"
                if [ "$ATTEMPT" -lt "$MAX_ATTEMPTS" ]; then
                    echo "    Ponawiam próbę za 5 sekund (próba $((ATTEMPT + 1))/$MAX_ATTEMPTS)..."
                    sleep 5
                    ATTEMPT=$((ATTEMPT + 1))
                    continue
                else
                    rm -f "$PAYLOAD_FILE"
                    exit 1
                fi
            fi

            # Analiza odpowiedzi JSON
            PARSE_RESULT=$(python3 -c '
import json, sys
try:
    resp = json.loads(sys.argv[1])
    ok = resp.get("ok", False)
    err_code = resp.get("error_code", 0)
    retry_after = resp.get("parameters", {}).get("retry_after", 0)
    desc = resp.get("description", "")
    msg_id = resp.get("result", {}).get("message_id", "")
    print(json.dumps({
        "ok": bool(ok),
        "error_code": int(err_code),
        "retry_after": int(retry_after),
        "description": str(desc),
        "message_id": str(msg_id)
    }))
except Exception as e:
    print(json.dumps({
        "ok": False,
        "error_code": 0,
        "retry_after": 0,
        "description": f"Nieprawidłowy JSON: {e}",
        "message_id": ""
    }))
' "$TG_RESPONSE")

            IS_OK=$(python3 -c "import json, sys; print(str(json.loads(sys.argv[1])['ok']).lower())" "$PARSE_RESULT")
            ERR_CODE=$(python3 -c "import json, sys; print(json.loads(sys.argv[1])['error_code'])" "$PARSE_RESULT")
            RETRY_AFTER=$(python3 -c "import json, sys; print(json.loads(sys.argv[1])['retry_after'])" "$PARSE_RESULT")
            ERR_DESC=$(python3 -c "import json, sys; print(json.loads(sys.argv[1])['description'])" "$PARSE_RESULT")
            PARSED_MSG_ID=$(python3 -c "import json, sys; print(json.loads(sys.argv[1])['message_id'])" "$PARSE_RESULT")

            # Obsługa Telegram Rate-Limit HTTP 429
            if [ "$ERR_CODE" -eq 429 ] || [ "$RETRY_AFTER" -gt 0 ]; then
                RETRY_WAIT=$((RETRY_AFTER + 1))
                [ "$RETRY_WAIT" -le 1 ] && RETRY_WAIT=5
                echo >&2 "[RATE-LIMIT] Telegram API zgłosiło HTTP 429. Oczekiwanie ${RETRY_WAIT}s przed ponowieniem (próba $ATTEMPT/$MAX_ATTEMPTS)..."
                sleep "$RETRY_WAIT"
                ATTEMPT=$((ATTEMPT + 1))
                continue
            fi

            if [ "$IS_OK" = "true" ] && [[ "$PARSED_MSG_ID" =~ ^[0-9]+$ ]]; then
                MESSAGE_ID="$PARSED_MSG_ID"
                SEND_SUCCESS=true
                break
            fi

            echo >&2 "[BŁĄD] Telegram API odrzuciło żądanie dla $PKG_KEY: $ERR_DESC"
            if [ "$ATTEMPT" -lt "$MAX_ATTEMPTS" ]; then
                echo "    Ponawiam próbę za 5 sekund (próba $((ATTEMPT + 1))/$MAX_ATTEMPTS)..."
                sleep 5
                ATTEMPT=$((ATTEMPT + 1))
            else
                rm -f "$PAYLOAD_FILE"
                exit 1
            fi
        done

        rm -f "$PAYLOAD_FILE"

        if [ "$SEND_SUCCESS" = false ] || [ -z "$MESSAGE_ID" ]; then
            echo >&2 "[BŁĄD KRYTYCZNY] Publikacja wpisu nie powiodła się dla $PKG_KEY po $MAX_ATTEMPTS próbach."
            exit 1
        fi
    fi

    # Funkcja atomowego wstrzyknięcia ramki dyskusji do pojedynczego pliku
    inject_iframe() {
        local file="$1"
        local lang="$2"
        python3 -c '
import sys, re

path = sys.argv[1]
placeholder = sys.argv[2]
channel = sys.argv[3]
msg_id = sys.argv[4]
lang = sys.argv[5]
anchor = sys.argv[6]

widget_html = (
    f"<div translate=\"no\" class=\"notranslate\" style=\"margin-top: 35px; width: 100%; "
    f"border: var(--border-pink, 1px dashed #ff007f); background: #000; padding: 10px; min-height: 200px;\">\n"
    f"  <script async src=\"https://telegram.org/js/telegram-widget.js?22\" "
    f"data-telegram-discussion=\"{channel}/{msg_id}\" data-comments-limit=\"10\" data-color=\"FF007F\" data-dark=\"1\" data-telegram-login=\"Emosyfybot\"></script>\n"
    f"</div>"
)

with open(path, "r", encoding="utf-8") as f:
    data = f.read()

# Zapewnienie atrybutu lang w elemencie <article>
if re.search(r"<article\b", data, re.IGNORECASE) and not re.search(r"<article[^>]*\blang=", data, re.IGNORECASE):
    data = re.sub(r"<article([ >])", rf"<article lang=\"{lang}\"\1", data, count=1, flags=re.IGNORECASE)

# Sprawdzenie obecności widgetu z tym message_id
if re.search(rf"""(?:data-telegram-discussion=[\"\x27](?:{re.escape(channel)}|emochangeling)/{re.escape(msg_id)}[\"\x27]|<iframe[^>]+src=[\"\x27]https://t\.me/(?:{re.escape(channel)}|emochangeling)/{re.escape(msg_id)})""", data, re.IGNORECASE):
    pass
elif placeholder in data:
    data = data.replace(placeholder, widget_html, 1)
else:
    pattern = re.compile(rf"^([ \t]*){re.escape(anchor)}", re.MULTILINE)
    m = pattern.search(data)
    if not m:
        sys.stderr.write(f"[BŁĄD KRYTYCZNY] Nie odnaleziono kotwicy ani markera w {path}.\n")
        sys.exit(1)
    indent = m.group(1)
    replacement = f"{indent}{widget_html}\n\n{indent}{anchor}"
    data = data[:m.start()] + replacement + data[m.end():]

with open(path, "w", encoding="utf-8", newline="\n") as f:
    f.write(data)
' "$file" "$WIDGET_PLACEHOLDER" "$TG_CHANNEL_NAME" "$MESSAGE_ID" "$lang" "$WIDGET_ANCHOR"
    }

    ACTION_SUMMARY=""

    if [ "$NEED_PL" = "true" ] && [ -n "$PL_PATH" ]; then
        inject_iframe "$PL_PATH" "pl"
        MODIFIED_ARTICLES+=("$PL_PATH")
        ACTION_SUMMARY="PL"
    fi

    if [ "$NEED_EN" = "true" ] && [ -n "$EN_PATH" ]; then
        inject_iframe "$EN_PATH" "en"
        MODIFIED_ARTICLES+=("$EN_PATH")
        if [ -n "$ACTION_SUMMARY" ]; then
            ACTION_SUMMARY="PL i EN"
        else
            ACTION_SUMMARY="EN"
        fi
    fi

    if [ "$PKG_TYPE" = "PAIR" ]; then
        echo "[Para $PACKAGE_NUM/$TOTAL_PACKAGES] Sukces dla $PKG_KEY (message_id: $MESSAGE_ID) -> wdrożono w $ACTION_SUMMARY"
    else
        echo "[Artykuł $PACKAGE_NUM/$TOTAL_PACKAGES] Sukces dla $PKG_KEY (message_id: $MESSAGE_ID) -> wdrożono w $ACTION_SUMMARY"
    fi

    # Wyznaczenie ostatniego adresu kanonicznego do weryfikacji HTTP Polling
    LAST_MESSAGE_ID="$MESSAGE_ID"
    TARGET_VERIFY_FILE="${PL_PATH:-$EN_PATH}"
    LAST_CANONICAL_URL="$(python3 -c '
import sys, re
with open(sys.argv[1], "r", encoding="utf-8") as f:
    c = f.read()
m = re.search(r"<link\s+rel=[\"'"'"']canonical[\"'"'"']\s+href=[\"'"'"'](.*?)[\"'"'"']", c, re.IGNORECASE)
print(m.group(1).strip() if m else "")
' "$TARGET_VERIFY_FILE")"

done

TOTAL_MODIFIED=${#MODIFIED_ARTICLES[@]}

# ==============================================================================
# 5. FINALIZACJA, PODPISYWANIE GPG I POJEDYNCZY ZBIORCZY COMMIT GIT
# ==============================================================================

CURRENT_STAGE="Regeneracja kanałów RSS"
echo "==> Regeneracja kanałów RSS (generate_rss.py)..."
python3 "$RSS_SCRIPT"

CURRENT_STAGE="Podpisywanie kryptograficzne GPG (klucz $GPG_KEY_ID)"
echo "==> Podpisywanie zmienionych plików HTML kluczem GPG $GPG_KEY_ID..."

for p_file in "${MODIFIED_ARTICLES[@]}"; do
    "$GPG_BIN" --batch --yes --detach-sign -a -u "$GPG_KEY_ID" "$p_file"
done

echo "==> Podpisywanie zaktualizowanych kanałów RSS..."
for r_file in "$RSS_FILE_DEFAULT" "$RSS_FILE_PL" "$RSS_FILE_EN"; do
    if [ -f "$r_file" ]; then
        "$GPG_BIN" --batch --yes --detach-sign -a -u "$GPG_KEY_ID" "$r_file"
    fi
done

CURRENT_STAGE="Pojedynczy zbiorczy commit Git"
echo "==> Staging zmodyfikowanych artykułów oraz kanałów RSS..."

for p_file in "${MODIFIED_ARTICLES[@]}"; do
    git -C "$REPO_ROOT" add "$p_file"
    if [ -f "${p_file}.asc" ]; then
        git -C "$REPO_ROOT" add "${p_file}.asc"
    fi
done

for r_file in "$RSS_FILE_DEFAULT" "$RSS_FILE_PL" "$RSS_FILE_EN"; do
    if [ -f "$r_file" ]; then
        git -C "$REPO_ROOT" add "$r_file"
        if [ -f "${r_file}.asc" ]; then
            git -C "$REPO_ROOT" add "${r_file}.asc"
        fi
    fi
done

if ! git -C "$REPO_ROOT" diff --staged --quiet; then
    COMMIT_MSG="chore(discussion): masowe powiązanie dyskusji Telegram dla ${TOTAL_MODIFIED} artykułów [backfill]"
    echo "==> Tworzenie pojedynczego zbiorczego commita Git:"
    echo "    $COMMIT_MSG"
    git -C "$REPO_ROOT" commit -m "$COMMIT_MSG"

    CURRENT_STAGE="Wypchnięcie zmian do repozytorium zdalnego (git push)"
    echo "==> Wypychanie zmian do aktywnej gałęzi $CURRENT_BRANCH..."
    git -C "$REPO_ROOT" push origin "$CURRENT_BRANCH"
else
    echo "    Informacja: Brak zmian w indeksie Git (nothing to commit)."
fi

# ==============================================================================
# 6. ASYNCHRONICZNY HTTP POLLING KOŃCOWY
# ==============================================================================

poll_http_endpoint() {
    local url="$1"
    local expected_text="$2"
    local max_attempts=15
    local delay=5
    local attempt=1

    echo "==> Rozpoczynam HTTP Polling weryfikujący wdrożenie na produkcji: $url"
    while [ "$attempt" -le "$max_attempts" ]; do
        echo "    [Próba $attempt/$max_attempts] Sprawdzanie dostępności ramki dyskusji w sieci..."
        
        local response_body
        local http_code
        response_body=$(curl -sSL --max-time 10 "$url" 2>/dev/null || true)
        http_code=$(curl -sSL -o /dev/null -w "%{http_code}" --max-time 10 "$url" 2>/dev/null || true)

        if [ "$http_code" = "200" ]; then
            if [ -n "$expected_text" ]; then
                if echo "$response_body" | grep -q -F "$expected_text"; then
                    echo "    -> Sukces: Kod 200 OK oraz odnaleziono sygnaturę ramki dyskusji w sieci."
                    return 0
                else
                    echo "    -> Kod 200 OK, oczekiwanie na odświeżenie cache Cloudflare..."
                fi
            else
                echo "    -> Sukces: Kod 200 OK."
                return 0
            fi
        else
            echo "    -> Kod odpowiedzi HTTP: $http_code (oczekiwano 200)."
        fi

        sleep "$delay"
        attempt=$((attempt + 1))
    done

    echo >&2 "[BŁĄD] Przekroczono limit czasu oczekiwania na synchronizację ramki pod adresem: $url"
    return 1
}

CURRENT_STAGE="Końcowy HTTP Polling dla ostatniego przetworzonego artykułu"
if [ -n "$LAST_CANONICAL_URL" ] && [ -n "$LAST_MESSAGE_ID" ]; then
    EXPECTED_IFRAME_SIGNATURE="t.me/${TG_CHANNEL_NAME}/${LAST_MESSAGE_ID}"
    echo "==> Weryfikacja końcowa wdrożenia ramki dyskusyjnej dla ostatniego artykułu..."
    poll_http_endpoint "$LAST_CANONICAL_URL" "$EXPECTED_IFRAME_SIGNATURE"
fi

echo "=============================================================================="
echo "==> Masowa migracja dwujęzycznych par dyskusyjnych zakończona pełnym sukcesem!"
echo "    Przetworzone pakiety:   $TOTAL_PACKAGES"
echo "    Zmodyfikowane artykuły: $TOTAL_MODIFIED"
echo "    Ostatni artykuł:        $LAST_CANONICAL_URL"
echo "    Ostatnia dyskusja:      https://t.me/${TG_CHANNEL_NAME}/${LAST_MESSAGE_ID}"
echo "=============================================================================="
