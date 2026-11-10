"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  ArrowRight,
  Bell,
  CircleCheck,
  Check,
  ChevronDown,
  ClipboardCheck,
  Clock3,
  LogOut,
  LoaderCircle,
  MapPin,
  PackageCheck,
  PackageOpen,
  Pencil,
  RotateCcw,
  Search,
  ShoppingBag,
  Truck,
  X,
} from "lucide-react";
import { OrderProductImage } from "@/features/shared/order-product-image";
import { ChangePasswordForm } from "@/features/auth/change-password-form";
import {
  apiRequest,
  getApiErrorMessage,
  type UserProfile,
} from "@/lib/api/client";
import {
  formatDate,
  formatDateTime,
  formatFcfa,
  orderStatusLabels,
  type OrderStatus,
  type SalesOrder,
  type SalesOrderPage,
} from "@/features/sales/sales-types";
import { useShopCart } from "./use-shop-cart";
import type {
  StoreCustomerProfile,
  StoreOrderNotification,
  StoreOrderSummary,
  StoreProductPage,
} from "./store-types";

const pageSize = 5;
const statusFilters: Array<{ value: OrderStatus | "all"; label: string }> = [
  { value: "all", label: "Toutes" },
  { value: "pending", label: "À confirmer" },
  { value: "confirmed", label: "Validées" },
  { value: "preparing", label: "En préparation" },
  { value: "delivered", label: "Livrées" },
  { value: "cancelled", label: "Annulées" },
];

const statusClassNames = {
  pending: "warning",
  confirmed: "",
  preparing: "warning",
  delivered: "delivered",
  cancelled: "cancelled",
} as const;

const orderProgressSteps = [
  { status: "pending", label: "Reçue", description: "Demande enregistrée", icon: PackageCheck },
  { status: "confirmed", label: "Validée", description: "Commande vérifiée", icon: ClipboardCheck },
  { status: "preparing", label: "Préparation", description: "Votre commande est préparée", icon: PackageOpen },
  { status: "delivered", label: "Livrée", description: "Commande remise", icon: Truck },
] as const;

const orderProgressMessages = {
  pending: "Votre demande est bien reçue. Notre équipe va vérifier la disponibilité des produits.",
  confirmed: "Votre commande est validée par notre équipe.",
  preparing: "Notre équipe prépare votre commande.",
  delivered: "Votre commande a été livrée. Merci pour votre confiance !",
} as const;

