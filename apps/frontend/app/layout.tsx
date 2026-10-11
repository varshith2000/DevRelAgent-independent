import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./theme.css";
import { SetupGate } from "../components/SetupGate";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "DevRelAgent — Engineering Support Workspace",
  description: "A self-hosted developer-support assistant for engineering questions, configured knowledge sources, and human-reviewed actions.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  // The interface is dark-only (see theme.css), so the dark variant is pinned
  // on the root element instead of following the visitor's OS colour scheme.
  return (
    <html lang="en" className="dark">
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased`}
      >
        <SetupGate>{children}</SetupGate>
      </body>
    </html>
  );
}
