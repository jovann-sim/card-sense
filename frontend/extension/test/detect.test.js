const test = require("node:test");
const assert = require("node:assert/strict");

const { looksLikeCheckout, merchantName, detectPage } = require("../detect.js");

function documentWith(meta = {}, title = "") {
  return {
    title,
    querySelector(selector) {
      if (selector.includes("og:site_name") && meta.og) return { content: meta.og };
      if (selector.includes("application-name") && meta.app) return { content: meta.app };
      return null;
    },
  };
}

test("checkout detection uses only the URL and title", () => {
  assert.equal(looksLikeCheckout("https://shop.example/checkout", "Shop"), true);
  assert.equal(looksLikeCheckout("https://shop.example/cart", "Payment · Shop"), true);
  assert.equal(looksLikeCheckout("https://shop.example/products", "Shop"), false);
});

test("published site name wins and hostname is the conservative fallback", () => {
  assert.equal(merchantName(documentWith({ og: "  Acme Shop  " }), "www.example.com"), "Acme Shop");
  assert.equal(merchantName(documentWith(), "www.example.com"), "example.com");
});

test("content-script payload excludes query, fragment, and page contents", () => {
  const result = detectPage(
    {
      href: "https://shop.example/checkout?order=secret#payment",
      origin: "https://shop.example",
      pathname: "/checkout",
      hostname: "shop.example",
    },
    documentWith({ app: "Example Shop" }, "Checkout"),
  );
  assert.deepEqual(result, {
    isCheckout: true,
    merchant: "Example Shop",
    url: "https://shop.example/checkout",
  });
});
