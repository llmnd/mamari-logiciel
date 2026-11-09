import type { Metadata } from "next";
import { StorePage } from "@/features/store/store-pages";

export const metadata: Metadata = {
  title: "La boutique Mamari",
  description: "Découvrez et commandez les produits proposés par Mamari.",
};

export default function ProductsRoute() {
  return <StorePage />;
}
