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

function looksLikeCheckout() {
  const url = location.href.toLowerCase();
  if (CHECKOUT_HINTS.some((hint) => url.includes(hint))) return true;

  const text = document.title.toLowerCase();
  return CHECKOUT_HINTS.some((hint) => text.includes(hint));
}

function merchantName() {
  const og = document.querySelector('meta[property="og:site_name"]');
  if (og?.content) return og.content.trim();

  const appName = document.querySelector('meta[name="application-name"]');
  if (appName?.content) return appName.content.trim();

  return location.hostname.replace(/^www\./, "");
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type !== "cardsense:detect") return;

  sendResponse({
    isCheckout: looksLikeCheckout(),
    merchant: merchantName(),
    url: location.origin + location.pathname,
  });

  return true;
});
