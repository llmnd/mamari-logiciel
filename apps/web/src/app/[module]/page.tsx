import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowRight, Construction } from "lucide-react";
import { UserManagement } from "@/features/administration/user-management";
import { AgriculturePage } from "@/features/agriculture/agriculture-page";
import { OperationsPage } from "@/features/operations/operations-page";
import { SalesPage } from "@/features/sales/sales-page";
import { LivestockPage } from "@/features/livestock/livestock-page";
import { ProductionPage } from "@/features/production/production-page";
import { CustomersPage } from "@/features/customers/customers-page";
import { StocksPage } from "@/features/stocks/stocks-page";
import { FinancesPage } from "@/features/finances/finances-page";
import { HumanResourcesPage } from "@/features/human-resources/human-resources-page";
import { CommunicationPage } from "@/features/communication/communication-page";
import { CompanyPage } from "@/features/company/company-page";
import { ActivityPage } from "@/features/audit/activity-page";
import { ReportsPage } from "@/features/dashboard/reports-page";
import { PublicInboxPage } from "@/features/public-site/public-inbox-page";

const modules: Record<string, { title: string; description: string }> = {
  operations: {
    title: "Opérations",
    description: "Planifiez les activités et suivez le travail de vos équipes.",
  },
  agriculture: {
    title: "Agriculture",
    description: "Pilotez vos exploitations, parcelles, campagnes et récoltes.",
  },
  elevage: {
    title: "Élevage",
    description: "Suivez vos bâtiments, animaux, lots, soins et productions.",
  },
  stocks: {
    title: "Stocks",
    description: "Centralisez vos produits, inventaires et mouvements de stock.",
  },
  productions: {
    title: "Productions",
    description: "Organisez les lots et le suivi de vos productions.",
  },
  ventes: {
    title: "Ventes",
    description: "Gérez vos clients, commandes, factures et règlements.",
  },
  clients: {
    title: "Clients",
    description: "Centralisez les coordonnées des particuliers et professionnels de Mamari.",
  },
  finances: {
    title: "Finances",
    description: "Suivez vos dépenses, recettes, budgets et marges.",
  },
  rh: {
    title: "Ressources humaines",
    description: "Organisez vos collaborateurs, équipes et responsabilités.",
  },
  communication: {
    title: "Communication",
    description: "Préparez vos actualités, contenus et médias.",
  },
  entreprise: {
    title: "Entreprise",
    description: "Retrouvez les informations et la structure de votre entreprise.",
  },
  administration: {
    title: "Administration",
    description: "Configurez les utilisateurs, rôles et paramètres de la plateforme.",
  },
  aide: {
    title: "Centre d'aide",
    description: "Retrouvez les ressources et informations pour vous accompagner.",
  },
  activite: {
    title: "Activité et approbations",
    description: "Suivez le journal d’activité et traitez les demandes soumises par les équipes.",
  },
  rapports: {
    title: "Rapports d’activité",
    description: "Comparez et exportez les indicateurs opérationnels de votre organisation.",
  },
  messages: {
    title: "Messages et newsletter",
    description: "Consultez les demandes du site public et les inscriptions à la newsletter.",
  },
};

export function generateStaticParams() {
  return Object.keys(modules).map((module) => ({ module }));
}

export default async function ModulePage({
  params,
}: {
  params: Promise<{ module: string }>;
}) {
  const { module } = await params;
  const page = modules[module];
  if (!page) notFound();
  if (module === "operations") return <OperationsPage />;
  if (module === "ventes") return <SalesPage />;
  if (module === "clients") return <CustomersPage />;
  if (module === "agriculture") return <AgriculturePage />;
  if (module === "elevage") return <LivestockPage />;
  if (module === "productions") return <ProductionPage />;
  if (module === "stocks") return <StocksPage />;
  if (module === "finances") return <FinancesPage />;
  if (module === "rh") return <HumanResourcesPage />;
  if (module === "communication") return <CommunicationPage />;
  if (module === "entreprise") return <CompanyPage />;
  if (module === "activite") return <ActivityPage />;
  if (module === "rapports") return <ReportsPage />;
  if (module === "messages") return <PublicInboxPage />;

  return (
    <div className="dashboard-content">
      <section className="page-heading" aria-labelledby="module-title">
        <div>
          <p className="eyebrow">Espace de travail</p>
          <h1 className="page-title" id="module-title">{page.title}</h1>
          <p className="page-description">{page.description}</p>
        </div>
      </section>
      {module === "administration" ? (
        <UserManagement />
      ) : (
      <section className="panel module-placeholder">
        <span className="module-placeholder-icon">
          <Construction size={21} />
        </span>
        <h2>Votre espace {page.title.toLowerCase()} prend forme</h2>
        <p>
          La navigation et les fondations de ce module sont en place. Les
          fonctionnalités métier seront ajoutées progressivement, avec des
          données fiables et reliées aux autres activités de l&apos;entreprise.
        </p>
        <Link className="module-back-link" href="/">
          Retour au tableau de bord <ArrowRight size={14} />
        </Link>
      </section>
      )}
    </div>
  );
}
