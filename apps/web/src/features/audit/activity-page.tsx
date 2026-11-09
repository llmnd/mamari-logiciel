"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ClipboardCheck, History, LoaderCircle, RotateCw } from "lucide-react";
import {
  apiRequest,
  getApiErrorMessage,
  type UserProfile,
} from "@/lib/api/client";
import { formatDate } from "@/features/sales/sales-types";

type AuditModule = "sales" | "stocks" | "agriculture" | "livestock";
type ApprovalAction = "stock_adjustment" | "order_cancellation";

interface AuditEvent {
  id: string;
  module: AuditModule;
  action: string;
  entity_type: string;
  entity_id: string | null;
  summary: string;
  actor_name: string | null;
  created_at: string;
}

interface AuditEventPage {
  items: AuditEvent[];
  total: number;
  page: number;
  page_size: number;
}

interface ApprovalRequest {
  id: string;
  action: ApprovalAction;
  resource_id: string;
  payload: Record<string, unknown>;
  reason: string;
  status: "pending" | "approved" | "rejected";
  requester_name: string | null;
  reviewer_name: string | null;
  review_note: string | null;
  created_at: string;
}

interface StockOption {
  id: string;
  name: string;
  unit: string;
}

interface OrderOption {
  id: string;
  reference: string;
  customer_name: string;
  status: string;
}

interface PageResult<T> {
  items: T[];
}

const moduleLabels: Record<AuditModule, string> = {
  sales: "Ventes",
  stocks: "Stocks",
  agriculture: "Agriculture",
  livestock: "Élevage",
};

const statusLabels = {
  pending: "En attente",
  approved: "Approuvée",
  rejected: "Refusée",
} as const;

