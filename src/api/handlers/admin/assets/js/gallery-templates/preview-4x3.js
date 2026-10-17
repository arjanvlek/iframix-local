// Previews of the webapp 2.3.8 4:3 catalogs, drawn in percent-of-frame
// geometry taken from the on-device screenshots
// (docs/gallery-mode-templates-2.3.8.md). Each renderer returns the
// SVG for a template id, or undefined for an id outside its catalog.

function _preview4x3Landscape(k, id) {
    const {photoUrl, bg, fullPhoto, pPhoto, pRect, pPanel, hbar, vbar,
        fade, svg, TITLE, DESC} = k;
    // Webapp 2.3.8, display mounted in landscape (8 layouts).
    // Geometry: docs/gallery-mode-templates-2.3.8.md §2.
    switch (id) {
        case 1: // Left bookend
            return svg(
                bg("#111")
                + pPanel(0, 0, 25, 100, "#EFEBE9")
                + pPhoto(25, 0, 75, 100)
                + fade(25, 78, 75, 22)
                + vbar(12.5, 22, 78, TITLE, "#222")
                + hbar(30, 93, 40, DESC, "#fff")
            );
        case 2: // Split canvas
            return svg(
                bg("#F8F5F0")
                + pPanel(0, 0, 40, 100, "#F8F5F0")
                + pPhoto(40, 0, 60, 100)
                + hbar(8, 42, 24, TITLE, "#222")
                + hbar(8, 48, 18, TITLE, "#222")
                + hbar(8, 56, 26, DESC, "#888")
                + hbar(8, 60, 14, DESC, "#888")
            );
        case 3: // Asymmetric base
            return svg(
                bg("#fff")
                + pPhoto(0, 0, 100, 72)
                + pPanel(0, 72, 75, 28, "#EFEBE9")
                + pRect(75, 72, 25, 28, "#1C2826")
                + hbar(14, 86, 45, DESC, "#666")
                + hbar(80, 82, 15, TITLE, "#fff")
                + hbar(80, 88, 12, TITLE, "#fff")
                + hbar(80, 94, 8, TITLE, "#fff")
            );
        case 4: // Cross boundary
            return svg(
                bg("#fff")
                + pPhoto(0, 0, 100, 72)
                + pRect(10, 32, 12, 56, "#000")
                + vbar(16, 38, 82, 2.2, "#fff")
                + pRect(35.5, 82, 0.6, 8, "#E63946")
                + hbar(38.5, 86, 42, DESC, "#666")
            );
        case 5: // Dark card
            return svg(
                (photoUrl ? fullPhoto() : bg("#9e9e9e"))
                + pRect(6, 58, 45, 34, "#161618")
                + pRect(6, 58, 45, 1.2, "#D4AF37")
                + hbar(9, 67, 34, TITLE, "#fff")
                + hbar(9, 74, 20, TITLE, "#fff")
                + hbar(9, 82, 34, DESC, "#bbb")
                + hbar(9, 86, 16, DESC, "#bbb")
            );
        case 6: // Legacy top cover
            return svg(
                bg("#fff")
                + pPhoto(0, 0, 100, 72)
                + pPanel(0, 72, 100, 28, "#fff")
                + hbar(28, 83, 44, TITLE, "#222")
                + hbar(30, 90, 40, DESC, "#888")
            );
        case 7: // Legacy bottom left
            return svg(
                bg("#fff")
                + pPhoto(0, 0, 100, 72)
                + pPanel(0, 72, 100, 28, "#fff")
                + hbar(5, 82, 40, DESC, "#888")
                + hbar(5, 89, 48, TITLE, "#222")
            );
        case 8: // Legacy side ribbon
            return svg(
                bg("#fff")
                + pPhoto(0, 0, 75, 100)
                + pPanel(75, 0, 25, 100, "#fff")
                + vbar(89, 12, 62, TITLE, "#222")
                + vbar(84, 20, 62, DESC, "#888")
            );
    }
}

function _preview4x3Portrait(k, id) {
    const {photoUrl, X, bg, fullPhoto, pPhoto, pRect, pPanel, hbar, vbar,
        fade, svg, TITLE, DESC} = k;
    // Webapp 2.3.8, display mounted in portrait (7 layouts).
    // Geometry: docs/gallery-mode-templates-2.3.8.md §3. Note the
    // bundle names of ids 3 and 6 are mirrored relative to what
    // renders; the drawings follow the render.
    switch (id) {
        case 1: // Classic bottom
            return svg(
                bg("#FCFBF9")
                + pPhoto(0, 0, 100, 70)
                + pPanel(0, 70, 100, 30, "#FCFBF9")
                + hbar(11, 83, 38, TITLE, "#222")
                + hbar(11, 88, 52, DESC, "#888")
            );
        case 2: // Magazine top
            return svg(
                bg("#EFEBE9")
                + pPhoto(0, 0, 100, 70)
                + pPanel(0, 70, 100, 30, "#EFEBE9")
                + pRect(41.7, 80, 0.5, 9, "#BCAAA4")
                + hbar(12, 82, 24, TITLE, "#222")
                + hbar(12, 87, 18, TITLE, "#222")
                + hbar(46, 83, 40, DESC, "#666")
                + hbar(46, 87, 14, DESC, "#666")
            );
        case 3: // "Left sidebar" — renders sidebar right
            return svg(
                bg("#EFEBE9")
                + pPhoto(0, 0, 75, 100)
                + fade(0, 45, 75, 55)
                + pPanel(75, 0, 25, 100, "#EFEBE9")
                + vbar(87.5, 33, 67, TITLE, "#222")
                + hbar(11, 93, 50, DESC, "#fff")
            );
        case 4: // Overlap card
            return svg(
                (photoUrl ? fullPhoto() : bg("#9e9e9e"))
                + pRect(12, -3, 15, 44, "#D4494C", ' rx="' + X(2) + '"')
                + vbar(19.5, 7, 37, 2.4, "#fff")
                + pRect(34, 81, 58, 14, "#fff")
                + hbar(40, 86, 46, DESC, "#333")
                + hbar(58, 90, 10, DESC, "#333")
            );
        case 5: // Cinematic fade
            return svg(
                bg("#fff")
                + pPhoto(0, 0, 100, 70)
                + pRect(12, 40, 15, 49, "#000")
                + vbar(19.5, 45, 84, 2.4, "#fff")
                + pRect(36, 81, 0.6, 7, "#E63946")
                + hbar(40, 83, 46, DESC, "#666")
                + hbar(40, 87, 12, DESC, "#666")
            );
        case 6: // "Right spine" — renders spine left
            return svg(
                bg("#111")
                + pPanel(0, 0, 25, 100, "#F4F1EA")
                + pPhoto(25, 0, 75, 100)
                + vbar(14, 27, 57, TITLE, "#222")
                + hbar(6, 82, 13, DESC, "#666")
                + hbar(6, 85.5, 14, DESC, "#666")
                + hbar(6, 89, 13, DESC, "#666")
                + hbar(6, 92.5, 10, DESC, "#666")
            );
        case 7: // Glass pillar
            return svg(
                (photoUrl ? fullPhoto() : bg("#9e9e9e"))
                + pRect(40, 0, 20, 100, "#233334")
                + vbar(50, 33, 66, 2.4, "#fff")
                + pRect(12, 70, 76, 10, "#fff")
                + hbar(23, 75, 54, DESC, "#333")
            );
    }
}
