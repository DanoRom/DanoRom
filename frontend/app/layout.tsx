import type { Metadata } from "next";
import Link from "next/link";
import NavAuth from "@/components/NavAuth";
import "./globals.css";

export const metadata: Metadata = {
  title: "Developer Platform",
  description:
    "Evaluates the build stage of your application and provides branched pathways to completion.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body suppressHydrationWarning>
        <nav className="nav">
          <Link href="/" className="nav-title">
            ⚙ Developer Platform
          </Link>
          <div className="nav-links">
            <Link href="/">Dashboard</Link>
            <NavAuth />
          </div>
        </nav>
        {children}
      </body>
    </html>
  );
}
