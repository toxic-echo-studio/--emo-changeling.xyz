---
name: magazine-publish
description: >-
  Kompletna procedura publikacji nowych wydań i artykułów w e-zinie /MAGAZINE (reverse.emo-changeling.xyz)
  w modelu dwujęzycznych par publikacyjnych (Bilingual Thread Pairing).
  Aktywuj ten skill, gdy użytkownik wpisze polecenie "/MAGAZINE", zażąda publikacji nowego numeru magazynu,
  dodania nowego artykułu PL/EN lub połączenia publikacji z Telegramem, kanałami RSS i Cloudflare Pages.
---

# Procedura publikacji treści w module /MAGAZINE

Moduł e-zinu / magazynu funkcjonuje w ramach zdecentralizowanego ekosystemu *The Reverse Emo Changeling* pod domeną `https://reverse.emo-changeling.xyz` i jest wdrażany statycznie na Cloudflare Pages.

Repozytorium modułu: `c:\Users\mighn\source\repos\toxic-echo-studio\--emo-changeling.xyz\MAGAZINE`

---

## Filozofia i twarde zasady publikacji

1. **Bilingual Thread Pairing**: Każdy materiał składa się z pary językowej PL (`pl/<nr>-<rok>/<slug>.html`) oraz EN (`en/<nr>-<rok>/<slug>.html`). Obie wersje posiadają identyczny slug i dzielą **dokładnie jeden wspólny wątek dyskusyjny** na Telegramie (`@emochangeling`).
2. **Statyczność i brak zbędnego JS**: Nawigacja, zakładki i przełączanie wydań w katalogu opierają się na semantycznym HTML5 i Pure CSS (ukryte radio buttony `#issue-select-<nr>`).
3. **Format kodowania**: Wszystkie pliki tekstowe (HTML, CSS, XML, TXT, SH) muszą być zapisane jako UTF-8 bez BOM z zakończeniami linii LF (`\n`). Wsady zewnętrzne (np. z Google Drive) mogą być zakodowane w Windows-1250 i wymagają konwersji do UTF-8.
4. **Rygor GPG**: Każdy publikowany lub modyfikowany plik w module magazynu musi posiadać odpowiadający mu odłączony podpis PGP (`.asc`), wygenerowany kluczem redakcyjnym:
   `55B1F5E9342F388E6F06483C34A85D454D1FD3BC`
5. **Jednoznaczne wdrożenie**: Całość zmian trafia do repozytorium w **dokładnie jednym commicie Git**, po czym weryfikowane jest wdrożenie na Cloudflare Pages przez HTTP polling (`200 OK`).

---

## 8-etapowy algorytm publikacji

### Krok 1: Przygotowanie i normalizacja wsadu
- Jeśli wsad pochodzi z zewnętrznego URL (np. Google Drive `export=download`), pobierz go do folderu tymczasowego.
- Sprawdź kodowanie znaków. Jeśli plik zawiera polskie znaki w CP1250 / Windows-1250, przekonwertuj go na czyste UTF-8 (np. za pomocą Pythona `content.decode('cp1250').encode('utf-8')`).
- Wyodrębnij:
  - Numer wydania i rok (np. `20/2026`),
  - Datę publikacji w formacie ISO (np. `2026-09-09`),
  - Tytuł PL oraz Tytuł EN,
  - Ewentualny link do materiału wideo YouTube (jeśli dotyczy),
  - Pełną treść artykułu w obu językach.

### Krok 2: Przygotowanie semantycznych szablonów HTML artykułu
Utwórz pliki:
- `MAGAZINE/pl/<nr>-<rok>/<slug>.html`
- `MAGAZINE/en/<nr>-<rok>/<slug>.html`

