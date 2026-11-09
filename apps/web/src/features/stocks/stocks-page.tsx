"use client";

import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowDownLeft,
  ArrowLeftRight,
  ArrowUpRight,
  Boxes,
  ClipboardList,
  Egg,
  History,
  PackagePlus,
  Plus,
  Search,
  Wheat,
} from "lucide-react";
import {
  apiRequest,
  getApiErrorMessage,
  type UserProfile,
} from "@/lib/api/client";
import { formatDate } from "@/features/sales/sales-types";
import { MeasurementUnitSelect } from "@/features/shared/measurement-unit-select";

const stockSources = [
  { id: "agriculture", label: "Agriculture", icon: Wheat },
  { id: "elevage", label: "Élevage", icon: Egg },
  { id: "other", label: "Autres", icon: Boxes },
] as const;
type StockSource = (typeof stockSources)[number]["id"];
type DialogMode = "create" | "edit" | "movement" | "transfer" | "history" | null;
type MovementType = "opening" | "production" | "sale" | "cancellation" | "addition"
  | "loss" | "consumption" | "adjustment" | "transfer_in" | "transfer_out";

interface StockItem {
  id: string;
  product_id: string | null;
  product_name: string | null;
  source: StockSource;
  name: string;
  unit: string;
  location: string;
  minimum_quantity: number | string | null;
  balance: number | string;
  movement_count: number;
  created_at: string;
}

interface StockMovement {
  id: string;
  stock_item_id: string;
  movement_type: MovementType;
  direction: "in" | "out";
  quantity: number | string;
  movement_date: string;
  reference_type: string | null;
  reference_id: string | null;
  transfer_id: string | null;
  note: string | null;
  created_at: string;
}

interface MovementPage {
  items: StockMovement[];
  total: number;
  page: number;
  page_size: number;
}

interface CatalogProduct {
  id: string;
  name: string;
  unit: string;
  stock_quantity: number;
  is_active: boolean;
}

function formatQuantity(quantity: number | string): string {
  return new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 3 }).format(Number(quantity));
}

const movementLabels: Record<MovementType, string> = {
  opening: "Stock d’ouverture",
  production: "Production",
  sale: "Vente",
  cancellation: "Annulation de vente",
  addition: "Ajout",
  loss: "Perte",
  consumption: "Consommation",
  adjustment: "Ajustement",
  transfer_in: "Transfert reçu",
  transfer_out: "Transfert envoyé",
};

