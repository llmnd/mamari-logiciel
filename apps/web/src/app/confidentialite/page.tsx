import type { Metadata } from "next";
import { PublicLegalPage } from "@/features/store/store-pages";

export const metadata: Metadata = {
  title: "Confidentialité",
  description: "Informations sur les données recueillies par le site Mamari.",
};

export default function PrivacyRoute() {
  return <PublicLegalPage kind="privacy" />;
}
