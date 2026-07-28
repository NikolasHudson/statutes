// Side panel — sign-in and the PDF preview.
//
// v1 has no cloud saving, so this no longer carries a connection status or a
// recent-saves list: a filing is previewed and downloaded locally, and nothing
// is sent anywhere. The OneDrive flow is preserved server-side behind
// EDMS_CLOUD_ENABLED for v2.
//
// The preview is the reason this is a side panel and not a modal: the docket
// stays visible and clickable beside it, so triaging twenty filings is twenty
// clicks rather than twenty open/close cycles. Bytes arrive from the content
// script (which fetched them same-origin, with the user's court session) via the
// service worker, and are rendered here — on the extension origin — where the
// court page's CSP has no say. Hudson is never contacted for a preview.

const $ = (id) => document.getElementById(id);

let objectUrl = null;
let previewMeta = null;

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

// --- auth -------------------------------------------------------------------

async function renderAuth() {
  const status = await send({ type: "cv:authStatus" });
  const signedIn = Boolean(status.signedIn);
  $("signedOut").hidden = signedIn;
  $("signedIn").hidden = !signedIn;
  if (!signedIn) {
    $("accountLine").textContent = "";
    return;
  }
  // With the OneDrive status gone the footer has room for the account itself,
  // which is what it should have said all along.
  $("accountLine").textContent = status.email || "Signed in";
}

// --- preview ---------------------------------------------------------------

function clearPreview() {
  if (objectUrl) {
    URL.revokeObjectURL(objectUrl);
    objectUrl = null;
  }
  previewMeta = null;
  $("previewEmbed").removeAttribute("src");
  $("preview").hidden = true;
  $("previewNote").hidden = true;
  $("idlePane").hidden = false;
}

async function loadPreview() {
  const resp = await send({ type: "cv:takePreview" });
  if (!resp.ok || !resp.preview) return;

  const { bytes, title, meta } = resp.preview;
  if (objectUrl) URL.revokeObjectURL(objectUrl);
  // `bytes` crossed the message boundary as a plain array — structured clone
  // does not carry a Blob, and reconstructing here keeps the transfer honest
  // about what it is.
  objectUrl = URL.createObjectURL(new Blob([new Uint8Array(bytes)], { type: "application/pdf" }));
  previewMeta = meta || null;

  $("previewTitle").textContent = title || "Filing";
  // PDF open parameters, read by Chrome's built-in viewer. The panel is ~360px
  // wide, so the thumbnail rail costs more than it gives: navpanes=0 keeps it
  // closed, and FitH starts at page width instead of whole-page (which renders
  // a full page as an unreadable postage stamp at this width). The user can
  // still open the rail from the viewer's own toolbar.
  $("previewEmbed").src = `${objectUrl}#navpanes=0&view=FitH`;
  $("previewNote").hidden = true;
  $("preview").hidden = false;
  // The panel is narrow; anything under the PDF just pushes it off screen.
  $("idlePane").hidden = true;
}

function note(text, ok = false) {
  const el = $("previewNote");
  el.textContent = text;
  el.style.borderLeftColor = ok ? "var(--cds-success)" : "var(--cds-danger)";
  el.hidden = false;
}

async function downloadFromPreview() {
  if (!previewMeta?.pdfUrl) return;
  const resp = await send({
    type: "cv:downloadLocal",
    url: previewMeta.pdfUrl,
    filename: previewMeta.filename,
  });
  if (!resp.ok) note(resp.error || "Download failed.");
}

// --- wiring ----------------------------------------------------------------

$("signIn").addEventListener("click", async () => {
  const btn = $("signIn");
  btn.disabled = true;
  btn.textContent = "Opening Hudson…";
  const resp = await send({ type: "cv:signIn" });
  btn.disabled = false;
  btn.textContent = "Sign in to Hudson";
  if (resp.ok) {
    $("signInError").hidden = true;
    await renderAuth();
  } else {
    $("signInError").textContent = resp.error || "Sign-in failed.";
    $("signInError").hidden = false;
  }
});

$("signOut").addEventListener("click", async () => {
  await send({ type: "cv:signOut" });
  await renderAuth();
});

$("openSettings").addEventListener("click", () => send({ type: "cv:openSettings" }));
$("previewClose").addEventListener("click", clearPreview);
$("previewDownload").addEventListener("click", downloadFromPreview);

chrome.runtime.onMessage.addListener((msg) => {
  if (msg?.type === "cv:previewReady") void loadPreview();
});

// A preview may already be waiting: the service worker stashes the bytes and
// *then* opens the panel, so the ready message can land before this script runs.
window.addEventListener("unload", clearPreview);
void renderAuth();
void loadPreview();
