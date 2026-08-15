"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import Script from "next/script";
import type { AgentRun, CardDetail } from "@/lib/types";
import { api, userId } from "@/lib/client-api";
import { dayMonth } from "@/lib/format";

/** Onboarding dialog backed by the real persisted agent run lifecycle. */
const RUN_POLL_MS = 400;

type Step = "accounts" | "documents" | "goal" | "running" | "done";

type PlaidAccount = {
  id: string;
  name: string;
  officialName?: string | null;
  mask?: string | null;
  type: string;
  subtype?: string | null;
  linkedCard?: string | null;
};

const TRACKS = [
  { id: "points", label: "Points" },
  { id: "cashback", label: "Cash back" },
  { id: "miles", label: "Air miles" },
] as const;

type RewardTrack = (typeof TRACKS)[number]["id"];
type LiveAgentStatus = "queued" | "running" | "ok" | "degraded" | "failed";
type LiveAgent = Omit<AgentRun, "status"> & {
  status: LiveAgentStatus;
  summary?: string | null;
  detail?: string | null;
};
type RunStatus = {
  runId: string;
  status: "queued" | "running" | "complete" | "failed";
  agents: LiveAgent[];
};
type CompletedConnectionRun = {
  runId: string;
  agents: LiveAgent[];
};

export function ConnectFlow({ agents, wallet }: { agents: AgentRun[]; wallet: CardDetail[] }) {
  const [open, setOpen] = useState(false);
  const [step, setStep] = useState<Step>("accounts");
  const [linked, setLinked] = useState(false);
  const [track, setTrack] = useState<RewardTrack | null>(null);
  const [liveAgents, setLiveAgents] = useState<LiveAgent[]>(
    agents.map((agent) => ({ ...agent, status: "queued" })),
  );
  const [runError, setRunError] = useState<string | null>(null);
  const [startingRun, setStartingRun] = useState(false);
  const [plaidReady, setPlaidReady] = useState(false);
  const [connecting, setConnecting] = useState(false);
  const [connectionPhase, setConnectionPhase] = useState<"opening" | "syncing">("opening");
  const [connectionError, setConnectionError] = useState<string | null>(null);
  const [connectedAccounts, setConnectedAccounts] = useState<PlaidAccount[]>([]);
  const [connectionRun, setConnectionRun] = useState<CompletedConnectionRun | null>(null);
  const dialogRef = useRef<HTMLDivElement>(null);
  const linkRef = useRef<ReturnType<NonNullable<Window["Plaid"]>["create"]> | null>(null);
  const syncingRef = useRef(false);
  const pollGenerationRef = useRef(0);
  const router = useRouter();

  const destroyLink = useCallback(() => {
    linkRef.current?.destroy();
    linkRef.current = null;
  }, []);

  const completePlaidConnection = useCallback(async (
    publicToken: string,
    metadata?: { institution?: { institution_id?: string | null; name?: string | null } | null },
  ) => {
    syncingRef.current = true;
    setConnectionPhase("syncing");
    try {
      await api("/api/v1/plaid/exchange-token", {
        method: "POST",
        body: JSON.stringify({
          publicToken,
          userId,
          institutionId: metadata?.institution?.institution_id,
          institutionName: metadata?.institution?.name,
        }),
      });
      const sync = await api<{
        runId: string;
        snapshot: { agents: LiveAgent[] };
      }>("/api/v1/plaid/sync", {
        method: "POST",
        body: JSON.stringify({ userId }),
      });
      const accounts = await api<PlaidAccount[]>("/api/v1/plaid/accounts");
      setConnectedAccounts(accounts);
      setConnectionRun({ runId: sync.runId, agents: sync.snapshot.agents });
      setLinked(true);
      router.refresh();
    } catch (error) {
      setConnectionError(error instanceof Error ? error.message : "Unable to sync Plaid transactions.");
    } finally {
      syncingRef.current = false;
      setConnecting(false);
      destroyLink();
    }
  }, [destroyLink, router]);

  async function connectPlaid() {
    if (connecting || !plaidReady || !window.Plaid) return;
    setConnectionError(null);
    setConnectionPhase("opening");
    setConnecting(true);
    try {
      const result = await api<{ link_token: string }>("/api/v1/plaid/link-token", {
        method: "POST", body: JSON.stringify({ userId }),
      });
      destroyLink();
      linkRef.current = window.Plaid.create({
        token: result.link_token,
        onSuccess: completePlaidConnection,
        onExit: (error) => {
          if (syncingRef.current) return;
          destroyLink();
          setConnecting(false);
          if (error) setConnectionError(error.display_message ?? error.error_message ?? "Plaid Link was closed.");
        },
      });
      linkRef.current.open();
    } catch (error) {
      setConnecting(false);
      setConnectionError(error instanceof Error ? error.message : "Unable to start Plaid Link.");
    }
  }

  useEffect(() => () => destroyLink(), [destroyLink]);

  const close = useCallback(() => {
    pollGenerationRef.current += 1;
    destroyLink();
    setOpen(false);
    setStep("accounts");
    setLinked(false);
    setConnectedAccounts([]);
    setConnectionRun(null);
    setTrack(null);
    setRunError(null);
    setStartingRun(false);
    setLiveAgents(agents.map((agent) => ({ ...agent, status: "queued" })));
  }, [agents, destroyLink]);

  useEffect(() => {
    if (!open) return;
    dialogRef.current?.focus();

    const onKey = (e: KeyboardEvent) => e.key === "Escape" && close();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, close]);

  const startRun = useCallback(async (selectedTrack: RewardTrack | null) => {
    const generation = ++pollGenerationRef.current;
    setRunError(null);
    setStartingRun(true);
    setLiveAgents(agents.map((agent) => ({ ...agent, status: "queued" })));
    setStep("running");
    try {
      if (selectedTrack) {
        await api("/api/v1/goals", {
          method: "POST",
          body: JSON.stringify({
            track: selectedTrack,
            target: null,
            unitLabel: selectedTrack === "cashback" ? "dollars" : selectedTrack,
            current: 0,
            deadline: null,
            purpose: "",
          }),
        });
      } else {
        await api("/api/v1/goals", { method: "DELETE" });
      }

      // Plaid sync already completed a real five-agent run. Goal writes use a
      // targeted projection, so launching the pipeline again here duplicated
      // model calls, activity entries, and Firestore writes without changing
      // the transaction input. Reuse the completed run that produced the
      // connected snapshot and only fall back to a new run when onboarding did
      // not originate from a successful sync.
      if (connectionRun) {
        setLiveAgents(connectionRun.agents);
        setStartingRun(false);
        setStep("done");
        router.refresh();
        return;
      }

      const queued = await api<{ runId: string }>("/api/v1/runs/async", {
        method: "POST",
        body: JSON.stringify({ request: "Complete Plaid onboarding and refresh CardSense" }),
      });
      setStartingRun(false);

      while (pollGenerationRef.current === generation) {
        const run = await api<RunStatus>(`/api/v1/runs/${queued.runId}`);
        setLiveAgents(run.agents);
        if (run.status === "complete") {
          setStep("done");
          router.refresh();
          return;
        }
        if (run.status === "failed") {
          const failure = run.agents.find((agent) => agent.status === "failed");
          throw new Error(failure?.detail || "An agent could not complete the onboarding run.");
        }
        await new Promise((resolve) => window.setTimeout(resolve, RUN_POLL_MS));
      }
    } catch (error) {
      if (pollGenerationRef.current !== generation) return;
      setStartingRun(false);
      setRunError(error instanceof Error ? error.message : "Unable to run the CardSense agents.");
    }
  }, [agents, connectionRun, router]);

  if (!open) {
    return (
      <>
        <Script
          id="plaid-link"
          src="https://cdn.plaid.com/link/v2/stable/link-initialize.js"
          strategy="afterInteractive"
          onReady={() => setPlaidReady(Boolean(window.Plaid))}
          onError={() => {
            setPlaidReady(false);
            setConnectionError("Plaid Link could not be loaded. Check your network or content blocker and try again.");
          }}
        />
        <button type="button" className="replay" onClick={() => setOpen(true)}>
          Connect accounts
        </button>
      </>
    );
  }

  return (
    <>
      <Script
        id="plaid-link"
        src="https://cdn.plaid.com/link/v2/stable/link-initialize.js"
        strategy="afterInteractive"
        onReady={() => setPlaidReady(Boolean(window.Plaid))}
        onError={() => {
          setPlaidReady(false);
          setConnectionError("Plaid Link could not be loaded. Check your network or content blocker and try again.");
        }}
      />
      <div className="scrim" onClick={close}>
      <div
        className="dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="connect-title"
        tabIndex={-1}
        ref={dialogRef}
        onClick={(e) => e.stopPropagation()}
      >
        <header className="dialog__head">
          <p className="dialog__step">
            {step === "accounts" && "Step 1 of 3"}
            {step === "documents" && "Step 2 of 3"}
            {step === "goal" && "Step 3 of 3"}
            {(step === "running" || step === "done") && "Setting up"}
          </p>
          <h2 className="dialog__title" id="connect-title">
            {step === "accounts" && "Connect the accounts you spend from"}
            {step === "documents" && "Verify your card terms"}
            {step === "goal" && "What are you trying to earn?"}
            {step === "running" && "Reading your spending"}
            {step === "done" && "Ready"}
          </h2>
        </header>

        <div className="dialog__body">
          {step === "accounts" && (
            <>
              {!linked ? (
                <>
                  <p className="dialog__lede">
                    CardSense reads transactions to work out which card earns
                    most where. It never moves money and never stores a card
                    number.
                  </p>
                  <button
                    type="button"
                    className="btn"
                    onClick={connectPlaid}
                    disabled={!plaidReady || connecting}
                  >
                    {connecting
                      ? connectionPhase === "syncing"
                        ? "Syncing transactions…"
                        : "Opening Plaid…"
                      : plaidReady
                        ? "Connect with Plaid"
                        : connectionError
                          ? "Plaid unavailable"
                          : "Loading Plaid…"}
                  </button>
                  <p className="dialog__fine">
                    Sandbox credentials — no real account is touched.
                  </p>
                  {connectionError && <p className="dialog__fine" role="alert">{connectionError}</p>}
                </>
              ) : (
                <>
                  <ul className="linked">
                    {connectedAccounts.map((account, i) => (
                      <li
                        key={account.id}
                        className="linked__item"
                        style={{ animationDelay: `${i * 260}ms` }}
                      >
                        <span className="linked__tick" aria-hidden>
                          ✓
                        </span>
                        <span className="linked__name">
                          {account.officialName || account.name}
                        </span>
                        <span className="linked__detail">
                          {[account.subtype || account.type, account.mask && `••${account.mask}`]
                            .filter(Boolean)
                            .join(" · ")}
                        </span>
                      </li>
                    ))}
                  </ul>
                  <button
                    type="button"
                    className="btn"
                    onClick={() => setStep("documents")}
                  >
                    Next
                  </button>
                </>
              )}
            </>
          )}

          {step === "documents" && (
            <>
              <p className="dialog__lede">
                These are the cards actually in your wallet. Reward rules come
                from each card&rsquo;s saved issuer terms, and CardSense will flag
                anything that needs a new source or recheck.
              </p>
              {wallet.length > 0 ? (
                <ul className="docs">
                  {wallet.map((card) => (
                    <li
                      key={card.walletId ?? card.id ?? card.cardId ?? `${card.name}-${card.last4}`}
                      className="docs__row"
                      data-state={card.parseStatus === "parsed" ? "ok" : "warn"}
                    >
                      <span className="docs__card">{card.name} · ••{card.last4}</span>
                      <span className="docs__locator">
                        {card.source.label} · {card.source.locator}
                        {card.parseStatus !== "failed" && card.nextRecheckAt
                          ? ` · next check ${dayMonth(card.nextRecheckAt)}`
                          : ""}
                      </span>
                      <span className="docs__state">
                        {card.parseStatus === "parsed"
                          ? `ready${card.parseConfidence != null ? ` · ${Math.round(card.parseConfidence * 100)}%` : ""}`
                          : card.parseStatus === "stale"
                            ? "recheck due"
                            : "needs terms"}
                      </span>
                    </li>
                  ))}
                </ul>
              ) : (
                <div className="docs__empty">
                  <p>No cards are in your wallet yet.</p>
                  <Link href="/cards">Add a card and its issuer terms</Link>
                </div>
              )}
              {wallet.some((card) => card.parseStatus !== "parsed") && (
                <p className="dialog__fine">
                  Cards needing attention are excluded from comparisons. You can continue now or {" "}
                  <Link href="/cards">review them in your wallet</Link>.
                </p>
              )}
              <button
                type="button"
                className="btn"
                onClick={() => setStep("goal")}
              >
                Next
              </button>
            </>
          )}

          {step === "goal" && (
            <>
              <p className="dialog__lede">
                Points, cash back and miles are not comparable until you say
                which one you want. You can put a number and a date on it later.
              </p>

              <div className="pform__kinds" style={{ marginTop: "1.25rem" }}>
                {TRACKS.map((t) => (
                  <button
                    key={t.id}
                    type="button"
                    className="chip"
                    aria-pressed={track === t.id}
                    onClick={() => setTrack(t.id)}
                  >
                    {t.label}
                  </button>
                ))}
              </div>

              <p className="dialog__fine">
                Not sure? Skip it and the strategy agent will pick whichever
                returns most against your actual spending.
              </p>

              <div className="pform__actions">
                <button
                  type="button"
                  className="btn"
                  disabled={startingRun}
                  onClick={() => startRun(track)}
                >
                  {startingRun ? "Saving…" : "Finish setup"}
                </button>
                <button
                  type="button"
                  className="btn btn--quiet"
                  disabled={startingRun}
                  onClick={() => {
                    setTrack(null);
                    startRun(null);
                  }}
                >
                  Skip
                </button>
              </div>
            </>
          )}

          {(step === "running" || step === "done") && (
            <>
              <ol className="stages">
                {liveAgents.map((agent) => {
                  const state = agent.status === "ok" || agent.status === "degraded"
                    ? "done"
                    : agent.status;

                  return (
                    <li key={agent.id} className="stage" data-state={state}>
                      <span className="stage__dot" aria-hidden />
                      <span className="stage__name">{agent.label}</span>
                      <span className="stage__status">
                        {state === "done" && agent.status === "degraded"
                          ? "degraded"
                          : state === "done"
                            ? "done"
                            : state === "running"
                              ? "working…"
                              : state === "failed"
                                ? "failed"
                                : "queued"}
                      </span>
                    </li>
                  );
                })}
              </ol>

              {runError && (
                <>
                  <p className="dialog__fine" role="alert">{runError}</p>
                  <button type="button" className="btn" onClick={() => startRun(track)}>
                    Retry the run
                  </button>
                </>
              )}

              {step === "done" && (
                <>
                  <p className="dialog__lede">
                    {liveAgents.some((agent) => agent.status === "degraded")
                      ? "The run completed with a visible coverage warning. Review the affected agent in Activity; all verified results are ready."
                      : "The live agent run completed and the latest verified results are ready."}
                  </p>
                  <button type="button" className="btn" onClick={close}>
                    See what you missed
                  </button>
                </>
              )}
            </>
          )}
        </div>

        <button
          type="button"
          className="dialog__close"
          onClick={close}
          aria-label="Close"
        >
          ✕
        </button>
      </div>
      </div>
    </>
  );
}