Wymagane elementy w obu plikach:
- Tag `<html>` z `lang="pl"` lub `lang="en"`, odpowiednie `data-version` i `data-build`.
- **[AUDIT RULE - LINKOWANIE]** Zewnętrzny link kierujący do TX2 Unofficial (https://tx2.emo-changeling.xyz/) w nawigacji lub treści MUSI bezwzględnie posiadać atrybuty 
el="sponsored nofollow".
- Canonical i hreflang wskazujące obie wersje językowe:
  ```html
  <link rel="canonical" href="https://reverse.emo-changeling.xyz/pl/<nr>-<rok>/<slug>.html">
  <link rel="alternate" hreflang="pl" href="https://reverse.emo-changeling.xyz/pl/<nr>-<rok>/<slug>.html">
  <link rel="alternate" hreflang="en" href="https://reverse.emo-changeling.xyz/en/<nr>-<rok>/<slug>.html">
  ```
- Kompletne metatagi Open Graph i Twitter Card.
- Dane strukturalne Schema.org (`@type: Article`, `isPartOf: PublicationIssue`, `author: Person`, `publisher: Organization`). W przypadku materiału wideo dodaj powiązany obiekt `video: VideoObject`.
- Treść artykułu wewnątrz `<article id="article" class="article-reader"><section class="article-body">`.
- Stopka redakcyjna w elemencie `<details class="editorial-details notranslate" translate="no">`.
- Pływające menu nawigacyjne (`<details class="floating-nav notranslate" translate="no">`), w którym zewnętrzny link do TX2 Unofficial posiada obowiązkowo atrybut `rel="sponsored nofollow"`:
  ```html
  <a href="https://tx2.emo-changeling.xyz/" class="floating-nav-link" rel="sponsored nofollow">TX2 Unofficial</a>
  ```

### Krok 3: Dodanie reguł Pure CSS dla nowego wydania
W pliku `MAGAZINE/css/style.css`:
- Sprawdź, czy numer wydania ma już zdefiniowane reguły selektora radio buttonów.
- Jeśli to nowe wydanie, dopisz reguły dla nagłówka i feedu:
  ```css
  #issue-select-<nr>:checked ~ .magazine-content .issue-header-<nr>,
  #issue-select-<nr>:checked ~ * .issue-feed-<nr> {
      display: block;
  }
  ```

### Krok 4: Aktualizacja katalogu i archiwów magazynu
1. **`MAGAZINE/pl/index.html` oraz `MAGAZINE/en/index.html`**:
   - Ustaw radio button nowego numeru jako domyślnie zaznaczony (`checked`).
   - W sekcji nagłówków dodaj blok `<div class="issue-header issue-header-<nr>">` z metadanymi i tytułem numeru.
   - W sekcji feedu dodaj `<div class="issue-feed issue-feed-<nr>">` z kartą nowego artykułu.
2. **`MAGAZINE/pl/archive.html` oraz `MAGAZINE/en/archive.html`**:
   - Dodaj wpis nowego numeru na samej górze listy archiwalnej (`<li class="archive-item">`).
3. **`MAGAZINE/index.html`**:
   - Zaktualizuj opis i numer bieżącego wydania, podbij wersję e-zinu (np. z `1.10.19` do `1.10.20`).
4. **Metadane serwisu**:
   - `MAGAZINE/sitemap.xml`: dodaj wpisy `<url>` dla wersji PL i EN.
   - `MAGAZINE/llms.txt`: podbij `system_version` oraz `revision_date`.

### Krok 5: Automatyzacja integracji Telegram i wstrzyknięcie wątku
W powłoce `pwsh` na maszynie Windows uruchom skrypt masowej migracji/publikacji za pomocą bash z Git:
```powershell
& "C:\Program Files\Git\bin\bash.exe" bulk_tg_backfill.sh --yes
```
*Działanie skryptu:*
- Weryfikuje konfigurację `.env` i obecność klucza GPG.
- Publikuje dwujęzyczny post na kanale Telegram `@emochangeling`.
- Pobiera przydzielony `message_id`.
- Automatycznie wstrzykuje sekcję dyskusyjną `telegram-comments-wrapper` z linkiem `https://t.me/emochangeling/<message_id>?comment=1` do obu plików HTML.
- Uruchamia `generate_rss.py`, regenerując pliki `rss-pl.xml`, `rss-en.xml` oraz `rss.xml`.
- Podpisuje zmodyfikowane pliki kluczem GPG.

### Krok 6: Podpisanie pozostałych plików GPG
Upewnij się, że wszystkie zmienione i nowe pliki posiadają aktualne pliki `.asc`:
```powershell
$gpg = "C:\Program Files\GnuPG\bin\gpg.exe"
$key = "55B1F5E9342F388E6F06483C34A85D454D1FD3BC"
$files = @(
    "css/style.css",
    "pl/index.html", "en/index.html",
    "pl/archive.html", "en/archive.html",
    "index.html", "sitemap.xml", "llms.txt"
)
foreach ($f in $files) {
    & $gpg --batch --yes --armor --detach-sign --local-user $key $f
}
```

### Krok 7: Zbiorczy Commit Git i Push
W katalogu `--emo-changeling.xyz`:
```powershell
git add .
git commit -m "publish(magazine): release issue <nr>/<rok> (<slug>) with telegram thread and gpg signatures"
git push origin main
```

### Krok 8: Weryfikacja propagacji HTTP (Cloudflare Pages)
Po wykonaniu `git push` odczekaj na propagację CDN na krawędzi Cloudflare (skonfigurowano margines min. 40 prób co 10 s):
```powershell
$urls = @(
    "https://reverse.emo-changeling.xyz/pl/<nr>-<rok>/<slug>.html",
    "https://reverse.emo-changeling.xyz/en/<nr>-<rok>/<slug>.html"
)
foreach ($u in $urls) {
    $res = Invoke-WebRequest -Uri $u -Method Head -SkipHttpErrorCheck
    Write-Output "$u -> $($res.StatusCode)"
}
```
Sprawdź, czy oba endpointy zwracają status **200 OK**.
