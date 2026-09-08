#!/usr/bin/env bash
# ==============================================================================
# Skrypt: antigravity_tg_push.sh
# Rola: Automatyzacja publikacji artykułów w ekosystemie The Reverse Emo Changeling
# Standard: Idempotencja, Two-Phase State Machine, Secret Masking, Clean Git Staging
# ==============================================================================

set -Eeuo pipefail
export PYTHONIOENCODING=utf-8

# Kontekst etapu wykonania do bezpiecznego logowania w pułapce ERR
CURRENT_STAGE="Inicjalizacja środowiska i preflight"

# Bezpieczny trap ERR: raportuje numer linii i nazwę etapu, CAŁKOWICIE bez $BASH_COMMAND (ochrona tokena Telegrama)
trap 'echo >&2 "[FATAL ERR] Awaria w linii $LINENO podczas etapu: '\''$CURRENT_STAGE'\''. Przerywam procedurę."' ERR

# Wybór binarnego gpg z priorytetem dla natywnej instalacji Windows GnuPG
GPG_BIN="gpg"
if [ -x "/c/Program Files/GnuPG/bin/gpg.exe" ]; then
    GPG_BIN="/c/Program Files/GnuPG/bin/gpg.exe"
elif [ -x "/c/Program Files (x86)/GnuPG/bin/gpg.exe" ]; then
    GPG_BIN="/c/Program Files (x86)/GnuPG/bin/gpg.exe"
fi

# ==============================================================================
# 1. RYGOR ŚRODOWISKA I PREFLIGHT
# ==============================================================================

CURRENT_STAGE="Weryfikacja narzędzi systemowych"
for cmd in git curl jq python3 "$GPG_BIN"; do
    if ! command -v "$cmd" &> /dev/null; then
        echo >&2 "[BŁĄD] Wymagane narzędzie '$cmd' nie jest zainstalowane w systemie."
        exit 1
    fi
done

