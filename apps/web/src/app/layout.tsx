import type { Metadata } from "next";
import type { ReactNode } from "react";
import { AppShell } from "@/components/app-shell";
import { Providers } from "@/components/providers";
import "leaflet/dist/leaflet.css";
import "lenis/dist/lenis.css";
import "./globals.css";
import "./refined.css";
import "./refined-plus.css";
import "./auth.css";
import "./public.css";

export const metadata: Metadata = {
  title: {
    default: "Mamari — Pilotage d'entreprise",
    template: "%s — Mamari",
  },
  description:
    "La plateforme de pilotage des activités et des opérations de votre entreprise.",
};

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="fr">
      <body>
        <Providers>
          <AppShell>{children}</AppShell>
        </Providers>
      </body>
    </html>
  );
}
