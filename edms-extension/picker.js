// PARKED FOR v2 — not wired up in v1.
//
// v1 ships without cloud saving, so nothing imports this module. It is kept
// (rather than deleted) because it is the only copy: the extension is not in
// git history yet. The matching server endpoints are preserved behind
// EDMS_CLOUD_ENABLED. Exclude this file from the Web Store build until v2.

// Hudson EDMSpro OneDrive folder picker — shared by content.js and options.js.
// Exposes window.EdmsPicker.create({ onConfirm, onCancel }) → returns a panel
// element ready to insert into the DOM. The first call also injects the picker's
// stylesheet into document.head.

(function () {
  if (window.EdmsPicker) return;

  const STYLE = `
/* Carbon v11 — tokens come from tokens.css (options page) or the .cv-casepop
   ancestor (host pages); fallbacks are the light-theme values. */
.cvp {
  background: var(--cds-bg, #ffffff);
  border: 1px solid var(--cds-border, #e0e0e0);
  margin-top: 8px;
  font-family: var(--font-sans, -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif);
  color: var(--cds-text, #161616);
  overflow: hidden;
}
.cvp[hidden] { display: none; }
.cvp__crumbs {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px;
  padding: 10px 12px;
  background: var(--cds-layer, #f4f4f4);
  border-bottom: 1px solid var(--cds-border, #e0e0e0);
  font-size: 12px;
  color: var(--cds-text-2, #525252);
}
.cvp__crumb {
  all: unset;
  cursor: pointer;
  padding: 2px 6px;
  color: var(--cds-link, #0f62fe);
}
.cvp__crumb:hover { background: var(--cds-layer-hover, #e8e8e8); }
.cvp__crumb:focus-visible {
  outline: 2px solid var(--cds-blue, #0f62fe);
  outline-offset: 1px;
}
.cvp__crumb--current {
  color: var(--cds-text, #161616);
  cursor: default;
  font-weight: 600;
}
.cvp__crumb--current:hover { background: transparent; }
.cvp__sep { color: var(--cds-helper, #6f6f6f); }
.cvp__body {
  max-height: 220px;
  overflow-y: auto;
}
.cvp__row {
  all: unset;
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 8px 12px;
  cursor: pointer;
  font-size: 13px;
  border-bottom: 1px solid var(--cds-border, #e0e0e0);
  box-sizing: border-box;
}
.cvp__row:hover { background: var(--cds-layer-hover, #e8e8e8); }
.cvp__row:focus-visible {
  outline: 2px solid var(--cds-blue, #0f62fe);
  outline-offset: -2px;
}
.cvp__row svg { flex-shrink: 0; color: var(--cds-text-2, #525252); }
.cvp__row-name { flex: 1; }
.cvp__row-count {
  font-size: 11px;
  color: var(--cds-helper, #6f6f6f);
}
.cvp__empty {
  padding: 14px 12px;
  font-size: 12px;
  color: var(--cds-helper, #6f6f6f);
  text-align: center;
}
.cvp__newfolder {
  padding: 8px 12px;
  border-top: 1px solid var(--cds-border, #e0e0e0);
  background: var(--cds-layer, #f4f4f4);
  display: flex;
  align-items: center;
  gap: 6px;
}
.cvp__newfolder input {
  flex: 1;
  height: 28px;
  padding: 0 8px;
  border: none;
  border-bottom: 1px solid var(--cds-border-strong, #8d8d8d);
  background: var(--cds-bg, #ffffff);
  color: var(--cds-text, #161616);
  font-size: 12px;
  outline: none;
  font-family: var(--font-sans, -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif);
}
.cvp__newfolder input:focus {
  outline: 2px solid var(--cds-blue, #0f62fe);
  outline-offset: -2px;
}
.cvp__btn {
  all: unset;
  display: inline-flex;
  align-items: center;
  height: 28px;
  padding: 0 12px;
  font-size: 12px;
  cursor: pointer;
  transition: background 0.11s ease, color 0.11s ease, border-color 0.11s ease;
  box-sizing: border-box;
}
.cvp__btn:focus-visible {
  outline: 2px solid var(--cds-blue, #0f62fe);
  outline-offset: 1px;
}
.cvp__btn:disabled {
  background: var(--cds-layer-selected, #e0e0e0);
  color: var(--cds-helper, #6f6f6f);
  cursor: not-allowed;
}
.cvp__btn--primary {
  background: var(--cds-blue, #0f62fe);
  color: #fff;
}
.cvp__btn--primary:hover:not(:disabled) { background: var(--cds-blue-hover, #0353e9); }
.cvp__btn--primary:active:not(:disabled) { background: var(--cds-blue-active, #002d9c); }
.cvp__btn--secondary {
  background: transparent;
  color: var(--cds-link, #0f62fe);
  border: 1px solid var(--cds-link, #0f62fe);
}
.cvp__btn--secondary:hover:not(:disabled) {
  background: var(--cds-blue, #0f62fe);
  border-color: var(--cds-blue, #0f62fe);
  color: #fff;
}
.cvp__btn--link {
  background: transparent;
  color: var(--cds-link, #0f62fe);
  padding: 0 8px;
}
.cvp__btn--link:hover:not(:disabled) { background: var(--cds-layer-hover, #e8e8e8); }
.cvp__footer {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  border-top: 1px solid var(--cds-border, #e0e0e0);
  background: var(--cds-layer, #f4f4f4);
}
.cvp__footer-path {
  flex: 1;
  font-family: var(--font-mono, ui-monospace, SFMono-Regular, Menlo, monospace);
  font-size: 11px;
  color: var(--cds-text-2, #525252);
  word-break: break-all;
}
.cvp__status {
  padding: 8px 12px;
  font-size: 12px;
  background: var(--cds-layer, #f4f4f4);
  color: var(--cds-text, #161616);
  border-left: 3px solid var(--cds-danger, #da1e28);
}
.cvp__loading {
  padding: 14px 12px;
  text-align: center;
  font-size: 12px;
  color: var(--cds-helper, #6f6f6f);
}
`;

  const ICON_FOLDER =
    '<svg viewBox="0 0 20 20" width="14" height="14" aria-hidden="true"><path fill="currentColor" d="M2 5a2 2 0 0 1 2-2h4l2 2h6a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5Z"/></svg>';

  function installStyles() {
    if (document.querySelector('style[data-cv-picker]')) return;
    const s = document.createElement("style");
    s.setAttribute("data-cv-picker", "1");
    s.textContent = STYLE;
    document.head.appendChild(s);
  }

  function send(payload) {
    return new Promise((resolve) => {
      if (!chrome?.runtime?.sendMessage) {
        resolve({ ok: false, error: "no chrome.runtime" });
        return;
      }
      chrome.runtime.sendMessage(payload, (resp) => {
        if (chrome.runtime.lastError) {
          resolve({ ok: false, error: chrome.runtime.lastError.message });
        } else {
          resolve(resp || { ok: false });
        }
      });
    });
  }

  function create({ onConfirm, onCancel } = {}) {
    installStyles();

    const wrap = document.createElement("div");
    wrap.className = "cvp";

    // Mutable nav stack: each entry { id, name }. The first is always { id: "root", name: "OneDrive" }.
    const stack = [{ id: "root", name: "OneDrive" }];

    wrap.innerHTML = `
      <div class="cvp__crumbs" data-cvp-crumbs></div>
      <div class="cvp__status" hidden data-cvp-status></div>
      <div class="cvp__body" data-cvp-body><div class="cvp__loading">Loading…</div></div>
      <div class="cvp__newfolder" data-cvp-newfolder hidden>
        <input type="text" placeholder="New folder name" data-cvp-newname />
        <button type="button" class="cvp__btn cvp__btn--primary" data-cvp-act="newcreate">Create</button>
        <button type="button" class="cvp__btn cvp__btn--secondary" data-cvp-act="newcancel">Cancel</button>
      </div>
      <div class="cvp__footer">
        <span class="cvp__footer-path" data-cvp-current>OneDrive</span>
        <button type="button" class="cvp__btn cvp__btn--link" data-cvp-act="newfolder">+ New folder</button>
        <button type="button" class="cvp__btn cvp__btn--secondary" data-cvp-act="cancel">Cancel</button>
        <button type="button" class="cvp__btn cvp__btn--primary" data-cvp-act="use">Use this folder</button>
      </div>
    `;

    const elCrumbs = wrap.querySelector("[data-cvp-crumbs]");
    const elBody = wrap.querySelector("[data-cvp-body]");
    const elStatus = wrap.querySelector("[data-cvp-status]");
    const elNewFolder = wrap.querySelector("[data-cvp-newfolder]");
    const elNewName = wrap.querySelector("[data-cvp-newname]");
    const elCurrent = wrap.querySelector("[data-cvp-current]");

    function currentPath() {
      // Skip the root ("OneDrive"); join remaining names with "/".
      return stack.slice(1).map((s) => s.name).join("/");
    }

    function setStatus(msg) {
      if (!msg) {
        elStatus.hidden = true;
        elStatus.textContent = "";
        return;
      }
      elStatus.hidden = false;
      elStatus.textContent = msg;
    }

    function renderCrumbs() {
      elCrumbs.innerHTML = "";
      stack.forEach((s, i) => {
        const isLast = i === stack.length - 1;
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = `cvp__crumb ${isLast ? "cvp__crumb--current" : ""}`;
        btn.textContent = s.name;
        if (!isLast) {
          btn.addEventListener("click", () => {
            // Pop back to this level.
            stack.length = i + 1;
            load();
          });
        }
        elCrumbs.appendChild(btn);
        if (!isLast) {
          const sep = document.createElement("span");
          sep.className = "cvp__sep";
          sep.textContent = "›";
          elCrumbs.appendChild(sep);
        }
      });
      elCurrent.textContent = currentPath() ? `OneDrive / ${currentPath()}` : "OneDrive (root)";
    }

    async function load() {
      setStatus("");
      elBody.innerHTML = '<div class="cvp__loading">Loading…</div>';
      renderCrumbs();
      const parent = stack[stack.length - 1];
      const resp = await send({ type: "cv:listFolders", parentId: parent.id });
      if (!resp?.ok) {
        elBody.innerHTML = "";
        setStatus(resp?.error || "Couldn't list folders.");
        return;
      }
      const folders = (resp.data && resp.data.folders) || [];
      if (!folders.length) {
        elBody.innerHTML = '<div class="cvp__empty">No subfolders here.</div>';
        return;
      }
      elBody.innerHTML = "";
      for (const f of folders) {
        const row = document.createElement("button");
        row.type = "button";
        row.className = "cvp__row";
        row.innerHTML = `
          ${ICON_FOLDER}
          <span class="cvp__row-name"></span>
          <span class="cvp__row-count"></span>
        `;
        row.querySelector(".cvp__row-name").textContent = f.name;
        row.querySelector(".cvp__row-count").textContent =
          f.child_count ? `${f.child_count} item${f.child_count === 1 ? "" : "s"}` : "";
        row.addEventListener("click", () => {
          stack.push({ id: f.id, name: f.name });
          load();
        });
        elBody.appendChild(row);
      }
    }

    wrap.querySelector('[data-cvp-act="cancel"]').addEventListener("click", () => {
      if (onCancel) onCancel();
    });
    wrap.querySelector('[data-cvp-act="use"]').addEventListener("click", () => {
      const path = currentPath();
      if (onConfirm) onConfirm(path);
    });
    wrap.querySelector('[data-cvp-act="newfolder"]').addEventListener("click", () => {
      elNewFolder.hidden = false;
      elNewName.value = "";
      elNewName.focus();
    });
    wrap.querySelector('[data-cvp-act="newcancel"]').addEventListener("click", () => {
      elNewFolder.hidden = true;
    });
    const onCreate = async () => {
      const name = (elNewName.value || "").trim();
      if (!name) return;
      setStatus("Creating…");
      const parent = stack[stack.length - 1];
      const resp = await send({
        type: "cv:createFolder",
        parentId: parent.id,
        name,
      });
      if (!resp?.ok) {
        setStatus(resp?.error || "Couldn't create folder.");
        return;
      }
      setStatus("");
      elNewFolder.hidden = true;
      stack.push({ id: resp.data.id, name: resp.data.name });
      load();
    };
    wrap.querySelector('[data-cvp-act="newcreate"]').addEventListener("click", onCreate);
    elNewName.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        onCreate();
      }
    });

    load();
    return wrap;
  }

  window.EdmsPicker = { create };
})();
