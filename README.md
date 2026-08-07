# card_up

`card_up` is a small Python CLI that routes finance-related requests through a set of agent roles and prints a combined workflow result.

## What the agents do

### Transaction agent
- Scans the `statements/` directory for CSV bank statements
- Parses rows with positive spend
- Summarizes total spend, spending by category, spending by month, and source files
- Uses Vertex AI when credentials are available, otherwise falls back to local logic

### Budget agent
- Takes the transaction summary
- Forecasts future monthly spend
- Suggests a recommended cap
- Uses Vertex AI when available, with local fallback behavior

### Rewards agent
- Compares the spending mix against a small set of card profiles
- Estimates which card gives the best rewards value
- Emits reminders when rewards may be near a cap

### Deal agent
- Suggests categories or merchant areas worth monitoring for better deals
- This is currently scaffolded and does not connect to a live deal source yet

### Recommendation agent
- Combines the transaction, budget, rewards, and deal outputs
- Suggests spending habits
- Recommends the best card for the current spend mix
- Reminds the user when rewards may be maxed out

## How it works

The CLI entrypoint is [main.py](main.py). It:

1. Accepts a user request
2. Scans a statement directory for CSV files
3. Runs the orchestrator
4. Prints either a readable summary or JSON

The agent implementations live in [finance_agents.py](finance_agents.py). The orchestrator wires the agents together in this order:

1. transaction
2. budget
3. rewards
4. deal
5. recommendation

If Vertex AI credentials are available, the agents call Gemini through the Vertex AI SDK.
If credentials are missing, the program falls back to local deterministic logic and still runs successfully.

## Requirements

Install the Python package used by the app:

```bash
pip install google-genai
```

If you want live Vertex AI calls, authenticate with Application Default Credentials:

```bash
gcloud auth application-default login
```

## Run the project

From the project root:

```bash
python main.py
```

With a custom request:

```bash
python main.py "Analyze my spending"
```

With JSON output:

```bash
python main.py "Recommend a rewards card" --json
```

With a custom statement directory:

```bash
python main.py --statement-dir statements
```

## Sample CSV

A working sample statement is included at:

```text
statements/sample_bank_statement.csv
```

Its columns are:

- `date`
- `description`
- `merchant`
- `category`
- `amount`

That format is compatible with the current transaction parser.

## Example flow

1. Transaction agent loads the CSV statements.
2. Budget agent forecasts spend from the summary.
3. Rewards agent ranks cards based on the spend mix.
4. Deal agent suggests deal watch categories.
5. Recommendation agent synthesizes the final advice.

## Notes

- The default statement directory is `statements/`
- The default prompt is `Recommend a budget.`
- The app prints fallback output if Vertex AI credentials are not available
- There is no `requirements.txt` yet, so install dependencies manually for now