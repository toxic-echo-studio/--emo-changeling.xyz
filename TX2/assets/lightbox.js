document.addEventListener("DOMContentLoaded", () => {
    const dialog = document.getElementById("lightbox-dialog");
    const img = document.getElementById("lightbox-img");
    const closeBtn = document.getElementById("lightbox-close");
    const cards = document.querySelectorAll(".fanart-card");

    if (!dialog || !img || !closeBtn) return;

    let scale = 1;
    let translateX = 0;
    let translateY = 0;
    let isDragging = false;
    let startX = 0;
    let startY = 0;

    // Mobile gesture variables
    let initialTouchDist = 0;
    let initialScale = 1;

    const resetZoom = () => {
        scale = 1;
        translateX = 0;
        translateY = 0;
        applyTransform();
    };

    const applyTransform = () => {
        img.style.transform = `translate(${translateX}px, ${translateY}px) scale(${scale})`;
    };

    // Open lightbox on card click
    cards.forEach(card => {
        const cardImg = card.querySelector("img");
        if (!cardImg) return;

        card.addEventListener("click", () => {
            img.src = cardImg.src;
            img.alt = cardImg.alt;
            resetZoom();
            dialog.showModal();
        });
    });

    // Close lightbox
    const closeLightbox = () => {
        dialog.close();
    };

    closeBtn.addEventListener("click", closeLightbox);

    // Close on dialog overlay click
    dialog.addEventListener("click", (e) => {
        if (e.target === dialog || e.target.classList.contains("lightbox-wrapper") || e.target.classList.contains("lightbox-content")) {
            closeLightbox();
        }
    });

    // Close on Escape key (handled natively by <dialog>, but reset scale)
    dialog.addEventListener("close", resetZoom);

    // Desktop Mouse Wheel Zoom
    dialog.addEventListener("wheel", (e) => {
        e.preventDefault();
        const zoomSpeed = 0.15;
        if (e.deltaY < 0) {
            scale = Math.min(scale + zoomSpeed, 5); // Limit max scale to 5x
        } else {
            scale = Math.max(scale - zoomSpeed, 1); // Limit min scale to 1x
            if (scale === 1) {
                translateX = 0;
                translateY = 0;
            }
        }
        applyTransform();
    }, { passive: false });

    // Desktop Mouse Drag to Pan
    img.addEventListener("mousedown", (e) => {
        if (scale <= 1) return;
        isDragging = true;
        startX = e.clientX - translateX;
        startY = e.clientY - translateY;
        e.preventDefault();
    });

    window.addEventListener("mousemove", (e) => {
        if (!isDragging) return;
        translateX = e.clientX - startX;
        translateY = e.clientY - startY;
        applyTransform();
    });

    window.addEventListener("mouseup", () => {
        isDragging = false;
    });

    // Helper: calculate distance between two touches
    const getTouchDistance = (touch1, touch2) => {
        return Math.hypot(touch2.clientX - touch1.clientX, touch2.clientY - touch1.clientY);
    };

    // Mobile Touch Gestures (Pinch-to-zoom and Pan)
    img.addEventListener("touchstart", (e) => {
        if (e.touches.length === 2) {
            initialTouchDist = getTouchDistance(e.touches[0], e.touches[1]);
            initialScale = scale;
        } else if (e.touches.length === 1) {
            isDragging = true;
            startX = e.touches[0].clientX - translateX;
            startY = e.touches[0].clientY - translateY;
        }
    });

    img.addEventListener("touchmove", (e) => {
        if (e.touches.length === 2) {
            // Pinch-to-zoom
            e.preventDefault();
            const currentDist = getTouchDistance(e.touches[0], e.touches[1]);
            if (initialTouchDist > 0) {
                const factor = currentDist / initialTouchDist;
                scale = Math.max(1, Math.min(initialScale * factor, 5));
                applyTransform();
            }
        } else if (e.touches.length === 1 && isDragging) {
            // Drag-to-pan (only if zoomed in)
            if (scale > 1) {
                e.preventDefault();
                translateX = e.touches[0].clientX - startX;
                translateY = e.touches[0].clientY - startY;
                applyTransform();
            }
        }
    }, { passive: false });

    img.addEventListener("touchend", (e) => {
        if (e.touches.length < 2) {
            initialTouchDist = 0;
        }
        if (e.touches.length === 0) {
            isDragging = false;
        }
    });
});
