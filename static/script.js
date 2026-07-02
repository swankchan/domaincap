const urlsInput = document.getElementById("urls");
const submitBtn = document.getElementById("submit");
const clearBtn = document.getElementById("clear");

// OS & Browser icons (Simple Icons, colorful brand logos)
const OS_ICONS = {
    windows: "/static/icons/microsoft.svg",
    macos: "/static/icons/apple.svg",
    linux: "/static/icons/linux.svg",
    iphone: "/static/icons/apple.svg",
    android: "/static/icons/android.svg",
};
const BROWSER_ICONS = {
    chrome: "/static/icons/googlechrome.svg",
    firefox: "/static/icons/firefox.svg",
    safari: "/static/icons/safari.svg",
    edge: "/static/icons/microsoftedge.svg",
};

// Browser support per OS (Safari only on macOS/iOS)
const OS_BROWSER_SUPPORT = {
    windows: ["chrome", "edge", "firefox"],
    macos: ["chrome", "edge", "firefox", "safari"],
    linux: ["chrome", "firefox"],
    iphone: ["safari", "chrome", "firefox"],
    android: ["chrome", "firefox"],
};

function updateBrowserOptions() {
    const os = document.getElementById("os")?.value;
    const browserSelect = document.getElementById("browser");
    if (!os || !browserSelect) return;

    const supported = OS_BROWSER_SUPPORT[os] || ["chrome"];
    const currentBrowser = browserSelect.value;

    // Clear and repopulate browser options
    browserSelect.innerHTML = "";
    for (const br of supported) {
        const option = document.createElement("option");
        option.value = br;
        option.textContent = br.charAt(0).toUpperCase() + br.slice(1);
        browserSelect.appendChild(option);
    }

    // Restore current browser if supported, otherwise set to first available
    if (supported.includes(currentBrowser)) {
        browserSelect.value = currentBrowser;
    } else if (supported.length > 0) {
        browserSelect.value = supported[0];
    }

    updateOptionIcons();
}

function updateOptionIcons() {
    const osEl = document.getElementById("os");
    const browserEl = document.getElementById("browser");
    const osIconEl = document.getElementById("os-icon");
    const browserIconEl = document.getElementById("browser-icon");
    const setIcon = (el, src) => {
        if (!el) return;
        if (src) {
            el.innerHTML = `<img src="${src}" alt="" width="20" height="20">`;
        } else {
            el.innerHTML = "";
        }
    };
    setIcon(osIconEl, OS_ICONS[osEl?.value]);
    setIcon(browserIconEl, BROWSER_ICONS[browserEl?.value]);
}

updateOptionIcons();
document.getElementById("os")?.addEventListener("change", updateBrowserOptions);
document.getElementById("browser")?.addEventListener("change", updateOptionIcons);

const progressEl = document.getElementById("progress");
const reportEl = document.getElementById("report");
const reportTotal = document.getElementById("total");
const reportValid = document.getElementById("valid-count");
const reportInvalid = document.getElementById("invalid-count");
const invalidListEl = document.getElementById("invalid-list");
const invalidUrlsEl = document.getElementById("invalid-urls");
const galleryEl = document.getElementById("gallery");
const screenshotsEl = document.getElementById("screenshots");

submitBtn.addEventListener("click", handleSubmit);
clearBtn.addEventListener("click", () => {
    urlsInput.value = "";
    reportEl.classList.add("hidden");
    galleryEl.classList.add("hidden");
});

async function handleSubmit() {
    const text = urlsInput.value.trim();
    if (!text) {
        alert("Please enter at least one URL");
        return;
    }

    submitBtn.disabled = true;
    progressEl.classList.remove("hidden");
    reportEl.classList.add("hidden");
    galleryEl.classList.add("hidden");

    const progressText = document.getElementById("progress-text");
    progressText.textContent = "Processing, please wait…";

    try {
        const os = document.getElementById("os").value;
        const browser = document.getElementById("browser").value;
        const headless = document.getElementById("headless").checked;

        const res = await fetch("/api/process", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ urls: text, os, browser, headless, watermark: document.getElementById("watermark").checked }),
        });

        if (!res.ok) {
            const errData = await res.json().catch(() => ({}));
            throw new Error(errData.error || "Processing failed");
        }

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split("\n\n");
            buffer = lines.pop() || "";
            for (const line of lines) {
                if (line.startsWith("data: ")) {
                    try {
                        const msg = JSON.parse(line.slice(6));
                        if (msg.type === "progress") {
                            progressText.textContent = `Processing URL ${msg.current} / ${msg.total}: ${msg.url}`;
                        } else if (msg.type === "done") {
                            displayResults(msg);
                        }
                    } catch (_) {}
                }
            }
        }
        if (buffer.startsWith("data: ")) {
            try {
                const msg = JSON.parse(buffer.slice(6));
                if (msg.type === "done") displayResults(msg);
            } catch (_) {}
        }
    } catch (err) {
        alert(err.message || "An error occurred, please try again later");
    } finally {
        submitBtn.disabled = false;
        progressEl.classList.add("hidden");
    }
}

