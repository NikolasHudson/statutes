// Toolbar popup — a launcher, not a settings screen.
//
// Everything that used to live here (the contribution toggle above all) now
// lives in the app at /account/edms. That is not tidying: turning contribution
// sharing on is session-only server-side, so a toggle here could never have
// worked, and a control that silently fails is worse than no control.

const els = {
  conn: document.getElementById("connStatus"),
  openPanel: document.getElementById("openPanel"),
  openDemo: document.getElementById("openDemo"),
  openSettings: document.getElementById("openSettings"),
  openOptions: document.getElementById("openOptions"),
};

function send(message) {
  return new Promise((resolve) => {
    chrome.runtime.sendMessage(message, (resp) => {
      if (chrome.runtime.lastError) {
        resolve({ ok: false, error: chrome.runtime.lastError.message });
      } else {
        resolve(resp || { ok: false, error: "no response" });
      }
    });
  });
}

async function renderStatus() {
  const auth = await send({ type: "cv:authStatus" });
  if (!auth.signedIn) {
    els.conn.textContent = "Not signed in — open the side panel to sign in.";
    els.conn.className = "conn conn--warn";
    return;
  }
  // v1 saves nowhere, so there is no connection to report — just who you are.
  els.conn.textContent = auth.email ? `Signed in · ${auth.email}` : "Signed in";
  els.conn.className = "conn conn--ok";
}

els.openPanel.addEventListener("click", async () => {
  // Opening the panel needs a user gesture, and this click is one — so it is
  // done here rather than round-tripping through the service worker.
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  try {
    await chrome.sidePanel.open(tab?.id ? { tabId: tab.id } : { windowId: tab?.windowId });
    window.close();
  } catch {
    els.conn.textContent = "Chrome would not open the side panel.";
    els.conn.className = "conn conn--warn";
  }
});

els.openDemo.addEventListener("click", () => {
  void send({ type: "cv:openDemo" });
  window.close();
});

els.openSettings.addEventListener("click", () => {
  void send({ type: "cv:openSettings" });
  window.close();
});

els.openOptions.addEventListener("click", () => {
  chrome.runtime.openOptionsPage();
  window.close();
});

void renderStatus();
