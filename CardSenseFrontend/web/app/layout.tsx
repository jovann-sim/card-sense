import type { Metadata } from "next";
import { Archivo, Public_Sans, IBM_Plex_Mono } from "next/font/google";
import { AgentRail } from "@/components/AgentRail";
import { SiteFooter } from "@/components/SiteFooter";
import { snapshot } from "@/lib/mock";
import "./globals.css";

/** Display: an expanded grotesque, used only for figures and headlines. */
const archivo = Archivo({
  subsets: ["latin"],
  axes: ["wdth"],
  variable: "--font-archivo",
  display: "swap",
});

/** Body: institutional rather than the usual product-sans default. */
const publicSans = Public_Sans({
  subsets: ["latin"],
  variable: "--font-public-sans",
  display: "swap",
});

/** Utility: every dollar figure, label, and card number on the page. */
const plexMono = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["400", "500"],
  variable: "--font-plex-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: "CardSense — Spending analytics",
  description:
    "What your spending earned, what it should have earned, and which card to reach for next.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    // The font variables must land on <html>: globals.css resolves them inside
    // `:root`, which is this element. On <body> they would be out of scope and
    // every face would quietly fall back to system-ui.
    <html
      lang="en"
      className={`${archivo.variable} ${publicSans.variable} ${plexMono.variable}`}
    >
      <body>
        <AgentRail
          agents={snapshot.agents}
          generatedAt={snapshot.generatedAt}
        />
        {children}
        <SiteFooter agents={snapshot.agents} />
      </body>
    </html>
  );
}
