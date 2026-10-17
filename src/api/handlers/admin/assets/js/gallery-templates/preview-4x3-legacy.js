// Previews of the webapp 2.3.1–2.3.5 4:3 catalog (10 layouts), drawn
// on the original 100x60 grid. Returns undefined for an unknown id.

function _preview4x3Legacy(k, id) {
    const {photoUrl, fx, fy, photo, clipPoly, clipPath, bg, fullPhoto,
        panel, lines, svg} = k;
    // Webapp 2.3.1–2.3.5: the 10 entries of the ``pq``/``mq`` catalogs.
    switch (id) {
        case 1: // Left bookend
            return svg(
                bg("#f5f5f5")
                + panel(0, 0, 25, 60)
                + photo(25, 0, 75, 60)
                + '<rect x="' + fx(25) + '" y="' + fy(44) +
                  '" width="' + fx(75) + '" height="' + fy(16) +
                  '" fill="rgba(0,0,0,0.45)"/>'
                + lines(62, 50, 40, 2, "#fff")
                + lines(8, 28, 14, 2, "#999")
            );
        case 2: // Split canvas
            return svg(
                bg("#f5f5f5")
                + panel(0, 0, 40, 60)
                + photo(40, 0, 60, 60)
                + lines(20, 28, 26, 2)
            );
        case 3: { // Corner cut
            const cid = clipPoly(
                [[0, 0], [100, 0], [100, 30], [0, 40]]);
            return svg(
                bg("#f5f5f5")
                + photo(0, 0, 100, 40, cid)
                + lines(50, 47, 50, 2)
            );
        }
        case 4: // Asymmetric base
            return svg(
                bg("#f5f5f5")
                + photo(0, 0, 100, 43)
                + lines(30, 50, 30, 2)
                + lines(70, 50, 24, 2)
            );
        case 5: // Cross boundary
            return svg(
                bg("#f5f5f5")
                + photo(0, 0, 100, 45)
                + '<rect x="' + fx(55) + '" y="' + fy(32) +
                  '" width="' + fx(35) + '" height="' + fy(18) +
                  '" fill="#5a5a5a"/>'
                + lines(20, 53, 22, 1)
            );
        case 6: // Dark card
            return svg(
                (photoUrl ? fullPhoto() : bg("#9e9e9e"))
                + '<rect x="' + fx(20) + '" y="' + fy(38) +
                  '" width="' + fx(60) + '" height="' + fy(14) +
                  '" rx="2" fill="#333"/>'
                + lines(50, 42, 36, 2, "#cfcfcf")
            );
        case 7: { // Side arch
            const d = "M " + fx(38) + "," + fy(0) +
                " L " + fx(100) + "," + fy(0) +
                " L " + fx(100) + "," + fy(60) +
                " L " + fx(38) + "," + fy(60) +
                " Q " + fx(18) + "," + fy(30) +
                " " + fx(38) + "," + fy(0) + " Z";
            const cid = clipPath(d);
            return svg(
                bg("#f5f5f5")
                + panel(0, 0, 38, 60)
                + photo(18, 0, 82, 60, cid)
                + lines(13, 28, 18, 2)
            );
        }
        case 8: // Top cover
            return svg(
                bg("#f5f5f5")
                + photo(0, 0, 100, 45)
                + lines(50, 51, 50, 2)
            );
        case 9: // Bottom left
            return svg(
                bg("#f5f5f5")
                + photo(0, 0, 100, 45)
                + lines(20, 51, 28, 2)
            );
        case 10: // Side ribbon
            return svg(
                bg("#f5f5f5")
                + photo(0, 0, 75, 60)
                + panel(75, 0, 25, 60)
                + lines(87, 18, 16, 4)
            );
    }
}
