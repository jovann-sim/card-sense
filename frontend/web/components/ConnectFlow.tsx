"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import Script from "next/script";
import type { AgentRun } from "@/lib/types";
import { api, userId } from "@/lib/client-api";

/**
 * Onboarding, as a dialog over the dashboard rather than its own route — the
 * dashboard fills in behind it as each agent reports.
 *
 * The agent sequence is a *replay*, not a live run. Real runtime is around 26
 * seconds, which is far too long for a four-minute video and a live sandbox
 * call is a bad thing to depend on while recording. Timings below are paced for
 * the camera; swap `STAGE_MS` for real stage transitions when the agents are
 * wired up and you want the honest version.
 */
const STAGE_MS = 1_600;

const INSTITUTIONS = [
  { name: "Chase", detail: "3 cards · 2 accounts" },
  { name: "Amex", detail: "1 card" },
];

const DOCUMENTS = [
  { card: "Sapphire Reserve", locator: "terms-sapphire-2026.pdf", state: "ok" },
  { card: "Everyday Blue", locator: "everydayblue-terms.pdf", state: "ok" },
  { card: "Horizon Miles", locator: "horizon-benefits.html", state: "ok" },
  { card: "Cashback One", locator: "cashbackone.com/rates", state: "ok" },
  { card: "Meridian Signature", locator: "meridian-terms.pdf", state: "warn" },
] as const;

type Step = "accounts" | "documents" | "goal" | "running" | "done";

const TRACKS = [
  { id: "points", label: "Points" },
  { id: "cashback", label: "Cash back" },
  { id: "miles", label: "Air miles" },
] as const;

export function ConnectFlow({ agents }: { agents: AgentRun[] }) {
  const [open, setOpen] = useState(false);
  const [step, setStep] = useState<Step>("accounts");
  const [linked, setLinked] = useState(false);
  const [track, setTrack] = useState<string | null>(null);
  const [stage, setStage] = useState(-1);
  const [plaidReady, setPlaidReady] = useState(false);
  const [connecting, setConnecting] = useState(false);
  const [connectionError, setConnectionError] = useState<string | null>(null);
  const dialogRef = useRef<HTMLDivElement>(null);
  const linkRef = useRef<ReturnType<NonNullable<Window["Plaid"]>["create"]> | null>(null);
  const syncingRef = useRef(false);
  const router = useRouter();

  const destroyLink = useCallback(() => {
    linkRef.current?.destroy();
    linkRef.current = null;
  }, []);

  const completePlaidConnection = useCallback(async (publicToken: string) => {
    syncingRef.current = true;
    try {
      await api("/api/v1/plaid/exchange-token", {
        method: "POST", body: JSON.stringify({ publicToken, userId }),
      });
      await api("/api/v1/plaid/sync", { method: "POST", body: JSON.stringify({ userId }) });
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
    destroyLink();
    setOpen(false);
    setStep("accounts");
    setLinked(false);
    setTrack(null);
    setStage(-1);
  }, [destroyLink]);

  useEffect(() => {
    if (!open) return;
    dialogRef.current?.focus();

    const onKey = (e: KeyboardEvent) => e.key === "Escape" && close();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, close]);

  // Someone who has asked for less motion gets the finished state, not a
  // staged reveal they did not ask to sit through.
  const startRun = useCallback(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      setStage(agents.length);
      setStep("done");
      return;
    }
    setStage(0);
    setStep("running");
  }, [agents.length]);

  // Walk the agents one at a time once the run starts.
  useEffect(() => {
    if (step !== "running") return;

    if (stage >= agents.length) {
      const t = setTimeout(() => setStep("done"), 600);
      return () => clearTimeout(t);
    }

    const t = setTimeout(() => setStage((s) => s + 1), STAGE_MS);
    return () => clearTimeout(t);
  }, [step, stage, agents.length]);

  if (!open) {
    return (
      <>
        <Script id="plaid-link" src="https://cdn.plaid.com/link/v2/stable/link-initialize.js" strategy="afterInteractive" onLoad={() => setPlaidReady(true)} />
        <button type="button" className="replay" onClick={() => setOpen(true)}>
          Replay connect
        </button>
      </>
    );
  }

  return (
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
            {step === "documents" && "Point us at your card terms"}
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
                    {connecting ? "Connecting…" : plaidReady ? "Connect with Plaid" : "Loading Plaid…"}
                  </button>
                  <p className="dialog__fine">
                    Sandbox credentials — no real account is touched.
                  </p>
                  {connectionError && <p className="dialog__fine" role="alert">{connectionError}</p>}
                </>
              ) : (
                <>
                  <ul className="linked">
                    {INSTITUTIONS.map((inst, i) => (
                      <li
                        key={inst.name}
                        className="linked__item"
                        style={{ animationDelay: `${i * 260}ms` }}
                      >
                        <span className="linked__tick" aria-hidden>
                          ✓
                        </span>
                        <span className="linked__name">{inst.name}</span>
                        <span className="linked__detail">{inst.detail}</span>
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
                Reward rules come from the issuer&rsquo;s own terms. Give us a
                link or a PDF for each card and the card intelligence agent
                rereads them weekly.
              </p>
              <ul className="docs">
                {DOCUMENTS.map((doc) => (
                  <li key={doc.card} className="docs__row" data-state={doc.state}>
                    <span className="docs__card">{doc.card}</span>
                    <span className="docs__locator">{doc.locator}</span>
                    <span className="docs__state">
                      {doc.state === "ok" ? "ready" : "may not parse"}
                    </span>
                  </li>
                ))}
              </ul>
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
                <button type="button" className="btn" onClick={startRun}>
                  Start the agents
                </button>
                <button
                  type="button"
                  className="btn btn--quiet"
                  onClick={() => {
                    setTrack(null);
                    startRun();
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
                {agents.map((agent, i) => {
                  const state =
                    i < stage ? "done" : i === stage ? "running" : "queued";

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
                              : "queued"}
                      </span>
                    </li>
                  );
                })}
              </ol>

              {step === "done" && (
                <>
                  <p className="dialog__lede">
                    One card&rsquo;s terms did not parse, so it is excluded from
                    every comparison until it does. Everything else is ready.
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
  );
}