export function ActivityPage() {
  const queryClient = useQueryClient();
  const [module, setModule] = useState<AuditModule | "all">("all");
  const [approvalStatus, setApprovalStatus] = useState<ApprovalRequest["status"]>("pending");
  const [action, setAction] = useState<ApprovalAction>("stock_adjustment");
  const [resourceId, setResourceId] = useState("");
  const [quantity, setQuantity] = useState("");
  const [direction, setDirection] = useState<"in" | "out">("out");
  const [reason, setReason] = useState("");
  const profile = useQuery({
    queryKey: ["auth", "me"],
    queryFn: () => apiRequest<UserProfile>("/auth/me"),
    retry: false,
  });
  const membership = profile.data?.memberships[0];
  const headers = membership
    ? { "X-Organization-ID": membership.organization_id }
    : undefined;
  const isOperator = membership?.role === "operator";
  const canApprove = Boolean(
    membership && ["owner", "admin", "manager"].includes(membership.role),
  );
  const events = useQuery({
    queryKey: ["audit", "events", membership?.organization_id, module],
    queryFn: () =>
      apiRequest<AuditEventPage>(
        `/audit/events?page=1&page_size=100${module === "all" ? "" : `&module=${module}`}`,
        { headers },
      ),
    enabled: Boolean(membership),
    refetchInterval: 30_000,
  });
  const approvals = useQuery({
    queryKey: ["audit", "requests", membership?.organization_id, approvalStatus],
    queryFn: () =>
      apiRequest<ApprovalRequest[]>(`/audit/requests?status=${approvalStatus}`, { headers }),
    enabled: Boolean(membership),
    refetchInterval: 30_000,
  });
  const stocks = useQuery({
    queryKey: ["audit", "stock-options", membership?.organization_id],
    queryFn: () => apiRequest<StockOption[]>("/stocks/items", { headers }),
    enabled: Boolean(isOperator && action === "stock_adjustment" && membership),
  });
  const orders = useQuery({
    queryKey: ["audit", "order-options", membership?.organization_id],
    queryFn: () =>
      apiRequest<PageResult<OrderOption>>(
        "/sales/orders?status=pending&page=1&page_size=100",
        { headers },
      ),
    enabled: Boolean(isOperator && action === "order_cancellation" && membership),
  });
  const createRequest = useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      apiRequest<ApprovalRequest>("/audit/requests", {
        method: "POST",
        headers: { ...headers, "Content-Type": "application/json" },
        body: JSON.stringify(body),
      }),
    onSuccess: async () => {
      setQuantity("");
      setReason("");
      setResourceId("");
      await queryClient.invalidateQueries({ queryKey: ["audit"] });
    },
  });
  const reviewRequest = useMutation({
    mutationFn: ({ id, decision }: { id: string; decision: "approved" | "rejected" }) =>
      apiRequest<ApprovalRequest>(`/audit/requests/${id}`, {
        method: "PATCH",
        headers: { ...headers, "Content-Type": "application/json" },
        body: JSON.stringify({ decision }),
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["audit"] });
      await queryClient.invalidateQueries({ queryKey: ["stocks"] });
      await queryClient.invalidateQueries({ queryKey: ["sales"] });
    },
  });
  const pendingRequests = approvals.data ?? [];

  function submitRequest(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const body: Record<string, unknown> = {
      action,
      resource_id: resourceId,
      reason: reason.trim(),
    };
    if (action === "stock_adjustment") {
      body.quantity = quantity;
      body.direction = direction;
      body.movement_date = new Date().toISOString().slice(0, 10);
    }
    createRequest.mutate(body);
  }

  return (
    <div className="dashboard-content activity-workspace">
      <section className="page-heading" aria-labelledby="activity-title">
        <div>
          <p className="eyebrow">Traçabilité et décisions</p>
          <h1 className="page-title" id="activity-title">Activité et approbations</h1>
          <p className="page-description">
            Retrouvez les opérations importantes et les demandes qui nécessitent un responsable.
          </p>
        </div>
        <button
          className="button-secondary"
          onClick={() => {
            void events.refetch();
            void approvals.refetch();
          }}
          type="button"
        >
          <RotateCw size={15} /> Actualiser
        </button>
      </section>

      {isOperator ? (
        <section className="panel activity-request-panel" aria-labelledby="request-title">
          <div className="panel-header">
            <div>
              <h2 className="panel-title" id="request-title">Soumettre une demande</h2>
              <p className="panel-subtitle">Un responsable doit approuver avant l’exécution.</p>
            </div>
          </div>
          <form className="activity-request-form" onSubmit={submitRequest}>
            <label>
              <span>Type de demande</span>
              <select
                value={action}
                onChange={(event) => {
                  setAction(event.target.value as ApprovalAction);
                  setResourceId("");
                }}
              >
                <option value="stock_adjustment">Ajustement manuel de stock</option>
                <option value="order_cancellation">Annulation d’une commande en attente</option>
              </select>
            </label>
            <label>
              <span>{action === "stock_adjustment" ? "Article de stock" : "Commande"}</span>
              <select
                required
                value={resourceId}
                onChange={(event) => setResourceId(event.target.value)}
              >
                <option value="">Choisir…</option>
                {action === "stock_adjustment"
                  ? (stocks.data ?? []).map((item) => (
                      <option key={item.id} value={item.id}>{item.name} ({item.unit})</option>
                    ))
                  : (orders.data?.items ?? []).map((order) => (
                      <option key={order.id} value={order.id}>
                        {order.reference} · {order.customer_name}
                      </option>
                    ))}
              </select>
            </label>
            {action === "stock_adjustment" ? (
              <>
                <label>
                  <span>Quantité</span>
                  <input
                    min="0.001"
                    required
                    step="0.001"
                    type="number"
                    value={quantity}
                    onChange={(event) => setQuantity(event.target.value)}
                  />
                </label>
                <label>
                  <span>Sens du mouvement</span>
                  <select
                    value={direction}
                    onChange={(event) => setDirection(event.target.value as "in" | "out")}
                  >
                    <option value="in">Augmenter le stock</option>
                    <option value="out">Diminuer le stock</option>
                  </select>
                </label>
              </>
            ) : null}
            <label className="activity-request-reason">
              <span>Motif</span>
              <input
                maxLength={1000}
                minLength={2}
                required
                value={reason}
                onChange={(event) => setReason(event.target.value)}
              />
            </label>
            {createRequest.isError ? (
              <p className="form-error" role="alert">{getApiErrorMessage(createRequest.error)}</p>
            ) : null}
            {createRequest.isSuccess ? (
              <p className="form-success" role="status">Demande envoyée pour approbation.</p>
            ) : null}
            <button className="button-primary" disabled={createRequest.isPending} type="submit">
              {createRequest.isPending ? <LoaderCircle className="auth-spinner" size={15} /> : null}
              Envoyer la demande
            </button>
          </form>
        </section>
      ) : null}

      <section className="panel activity-approvals-panel" aria-labelledby="approvals-title">
        <div className="panel-header">
          <div>
            <h2 className="panel-title" id="approvals-title">Demandes d’approbation</h2>
            <p className="panel-subtitle">
              {approvalStatus === "pending"
                ? `${pendingRequests.length} demande(s) en attente`
                : `${pendingRequests.length} demande(s) ${statusLabels[approvalStatus].toLowerCase()}(s)`}
            </p>
          </div>
          <label className="activity-filter">
            <span>État</span>
            <select
              value={approvalStatus}
              onChange={(event) =>
                setApprovalStatus(event.target.value as ApprovalRequest["status"])
              }
            >
              {Object.entries(statusLabels).map(([key, label]) => (
                <option key={key} value={key}>{label}</option>
              ))}
            </select>
          </label>
        </div>
        {approvals.isError ? (
          <p className="form-error" role="alert">{getApiErrorMessage(approvals.error)}</p>
        ) : null}
        {reviewRequest.isError ? (
          <p className="form-error" role="alert">{getApiErrorMessage(reviewRequest.error)}</p>
        ) : null}
        {pendingRequests.length ? (
          <div className="activity-approval-list">
            {pendingRequests.map((request) => (
              <article className="activity-approval-card" key={request.id}>
                <div>
                  <span className="activity-status">{statusLabels[request.status]}</span>
                  <h3>
                    {request.action === "stock_adjustment"
                      ? "Ajustement de stock"
                      : "Annulation de commande"}
                  </h3>
                  <p>{request.reason}</p>
                  {request.action === "stock_adjustment" ? (
                    <p className="activity-approval-meta">
                      {String(request.payload.quantity)} {String(request.payload.unit ?? "")} ·{" "}
                      {request.payload.direction === "in" ? "entrée" : "sortie"} ·{" "}
                      {String(request.payload.item_name ?? "Article")}
                    </p>
                  ) : (
                    <p className="activity-approval-meta">
                      {String(request.payload.order_reference ?? "Commande")} ·{" "}
                      {String(request.payload.customer_name ?? "")}
                    </p>
                  )}
                  <p className="activity-approval-meta">
                    Demandée par {request.requester_name ?? "un utilisateur"} ·{" "}
                    {formatDate(request.created_at)}
                  </p>
                </div>
                {canApprove && request.status === "pending" ? (
                  <div className="activity-approval-actions">
                    <button
                      className="button-secondary"
                      disabled={reviewRequest.isPending}
                      onClick={() => reviewRequest.mutate({ id: request.id, decision: "rejected" })}
                      type="button"
                    >
                      Refuser
                    </button>
                    <button
                      className="button-primary"
                      disabled={reviewRequest.isPending}
                      onClick={() => reviewRequest.mutate({ id: request.id, decision: "approved" })}
                      type="button"
                    >
                      Approuver
                    </button>
                  </div>
                ) : null}
              </article>
            ))}
          </div>
        ) : (
          <div className="activity-empty">
            <ClipboardCheck size={21} />
            <span>Aucune demande pour cet état.</span>
          </div>
        )}
      </section>

      <section className="panel activity-events-panel" aria-labelledby="events-title">
        <div className="panel-header">
          <div>
            <h2 className="panel-title" id="events-title">Journal d’activité</h2>
            <p className="panel-subtitle">
              {events.data?.total ?? 0} événement(s) récent(s)
            </p>
          </div>
          <label className="activity-filter">
            <span>Module</span>
            <select
              value={module}
              onChange={(event) => setModule(event.target.value as AuditModule | "all")}
            >
              <option value="all">Tous les modules</option>
              {Object.entries(moduleLabels).map(([key, label]) => (
                <option key={key} value={key}>{label}</option>
              ))}
            </select>
          </label>
        </div>
        {events.isError ? (
          <p className="form-error" role="alert">{getApiErrorMessage(events.error)}</p>
        ) : null}
        {events.isPending ? (
          <p className="activity-empty">Chargement du journal…</p>
        ) : events.data?.items.length ? (
          <div className="activity-event-list">
            {events.data.items.map((event) => (
              <article className="activity-event-row" key={event.id}>
                <span className="activity-event-icon"><History size={16} /></span>
                <div>
                  <strong>{event.summary}</strong>
                  <span>
                    {moduleLabels[event.module]} · {event.actor_name ?? "Système"} ·{" "}
                    {formatDate(event.created_at)}
                  </span>
                </div>
              </article>
            ))}
          </div>
        ) : (
          <div className="activity-empty">
            <History size={21} />
            <span>Aucune activité n’a encore été enregistrée.</span>
          </div>
        )}
      </section>
    </div>
  );
}
