"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import {
  ArrowRight,
  ArrowUpRight,
  ClipboardList,
  CalendarDays,
  ChartArea,
  ChartColumnIncreasing,
  ChartSpline,
  CircleDollarSign,
  Flower2,
  HeartPulse,
  PackageX,
  Sprout,
  ShoppingBasket,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import {
  ApiError,
  apiRequest,
  getApiErrorMessage,
  type UserProfile,
} from "@/lib/api/client";
import {
  formatDate,
  formatFcfa,
  orderStatusLabels,
} from "@/features/sales/sales-types";
import { isDashboardOverview } from "@/features/dashboard/dashboard-types";

type ChartStyle = "line" | "area" | "bars";
type ChartMetric = "revenue" | "production";

const metricLabels: Record<ChartMetric, string> = {
  revenue: "Chiffre d’affaires",
  production: "Production",
};

const chartStyles: Array<{
  value: ChartStyle;
  label: string;
  icon: typeof ChartSpline;
}> = [
  { value: "line", label: "Courbe", icon: ChartSpline },
  { value: "area", label: "Aire", icon: ChartArea },
  { value: "bars", label: "Colonnes", icon: ChartColumnIncreasing },
];

const statusClassNames = {
  pending: "warning",
  confirmed: "",
  preparing: "warning",
  delivered: "delivered",
  cancelled: "cancelled",
} as const;

function MetricValue({ text }: { text: string }) {
  const match = text.match(/^(.+?)\s*(FCFA|kg)$/);

  return (
    <div className="metric-value metric-value-live">
      {match ? <>{match[1]}<small>{match[2]}</small></> : text}
    </div>
  );
}

function ActivityChart({
  data,
  style,
  hasData,
  metric,
}: {
  data: Array<{ month: string; month_number: number; value: number }>;
  style: ChartStyle;
  hasData: boolean;
  metric: ChartMetric;
}) {
  const width = 720;
  const height = 196;
  const left = 5;
  const right = width - 5;
  const top = 5;
  const bottom = height - 5;
  const plotWidth = right - left;
  const plotHeight = bottom - top;
  const maxValue = Math.max(...data.map((month) => month.value), 1);
  const yMax = Math.ceil(maxValue / 4) * 4 || 4;
  const points = data.map((month, index) => ({
    ...month,
    x: left + (plotWidth * index) / Math.max(data.length - 1, 1),
    y: bottom - (month.value / yMax) * plotHeight,
  }));
  const linePath = points
    .map((point, index) => `${index === 0 ? "M" : "L"} ${point.x} ${point.y}`)
    .join(" ");
  const areaPath = `${linePath} L ${right} ${bottom} L ${left} ${bottom} Z`;
  const barWidth = Math.min(28, plotWidth / Math.max(data.length * 1.8, 1));
  const compactValue = (amount: number) => {
    let value: string;
    if (metric === "revenue" && amount >= 1_000_000) {
      value = `${new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 1 }).format(amount / 1_000_000)} M`;
    } else if (metric === "revenue" && amount >= 1_000) {
      value = `${new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 0 }).format(amount / 1_000)} k`;
    } else {
      value = new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 1 }).format(amount);
    }
    return metric === "revenue" ? `${value} F` : `${value} kg`;
  };
  const formatPointValue = (amount: number) =>
    metric === "revenue"
      ? formatFcfa(amount)
      : `${new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 2 }).format(amount)} kg`;
  const yTicks = Array.from({ length: 5 }, (_, index) =>
    Math.round((yMax * (4 - index)) / 4),
  );
  const seriesName = metric === "revenue" ? "Ventes" : "Récoltes";
  const emptyTitle =
    metric === "revenue"
      ? "Aucune vente enregistrée pour cette période"
      : "Aucune récolte enregistrée pour cette période";
  const emptyDescription =
    metric === "revenue"
      ? "Vos chiffres apparaîtront ici dès la première commande."
      : "La production apparaîtra ici dès la première récolte.";
  const emptyHref = metric === "revenue" ? "/ventes" : "/agriculture";
  const emptyLink = metric === "revenue" ? "Enregistrer une vente" : "Enregistrer une récolte";

  const pointLabel = (month: (typeof points)[number]) =>
    `${month.month} : ${formatPointValue(month.value)}`;

  return (
    <div className={`revenue-chart${hasData ? "" : " is-empty"}`}>
      <svg
        className="revenue-chart-svg"
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label={`${metricLabels[metric]} mensuelle, visualisation ${style}`}
        preserveAspectRatio="none"
      >
        <defs>
          <linearGradient id="activity-area-fill" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor="#38835c" stopOpacity=".22" />
            <stop offset="100%" stopColor="#38835c" stopOpacity=".015" />
          </linearGradient>
        </defs>
        {yTicks.map((tick, index) => {
          const y = top + (plotHeight * index) / 4;
          return (
            <line
              className="chart-grid-line"
              key={index}
              x1={left}
              x2={right}
              y1={y}
              y2={y}
              aria-label={compactValue(tick)}
            />
          );
        })}
        {style === "bars" ? (
          points.map((point) => (
            <rect
              key={point.month_number}
              className="revenue-chart-bar"
              x={point.x - barWidth / 2}
              y={point.y}
              width={barWidth}
              height={Math.max(bottom - point.y, 0)}
              rx="5"
            >
              <title>{pointLabel(point)}</title>
            </rect>
          ))
        ) : (
          <>
            {style === "area" ? <path className="revenue-chart-area" d={areaPath} /> : null}
            <path className="revenue-chart-line" d={linePath} />
            {points.map((point) => (
              <circle
                key={point.month_number}
                className="revenue-chart-point"
                cx={point.x}
                cy={point.y}
                r="3.5"
              >
                <title>{pointLabel(point)}</title>
              </circle>
            ))}
          </>
        )}
      </svg>
      <div className="chart-y-labels" aria-hidden="true">
        {yTicks.map((tick, index) => (
          <span key={index}>{compactValue(tick)}</span>
        ))}
      </div>
      <div className="chart-month-labels" aria-hidden="true">
        {data.map((month) => <span key={month.month_number}>{month.month}</span>)}
      </div>
      {!hasData ? (
        <div className="chart-empty-message">
          <span className="chart-empty-icon"><ChartSpline size={17} /></span>
          <strong>{emptyTitle}</strong>
          <span>{emptyDescription}</span>
          <Link href={emptyHref}>{emptyLink} <ArrowRight size={13} /></Link>
        </div>
      ) : null}
      <span className="visually-hidden">{seriesName}</span>
    </div>
  );
}

