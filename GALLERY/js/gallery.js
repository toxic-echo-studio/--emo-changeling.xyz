(function () {
    'use strict';

    const grid = document.getElementById('gallery-grid');
    const modal = document.getElementById('gallery-modal');
    const modalCloseBtn = document.getElementById('modal-close');
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
    const BLANK_GIF = 'data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7';

    const galleryMap = new Map();
    let galleryItems = [];

    const dataScript = document.getElementById('gallery-data');
    if (dataScript && dataScript.textContent) {
        try {
            const parsed = JSON.parse(dataScript.textContent);
            if (Array.isArray(parsed)) {
                galleryItems = parsed;
                parsed.forEach(function (item) {
                    if (item && item.id !== undefined && item.id !== null) {
                        galleryMap.set(String(item.id), item);
                    }
                });
            }
        } catch (e) {
            galleryItems = [];
        }
    }

    let lastFocusedCard = null;
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

    function isEn() {
        return document.documentElement.lang === 'en';
    }

    function cleanArtworkTitle(title) {
        return String(title || '').replace(/^(?:Go\u0142\u0105b|Pigeon)\s+#\d+:\s*/i, '');
    }

    function renderCardsFallback() {
        if (!grid || grid.querySelectorAll('button.gallery-card, .gallery-card').length > 0) {
            return;
        }
        const fragment = document.createDocumentFragment();
        galleryItems.forEach(function (item) {
            const cardBtn = document.createElement('button');
            cardBtn.type = 'button';
            cardBtn.className = 'gallery-card';
            cardBtn.dataset.itemId = String(item.id);

            const cleanTitle = cleanArtworkTitle(item.title);
            const isCyrillic = /[\u0400-\u04FF]/.test(cleanTitle);

            const itemDiv = document.createElement('div');
            itemDiv.className = 'gallery-item';

            const img = document.createElement('img');
            img.src = item.thumb || '';
            img.alt = cleanTitle;
            img.loading = 'lazy';
            itemDiv.appendChild(img);

            const captionDiv = document.createElement('div');
            captionDiv.className = 'gallery-item-caption';
            if (isCyrillic) {
                captionDiv.setAttribute('lang', 'ru');
            }
            captionDiv.textContent = cleanTitle;

            cardBtn.appendChild(itemDiv);
            cardBtn.appendChild(captionDiv);
            fragment.appendChild(cardBtn);
        });
        grid.appendChild(fragment);
    }

    renderCardsFallback();

    if (grid) {
        grid.addEventListener('click', function (e) {
            const card = e.target.closest('.gallery-card[data-item-id]');
            if (!card || !grid.contains(card)) return;
            const item = galleryMap.get(String(card.dataset.itemId));
            if (item) {
                lastFocusedCard = card;
                openModal(item);
            }
        });
    }

    function syncOpisLangButtons(lang) {
        if (!descContent) return;
        const btns = descContent.querySelectorAll('.lang-btn, .opis-lang-btn');
        btns.forEach(function (btn) {
            if (btn.getAttribute('data-lang') === lang) {
                btn.classList.add('active');
                btn.setAttribute('aria-current', 'true');
            } else {
                btn.classList.remove('active');
                btn.removeAttribute('aria-current');
            }
        });
    }

    if (descContent) {
        descContent.addEventListener('click', function (e) {
            const btn = e.target.closest('.lang-btn[data-lang], .opis-lang-btn[data-lang]');
            if (!btn || !descContent.contains(btn)) return;
            e.stopPropagation();
            const lang = btn.getAttribute('data-lang');
            if (!lang) return;
            descContent.setAttribute('data-active-lang', lang);
            syncOpisLangButtons(lang);
        });
    }

    function updateDownloadButton(slide) {
        if (!downloadBtn) return;
        if (slide && slide.download_tif) {
            downloadBtn.href = slide.download_tif;
            downloadBtn.setAttribute('data-asc', slide.download_tif + '.asc');
            downloadBtn.classList.add('is-inline-block');
            const lower = String(slide.download_tif).toLowerCase();
            if (lower.endsWith('.png')) {
                downloadBtn.textContent = 'DOWNLOAD MAX QUALITY (.PNG)';
            } else if (lower.endsWith('.jpg') || lower.endsWith('.jpeg')) {
                downloadBtn.textContent = 'DOWNLOAD MAX QUALITY (.JPG)';
            } else {
                downloadBtn.textContent = 'DOWNLOAD MAX QUALITY (.TIF)';
            }
        } else {
            downloadBtn.classList.remove('is-inline-block');
            downloadBtn.removeAttribute('href');
            downloadBtn.removeAttribute('data-asc');
        }
    }

    function updateSlide(newIndex) {
        if (!currentSlides.length || !sliderTrack) return;
        currentSlideIndex = Math.max(0, Math.min(currentSlides.length - 1, newIndex));
        sliderTrack.style.transition = '';
        sliderTrack.style.transform = 'translateX(-' + (currentSlideIndex * 100) + '%)';

        const activeSlide = currentSlides[currentSlideIndex];
        if (slideTitleEl) {
            slideTitleEl.textContent = cleanArtworkTitle(activeSlide.title);
        }

        updateDownloadButton(activeSlide);

        if (currentSlides.length > 1) {
            const isAtStart = (currentSlideIndex === 0);
            const isAtEnd = (currentSlideIndex === currentSlides.length - 1);
            if (prevBtn) {
                prevBtn.classList.remove('is-hidden');
                prevBtn.classList.toggle('is-disabled', isAtStart);
                prevBtn.setAttribute('aria-disabled', String(isAtStart));
            }
            if (nextBtn) {
                nextBtn.classList.remove('is-hidden');
                nextBtn.classList.toggle('is-disabled', isAtEnd);
                nextBtn.setAttribute('aria-disabled', String(isAtEnd));
            }
            if (slideCounter) {
                slideCounter.classList.remove('is-hidden');
                slideCounter.textContent = '[ ' + (currentSlideIndex + 1) + ' / ' + currentSlides.length + ' ]';
            }
            if (sliderViewport) {
                sliderViewport.classList.add('is-draggable');
            }
        } else {
            if (prevBtn) prevBtn.classList.add('is-hidden');
            if (nextBtn) nextBtn.classList.add('is-hidden');
            if (slideCounter) slideCounter.classList.add('is-hidden');
            if (sliderViewport) sliderViewport.classList.remove('is-draggable');
        }
    }

    if (prevBtn) {
        prevBtn.addEventListener('click', function (e) {
            e.preventDefault();
            e.stopPropagation();
            if (currentSlideIndex > 0) {
                updateSlide(currentSlideIndex - 1);
            }
        });
    }

    if (nextBtn) {
        nextBtn.addEventListener('click', function (e) {
            e.preventDefault();
            e.stopPropagation();
            if (currentSlideIndex < currentSlides.length - 1) {
                updateSlide(currentSlideIndex + 1);
            }
        });
    }

    function finishDrag() {
        if (!isDragging) return;
        isDragging = false;
        if (sliderViewport) sliderViewport.classList.remove('is-dragging');
        if (sliderTrack) sliderTrack.style.transition = '';
        if (dragDeltaX < -40 && currentSlideIndex < currentSlides.length - 1) {
            updateSlide(currentSlideIndex + 1);
        } else if (dragDeltaX > 40 && currentSlideIndex > 0) {
            updateSlide(currentSlideIndex - 1);
        } else {
            updateSlide(currentSlideIndex);
        }
        dragDeltaX = 0;
        setTimeout(function () {
            didDragMove = false;
        }, 50);
    }

    if (sliderViewport && sliderTrack) {
        sliderViewport.addEventListener('mousedown', function (e) {
            if (currentSlides.length <= 1) return;
            isDragging = true;
            didDragMove = false;
            dragStartX = e.clientX;
            dragDeltaX = 0;
            sliderViewport.classList.add('is-dragging');
            sliderTrack.style.transition = 'none';
            e.preventDefault();
        });

        window.addEventListener('mousemove', function (e) {
            if (!isDragging) return;
            dragDeltaX = e.clientX - dragStartX;
            if (Math.abs(dragDeltaX) > 5) {
                didDragMove = true;
            }
            sliderTrack.style.transform = 'translateX(calc(-' + (currentSlideIndex * 100) + '% + ' + dragDeltaX + 'px))';
        });

        window.addEventListener('mouseup', finishDrag);
        sliderViewport.addEventListener('mouseleave', finishDrag);

        sliderViewport.addEventListener('touchstart', function (e) {
            lastTouchTimestamp = Date.now();
            if (currentSlides.length > 1 && e.touches.length === 1) {
                isDragging = true;
                didDragMove = false;
                dragStartX = e.touches[0].clientX;
                dragDeltaX = 0;
                sliderTrack.style.transition = 'none';
            }
        }, { passive: true });

        sliderViewport.addEventListener('touchmove', function (e) {
            if (!isDragging || !e.touches.length) return;
            dragDeltaX = e.touches[0].clientX - dragStartX;
            if (Math.abs(dragDeltaX) > 5) {
                didDragMove = true;
            }
            sliderTrack.style.transform = 'translateX(calc(-' + (currentSlideIndex * 100) + '% + ' + dragDeltaX + 'px))';
        }, { passive: true });

        sliderViewport.addEventListener('touchend', finishDrag);

        sliderViewport.addEventListener('click', function (e) {
            if (didDragMove) return;
            if (!e.target.classList.contains('modal-image')) return;
            if (window.innerWidth > 768 && (Date.now() - lastTouchTimestamp > 600)) {
                openZoomOverlay();
            }
        });
    }

    if (zoomBtn) {
        zoomBtn.addEventListener('click', function (e) {
            e.preventDefault();
            e.stopPropagation();
            openZoomOverlay();
        });
    }

    function clampZoomPan() {
        if (!zoomStage || !zoomImg) return;
        const stageRect = zoomStage.getBoundingClientRect();
        const scaledW = zoomImg.offsetWidth * zoomScale;
        const scaledH = zoomImg.offsetHeight * zoomScale;
        const maxPanX = Math.max(0, (scaledW - stageRect.width) / 2);
        const maxPanY = Math.max(0, (scaledH - stageRect.height) / 2);
        zoomPanX = Math.max(-maxPanX, Math.min(maxPanX, zoomPanX));
        zoomPanY = Math.max(-maxPanY, Math.min(maxPanY, zoomPanY));
    }

    function applyZoomTransform() {
        if (!zoomImg || !zoomOverlay) return;
        zoomImg.style.transform = 'translate(' + zoomPanX + 'px, ' + zoomPanY + 'px) scale(' + zoomScale + ')';
        if (zoomScaleResetBtn) {
            zoomScaleResetBtn.textContent = zoomScale.toFixed(1) + 'x';
        }
        if (zoomStage) {
            zoomStage.classList.toggle('is-zoomed', zoomScale > 1.01);
        }
    }

    function zoomAtPoint(newScale, clientX, clientY) {
        if (!zoomStage) return;
        const clampedScale = Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, newScale));
        if (clampedScale === zoomScale) return;
        if (clampedScale <= 1.001) {
            zoomScale = 1.0;
            zoomPanX = 0;
            zoomPanY = 0;
            applyZoomTransform();
            return;
        }
        const stageRect = zoomStage.getBoundingClientRect();
        const cx = clientX - (stageRect.left + stageRect.width / 2);
        const cy = clientY - (stageRect.top + stageRect.height / 2);
        const ratio = clampedScale / zoomScale;
        zoomPanX = cx - (cx - zoomPanX) * ratio;
        zoomPanY = cy - (cy - zoomPanY) * ratio;
        zoomScale = clampedScale;
        clampZoomPan();
        applyZoomTransform();
    }

    function openZoomOverlay() {
        if (!zoomOverlay || !zoomImg || !currentSlides.length) return;
        const activeSlide = currentSlides[currentSlideIndex];
        if (!activeSlide || !activeSlide.full) return;
        zoomImg.src = activeSlide.full;
        zoomImg.alt = activeSlide.title || '';
        zoomScale = 1.0;
        zoomPanX = 0;
        zoomPanY = 0;
        if (zoomStage) {
            zoomStage.scrollTop = 0;
            zoomStage.scrollLeft = 0;
            zoomStage.classList.remove('is-panning', 'is-zoomed');
        }
        zoomImg.style.transform = '';
        applyZoomTransform();
        zoomOverlay.classList.add('active');
    }

    function closeZoomOverlay() {
        if (!zoomOverlay) return;
        zoomOverlay.classList.remove('active');
        zoomScale = 1.0;
        zoomPanX = 0;
        zoomPanY = 0;
        isZoomPanning = false;
        if (zoomStage) {
            zoomStage.classList.remove('is-panning', 'is-zoomed');
        }
        if (zoomImg) {
            zoomImg.style.transform = '';
            zoomImg.src = BLANK_GIF;
        }
    }

    if (zoomStage) {
        zoomStage.addEventListener('wheel', function (e) {
            e.preventDefault();
            const factor = e.deltaY < 0 ? 1.18 : (1 / 1.18);
            zoomAtPoint(zoomScale * factor, e.clientX, e.clientY);
        }, { passive: false });

        zoomStage.addEventListener('mousedown', function (e) {
            if (e.button !== 0 || zoomScale <= 1.01) return;
            isZoomPanning = true;
            didZoomPanMove = false;
            zoomPanStartX = e.clientX;
            zoomPanStartY = e.clientY;
            zoomPanOriginX = zoomPanX;
            zoomPanOriginY = zoomPanY;
            zoomStage.classList.add('is-panning');
            e.preventDefault();
        });

        window.addEventListener('mousemove', function (e) {
            if (!isZoomPanning) return;
            const dx = e.clientX - zoomPanStartX;
            const dy = e.clientY - zoomPanStartY;
            if (Math.abs(dx) > 4 || Math.abs(dy) > 4) {
                didZoomPanMove = true;
            }
            zoomPanX = zoomPanOriginX + dx;
            zoomPanY = zoomPanOriginY + dy;
            clampZoomPan();
            applyZoomTransform();
        });

        window.addEventListener('mouseup', function () {
            if (!isZoomPanning) return;
            isZoomPanning = false;
            zoomStage.classList.remove('is-panning');
            setTimeout(function () {
                didZoomPanMove = false;
            }, 50);
        });

        zoomStage.addEventListener('dblclick', function (e) {
            e.preventDefault();
            if (zoomScale > 1.05) {
                zoomAtPoint(1.0, e.clientX, e.clientY);
            } else {
                zoomAtPoint(2.5, e.clientX, e.clientY);
            }
        });

        zoomStage.addEventListener('click', function (e) {
            if (didZoomPanMove) return;
            if (zoomScale <= 1.01 && e.target === zoomStage) {
                closeZoomOverlay();
            }
        });

        zoomStage.addEventListener('touchstart', function (e) {
            if (e.touches.length === 2) {
                e.preventDefault();
                isZoomPanning = false;
                const dx = e.touches[0].clientX - e.touches[1].clientX;
                const dy = e.touches[0].clientY - e.touches[1].clientY;
                pinchStartDist = Math.hypot(dx, dy);
                pinchStartScale = zoomScale;
            } else if (e.touches.length === 1) {
                const now = Date.now();
                if (now - lastTapTimestamp < 300) {
                    e.preventDefault();
                    const t = e.touches[0];
                    if (zoomScale > 1.05) {
                        zoomAtPoint(1.0, t.clientX, t.clientY);
                    } else {
                        zoomAtPoint(2.5, t.clientX, t.clientY);
                    }
                    lastTapTimestamp = 0;
                    return;
                }
                lastTapTimestamp = now;
                if (zoomScale > 1.01) {
                    isZoomPanning = true;
                    didZoomPanMove = false;
                    zoomPanStartX = e.touches[0].clientX;
                    zoomPanStartY = e.touches[0].clientY;
                    zoomPanOriginX = zoomPanX;
                    zoomPanOriginY = zoomPanY;
                }
            }
        }, { passive: false });

        zoomStage.addEventListener('touchmove', function (e) {
            if (e.touches.length === 2 && pinchStartDist > 0) {
                e.preventDefault();
                const dx = e.touches[0].clientX - e.touches[1].clientX;
                const dy = e.touches[0].clientY - e.touches[1].clientY;
                const dist = Math.hypot(dx, dy);
                const midX = (e.touches[0].clientX + e.touches[1].clientX) / 2;
                const midY = (e.touches[0].clientY + e.touches[1].clientY) / 2;
                zoomAtPoint(pinchStartScale * (dist / pinchStartDist), midX, midY);
            } else if (e.touches.length === 1 && isZoomPanning) {
                e.preventDefault();
                const dx = e.touches[0].clientX - zoomPanStartX;
                const dy = e.touches[0].clientY - zoomPanStartY;
                if (Math.abs(dx) > 4 || Math.abs(dy) > 4) {
                    didZoomPanMove = true;
                }
                zoomPanX = zoomPanOriginX + dx;
                zoomPanY = zoomPanOriginY + dy;
                clampZoomPan();
                applyZoomTransform();
            }
        }, { passive: false });

        zoomStage.addEventListener('touchend', function (e) {
            if (e.touches.length < 2) {
                pinchStartDist = 0;
            }
            if (e.touches.length === 0) {
                isZoomPanning = false;
                setTimeout(function () {
                    didZoomPanMove = false;
                }, 50);
            }
        });
    }

    if (zoomScaleResetBtn) {
        zoomScaleResetBtn.addEventListener('click', function (e) {
            e.stopPropagation();
            zoomScale = 1.0;
            zoomPanX = 0;
            zoomPanY = 0;
            applyZoomTransform();
        });
    }

    if (zoomExitBtn) {
        zoomExitBtn.addEventListener('click', function (e) {
            e.stopPropagation();
            closeZoomOverlay();
        });
    }

    function sanitizeAndMapParsedDescription(parsedDoc) {
        if (!parsedDoc || !parsedDoc.body) return [];
        const allElements = parsedDoc.body.querySelectorAll('*');
        allElements.forEach(function (el) {
            el.removeAttribute('onclick');
            const styleAttr = el.getAttribute('style');
            if (styleAttr) {
                if (/font-size\s*:\s*15px/i.test(styleAttr)) {
                    el.classList.add('opis-fs-15');
                }
                if (/rgb\(\s*165\s*,\s*214\s*,\s*167\s*\)/i.test(styleAttr)) {
                    el.classList.add('gallery-comment');
                }
                if (/border-radius/i.test(styleAttr)) {
                    el.classList.add('opis-inline-img');
                }
                if (/rgba\(\s*0\s*,\s*0\s*,\s*0\s*,\s*0\.4\s*\)/i.test(styleAttr)) {
                    el.classList.add('opis-sketch-dark');
                }
                if (/text-align\s*:\s*center/i.test(styleAttr)) {
                    el.classList.add('opis-center-block');
                }
            }
            el.removeAttribute('style');
        });
        return Array.from(parsedDoc.body.childNodes);
    }

    function setDescriptionStatus(text, className) {
        if (!descContent) return;
        const span = document.createElement('span');
        span.className = className;
        span.textContent = text;
        descContent.replaceChildren(span);
    }

    async function openModal(item) {
        if (!modal || !sliderTrack) return;
        if (!lastFocusedCard && document.activeElement && document.activeElement !== document.body) {
            lastFocusedCard = document.activeElement;
        }

        modal.classList.add('active');
        if (modalCloseBtn && typeof modalCloseBtn.focus === 'function') {
            modalCloseBtn.focus();
        }

        currentSlides = (item.images && item.images.length > 0)
            ? item.images
            : [{ id: item.id, full: item.full, title: item.title, download_tif: item.download_tif }];

        const slideNodes = currentSlides.map(function (s, idx) {
            const slideDiv = document.createElement('div');
            slideDiv.className = 'modal-slide';
            slideDiv.style.transform = 'translateX(' + (idx * 100) + '%)';

            const imgEl = document.createElement('img');
            imgEl.src = s.full || '';
            imgEl.alt = s.title || '';
            imgEl.className = 'modal-image';
            imgEl.draggable = false;

            slideDiv.appendChild(imgEl);
            return slideDiv;
        });

        sliderTrack.replaceChildren.apply(sliderTrack, slideNodes);
        updateSlide(0);

        if (modalDetails && descContent) {
            if (item.descUrl) {
                modalDetails.classList.remove('is-hidden');
                modalDetails.removeAttribute('open');
                if (modalContent) modalContent.classList.remove('rotated');

                setDescriptionStatus(
                    isEn() ? 'Loading data from server...' : 'Wczytywanie danych z serwera...',
                    'blink'
                );

                try {
                    const response = await fetch(item.descUrl);
                    if (!response.ok) {
                        throw new Error(
                            isEn()
                                ? 'Description file not found (404).'
                                : 'Nie znaleziono pliku opisu (404).'
                        );
                    }

                    const htmlData = await response.text();
                    if (htmlData.includes('id="gallery-grid"') || htmlData.includes('data-system="Toxic Echo Studio"')) {
                        throw new Error(
                            isEn()
                                ? 'Server returned main page instead of description file. Check path!'
                                : 'Serwer zwrocil strone glowna zamiast pliku opisu. Sprawdz sciezke!'
                        );
                    }

                    const parser = new DOMParser();
                    const parsedDoc = parser.parseFromString(htmlData, 'text/html');
                    const mappedNodes = sanitizeAndMapParsedDescription(parsedDoc);

                    descContent.replaceChildren.apply(descContent, mappedNodes);
                    descContent.removeAttribute('data-active-lang');

                    const curLang = isEn() ? 'en' : 'pl';
                    syncOpisLangButtons(curLang);
                } catch (error) {
                    const prefix = isEn()
                        ? '[ERROR] Failed to load description: '
                        : '[ERROR] Blad wczytywania opisu: ';
                    const msg = error && error.message ? error.message : String(error);
                    setDescriptionStatus(prefix + msg, 'gallery-error');
                }
            } else {
                modalDetails.classList.add('is-hidden');
                modalDetails.removeAttribute('open');
                if (modalContent) modalContent.classList.remove('rotated');
            }
        }
    }

    if (rotateBtn && modalContent) {
        rotateBtn.addEventListener('click', function (e) {
            e.stopPropagation();
            modalContent.classList.toggle('rotated');
        });
    }

    function closeModal() {
        closeZoomOverlay();
        if (modal) modal.classList.remove('active');
        if (sliderTrack) sliderTrack.replaceChildren();
        if (modalContent) modalContent.classList.remove('rotated');
        if (downloadBtn) {
            downloadBtn.classList.remove('is-inline-block');
            downloadBtn.removeAttribute('href');
            downloadBtn.removeAttribute('data-asc');
        }
        if (lastFocusedCard && typeof lastFocusedCard.focus === 'function') {
            lastFocusedCard.focus();
        }
        lastFocusedCard = null;
    }

    if (modalCloseBtn) {
        modalCloseBtn.addEventListener('click', function (e) {
            e.preventDefault();
            e.stopPropagation();
            closeModal();
        });
    }

    if (modal) {
        modal.addEventListener('click', function (e) {
            if (didDragMove) return;
            if (
                e.target.closest('.tape-nav-btn') ||
                e.target.closest('.modal-slide-counter') ||
                e.target.closest('.modal-zoom-btn') ||
                e.target.closest('.zoom-overlay')
            ) {
                return;
            }
            if (
                e.target === modal ||
                e.target.classList.contains('modal-content') ||
                e.target.classList.contains('modal-slider-row')
            ) {
                closeModal();
            }
        });
    }

    document.addEventListener('keydown', function (e) {
        if (zoomOverlay && zoomOverlay.classList.contains('active')) {
            if (e.key === 'Escape') {
                e.preventDefault();
                closeZoomOverlay();
            }
            return;
        }
        if (!modal || !modal.classList.contains('active')) return;
        if (e.key === 'Escape') {
            closeModal();
        } else if (e.key === 'ArrowLeft' && currentSlides.length > 1) {
            if (currentSlideIndex > 0) updateSlide(currentSlideIndex - 1);
        } else if (e.key === 'ArrowRight' && currentSlides.length > 1) {
            if (currentSlideIndex < currentSlides.length - 1) updateSlide(currentSlideIndex + 1);
        }
    });
})();
