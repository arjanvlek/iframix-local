// Previews of the 16:9 catalog (mcol_1..5 / mrow_1..4), drawn on the
// original 100x60 grid. Returns undefined for an unknown id.

function _preview16x9(k, id) {
    const {photoUrl, photo, bg, fullPhoto, panel, box, lines, svg} = k;
    // 16:9 catalog. mcol_1..5 (display in landscape) and mrow_1..4
    // (display in portrait) per the override block in
    // webapp/index.html: split layout for 1/2, full-photo overlay
    // for 3/4/5.
    switch (id) {
        case 1: // photo left half, text right half
            return svg(
                bg("#f5f5f5")
                + panel(50, 0, 50, 60)
                + photo(0, 0, 50, 60)
                + lines(75, 26, 28, 2)
            );
        case 2: // photo right half, text left half
            return svg(
                bg("#f5f5f5")
                + panel(0, 0, 50, 60)
                + photo(50, 0, 50, 60)
                + lines(25, 26, 28, 2)
            );
        case 3: // full photo + caption card top-left
            return svg(
                (photoUrl ? fullPhoto() : bg("#9e9e9e"))
                + box(6, 8, 36, 18, "#e8e8e8")
                + lines(24, 13, 24, 2, "#666")
            );
        case 4: // full photo + caption card bottom-right
            return svg(
                (photoUrl ? fullPhoto() : bg("#9e9e9e"))
                + box(58, 34, 36, 18, "#e8e8e8")
                + lines(76, 39, 24, 2, "#666")
            );
        case 5: // full photo + translucent caption bottom-left
            return svg(
                (photoUrl ? fullPhoto() : bg("#9e9e9e"))
                + box(6, 38, 32, 14, "rgba(255,255,255,0.85)")
                + lines(22, 41, 20, 2, "#666")
            );
    }
}
