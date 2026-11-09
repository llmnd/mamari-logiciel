import type { Metadata } from "next";
import { PublicHomePage } from "@/features/store/store-pages";

export const metadata: Metadata = {
  title: "Mamari — Agriculture, élevage et produits",
  description:
    "Découvrez les activités agricoles de Mamari, son histoire et ses produits au rythme des saisons.",
};

export default function Home() {
  return <PublicHomePage />;
}
