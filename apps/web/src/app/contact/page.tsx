import type { Metadata } from "next";
import { PublicContactPage } from "@/features/store/store-pages";

export const metadata: Metadata = {
  title: "Nous contacter",
  description: "Écrivez à l’équipe Mamari grâce au formulaire de contact.",
};

export default function ContactRoute() {
  return <PublicContactPage />;
}
