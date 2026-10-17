// Full-resolution lightbox for normal photos.

function openLightbox(url) {
    const lb = document.getElementById("lightbox");
    $("img", lb).src = url;
    lb.classList.add("open");
}
function closeLightbox() {
    const lb = document.getElementById("lightbox");
    lb.classList.remove("open");
    $("img", lb).src = "";
}
