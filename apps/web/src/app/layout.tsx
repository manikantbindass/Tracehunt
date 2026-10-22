import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "TraceHunt AI · See the signal",
  description: "API monitoring, log exploration, and AI-powered incident intelligence in one connected workspace.",
  icons: { icon: "/icon.svg" },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