# Weryfikacja argumentów wejściowych
if [ $# -lt 1 ]; then
    echo "Użycie: $0 <ścieżka_do_pliku_artykulu.html>"
    echo "Przykład: $0 MAGAZINE/pl/1-2026/historia-emo-scene-w-5-minut.html"
    exit 1
fi

INPUT_FILE="$1"

CURRENT_STAGE="Weryfikacja środowiska Git"
if ! git rev-parse --is-inside-work-tree &> /dev/null; then
    echo >&2 "[BŁĄD] Bieżący katalog nie znajduje się wewnątrz repozytorium Git."
    exit 1
fi

REPO_ROOT="$(git rev-parse --show-toplevel)"
CURRENT_BRANCH="$(git rev-parse --abbrev-ref HEAD)"

if [ -z "$CURRENT_BRANCH" ] || [ "$CURRENT_BRANCH" = "HEAD" ]; then
    echo >&2 "[BŁĄD] Brak aktywnej gałęzi Git (detatched HEAD)."
    exit 1
fi

if ! git remote get-url origin &> /dev/null; then
    echo >&2 "[BŁĄD] Remote 'origin' nie jest skonfigurowany w repozytorium."
    exit 1
fi

# Ochrona przed zanieczyszczeniem commita: weryfikacja czystości indeksu stagingu
git diff --cached --quiet || (echo >&2 "[BŁĄD] W indeksie Git (staging) znajdują się już inne zmiany. Oczyść staging przed uruchomieniem publikacji." && exit 1)

CURRENT_STAGE="Weryfikacja prywatnego klucza kryptograficznego GPG"
GPG_KEY_ID="$(git config user.signingkey || true)"
if [ -z "$GPG_KEY_ID" ]; then
    echo >&2 "[BŁĄD] Git nie ma skonfigurowanego klucza podpisywania (user.signingkey)."
    exit 1
fi

if ! "$GPG_BIN" --batch --list-secret-keys "$GPG_KEY_ID" &> /dev/null; then
    echo >&2 "[BŁĄD KRYTYCZNY] Prywatny klucz GPG $GPG_KEY_ID (secret key) nie został odnaleziony w pęku kluczy ($GPG_BIN)."
    exit 1
fi

CURRENT_STAGE="Weryfikacja ścieżki artykułu"
ARTICLE_ABS="$(python3 -c 'import os, sys; print(os.path.abspath(sys.argv[1]))' "$INPUT_FILE")"

if [ ! -f "$ARTICLE_ABS" ]; then
    echo >&2 "[BŁĄD] Wskazany plik artykułu nie istnieje: $INPUT_FILE ($ARTICLE_ABS)"
    exit 1
fi

ARTICLE_REL="$(python3 -c 'import os, sys; print(os.path.relpath(sys.argv[1], sys.argv[2]).replace("\\", "/"))' "$ARTICLE_ABS" "$REPO_ROOT")"

if [[ ! "$ARTICLE_REL" =~ MAGAZINE/(pl|en)/[0-9]+-[0-9]{4}/[^/]+\.html$ ]]; then
    echo >&2 "[BŁĄD] Ścieżka artykułu '$ARTICLE_REL' nie pasuje do dozwolonej struktury wydań: MAGAZINE/(pl|en)/<nr>-<rok>/<nazwa>.html"
    exit 1
fi

CURRENT_STAGE="Bezpieczny odczyt konfiguracji środowiskowej"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_PATH=""
if [ -f "$SCRIPT_DIR/.env" ]; then
    ENV_PATH="$SCRIPT_DIR/.env"
elif [ -f "$REPO_ROOT/.env" ]; then
    ENV_PATH="$REPO_ROOT/.env"
fi

# Bezpieczny odczyt wartości bez wykonywania kodu powłoki (brak source $ENV_PATH)
# Odporny na znaki powrotu karetki \r (CRLF Windows), cudzysłowy oraz białe znaki
TG_BOT_TOKEN="${TG_BOT_TOKEN:-}"
TG_CHAT_ID="${TG_CHAT_ID:-}"

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
        # Usunięcie nazwy zmiennej i znaku równości
        val="${line#*=}"
        # Usunięcie komentarzy rozpoczynających się od niezacytowanego #
        val=$(echo "$val" | sed -E 's/[[:space:]]+#.*$//')
        # Usunięcie powrotu karetki \r (CRLF) oraz wiodących/kończących spacji
        val=$(echo "$val" | tr -d '\r' | sed -E 's/^[[:space:]]+//; s/[[:space:]]+$//')
        # Usunięcie opcjonalnych otaczających cudzysłowów "..." lub '...'
        if [[ "$val" =~ ^\"(.*)\"$ ]] || [[ "$val" =~ ^\'(.*)\'$ ]]; then
            val="${BASH_REMATCH[1]}"
            val=$(echo "$val" | sed -E 's/^[[:space:]]+//; s/[[:space:]]+$//')
        fi
        echo "$val"
    fi
}

if [ -n "$ENV_PATH" ]; then
    if [ -z "$TG_BOT_TOKEN" ]; then
        TG_BOT_TOKEN=$(parse_env_var "$ENV_PATH" "TG_BOT_TOKEN")
    fi
    if [ -z "$TG_CHAT_ID" ]; then
        TG_CHAT_ID=$(parse_env_var "$ENV_PATH" "TG_CHAT_ID")
    fi
fi

# Oczyszczenie wartości pochodzących ze środowiska systemowego z \r i spacji
TG_BOT_TOKEN=$(echo "$TG_BOT_TOKEN" | tr -d '\r' | sed -E 's/^[[:space:]]+//; s/[[:space:]]+$//')
TG_CHAT_ID=$(echo "$TG_CHAT_ID" | tr -d '\r' | sed -E 's/^[[:space:]]+//; s/[[:space:]]+$//')

TG_CHAT_ID="${TG_CHAT_ID:-@emochangeling}"
TG_CHANNEL_NAME="${TG_CHAT_ID#@}"
BASE_URL="https://reverse.emo-changeling.xyz"

if [ -z "$TG_BOT_TOKEN" ]; then
    echo >&2 "[BŁĄD] Zmienna TG_BOT_TOKEN nie została zdefiniowana lub jest pusta po oczyszczeniu."
    exit 1
fi

CURRENT_STAGE="Preflight test generatora RSS"
RSS_SCRIPT=""
if [ -f "$SCRIPT_DIR/generate_rss.py" ]; then
    RSS_SCRIPT="$SCRIPT_DIR/generate_rss.py"
elif [ -f "$REPO_ROOT/MAGAZINE/generate_rss.py" ]; then
    RSS_SCRIPT="$REPO_ROOT/MAGAZINE/generate_rss.py"
elif [ -f "$REPO_ROOT/scripts/generate_rss.py" ]; then
    RSS_SCRIPT="$REPO_ROOT/scripts/generate_rss.py"
else
    echo >&2 "[BŁĄD] Nie znaleziono generatora RSS (generate_rss.py)."
    exit 1
fi

python3 -m py_compile "$RSS_SCRIPT"

RSS_DIR="$(dirname "$RSS_SCRIPT")"
RSS_FILE_DEFAULT="$RSS_DIR/rss.xml"
RSS_FILE_PL="$RSS_DIR/rss-pl.xml"
RSS_FILE_EN="$RSS_DIR/rss-en.xml"

for item in "$RSS_FILE_DEFAULT" "$RSS_FILE_PL" "$RSS_FILE_EN"; do
    if git status --porcelain "$item" 2>/dev/null | grep -q .; then
        echo >&2 "[BŁĄD] Plik RSS '$item' posiada niezatwierdzone zmiany przed startem procedury."
        exit 1
    fi
done

# ==============================================================================
# 2. DWUETAPOWA MASZYNA STANÓW (TWO-PHASE STATE) & STRUKTURA ARTYKUŁU
# ==============================================================================

CURRENT_STAGE="Weryfikacja maszyny stanów (.state)"
ARTICLE_BASENAME="$(basename "$ARTICLE_ABS" .html)"
STATE_FILE="$SCRIPT_DIR/.state_${ARTICLE_BASENAME}.json"

RESUMING_STATE=false
RESUMED_MSG_ID=""

if [ -f "$STATE_FILE" ]; then
    echo "==> Znaleziono plik stanu: $STATE_FILE"
    CURRENT_PHASE=$(jq -r '.phase // empty' "$STATE_FILE" 2>/dev/null || true)

    if [ "$CURRENT_PHASE" = "telegram_sent" ]; then
        if jq -e '.message_id and (.message_id | type == "number")' "$STATE_FILE" >/dev/null 2>&1; then
            RESUMING_STATE=true
            RESUMED_MSG_ID="$(jq -r '.message_id' "$STATE_FILE")"
            echo "    [STAN] Wykryto stan 'telegram_sent'. Wznawianie procedury dla message_id: $RESUMED_MSG_ID."
        else
            echo >&2 "[BŁĄD] Plik stanu $STATE_FILE deklaruje stan 'telegram_sent', ale pole message_id jest nieprawidłowe."
            exit 1
        fi
    elif [ "$CURRENT_PHASE" = "telegram_send_started" ]; then
        echo >&2 "=================================================================================="
        echo >&2 "[KRYTYCZNY BŁĄD INTEGRACJI] Wykryto stan 'telegram_send_started' bez potwierdzenia!"
        echo >&2 "Poprzednie żądanie HTTP mogło dotrzeć do serwerów Telegrama (np. timeout lub błąd sieci)."
        echo >&2 "Aby uniknąć zaspamowania kanału $TG_CHAT_ID duplikatem artykułu:"
        echo >&2 "1. Zweryfikuj ręcznie na kanale Telegram, czy post z tym artykułem został opublikowany."
        echo >&2 "2. Jeśli TAK: uzupełnij plik $STATE_FILE o parametr 'message_id': <numer> i 'phase': 'telegram_sent'."
        echo >&2 "3. Jeśli NIE: usuń plik $STATE_FILE i uruchom skrypt ponownie."
        echo >&2 "=================================================================================="
        exit 1
    else
        echo >&2 "[BŁĄD] Plik stanu $STATE_FILE zawiera nieznaną lub uszkodzoną fazę: '$CURRENT_PHASE'."
        exit 1
    fi
fi

CURRENT_STAGE="Walidacja struktury HTML i pozycjonowanie znacznika dyskusji"
WIDGET_PLACEHOLDER="<!-- TELEGRAM_WIDGET_HERE -->"
WIDGET_ANCHOR="<!-- Navigation Links and License under Article -->"

# Pozycjonowanie i walidacja obecności znacznika dyskusji
if [ "$RESUMING_STATE" = false ]; then
    PLACEHOLDER_COUNT=$(grep -c -F "$WIDGET_PLACEHOLDER" "$ARTICLE_ABS" || true)

    if [ "$PLACEHOLDER_COUNT" -eq 1 ]; then
        echo "    Znacznik dyskusji '$WIDGET_PLACEHOLDER' jest już obecny w artykule."
    elif [ "$PLACEHOLDER_COUNT" -gt 1 ]; then
        echo >&2 "[BŁĄD] Znaleziono zduplikowany znacznik '$WIDGET_PLACEHOLDER' w artykule (liczba: $PLACEHOLDER_COUNT). Dozwolony jest maksymalnie jeden znacznik."
        exit 1
    else
        # Weryfikacja unikalności kotwicy nawigacji przed wstrzyknięciem
        ANCHOR_COUNT=$(grep -c -F "$WIDGET_ANCHOR" "$ARTICLE_ABS" || true)

        if [ "$ANCHOR_COUNT" -ne 1 ]; then
            echo >&2 "[BŁĄD] Kotwica '$WIDGET_ANCHOR' musi występować DOKŁADNIE JEDEN RAZ w pliku artykułu (znaleziono: $ANCHOR_COUNT). Przerywam procedurę przed operacjami Git i Telegram API."
            exit 1
        fi

        # Wstrzyknięcie dokładnie jednego znacznika bezpośrednio przed kotwicą z zachowaniem wcięcia
        echo "==> Wstrzykiwanie znacznika '$WIDGET_PLACEHOLDER' bezpośrednio przed kotwicą..."
        python3 -c '
import sys, re

path = sys.argv[1]
placeholder = sys.argv[2]
anchor = sys.argv[3]

with open(path, "r", encoding="utf-8") as f:
    content = f.read()

pattern = re.compile(rf"^([ \t]*){re.escape(anchor)}", re.MULTILINE)
matches = list(pattern.finditer(content))
if len(matches) != 1:
    sys.stderr.write(f"[BŁĄD] Kotwica musi występować dokładnie jeden raz w pliku (znaleziono: {len(matches)}).\n")
    sys.exit(1)

m = matches[0]
indent = m.group(1)
replacement = f"{indent}{placeholder}\n\n{indent}{anchor}"
new_content = content[:m.start()] + replacement + content[m.end():]

with open(path, "w", encoding="utf-8", newline="\n") as f:
    f.write(new_content)
' "$ARTICLE_ABS" "$WIDGET_PLACEHOLDER" "$WIDGET_ANCHOR"

        # Weryfikacja poprawności wstrzyknięcia
        VERIFY_COUNT=$(grep -c -F "$WIDGET_PLACEHOLDER" "$ARTICLE_ABS" || true)
        if [ "$VERIFY_COUNT" -ne 1 ]; then
            echo >&2 "[BŁĄD] Weryfikacja po wstrzyknięciu nie powiodła się. Liczba znaczników w pliku: $VERIFY_COUNT."
            exit 1
        fi
        echo "    Pomyślnie wstrzyknięto znacznik dyskusji przed kotwicą nawigacji."
    fi
else
    # Weryfikacja docelowej ramki iframe w trybie wznowienia ze stanu telegram_sent
    CURRENT_STAGE="Walidacja docelowej ramki iframe (tryb wznowienia)"
    EXPECTED_IFRAME_TARGET="t.me/${TG_CHANNEL_NAME}/${RESUMED_MSG_ID}"
    if ! grep -q "$EXPECTED_IFRAME_TARGET" "$ARTICLE_ABS"; then
        echo >&2 "[BŁĄD] Tryb wznowienia: Artykuł nie posiada docelowej ramki iframe dla wiadomości $RESUMED_MSG_ID ($EXPECTED_IFRAME_TARGET)."
        exit 1
    fi
    echo "    [WZNOWIENIE] Pomyślnie zweryfikowano obecność docelowej ramki iframe dla wiadomości $RESUMED_MSG_ID."
fi

CURRENT_STAGE="Ekstrakcja metadanych artykułu"
IFS=$'\t' read -r TITLE DESCRIPTION LANG_DETECTED TARGET_URL < <(python3 -c '
import sys, re
from html import unescape

article_path = sys.argv[1]
default_base = sys.argv[2]
with open(article_path, "r", encoding="utf-8") as f:
    html = f.read()

# Tytuł
t_m = re.search(r"<title>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
title = t_m.group(1).strip() if t_m else "The Reverse Emo Changeling"
title = re.sub(r"\s*\|\s*The Reverse Emo Changeling.*$", "", title, flags=re.IGNORECASE).strip()

# Opis
d_m = re.search(r"<meta\s+name=[\"\x27]description[\"\x27]\s+content=[\"\x27](.*?)[\"\x27]", html, re.IGNORECASE | re.DOTALL)
desc = d_m.group(1).strip() if d_m else ""

# Wykrycie języka
lang = "pl"
if "/en/" in article_path.replace("\\", "/"):
    lang = "en"

# Bezpośredni odczyt kanonicznego adresu URL
c_m = re.search(r"<link\s+rel=[\"\x27]canonical[\"\x27]\s+href=[\"\x27](.*?)[\"\x27]", html, re.IGNORECASE)
if not c_m:
    c_m = re.search(r"<link\s+href=[\"\x27](.*?)[\"\x27]\s+rel=[\"\x27]canonical[\"\x27]", html, re.IGNORECASE)

if c_m:
    canonical_url = c_m.group(1).strip()
else:
    rel_match = re.search(r"(pl|en)/[0-9]+-[0-9]{4}/[^/]+\.html$", article_path.replace("\\", "/"))
    rel_path = rel_match.group(0) if rel_match else ""
    clean_base = default_base.rstrip("/")
    canonical_url = f"{clean_base}/{rel_path}" if rel_path else ""

print(f"{unescape(title)}\t{unescape(desc)}\t{lang}\t{canonical_url}")
' "$ARTICLE_ABS" "$BASE_URL")

if [ -z "$TARGET_URL" ]; then
    echo >&2 "[BŁĄD] Nie udało się wyznaczyć poprawnego adresu kanonicznego dla $ARTICLE_ABS"
    exit 1
fi

# Relatywna ścieżka do komunikatów commita
CANONICAL_PATH="${TARGET_URL#"${BASE_URL%/}/"}"
if [ "$CANONICAL_PATH" = "$TARGET_URL" ]; then
    CANONICAL_PATH="$ARTICLE_REL"
fi

# Wstrzyknij lang do <article>, jeśli brak
if grep -qi "<article" "$ARTICLE_ABS" && ! grep -qi "<article[^>]*lang=" "$ARTICLE_ABS"; then
    echo "==> Wstrzykiwanie atrybutu lang=\"$LANG_DETECTED\" do znacznika <article>..."
    python3 -c '
import sys, re
path, lang = sys.argv[1], sys.argv[2]
with open(path, "r", encoding="utf-8") as f:
    content = f.read()
content = re.sub(r"<article([ >])", rf"<article lang=\"{lang}\"\1", content, count=1, flags=re.IGNORECASE)
with open(path, "w", encoding="utf-8") as f:
    f.write(content)
' "$ARTICLE_ABS" "$LANG_DETECTED"
fi

echo "==> Przygotowano parametry publikacji:"
echo "    Tytuł:   $TITLE"
echo "    Język:   $LANG_DETECTED"
echo "    URL:     $TARGET_URL"

# ==============================================================================
# 3. KROK 1: PIERWSZY COMMIT, PUSH I ASYNCHRONICZNY HTTP POLLING
# ==============================================================================

# Funkcja HTTP Polling
poll_http_endpoint() {
    local url="$1"
    local expected_text="$2"
    local max_attempts=12
    local delay=5
    local attempt=1

    echo "==> Rozpoczynam HTTP Polling docelowego adresu URL: $url"
    while [ $attempt -le $max_attempts ]; do
        echo "    [Próba $attempt/$max_attempts] Sprawdzanie dostępności..."
        
        HTTP_RESPONSE=$(curl -sSL --max-time 10 "$url" 2>/dev/null || true)
        HTTP_CODE=$(curl -sSL -o /dev/null -w "%{http_code}" --max-time 10 "$url" 2>/dev/null || true)

        if [ "$HTTP_CODE" = "200" ]; then
            if [ -n "$expected_text" ]; then
                if echo "$HTTP_RESPONSE" | grep -q -F "$expected_text"; then
                    echo "    -> Sukces: Zwrócono kod 200 OK oraz odnaleziono oczekiwaną sygnaturę."
                    return 0
                else
                    echo "    -> Kod 200 OK, ale zawartość strony jeszcze się nie zsynchronizowała."
                fi
            else
                echo "    -> Sukces: Zwrócono kod 200 OK."
                return 0
            fi
        else
            echo "    -> Kod odpowiedzi HTTP: $HTTP_CODE (oczekiwano 200)."
        fi

        sleep $delay
        attempt=$((attempt + 1))
    done

    echo >&2 "[BŁĄD] Przekroczono limit czasu oczekiwania na publikację pod adresem: $url"
    return 1
}

if [ "$RESUMING_STATE" = false ]; then
    CURRENT_STAGE="KROK 1: Pierwszy commit i push do Git"
    echo "==> [KROK 1/3] Pierwszy commit i synchronizacja Git..."
    
    echo "    Podpisywanie GPG dla: $(basename "$ARTICLE_ABS")..."
    "$GPG_BIN" --batch --yes --detach-sign -a -u "$GPG_KEY_ID" "$ARTICLE_ABS"

    git add "$ARTICLE_ABS"
    if [ -f "${ARTICLE_ABS}.asc" ]; then
        git add "${ARTICLE_ABS}.asc"
    fi
    
    if ! git diff --staged --quiet; then
        git commit -S -m "feat(magazine): publikacja artykułu ${CANONICAL_PATH}"
        echo "    Wypychanie do gałęzi $CURRENT_BRANCH..."
        git push origin "$CURRENT_BRANCH"
    else
        echo "    Informacja: Plik artykułu jest już zatwierdzony (nothing to commit). Kontynuuję weryfikację sieciową."
    fi

    CURRENT_STAGE="KROK 1: Asynchroniczny HTTP Polling przed Telegramem"
    poll_http_endpoint "$TARGET_URL" "$TITLE"
fi

# ==============================================================================
# 4. KROK 2: TELEGRAM API, SANITYZACJA I ZAPIS FAZY DWUETAPOWEJ
# ==============================================================================

MESSAGE_ID=""

if [ "$RESUMING_STATE" = true ]; then
    MESSAGE_ID="$RESUMED_MSG_ID"
    echo "==> [KROK 2/3] Pomijanie wysyłki do Telegram API (odczytano message_id: $MESSAGE_ID z pliku stanu)."
else
    CURRENT_STAGE="KROK 2: Formatowanie wiadomości dla Telegram API"
    echo "==> [KROK 2/3] Przygotowanie i wysyłka posta na Telegram: $TG_CHAT_ID..."

    TG_MSG="$(python3 -c '
import sys, html
from html import unescape

title, desc, url, lang = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]

safe_title = html.escape(unescape(title), quote=True)
safe_desc = html.escape(unescape(desc), quote=True)
safe_url = html.escape(url, quote=True)

link_text = "Czytaj artykuł" if lang == "pl" else "Read article"

overhead = len(safe_title) + len(safe_url) + len(link_text) + 20
max_desc_len = 3500 - overhead
if len(safe_desc) > max_desc_len:
    safe_desc = safe_desc[:max_desc_len].rsplit(" ", 1)[0] + "..."

msg = f"<b>{safe_title}</b>\n\n{safe_desc}\n\n🔗 <a href=\"{safe_url}\">{link_text}</a>"
print(msg)
' "$TITLE" "$DESCRIPTION" "$TARGET_URL" "$LANG_DETECTED")"

    CURRENT_STAGE="KROK 2: Zapis stanu 'telegram_send_started'"
    TIMESTAMP_START="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
    cat << EOF > "$STATE_FILE"
{
  "article": "$ARTICLE_REL",
  "phase": "telegram_send_started",
  "canonical_url": "$TARGET_URL",
  "started_at": "$TIMESTAMP_START"
}
EOF

    CURRENT_STAGE="KROK 2: Wywołanie Telegram Bot API (sendMessage)"
    # Użycie curl z zamaskowanym tokenem w logach, z wyłączeniem wycieków w stderr
    set +e
    TG_RESPONSE=$(curl -sS --max-time 15 -X POST "https://api.telegram.org/bot${TG_BOT_TOKEN}/sendMessage" \
        --data-urlencode "chat_id=${TG_CHAT_ID}" \
        --data-urlencode "text=${TG_MSG}" \
        --data-urlencode "parse_mode=HTML" \
        --data-urlencode "disable_web_page_preview=false" 2>&1)
    CURL_STATUS=$?
    set -e

    if [ $CURL_STATUS -ne 0 ]; then
        echo >&2 "[BŁĄD] curl zgłosił błąd połączenia z Telegram API (kod $CURL_STATUS). Stan pozostał w fazie 'telegram_send_started'."
        exit 1
    fi

    IS_OK=$(echo "$TG_RESPONSE" | jq -r '.ok // false' 2>/dev/null || echo "false")

    if [ "$IS_OK" != "true" ]; then
        TG_ERR_DESC=$(echo "$TG_RESPONSE" | jq -r '.description // "Brak opisu błędu"' 2>/dev/null || echo "Nieprawidłowy JSON")
        echo >&2 "[BŁĄD] Telegram API odrzuciło żądanie: $TG_ERR_DESC"
        exit 1
    fi

    MESSAGE_ID=$(echo "$TG_RESPONSE" | jq -r '.result.message_id // empty')

    if [[ ! "$MESSAGE_ID" =~ ^[0-9]+$ ]]; then
        echo >&2 "[BŁĄD] Odebrano nieprawidłowy message_id z Telegram API: '$MESSAGE_ID'"
        exit 1
    fi

    CURRENT_STAGE="KROK 2: Zapis stanu 'telegram_sent'"
    TIMESTAMP_SENT="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
    cat << EOF > "$STATE_FILE"
{
  "article": "$ARTICLE_REL",
  "phase": "telegram_sent",
  "message_id": $MESSAGE_ID,
  "canonical_url": "$TARGET_URL",
  "published_at": "$TIMESTAMP_SENT"
}
EOF
    echo "==> Pomyślnie opublikowano wpis na Telegramie. message_id: $MESSAGE_ID"
    echo "    Zaktualizowano plik stanu do fazy 'telegram_sent'."
fi

# ==============================================================================
# 5. KROK 3: WSTRZYKNIĘCIE RAMKI DYSKUSYJNEJ (ZERO-BACKEND PRIVACY POLICY)
# ==============================================================================

CURRENT_STAGE="KROK 3: Wstrzykiwanie ramki dyskusyjnej do artykułu HTML"
echo "==> [KROK 3/3] Osadzanie ramki dyskusyjnej w artykule..."

if grep -q "$WIDGET_PLACEHOLDER" "$ARTICLE_ABS"; then
    python3 -c '
import sys

path = sys.argv[1]
placeholder = sys.argv[2]
channel = sys.argv[3]
msg_id = sys.argv[4]

widget_html = (
    f"<div translate=\"no\" class=\"notranslate\" style=\"margin-top: 35px; width: 100%; "
    f"border: var(--border-pink, 1px dashed #ff007f); background: #000; padding: 10px; min-height: 200px;\">\n"
    f"  <script async src=\"https://telegram.org/js/telegram-widget.js?22\" "
    f"data-telegram-discussion=\"{channel}/{msg_id}\" data-comments-limit=\"10\" data-color=\"FF007F\" data-dark=\"1\" data-telegram-login=\"Emosyfybot\"></script>\n"
    f"</div>"
)

with open(path, "r", encoding="utf-8") as f:
    data = f.read()

data = data.replace(placeholder, widget_html, 1)

with open(path, "w", encoding="utf-8") as f:
    f.write(data)
' "$ARTICLE_ABS" "$WIDGET_PLACEHOLDER" "$TG_CHANNEL_NAME" "$MESSAGE_ID"
    echo "    Wstrzyknięto widget dyskusyjny dla message_id $MESSAGE_ID."
else
    if grep -q -E "(data-telegram-discussion=[\"']${TG_CHANNEL_NAME}/${MESSAGE_ID}[\"']|t.me/${TG_CHANNEL_NAME}/${MESSAGE_ID})" "$ARTICLE_ABS"; then
        echo "    Widget dyskusyjny dla message_id $MESSAGE_ID jest już obecny w pliku."
    else
        echo >&2 "[BŁĄD] Nie znaleziono znacznika '$WIDGET_PLACEHOLDER' ani widgetu dla wiadomości $MESSAGE_ID."
        exit 1
    fi
fi


# ==============================================================================
# 6. REGENERACJA RSS, FINALNY COMMIT I WERYFIKACJA KOŃCOWA
# ==============================================================================

CURRENT_STAGE="Regeneracja kanałów RSS"
echo "==> Regeneracja kanałów RSS..."
python3 "$RSS_SCRIPT"

CURRENT_STAGE="KROK 3: Drugi commit i push do Git"
# Aktualizacja podpisu GPG artykułu oraz podpisanie kanałów RSS
echo "==> Podpisywanie GPG zmienionego artykułu oraz feedów RSS..."
"$GPG_BIN" --batch --yes --detach-sign -a -u "$GPG_KEY_ID" "$ARTICLE_ABS"

# Jawny staging plików bez wildcardów
git add "$ARTICLE_ABS"
if [ -f "${ARTICLE_ABS}.asc" ]; then
    git add "${ARTICLE_ABS}.asc"
fi

for r_file in "$RSS_FILE_DEFAULT" "$RSS_FILE_PL" "$RSS_FILE_EN"; do
    if [ -f "$r_file" ]; then
        "$GPG_BIN" --batch --yes --detach-sign -a -u "$GPG_KEY_ID" "$r_file"
        git add "$r_file"
        if [ -f "${r_file}.asc" ]; then
            git add "${r_file}.asc"
        fi
    fi
done

if ! git diff --staged --quiet; then
    echo "==> Tworzenie drugiego commita z dyskusją i feedami RSS..."
    git commit -S -m "chore(discussion): podpięcie wątku TG #${MESSAGE_ID} dla ${CANONICAL_PATH}"
    echo "    Wypychanie zmian końcowych do gałęzi $CURRENT_BRANCH..."
    git push origin "$CURRENT_BRANCH"
else
    echo "    Informacja: Brak nowych zmian do zatwierdzenia w kroku finalnym (nothing to commit). Kontynuuję weryfikację."
fi

CURRENT_STAGE="KROK 3: Końcowy HTTP Polling ramki dyskusyjnej w sieci"
EXPECTED_IFRAME_SIGNATURE="t.me/${TG_CHANNEL_NAME}/${MESSAGE_ID}"
echo "==> Weryfikacja końcowa wdrożenia ramki dyskusyjnej w sieci..."
poll_http_endpoint "$TARGET_URL" "$EXPECTED_IFRAME_SIGNATURE"

CURRENT_STAGE="Finalizacja i sprzątanie pliku stanu"
if [ -f "$STATE_FILE" ]; then
    rm -f "$STATE_FILE"
    echo "==> Usunięto plik stanu: $STATE_FILE"
fi

echo "=============================================================================="
echo "==> Publikacja artykułu zakończona pełnym sukcesem!"
echo "    Artykuł:  $TARGET_URL"
echo "    Dyskusja: https://t.me/${TG_CHANNEL_NAME}/${MESSAGE_ID}"
echo "=============================================================================="
