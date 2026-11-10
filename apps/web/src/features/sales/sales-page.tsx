"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useDeferredValue, useEffect, useRef, useState, type FormEvent } from "react";
import {
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Plus,
  Search,
  ShoppingBasket,
  Trash2,
} from "lucide-react";
import Link from "next/link";
import {
  apiRequest,
  getApiErrorMessage,
  type UserProfile,
} from "@/lib/api/client";
import { CustomerSelect } from "@/features/customers/customer-select";
import type { Customer } from "@/features/customers/customer-types";
import { OrderProductImage } from "@/features/shared/order-product-image";
import {
  formatDate,
  formatFcfa,
  orderStatusLabels,
  type OrderStatus,
  type SalesOrder,
  type SalesOrderPage,
} from "@/features/sales/sales-types";

const statuses = ["pending", "confirmed", "preparing", "delivered", "cancelled"] as const;

interface CatalogProduct {
  id: string;
  name: string;
  unit: string;
  price_fcfa: number;
  stock_quantity: number;
  is_active: boolean;
  photo_url: string | null;
}

interface OrderLineDraft {
  product_id: string;
  quantity: number;
}

function isOrderStatus(value: string): value is OrderStatus {
  return statuses.some((status) => status === value);
}

export function SalesPage() {
  const queryClient = useQueryClient();
  const [formError, setFormError] = useState<string | null>(null);
  const [formMessage, setFormMessage] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<OrderStatus | "all">("all");
  const [page, setPage] = useState(1);
  const [selectedCustomer, setSelectedCustomer] = useState<Customer | null>(null);
  const [orderDialogOpen, setOrderDialogOpen] = useState(false);
  const [orderLines, setOrderLines] = useState<OrderLineDraft[]>([{ product_id: "", quantity: 1 }]);
  const orderDialogRef = useRef<HTMLDialogElement>(null);
  const deferredSearch = useDeferredValue(search.trim());
  const profile = useQuery({
    queryKey: ["auth", "me"],
    queryFn: () => apiRequest<UserProfile>("/auth/me"),
    retry: false,
  });
  const membership = profile.data?.memberships[0];
  const isOperator = membership?.role === "operator";
  const products = useQuery({
    queryKey: ["sales", "products", membership?.organization_id],
    queryFn: () => {
      if (!membership) throw new Error("Aucune organisation active n’est associée au compte.");
      return apiRequest<CatalogProduct[]>("/sales/products", {
        headers: { "X-Organization-ID": membership.organization_id },
      });
    },
    enabled: Boolean(membership),
    retry: false,
  });
  const orders = useQuery({
    queryKey: [
      "sales",
      "orders",
      membership?.organization_id,
      deferredSearch,
      statusFilter,
      page,
    ],
    queryFn: () => {
      if (!membership) throw new Error("Aucune organisation active n’est associée au compte.");
      const params = new URLSearchParams({
        page: String(page),
        page_size: "20",
      });
      if (deferredSearch) params.set("search", deferredSearch);
      if (statusFilter !== "all") params.set("status", statusFilter);
      return apiRequest<SalesOrderPage>(`/sales/orders?${params}`, {
        headers: { "X-Organization-ID": membership.organization_id },
      });
    },
    enabled: Boolean(membership),
    retry: false,
  });
  const canManageSales = Boolean(
    membership && ["owner", "admin", "manager", "operator"].includes(membership.role),
  );
  const updateStatus = useMutation({
    mutationFn: ({ id, status }: { id: string; status: OrderStatus }) => {
      if (!membership) throw new Error("Aucune organisation active n’est associée au compte.");
      return apiRequest<SalesOrder>(`/sales/orders/${id}/status`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          "X-Organization-ID": membership.organization_id,
        },
        body: JSON.stringify({ status }),
      });
    },
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["sales", "orders"] }),
        queryClient.invalidateQueries({ queryKey: ["dashboard", "overview"] }),
      ]);
    },
  });

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFormError(null);
    setFormMessage(null);
    setIsSubmitting(true);

    const form = event.currentTarget;
    const formData = new FormData(form);
    try {
      if (!membership) throw new Error("Aucune organisation active n’est associée au compte.");
      const order = await apiRequest<SalesOrder>("/sales/orders", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Organization-ID": membership.organization_id,
        },
        body: JSON.stringify({
          customer_id: formData.get("customer_id")?.toString(),
          order_date: formData.get("order_date")?.toString(),
          items: orderLines.map((line) => ({
            product_id: line.product_id,
            quantity: Number(line.quantity),
          })),
        }),
      });
      form.reset();
      setSelectedCustomer(null);
      setOrderLines([{ product_id: "", quantity: 1 }]);
      setFormError(null);
      orderDialogRef.current?.close();
      setPage(1);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["sales", "orders"] }),
        queryClient.invalidateQueries({ queryKey: ["dashboard", "overview"] }),
      ]);
      setFormMessage(`Commande ${order.reference} enregistrée.`);
    } catch (error) {
      setFormError(getApiErrorMessage(error));
    } finally {
      setIsSubmitting(false);
    }
  }

  const today = new Date().toISOString().slice(0, 10);
  const ordersData = orders.data;
  const productById = new Map((products.data ?? []).map((product) => [product.id, product]));
  const totalPages = Math.ceil((ordersData?.total ?? 0) / (ordersData?.page_size ?? 20));
  const availableProducts = (products.data ?? []).filter(
    (product) => product.is_active && product.stock_quantity > 0,
  );
  const orderTotal = orderLines.reduce((total, line) => {
    const product = availableProducts.find((item) => item.id === line.product_id);
    return total + (product?.price_fcfa ?? 0) * line.quantity;
  }, 0);

  useEffect(() => {
    const dialog = orderDialogRef.current;
    if (!dialog) return;
    if (orderDialogOpen && !dialog.open) dialog.showModal();
    else if (!orderDialogOpen && dialog.open) dialog.close();
  }, [orderDialogOpen]);

  return (
    <div className="dashboard-content">
      <section className="page-heading" aria-labelledby="sales-title">
        <div>
          <p className="eyebrow">Activité commerciale</p>
          <h1 className="page-title" id="sales-title">Ventes et commandes</h1>
          <p className="page-description">
            Enregistrez les commandes clients et suivez leur avancement.
          </p>
        </div>
        <div className="sales-heading-actions">
          <div className="date-chip">{ordersData?.total ?? 0} commande(s)</div>
          {canManageSales ? (
            <button
              className="button-primary"
              onClick={() => {
                setOrderLines([{ product_id: "", quantity: 1 }]);
                setFormError(null);
                setOrderDialogOpen(true);
              }}
              type="button"
            >
              <Plus size={16} /> Nouvelle commande
            </button>
          ) : null}
        </div>
      </section>

      {formMessage ? <p className="admin-success sales-feedback" role="status">{formMessage}</p> : null}
      {canManageSales ? (
        <dialog
          aria-labelledby="create-order-title"
          className="parcel-edit-dialog sales-order-dialog"
          onClose={() => setOrderDialogOpen(false)}
          onClick={(event) => {
            if (event.target === event.currentTarget) orderDialogRef.current?.close();
          }}
          ref={orderDialogRef}
        >
          <div className="parcel-edit-dialog-content">
            <div className="parcel-edit-dialog-heading">
              <div>
                <h2 id="create-order-title">Nouvelle commande</h2>
                <p>Choisissez les produits du catalogue. Le montant est calculé automatiquement.</p>
              </div>
              <button
                aria-label="Fermer"
                className="parcel-edit-dialog-close"
                onClick={() => orderDialogRef.current?.close()}
                type="button"
              >
                ×
              </button>
            </div>
            <form className="sales-order-form sales-order-dialog-form" onSubmit={handleSubmit}>
              <CustomerSelect
                organizationId={membership?.organization_id ?? ""}
                selectedCustomer={selectedCustomer}
                onChange={setSelectedCustomer}
              />
              <Link className="text-action" href="/clients">Créer une fiche client</Link>
              <div className="sales-order-lines">
                <div className="sales-order-lines-heading">
                  <strong>Produits commandés</strong>
                  <button
                    className="text-action"
                    onClick={() => setOrderLines((lines) => [...lines, { product_id: "", quantity: 1 }])}
                    type="button"
                  >
                    <Plus size={14} /> Ajouter une ligne
                  </button>
                </div>
                {products.isError ? (
                  <p className="auth-error" role="alert">{getApiErrorMessage(products.error)}</p>
                ) : null}
                {products.isPending ? <p className="stocks-loading" role="status">Chargement du catalogue…</p> : null}
                {!products.isPending && !availableProducts.length ? (
                  <p className="stocks-form-help">Aucun produit actif avec un stock disponible dans le catalogue.</p>
                ) : null}
                {orderLines.map((line, index) => {
                  const selectedProduct = availableProducts.find((product) => product.id === line.product_id);
                  return (
                    <div className="sales-order-line" key={index}>
                      <label className="auth-field">
                        <span>Produit</span>
                        <select
                          onChange={(event) => {
                            const product_id = event.currentTarget.value;
                            setOrderLines((lines) => lines.map((item, lineIndex) =>
                              lineIndex === index ? { ...item, product_id } : item,
                            ));
                          }}
                          required
                          value={line.product_id}
                        >
                          <option value="">Choisir dans le catalogue</option>
                          {availableProducts.map((product) => (
                            <option key={product.id} value={product.id}>
                              {product.name} · {formatFcfa(product.price_fcfa)} · stock {product.stock_quantity} {product.unit}
                            </option>
                          ))}
                        </select>
                      </label>
                      <label className="auth-field">
                        <span>Quantité</span>
                        <input
                          max={selectedProduct?.stock_quantity}
                          min="1"
                          onChange={(event) => {
                            const quantity = Number(event.currentTarget.value);
                            setOrderLines((lines) => lines.map((item, lineIndex) =>
                              lineIndex === index ? { ...item, quantity } : item,
                            ));
                          }}
                          required
                          type="number"
                          value={line.quantity}
                        />
                      </label>
                      <button
                        aria-label="Supprimer cette ligne"
                        className="sales-order-line-remove"
                        disabled={orderLines.length === 1}
                        onClick={() => setOrderLines((lines) => lines.filter((_, lineIndex) => lineIndex !== index))}
                        type="button"
                      >
                        <Trash2 size={16} />
                      </button>
                    </div>
                  );
                })}
                <div className="sales-order-total"><span>Total calculé</span><strong>{formatFcfa(orderTotal)}</strong></div>
              </div>
              <label className="auth-field">
                <span>Date de commande</span>
                <input name="order_date" defaultValue={today} required type="date" />
              </label>
              {formError ? <p className="auth-error" role="alert">{formError}</p> : null}
              <div className="parcel-edit-dialog-actions">
                <button className="button-secondary" onClick={() => orderDialogRef.current?.close()} type="button">
                  Annuler
                </button>
                <button className="button-primary" disabled={isSubmitting || !selectedCustomer} type="submit">
                  {isSubmitting ? "Enregistrement…" : "Enregistrer la commande"}
                </button>
              </div>
            </form>
          </div>
        </dialog>
      ) : null}

      {orders.isError ? (
        <div className="dashboard-error" role="alert">
          <p>{getApiErrorMessage(orders.error)}</p>
          <button className="button-secondary" type="button" onClick={() => void orders.refetch()}>
            Réessayer
          </button>
        </div>
      ) : null}
      {updateStatus.isError ? (
        <p className="auth-error sales-error" role="alert">
          {getApiErrorMessage(updateStatus.error)}
        </p>
      ) : null}

      <section className="panel sales-list-panel" aria-labelledby="orders-list-title">
        <div className="panel-header">
          <div>
            <h2 className="panel-title" id="orders-list-title">Toutes les commandes</h2>
            <p className="panel-subtitle">
              Données enregistrées dans l&apos;espace de votre entreprise.
            </p>
          </div>
        </div>
        <div className="sales-table-controls">
          <label className="sales-search">
            <Search size={15} aria-hidden="true" />
            <span className="visually-hidden">Rechercher une commande</span>
            <input
              type="search"
              value={search}
              placeholder="Client ou référence"
              onChange={(event) => {
                setSearch(event.target.value);
                setPage(1);
              }}
            />
          </label>
          <label className="sales-filter-label">
            <span className="visually-hidden">Filtrer par statut</span>
            <select
              className="select-compact"
              value={statusFilter}
              onChange={(event) => {
                const nextStatus = event.target.value;
                if (nextStatus === "all" || isOrderStatus(nextStatus)) {
                  setStatusFilter(nextStatus);
                  setPage(1);
                }
              }}
            >
              <option value="all">Tous les statuts</option>
              {statuses
                .filter((status) => !isOperator || status !== "cancelled")
                .map((status) => (
                <option key={status} value={status}>{orderStatusLabels[status]}</option>
                ))}
            </select>
          </label>
        </div>
        {orders.isPending ? (
          <div className="dashboard-loading" role="status">Chargement des commandes…</div>
        ) : ordersData?.items.length ? (
          <>
            <div className="table-wrap">
              <table className="data-table sales-table">
                <thead>
                  <tr>
                    <th scope="col">RÉFÉRENCE</th>
                    <th scope="col">CLIENT</th>
                    <th scope="col">ARTICLES</th>
                    <th scope="col">DATE</th>
                    <th scope="col">MONTANT</th>
                    <th scope="col">STATUT</th>
                  </tr>
                </thead>
                <tbody>
                  {ordersData.items.map((order) => (
                    <tr key={order.id}>
                      <td className="table-primary">{order.reference}</td>
                      <td>
                        <span className="sales-customer-details">
                          <strong>{order.customer_name}</strong>
                          {order.customer_phone ? <small>{order.customer_phone}</small> : null}
                          {order.customer_email ? <small>{order.customer_email}</small> : null}
                          {order.delivery_address ? <small>{order.delivery_address}</small> : null}
                        </span>
                      </td>
                      <td>
                        {order.items.length ? (
                          <details className="sales-order-items">
                            <summary>
                              {order.items.length} article(s) <ChevronDown size={13} />
                            </summary>
                            <div>
                              {order.items.map((item, index) => (
                                <div className="sales-order-item" key={`${order.id}-${item.product_id ?? index}`}>
                                  <OrderProductImage
                                    name={item.product_name}
                                    photoPath={item.product_id ? productById.get(item.product_id)?.photo_url ?? null : null}
                                    organizationId={membership?.organization_id}
                                  />
                                  <span className="sales-order-item-copy">
                                    <strong>{item.quantity} × {item.product_name}</strong>
                                    <small>{item.unit}</small>
                                  </span>
                                  <strong className="sales-order-item-price">
                                    {formatFcfa(item.quantity * item.unit_price_fcfa)}
                                  </strong>
                                </div>
                              ))}
                            </div>
                          </details>
                        ) : <span className="sales-manual-order">Saisie manuelle</span>}
                      </td>
                      <td>{formatDate(order.order_date)}</td>
                      <td className="table-primary">
                        {formatFcfa(order.amount_fcfa + (order.delivery_fee_fcfa ?? 0))}
                        {order.delivery_quote_required ? <small> · livraison à confirmer</small> : null}
                      </td>
                      <td>
                        {canManageSales && order.status !== "cancelled" ? (
                          <label className="status-select-label">
                            <span className="visually-hidden">Statut de {order.reference}</span>
                            <select
                              className={`status-select ${order.status}`}
                              value={order.status}
                              disabled={updateStatus.isPending}
                              onChange={(event) => {
                                if (isOrderStatus(event.target.value)) {
                                  updateStatus.mutate({
                                    id: order.id,
                                    status: event.target.value,
                                  });
                                }
                              }}
                            >
                              {statuses
                                .filter((status) => !isOperator || status !== "cancelled")
                                .map((status) => (
                                <option key={status} value={status}>
                                  {orderStatusLabels[status]}
                                </option>
                                ))}
                            </select>
                          </label>
                        ) : (
                          <span className={`status-pill ${order.status}`}>
                            {orderStatusLabels[order.status]}
                          </span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="sales-pagination">
              <span>
                {ordersData.total
                  ? `${(page - 1) * ordersData.page_size + 1}–${Math.min(page * ordersData.page_size, ordersData.total)} sur ${ordersData.total}`
                  : "0 commande"}
              </span>
              <div>
                <button
                  className="pagination-button"
                  type="button"
                  aria-label="Page précédente"
                  disabled={page <= 1}
                  onClick={() => setPage((current) => Math.max(current - 1, 1))}
                >
                  <ChevronLeft size={15} />
                </button>
                <span>Page {page} / {Math.max(totalPages, 1)}</span>
                <button
                  className="pagination-button"
                  type="button"
                  aria-label="Page suivante"
                  disabled={page >= totalPages}
                  onClick={() => setPage((current) => Math.min(current + 1, totalPages))}
                >
                  <ChevronRight size={15} />
                </button>
              </div>
            </div>
          </>
        ) : !orders.isError ? (
          <div className="sales-empty-state">
            <span className="chart-empty-icon"><ShoppingBasket size={18} /></span>
            <h3>{deferredSearch || statusFilter !== "all" ? "Aucune commande trouvée" : "Aucune commande pour le moment"}</h3>
            <p>
              {deferredSearch || statusFilter !== "all"
                ? "Modifiez vos filtres ou votre recherche."
                : "Les commandes de la boutique et les ventes saisies ici apparaîtront dans ce suivi."}
            </p>
          </div>
        ) : null}
      </section>
    </div>
  );
}
