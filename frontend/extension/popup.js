/**
 * Popup renderer.
 *
 * The seam is `getVerdict()`. Today it returns a fixed object so the UI can be
 * designed and demoed; when the Advisory Agent is live, replace its body with a
 * fetch to the same endpoint the dashboard reads and keep the shape identical.
 */

const AGENT_LABEL = {
  ingestion: "Ingestion agent",
  forecast: "Forecast agent",
  "card-intelligence": "Card intelligence agent",
  strategy: "Strategy agent",
  advisory: "Advisory agent",
};

async function getVerdict() {
  return {
    merchant: "shop.terrafirma.com · Dining & delivery",
    card: { name: "Sapphire Reserve", last4: "4471" },
    rate: "4× points on dining",
    reason:
      "Best card you hold for this merchant. Worth about $0.04 per dollar more than the card you used here last time.",
    // Set to null when there is nothing worth interrupting for.
    caveat:
      "Only $18 of the quarterly 4× cap is left. Past that, this card pays the same as every other card you hold.",
    runnerUp: "Cashback One ••7726 · 2% cash back",
    trace: [
      {
        agent: "ingestion",
        detail: "Merchant matched to MCC 5812 (eating places) with high confidence.",
      },
      {
        agent: "card-intelligence",
        detail: "Sapphire Reserve terms, retrieved 4 Aug: 4× points on MCC 5812 up to $1,500 per quarter.",
      },
      {
        agent: "strategy",
        detail: "Ranked 9 cards by nominal return. Sapphire Reserve leads by $0.04 per dollar until the cap.",
      },
    ],
  };
}

function el(id) {
  return document.getElementById(id);
}

function render(v) {
  el("merchant").textContent = v.merchant;
  el("card").textContent = v.card.name;
  el("digits").textContent = `••${v.card.last4}`;
  el("rate").textContent = v.rate;
  el("reason").textContent = v.reason;

  if (v.caveat) {
    el("caveat").textContent = v.caveat;
    el("caveat").hidden = false;
  }

  if (v.runnerUp) {
    el("runner").textContent = v.runnerUp;
    el("runnerWrap").hidden = false;
  }

  el("why").replaceChildren(
    ...v.trace.map((step) => {
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

function renderEmpty(message) {
  el("merchant").textContent = message;
  el("card").textContent = "No call to make";
  el("digits").textContent = "";
  el("reason").textContent =
    "CardSense only speaks up when one of your cards clearly beats the others here.";
}

getVerdict()
  .then((v) => (v ? render(v) : renderEmpty("No checkout detected on this page")))
  .catch(() => renderEmpty("Could not reach CardSense"));