function displayResults(data) {
    const { total, valid_count, invalid_count, results, os, browser } = data;

    reportTotal.textContent = total;
    reportValid.textContent = valid_count;
    reportInvalid.textContent = invalid_count;

    const invalidResults = results.filter((r) => !r.valid);
    if (invalidResults.length > 0) {
        invalidListEl.classList.remove("hidden");
        invalidUrlsEl.innerHTML = invalidResults
            .map(
                (r) =>
                    `<li>${escapeHtml(r.url)} <span class="error-msg">(${escapeHtml(r.error || "Invalid")})</span></li>`
            )
            .join("");
    } else {
        invalidListEl.classList.add("hidden");
    }

    const validResults = results.filter((r) => r.valid);
    screenshotsEl.innerHTML = validResults
        .map(
            (r) =>
                `<div class="screenshot-card">
                    <a href="${escapeHtml(r.url)}" target="_blank" rel="noopener">
                        <img src="${escapeHtml(r.screenshot)}" alt="${escapeHtml(r.url)}" loading="lazy">
                        <div class="url">${escapeHtml(r.url)}</div>
                    </a>
                </div>`
        )
        .join("");

    const envBadge = document.getElementById("env-badge");
    if (envBadge) {
        if (os && browser) {
            const osLabel = { windows: "Windows", macos: "macOS", linux: "Linux", iphone: "iPhone", android: "Android" }[os] || os;
            const browserLabel = browser.charAt(0).toUpperCase() + browser.slice(1);
            envBadge.textContent = `(${osLabel} · ${browserLabel})`;
        } else {
            envBadge.textContent = "";
        }
    }

    reportEl.classList.remove("hidden");
    galleryEl.classList.remove("hidden");
}

function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
}

// Tab switching
function switchTab(tabId) {
    document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
    document.querySelectorAll(".tab-panel").forEach((p) => p.classList.remove("active"));
    const btn = document.querySelector(`.tab[data-tab="${tabId}"]`);
    const panel = document.getElementById(`tab-${tabId}`);
    if (btn) btn.classList.add("active");
    if (panel) panel.classList.add("active");
}

document.querySelectorAll(".tab").forEach((btn) => {
    btn.addEventListener("click", () => switchTab(btn.dataset.tab));
});

// History search with wildcard (* = any chars, ? = single char) + pagination (10 per page)
const HISTORY_PAGE_SIZE = 10;
let historyCurrentPage = 0;

function buildSearchRegex(q) {
    if (!q) return null;
    const pattern = q
        .replace(/[.*+?^${}()|[\]\\]/g, (c) => (c === "*" || c === "?" ? c : "\\" + c))
        .replace(/\*/g, ".*")
        .replace(/\?/g, ".");
    return new RegExp(pattern, "i");
}

function updateHistoryDisplay() {
    const historySearch = document.getElementById("history-search");
    const paginationEl = document.getElementById("history-pagination");
    const historyRows = document.querySelectorAll("#tab-history tbody tr[data-url]");
    if (!historyRows.length) return;

    const q = (historySearch?.value || "").trim().toLowerCase();
    const re = buildSearchRegex(q);
    const visibleRows = [...historyRows].filter((r) => !re || re.test((r.dataset.url || "").toLowerCase()));

    const totalPages = Math.ceil(visibleRows.length / HISTORY_PAGE_SIZE);
    const showPagination = totalPages > 1;

    if (showPagination) {
        historyCurrentPage = Math.min(historyCurrentPage, totalPages - 1);
        const start = historyCurrentPage * HISTORY_PAGE_SIZE;
        const end = start + HISTORY_PAGE_SIZE;
        historyRows.forEach((r) => {
            const idx = visibleRows.indexOf(r);
            if (idx === -1) r.style.display = "none";
            else r.style.display = idx >= start && idx < end ? "" : "none";
        });

        paginationEl.classList.remove("hidden");
        paginationEl.innerHTML = `
            <button type="button" class="page-prev" ${historyCurrentPage === 0 ? "disabled" : ""}>Prev</button>
            <span class="page-info">Page ${historyCurrentPage + 1} / ${totalPages}</span>
            <button type="button" class="page-next" ${historyCurrentPage >= totalPages - 1 ? "disabled" : ""}>Next</button>
        `;
        paginationEl.querySelector(".page-prev")?.addEventListener("click", () => {
            if (historyCurrentPage > 0) {
                historyCurrentPage--;
                updateHistoryDisplay();
            }
        });
        paginationEl.querySelector(".page-next")?.addEventListener("click", () => {
            if (historyCurrentPage < totalPages - 1) {
                historyCurrentPage++;
                updateHistoryDisplay();
            }
        });
    } else {
        historyRows.forEach((r) => {
            r.style.display = visibleRows.includes(r) ? "" : "none";
        });
        paginationEl.classList.add("hidden");
    }
    if (typeof updateDeleteSelectedState === "function") updateDeleteSelectedState();
}

