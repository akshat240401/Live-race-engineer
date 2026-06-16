import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Live Race Engineer",
  description: "Real-time F1 UDP telemetry and driver coaching console",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}