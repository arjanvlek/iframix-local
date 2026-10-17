// Gallery Mode template preview: picks the renderer for the display's
// catalog and falls back to a numbered placeholder.

// Renders an SVG preview of the layout the iPad webapp shows for this
// template_id on the given display aspect and orientation
// (``templateType`` 1 = landscape, 2 = portrait; ``legacy`` selects the
// 2.3.1–2.3.5 4:3 catalog). When ``photoUrl`` is given,
// the photo itself is composited into the image areas (cover-cropped),
// so the modal preview is a true "how it will look" rendering;
// otherwise the image areas are plain grey. ``preview-text-bg`` rects
// pick up an accent tint when the parent option is selected.
function _templatePreviewSvg(aspect, id, photoUrl, templateType, legacy) {
    const k = _templatePreviewKit(aspect, photoUrl, templateType);
    const portrait = templateType === 2;
    let out;
    if (aspect !== "4x3") out = _preview16x9(k, id);
    else if (legacy) out = _preview4x3Legacy(k, id);
    else if (portrait) out = _preview4x3Portrait(k, id);
    else out = _preview4x3Landscape(k, id);
    if (out) return out;
    // Fallback for unexpected ids: label them numerically.
    return k.svg(
        k.bg("#f5f5f5")
        + '<text x="' + (k.W / 2) + '" y="' + (k.H / 2 + 6) +
        '" font-family="sans-serif" font-size="20" ' +
        'text-anchor="middle" fill="#888">' + id + "</text>"
    );
}
