"use client";

import { useQuery } from "@tanstack/react-query";
import { Download, Printer } from "lucide-react";
import { useState } from "react";
import { apiRequest, getApiErrorMessage, type UserProfile } from "@/lib/api/client";

interface PeriodSummary {
  start_date: string;
  end_date: string;
  order_count: number;
  revenue_fcfa: number | null;
  stock_movement_count: number;
  stock_quantities: Array<{
    unit: string;
    quantity_in: number;
    quantity_out: number;
  }>;
  harvest_count: number;
  harvest_quantity_kg: number;
  agriculture_income_fcfa: number | null;
  agriculture_expense_fcfa: number | null;
  livestock_record_count: number;
  livestock_quantities: Array<{ unit: string | null; quantity: number }>;
  livestock_income_fcfa: number | null;
  livestock_expense_fcfa: number | null;
}

interface ReportResponse {
  financial_access: boolean;
  current: PeriodSummary;
  previous: PeriodSummary;
}

function localDate(date: Date) {
  const offset = date.getTimezoneOffset();
  return new Date(date.getTime() - offset * 60_000).toISOString().slice(0, 10);
}

function number(value: number) {
  return new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 2 }).format(value);
}

function currency(value: number) {
  return `${new Intl.NumberFormat("fr-FR").format(value)} FCFA`;
}

function reportRows(period: PeriodSummary, label: string, financialAccess: boolean) {
  const rows: Array<[string, string, string, string]> = [
    [label, "Ventes", "Commandes non annulées", String(period.order_count)],
    [label, "Stocks", "Mouvements enregistrés", String(period.stock_movement_count)],
    [label, "Agriculture", "Récoltes", String(period.harvest_count)],
    [label, "Agriculture", "Production récoltée (kg)", number(period.harvest_quantity_kg)],
    [label, "Élevage", "Enregistrements", String(period.livestock_record_count)],
    ...period.stock_quantities.flatMap((item) => [
      [label, "Stocks", `Quantité entrée (${item.unit})`, number(item.quantity_in)] as [
        string,
        string,
        string,
        string,
      ],
      [label, "Stocks", `Quantité sortie (${item.unit})`, number(item.quantity_out)] as [
        string,
        string,
        string,
        string,
      ],
    ]),
    ...period.livestock_quantities.map((item) => [
      label,
      "Élevage",
      `Quantité suivie${item.unit ? ` (${item.unit})` : ""}`,
      number(item.quantity),
    ] as [string, string, string, string]),
  ];
  if (financialAccess) {
    rows.push([label, "Ventes", "Chiffre d’affaires (FCFA)", String(period.revenue_fcfa ?? 0)]);
    rows.push(
      [label, "Agriculture", "Recettes (FCFA)", String(period.agriculture_income_fcfa ?? 0)],
      [label, "Agriculture", "Dépenses (FCFA)", String(period.agriculture_expense_fcfa ?? 0)],
      [label, "Élevage", "Recettes (FCFA)", String(period.livestock_income_fcfa ?? 0)],
      [label, "Élevage", "Dépenses (FCFA)", String(period.livestock_expense_fcfa ?? 0)],
    );
  }
  return rows;
}

