"use client";

import Image from "next/image";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { ArrowRight, Home, Leaf, LoaderCircle, UserRound } from "lucide-react";
import {
  apiRequest,
  getApiErrorMessage,
  type UserProfile,
} from "@/lib/api/client";
import { PasswordInput } from "@/features/auth/password-input";

function AuthBrand() {
  return (
    <Link className="auth-brand" href="/" aria-label="Mamari, accueil">
      <Image alt="" className="auth-brand-logo" height={72} src="/icon.png" width={74} />
    </Link>
  );
}

function AuthLayout({
  eyebrow,
  title,
  description,
  children,
}: Readonly<{
  eyebrow: string;
  title: string;
  description: string;
  children: ReactNode;
}>) {
  return (
    <main className="auth-page">
      <section className="auth-visual" aria-hidden="true">
        <Image
          className="auth-visual-main"
          src="/images/login-corn.png"
          alt=""
          fill
          priority
          sizes="(max-width: 860px) 100vw, 55vw"
        />

        <div className="auth-visual-shade" />

        <div className="auth-visual-mark">
          <Leaf size={16} strokeWidth={1.8} />
          <span>mamari</span>
        </div>

        <div className="auth-photo-card auth-photo-card-tractor">
          <Image
            src="/images/login-tractor.png"
            alt=""
            fill
            sizes="(max-width: 860px) 24vw, 14vw"
          />
        </div>
        <div className="auth-photo-card auth-photo-card-cows">
          <Image
            src="/images/login-cows.png"
            alt=""
            fill
            sizes="(max-width: 860px) 24vw, 14vw"
          />
        </div>

        <div className="auth-visual-copy">
          <span>Au rythme de vos saisons</span>
          <p>La sérénité de piloter votre activité, simplement.</p>
        </div>
      </section>

      <section className="auth-content">
        <Link className="auth-home-link" href="/" aria-label="Retour au site public">
          <Home size={17} strokeWidth={1.8} />
          <span>Accueil</span>
        </Link>
        <div className="auth-card">
          <AuthBrand />
          <p className="eyebrow">{eyebrow}</p>
          <h1 className="page-title">{title}</h1>
          <p className="page-description">{description}</p>
          {children}
        </div>
        <p className="auth-footer">
          Mamari · Le pilotage clair de votre entreprise.
        </p>
      </section>
    </main>
  );
}

export function LoginPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setIsSubmitting(true);

    const formData = new FormData(event.currentTarget);
    try {
      const profile = await apiRequest<UserProfile>("/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          username: formData.get("username")?.toString(),
          password: formData.get("password")?.toString(),
        }),
      });
      await queryClient.cancelQueries({ queryKey: ["auth", "me"], exact: true });
      queryClient.setQueryData(["auth", "me"], profile);
      const requestedPath = new URLSearchParams(window.location.search).get("next");
      const requestedDestination =
        requestedPath?.startsWith("/") && !requestedPath.startsWith("//")
          ? requestedPath
          : null;
      const destination = profile.customer_account
        ? requestedDestination === "/panier" ? "/panier" : "/mon-compte"
        : requestedDestination ?? "/dashboard";
      router.replace(destination);
    } catch (submitError) {
      setError(getApiErrorMessage(submitError));
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <AuthLayout
      eyebrow="Votre espace de travail"
      title="Connectez-vous à Mamari"
      description="Accédez à votre espace client ou à l’espace de travail de votre équipe."
    >
      <form className="auth-form" onSubmit={handleSubmit}>
        <label className="auth-field">
          <span>Identifiant ou e-mail</span>
          <input
            autoComplete="username"
            autoFocus
            name="username"
            placeholder="Votre identifiant ou e-mail"
            required
            type="text"
          />
        </label>
        <label className="auth-field">
          <span>Mot de passe</span>
          <PasswordInput
            autoComplete="current-password"
            minLength={6}
            name="password"
            placeholder="Votre mot de passe"
            required
          />
        </label>
        {error ? (
          <p className="auth-error" role="alert">
            {error}
          </p>
        ) : null}
        <button
          className="button-primary auth-submit"
          disabled={isSubmitting}
          type="submit"
        >
          {isSubmitting ? (
            <LoaderCircle className="auth-spinner" size={16} />
          ) : null}
          Se connecter
          {!isSubmitting ? <ArrowRight size={16} /> : null}
        </button>
      </form>
      <p className="auth-switch">
        Nouveau client ? <Link href="/register">Créer un compte pour commander</Link>
      </p>
    </AuthLayout>
  );
}

export function CustomerRegisterPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setIsSubmitting(true);
    const formData = new FormData(event.currentTarget);
    try {
      const profile = await apiRequest<UserProfile>("/auth/customer/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          full_name: formData.get("full_name")?.toString(),
          email: formData.get("email")?.toString(),
          phone: formData.get("phone")?.toString(),
          password: formData.get("password")?.toString(),
        }),
      });
      await queryClient.cancelQueries({ queryKey: ["auth", "me"], exact: true });
      queryClient.setQueryData(["auth", "me"], profile);
      const requestedPath = new URLSearchParams(window.location.search).get("next");
      router.replace(requestedPath === "/panier" ? "/panier" : "/mon-compte");
    } catch (submitError) {
      setError(getApiErrorMessage(submitError));
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <AuthLayout
      eyebrow="Votre espace client"
      title="Créez votre compte"
      description="Retrouvez vos achats et suivez l’avancement de vos commandes."
    >
      <form className="auth-form" onSubmit={handleSubmit}>
        <label className="auth-field">
          <span>Nom complet</span>
          <input autoComplete="name" autoFocus maxLength={160} minLength={2} name="full_name" required />
        </label>
        <label className="auth-field">
          <span>Adresse e-mail</span>
          <input autoComplete="email" maxLength={320} name="email" required type="email" />
        </label>
        <label className="auth-field">
          <span>Téléphone</span>
          <input autoComplete="tel" maxLength={32} minLength={6} name="phone" required type="tel" />
        </label>
        <label className="auth-field">
          <span>Mot de passe</span>
          <PasswordInput autoComplete="new-password" minLength={6} name="password" required />
        </label>
        {error ? <p className="auth-error" role="alert">{error}</p> : null}
        <button className="button-primary auth-submit" disabled={isSubmitting} type="submit">
          {isSubmitting ? <LoaderCircle className="auth-spinner" size={16} /> : <UserRound size={16} />}
          Créer mon compte
          {!isSubmitting ? <ArrowRight size={16} /> : null}
        </button>
      </form>
      <p className="auth-switch">
        Vous avez déjà un compte ? <Link href="/login?next=%2Fpanier">Se connecter</Link>
      </p>
    </AuthLayout>
  );
}