const Core = globalThis.CardSenseExtension;
const form = document.getElementById("form");
const input = document.getElementById("apiOrigin");
const status = document.getElementById("status");

chrome.storage.sync.get({ apiOrigin: Core.DEFAULT_API_ORIGIN }).then(({ apiOrigin }) => {
  input.value = apiOrigin;
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  status.dataset.kind = "";
  try {
    const apiOrigin = Core.normalizeApiOrigin(input.value);
    const granted = await chrome.permissions.request({
      origins: [Core.permissionPattern(apiOrigin)],
    });
    if (!granted) throw new Error("Permission for that backend was not granted.");
    await chrome.storage.sync.set({ apiOrigin });
    input.value = apiOrigin;
    status.textContent = `Saved ${apiOrigin}`;
    status.dataset.kind = "success";
  } catch (error) {
    status.textContent = error instanceof Error ? error.message : "Could not save this backend.";
    status.dataset.kind = "error";
  }
});
