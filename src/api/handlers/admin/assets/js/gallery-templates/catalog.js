// Gallery Mode template catalogs: which layouts the display can
// render for its aspect, orientation and served webapp version, and
// how it treats a stored (template_type, template_id) pair.

//
// The modal keeps the design's layout (large live preview left, named
// option list right) but the catalog is the real one the display
// renders, so every option offered here is a value the display can
// actually show:
//
//   * 4:3 displays use the webapp's inline template engine. Webapp
//     2.3.8 ships 8 layouts for a display mounted in landscape and 7 for
//     a display mounted in portrait (2.3.1–2.3.5 shipped 10 + 10, kept
//     below as TPL_META_4X3_LEGACY for the version-aware branch).
//   * 16:9 displays use the static ``mcol_1..5`` (landscape) /
//     ``mrow_1..4`` (portrait) classes.
//
// ``template_type`` is the DISPLAY orientation (1 = landscape, 2 =
// portrait), not the photo's: the webapp selects its catalog from
// ``window.orientation`` and ignores a stored ``template_id`` whose
// ``template_type`` does not match that orientation (verified on an
// iPad 4 with webapp 2.3.8, see docs/gallery-mode-templates-2.3.8.md
// §1). The picker therefore reads the orientation from the device
// view's ``data-orientation`` (derived server-side from the session's
// width/height) and always saves ``template_type`` for that
// orientation. Names come from the bundle's catalog; the descriptions
// describe what the display really renders (two bundle names are
// misleading — "Left Sidebar" puts its sidebar on the right and
// "Right Spine" its spine on the left).

const TPL_META_4X3_LANDSCAPE = [
    {name: "Left bookend", desc: "Beige sidebar left with the date rotated, photo right with a caption strip at its foot"},
    {name: "Split canvas", desc: "Off-white caption panel left (40%), photo right"},
    {name: "Asymmetric base", desc: "Photo on top, beige caption row below with a dark-green date block at the right"},
    {name: "Cross boundary", desc: "Photo on top, black rotated date ribbon crossing into the white band, caption right of it"},
    {name: "Dark card", desc: "Full photo with a dark gold-trimmed caption card bottom-left"},
    {name: "Legacy top cover", desc: "Photo on top, centred date and caption below"},
    {name: "Legacy bottom left", desc: "Photo on top, left-aligned caption above the date"},
    {name: "Legacy side ribbon", desc: "Photo left (75%), white column right with the date and caption rotated"},
];
const TPL_META_4X3_PORTRAIT = [
    {name: "Classic bottom", desc: "Photo on top (70%), left-aligned serif date and caption below"},
    {name: "Magazine top", desc: "Photo on top, beige band below with the date left and the caption right of a thin rule"},
    {name: "Left sidebar", desc: "Photo left (75%) with a dark fade, beige sidebar right with the date rotated"},
    {name: "Overlap card", desc: "Full photo, red rotated date pill hanging from the top-left, white caption card bottom-right"},
    {name: "Cinematic fade", desc: "Photo on top, black rotated date ribbon crossing into the white band, caption right of it"},
    {name: "Right spine", desc: "Beige spine left (25%) with the date rotated and the caption at its foot, photo right"},
    {name: "Glass pillar", desc: "Full photo, dark centre pillar with the date rotated, white caption card across the lower third"},
];
// Webapp 2.3.1–2.3.5 catalog (10 per orientation), offered when the
// server is started with ``--webapp-version`` older than 2.3.8 (see
// legacy4x3Catalog()). The names are the landscape ones; the bundle's
// portrait names differed (Diagonal Cut, The Chevron, Parallelogram,
// Classic Bottom, Magazine Top, Left Sidebar, Overlap Card, Cinematic
// Fade, Right Spine, Glass Pillar).
const TPL_META_4X3_LEGACY = [
    {name: "Left bookend", desc: "Sidebar left, photo right with caption strip"},
    {name: "Split canvas", desc: "Caption panel left, photo right"},
    {name: "Corner cut", desc: "Photo with a diagonal caption area below"},
    {name: "Asymmetric base", desc: "Photo on top, captions below"},
    {name: "Cross boundary", desc: "Photo with an overlapping block"},
    {name: "Dark card", desc: "Full photo with a dark caption card"},
    {name: "Side arch", desc: "Caption left, photo right behind an arch"},
    {name: "Top cover", desc: "Photo on top, centered caption below"},
    {name: "Bottom left", desc: "Photo on top, caption bottom-left"},
    {name: "Side ribbon", desc: "Photo left, caption ribbon right"},
];
const TPL_META_16X9_H = [
    {name: "Photo left", desc: "Photo on the left, caption panel right"},
    {name: "Photo right", desc: "Photo on the right, caption panel left"},
    {name: "Overlay top-left", desc: "Full photo, caption card top-left"},
    {name: "Overlay bottom-right", desc: "Full photo, caption card bottom-right"},
    {name: "Overlay bottom-left", desc: "Full photo, translucent caption bottom-left"},
];
// mrow_1..4 (16:9 display in portrait) reuse the first four designs.
const TPL_META_16X9_V = TPL_META_16X9_H.slice(0, 4);

