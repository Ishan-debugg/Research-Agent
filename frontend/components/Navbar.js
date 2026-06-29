"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useResearch } from "../context/ResearchContext";

const LINKS = [
  { href: "/", label: "Home", needsData: false },
  { href: "/search", label: "Search", needsData: false },
  { href: "/results", label: "Results", needsData: true },
  { href: "/graph", label: "Graph", needsData: true },
  { href: "/history", label: "History", needsData: false },
  { href: "/settings", label: "Settings", needsData: false },
];

export default function Navbar() {
  const pathname = usePathname();
  const research = useResearch();

  return (
    <nav className="sticky top-0 z-50 border-b border-[var(--border)] bg-[var(--bg)]/90 backdrop-blur">
      <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
        <Link href="/" className="font-[var(--font-display)] text-lg tracking-tight">
          Research<span className="text-[var(--accent)]">Copilot</span>
        </Link>
        <div className="flex items-center gap-5 text-sm">
          {LINKS.map(function (link) {
            const disabled = link.needsData && !research.data;
            const active = pathname === link.href;

            if (disabled) {
              return (
                <span key={link.href} className="text-[var(--text-muted)] opacity-40 cursor-not-allowed">
                  {link.label}
                </span>
              );
            }

            return (
              <Link
                key={link.href}
                href={link.href}
                className={
                  active
                    ? "text-[var(--accent)]"
                    : "text-[var(--text-muted)] hover:text-[var(--text)] transition-colors"
                }
              >
                {link.label}
              </Link>
            );
          })}
        </div>
      </div>
    </nav>
  );
}