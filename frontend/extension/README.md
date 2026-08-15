# CardSense browser extension

Tells you which card to reach for, on the page you are already on.

## What it does

Reads the hostname, resolves it to a merchant category code, and asks the
backend which of your cards pays most for that code. The answer comes from the
same rules and the same optimiser as the dashboard, so the two cannot disagree.

It declines twice over: when the merchant cannot be named, and when no card you
hold has a readable rule covering it. A confident wrong card at checkout is
worse than no popup at all.

## What it does not do

It never fills, stores or transmits a card number. It does not read form
fields, cart contents or page text. What leaves the machine is a hostname and,
where the site publishes one, its own name — that is the entire payload, and
the request model on the server is deliberately narrow enough to enforce it.

The `••1111` shown is the last four digits you typed when adding the card, so
you can tell two cards apart. It is an identifier, not a number.

## Running it

The backend must be running on `http://localhost:8080`:

```bash
cd backend && .venv/bin/uvicorn app.main:app --port 8080
```

Then load the extension:

1. Open `chrome://extensions`
2. Turn on **Developer mode** (top right)
3. **Load unpacked**, and choose this `frontend/extension` folder
4. Visit a shop — instacart.com, doordash.com, netflix.com — and open the popup

## Try these

| Site | Expected |
|---|---|
| `instacart.com` | Blue Cash Preferred, 6% — with its annual cap stated |
| `doordash.com` | the dining card, with the runner-up beside it |
| `netflix.com` | the streaming rate |
| any unknown shop | declines, and says why |

## Adding merchants

`backend/app/merchants.py` holds the domain table. A known domain is treated as
fact; a category word in a site's own name is treated as a hint and reported at
low confidence. Anything else resolves to nothing on purpose.