export function StocksPage() {
  const queryClient = useQueryClient();
  const [activeSource, setActiveSource] = useState<StockSource>("agriculture");
  const [search, setSearch] = useState("");
  const [mode, setMode] = useState<DialogMode>(null);
  const [selectedItem, setSelectedItem] = useState<StockItem | null>(null);
  const [historyPage, setHistoryPage] = useState(1);
  const [formError, setFormError] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const dialogRef = useRef<HTMLDialogElement>(null);
  const profile = useQuery({
    queryKey: ["auth", "me"],
    queryFn: () => apiRequest<UserProfile>("/auth/me"),
    retry: false,
  });
  const membership = profile.data?.memberships[0];
  const organizationId = membership?.organization_id;
  const canManageStock = Boolean(
    membership && ["owner", "admin", "manager"].includes(membership.role),
  );
  const canRecordStockMovement = canManageStock || membership?.role === "operator";
  const headers = organizationId ? { "X-Organization-ID": organizationId } : undefined;
  const stockQuery = useQuery({
    queryKey: ["stocks", "ledger", organizationId],
    queryFn: () => {
      if (!headers) throw new Error("Aucune organisation active n’est associée au compte.");
      return apiRequest<StockItem[]>("/stocks/items", { headers });
    },
    enabled: Boolean(headers),
    retry: false,
  });
  const productsQuery = useQuery({
    queryKey: ["stocks", "catalog-products", organizationId],
    queryFn: () => {
      if (!headers) throw new Error("Aucune organisation active n’est associée au compte.");
      return apiRequest<CatalogProduct[]>("/sales/products", { headers });
    },
    enabled: Boolean(headers && mode === "edit"),
    retry: false,
  });
  const movementsQuery = useQuery({
    queryKey: ["stocks", "movements", organizationId, selectedItem?.id, historyPage],
    queryFn: () => {
      if (!headers || !selectedItem) throw new Error("Sélectionnez un article de stock.");
      return apiRequest<MovementPage>(
        `/stocks/movements?item_id=${selectedItem.id}&page=${historyPage}&page_size=20`,
        { headers },
      );
    },
    enabled: Boolean(headers && selectedItem && mode === "history"),
    retry: false,
  });

  const visibleItems = useMemo(() => {
    const needle = search.trim().toLocaleLowerCase("fr");
    return (stockQuery.data ?? [])
      .filter((item) => item.source === activeSource)
      .filter((item) =>
        [item.name, item.location, item.product_name ?? ""]
          .join(" ")
          .toLocaleLowerCase("fr")
          .includes(needle),
      )
      .sort((a, b) => a.name.localeCompare(b.name, "fr") || a.location.localeCompare(b.location, "fr"));
  }, [activeSource, search, stockQuery.data]);
  const selectedSource = stockSources.find((source) => source.id === activeSource)!;
  const ActiveIcon = selectedSource.icon;

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (mode && !dialog.open) dialog.showModal();
    else if (!mode && dialog.open) dialog.close();
  }, [mode]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!headers) return;
    setFormError(null);
    setIsSubmitting(true);
    const formData = new FormData(event.currentTarget);
    const quantity = Number(formData.get("quantity") || 0);
    const today = new Date().toISOString().slice(0, 10);
    try {
      if (mode === "create") {
        await apiRequest("/stocks/items", {
          method: "POST",
          headers: { ...headers, "Content-Type": "application/json" },
          body: JSON.stringify({
            source: activeSource,
            name: formData.get("name"),
            unit: formData.get("unit"),
            location: formData.get("location"),
            minimum_quantity: formData.get("minimum_quantity")
              ? Number(formData.get("minimum_quantity"))
              : null,
            opening_quantity: quantity,
            note: formData.get("note") || null,
          }),
        });
        setFeedback("Article de stock créé.");
      } else if (mode === "edit" && selectedItem) {
        const productId = String(formData.get("product_id") || "");
        await apiRequest(`/stocks/items/${selectedItem.id}`, {
          method: "PATCH",
          headers: { ...headers, "Content-Type": "application/json" },
          body: JSON.stringify({
            source: formData.get("source"),
            name: formData.get("name"),
            location: formData.get("location"),
            minimum_quantity: formData.get("minimum_quantity")
              ? Number(formData.get("minimum_quantity"))
              : null,
            product_id: productId || null,
          }),
        });
        setFeedback("Article de stock mis à jour.");
      } else if (mode === "movement" && selectedItem) {
        const movementType = String(formData.get("movement_type"));
        const payload: Record<string, unknown> = {
          movement_type: movementType,
          quantity,
          movement_date: formData.get("movement_date") || today,
          note: formData.get("note"),
        };
        if (movementType === "adjustment") payload.direction = formData.get("direction");
        await apiRequest(`/stocks/items/${selectedItem.id}/movements`, {
          method: "POST",
          headers: { ...headers, "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        setFeedback("Mouvement de stock enregistré.");
      } else if (mode === "transfer" && selectedItem) {
        await apiRequest(`/stocks/items/${selectedItem.id}/transfers`, {
          method: "POST",
          headers: { ...headers, "Content-Type": "application/json" },
          body: JSON.stringify({
            destination_item_id: formData.get("destination_item_id"),
            quantity,
            movement_date: formData.get("movement_date") || today,
            note: formData.get("note") || null,
          }),
        });
        setFeedback("Transfert de stock enregistré.");
      }
      setMode(null);
      setSelectedItem(null);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["stocks", "ledger"] }),
        queryClient.invalidateQueries({ queryKey: ["stocks", "movements"] }),
        queryClient.invalidateQueries({ queryKey: ["sales", "products"] }),
        queryClient.invalidateQueries({ queryKey: ["dashboard", "overview"] }),
      ]);
    } catch (error) {
      setFormError(getApiErrorMessage(error));
    } finally {
      setIsSubmitting(false);
    }
  }

  const currentItem = selectedItem;
  const transferDestinations = (stockQuery.data ?? []).filter(
    (item) =>
      currentItem &&
      item.id !== currentItem.id &&
      item.name === currentItem.name &&
      item.unit === currentItem.unit &&
      item.location !== currentItem.location,
  );

  return (
    <div className="dashboard-content stocks-workspace">
      <section className="page-heading" aria-labelledby="stocks-title">
        <div>
          <p className="eyebrow">Mouvements et quantités disponibles</p>
          <h1 className="page-title" id="stocks-title">Stocks</h1>
          <p className="page-description">
            Consultez les soldes réels et tracez les entrées, ventes, pertes et consommations.
          </p>
        </div>
        {canManageStock ? (
          <button className="button-primary" onClick={() => { setSelectedItem(null); setFormError(null); setMode("create"); }} type="button">
            <Plus size={16} /> Nouvel article
          </button>
        ) : null}
      </section>

      {feedback ? <p className="admin-success sales-feedback" role="status">{feedback}</p> : null}
      {stockQuery.isError || profile.isError ? (
        <p className="auth-error" role="alert">{getApiErrorMessage(stockQuery.error ?? profile.error)}</p>
      ) : null}
      {profile.data && !organizationId ? (
        <p className="auth-error" role="alert">Aucune organisation active n’est associée au compte.</p>
      ) : null}

      <div className="stocks-tabs" role="group" aria-label="Origine des stocks">
        {stockSources.map(({ id, label, icon: Icon }) => (
          <button
            aria-pressed={activeSource === id}
            className="stocks-tab"
            key={id}
            onClick={() => { setActiveSource(id); setSearch(""); }}
            type="button"
          >
            <Icon size={16} />
            {label}
            <span>{stockQuery.data?.filter((item) => item.source === id).length ?? 0}</span>
          </button>
        ))}
      </div>

      <section className="stocks-panel" aria-labelledby="stocks-panel-title">
        <div className="stocks-panel-heading">
          <div className="stocks-title-icon"><ActiveIcon size={20} /></div>
          <div>
            <h2 id="stocks-panel-title">Stocks · {selectedSource.label.toLowerCase()}</h2>
            <p>Les soldes sont calculés à partir du journal de mouvements.</p>
          </div>
        </div>

        <div className="stocks-summary-grid" aria-label="Résumé du stock">
          <article className="stocks-summary-card">
            <span>Articles suivis</span>
            <strong>{visibleItems.length}</strong>
            <small>dans cette catégorie</small>
          </article>
          <article className="stocks-summary-card stocks-summary-highlight">
            <span>Mouvements enregistrés</span>
            <strong>{visibleItems.reduce((sum, item) => sum + item.movement_count, 0)}</strong>
            <small>historique conservé</small>
          </article>
          <article className="stocks-summary-card">
            <span>Origine des soldes</span>
            <strong>Journal</strong>
            <small>ouverture + entrées − sorties</small>
          </article>
        </div>

        <section className="stocks-records" aria-labelledby="stocks-records-title">
          <div className="stocks-section-heading stocks-records-heading">
            <div>
              <h3 id="stocks-records-title">Articles disponibles</h3>
              <p>{visibleItems.length} article{visibleItems.length === 1 ? "" : "s"}</p>
            </div>
            <label className="stocks-search">
              <Search size={16} aria-hidden="true" />
              <span className="visually-hidden">Rechercher un article de stock</span>
              <input
                onChange={(event) => setSearch(event.currentTarget.value)}
                placeholder="Rechercher un article, un lieu…"
                type="search"
                value={search}
              />
            </label>
          </div>

          {stockQuery.isPending ? (
            <p className="stocks-loading" role="status">Chargement des stocks…</p>
          ) : visibleItems.length ? (
            <div className="stocks-record-list">
              {visibleItems.map((item) => (
                <article className="stocks-record" key={item.id}>
                  <span className="stocks-record-icon">
                    {item.source === "agriculture" ? <Wheat size={18} /> : item.source === "elevage" ? <Egg size={18} /> : <Boxes size={18} />}
                  </span>
                  <div className="stocks-record-main">
                    <div>
                      <strong>{item.name}</strong>
                      <small>{item.product_name ? `Produit catalogue · ${item.product_name}` : `${item.movement_count} mouvement(s)`}</small>
                    </div>
                    <span className="stocks-record-location">{item.location}</span>
                  </div>
                  <b>
                    {formatQuantity(item.balance)} <small>{item.unit}</small>
                    {item.minimum_quantity !== null && Number(item.balance) <= Number(item.minimum_quantity)
                      ? <small className="stocks-low-stock-label">Sous le seuil</small>
                      : null}
                  </b>
                  <div className="stocks-item-actions">
                    <button aria-label={`Historique ${item.name}`} onClick={() => { setSelectedItem(item); setHistoryPage(1); setMode("history"); }} title="Historique" type="button">
                      <History size={16} />
                    </button>
                    {canRecordStockMovement ? (
                      <button aria-label={`Ajouter un mouvement pour ${item.name}`} onClick={() => { setSelectedItem(item); setFormError(null); setMode("movement"); }} title="Entrée ou sortie" type="button">
                        <ClipboardList size={16} />
                      </button>
                    ) : null}
                    {canManageStock ? (
                      <>
                        <button aria-label={`Transférer ${item.name}`} onClick={() => { setSelectedItem(item); setFormError(null); setMode("transfer"); }} title="Transfert" type="button">
                          <ArrowLeftRight size={16} />
                        </button>
                        <button aria-label={`Modifier ${item.name}`} onClick={() => { setSelectedItem(item); setFormError(null); setMode("edit"); }} title="Modifier" type="button">
                          <PackagePlus size={16} />
                        </button>
                      </>
                    ) : null}
                  </div>
                </article>
              ))}
            </div>
          ) : (
            <div className="stocks-empty">
              <span><Boxes size={22} /></span>
              <h3>{stockQuery.data?.length ? "Aucun résultat" : "Aucun article de stock"}</h3>
              <p>
                {stockQuery.data?.length
                  ? "Essayez une autre recherche ou choisissez une autre catégorie."
                  : "Ajoutez un article pour commencer à suivre son stock physique."}
              </p>
            </div>
          )}
        </section>
      </section>

      <dialog
        aria-labelledby="stock-dialog-title"
        className="parcel-edit-dialog sales-order-dialog"
        onClose={() => setMode(null)}
        onClick={(event) => { if (event.target === event.currentTarget) dialogRef.current?.close(); }}
        ref={dialogRef}
      >
        <div className="parcel-edit-dialog-content">
          <div className="parcel-edit-dialog-heading">
            <div>
              <h2 id="stock-dialog-title">
                {mode === "create" ? "Nouvel article de stock"
                  : mode === "edit" ? "Modifier l’article"
                    : mode === "movement" ? "Enregistrer un mouvement"
                      : mode === "transfer" ? "Transférer le stock"
                        : "Historique des mouvements"}
              </h2>
              <p>{currentItem ? `${currentItem.name} · ${currentItem.location}` : "Créez un article avec son unité et son lieu de stockage."}</p>
            </div>
            <button aria-label="Fermer" className="parcel-edit-dialog-close" onClick={() => dialogRef.current?.close()} type="button">×</button>
          </div>

          {mode === "history" ? (
            <div className="stocks-dialog-history">
              {movementsQuery.isPending ? <p role="status">Chargement de l’historique…</p> : null}
              {movementsQuery.isError ? <p className="auth-error" role="alert">{getApiErrorMessage(movementsQuery.error)}</p> : null}
              {movementsQuery.data?.items.length ? movementsQuery.data.items.map((movement) => (
                <article className="stocks-record" key={movement.id}>
                  <span className="stocks-record-icon">
                    {movement.direction === "in" ? <ArrowDownLeft size={18} /> : <ArrowUpRight size={18} />}
                  </span>
                  <div className="stocks-record-main">
                    <div>
                      <strong>{movementLabels[movement.movement_type]}</strong>
                      <small>{movement.note || "Aucune note"}</small>
                    </div>
                  </div>
                  <time dateTime={movement.movement_date}>{formatDate(movement.movement_date)}</time>
                  <b>{movement.direction === "in" ? "+" : "−"}{formatQuantity(movement.quantity)} <small>{currentItem?.unit}</small></b>
                </article>
              )) : null}
              {movementsQuery.data && !movementsQuery.data.items.length ? <p>Aucun mouvement enregistré.</p> : null}
              {movementsQuery.data && movementsQuery.data.total > movementsQuery.data.page_size ? (
                <nav className="stocks-pagination" aria-label="Pagination de l’historique des mouvements">
                  <button
                    disabled={historyPage === 1}
                    onClick={() => setHistoryPage((page) => page - 1)}
                    type="button"
                  >
                    Précédent
                  </button>
                  <span>
                    Page {historyPage} sur {Math.ceil(movementsQuery.data.total / movementsQuery.data.page_size)}
                  </span>
                  <button
                    disabled={historyPage >= Math.ceil(movementsQuery.data.total / movementsQuery.data.page_size)}
                    onClick={() => setHistoryPage((page) => page + 1)}
                    type="button"
                  >
                    Suivant
                  </button>
                </nav>
              ) : null}
            </div>
          ) : (
            <form className="sales-order-form sales-order-dialog-form" onSubmit={handleSubmit}>
              {mode === "create" ? (
                <>
                  <label className="auth-field"><span>Nom / nature</span><input autoFocus maxLength={160} minLength={2} name="name" required /></label>
                  <div className="auth-form-grid">
                    <label className="auth-field"><span>Unité</span><MeasurementUnitSelect name="unit" required /></label>
                    <label className="auth-field"><span>Lieu de stockage</span><input defaultValue="Magasin" maxLength={120} name="location" required /></label>
                    <label className="auth-field"><span>Seuil minimum (facultatif)</span><input min="0" name="minimum_quantity" step="0.001" type="number" /></label>
                  </div>
                  <label className="auth-field"><span>Stock d’ouverture (facultatif)</span><input min="0" name="quantity" step="0.001" type="number" defaultValue="0" /></label>
                  <label className="auth-field"><span>Note</span><textarea maxLength={1000} name="note" rows={2} /></label>
                </>
              ) : null}
              {mode === "edit" && currentItem ? (
                <>
                  <label className="auth-field"><span>Origine</span>
                    <select defaultValue={currentItem.source} name="source">
                      {stockSources.map((source) => <option key={source.id} value={source.id}>{source.label}</option>)}
                    </select>
                  </label>
                  <label className="auth-field"><span>Nom / nature</span><input autoFocus defaultValue={currentItem.name} maxLength={160} minLength={2} name="name" required /></label>
                  <label className="auth-field"><span>Lieu de stockage</span><input defaultValue={currentItem.location} maxLength={120} name="location" required /></label>
                  <label className="auth-field"><span>Seuil minimum (facultatif)</span><input defaultValue={currentItem.minimum_quantity ?? ""} min="0" name="minimum_quantity" step="0.001" type="number" /></label>
                  <label className="auth-field"><span>Produit du catalogue (optionnel)</span>
                    <select defaultValue={currentItem.product_id ?? ""} name="product_id">
                      <option value="">Aucun lien</option>
                      {productsQuery.data?.filter((product) =>
                        (product.is_active || product.id === currentItem.product_id) &&
                        product.unit === currentItem.unit,
                      ).map((product) => (
                        <option key={product.id} value={product.id}>{product.name} · {product.stock_quantity} {product.unit}</option>
                      ))}
                    </select>
                  </label>
                  {productsQuery.isError ? <p className="auth-error" role="alert">{getApiErrorMessage(productsQuery.error)}</p> : null}
                  <p className="stocks-form-help">Un produit lié utilisera ce solde pour les ventes. Unités attendues : {currentItem.unit}.</p>
                </>
              ) : null}
              {mode === "movement" ? (
                <>
                  <label className="auth-field"><span>Type de mouvement</span>
                    <select name="movement_type">
                      <option value="addition">Ajout / approvisionnement</option>
                      <option value="loss">Perte</option>
                      <option value="consumption">Consommation</option>
                      {canManageStock ? <option value="adjustment">Ajustement d’inventaire</option> : null}
                    </select>
                  </label>
                  {canManageStock ? (
                    <label className="auth-field"><span>Sens (pour un ajustement)</span>
                      <select defaultValue="out" name="direction"><option value="in">Entrée</option><option value="out">Sortie</option></select>
                    </label>
                  ) : null}
                  <div className="auth-form-grid">
                    <label className="auth-field"><span>Quantité ({currentItem?.unit})</span><input autoFocus min="0.001" name="quantity" required step="0.001" type="number" /></label>
                    <label className="auth-field"><span>Date</span><input defaultValue={new Date().toISOString().slice(0, 10)} name="movement_date" required type="date" /></label>
                  </div>
                  <label className="auth-field"><span>Motif / référence</span><textarea maxLength={1000} minLength={2} name="note" required rows={2} /></label>
                </>
              ) : null}
              {mode === "transfer" ? (
                <>
                  <label className="auth-field"><span>Lieu de destination</span>
                    <select name="destination_item_id" required>
                      <option value="">Choisir un lieu</option>
                      {transferDestinations.map((item) => <option key={item.id} value={item.id}>{item.location} · {formatQuantity(item.balance)} {item.unit}</option>)}
                    </select>
                  </label>
                  {!transferDestinations.length ? <p className="stocks-form-help">Créez d’abord un article de même nature et unité dans un autre lieu.</p> : null}
                  <div className="auth-form-grid">
                    <label className="auth-field"><span>Quantité ({currentItem?.unit})</span><input autoFocus min="0.001" name="quantity" required step="0.001" type="number" /></label>
                    <label className="auth-field"><span>Date</span><input defaultValue={new Date().toISOString().slice(0, 10)} name="movement_date" required type="date" /></label>
                  </div>
                  <label className="auth-field"><span>Note</span><textarea maxLength={1000} name="note" rows={2} /></label>
                </>
              ) : null}
              {formError ? <p className="auth-error" role="alert">{formError}</p> : null}
              <div className="parcel-edit-dialog-actions">
                <button className="button-secondary" onClick={() => dialogRef.current?.close()} type="button">Annuler</button>
                <button className="button-primary" disabled={isSubmitting || (mode === "transfer" && !transferDestinations.length)} type="submit">
                  {isSubmitting ? "Enregistrement…" : mode === "create" ? "Créer l’article" : mode === "edit" ? "Enregistrer" : mode === "transfer" ? "Transférer" : "Enregistrer le mouvement"}
                </button>
              </div>
            </form>
          )}
        </div>
      </dialog>
    </div>
  );
}
