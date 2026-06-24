import "./globals.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "LedgerFlow — Invoice Intake",
  description:
    "Confidence-gated invoice automation with a human-in-the-loop review queue.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen antialiased">{children}</body>
    </html>
  );
}
