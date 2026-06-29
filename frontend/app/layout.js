import { Fraunces, Inter, IBM_Plex_Mono } from "next/font/google";
import "./globals.css";
import { ResearchProvider } from "../context/ResearchContext";
import { UserProfileProvider } from "../context/UserProfileContext";
import Navbar from "../components/Navbar";

const fraunces = Fraunces({
  subsets: ["latin"],
  variable: "--font-display",
  weight: ["400", "500", "600"],
});

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-body",
});

const plexMono = IBM_Plex_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
  weight: ["400", "500"],
});

export const metadata = {
  title: "Research Copilot",
  description: "Map an entire ML research field from a single search.",
};

export default function RootLayout({ children }) {
  const fontVars = fraunces.variable + " " + inter.variable + " " + plexMono.variable;

  return (
    <html lang="en" className={fontVars}>
      <body>
        <UserProfileProvider>
          <ResearchProvider>
            <Navbar />
            {children}
          </ResearchProvider>
        </UserProfileProvider>
      </body>
    </html>
  );
}
