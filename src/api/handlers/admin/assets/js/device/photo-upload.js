// Photos tab: dropzone uploads (asset/upload, then one setMedia).

/* ---- upload (dropzone) ---- */

async function handleFiles(view, fileList) {
    const files = Array.from(fileList || []).filter(
        (f) => /^image\//.test(f.type) || /\.(jpe?g|png|gif|webp|heic)$/i
            .test(f.name));
    if (!files.length) return;
    const deviceId = view.dataset.deviceId;
    const state = getState(deviceId);
    const kind = state.kind;
    const dz = $(".dropzone", view);
    const title = $(".dz-title", view);
    const origTitle = title.textContent;
    dz.classList.add("busy");

    // Upload sequentially (one file at a time) to avoid overwhelming the
    // server when many photos are selected. Mirrors how the native app
    // uploads photos one by one.
    const assetIds = [];
    try {
        for (const [idx, file] of files.entries()) {
            title.textContent = "Uploading " + (idx + 1) + "/" +
                files.length + "…";
            const fd = new FormData();
            fd.append("file", file);
            fd.append("key", file.name);
            const suffix =
                (file.name.split(".").pop() || "jpg").toLowerCase();
            fd.append("x:suffix", suffix);
            const r = await fetch("/api/user/asset/upload",
                {method: "POST", body: fd});
            const data = await r.json();
            if (data && data.code === 1 && data.data && data.data.id) {
                assetIds.push(data.data.id);
            } else {
                throw new Error("upload rejected for " + file.name);
            }
        }
        const data = await postJSON("/api/ipad/media/setMedia", {
            device_id: parseInt(deviceId, 10),
            asset_ids: assetIds,
            type: kind,
        });
        if (data.code === 1) {
            toast(assetIds.length +
                (kind === "ai" ? " Gallery Mode photo" : " photo") +
                (assetIds.length > 1 ? "s" : "") + " added");
            loadPhotos(view);
        } else {
            toast("setMedia failed: " + (data.msg || "?"), true);
        }
    } catch (e) {
        toast("Upload failed: " + e, true);
    } finally {
        dz.classList.remove("busy");
        title.textContent = origTitle;
    }
}