// ``template_type`` value the display expects for a device view:
// 1 when the display is mounted in landscape, 2 in portrait.
function displayTemplateType(view) {
    return (view && view.dataset && view.dataset.orientation === "portrait")
        ? 2 : 1;
}

// The webapp version this server serves to the displays (from the
// ``--webapp-version`` flag; rendered on <body data-webapp-version>).
// The 4:3 catalog changed in 2.3.8, so the picker must follow it.
function servedWebappVersion() {
    return (document.body && document.body.dataset.webappVersion) || "";
}

function _versionAtLeast(version, minimum) {
    const a = String(version || "").split(".").map((n) => parseInt(n, 10) || 0);
    const b = String(minimum).split(".").map((n) => parseInt(n, 10) || 0);
    for (let i = 0; i < Math.max(a.length, b.length); i++) {
        const x = a[i] || 0, y = b[i] || 0;
        if (x !== y) return x > y;
    }
    return true;
}

// True when the served bundle still has the 2.3.1–2.3.5 4:3 catalog
// (10 layouts per orientation). An unknown version is treated as the
// current bundle.
function legacy4x3Catalog() {
    const v = servedWebappVersion();
    return !!v && !_versionAtLeast(v, "2.3.8");
}

function templateCatalog(aspect, templateType) {
    if (aspect === "4x3") {
        if (legacy4x3Catalog()) return TPL_META_4X3_LEGACY;
        return templateType === 2 ? TPL_META_4X3_PORTRAIT
                                  : TPL_META_4X3_LANDSCAPE;
    }
    return templateType === 2 ? TPL_META_16X9_V : TPL_META_16X9_H;
}

// How the display treats a stored (template_type, template_id) pair:
//   {kind: "auto"}      — no template saved, the display picks at random
//   {kind: "mismatch"}  — saved for the other orientation; the display
//                         ignores the id (random)
//   {kind: "clamped", shows: M} — id beyond the catalog; the display
//                         renders style M (the last one)
//   {kind: "ok"}        — rendered as saved
function templateEffect(aspect, templateType, id, storedType) {
    if (!id) return {kind: "auto"};
    if (storedType && storedType !== templateType) return {kind: "mismatch"};
    const cat = templateCatalog(aspect, templateType);
    if (id > cat.length) return {kind: "clamped", shows: cat.length};
    return {kind: "ok"};
}

// Name for the chip on a Gallery Mode tile. ``storedType`` is the
// template_type saved with the photo.
function templateChipName(aspect, templateType, id, storedType) {
    const cat = templateCatalog(aspect, templateType);
    const fx = templateEffect(aspect, templateType, id, storedType);
    if (fx.kind === "mismatch") return "Auto (orientation mismatch)";
    if (fx.kind === "clamped") {
        return "Style " + id + " (shows as " + cat[fx.shows - 1].name + ")";
    }
    if (id >= 1 && id <= cat.length) return cat[id - 1].name;
    return "Auto";
}

const _COUNT_WORDS = ["", "one", "two", "three", "four", "five", "six",
                      "seven", "eight", "nine", "ten"];

function _templatePickerSpec(aspect, templateType) {
    const orient = templateType === 2 ? "portrait" : "landscape";
    const count = templateCatalog(aspect, templateType).length;
    return {
        count,
        hint: "Display is mounted in " + orient + " · " +
            (_COUNT_WORDS[count] || count) + " templates suit a " +
            (aspect === "4x3" ? "4:3" : "16:9") + " display in " +
            orient + ".",
    };
}