function downloadCsv(report: ReportResponse) {
  const rows = [
    ["Période", "Module", "Indicateur", "Valeur"],
    ...reportRows(report.current, "Période sélectionnée", report.financial_access),
    ...reportRows(report.previous, "Période précédente équivalente", report.financial_access),
  ];
  const csv = rows
    .map((row) => row.map((field) => `"${field.replaceAll('"', '""')}"`).join(";"))
    .join("\r\n");
  const blob = new Blob(["\uFEFF", csv], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `rapport-mamari-${report.current.start_date}-${report.current.end_date}.csv`;
  anchor.click();
  URL.revokeObjectURL(url);
}

function ReportCards({
  period,
  title,
  financialAccess,
}: {
  period: PeriodSummary;
  title: string;
  financialAccess: boolean;
}) {
  const cards = [
    ...(financialAccess
      ? [{ label: "Chiffre d’affaires", value: currency(period.revenue_fcfa ?? 0) }]
      : []),
    { label: "Commandes", value: number(period.order_count) },
    { label: "Mouvements de stock", value: number(period.stock_movement_count) },
    ...period.stock_quantities.map((item) => ({
      label: `Entrées / sorties (${item.unit})`,
      value: `${number(item.quantity_in)} / ${number(item.quantity_out)}`,
    })),
    { label: "Récoltes", value: `${number(period.harvest_quantity_kg)} kg · ${period.harvest_count}` },
    { label: "Élevage", value: `${period.livestock_record_count} enregistrement(s)` },
    ...period.livestock_quantities.map((item) => ({
      label: `Quantité élevage${item.unit ? ` (${item.unit})` : ""}`,
      value: number(item.quantity),
    })),
    ...(financialAccess
      ? [
          { label: "Recettes agriculture / élevage", value: `${currency(period.agriculture_income_fcfa ?? 0)} / ${currency(period.livestock_income_fcfa ?? 0)}` },
          { label: "Dépenses agriculture / élevage", value: `${currency(period.agriculture_expense_fcfa ?? 0)} / ${currency(period.livestock_expense_fcfa ?? 0)}` },
        ]
      : []),
  ];
  return (
    <section className="report-period" aria-label={title}>
      <div className="report-period-heading">
        <h2>{title}</h2>
        <span>{period.start_date} — {period.end_date}</span>
      </div>
      <div className="report-metrics">
        {cards.map((card) => (
          <article className="report-metric" key={card.label}>
            <span>{card.label}</span>
            <strong>{card.value}</strong>
          </article>
        ))}
      </div>
    </section>
  );
}

export function ReportsPage() {
  const now = new Date();
  const [startDate, setStartDate] = useState(localDate(new Date(now.getFullYear(), now.getMonth(), 1)));
  const [endDate, setEndDate] = useState(localDate(now));
  const profile = useQuery({
    queryKey: ["auth", "me"],
    queryFn: () => apiRequest<UserProfile>("/auth/me"),
    retry: false,
  });
  const membership = profile.data?.memberships[0];
  const report = useQuery({
    queryKey: ["reports", membership?.organization_id, startDate, endDate],
    queryFn: () =>
      apiRequest<ReportResponse>(
        `/dashboard/reports/summary?start_date=${startDate}&end_date=${endDate}`,
        { headers: { "X-Organization-ID": membership!.organization_id } },
      ),
    enabled: Boolean(membership && startDate && endDate && startDate <= endDate),
  });

  return (
    <div className="dashboard-content reports-workspace">
      <section className="page-heading" aria-labelledby="reports-title">
        <div>
          <p className="eyebrow">Pilotage et suivi</p>
          <h1 className="page-title" id="reports-title">Rapports d’activité</h1>
          <p className="page-description">
            Comparez ventes, stocks, agriculture et élevage avec la période précédente équivalente.
          </p>
        </div>
        <div className="report-actions">
          <button
            className="button-secondary"
            disabled={!report.data}
            onClick={() => report.data && downloadCsv(report.data)}
            type="button"
          >
            <Download size={15} /> Exporter CSV
          </button>
          <button
            className="button-secondary"
            disabled={!report.data}
            onClick={() => window.print()}
            type="button"
          >
            <Printer size={15} /> Imprimer / PDF
          </button>
        </div>
      </section>
      <section className="panel report-filter-panel" aria-label="Période du rapport">
        <label>
          <span>Du</span>
          <input type="date" value={startDate} onChange={(event) => setStartDate(event.target.value)} />
        </label>
        <label>
          <span>Au</span>
          <input type="date" value={endDate} onChange={(event) => setEndDate(event.target.value)} />
        </label>
      </section>
      {startDate > endDate ? (
        <p className="form-error" role="alert">La date de début doit précéder la date de fin.</p>
      ) : null}
      {report.isError ? (
        <div className="dashboard-error" role="alert">
          <p>{getApiErrorMessage(report.error)}</p>
          <button className="button-secondary" onClick={() => void report.refetch()} type="button">
            Réessayer
          </button>
        </div>
      ) : null}
      {report.isPending ? <div className="dashboard-loading">Calcul des rapports…</div> : null}
      {report.data ? (
        <div className="report-periods">
          <ReportCards
            financialAccess={report.data.financial_access}
            period={report.data.current}
            title="Période sélectionnée"
          />
          <ReportCards
            financialAccess={report.data.financial_access}
            period={report.data.previous}
            title="Période précédente équivalente"
          />
        </div>
      ) : null}
    </div>
  );
}