export function CustomerAccountPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const { cart, setCart } = useShopCart();
  const profileDialogRef = useRef<HTMLDialogElement>(null);
  const notificationsDialogRef = useRef<HTMLDialogElement>(null);
  const [page, setPage] = useState(1);
  const [profileDialogOpen, setProfileDialogOpen] = useState(false);
  const [notificationsDialogOpen, setNotificationsDialogOpen] = useState(false);
  const [statusFilter, setStatusFilter] = useState<OrderStatus | "all">("all");
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [orderActionMessage, setOrderActionMessage] = useState("");
  const [reorderAddedToCart, setReorderAddedToCart] = useState(false);
  const [editingProfile, setEditingProfile] = useState(false);
  const [profileUpdateMessage, setProfileUpdateMessage] = useState("");
  const profile = useQuery({
    queryKey: ["auth", "me"],
    queryFn: () => apiRequest<UserProfile>("/auth/me"),
    retry: false,
  });
  const customerProfile = useQuery({
    queryKey: ["store", "my-profile"],
    queryFn: () => apiRequest<StoreCustomerProfile>("/store/my-profile"),
    retry: false,
  });
  const orderSummary = useQuery({
    queryKey: ["store", "my-orders", "summary"],
    queryFn: () => apiRequest<StoreOrderSummary>("/store/my-orders/summary"),
    refetchInterval: 30_000,
    retry: false,
  });
  const notifications = useQuery({
    queryKey: ["store", "my-notifications"],
    queryFn: () => apiRequest<StoreOrderNotification[]>("/store/my-notifications"),
    refetchInterval: 30_000,
    retry: false,
  });
  const orders = useQuery({
    queryKey: ["store", "my-orders", page, statusFilter, search],
    queryFn: () => {
      const params = new URLSearchParams({
        page: String(page),
        page_size: String(pageSize),
      });
      if (statusFilter !== "all") params.set("status", statusFilter);
      if (search) params.set("search", search);
      return apiRequest<SalesOrderPage>(`/store/my-orders?${params}`);
    },
    refetchInterval: 30_000,
    retry: false,
  });
  const catalog = useQuery({
    queryKey: ["store", "products"],
    queryFn: () => apiRequest<StoreProductPage>("/store/products"),
    retry: false,
  });
  const productById = new Map((catalog.data?.items ?? []).map((product) => [product.id, product]));
  const logout = useMutation({
    mutationFn: () => apiRequest<{ message: string }>("/auth/logout", { method: "POST" }),
    onSuccess: () => {
      queryClient.clear();
      router.replace("/");
    },
  });
  const updateProfile = useMutation({
    mutationFn: (data: Pick<StoreCustomerProfile, "full_name" | "phone" | "address">) =>
      apiRequest<StoreCustomerProfile>("/store/my-profile", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data),
      }),
    onSuccess: (updatedProfile) => {
      queryClient.setQueryData(["store", "my-profile"], updatedProfile);
      queryClient.setQueryData<UserProfile>(["auth", "me"], (current) =>
        current ? { ...current, full_name: updatedProfile.full_name } : current,
      );
      setEditingProfile(false);
      setProfileUpdateMessage("Vos coordonnées ont été mises à jour.");
    },
  });
  const cancelOrder = useMutation({
    mutationFn: (orderId: string) =>
      apiRequest<SalesOrder>(`/store/my-orders/${orderId}/cancel`, { method: "POST" }),
    onSuccess: async (cancelledOrder) => {
      setOrderActionMessage(`La commande ${cancelledOrder.reference} a été annulée.`);
      setPage(1);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["store", "my-orders"] }),
        queryClient.invalidateQueries({ queryKey: ["store", "my-orders", "summary"] }),
        queryClient.invalidateQueries({ queryKey: ["store", "my-notifications"] }),
        queryClient.invalidateQueries({ queryKey: ["store", "products"] }),
      ]);
    },
  });
  const totalPages = Math.ceil((orders.data?.total ?? 0) / pageSize);
  const customerName = profile.data?.full_name ?? "Mon compte";
  const customerInitials = customerName
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part.charAt(0))
    .join("")
    .toLocaleUpperCase("fr");

  useEffect(() => {
    const dialog = profileDialogRef.current;
    if (!dialog) return;
    if (profileDialogOpen && !dialog.open) dialog.showModal();
    else if (!profileDialogOpen && dialog.open) dialog.close();
  }, [profileDialogOpen]);

  useEffect(() => {
    const dialog = notificationsDialogRef.current;
    if (!dialog) return;
    if (notificationsDialogOpen && !dialog.open) dialog.showModal();
    else if (!notificationsDialogOpen && dialog.open) dialog.close();
  }, [notificationsDialogOpen]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setSearch(searchInput.trim());
      setPage(1);
    }, 250);
    return () => window.clearTimeout(timer);
  }, [searchInput]);

  function reorder(order: SalesOrder) {
    const currentProducts = new Map((catalog.data?.items ?? []).map((product) => [product.id, product]));
    let restoredCount = 0;
    let skippedCount = 0;
    const nextCart = { ...cart };
    for (const item of order.items) {
      const product = item.product_id ? currentProducts.get(item.product_id) : undefined;
      if (!product || product.stock_quantity < 1) {
        skippedCount += 1;
        continue;
      }
      const quantity = Math.min(
        999,
        product.stock_quantity,
        (nextCart[product.id] ?? 0) + item.quantity,
      );
      if (quantity <= (nextCart[product.id] ?? 0)) {
        skippedCount += 1;
        continue;
      }
      nextCart[product.id] = quantity;
      restoredCount += 1;
    }
    setReorderAddedToCart(restoredCount > 0 && skippedCount > 0);
    if (restoredCount) {
      setCart(nextCart);
      if (skippedCount) {
        setOrderActionMessage(
          `${restoredCount} article(s) ajouté(s) au panier. ${skippedCount} indisponible(s) ou limité(s) par le stock.`,
        );
      } else {
        router.push("/panier");
      }
    } else {
      setOrderActionMessage(
        "Aucun article n’a pu être ajouté : les produits sont épuisés ou votre panier contient déjà les quantités disponibles.",
      );
    }
  }

  function requestCancellation(order: SalesOrder) {
    if (!window.confirm(`Voulez-vous vraiment annuler la commande ${order.reference} ?`)) return;
    setOrderActionMessage("");
    setReorderAddedToCart(false);
    cancelOrder.mutate(order.id);
  }

  return (
    <main className="customer-account-page">
      <header className="customer-account-header">
        <Link className="store-back-link" href="/produits">
          <ArrowLeft size={15} /> Retour à la boutique
        </Link>
        <button
          aria-controls="customer-profile-dialog"
          aria-expanded={profileDialogOpen}
          aria-haspopup="dialog"
          className="customer-account-user"
          onClick={() => setProfileDialogOpen(true)}
          type="button"
        >
          <span className="customer-account-avatar" aria-hidden="true">{customerInitials}</span>
          <span className="customer-account-user-copy">
            <strong>{customerName}</strong>
          </span>
        </button>
        <div className="customer-account-actions">
          <button
            aria-controls="customer-notifications-dialog"
            aria-expanded={notificationsDialogOpen}
            aria-haspopup="dialog"
            aria-label={`Notifications${notifications.data?.length ? `, ${notifications.data.length} mises à jour` : ""}`}
            className="customer-notifications-trigger"
            onClick={() => setNotificationsDialogOpen(true)}
            type="button"
          >
            <Bell size={18} />
            {notifications.data?.length ? (
              <span aria-hidden="true">{notifications.data.length > 9 ? "9+" : notifications.data.length}</span>
            ) : null}
          </button>
          <button
            className="button-secondary"
            disabled={logout.isPending}
            onClick={() => logout.mutate()}
            type="button"
          >
            <LogOut size={15} /> {logout.isPending ? "Déconnexion…" : "Se déconnecter"}
          </button>
        </div>
      </header>

      <dialog
        aria-labelledby="customer-profile-dialog-title"
        className="customer-profile-dialog"
        id="customer-profile-dialog"
        onClose={() => {
          setProfileDialogOpen(false);
          setEditingProfile(false);
        }}
        onClick={(event) => {
          if (event.target === event.currentTarget) setProfileDialogOpen(false);
        }}
        ref={profileDialogRef}
      >
        <section className="customer-profile-dialog-card">
          <header className="customer-profile-dialog-header">
            <div>
              <p className="public-eyebrow">Mon compte</p>
              <h2 id="customer-profile-dialog-title">Profil et sécurité</h2>
            </div>
            <button
              aria-label="Fermer le profil"
              autoFocus
              className="customer-profile-dialog-close"
              onClick={() => setProfileDialogOpen(false)}
              type="button"
            >
              <X size={18} />
            </button>
          </header>
          <div className="customer-profile-dialog-identity">
            <span className="customer-account-avatar" aria-hidden="true">{customerInitials}</span>
            <strong>{customerName}</strong>
          </div>
          {customerProfile.isPending ? (
            <p className="customer-profile-loading" role="status">Chargement du profil…</p>
          ) : customerProfile.isError ? (
            <div className="customer-profile-error" role="alert">
              <p>{getApiErrorMessage(customerProfile.error)}</p>
              <button className="button-secondary" onClick={() => void customerProfile.refetch()} type="button">
                Réessayer
              </button>
            </div>
          ) : customerProfile.data ? (
            editingProfile ? (
              <form
                className="customer-profile-edit-form"
                onSubmit={(event) => {
                  event.preventDefault();
                  setProfileUpdateMessage("");
                  const formData = new FormData(event.currentTarget);
                  updateProfile.mutate({
                    full_name: String(formData.get("full_name") ?? "").trim(),
                    phone: String(formData.get("phone") ?? "").trim(),
                    address: String(formData.get("address") ?? "").trim() || null,
                  });
                }}
              >
                <label>
                  <span>Nom complet</span>
                  <input defaultValue={customerProfile.data.full_name} maxLength={160} minLength={2} name="full_name" required />
                </label>
                <label>
                  <span>Téléphone</span>
                  <input autoComplete="tel" defaultValue={customerProfile.data.phone} maxLength={32} minLength={6} name="phone" required />
                </label>
                <label>
                  <span>Adresse habituelle</span>
                  <textarea defaultValue={customerProfile.data.address ?? ""} maxLength={500} name="address" rows={3} />
                </label>
                {updateProfile.isError ? (
                  <p className="password-change-error" role="alert">{getApiErrorMessage(updateProfile.error)}</p>
                ) : null}
                <div className="customer-profile-edit-actions">
                  <button className="button-secondary" onClick={() => setEditingProfile(false)} type="button">
                    Annuler
                  </button>
                  <button className="button-primary" disabled={updateProfile.isPending} type="submit">
                    {updateProfile.isPending ? <LoaderCircle className="auth-spinner" size={16} /> : null}
                    {updateProfile.isPending ? "Enregistrement…" : "Enregistrer"}
                  </button>
                </div>
              </form>
            ) : (
              <div className="customer-profile-details">
                {profileUpdateMessage ? <p className="customer-profile-success" role="status">{profileUpdateMessage}</p> : null}
                <div><span>E-mail</span><strong>{customerProfile.data.email}</strong></div>
                <div><span>Téléphone</span><strong>{customerProfile.data.phone}</strong></div>
                <div><span>Adresse</span><strong>{customerProfile.data.address || "Non renseignée"}</strong></div>
                <button
                  className="customer-profile-edit-trigger"
                  onClick={() => {
                    setProfileUpdateMessage("");
                    setEditingProfile(true);
                  }}
                  type="button"
                >
                  <Pencil size={15} /> Modifier mes coordonnées
                </button>
              </div>
            )
          ) : null}
          <div className="customer-profile-dialog-password">
            <h3>Sécurité du compte</h3>
            <ChangePasswordForm />
          </div>
        </section>
      </dialog>

      <dialog
        aria-labelledby="customer-notifications-title"
        className="customer-profile-dialog customer-notifications-dialog"
        id="customer-notifications-dialog"
        onClose={() => setNotificationsDialogOpen(false)}
        onClick={(event) => {
          if (event.target === event.currentTarget) setNotificationsDialogOpen(false);
        }}
        ref={notificationsDialogRef}
      >
        <section className="customer-profile-dialog-card">
          <header className="customer-profile-dialog-header">
            <div>
              <p className="public-eyebrow">Suivi des commandes</p>
              <h2 id="customer-notifications-title">Notifications</h2>
            </div>
            <button
              aria-label="Fermer les notifications"
              autoFocus
              className="customer-profile-dialog-close"
              onClick={() => setNotificationsDialogOpen(false)}
              type="button"
            >
              <X size={18} />
            </button>
          </header>
          {notifications.isError ? (
            <div className="customer-notifications-error" role="alert">
              <p>Les mises à jour récentes n’ont pas pu être chargées. {getApiErrorMessage(notifications.error)}</p>
              <button className="button-secondary" onClick={() => void notifications.refetch()} type="button">
                Réessayer
              </button>
            </div>
          ) : notifications.isPending ? (
            <p className="customer-profile-loading" role="status">Chargement des notifications…</p>
          ) : notifications.data?.length ? (
            <section className="customer-recent-updates" aria-label="Mises à jour récentes">
              <div className="customer-recent-updates-heading">
                <Bell size={17} />
                <h3>Mises à jour récentes</h3>
                <span aria-label="Actualisé automatiquement">En direct</span>
              </div>
              <ul>
                {notifications.data.map((notification) => (
                  <li key={`${notification.order_id}-${notification.created_at}`}>
                    <CircleCheck size={16} />
                    <p>
                      <strong>{notification.order_reference}</strong> · {orderStatusLabels[notification.status]}
                    </p>
                    <time dateTime={notification.created_at}>{formatDateTime(notification.created_at)}</time>
                  </li>
                ))}
              </ul>
            </section>
          ) : (
            <div className="customer-notifications-empty">
              <Bell size={22} />
              <p>Vous n’avez pas encore de mise à jour sur vos commandes.</p>
            </div>
          )}
        </section>
      </dialog>

      {logout.isError ? <p className="auth-error" role="alert">{getApiErrorMessage(logout.error)}</p> : null}
      {cancelOrder.isError ? <p className="auth-error" role="alert">{getApiErrorMessage(cancelOrder.error)}</p> : null}
      {orderActionMessage ? (
        <p className="customer-order-action-message" role="status">
          {orderActionMessage}
          {reorderAddedToCart ? <Link href="/panier">Voir le panier <ArrowRight size={14} /></Link> : null}
        </p>
      ) : null}
      {orderSummary.isError ? (
        <div className="dashboard-error" role="alert">
          <p>Impossible de charger le résumé de vos commandes. {getApiErrorMessage(orderSummary.error)}</p>
          <button className="button-secondary" onClick={() => void orderSummary.refetch()} type="button">Réessayer</button>
        </div>
      ) : orderSummary.isPending ? (
        <section className="customer-order-summary" aria-label="Résumé des commandes" aria-busy="true">
          {[1, 2, 3].map((item) => <div className="customer-summary-skeleton" key={item} />)}
        </section>
      ) : orderSummary.data ? (
        <section className="customer-order-summary" aria-label="Résumé des commandes">
          <article>
            <span>Commandes en cours</span>
            <strong>{orderSummary.data.in_progress_count}</strong>
          </article>
          <article>
            <span>Commandes livrées</span>
            <strong>{orderSummary.data.delivered_count}</strong>
          </article>
          <article>
            <span>Total des achats livrés</span>
            <strong>{formatFcfa(orderSummary.data.total_spent_fcfa)}</strong>
          </article>
        </section>
      ) : null}

      <section className="customer-orders-section" aria-label="Vos commandes">
        <div className="customer-orders-toolbar">
          <div>
            <h1>Mes commandes</h1>
            <p>
              {orders.data ? `${orders.data.total} commande(s)` : "Suivez vos achats et leur avancement"}
              {statusFilter !== "all"
                ? ` · ${statusFilters.find((item) => item.value === statusFilter)?.label.toLowerCase()}`
                : ""}
            </p>
          </div>
          <label className="customer-orders-search">
            <Search size={16} />
            <span className="visually-hidden">Rechercher une référence de commande</span>
            <input
              onChange={(event) => setSearchInput(event.target.value)}
              placeholder="Référence de commande"
              type="search"
              value={searchInput}
            />
          </label>
          <label className="customer-orders-filter">
            <span>Filtrer par statut</span>
            <select
              onChange={(event) => {
                const selectedFilter = statusFilters.find(
                  (filter) => filter.value === event.target.value,
                );
                if (!selectedFilter) return;
                setStatusFilter(selectedFilter.value);
                setPage(1);
              }}
              value={statusFilter}
            >
              {statusFilters.map((filter) => (
                <option key={filter.value} value={filter.value}>{filter.label}</option>
              ))}
            </select>
          </label>
        </div>

        {catalog.isError ? (
          <div className="dashboard-error" role="alert">
            <p>Impossible de vérifier les disponibilités pour recommander. {getApiErrorMessage(catalog.error)}</p>
            <button className="button-secondary" onClick={() => void catalog.refetch()} type="button">Réessayer</button>
          </div>
        ) : null}
        {orders.isError ? (
          <div className="dashboard-error" role="alert">
            <p>{getApiErrorMessage(orders.error)}</p>
            <button className="button-secondary" type="button" onClick={() => void orders.refetch()}>
              Réessayer
            </button>
          </div>
        ) : orders.isPending ? (
          <div className="customer-orders-loading" role="status" aria-label="Chargement des commandes">
            {[1, 2].map((item) => <div className="customer-order-skeleton" key={item} />)}
          </div>
        ) : orders.data && (orders.data.total > 0 || statusFilter !== "all" || search) ? (
          <>
            {orders.data.items.length ? (
              <section className="customer-order-list" aria-label="Commandes de cette page">
                {orders.data.items.map((order) => {
                  const currentStep = orderProgressSteps.findIndex((step) => step.status === order.status);
                  return (
                    <article className="customer-order-card" key={order.id}>
                      <div className="customer-order-heading">
                        <div>
                          <span className="public-eyebrow">Commande {order.reference}</span>
                          <time dateTime={order.order_date}>{formatDate(order.order_date)}</time>
                        </div>
                        <span className={`status-pill ${statusClassNames[order.status]}`}>
                          {orderStatusLabels[order.status]}
                        </span>
                      </div>
                      {order.status === "cancelled" ? (
                        <div className="customer-order-cancelled" role="status">
                          <span><X size={16} /></span>
                          <div>
                            <strong>Commande annulée</strong>
                            <p>Cette commande ne sera pas préparée. Contactez notre équipe si vous avez besoin d’aide.</p>
                          </div>
                        </div>
                      ) : (
                        <details className="customer-order-progress-toggle">
                          <summary>
                            <span><PackageCheck size={16} /> Voir la progression</span>
                            <ChevronDown size={16} />
                          </summary>
                          <section
                            className="customer-order-progress"
                            aria-label={`Progression de la commande ${order.reference}`}
                          >
                            <ol>
                              {orderProgressSteps.map(({ label, description, icon: Icon }, index) => {
                                const isComplete = index < currentStep;
                                const isCurrent = index === currentStep;
                                return (
                                  <li
                                    className={`customer-progress-step${isComplete ? " is-complete" : ""}${isCurrent ? " is-current" : ""}`}
                                    key={label}
                                    aria-current={isCurrent ? "step" : undefined}
                                  >
                                    <span className="customer-progress-marker">
                                      {isComplete ? <Check size={15} strokeWidth={2.5} /> : <Icon size={16} />}
                                    </span>
                                    <span className="customer-progress-copy">
                                      <strong>{label}</strong>
                                      <small>{description}</small>
                                    </span>
                                  </li>
                                );
                              })}
                            </ol>
                            <p className="customer-order-status-note">
                              <PackageCheck size={17} />
                              {orderProgressMessages[order.status]}
                            </p>
                          </section>
                        </details>
                      )}
                      <ul className="customer-order-items customer-order-product-list">
                        {order.items.map((item) => (
                          <li key={`${order.id}-${item.product_id ?? item.product_name}`}>
                            <OrderProductImage
                              name={item.product_name}
                              photoPath={item.product_id ? productById.get(item.product_id)?.photo_url ?? null : null}
                            />
                            <span className="customer-order-product-copy">
                              <strong>{item.quantity} × {item.product_name}</strong>
                              <small>{item.unit}</small>
                            </span>
                            <strong className="customer-order-product-price">
                              {formatFcfa(item.quantity * item.unit_price_fcfa)}
                            </strong>
                          </li>
                        ))}
                      </ul>
                      <details className="customer-order-details">
                        <summary>
                          <span><Clock3 size={16} /> Adresse et historique</span>
                          <ChevronDown size={16} />
                        </summary>
                        <div className="customer-order-details-content">
                          <div className="customer-order-delivery">
                            <MapPin size={16} />
                            <span>
                              <small>Adresse de livraison</small>
                              <strong>{order.delivery_address || "À confirmer avec l’équipe"}</strong>
                            </span>
                          </div>
                          <ol className="customer-order-history">
                            {order.status_history.map((event, index) => (
                              <li key={`${event.status}-${event.created_at}-${index}`}>
                                <span className="customer-order-history-marker" />
                                <strong>{orderStatusLabels[event.status]}</strong>
                                <time dateTime={event.created_at}>{formatDateTime(event.created_at)}</time>
                              </li>
                            ))}
                          </ol>
                        </div>
                      </details>
                      <div className="customer-order-total">
                        <span>Produits</span>
                        <strong>{formatFcfa(order.amount_fcfa)}</strong>
                      </div>
                      <div className="customer-order-total">
                        <span>
                          Livraison
                          {order.delivery_distance_km === null ? "" : ` · ${order.delivery_distance_km.toLocaleString("fr-FR")} km`}
                        </span>
                        <strong>
                          {order.delivery_quote_required
                            ? "À confirmer"
                            : formatFcfa(order.delivery_fee_fcfa ?? 0)}
                        </strong>
                      </div>
                      <div className="customer-order-total">
                        <span>{order.delivery_quote_required ? "Total provisoire" : "Total avec livraison"}</span>
                        <strong className={order.delivery_quote_required ? "is-provisional" : undefined}>
                          {order.delivery_quote_required
                            ? `${formatFcfa(order.amount_fcfa)} + livraison à confirmer`
                            : formatFcfa(order.amount_fcfa + (order.delivery_fee_fcfa ?? 0))}
                        </strong>
                      </div>
                      {order.delivery_quote_required ? (
                        <p className="checkout-delivery-warning">Le montant des produits est connu. Notre équipe vous communiquera le total final après confirmation des frais de livraison.</p>
                      ) : null}
                      <div className="customer-order-actions">
                        <button
                          className="button-secondary"
                          disabled={catalog.isPending || catalog.isError}
                          onClick={() => reorder(order)}
                          type="button"
                        >
                          <RotateCcw size={15} /> Commander à nouveau
                        </button>
                        {order.status === "pending" ? (
                          <button
                            className="customer-order-cancel-button"
                            disabled={cancelOrder.isPending}
                            onClick={() => requestCancellation(order)}
                            type="button"
                          >
                            {cancelOrder.isPending && cancelOrder.variables === order.id
                              ? <LoaderCircle className="auth-spinner" size={15} />
                              : <X size={15} />}
                            Annuler la commande
                          </button>
                        ) : null}
                      </div>
                    </article>
                  );
                })}
              </section>
            ) : (
              <div className="customer-orders-filter-empty">
                <ShoppingBag size={22} />
                <p>{search ? "Aucune commande ne correspond à cette référence." : "Aucune commande avec ce statut."}</p>
              </div>
            )}
            {totalPages > 1 ? (
              <nav className="customer-orders-pagination" aria-label="Pages des commandes">
                <button
                  className="button-secondary"
                  disabled={page <= 1}
                  onClick={() => setPage((current) => current - 1)}
                  type="button"
                >
                  <ArrowLeft size={15} /> Précédent
                </button>
                <span>Page {page} sur {totalPages}</span>
                <button
                  className="button-secondary"
                  disabled={page >= totalPages}
                  onClick={() => setPage((current) => current + 1)}
                  type="button"
                >
                  Suivant <ArrowRight size={15} />
                </button>
              </nav>
            ) : null}
          </>
        ) : (
          <div className="customer-account-empty">
            <ShoppingBag size={25} />
            <h2>Pas encore de commande</h2>
            <p>Vos prochaines commandes et leur avancement apparaîtront ici.</p>
            <Link className="button-primary" href="/produits">
              Découvrir la boutique <ArrowRight size={15} />
            </Link>
          </div>
        )}
      </section>
    </main>
  );
}
