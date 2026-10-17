// SVG drawing kit shared by the Gallery Mode template preview
// renderers (preview-*.js). It sizes the frame for
// the display aspect / orientation and returns the drawing helpers;
// clip paths and gradients are collected in ``defs`` and emitted by
// ``svg()``. ``_svgUid`` keeps their ids unique across previews.

let _svgUid = 0;
function _templatePreviewKit(aspect, photoUrl, templateType) {
    // Frame: 4:3 displays get a 4:3 box (or 3:4 when the display is
    // mounted in portrait), 16:9 displays a 16:9 box.
    const portrait = templateType === 2;
    const W = aspect === "4x3" ? (portrait ? 90 : 120) : 160;
    const H = aspect === "4x3" ? (portrait ? 120 : 90) : 90;
    // Legacy (2.3.1–2.3.5 4:3 catalog) and 16:9 layouts are authored on
    // the original 100x60 grid; map into the aspect-correct viewBox so
    // embedded photos keep their proportions.
    const fx = (v) => +(v / 100 * W).toFixed(2);
    const fy = (v) => +(v / 60 * H).toFixed(2);
    // The 2.3.8 4:3 layouts are authored in percent of the frame, taken
    // from the on-device screenshots (docs/gallery-mode-templates-2.3.8.md).
    const X = (v) => +(v / 100 * W).toFixed(2);
    const Y = (v) => +(v / 100 * H).toFixed(2);
    const esc = (u) => String(u || "")
        .replace(/&/g, "&amp;").replace(/"/g, "&quot;")
        .replace(/</g, "%3C").replace(/>/g, "%3E");
    const defs = [];

    const photoAt = (x, y, w, h, clip) => {
        const attrs = 'x="' + x + '" y="' + y + '" width="' + w +
            '" height="' + h + '"' +
            (clip ? ' clip-path="url(#' + clip + ')"' : "");
        if (photoUrl) {
            return '<image href="' + esc(photoUrl) + '" ' + attrs +
                ' preserveAspectRatio="xMidYMid slice"/>';
        }
        return '<rect ' + attrs + ' fill="#9e9e9e"/>';
    };
    const photo = (x, y, w, h, clip) =>
        photoAt(fx(x), fy(y), fx(w), fy(h), clip);
    const clipPoly = (points) => {
        const cid = "tplclip" + (++_svgUid);
        const pts = points.map(
            ([x, y]) => fx(x) + "," + fy(y)).join(" ");
        defs.push('<clipPath id="' + cid + '"><polygon points="' +
            pts + '"/></clipPath>');
        return cid;
    };
    const clipPath = (d) => {
        const cid = "tplclip" + (++_svgUid);
        defs.push('<clipPath id="' + cid + '"><path d="' + d +
            '"/></clipPath>');
        return cid;
    };
    const bg = (color) => '<rect width="' + W + '" height="' + H +
        '" fill="' + color + '"/>';
    const fullPhoto = () => photoAt(0, 0, W, H);
    const panel = (x, y, w, h) =>
        '<rect class="preview-text-bg" x="' + fx(x) + '" y="' + fy(y) +
        '" width="' + fx(w) + '" height="' + fy(h) + '" fill="#e0e0e0"/>';
    const box = (x, y, w, h, fill) =>
        '<rect x="' + fx(x) + '" y="' + fy(y) + '" width="' + fx(w) +
        '" height="' + fy(h) + '" rx="3" fill="' + fill +
        '" stroke="#bbb" stroke-width="0.5"/>';
    const lines = (cx, y, w, count, color) => {
        let s = "";
        for (let i = 0; i < count; i++) {
            const lw = w * (1 - i * 0.18);
            s += '<rect x="' + fx(cx - lw / 2) + '" y="' + fy(y + i * 5) +
                '" width="' + fx(lw) + '" height="' + fy(2) +
                '" rx="1" fill="' + (color || "#888") + '"/>';
        }
        return s;
    };

    // Percent-of-frame helpers for the 2.3.8 4:3 layouts.
    const pPhoto = (x, y, w, h) => photoAt(X(x), Y(y), X(w), Y(h));
    const pRect = (x, y, w, h, fill, extra) =>
        '<rect x="' + X(x) + '" y="' + Y(y) + '" width="' + X(w) +
        '" height="' + Y(h) + '" fill="' + fill + '"' +
        (extra || "") + "/>";
    // Caption panel that picks up the accent tint when selected.
    const pPanel = (x, y, w, h, fill) =>
        '<rect class="preview-text-bg" x="' + X(x) + '" y="' + Y(y) +
        '" width="' + X(w) + '" height="' + Y(h) + '" fill="' +
        (fill || "#e0e0e0") + '"/>';
    // Horizontal text bar: left edge x, vertical centre y, width w (all
    // in percent), thickness t in percent of the frame height.
    const hbar = (x, y, w, t, color) =>
        '<rect x="' + X(x) + '" y="' + Y(y - t / 2) + '" width="' + X(w) +
        '" height="' + Y(t) + '" rx="' + (Y(t) / 2) + '" fill="' +
        (color || "#666") + '"/>';
    // Vertical text bar (a rotated title): horizontal centre x, from y1
    // to y2, thickness t in percent of the frame width.
    const vbar = (x, y1, y2, t, color) =>
        '<rect x="' + X(x - t / 2) + '" y="' + Y(y1) + '" width="' + X(t) +
        '" height="' + Y(y2 - y1) + '" rx="' + (X(t) / 2) + '" fill="' +
        (color || "#666") + '"/>';
    // Bottom-up darkening for photos with a caption overlay.
    const fade = (x, y, w, h) => {
        const gid = "tplfade" + (++_svgUid);
        defs.push('<linearGradient id="' + gid +
            '" x1="0" y1="1" x2="0" y2="0">' +
            '<stop offset="0" stop-color="#000" stop-opacity="0.75"/>' +
            '<stop offset="1" stop-color="#000" stop-opacity="0"/>' +
            "</linearGradient>");
        return pRect(x, y, w, h, "url(#" + gid + ")");
    };

    const svg = (body) =>
        '<svg viewBox="0 0 ' + W + " " + H +
        '" xmlns="http://www.w3.org/2000/svg">' +
        (defs.length ? "<defs>" + defs.join("") + "</defs>" : "") +
        body + "</svg>";

    const TITLE = 3.2;   // title bar thickness (percent)
    const DESC = 1.8;    // caption bar thickness (percent)

    return {
        W, H, photoUrl, fx, fy, X, Y, photoAt, photo, clipPoly, clipPath,
        bg, fullPhoto, panel, box, lines, pPhoto, pRect, pPanel, hbar, vbar,
        fade, svg, TITLE, DESC,
    };
}
