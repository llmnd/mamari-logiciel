"use client";

import NextImage from "next/image";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  Bell,
  Building2,
  CalendarDays,
  ChevronRight,
  CircleHelp,
  ClipboardList,
  Coins,
  Contact,
  Factory,
  FileSpreadsheet,
  Image as ImageIcon,
  LayoutDashboard,
  Leaf,
  Mail,
  LoaderCircle,
  LogOut,
  Package,
  Pencil,
  Settings2,
  ShoppingCart,
  UsersRound,
  X,
} from "lucide-react";
import { ChangePasswordForm } from "@/features/auth/change-password-form";
import {
  ApiError,
  apiRequest,
  getApiErrorMessage,
  type OrganizationMembership,
  type UserProfile,
} from "@/lib/api/client";

const navigation = [
  { label: "Vue d'ensemble", href: "/dashboard", icon: LayoutDashboard },
  { label: "Activité et approbations", href: "/activite", icon: Activity },
  { label: "Rapports", href: "/rapports", icon: FileSpreadsheet },
  { label: "Opérations", href: "/operations", icon: ClipboardList },
  { label: "Agriculture", href: "/agriculture", icon: Leaf },
  { label: "Élevage", href: "/elevage", icon: Activity },
  { label: "Stocks", href: "/stocks", icon: Package },
  { label: "Productions", href: "/productions", icon: Factory },
  { label: "Ventes", href: "/ventes", icon: ShoppingCart },
  { label: "Clients", href: "/clients", icon: Contact },
  { label: "Finances", href: "/finances", icon: Coins },
  { label: "Ressources humaines", href: "/rh", icon: UsersRound },
  { label: "Communication", href: "/communication", icon: ImageIcon },
  { label: "Messages et newsletter", href: "/messages", icon: Mail },
  { label: "Entreprise", href: "/entreprise", icon: Building2 },
  { label: "Administration", href: "/administration", icon: Settings2 },
];

const roleLabels = {
  owner: "Propriétaire",
  admin: "Administratrice",
  manager: "Gestionnaire",
  operator: "Opérateur",
  reader: "Lecture seule",
} as const;

function canAccessPath(role: OrganizationMembership["role"], pathname: string): boolean {
  if (role === "owner" || role === "admin") return true;
  if (role === "manager") return pathname !== "/administration" && !pathname.startsWith("/administration/");
  return (
    pathname === "/dashboard" ||
    pathname === "/activite" ||
    pathname === "/rapports" ||
    pathname === "/agriculture" ||
    pathname === "/elevage" ||
    pathname === "/operations" ||
    pathname.startsWith("/operations/") ||
    pathname === "/stocks" ||
    pathname === "/productions" ||
    pathname === "/ventes" ||
    pathname === "/clients" ||
    pathname === "/aide" ||
    pathname.startsWith("/aide/")
  );
}

