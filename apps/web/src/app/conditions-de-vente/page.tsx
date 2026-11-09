import type { Metadata } from "next";
import { PublicLegalPage } from "@/features/store/store-pages";

export const metadata: Metadata = {
  title: "Conditions de vente",
  description: "Informations provisoires sur les commandes et conditions de vente Mamari.",
};

export default function SalesConditionsRoute() {
  return <PublicLegalPage kind="sales" />;
}