export function DashboardPage() {
  const [year, setYear] = useState(new Date().getFullYear());
  const [chartStyle, setChartStyle] = useState<ChartStyle>("line");
  const [chartMetric, setChartMetric] = useState<ChartMetric>("revenue");
  const [selectedMetric, setSelectedMetric] = useState<string | null>(null);
  const metricDialogRef = useRef<HTMLDialogElement>(null);
  const profile = useQuery({
    queryKey: ["auth", "me"],
    queryFn: () => apiRequest<UserProfile>("/auth/me"),
    retry: false,
  });
  const membership = profile.data?.memberships[0];
  const financialAccess = Boolean(
    membership && ["owner", "admin", "manager"].includes(membership.role),
  );
  const visibleChartMetric: ChartMetric = financialAccess ? chartMetric : "production";
  const overview = useQuery({
    queryKey: ["dashboard", "overview", membership?.organization_id, year],
    queryFn: async () => {
      const response = await apiRequest<unknown>(`/dashboard/overview?year=${year}`, {
        headers: { "X-Organization-ID": membership!.organization_id },
      });
      if (!isDashboardOverview(response)) {
        throw new ApiError(
          "Le format des indicateurs n’est pas compatible avec cette version.",
          502,
          { detail: "Mettez à jour puis redémarrez le backend Mamari." },
        );
      }
      return response;
    },
    enabled: Boolean(membership),
    refetchInterval: 15_000,
    retry: false,
  });

  const value = overview.data;
  const metrics = value
    ? [
        ...(financialAccess ? [{
          label: "Chiffre d’affaires",
          value: formatFcfa(value.revenue_fcfa ?? 0),
          detail: "ventes non annulées cette année",
          icon: CircleDollarSign,
        }] : []),
        {
          label: "Commandes",
          value: value.order_count.toLocaleString("fr-FR"),
          detail: `${value.pending_order_count} à traiter · ${value.customer_count} client(s)`,
          icon: ShoppingBasket,
        },
        {
          label: "Production",
          value: `${new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 2 }).format(value.production_kg)} kg`,
          detail: `${value.harvest_count} récolte(s) cette année`,
          icon: Sprout,
        },
        {
          label: "Parcelles actives",
          value: value.parcel_count.toLocaleString("fr-FR"),
          detail: "exploitations suivies",
          icon: Flower2,
        },
        {
          label: "Tâches en retard",
          value: value.overdue_task_count.toLocaleString("fr-FR"),
          detail: `${value.open_task_count} tâche(s) à terminer`,
          icon: ClipboardList,
        },
        {
          label: "Soins en retard",
          value: value.overdue_care_count.toLocaleString("fr-FR"),
          detail: "échéances de santé non traitées",
          icon: HeartPulse,
        },
        {
          label: "À réapprovisionner",
          value: value.restock_item_count.toLocaleString("fr-FR"),
          detail: "articles avec un solde nul ou négatif",
          icon: PackageX,
        },
      ]
    : [];
  const currentYear = new Date().getFullYear();
  const activeMetric = metrics.find((metric) => metric.label === selectedMetric);

  useEffect(() => {
    const dialog = metricDialogRef.current;
    if (!dialog) return;
    if (activeMetric && !dialog.open) dialog.showModal();
    else if (!activeMetric && dialog.open) dialog.close();
  }, [activeMetric]);

  return (
    <div className="dashboard-content">
      <section className="page-heading" aria-labelledby="dashboard-title">
        <div className="dashboard-update">
          <p className="eyebrow">
            {new Intl.DateTimeFormat("fr-FR", {
              weekday: "long",
              day: "numeric",
              month: "long",
              year: "numeric",
            }).format(new Date())}
          </p>
          <h1 className="page-title" id="dashboard-title">
            Bonjour{profile.data ? `, ${profile.data.full_name.split(/\s+/)[0]}` : ""}
          </h1>
          <p className="page-description">
            Les indicateurs ci-dessous sont calculés à partir des activités enregistrées.
          </p>
        </div>
        <div>
          <div className="date-chip">
            <CalendarDays size={15} />
            {value?.year ?? year}
          </div>
        </div>
      </section>

      {overview.isError ? (
        <div className="dashboard-error" role="alert">
          <p>{getApiErrorMessage(overview.error)}</p>
          <button
            className="button-secondary"
            type="button"
            onClick={() => void overview.refetch()}
          >
            Réessayer
          </button>
        </div>
      ) : null}

      {overview.isPending ? (
        <div className="dashboard-loading" role="status">Chargement des données réelles…</div>
      ) : null}

      {value ? (
        <>
          <section className="metrics-grid" aria-label="Indicateurs réels de l’entreprise">
            {metrics.map((metric) => {
              const Icon = metric.icon;
              return (
                <button
                  aria-haspopup="dialog"
                  className="metric-card"
                  key={metric.label}
                  onClick={() => setSelectedMetric(metric.label)}
                  type="button"
                >
                  <div className="metric-heading">
                    <span>{metric.label}</span>
                    <span className="metric-icon"><Icon size={18} /></span>
                  </div>
                  <MetricValue text={metric.value} />
                  <div className="metric-foot">{metric.detail}</div>
                  <span className="metric-details-hint">Voir le détail</span>
                </button>
              );
            })}
          </section>
          <dialog
            aria-labelledby="metric-details-title"
            className="parcel-edit-dialog dashboard-metric-dialog"
            onClose={() => setSelectedMetric(null)}
            onClick={(event) => {
              if (event.target === event.currentTarget) metricDialogRef.current?.close();
            }}
            ref={metricDialogRef}
          >
            <div className="parcel-edit-dialog-content">
              <div className="parcel-edit-dialog-heading">
                <div>
                  <h2 id="metric-details-title">{activeMetric?.label}</h2>
                  <p>Indicateur calculé sur l’année {year}</p>
                </div>
                <button
                  aria-label="Fermer"
                  className="parcel-edit-dialog-close"
                  onClick={() => metricDialogRef.current?.close()}
                  type="button"
                >
                  ×
                </button>
              </div>
              {activeMetric?.label === "Chiffre d’affaires" && value && financialAccess ? (
                <div className="metric-explanation">
                  <p>
                    Total des commandes confirmées, en préparation ou livrées. Les commandes en attente et annulées ne sont pas incluses.
                  </p>
                  <ul>
                    {(value.monthly_revenue ?? []).map((month) => (
                      <li key={month.month_number}>
                        <span>{month.month}</span><strong>{formatFcfa(month.amount_fcfa)}</strong>
                      </li>
                    ))}
                  </ul>
                  <Link className="module-back-link" href="/ventes">
                    Voir les commandes <ArrowRight size={14} />
                  </Link>
                </div>
              ) : null}
              {activeMetric?.label === "Commandes" && value ? (
                <div className="metric-explanation">
                  <p>
                    {value.order_count} commande(s) non annulée(s) sur l’année. {value.pending_order_count} commande(s) sont à traiter.
                  </p>
                  <p>
                    {value.customer_count} client(s) distinct(s)
                    {financialAccess
                      ? ` et un panier moyen de ${formatFcfa(value.average_order_fcfa ?? 0)} pour les commandes prises en compte dans le chiffre d’affaires.`
                      : "."}
                  </p>
                  <Link className="module-back-link" href="/ventes">
                    Gérer les commandes <ArrowRight size={14} />
                  </Link>
                </div>
              ) : null}
              {activeMetric?.label === "Production" && value ? (
                <div className="metric-explanation">
                  <p>
                    Cumul des récoltes saisies pour l’année : {value.harvest_count} récolte(s).
                  </p>
                  <ul>
                    {value.monthly_production_kg.map((month) => (
                      <li key={month.month_number}>
                        <span>{month.month}</span>
                        <strong>{new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 2 }).format(month.quantity_kg)} kg</strong>
                      </li>
                    ))}
                  </ul>
                  <Link className="module-back-link" href="/agriculture">
                    Voir l’agriculture <ArrowRight size={14} />
                  </Link>
                </div>
              ) : null}
              {activeMetric?.label === "Parcelles actives" && value ? (
                <div className="metric-explanation">
                  <p>
                    {value.parcel_count} parcelle(s) actuellement active(s), tous sites confondus.
                  </p>
                  <Link className="module-back-link" href="/agriculture">
                    Voir les parcelles <ArrowRight size={14} />
                  </Link>
                </div>
              ) : null}
              {activeMetric?.label === "Tâches en retard" && value ? (
                <div className="metric-explanation">
                  <p>
                    {value.overdue_task_count} tâche(s) ont dépassé leur échéance parmi les{" "}
                    {value.open_task_count} tâche(s) encore à terminer.
                  </p>
                  <Link className="module-back-link" href="/operations">
                    Ouvrir les opérations <ArrowRight size={14} />
                  </Link>
                </div>
              ) : null}
              {activeMetric?.label === "Soins en retard" && value ? (
                <div className="metric-explanation">
                  <p>
                    {value.overdue_care_count} échéance(s) de santé sont dépassées et n’ont pas
                    encore été marquées comme effectuées.
                  </p>
                  <Link className="module-back-link" href="/elevage">
                    Ouvrir le suivi d’élevage <ArrowRight size={14} />
                  </Link>
                </div>
              ) : null}
              {activeMetric?.label === "À réapprovisionner" && value ? (
                <div className="metric-explanation">
                  <p>
                    {value.restock_item_count} article(s) sont au niveau ou sous le seuil d’alerte
                    configuré. Vérifiez leurs mouvements pour planifier un réapprovisionnement.
                  </p>
                  <Link className="module-back-link" href="/stocks">
                    Voir les stocks <ArrowRight size={14} />
                  </Link>
                </div>
              ) : null}
            </div>
          </dialog>

          <section className="dashboard-grid" aria-label="Suivi des activités">
            <article className="panel revenue-panel">
              <div className="panel-header revenue-panel-header">
                <div>
                  <h2 className="panel-title">{metricLabels[visibleChartMetric]}</h2>
                  <p className="panel-subtitle">
                    {visibleChartMetric === "revenue"
                      ? "Commandes confirmées, en préparation et livrées · FCFA"
                      : "Poids des récoltes enregistrées · kg"}
                  </p>
                </div>
                <label className="year-select-label">
                  <span>Année</span>
                  <select
                    className="select-compact"
                    aria-label="Année des indicateurs"
                    value={year}
                    onChange={(event) => setYear(Number(event.target.value))}
                  >
                    {Array.from({ length: 5 }, (_, index) => currentYear - index).map(
                      (itemYear) => <option key={itemYear} value={itemYear}>{itemYear}</option>,
                    )}
                  </select>
                </label>
              </div>

              <div className="chart-toolbar">
                <div className="chart-controls">
                  <div className="chart-style-control" role="group" aria-label="Indicateur du graphique">
                    {((financialAccess
                      ? ["revenue", "production"]
                      : ["production"]) as ChartMetric[]).map((metric) => (
                      <button
                        className="chart-style-button"
                        key={metric}
                        type="button"
                        aria-pressed={visibleChartMetric === metric}
                        data-active={visibleChartMetric === metric}
                        onClick={() => setChartMetric(metric)}
                      >
                        {metric === "revenue" ? <CircleDollarSign size={15} /> : <Sprout size={15} />}
                        <span>{metric === "revenue" ? "Revenus" : "Production"}</span>
                      </button>
                    ))}
                  </div>
                  <span className="chart-legend">
                    <span className="legend-item">
                      <span className="legend-dot" /> {visibleChartMetric === "revenue" ? "Ventes" : "Récoltes"}
                    </span>
                  </span>
                </div>
                <div className="chart-style-control" role="group" aria-label="Type de graphique">
                  {chartStyles.map(({ value: style, label, icon: Icon }) => (
                    <button
                      className="chart-style-button"
                      key={style}
                      type="button"
                      aria-label={label}
                      aria-pressed={chartStyle === style}
                      data-active={chartStyle === style}
                      onClick={() => setChartStyle(style)}
                    >
                      <Icon size={15} />
                      <span>{label}</span>
                    </button>
                  ))}
                </div>
              </div>
              <ActivityChart
                data={
                  visibleChartMetric === "revenue"
                    ? (value.monthly_revenue ?? []).map((month) => ({
                        month: month.month,
                        month_number: month.month_number,
                        value: month.amount_fcfa,
                      }))
                    : value.monthly_production_kg.map((month) => ({
                        month: month.month,
                        month_number: month.month_number,
                        value: month.quantity_kg,
                      }))
                }
                style={chartStyle}
                hasData={visibleChartMetric === "revenue" ? (value.revenue_fcfa ?? 0) > 0 : value.production_kg > 0}
                metric={visibleChartMetric}
              />
            </article>

            <article className="panel recent-orders-panel">
              <div className="panel-header">
                <div>
                  <h2 className="panel-title">Commandes récentes</h2>
                  <p className="panel-subtitle">Dernières ventes enregistrées</p>
                </div>
                <Link className="icon-button" href="/ventes" aria-label="Ouvrir les ventes">
                  <ArrowUpRight size={15} />
                </Link>
              </div>
              {value.recent_orders.length ? (
                <div className="activity-list">
                  {value.recent_orders.map((order) => (
                    <div className="activity-item" key={order.id}>
                      <span className="activity-marker"><ShoppingBasket size={15} /></span>
                      <div className="activity-copy">
                        <p>
                          <strong>{order.customer_name}</strong>
                          <br />
                          {order.reference} · {formatFcfa(order.amount_fcfa)}
                        </p>
                        <div className="activity-meta">
                          <time dateTime={order.order_date}>{formatDate(order.order_date)}</time>
                          <span className={`status-pill ${statusClassNames[order.status]}`}>
                            {orderStatusLabels[order.status]}
                          </span>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="recent-orders-empty">
                  <ShoppingBasket size={20} />
                  <p>Aucune commande enregistrée pour {year}.</p>
                  <Link href="/ventes">Ajouter la première vente <ArrowRight size={13} /></Link>
                </div>
              )}
            </article>
          </section>
          <section className="panel recent-harvest-panel">
            <div className="panel-header">
              <div>
                <h2 className="panel-title">Récoltes récentes</h2>
                <p className="panel-subtitle">Production agricole saisie cette année</p>
              </div>
              <Link className="icon-button" href="/agriculture" aria-label="Ouvrir l’agriculture">
                <ArrowUpRight size={15} />
              </Link>
            </div>
            {value.recent_harvests.length ? (
              <div className="activity-list">
                {value.recent_harvests.map((harvest) => (
                  <div className="activity-item" key={harvest.id}>
                    <span className="activity-marker"><Sprout size={15} /></span>
                    <div className="activity-copy">
                      <p>
                        <strong>{harvest.crop}</strong> · {harvest.parcel_name}
                        <br />
                        {new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 2 }).format(harvest.quantity_kg)} kg
                      </p>
                      <div className="activity-meta">
                        <time dateTime={harvest.harvest_date}>{formatDate(harvest.harvest_date)}</time>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="recent-orders-empty">
                <Sprout size={20} />
                <p>Aucune récolte enregistrée pour {year}.</p>
                <Link href="/agriculture">Ajouter une récolte <ArrowRight size={13} /></Link>
              </div>
            )}
          </section>
        </>
      ) : null}
    </div>
  );
}
