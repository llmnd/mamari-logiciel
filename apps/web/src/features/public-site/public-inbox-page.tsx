"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { LoaderCircle, Mail, RefreshCw } from "lucide-react";
import { useState } from "react";
import { apiRequest, getApiErrorMessage, type UserProfile } from "@/lib/api/client";

type InquiryStatus = "new" | "read" | "replied";

interface ContactInquiry {
  id: string;
  full_name: string;
  email: string;
  subject: string;
  message: string;
  status: InquiryStatus;
  created_at: string;
}

interface NewsletterSubscriber {
  id: string;
  email: string;
  consented_at: string;
  created_at: string;
}

interface PublicInbox {
  inquiries: ContactInquiry[];
  subscribers: NewsletterSubscriber[];
  inquiry_total: number;
  subscriber_total: number;
}

const inquiryStatusLabels: Record<InquiryStatus, string> = {
  new: "Nouveau",
  read: "Lu",
  replied: "Répondu",
};

function formatDate(value: string) {
  return new Intl.DateTimeFormat("fr-FR", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

export function PublicInboxPage() {
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const inquiryPageSize = 50;
  const profile = useQuery({
    queryKey: ["auth", "me"],
    queryFn: () => apiRequest<UserProfile>("/auth/me"),
    retry: false,
  });
  const organizationId = profile.data?.memberships[0]?.organization_id;
  const inbox = useQuery({
    queryKey: ["public-inbox", organizationId, page],
    queryFn: () =>
      apiRequest<PublicInbox>(`/public/inbox?page=${page}&page_size=${inquiryPageSize}`, {
        headers: { "X-Organization-ID": organizationId ?? "" },
      }),
    enabled: Boolean(organizationId),
  });
  const updateStatus = useMutation({
    mutationFn: ({ id, status }: { id: string; status: InquiryStatus }) =>
      apiRequest<ContactInquiry>(`/public/inbox/${id}`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          "X-Organization-ID": organizationId ?? "",
        },
        body: JSON.stringify({ status }),
      }),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["public-inbox", organizationId] }),
  });

  return (
    <div className="dashboard-content public-inbox-page">
      <section className="page-heading" aria-labelledby="public-inbox-title">
        <div>
          <p className="eyebrow">Site public</p>
          <h1 className="page-title" id="public-inbox-title">Messages et newsletter</h1>
          <p className="page-description">
            Consultez les demandes envoyées depuis le site et les inscriptions actives.
          </p>
        </div>
        <button
          className="button-secondary"
          type="button"
          onClick={() => void inbox.refetch()}
          disabled={inbox.isFetching}
        >
          {inbox.isFetching
            ? <LoaderCircle className="auth-spinner" size={16} />
            : <RefreshCw size={16} />}
          Actualiser
        </button>
      </section>

      {inbox.isPending ? (
        <section className="panel public-inbox-state" role="status">
          <LoaderCircle className="auth-spinner" size={20} /> Chargement de la boîte de réception…
        </section>
      ) : inbox.isError ? (
        <section className="panel public-inbox-state" role="alert">
          <p>{getApiErrorMessage(inbox.error)}</p>
          <button className="button-primary" type="button" onClick={() => void inbox.refetch()}>
            Réessayer
          </button>
        </section>
      ) : (
        <>
          <section className="public-inbox-summary" aria-label="Résumé">
            <article className="panel public-inbox-stat">
              <span><Mail size={17} /> Demandes reçues</span>
              <strong>{inbox.data.inquiry_total}</strong>
            </article>
            <article className="panel public-inbox-stat">
              <span><Mail size={17} /> Abonnés actifs</span>
              <strong>{inbox.data.subscriber_total}</strong>
            </article>
          </section>

          <section className="panel public-inbox-section" aria-labelledby="inquiries-title">
            <header>
              <div>
                <h2 id="inquiries-title">Demandes de contact</h2>
                <p>Les plus récentes apparaissent en premier.</p>
              </div>
            </header>
            {inbox.data.inquiries.length === 0 ? (
              <p className="public-inbox-empty">Aucune demande reçue pour le moment.</p>
            ) : (
              <div className="public-inquiry-list">
                {inbox.data.inquiries.map((inquiry) => (
                  <article className="public-inquiry-card" key={inquiry.id}>
                    <div className="public-inquiry-heading">
                      <div>
                        <h3>{inquiry.subject}</h3>
                        <p>{inquiry.full_name} · <a href={`mailto:${inquiry.email}`}>{inquiry.email}</a></p>
                      </div>
                      <label>
                        <span className="sr-only">Statut de la demande</span>
                        <select
                          value={inquiry.status}
                          disabled={updateStatus.isPending}
                          onChange={(event) =>
                            updateStatus.mutate({
                              id: inquiry.id,
                              status: event.target.value as InquiryStatus,
                            })
                          }
                        >
                          {Object.entries(inquiryStatusLabels).map(([value, label]) => (
                            <option key={value} value={value}>{label}</option>
                          ))}
                        </select>
                      </label>
                    </div>
                    <p className="public-inquiry-message">{inquiry.message}</p>
                    <time dateTime={inquiry.created_at}>{formatDate(inquiry.created_at)}</time>
                  </article>
                ))}
              </div>
            )}
            {inbox.data.inquiry_total > inquiryPageSize ? (
              <nav className="public-inbox-pagination" aria-label="Pagination des demandes">
                <button
                  className="button-secondary"
                  type="button"
                  disabled={page <= 1 || inbox.isFetching}
                  onClick={() => setPage((current) => Math.max(1, current - 1))}
                >
                  Précédent
                </button>
                <span aria-live="polite">
                  Page {page} sur {Math.ceil(inbox.data.inquiry_total / inquiryPageSize)}
                </span>
                <button
                  className="button-secondary"
                  type="button"
                  disabled={
                    page >= Math.ceil(inbox.data.inquiry_total / inquiryPageSize) ||
                    inbox.isFetching
                  }
                  onClick={() => setPage((current) => current + 1)}
                >
                  Suivant
                </button>
              </nav>
            ) : null}
            {updateStatus.isError ? (
              <p className="public-inbox-error" role="alert">{getApiErrorMessage(updateStatus.error)}</p>
            ) : null}
          </section>

          <section className="panel public-inbox-section" aria-labelledby="subscribers-title">
            <header>
              <div>
                <h2 id="subscribers-title">Newsletter</h2>
                <p>Adresses ayant consenti à recevoir les actualités.</p>
              </div>
            </header>
            {inbox.data.subscribers.length === 0 ? (
              <p className="public-inbox-empty">Aucun abonné actif pour le moment.</p>
            ) : (
              <>
                <ul className="public-subscriber-list">
                  {inbox.data.subscribers.map((subscriber) => (
                    <li key={subscriber.id}>
                      <a href={`mailto:${subscriber.email}`}>{subscriber.email}</a>
                      <span>Inscription le {formatDate(subscriber.consented_at)}</span>
                    </li>
                  ))}
                </ul>
                {inbox.data.subscriber_total > inbox.data.subscribers.length ? (
                  <p className="public-inbox-empty">
                    Affichage des 500 inscriptions actives les plus récentes.
                  </p>
                ) : null}
              </>
            )}
          </section>
        </>
      )}
    </div>
  );
}
