/**
 * Content script: works out whether the current page is a checkout, and who the
 * merchant is. It reads the page and reports; it never touches form fields.
 *
 * Deliberately conservative — a wrong merchant produces a wrong card
 * recommendation, which is worse than no recommendation at all.
 */

const CHECKOUT_HINTS = [
  "checkout",
  "payment",
  "place your order",
  "order summary",
  "billing",
];

function looksLikeCheckout(urlValue = location.href, titleValue = document.title) {
  const url = urlValue.toLowerCase();
  if (CHECKOUT_HINTS.some((hint) => url.includes(hint))) return true;

  const text = titleValue.toLowerCase();
  return CHECKOUT_HINTS.some((hint) => text.includes(hint));
}

function merchantName(doc = document, hostname = location.hostname) {
  const og = doc.querySelector('meta[property="og:site_name"]');
  if (og?.content) return og.content.trim();

  const appName = doc.querySelector('meta[name="application-name"]');
  if (appName?.content) return appName.content.trim();

  return hostname.replace(/^www\./, "");
}

function detectPage(loc = location, doc = document) {
  return {
    isCheckout: looksLikeCheckout(loc.href, doc.title),
    merchant: merchantName(doc, loc.hostname),
    url: loc.origin + loc.pathname,
  };
}

if (typeof chrome !== "undefined" && chrome.runtime?.onMessage) chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type !== "cardsense:detect") return;

  sendResponse(detectPage());

  return true;
});

if (typeof module === "object" && module.exports) {
  module.exports = { looksLikeCheckout, merchantName, detectPage };
}