const historySearch = document.getElementById("history-search");
if (historySearch) {
    historySearch.addEventListener("input", () => {
        historyCurrentPage = 0;
        updateHistoryDisplay();
    });
    updateHistoryDisplay();
}

// Column visibility (History)
const COL_VIS_KEY = "domaincap_cols";
function getColumnVisibility() {
    try {
        const s = localStorage.getItem(COL_VIS_KEY);
        if (s) return JSON.parse(s);
    } catch (_) {}
    return {};
}
function setColumnVisibility(col, visible) {
    const v = getColumnVisibility();
    v[col] = visible;
    try { localStorage.setItem(COL_VIS_KEY, JSON.stringify(v)); } catch (_) {}
}
function applyColumnVisibility() {
    const v = getColumnVisibility();
    document.querySelectorAll("#columns-menu input[data-col]").forEach((cb) => {
        const col = cb.dataset.col;
        if (v[col] !== undefined) cb.checked = v[col];
        const visible = cb.checked;
        document.querySelectorAll(`#tab-history [data-col="${col}"]`).forEach((el) => {
            el.classList.toggle("col-hidden", !visible);
        });
    });
}
const columnsBtn = document.getElementById("columns-btn");
const columnsMenu = document.getElementById("columns-menu");
if (columnsBtn && columnsMenu) {
    columnsBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        columnsMenu.classList.toggle("hidden");
    });
    document.addEventListener("click", () => columnsMenu.classList.add("hidden"));
    columnsMenu.addEventListener("click", (e) => e.stopPropagation());
    columnsMenu.querySelectorAll("input[data-col]").forEach((cb) => {
        cb.addEventListener("change", () => {
            setColumnVisibility(cb.dataset.col, cb.checked);
            applyColumnVisibility();
        });
    });
    applyColumnVisibility();
}

// Delete history (single)
document.querySelectorAll(".btn-delete").forEach((btn) => {
    btn.addEventListener("click", async () => {
        const id = btn.dataset.id;
        if (!id || !confirm("Delete this record?")) return;
        btn.disabled = true;
        try {
            const res = await fetch(`/api/capture/${id}`, { method: "DELETE" });
            if (!res.ok) throw new Error("Delete failed");
            const row = btn.closest("tr");
            row?.remove();
            if (!document.querySelector("#tab-history tbody tr")) {
                window.location.href = "/?tab=history";
            } else {
                updateHistoryDisplay();
            }
        } catch (err) {
            alert(err.message || "Delete failed");
        } finally {
            btn.disabled = false;
        }
    });
});

// Multiple selection for deletion
function getSelectedIds() {
    return [...document.querySelectorAll("#tab-history .row-select:checked")].map((cb) => parseInt(cb.value, 10));
}

function updateDeleteSelectedState() {
    const btn = document.getElementById("delete-selected-btn");
    if (btn) btn.disabled = getSelectedIds().length === 0;
    const selectAll = document.getElementById("select-all");
    if (selectAll) {
        const visible = document.querySelectorAll("#tab-history tbody tr[data-id]");
        const visibleShown = [...visible].filter((r) => r.style.display !== "none");
        const checked = visibleShown.filter((r) => r.querySelector(".row-select:checked")).length;
        selectAll.checked = visibleShown.length > 0 && checked === visibleShown.length;
        selectAll.indeterminate = checked > 0 && checked < visibleShown.length;
    }
}

document.querySelectorAll("#tab-history .row-select").forEach((cb) => {
    cb.addEventListener("change", updateDeleteSelectedState);
});

const selectAllEl = document.getElementById("select-all");
if (selectAllEl) {
    selectAllEl.addEventListener("change", () => {
        const checked = selectAllEl.checked;
        document.querySelectorAll("#tab-history .row-select").forEach((cb) => {
            const row = cb.closest("tr");
            if (row && row.style.display !== "none") cb.checked = checked;
        });
        updateDeleteSelectedState();
    });
}

updateDeleteSelectedState();

const deleteSelectedBtn = document.getElementById("delete-selected-btn");
if (deleteSelectedBtn) {
    deleteSelectedBtn.addEventListener("click", async () => {
        const ids = getSelectedIds();
        if (!ids.length || !confirm(`Delete ${ids.length} selected record(s)?`)) return;
        deleteSelectedBtn.disabled = true;
        try {
            const res = await fetch("/api/capture/bulk-delete", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ ids }),
            });
            if (!res.ok) throw new Error("Delete failed");
            const data = await res.json().catch(() => ({}));
            ids.forEach((id) => {
                const row = document.querySelector(`#tab-history tr[data-id="${id}"]`);
                row?.remove();
            });
            if (!document.querySelector("#tab-history tbody tr")) {
                window.location.href = "/?tab=history";
            } else {
                updateHistoryDisplay();
            }
        } catch (err) {
            alert(err.message || "Delete failed");
        } finally {
            deleteSelectedBtn.disabled = false;
            updateDeleteSelectedState();
        }
    });
}