export function AppShell({ children }: Readonly<{ children: ReactNode }>) {
  const pathname = usePathname();
  const router = useRouter();
  const queryClient = useQueryClient();
  const profileButtonRef = useRef<HTMLButtonElement>(null);
  const profileDialogRef = useRef<HTMLDialogElement>(null);
  const isPublicRoute =
    pathname === "/" ||
    pathname === "/produits" ||
    pathname === "/panier" ||
    pathname === "/qui-sommes-nous" ||
    pathname === "/contact" ||
    pathname === "/confidentialite" ||
    pathname === "/conditions-de-vente" ||
    pathname === "/login" ||
    pathname === "/register";
  const isCustomerRoute = pathname === "/mon-compte";
  const [logoutError, setLogoutError] = useState<string | null>(null);
  const [logoutPending, setLogoutPending] = useState(false);
  const [profileDialogOpen, setProfileDialogOpen] = useState(false);
  const [profileEditing, setProfileEditing] = useState(false);
  const profile = useQuery({
    queryKey: ["auth", "me"],
    queryFn: () => apiRequest<UserProfile>("/auth/me"),
    enabled: !isPublicRoute,
    retry: false,
  });
  const updateProfile = useMutation({
    mutationFn: (data: { full_name: string; phone: string | null }) => {
      const organizationId = profile.data?.memberships[0]?.organization_id;
      if (!organizationId) throw new Error("Aucune organisation active n’est associée au compte.");
      return apiRequest<UserProfile>("/auth/me", {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          "X-Organization-ID": organizationId,
        },
        body: JSON.stringify(data),
      });
    },
    onSuccess: (updatedProfile) => {
      queryClient.setQueryData(["auth", "me"], updatedProfile);
      setProfileEditing(false);
    },
  });
  const role = profile.data?.memberships[0]?.role;
  const canAccessCurrentPath = role ? canAccessPath(role, pathname) : true;

  useEffect(() => {
    if (!isPublicRoute && profile.error instanceof ApiError && profile.error.status === 401) {
      router.replace(`/login?next=${encodeURIComponent(pathname)}`);
    }
  }, [isPublicRoute, pathname, profile.error, router]);

  useEffect(() => {
    if (!isPublicRoute && role && !canAccessCurrentPath) {
      router.replace("/dashboard");
    }
  }, [canAccessCurrentPath, isPublicRoute, role, router]);

  useEffect(() => {
    const dialog = profileDialogRef.current;
    if (!dialog) return;

    if (profileDialogOpen && !dialog.open) {
      dialog.showModal();
    } else if (!profileDialogOpen && dialog.open) {
      dialog.close();
    }
  }, [profileDialogOpen]);

  if (isPublicRoute) return <>{children}</>;

  if (profile.isPending) {
    return (
      <div className="auth-loading" role="status">
        <NextImage alt="" className="private-brand-logo" height={42} src="/icon.png" width={44} />
        <span>Chargement de votre espace…</span>
      </div>
    );
  }

  if (profile.isError || !profile.data) {
    return (
      <div className="auth-loading">
        <p className="auth-error">{getApiErrorMessage(profile.error)}</p>
        <button className="button-primary" type="button" onClick={() => void profile.refetch()}>
          Réessayer
        </button>
      </div>
    );
  }

  if (isCustomerRoute) {
    if (profile.data.customer_account) return <>{children}</>;
    return (
      <div className="auth-loading">
        <p className="auth-error">Cet espace est réservé aux comptes clients de la boutique.</p>
        <button className="button-secondary" type="button" onClick={() => router.replace("/produits")}>
          Retour à la boutique
        </button>
      </div>
    );
  }

  const membership = profile.data.memberships[0];
  if (!membership) {
    return (
      <div className="auth-loading">
        <p className="auth-error">Aucune organisation active n&apos;est associée à votre compte.</p>
        <button
          className="button-secondary"
          type="button"
          onClick={() => router.replace("/login")}
        >
          Retour à la connexion
        </button>
      </div>
    );
  }

  if (!canAccessCurrentPath) {
    return (
      <div className="auth-loading" role="status">
        <span>Redirection vers les pages autorisées…</span>
      </div>
    );
  }

  const currentPage =
    navigation.find((item) => item.href === pathname)?.label ?? "Vue d'ensemble";
  const profileInitials = profile.data.full_name
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part.charAt(0))
    .join("")
    .toLocaleUpperCase("fr");

  async function handleLogout() {
    if (logoutPending) return;
    setLogoutError(null);
    setLogoutPending(true);
    try {
      await apiRequest<{ message: string }>("/auth/logout", { method: "POST" });
      queryClient.clear();
      router.replace("/");
    } catch (error) {
      setLogoutError(getApiErrorMessage(error));
    } finally {
      setLogoutPending(false);
    }
  }

  return (
    <div className="app-shell">
      <aside className="sidebar" aria-label="Navigation principale">
        <Link className="brand" href="/" aria-label="Mamari, accueil">
          <NextImage alt="" className="private-brand-logo" height={62} src="/icon.png" width={64} />
          <span>
            <span className="brand-caption">Gestion d&apos;entreprise</span>
          </span>
        </Link>

        <nav aria-label="Modules">
          <div className="nav-label">Espace de travail</div>
          <div className="nav-list">
            {navigation.filter(({ href }) => canAccessPath(membership.role, href)).map(({ label, href, icon: Icon }) => {
              const active =
                pathname === href ||
                (href !== "/" && pathname.startsWith(`${href}/`));
              return (
                <Link
                  key={href}
                  className="nav-link"
                  href={href}
                  data-active={active}
                  aria-current={active ? "page" : undefined}
                >
                  <Icon size={17} strokeWidth={1.8} />
                  <span>{label}</span>
                </Link>
              );
            })}
          </div>
        </nav>

        <div className="sidebar-footer">
          <button
            ref={profileButtonRef}
            className="profile profile-trigger"
            type="button"
            aria-haspopup="dialog"
            aria-expanded={profileDialogOpen}
            aria-controls="profile-dialog"
            onClick={() => setProfileDialogOpen(true)}
          >
            <span className="profile-avatar">
              {profileInitials}
            </span>
            <span className="profile-copy">
              <strong title={profile.data.full_name}>{profile.data.full_name}</strong>
              <span title={profile.data.username}>
                {roleLabels[membership.role]} · {profile.data.username}
              </span>
            </span>
            <ChevronRight className="profile-trigger-chevron" size={16} aria-hidden="true" />
          </button>
        </div>
      </aside>

      <dialog
        ref={profileDialogRef}
        id="profile-dialog"
        className="profile-dialog"
        aria-labelledby="profile-dialog-title"
        onClose={() => {
          setProfileDialogOpen(false);
          setProfileEditing(false);
        }}
        onClick={(event) => {
          if (event.target === event.currentTarget) setProfileDialogOpen(false);
        }}
      >
        <section className="profile-dialog-card">
          <header className="profile-dialog-header">
            <div>
              <p className="profile-dialog-eyebrow">Votre compte</p>
              <h2 id="profile-dialog-title">Profil et actions</h2>
            </div>
            <button
              className="profile-dialog-close"
              type="button"
              aria-label="Fermer le profil"
              onClick={() => setProfileDialogOpen(false)}
              autoFocus
            >
              <X size={18} />
            </button>
          </header>

          <div className="profile-dialog-identity">
            <span className="profile-avatar profile-dialog-avatar" aria-hidden="true">
              {profileInitials}
            </span>
            <span className="profile-dialog-copy">
              <strong>{profile.data.full_name}</strong>
              <span>{roleLabels[membership.role]} · {profile.data.username}</span>
              <span>{membership.organization_name}</span>
            </span>
          </div>

          {profileEditing ? (
            <form
              className="profile-edit-form"
              onSubmit={(event) => {
                event.preventDefault();
                const formData = new FormData(event.currentTarget);
                updateProfile.mutate({
                  full_name: String(formData.get("full_name") ?? "").trim(),
                  phone: String(formData.get("phone") ?? "").trim() || null,
                });
              }}
            >
              <label>
                <span>Nom complet</span>
                <input
                  autoComplete="name"
                  defaultValue={profile.data.full_name}
                  maxLength={160}
                  minLength={2}
                  name="full_name"
                  required
                />
              </label>
              <label>
                <span>Téléphone</span>
                <input
                  autoComplete="tel"
                  defaultValue={profile.data.phone ?? ""}
                  maxLength={32}
                  minLength={6}
                  name="phone"
                  type="tel"
                />
              </label>
              {updateProfile.isError ? (
                <p className="profile-edit-error" role="alert">{getApiErrorMessage(updateProfile.error)}</p>
              ) : null}
              <div className="profile-edit-actions">
                <button
                  className="profile-edit-cancel"
                  onClick={() => {
                    updateProfile.reset();
                    setProfileEditing(false);
                  }}
                  type="button"
                >
                  Annuler
                </button>
                <button className="profile-edit-save" disabled={updateProfile.isPending} type="submit">
                  {updateProfile.isPending ? <LoaderCircle className="auth-spinner" size={15} /> : null}
                  {updateProfile.isPending ? "Enregistrement…" : "Enregistrer"}
                </button>
              </div>
            </form>
          ) : (
            <button
              className="profile-edit-trigger"
              onClick={() => {
                updateProfile.reset();
                setProfileEditing(true);
              }}
              type="button"
            >
              <Pencil size={15} /> Modifier mon profil
            </button>
          )}

          <div className="profile-dialog-actions">
            <Link
              className="profile-dialog-action"
              href="/aide"
              onClick={() => setProfileDialogOpen(false)}
            >
              <CircleHelp size={18} aria-hidden="true" />
              <span>Centre d&apos;aide</span>
              <ChevronRight size={16} aria-hidden="true" />
            </Link>
            <button
              className="profile-dialog-action profile-dialog-logout"
              type="button"
              onClick={() => void handleLogout()}
              disabled={logoutPending}
              aria-busy={logoutPending}
            >
              <LogOut size={18} aria-hidden="true" />
              <span>{logoutPending ? "Déconnexion en cours…" : "Se déconnecter"}</span>
            </button>
          </div>
          <section className="profile-password-section" aria-labelledby="profile-password-title">
            <h3 id="profile-password-title">Sécurité du compte</h3>
            <ChangePasswordForm />
          </section>
          {logoutError ? <p className="logout-error" role="alert">{logoutError}</p> : null}
        </section>
      </dialog>

      <div className="main-area">
        <header className="topbar">
          <div className="breadcrumb">
            <span>{membership.organization_name}</span>
            <ChevronRight size={14} />
            <strong>{currentPage}</strong>
          </div>
          <div className="topbar-actions">
            <button className="icon-button" type="button" aria-label="Calendrier">
              <CalendarDays size={16} />
            </button>
            <button className="icon-button" type="button" aria-label="Notifications">
              <Bell size={16} />
            </button>
          </div>
        </header>
        <main>{children}</main>
      </div>
    </div>
  );
}
