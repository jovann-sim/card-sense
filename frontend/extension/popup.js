/**
 * Popup renderer.
 *
 * Asks the content script where we are, asks the backend which card wins there,
 * renders the answer. The verdict comes from the same rules and the same
 * optimiser as the dashboard, so the two cannot disagree about a card.
 *
 * What leaves this machine is a hostname and a site name. Never the page, never
 * a form field, never a card number — the extension is advisory only, and reads
 * far less than it is technically permitted to.
 */

const API = "http://localhost:8080";

const AGENT_LABEL = {
  ingestion: "Ingestion agent",
  forecast: "Forecast agent",
  "card-intelligence": "Card intelligence agent",
  strategy: "Strategy agent",
  advisory: "Advisory agent",
};

/** Ask the content script what page this is. */
async function detect() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.id) return null;
  try {
    return await chrome.tabs.sendMessage(tab.id, { type: "cardsense:detect" });
  } catch {
    // No content script on this page — a new tab, the store, a PDF. Fall back
    // to the tab's own URL, which is enough to name a merchant.
    return tab.url ? { merchant: null, url: tab.url, isCheckout: false } : null;
  }
}

async function getVerdict() {
  const page = await detect();
  if (!page?.url) return null;

  const response = await fetch(`${API}/api/v1/advise/merchant`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url: page.url, merchant: page.merchant }),
  });
  if (!response.ok) throw new Error(`CardSense API returned ${response.status}`);

  const verdict = await response.json();
  return { ...verdict, isCheckout: page.isCheckout };
}

function el(id) {
  return document.getElementById(id);
}

function render(v) {
  const label = v.category ? `${v.merchant} · ${v.category}` : v.merchant;
  el("merchant").textContent = v.isCheckout ? `${label} · checkout` : label;

  el("card").textContent = v.card.name;
  el("digits").textContent = `••${v.card.last4}`;
  el("rate").textContent = v.rate ?? "";
  el("reason").textContent = v.reason;

  // A low-confidence merchant match is stated, because the card it produces is
  // only as good as the category behind it.
  const caveat = v.confidence === "low"
    ? `${v.caveat ? v.caveat + " " : ""}The category here was guessed from the site's name, not a known merchant.`
    : v.caveat;

  if (caveat) {
    el("caveat").textContent = caveat;
    el("caveat").hidden = false;
  }

  if (v.runnerUp) {
    el("runner").textContent = v.runnerUp;
    el("runnerWrap").hidden = false;
  }

  el("why").replaceChildren(
    ...(v.trace ?? []).map((step) => {
      const li = document.createElement("li");
      const agent = document.createElement("span");
      agent.className = "why__agent";
      agent.textContent = AGENT_LABEL[step.agent] ?? step.agent;
      const detail = document.createElement("span");
      detail.className = "why__detail";
      detail.textContent = step.detail;
      li.append(agent, detail);
      return li;
    }),
  );
}

function renderEmpty(headline, message) {
  el("merchant").textContent = headline;
  el("card").textContent = "No call to make";
  el("digits").textContent = "";
  el("rate").textContent = "";
  el("reason").textContent = message;
  el("why").replaceChildren();
}

getVerdict()
  .then((v) => {
    if (!v) return renderEmpty("No page to read", "Open a shop and try again.");
    if (!v.card) {
      // Declining is the right answer twice over: when we cannot name the
      // merchant, and when no held card has a readable rule for it.
      return renderEmpty(v.merchant ?? "Unknown merchant", v.reason);
    }
    render(v);
  })
  .catch(() =>
    renderEmpty(
      "Could not reach CardSense",
      "The backend is not running on localhost:8080, so there is nothing to recommend from.",
    ),
  );
