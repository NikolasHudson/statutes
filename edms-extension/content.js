// Hudson EDMSpro content script — runs on Iowa EDMS docket pages and on the
// bundled demo page.
//
// It scrapes the docket, injects the per-row actions (preview / download / save)
// and the per-case controls, and asks the service worker to do anything that
// touches the network beyond this origin. It deliberately holds no credentials
// and makes no cross-origin request itself: the one fetch it does perform is for
// the filing PDF, same-origin, with the user's own court session — exactly the
// request their click on the link would have made.

(() => {
  // Display-only copy of the safety filter, used to flag a confidential case
  // type on the banner. v1 uploads nothing, so this decides nothing; it stays
  // deliberately BROADER than the server's list because over-reporting
  // "confidential" is the harmless direction to be wrong in.
  const FALLBACK_BLOCKED = {
    JD: "Juvenile delinquency",
    JV: "Juvenile",
    AD: "Adoption",
    DM: "Domestic / dissolution",
    GC: "Guardianship / conservatorship",
    CD: "Child in need of assistance",
    PB: "Probate",
  };

  const DEFAULT_SETTINGS = {
    crowdsource_opt_in: false,
    naming_template: "{date}_{case_num}_{doc_title}",
  };

  const state = {
    settings: { ...DEFAULT_SETTINGS },
    blocked: { ...FALLBACK_BLOCKED },
    meta: null,
    signedIn: false,
  };

  // ---------- shared helpers ----------

  // Settings come from the server — it needs them anyway to resolve a
  // destination, so a device-local copy could only ever be a second answer.
  // A failure here is not fatal: the save flow reads the authoritative values
  // server-side, and the only thing a stale copy affects is the preview text.
  async function loadSettings() {
    const resp = await sendBgMessage({ type: "cv:getSettings" });
    return resp?.ok ? resp.settings : { ...DEFAULT_SETTINGS };
  }

  async function loadBlockedList() {
    const resp = await sendBgMessage({ type: "cv:getSafety" });
    if (!resp?.ok || !Array.isArray(resp.safety?.blocked)) return { ...FALLBACK_BLOCKED };
    const map = {};
    for (const row of resp.safety.blocked) map[row.prefix] = row.label;
    return map;
  }

  async function loadSignedIn() {
    const resp = await sendBgMessage({ type: "cv:authStatus" });
    return Boolean(resp?.signedIn);
  }

  function openSettingsPage() {
    return sendBgMessage({ type: "cv:openSettings" });
  }

  function buildSignInBtn() {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "cv-signin";
    const label = () => {
      btn.innerHTML =
        '<svg viewBox="0 0 20 20" width="14" height="14" aria-hidden="true"><path fill="currentColor" d="M11 3h5a1 1 0 0 1 1 1v12a1 1 0 0 1-1 1h-5v-2h4V5h-4V3Zm-1 4 4 3-4 3v-2H3V9h7V7Z"/></svg>' +
        "<span>Sign in to Hudson EDMSpro</span>";
    };
    label();
    btn.title = "Sign in to Hudson — opens a Hudson window";
    btn.addEventListener("click", async (e) => {
      e.preventDefault();
      e.stopPropagation();
      btn.disabled = true;
      btn.innerHTML = "<span>Opening Hudson…</span>";
      const resp = await sendBgMessage({ type: "cv:signIn" });
      btn.disabled = false;
      if (resp?.ok) {
        // Re-run the whole injection so the row actions appear.
        showToast("Signed in to Hudson EDMSpro");
        window.location.reload();
      } else {
        label();
        showToast(resp?.error || "Sign-in failed");
      }
    });
    return btn;
  }

  function safetyCheck(meta) {
    const label = state.blocked[meta.prefix];
    return { blocked: Boolean(label), reason: label || null };
  }

  function sanitizeForFilename(s) {
    return (s || "")
      .replace(/[\\/:*?"<>|\r\n\t]+/g, " ")
      .replace(/\s+/g, " ")
      .trim()
      .replace(/\s/g, "-")
      .slice(0, 120);
  }

  function applyNamingConvention(template, meta, parts) {
    const docTitle = parts?.docTitle || "document";
    const docType = parts?.docType || "";
    const docketNum = parts?.docketNum || "";
    return template
      .replace("{date}", sanitizeForFilename(meta.filedDate || parts?.rowDate || "undated"))
      .replace("{case_num}", sanitizeForFilename(meta.caseNumber || "unknown"))
      .replace("{doc_title}", sanitizeForFilename(docTitle))
      .replace("{doc_type}", sanitizeForFilename(docType))
      .replace("{docket_num}", sanitizeForFilename(docketNum))
      .replace("{judge}", sanitizeForFilename(meta.judge))
      .replace("{county}", sanitizeForFilename(meta.county));
  }

  function sendBgMessage(payload) {
    return new Promise((resolve) => {
      if (!chrome?.runtime?.sendMessage) {
        resolve({ ok: false, error: "no chrome.runtime" });
        return;
      }
      chrome.runtime.sendMessage(payload, (resp) => {
        if (chrome.runtime.lastError) {
          resolve({ ok: false, error: chrome.runtime.lastError.message });
        } else {
          resolve(resp || { ok: false, error: "no response" });
        }
      });
    });
  }

  function requestDownloadLocal(url, filename) {
    return sendBgMessage({ type: "cv:downloadLocal", url, filename });
  }

  function showToast(text) {
    let host = document.querySelector(".cv-toast-host");
    if (!host) {
      host = document.createElement("div");
      host.className = "cv-toast-host";
      document.body.appendChild(host);
    }
    const t = document.createElement("div");
    t.className = "cv-toast";
    t.textContent = text;
    host.appendChild(t);
    requestAnimationFrame(() => t.classList.add("cv-toast--in"));
    setTimeout(() => {
      t.classList.remove("cv-toast--in");
      setTimeout(() => t.remove(), 250);
    }, 2600);
  }

  // ---------- demo-mode (existing prototype) ----------

  function scrapeMetadataDemo() {
    const root = document.querySelector("[data-cv-docket]") || document;
    const pick = (sel) => {
      const el = root.querySelector(`[data-cv-field="${sel}"]`);
      return el ? el.textContent.trim() : "";
    };

    const caseNumber = pick("case-number");
    const judge = pick("judge");
    const filedDate = pick("filed-date");
    const caption = pick("caption");
    const county = pick("county");
    const caseType = pick("case-type");
    const prefix = (caseNumber.match(/[A-Z]{2,3}/) || [""])[0].toUpperCase();

    return { caseNumber, judge, filedDate, caption, county, caseType, prefix };
  }

  function buildBanner(meta, safety, extras) {
    const banner = document.createElement("div");
    banner.className = `cv-banner ${safety.blocked ? "cv-banner--blocked" : "cv-banner--ok"}`;

    const left = document.createElement("div");
    left.className = "cv-banner__left";

    const dot = document.createElement("span");
    dot.className = "cv-banner__dot";

    const title = document.createElement("div");
    title.className = "cv-banner__title";
    title.textContent = safety.blocked
      ? `Public sharing blocked — ${safety.reason} case`
      : "Hudson EDMSpro is ready on this docket";

    const sub = document.createElement("div");
    sub.className = "cv-banner__sub";
    sub.textContent = safety.blocked
      ? "Confidential case type. Downloads stay on this device — v1 uploads nothing."
      : `${meta.caption || "Untitled case"} · ${meta.caseNumber || "no case #"} · ${meta.county || ""}`;

    const text = document.createElement("div");
    text.appendChild(title);
    text.appendChild(sub);

    left.appendChild(dot);
    left.appendChild(text);

    const right = document.createElement("div");
    right.className = "cv-banner__right";

    if (!state.signedIn) {
      right.appendChild(buildSignInBtn());
    } else if (extras?.downloadAllBtn) {
      // No contribution chip in v1: the opt-in still exists as a setting, but
      // nothing can act on it here, and a banner reading "Crowdsource: on" over
      // a docket that shares nothing would be a lie on a lawyer's screen.
      right.appendChild(extras.downloadAllBtn);
    }

    banner.appendChild(left);
    banner.appendChild(right);

    return banner;
  }

  function buildDownloadButtonDemo(rowEl, meta) {
    const docTitle = rowEl.dataset.cvDocTitle || "Document";
    const filename = applyNamingConvention(
      state.settings.naming_template,
      meta,
      { docTitle },
    ) + ".pdf";

    const wrap = document.createElement("div");
    wrap.className = "cv-action";

    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "cv-action__btn";
    btn.innerHTML = `
      <svg viewBox="0 0 20 20" width="14" height="14" aria-hidden="true">
        <path fill="currentColor" d="M5 3h7l4 4v10a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1Zm6 1.5V8h3.5L11 4.5Z"/>
      </svg>
      <span>Download</span>
    `;

    const tooltip = document.createElement("div");
    tooltip.className = "cv-action__tip";
    const tipRow = document.createElement("div");
    tipRow.className = "cv-tip__row";
    const tipLabel = document.createElement("span");
    tipLabel.textContent = "Filename";
    const tipValue = document.createElement("strong");
    tipValue.textContent = filename;
    tipRow.appendChild(tipLabel);
    tipRow.appendChild(tipValue);
    tooltip.appendChild(tipRow);

    btn.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      simulateDownload(btn, filename);
    });

    wrap.appendChild(btn);
    wrap.appendChild(tooltip);
    return wrap;
  }

  function simulateDownload(btn, filename) {
    btn.disabled = true;
    btn.classList.add("cv-action__btn--working");
    btn.innerHTML = `
      <span class="cv-spinner" aria-hidden="true"></span>
      <span>Downloading…</span>
    `;

    setTimeout(() => {
      btn.classList.remove("cv-action__btn--working");
      btn.classList.add("cv-action__btn--done");
      btn.innerHTML = `
        <svg viewBox="0 0 20 20" width="14" height="14" aria-hidden="true">
          <path fill="currentColor" d="m8.5 13.5-3-3 1.4-1.4L8.5 10.7l5.6-5.6L15.5 6.5l-7 7Z"/>
        </svg>
        <span>Downloaded</span>
      `;
      showToast(`Downloaded ${filename}`);
      setTimeout(() => {
        btn.disabled = false;
        btn.classList.remove("cv-action__btn--done");
        btn.innerHTML = `
          <svg viewBox="0 0 20 20" width="14" height="14" aria-hidden="true">
            <path fill="currentColor" d="M5 3h7l4 4v10a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1Zm6 1.5V8h3.5L11 4.5Z"/>
          </svg>
          <span>Download</span>
        `;
      }, 2200);
    }, 900);
  }

  async function injectDemo() {
    const meta = scrapeMetadataDemo();
    if (!meta.caseNumber) return false;
    state.meta = meta;
    const safety = safetyCheck(meta);

    const dock = document.querySelector("[data-cv-docket]");
    if (!dock) return false;

    if (!dock.querySelector(".cv-banner")) {
      dock.insertBefore(buildBanner(meta, safety), dock.firstChild);
    }

    if (state.signedIn) {
      const rows = dock.querySelectorAll("[data-cv-filing-row]");
      rows.forEach((row) => {
        if (row.querySelector(".cv-action")) return;
        const slot = row.querySelector("[data-cv-action-slot]") || row;
        slot.appendChild(buildDownloadButtonDemo(row, meta));
      });
    }
    return true;
  }

  // ---------- real EDMS docket page ----------

  function findDocketTable() {
    const tables = document.querySelectorAll("table");
    for (const t of tables) {
      const firstCell = t.rows?.[0]?.cells?.[0];
      if (firstCell && /File\s*Date/i.test(firstCell.textContent || "")) {
        return t;
      }
    }
    return null;
  }

  function findCaseHeaderTable() {
    const tables = document.querySelectorAll("table");
    for (const t of tables) {
      const txt = (t.innerText || "").trim();
      if (/^Case\s*Number\s*:/i.test(txt)) return t;
    }
    return null;
  }

  function scrapeMetadataRealEdms() {
    let caseNumber = "";
    let caption = "";
    let judge = "";
    let county = "";
    let caseType = "";
    let filedDate = "";

    // Prefer the hidden form1 inputs — most reliable for the case number.
    try {
      const form = document.forms?.form1;
      if (form?.caseNumber?.value) caseNumber = form.caseNumber.value.trim();
    } catch (_) {
      /* ignore */
    }

    const header = findCaseHeaderTable();
    if (header) {
      const text = header.innerText || "";
      const m1 = text.match(/Case\s*Number\s*:\s*([A-Z0-9]+)/i);
      if (!caseNumber && m1) caseNumber = m1[1].trim();
      const m2 = text.match(/Case\s*Title\s*:\s*(.+)/i);
      if (m2) caption = m2[1].trim();
    }

    // The "details" table generally sits adjacent to the header table.
    const tables = [...document.querySelectorAll("table")];
    for (const t of tables) {
      const txt = (t.innerText || "").trim();
      if (/County\s*:/i.test(txt) && /Case\s*Type\s*:/i.test(txt)) {
        const mc = txt.match(/County\s*:\s*([^\n\r]+)/i);
        if (mc) county = mc[1].trim();
        const mt = txt.match(/Case\s*Type\s*:\s*(.+?)(?:\s{2,}|\s*Judge\s*:|\n|$)/i);
        if (mt) caseType = mt[1].trim();
        const mj = txt.match(/Judge\s*:\s*([^\n\r]*)/i);
        if (mj) judge = mj[1].trim();
        const mo = txt.match(/Opened\s*:\s*([\d-]+)/i);
        if (mo) filedDate = mo[1].trim();
        break;
      }
    }

    const prefix = (caseNumber.match(/^[A-Z]+/) || [""])[0].toUpperCase();
    return { caseNumber, caption, judge, county, caseType, filedDate, prefix };
  }

  function parseRow(tr) {
    const anchor = tr.querySelector('a[href*="GetNotifierDocument"]');
    if (!anchor) return null;

    const dateCell = tr.cells?.[0];
    const docketCell = tr.cells?.[1];
    const bodyCell = tr.cells?.[2];
    if (!dateCell || !docketCell || !bodyCell) return null;

    const dateRaw = (dateCell.innerText || "").trim();
    // dateRaw like "05-01-2026 11:49:00 AM\nCourt"
    const [dateLine, ...filerLines] = dateRaw.split(/\r?\n/);
    const rowDate = (dateLine.match(/^\d{2}-\d{2}-\d{4}/) || [""])[0];
    const filerShort = filerLines.join(" ").trim();

    const docketNum = (docketCell.innerText || "").trim();
    const docType = (anchor.textContent || "").trim();

    let description = "";
    const descFont = bodyCell.querySelector(
      'table tr:first-child td font[color="000000"]',
    );
    if (descFont) {
      description = (descFont.innerText || "").replace(/\s+/g, " ").trim();
    }

    let fullFiler = "";
    const filerRow = bodyCell.querySelector(
      "table tr:nth-child(2) td font",
    );
    if (filerRow) {
      fullFiler = (filerRow.innerText || "").replace(/^Filed\s*by\s*:\s*/i, "").trim();
    }

    const pdfUrl = anchor.href; // resolved to absolute by the browser
    const cmsDocId = (pdfUrl.match(/cmsDocId=(\d+)/) || [, ""])[1];

    return {
      tr,
      anchor,
      bodyCell,
      rowDate,
      filerShort,
      docketNum,
      docType,
      description,
      fullFiler,
      pdfUrl,
      cmsDocId,
    };
  }

  function buildFilename(meta, row) {
    const title = row.description || row.docType || "document";
    const convention =
      state.settings.naming_template || DEFAULT_SETTINGS.naming_template;
    const base = applyNamingConvention(convention, meta, {
      docTitle: title,
      docType: row.docType,
      docketNum: row.docketNum,
      rowDate: row.rowDate,
    });
    return (base || "document") + ".pdf";
  }

  // SVG icon strings (currentColor so the button color schemes can recolor them).
  const ICON_DOWNLOAD =
    '<svg viewBox="0 0 20 20" width="14" height="14" aria-hidden="true"><path fill="currentColor" d="M10 3v9.2l3.1-3.1 1.4 1.4-5.5 5.5-5.5-5.5 1.4-1.4 3.1 3.1V3h2Zm-6 14h12v2H4v-2Z"/></svg>';
  const ICON_CHECK =
    '<svg viewBox="0 0 20 20" width="12" height="12" aria-hidden="true"><path fill="currentColor" d="m8.5 13.5-3-3 1.4-1.4L8.5 10.7l5.6-5.6L15.5 6.5l-7 7Z"/></svg>';
  const ICON_OPEN =
    '<svg viewBox="0 0 20 20" width="10" height="10" aria-hidden="true"><path fill="currentColor" d="M12 3h5v5h-2V6.4l-7.3 7.3-1.4-1.4L13.6 5H12V3Zm-7 4h4v2H7v8h8v-4h2v6H5V7Z"/></svg>';
  const ICON_EYE =
    '<svg viewBox="0 0 20 20" width="14" height="14" aria-hidden="true"><path fill="currentColor" d="M10 4c-4 0-7.3 2.6-9 6 1.7 3.4 5 6 9 6s7.3-2.6 9-6c-1.7-3.4-5-6-9-6Zm0 10a4 4 0 1 1 0-8 4 4 0 0 1 0 8Zm0-2a2 2 0 1 0 0-4 2 2 0 0 0 0 4Z"/></svg>';
  const ICON_GEAR =
    '<svg viewBox="0 0 20 20" width="13" height="13" aria-hidden="true"><path fill="currentColor" d="m12.1 2.2.4 2a6 6 0 0 1 1.5.9l2-.6 1.5 2.5-1.5 1.5a6 6 0 0 1 0 1.8l1.5 1.6L16 14.4l-2-.6a6 6 0 0 1-1.5.9l-.4 2H7.9l-.4-2A6 6 0 0 1 6 13.8l-2 .6L2.5 12l1.5-1.5a6 6 0 0 1 0-1.8L2.5 7.1 4 4.6l2 .6c.5-.4 1-.7 1.5-.9l.4-2h4.2ZM10 7a3 3 0 1 0 0 6 3 3 0 0 0 0-6Z"/></svg>';

  function setIconBtnState(btn, mode, icon, title) {
    btn.classList.remove(
      "cv-iconbtn--working",
      "cv-iconbtn--done",
      "cv-iconbtn--error",
    );
    btn.disabled = mode === "working";
    if (mode === "working") {
      btn.classList.add("cv-iconbtn--working");
      btn.innerHTML = '<span class="cv-spinner" aria-hidden="true"></span>';
    } else if (mode === "done") {
      btn.classList.add("cv-iconbtn--done");
      btn.innerHTML = ICON_CHECK;
    } else if (mode === "error") {
      btn.classList.add("cv-iconbtn--error");
      btn.innerHTML = "!";
    } else {
      btn.innerHTML = icon;
    }
    if (title) btn.title = title;
  }

  function buildLocalDownloadBtn(meta, row) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "cv-iconbtn cv-iconbtn--local";
    setIconBtnState(btn, "idle", ICON_DOWNLOAD, `Download PDF · ${row.docType || ""}`.trim());

    btn.addEventListener("click", async (e) => {
      e.preventDefault();
      e.stopPropagation();
      const filename = buildFilename(meta, row);
      setIconBtnState(btn, "working", ICON_DOWNLOAD);
      const resp = await requestDownloadLocal(row.pdfUrl, filename);
      if (resp?.ok) {
        setIconBtnState(btn, "done", ICON_DOWNLOAD, "Downloaded");
        showToast(`Downloaded ${filename}`);
        setTimeout(() => setIconBtnState(btn, "idle", ICON_DOWNLOAD, "Download PDF"), 2200);
      } else {
        setIconBtnState(btn, "error", ICON_DOWNLOAD, resp?.error || "Download failed");
        showToast(`Download failed: ${resp?.error || "unknown error"}`);
        setTimeout(() => setIconBtnState(btn, "idle", ICON_DOWNLOAD, "Download PDF"), 2500);
      }
    });
    return btn;
  }

  function buildPreviewBtn(meta, row) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "cv-iconbtn cv-iconbtn--preview";
    setIconBtnState(btn, "idle", ICON_EYE, "Preview this filing");

    btn.addEventListener("click", async (e) => {
      e.preventDefault();
      e.stopPropagation();
      setIconBtnState(btn, "working", ICON_EYE);

      // Fetched HERE, not in the service worker: this origin is the court's, so
      // the request carries the user's own EDMS session by construction. Hudson
      // is never contacted — a preview is the same request their click on the
      // link would have made.
      let bytes;
      try {
        const resp = await fetch(row.pdfUrl, { credentials: "include" });
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        bytes = Array.from(new Uint8Array(await resp.arrayBuffer()));
      } catch (err) {
        setIconBtnState(btn, "error", ICON_EYE, "Couldn't load the PDF");
        showToast(`Preview failed: ${err.message}`);
        setTimeout(() => setIconBtnState(btn, "idle", ICON_EYE, "Preview this filing"), 2500);
        return;
      }

      // Sent from inside the click handler on purpose: Chrome only lets the
      // side panel be opened while a user gesture is still in scope, and the
      // gesture has to survive this one hop to the service worker.
      const opened = await sendBgMessage({
        type: "cv:openPreview",
        bytes,
        title: row.description || row.docType || "Filing",
        meta: {
          pdfUrl: row.pdfUrl,
          filename: buildFilename(meta, row),
        },
      });

      setIconBtnState(btn, "idle", ICON_EYE, "Preview this filing");
      if (!opened?.ok) {
        showToast(opened?.error || "Couldn't open the preview panel.");
      }
    });
    return btn;
  }

  function buildRowActions(meta, row) {
    const wrap = document.createElement("div");
    wrap.className = "cv-actions";
    // Preview first: on a long docket the question is almost always "what IS
    // this?" before "do I want a copy?".
    wrap.appendChild(buildPreviewBtn(meta, row));
    wrap.appendChild(buildLocalDownloadBtn(meta, row));
    return wrap;
  }

  function dedupeRows(rows) {
    const seen = new Set();
    return rows.filter((r) => {
      const key = r.cmsDocId || r.pdfUrl;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
  }

  function uniqueZipName(used, base) {
    if (!used.has(base)) {
      used.add(base);
      return base;
    }
    const idx = base.lastIndexOf(".");
    const stem = idx >= 0 ? base.slice(0, idx) : base;
    const ext = idx >= 0 ? base.slice(idx) : "";
    let i = 1;
    while (true) {
      const candidate = `${stem} (${i})${ext}`;
      if (!used.has(candidate)) {
        used.add(candidate);
        return candidate;
      }
      i += 1;
    }
  }

  async function downloadAllAsZip(meta, allRows, btn, setLabel, restoreLabel) {
    const rows = dedupeRows(allRows);
    const total = rows.length;
    if (!total) {
      showToast("No documents to download.");
      return;
    }
    if (!window.EdmsZip) {
      showToast("Zip builder isn't loaded — reload the extension.");
      return;
    }

    btn.disabled = true;
    setLabel(`Downloading 0 / ${total}…`);

    const used = new Set();
    const results = [];
    let done = 0;
    let failed = 0;
    const CONCURRENCY = 4;
    let cursor = 0;
    const worker = async () => {
      while (cursor < rows.length) {
        const i = cursor++;
        const row = rows[i];
        const name = uniqueZipName(used, buildFilename(meta, row));
        try {
          const resp = await fetch(row.pdfUrl, { credentials: "include" });
          if (!resp.ok) {
            failed += 1;
          } else {
            const bytes = new Uint8Array(await resp.arrayBuffer());
            results.push({ name, data: bytes });
            done += 1;
          }
        } catch (_err) {
          failed += 1;
        }
        setLabel(`Downloading ${done + failed} / ${total}…`);
      }
    };
    await Promise.all(Array.from({ length: Math.min(CONCURRENCY, total) }, worker));

    if (!results.length) {
      btn.disabled = false;
      restoreLabel();
      showToast(`All ${total} downloads failed.`);
      return;
    }

    setLabel(`Building zip…`);
    const blob = window.EdmsZip.build(results);
    const today = new Date().toISOString().slice(0, 10);
    const zipName = `${(meta.caseNumber || "filings").replace(/[^A-Za-z0-9_-]/g, "")}_${today}.zip`;

    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = zipName;
    a.style.display = "none";
    document.body.appendChild(a);
    a.click();
    setTimeout(() => {
      URL.revokeObjectURL(a.href);
      a.remove();
    }, 1000);

    btn.disabled = false;
    restoreLabel();
    showToast(
      failed ? `Saved ${done} into ${zipName}, ${failed} failed.` : `Saved ${done} files into ${zipName}.`,
    );
  }

  // One action left in v1, so this is a button rather than the old split
  // dropdown (zip / save-all-to-OneDrive).
  function buildDownloadAllBtn(meta, allRows) {
    const wrap = document.createElement("div");
    wrap.className = "cv-dlall";

    const uniqueRows = dedupeRows(allRows);
    const total = uniqueRows.length;

    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "cv-dlall__btn";
    const defaultLabel = `Download all (${total})`;
    const setLabel = (text) => {
      btn.innerHTML = `${ICON_DOWNLOAD}<span>${text}</span>`;
    };
    const restoreLabel = () => setLabel(defaultLabel);
    restoreLabel();

    btn.addEventListener("click", async (e) => {
      e.preventDefault();
      e.stopPropagation();
      await downloadAllAsZip(meta, uniqueRows, btn, setLabel, restoreLabel);
    });

    wrap.appendChild(btn);
    return wrap;
  }

  async function injectRealEdms() {
    const docket = findDocketTable();
    if (!docket) return false;

    const meta = scrapeMetadataRealEdms();
    if (!meta.caseNumber) return false;
    state.meta = meta;
    const safety = safetyCheck(meta);

    if (state.signedIn) {
      // Add a 4th "EDMSpro" column to the docket table.
      const tableRows = [...docket.rows];
      const headerRow = tableRows[0];
      if (headerRow && !headerRow.querySelector(".cv-dl-coltitle")) {
        const headerCell = document.createElement("td");
        headerCell.className = "coltitle cv-dl-coltitle";
        headerCell.setAttribute("align", "center");
        headerCell.textContent = "EDMSpro";
        headerRow.appendChild(headerCell);
      }

      const rows = [];
      tableRows.forEach((tr, idx) => {
        if (idx === 0) return; // header
        if (tr.querySelector(".cv-dl-cell")) return; // already injected
        const cell = document.createElement("td");
        cell.className = "cv-dl-cell";
        cell.setAttribute("align", "center");
        cell.setAttribute("valign", "middle");

        const parsed = parseRow(tr);
        if (parsed) {
          rows.push(parsed);
          cell.appendChild(buildRowActions(meta, parsed));
        }
        tr.appendChild(cell);
      });

      // Banner + bulk download — slot above the docket table.
      if (!document.querySelector(".cv-banner[data-cv-real]")) {
        const downloadAllBtn = rows.length ? buildDownloadAllBtn(meta, rows) : null;
        const banner = buildBanner(meta, safety, { downloadAllBtn });
        banner.setAttribute("data-cv-real", "1");
        docket.parentNode.insertBefore(banner, docket);
      }
    } else if (!document.querySelector(".cv-banner[data-cv-real]")) {
      // Signed-out: banner only, no column, no row actions.
      const banner = buildBanner(meta, safety);
      banner.setAttribute("data-cv-real", "1");
      docket.parentNode.insertBefore(banner, docket);
    }
    return true;
  }

  // ---------- bootstrap ----------

  async function inject() {
    // Signed-in state first: everything else is a server call that would only
    // 401, and the signed-out banner needs none of it.
    state.signedIn = await loadSignedIn();
    if (state.signedIn) {
      const [settings, blocked] = await Promise.all([loadSettings(), loadBlockedList()]);
      state.settings = settings;
      state.blocked = blocked;
    } else {
      state.settings = { ...DEFAULT_SETTINGS };
      state.blocked = { ...FALLBACK_BLOCKED };
    }
    if (await injectDemo()) return;
    injectRealEdms();
  }

  function teardownInjections() {
    document.querySelectorAll(".cv-banner").forEach((el) => el.remove());
    document.querySelectorAll(".cv-casepop").forEach((el) => el.remove());
    document.querySelectorAll(".cv-dl-coltitle, .cv-dl-cell").forEach((el) => el.remove());
    document.querySelectorAll(".cv-action").forEach((el) => el.remove());
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", inject);
  } else {
    inject();
  }

  // Re-run when the demo page swaps cases
  document.addEventListener("cv:rescrape", inject);

  // Re-render when the user signs in or out anywhere else — the side panel, the
  // options page, or another tab. The refresh token is the thing that says
  // "signed in", so watching it covers all three.
  if (chrome?.storage?.onChanged) {
    chrome.storage.onChanged.addListener((changes, area) => {
      if (area !== "local" || !changes.edmsRefreshToken) return;
      const nowSignedIn = Boolean(changes.edmsRefreshToken.newValue);
      if (nowSignedIn === state.signedIn) return;
      teardownInjections();
      inject();
    });
  }
})();
