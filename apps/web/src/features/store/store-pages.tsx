"use client";

import Image from "next/image";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Lenis from "lenis";
import {
  ArrowRight,
  ArrowLeft,
  ArrowUp,
  Check,
  ChevronRight,
  Leaf,
  LoaderCircle,
  Minus,
  Plus,
  Search,
  ShieldCheck,
  ShoppingBag,
  Sprout,
  Tractor,
  Trash2,
  Wheat,
  Truck,
  Sun,
  CalendarDays,
  Users,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { ApiError, apiRequest, getApiErrorMessage } from "@/lib/api/client";
import { formatFcfa } from "@/features/sales/sales-types";
import type {
  StoreCustomerProfile,
  StoreOrder,
  StoreProduct,
  StoreProductPage,
} from "./store-types";
import { useShopCart } from "./use-shop-cart";
import { useProductPhoto } from "./use-product-photo";
import type { UserProfile } from "@/lib/api/client";

const storeProductsQueryKey = ["store", "products"];

/* ------------------------------------------------------------------ */
/*  HEADER                                                             */
/* ------------------------------------------------------------------ */
function PublicHeader() {
  const { cart } = useShopCart();
  const profile = useQuery({
    queryKey: ["auth", "me"],
    queryFn: () => apiRequest<UserProfile>("/auth/me"),
    retry: false,
  });
  const cartCount = Object.values(cart).reduce((total, quantity) => total + quantity, 0);
  const [scrolled, setScrolled] = useState(false);
  const [showTop, setShowTop] = useState(false);
  const lenisRef = useRef<Lenis | null>(null);

  useEffect(() => {
    const lenis = new Lenis({
      autoRaf: true,
      anchors: { offset: -110 },
      lerp: 0.1,
      respectReducedMotion: true,
      stopInertiaOnNavigate: true,
    });
    lenisRef.current = lenis;

    const onScroll = () => {
      setScrolled(window.scrollY > 24);
      setShowTop(window.scrollY > 700);
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      window.removeEventListener("scroll", onScroll);
      lenis.destroy();
      lenisRef.current = null;
    };
  }, []);

  function scrollToTop() {
    if (lenisRef.current) {
      lenisRef.current.scrollTo(0);
    } else {
      window.scrollTo({ top: 0, behavior: "smooth" });
    }
  }

  return (
    <>
      <header className={`public-header${scrolled ? " is-scrolled" : ""}`}>
        <Link className="public-brand" href="/" aria-label="Mamari, accueil">
          <Image
            alt=""
            className="public-brand-logo"
            height={76}
            priority
            src="/icon.png"
            width={78}
          />
        </Link>
        <nav className="public-navigation" aria-label="Navigation principale">
          <span className="public-nav-links">
            <Link href="/#activites">Nos activités</Link>
            <Link href="/qui-sommes-nous">Qui sommes-nous ?</Link>
            <Link href="/produits">La boutique</Link>
          </span>
          <span className="public-nav-actions">
            <Link className="public-cart-link" href="/panier" aria-label={`Panier${cartCount ? `, ${cartCount} article(s)` : ""}`}>
              <ShoppingBag size={17} />
              <span>Panier</span>
              {cartCount ? <span className="public-cart-count">{cartCount}</span> : null}
            </Link>
            <Link
              className="public-login-link"
              href={profile.data?.customer_account ? "/mon-compte" : "/login"}
            >
              {profile.data?.customer_account ? "Mon compte" : "Connexion"} <ArrowRight size={14} />
            </Link>
          </span>
        </nav>
      </header>
      <button
        className={`public-top-button${showTop ? " is-visible" : ""}`}
        type="button"
        aria-label="Retour en haut de la page"
        tabIndex={showTop ? 0 : -1}
        onClick={scrollToTop}
      >
        <ArrowUp size={18} />
      </button>
    </>
  );
}

/* ------------------------------------------------------------------ */
/*  FOOTER                                                             */
/* ------------------------------------------------------------------ */
function PublicFooter() {
  return (
    <footer className="public-footer">
      <div className="public-footer-main">
        <div className="public-footer-about">
          <Link className="public-brand" href="/" aria-label="Mamari, accueil">
            <Image
              alt=""
              className="public-brand-logo"
              height={66}
              src="/icon.png"
              width={68}
            />
          </Link>
          <p>Des activités agricoles durables et des produits choisis avec soin, au rythme des saisons.</p>
        </div>
        <nav className="public-footer-nav" aria-label="Découvrir Mamari">
          <h2>Découvrir</h2>
          <Link href="/#activites">Nos activités</Link>
          <Link href="/qui-sommes-nous">Qui sommes-nous ?</Link>
          <Link href="/produits">La boutique</Link>
          <Link href="/panier">Votre panier</Link>
          <Link href="/contact">Nous contacter</Link>
        </nav>
        <div className="public-footer-team">
          <h2>Une question ?</h2>
          <p>Notre équipe est à votre écoute pour vous accompagner.</p>
          <Link href="/login?next=%2Fmon-compte">Espace client <ArrowRight size={14} /></Link>
          <Link href="/dashboard">Espace équipe <ArrowRight size={14} /></Link>
          <Link href="/confidentialite">Confidentialité</Link>
          <Link href="/conditions-de-vente">Conditions de vente</Link>
        </div>
      </div>
      <div className="public-footer-bottom">
        <span>© {new Date().getFullYear()} Mamari. Tous droits réservés.</span>
        <span>Du champ à votre table.</span>
      </div>
    </footer>
  );
}

/* ------------------------------------------------------------------ */
/*  PRODUCT IMAGE                                                      */
/* ------------------------------------------------------------------ */
function ProductImage({
  product,
  className = "store-product-image",
}: {
  product: StoreProduct;
  className?: string;
}) {
  const { imageUrl, hasError } = useProductPhoto(product.photo_url);
  return (
    <div className={className}>
      {imageUrl ? (
        <Image alt="" fill sizes="(max-width: 700px) 90vw, (max-width: 1100px) 45vw, 28vw" src={imageUrl} unoptimized />
      ) : (
        <span className="store-product-placeholder">
          <Sprout size={38} strokeWidth={1.3} aria-hidden="true" />
          {hasError ? <small>Photo indisponible</small> : null}
        </span>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  PRODUCT CARD                                                       */
/*  Avec onAdd : bouton « Ajouter », puis stepper − / + dès que le     */
/*  produit est dans le panier.                                        */
/* ------------------------------------------------------------------ */
function StoreProductCard({
  product,
  quantity = 0,
  onAdd,
  onRemove,
}: {
  product: StoreProduct;
  quantity?: number;
  onAdd?: (product: StoreProduct) => void;
  onRemove?: (product: StoreProduct) => void;
}) {
  const unavailable = product.stock_quantity < 1;
  const lowStock = !unavailable && product.stock_quantity <= 5;
  return (
    <article className={`store-product-card${unavailable ? " is-soldout" : ""}`}>
      {lowStock ? <span className="store-stock-low">Plus que {product.stock_quantity}</span> : null}
      <ProductImage product={product} />
      <div className="store-product-copy">
        <div className="store-product-heading">
          <div>
            {product.category ? <span className="store-product-category">{product.category}</span> : null}
            <h3>{product.name}</h3>
          </div>
          {unavailable ? <span className="store-stock-empty">Épuisé</span> : null}
        </div>
        {product.description ? <p>{product.description}</p> : null}
        <div className="store-product-bottom">
          <span className="store-product-price">
            {formatFcfa(product.price_fcfa)}
            <small> / {product.unit}</small>
          </span>
          {onAdd ? (
            quantity > 0 ? (
              <div className="store-quantity" role="group" aria-label={`Quantité de ${product.name}`}>
                <button type="button" aria-label={`Retirer une unité de ${product.name}`} onClick={() => onRemove?.(product)}>
                  <Minus size={14} />
                </button>
                <span>{quantity}</span>
                <button
                  type="button"
                  aria-label={`Ajouter une unité de ${product.name}`}
                  disabled={quantity >= product.stock_quantity}
                  onClick={() => onAdd(product)}
                >
                  <Plus size={14} />
                </button>
              </div>
            ) : (
              <button className="store-add-button" type="button" disabled={unavailable} onClick={() => onAdd(product)}>
                <Plus size={16} /> Ajouter
              </button>
            )
          ) : (
            <Link className="store-card-link" href="/produits">
              Découvrir <ArrowRight size={14} />
            </Link>
          )}
        </div>
      </div>
    </article>
  );
}

/* ------------------------------------------------------------------ */
/*  FAQ                                                                */
/* ------------------------------------------------------------------ */
const faqItems = [
  {
    question: "Comment passer commande ?",
    answer:
      "Ajoutez vos produits au panier, renseignez vos coordonnées puis confirmez. Notre équipe vous recontacte pour valider votre commande.",
  },
  {
    question: "Faut-il payer en ligne ?",
    answer:
      "Non, aucun paiement en ligne n’est demandé. Le règlement est organisé avec notre équipe au moment de la confirmation.",
  },
  {
    question: "Comment se passe la livraison ?",
    answer:
      "Les modalités de livraison sont confirmées avec vous par téléphone, selon votre adresse et la disponibilité des produits.",
  },
  {
    question: "Les produits sont-ils toujours disponibles ?",
    answer:
      "Les stocks sont mis à jour en continu. Un produit épuisé est signalé dans la boutique et les quantités sont limitées au stock disponible.",
  },
];

function FaqSection() {
  return (
    <section className="public-section public-faq">
      <div className="public-section-heading">
        <div>
          <p className="public-eyebrow">Bon à savoir</p>
          <h2>Vos questions, nos réponses.</h2>
        </div>
        <p>Tout ce qu&apos;il faut savoir avant de passer commande.</p>
      </div>
      <div className="public-faq-list">
        {faqItems.map((item) => (
          <details className="public-faq-item" key={item.question}>
            <summary>
              <span>{item.question}</span>
              <Plus size={18} aria-hidden="true" />
            </summary>
            <p>{item.answer}</p>
          </details>
        ))}
      </div>
    </section>
  );
}

/* ------------------------------------------------------------------ */
/*  HOME                                                               */
/* ------------------------------------------------------------------ */
export function PublicHomePage() {
  const products = useQuery({
    queryKey: storeProductsQueryKey,
    queryFn: () => apiRequest<StoreProductPage>("/store/products"),
    retry: false,
  });
  const featuredProducts = products.data?.items.slice(0, 3) ?? [];
  const newsletter = useMutation({
    mutationFn: (submission: { email: string; website: string }) =>
      apiRequest<{
        subscribed: boolean;
        already_subscribed: boolean;
        unsubscribe_token: string | null;
      }>("/public/newsletter", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...submission, consent: true }),
      }),
  });
  const unsubscribe = useMutation({
    mutationFn: (token: string) =>
      apiRequest<void>("/public/newsletter/unsubscribe", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token }),
      }),
  });
  const unsubscribeToken = newsletter.data?.unsubscribe_token;

  function handleNewsletter(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formData = new FormData(event.currentTarget);
    newsletter.mutate({
      email: String(formData.get("email") ?? "").trim(),
      website: String(formData.get("website") ?? ""),
    });
  }

  return (
    <div className="public-site">
      <PublicHeader />
      <main>
        {/* ---------- HERO ---------- */}
        <section className="public-hero">
          <div className="public-hero-photo">
            <div className="public-hero-copy">
              <p className="public-eyebrow">Cultiver · Élever · Partager</p>
              <h1>
                La terre nous
                <br />
                <em>rassemble.</em>
              </h1>
              <p>
                Des savoir-faire vivants, des produits choisis avec soin et une
                entreprise qui grandit au rythme des saisons.
              </p>
              <div className="public-hero-actions">
                <Link className="public-primary-link" href="/produits">
                  Découvrir nos produits <ArrowRight size={17} />
                </Link>
                <Link className="public-hero-story-link" href="/qui-sommes-nous">
                  Notre histoire
                </Link>
              </div>
              <p className="public-hero-meta">
                <Leaf size={12} /> Une aventure portée par le terrain
              </p>
            </div>
            <div className="public-hero-collage" role="group" aria-label="La vie à la ferme, entre élevage et pâturage">
              <figure className="public-hero-image public-hero-image-horses">
                <Image
                  alt="Deux chevaux profitent d’un pré au soleil."
                  fill
                  priority
                  quality={90}
                  sizes="(max-width: 600px) 100vw, (max-width: 1100px) 92vw, 36vw"
                  src="/images/mamari-hero-horses.png"
                />
                <figcaption>Au rythme des saisons</figcaption>
              </figure>
              <figure className="public-hero-image public-hero-image-pasture">
                <Image
                  alt="Des animaux se reposent dans un pré ensoleillé."
                  fill
                  quality={85}
                  sizes="(max-width: 600px) 33vw, (max-width: 820px) 30vw, 18vw"
                  src="/images/mamari-hero-pasture.png"
                />
                <figcaption>La vie au pré</figcaption>
              </figure>
              <figure className="public-hero-image public-hero-image-cows">
                <Image
                  alt="Deux vaches dans un pâturage."
                  fill
                  quality={85}
                  sizes="(max-width: 600px) 33vw, (max-width: 820px) 30vw, 20vw"
                  src="/images/mamari-hero-cows.png"
                />
                <figcaption>Au plus près du vivant</figcaption>
              </figure>
              <figure className="public-hero-image public-hero-image-chickens">
                <Image
                  alt="Une poule et son élevage en plein air."
                  fill
                  quality={85}
                  sizes="(max-width: 600px) 33vw, (max-width: 820px) 30vw, 18vw"
                  src="/images/mamari-hero-chickens.png"
                />
                <figcaption>La ferme en mouvement</figcaption>
              </figure>
            </div>
          </div>
        </section>

        {/* ---------- STATS ---------- */}
        <section className="public-values-strip" aria-label="Les valeurs Mamari">
          <div>
            <span className="public-values-icon"><Sprout size={19} /></span>
            <p><strong>La terre</strong><small>Notre premier repère</small></p>
          </div>
          <div>
            <span className="public-values-icon"><Wheat size={19} /></span>
            <p><strong>Le savoir-faire</strong><small>Apprendre, chaque jour</small></p>
          </div>
          <div>
            <span className="public-values-icon"><Users size={19} /></span>
            <p><strong>Le lien humain</strong><small>Avancer ensemble</small></p>
          </div>
        </section>

        {/* ---------- ACTIVITÉS ---------- */}
        <section className="public-section public-activities" id="activites">
          <div className="public-section-heading">
            <div>
              <p className="public-eyebrow">Ce qui nous anime</p>
              <h2>Des activités qui prennent racine.</h2>
            </div>
            <p>
              De la préparation des cultures à la valorisation des récoltes,
              chaque activité participe à une même ambition.
            </p>
          </div>
          <div className="public-bento">
            <article className="public-bento-tile public-bento-agri">
              <Image alt="" fill quality={85} sizes="(max-width: 900px) 100vw, 50vw" src="/images/mamari-survey.png" />
              <div className="public-bento-copy">
                <span><Wheat size={21} /></span>
                <h3>Agriculture</h3>
                <p>Des parcelles suivies avec attention et des cultures au rythme des saisons.</p>
              </div>
            </article>
            <article className="public-bento-tile public-bento-livestock">
              <Image alt="" fill quality={85} sizes="(max-width: 900px) 50vw, 25vw" src="/images/mamari-hero-cows.png" />
              <div className="public-bento-copy">
                <span><Sprout size={21} /></span>
                <h3>Élevage</h3>
                <p>Des élevages conduits avec soin, au cœur d&apos;une exploitation vivante.</p>
              </div>
            </article>
            <article className="public-bento-tile public-bento-products">
              <span><Tractor size={21} /></span>
              <h3>Productions</h3>
              <p>Des produits sélectionnés et préparés pour rejoindre votre quotidien.</p>
            </article>
            <Link className="public-bento-tile public-bento-shop" href="/produits">
              <small>La boutique</small>
              <strong>Découvrir les produits</strong>
              <span><ArrowRight size={20} /></span>
            </Link>
          </div>
        </section>

        {/* ---------- HISTOIRE ---------- */}
        <section className="public-section public-story" id="histoire">
          <div className="public-story-copy">
            <p className="public-eyebrow">Qui sommes-nous ?</p>
            <h2>Une histoire qui se construit sur le terrain.</h2>
            <p>
              Mamari grandit au fil du travail, des apprentissages et des rencontres.
              Au cœur de cette aventure : le respect de la terre, le goût du travail
              bien fait et l&apos;envie de bâtir quelque chose qui ait du sens.
            </p>
            <Link className="public-text-link" href="/qui-sommes-nous">
              Découvrir notre histoire <ArrowRight size={15} />
            </Link>
          </div>
          <div className="public-story-visual">
            <Image
              alt="Un membre de l’équipe observe une parcelle et prend des notes sur le terrain."
              fill
              quality={90}
              sizes="(max-width: 900px) 90vw, 45vw"
              src="/images/mamari-field-work.png"
            />
            <div className="public-story-badge">
              <Leaf size={18} />
              <div>
                <strong>Au plus près du terrain</strong>
                <span>Le travail, à hauteur d&apos;humain</span>
              </div>
            </div>
          </div>
        </section>

        <section className="public-section public-home-history">
          <div className="public-home-history-copy">
            <p className="public-eyebrow">L&apos;aventure Mamari</p>
            <h2>Une aventure qui a pris racine.</h2>
            <p>
              Mamari cultive bien plus que des produits : un lien de confiance
              avec la terre et celles et ceux qui la travaillent. Chaque saison
              rappelle l&apos;importance du rythme juste et du travail bien fait.
            </p>
            <ol className="public-home-history-timeline">
              <li>
                <span>La terre</span>
                <div>
                  <strong>L&apos;agriculture au cœur de l&apos;aventure</strong>
                  <p>Le travail de la terre et le respect des saisons nous guident.</p>
                </div>
              </li>
              <li>
                <span>L&apos;élevage</span>
                <div>
                  <strong>Des activités qui grandissent</strong>
                  <p>Une exploitation vivante, attentive au bien-être animal.</p>
                </div>
              </li>
              <li>
                <span>Le partage</span>
                <div>
                  <strong>Des produits plus proches de vous</strong>
                  <p>La boutique prolonge le lien entre Mamari et ses clients.</p>
                </div>
              </li>
            </ol>
            <Link className="public-text-link" href="/produits">
              Découvrir nos produits <ArrowRight size={15} />
            </Link>
          </div>
        </section>

        {/* ---------- PRODUITS VEDETTES ---------- */}
        <section className="public-section public-featured">
          <div className="public-section-heading">
            <div>
              <p className="public-eyebrow">La boutique Mamari</p>
              <h2>Les produits du moment.</h2>
            </div>
            <Link className="public-text-link" href="/produits">
              Tous les produits <ArrowRight size={15} />
            </Link>
          </div>
          {products.isPending ? (
            <p className="store-loading" role="status">Découverte de la boutique…</p>
          ) : products.isError ? (
            <p className="store-feedback store-feedback-error" role="alert">
              {getApiErrorMessage(products.error)}
            </p>
          ) : featuredProducts.length ? (
            <div className="store-product-grid">
              {featuredProducts.map((product) => (
                <StoreProductCard key={product.id} product={product} />
              ))}
            </div>
          ) : (
            <div className="public-products-empty">
              <ShoppingBag size={21} />
              <p>Nos premiers produits arrivent bientôt dans la boutique.</p>
            </div>
          )}
        </section>

        {/* ---------- DÉMARCHE ---------- */}
        <section className="public-section public-process">
          <div className="public-section-heading">
            <div>
              <p className="public-eyebrow">Notre démarche</p>
              <h2>Du champ à votre table.</h2>
            </div>
            <p>Chaque étape est menée avec soin, dans le respect du vivant et des saisons.</p>
          </div>
          <div className="public-process-grid">
            <article>
              <span className="public-process-number">01</span>
              <span className="public-process-icon"><Sprout size={22} /></span>
              <h3>Semer</h3>
              <p>Nous préparons la terre et semons au bon moment.</p>
            </article>
            <article>
              <span className="public-process-number">02</span>
              <span className="public-process-icon"><Wheat size={22} /></span>
              <h3>Cultiver</h3>
              <p>Un suivi quotidien, sans compromis sur la qualité.</p>
            </article>
            <article>
              <span className="public-process-number">03</span>
              <span className="public-process-icon"><Sun size={22} /></span>
              <h3>Récolter</h3>
              <p>À pleine maturité, pour des saveurs authentiques.</p>
            </article>
            <article>
              <span className="public-process-number">04</span>
              <span className="public-process-icon"><Truck size={22} /></span>
              <h3>Partager</h3>
              <p>Livré chez vous, frais et prêt à savourer.</p>
            </article>
          </div>
        </section>

        {/* ---------- VISAGES DE MAMARI ---------- */}
        <section className="public-section public-home-gallery">
          <div className="public-section-heading">
            <div>
              <p className="public-eyebrow">Une aventure humaine</p>
              <h2>Le chemin se fait ensemble.</h2>
            </div>
            <Link className="public-text-link" href="/qui-sommes-nous">
              Rencontrer Mamari <ArrowRight size={15} />
            </Link>
          </div>
          <div className="public-home-gallery-grid">
            <figure className="public-home-gallery-card public-home-gallery-field">
              <Image alt="Travail de suivi des cultures dans une parcelle." fill quality={90} sizes="(max-width: 700px) 100vw, 40vw" src="/images/mamari-survey.png" />
              <figcaption><span>01</span><strong>Être au contact du terrain</strong></figcaption>
            </figure>
            <figure className="public-home-gallery-card">
              <Image alt="Remise d’un certificat de reconnaissance au dirigeant de Mamari." fill quality={90} sizes="(max-width: 700px) 100vw, 30vw" src="/images/mamari-certificate.png" />
              <figcaption><span>02</span><strong>Apprendre et faire ses preuves</strong></figcaption>
            </figure>
            <figure className="public-home-gallery-card">
              <Image alt="Cérémonie de remise de distinctions." fill quality={90} sizes="(max-width: 700px) 100vw, 30vw" src="/images/mamari-recognition.png" />
              <figcaption><span>03</span><strong>Faire grandir une ambition</strong></figcaption>
            </figure>
          </div>
        </section>

        <FaqSection />

        {/* ---------- BANNIÈRE CONTACT ---------- */}
        <section className="public-contact-banner">
          <div>
            <p className="public-eyebrow">L&apos;aventure Mamari</p>
            <h2>Une question ou une envie de collaborer ?</h2>
          </div>
          <Link className="public-secondary-link" href="/contact">
            Écrivez-nous <ChevronRight size={16} />
          </Link>
        </section>

        {/* ---------- NEWSLETTER ---------- */}
        <section className="public-newsletter">
          <div className="public-newsletter-inner">
            <div>
              <p className="public-eyebrow">Rejoignez-nous</p>
              <h2>Recevez des nouvelles du champ.</h2>
              <p>
                Nouveautés, récoltes de saison et recettes : une lettre au rythme
                des saisons, directement dans votre boîte mail.
              </p>
              <div className="public-newsletter-meta">
                <CalendarDays size={14} /> Une lettre par mois · Sans engagement
              </div>
            </div>
            <form className="public-newsletter-form" onSubmit={handleNewsletter}>
              {newsletter.isSuccess ? (
                <div className="public-newsletter-confirmation" role="status">
                  <p className="public-newsletter-success">
                    <Check size={16} />
                    {unsubscribe.isSuccess
                      ? "Votre désinscription est enregistrée."
                      : newsletter.data.already_subscribed
                        ? "Cette adresse est déjà inscrite."
                        : "Votre inscription est enregistrée."}
                  </p>
                  {unsubscribeToken && !unsubscribe.isSuccess ? (
                    <button
                      type="button"
                      className="public-newsletter-unsubscribe"
                      disabled={unsubscribe.isPending}
                      onClick={() => unsubscribe.mutate(unsubscribeToken)}
                    >
                      {unsubscribe.isPending ? "Désinscription…" : "Annuler mon inscription"}
                    </button>
                  ) : null}
                  {unsubscribe.isError ? (
                    <p className="public-form-error" role="alert">{getApiErrorMessage(unsubscribe.error)}</p>
                  ) : null}
                </div>
              ) : (
                <>
                  <label className="public-form-label" htmlFor="newsletter-email">Votre adresse e-mail</label>
                  <input id="newsletter-email" type="email" name="email" autoComplete="email" placeholder="votre@email.com" required aria-label="Votre adresse email" />
                  <input className="public-honeypot" type="text" name="website" tabIndex={-1} autoComplete="off" aria-hidden="true" />
                  <label className="public-consent">
                    <input type="checkbox" required />
                    <span>J’accepte de recevoir les actualités de Mamari. Je pourrai demander le retrait de mon inscription.</span>
                  </label>
                  {newsletter.isError ? (
                    <p className="public-form-error" role="alert">{getApiErrorMessage(newsletter.error)}</p>
                  ) : null}
                  {newsletter.isSuccess ? null : (
                    <button type="submit" disabled={newsletter.isPending}>
                      {newsletter.isPending ? "Enregistrement…" : "S’inscrire"} <ArrowRight size={15} />
                    </button>
                  )}
                  <small className="public-form-note">
                    L’inscription est enregistrée. L’envoi des lettres commencera après configuration du service e-mail.
                  </small>
                </>
              )}
            </form>
          </div>
        </section>
      </main>
      <PublicFooter />
    </div>
  );
}

export function PublicContactPage() {
  const contact = useMutation({
    mutationFn: (submission: {
      full_name: string;
      email: string;
      subject: string;
      message: string;
      website: string;
    }) =>
      apiRequest<{ id: string }>("/public/contact", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...submission, consent: true }),
      }),
  });

  function submitContact(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    contact.mutate(
      {
        full_name: String(data.get("full_name") ?? "").trim(),
        email: String(data.get("email") ?? "").trim(),
        subject: String(data.get("subject") ?? "").trim(),
        message: String(data.get("message") ?? "").trim(),
        website: String(data.get("website") ?? ""),
      },
      { onSuccess: () => form.reset() },
    );
  }

  return (
    <div className="public-site">
      <PublicHeader />
      <main className="public-legal-page">
        <p className="public-eyebrow">Nous contacter</p>
        <h1>Parlons de votre projet.</h1>
        <p className="public-legal-intro">
          Envoyez-nous votre message. Il sera enregistré dans la boîte de réception
          de l’équipe Mamari. Aucun e-mail de réponse automatique n’est envoyé pour le moment.
        </p>
        {contact.isSuccess ? (
          <p className="public-contact-success" role="status">
            <Check size={18} /> Votre message a bien été enregistré. Merci de nous avoir écrit.
          </p>
        ) : (
          <form className="public-contact-form" onSubmit={submitContact}>
            <label>
              <span>Nom complet</span>
              <input autoComplete="name" name="full_name" maxLength={160} minLength={2} required />
            </label>
            <label>
              <span>Adresse e-mail</span>
              <input autoComplete="email" name="email" type="email" maxLength={320} required />
            </label>
            <label>
              <span>Objet</span>
              <input name="subject" maxLength={160} minLength={2} required />
            </label>
            <label>
              <span>Message</span>
              <textarea name="message" rows={6} maxLength={5000} minLength={10} required />
            </label>
            <input className="public-honeypot" type="text" name="website" tabIndex={-1} autoComplete="off" aria-hidden="true" />
            <label className="public-consent">
              <input type="checkbox" required />
              <span>J’accepte que Mamari utilise ces informations pour traiter ma demande.</span>
            </label>
            {contact.isError ? (
              <p className="public-form-error" role="alert">{getApiErrorMessage(contact.error)}</p>
            ) : null}
            <button className="public-primary-link" type="submit" disabled={contact.isPending}>
              {contact.isPending ? "Envoi en cours…" : "Envoyer le message"} <ArrowRight size={16} />
            </button>
          </form>
        )}
      </main>
      <PublicFooter />
    </div>
  );
}

export function PublicLegalPage({ kind }: { kind: "privacy" | "sales" }) {
  const privacy = kind === "privacy";
  return (
    <div className="public-site">
      <PublicHeader />
      <main className="public-legal-page">
        <p className="public-eyebrow">Informations</p>
        <h1>{privacy ? "Confidentialité" : "Conditions de vente"}</h1>
        <p className="public-legal-draft" role="note">
          Brouillon informatif — cette page doit être complétée et validée par l’entreprise
          avant d’être considérée comme une information juridique définitive.
        </p>
        {privacy ? (
          <>
            <h2>Données recueillies</h2>
            <p>
              Lorsque vous utilisez le formulaire de contact ou vous inscrivez à la
              newsletter, Mamari enregistre les informations que vous fournissez afin
              de gérer votre demande ou votre inscription. L’inscription à la newsletter
              repose sur votre consentement et peut être retirée via le lien de
              désinscription disponible après une nouvelle inscription. Pour les
              inscriptions antérieures, vous pouvez demander le retrait via le formulaire
              de contact.
            </p>
            <h2>Destinataires et durée de conservation</h2>
            <p>
              Les demandes sont accessibles aux responsables autorisés de l’espace
              Mamari. Les destinataires, sous-traitants, durées de conservation et
              modalités d’exercice des droits doivent être précisés par l’entreprise
              avant la mise en service définitive.
            </p>
            <h2>Contact et responsable du traitement</h2>
            <p>
              Le nom légal de l’entité, son adresse, l’identité du responsable du
              traitement et les coordonnées de contact restent à compléter par Mamari.
            </p>
          </>
        ) : (
          <>
            <h2>Commandes</h2>
            <p>
              Les commandes en ligne sont transmises à l’équipe Mamari, qui confirme
              leur disponibilité et leurs modalités avant leur préparation. Le détail
              des produits, prix, frais, livraison et moyens de paiement doit être
              confirmé lors de la validation de chaque commande.
            </p>
            <h2>Annulation, livraison et réclamations</h2>
            <p>
              Les règles applicables à l’annulation, à la livraison, aux retours et aux
              réclamations sont à confirmer par l’entreprise et doivent être publiées
              avant d’être présentées comme des engagements contractuels.
            </p>
            <h2>Éditeur</h2>
            <p>
              La dénomination légale, l’adresse, les identifiants d’immatriculation et
              les coordonnées de Mamari restent à fournir par l’entreprise.
            </p>
          </>
        )}
        <Link className="public-text-link" href="/contact">Une question ? Contactez-nous <ArrowRight size={15} /></Link>
      </main>
      <PublicFooter />
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  ABOUT                                                              */
/* ------------------------------------------------------------------ */
export function AboutPage() {
  return (
    <div className="public-site">
      <PublicHeader />
      <main className="public-about">
        <section className="public-about-hero">
          <div className="public-about-hero-copy">
            <p className="public-eyebrow">Qui sommes-nous ?</p>
            <h1>Une histoire de terre, de travail et de liens humains.</h1>
            <p>
              Mamari grandit au fil des saisons, des apprentissages et des
              rencontres. Une aventure agricole portée par une conviction :
              le travail de la terre peut nourrir bien plus que nos assiettes.
            </p>
            <div className="public-about-hero-actions">
              <Link className="public-primary-link" href="/#activites">
                Nos activités <ArrowRight size={16} />
              </Link>
              <Link className="public-about-secondary-link" href="/produits">
                Découvrir la boutique
              </Link>
            </div>
            <span className="public-about-signature">Au rythme de la terre, avec celles et ceux qui la font vivre.</span>
          </div>
          <figure className="public-about-hero-visual">
            <Image
              alt="Un technicien de Mamari observe une parcelle avec un instrument de mesure."
              fill
              priority
              quality={90}
              sizes="(max-width: 900px) 100vw, 48vw"
              src="/images/mamari-survey.png"
            />
            <figcaption>
              <span>Notre histoire</span>
              <strong>Commence au contact du terrain.</strong>
            </figcaption>
          </figure>
        </section>

        <section className="public-about-opening">
          <span aria-hidden="true">“</span>
          <p>
            Faire grandir Mamari, c&apos;est croire qu&apos;avec de la patience,
            du courage et les bonnes personnes à ses côtés, une idée peut
            prendre racine et devenir utile à beaucoup.
          </p>
          <small>La conviction qui nous accompagne</small>
        </section>

        <section className="public-about-human">
          <div className="public-about-human-visual">
            <figure className="public-about-human-portrait">
              <Image
                alt="Portrait d’un membre de l’équipe Mamari."
                fill
                quality={90}
                sizes="(max-width: 800px) 88vw, 38vw"
                src="/images/mamari-portrait.png"
              />
            </figure>
            <figure className="public-about-human-moment">
              <Image
                alt="Un membre de Mamari face à l’horizon."
                fill
                quality={90}
                sizes="(max-width: 800px) 42vw, 18vw"
                src="/images/mamari-team.png"
              />
              <figcaption>Regarder plus loin</figcaption>
            </figure>
          </div>
          <div className="public-about-human-copy">
            <p className="public-eyebrow">Derrière chaque projet, des personnes</p>
            <h2>Une ambition n&apos;a de sens que si elle est partagée.</h2>
            <p>
              Il y a les idées, bien sûr. Mais il y a surtout les personnes qui
              les portent : celles qui apprennent, qui recommencent, qui
              transmettent et qui donnent le meilleur d&apos;elles-mêmes.
            </p>
            <p>
              Mamari, c&apos;est cette énergie humaine mise au service d&apos;un
              projet agricole en mouvement, avec l&apos;envie de faire les choses
              avec sérieux et avec cœur.
            </p>
          </div>
        </section>

        <section className="public-section public-about-values">
          <div className="public-section-heading">
            <div>
              <p className="public-eyebrow">Ce que nous voulons faire grandir</p>
              <h2>Plus qu&apos;une récolte.</h2>
            </div>
            <p>Une façon d&apos;entreprendre attentive à la terre comme aux personnes.</p>
          </div>
          <div className="public-about-values-grid">
            <article>
              <span><Sprout size={21} /></span>
              <h3>Prendre soin du vivant</h3>
              <p>Respecter les saisons, comprendre le terrain et avancer avec attention.</p>
            </article>
            <article>
              <span><Wheat size={21} /></span>
              <h3>Faire les choses avec cœur</h3>
              <p>Apporter du soin à chaque étape, du premier geste au produit partagé.</p>
            </article>
            <article>
              <span><Users size={21} /></span>
              <h3>Grandir ensemble</h3>
              <p>Écouter, apprendre et reconnaître la valeur de chaque contribution.</p>
            </article>
          </div>
        </section>

        <section className="public-about-closing">
          <div className="public-about-closing-copy">
            <p className="public-eyebrow">Et la suite s&apos;écrit ensemble</p>
            <h2>Merci de faire une place à Mamari dans votre histoire.</h2>
            <p>
              Chaque rencontre, chaque échange et chaque produit partagé
              prolongent cette aventure.
            </p>
            <Link className="public-primary-link" href="/produits">
              Découvrir nos produits <ArrowRight size={16} />
            </Link>
          </div>
          <div className="public-about-closing-photos">
            <Image
              alt="Un moment de rencontre autour de projets agricoles."
              fill
              quality={90}
              sizes="(max-width: 800px) 88vw, 34vw"
              src="/images/mamari-event.png"
            />
          </div>
        </section>
      </main>
      <PublicFooter />
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  STORE PAGE                                                         */
/*  Recherche, catégories, tri, filtre « en stock », stepper sur les   */
/*  cartes et barre panier flottante.                                  */
/* ------------------------------------------------------------------ */
type SortKey = "featured" | "price-asc" | "price-desc" | "name";

const sortLabels: Record<SortKey, string> = {
  featured: "Notre sélection",
  "price-asc": "Prix croissant",
  "price-desc": "Prix décroissant",
  name: "Nom A–Z",
};

export function StorePage() {
  const { cart, setCart } = useShopCart();
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("all");
  const [sort, setSort] = useState<SortKey>("featured");
  const [inStockOnly, setInStockOnly] = useState(false);
  const products = useQuery({
    queryKey: storeProductsQueryKey,
    queryFn: () => apiRequest<StoreProductPage>("/store/products"),
    retry: false,
  });

  const availableProducts = useMemo(() => products.data?.items ?? [], [products.data]);
  const categories = useMemo(
    () =>
      Array.from(
        new Set(availableProducts.map((product) => product.category).filter((value): value is string => Boolean(value))),
      ).sort((a, b) => a.localeCompare(b, "fr")),
    [availableProducts],
  );
  const visibleProducts = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const filtered = availableProducts.filter(
      (product) =>
        (category === "all" || product.category === category)
        && (!inStockOnly || product.stock_quantity > 0)
        && (!needle
          || `${product.name} ${product.description ?? ""} ${product.category ?? ""}`.toLowerCase().includes(needle)),
    );
    const sorted = [...filtered];
    if (sort === "price-asc") sorted.sort((a, b) => a.price_fcfa - b.price_fcfa);
    if (sort === "price-desc") sorted.sort((a, b) => b.price_fcfa - a.price_fcfa);
    if (sort === "name") sorted.sort((a, b) => a.name.localeCompare(b.name, "fr"));
    return sorted;
  }, [availableProducts, category, inStockOnly, query, sort]);

  const cartCount = Object.values(cart).reduce((sum, quantity) => sum + quantity, 0);
  const cartTotal = availableProducts.reduce(
    (sum, product) => sum + product.price_fcfa * (cart[product.id] ?? 0),
    0,
  );

  function addProduct(product: StoreProduct) {
    setCart((current) => ({
      ...current,
      [product.id]: Math.min((current[product.id] ?? 0) + 1, product.stock_quantity),
    }));
  }

  function removeProduct(product: StoreProduct) {
    setCart((current) => {
      const next = (current[product.id] ?? 0) - 1;
      if (next < 1) {
        const remaining = { ...current };
        delete remaining[product.id];
        return remaining;
      }
      return { ...current, [product.id]: next };
    });
  }

  function resetFilters() {
    setQuery("");
    setCategory("all");
    setInStockOnly(false);
    setSort("featured");
  }

  return (
    <div className="public-site">
      <PublicHeader />
      <main className="public-section store-page">
        <div className="store-page-heading">
          <div>
            <p className="public-eyebrow">La boutique Mamari</p>
            <h1>Des produits choisis avec soin.</h1>
            <p>Parcourez notre sélection et ajoutez vos produits au panier.</p>
          </div>
          <Link className="store-back-link" href="/panier">
            <ShoppingBag size={15} /> Mon panier
            {cartCount ? <span className="store-heading-cart-count">{cartCount}</span> : null}
          </Link>
        </div>

        {products.isPending ? (
          <p className="store-loading" role="status">Chargement des produits…</p>
        ) : products.isError ? (
          <div className="store-feedback store-feedback-error" role="alert">
            {getApiErrorMessage(products.error)}
          </div>
        ) : availableProducts.length ? (
          <div className="store-layout store-catalog-layout">
            <section aria-label="Produits disponibles" className="store-catalog store-catalog-full">
              <div className="store-toolbar">
                <label className="store-search">
                  <Search size={17} aria-hidden="true" />
                  <span className="visually-hidden">Rechercher un produit</span>
                  <input
                    type="search"
                    value={query}
                    placeholder="Rechercher un produit…"
                    onChange={(event) => setQuery(event.target.value)}
                  />
                </label>
                {categories.length ? (
                  <div className="store-chips" role="group" aria-label="Catégories">
                    <button className="store-chip" type="button" aria-pressed={category === "all"} onClick={() => setCategory("all")}>
                      Tout
                    </button>
                    {categories.map((value) => (
                      <button
                        className="store-chip"
                        key={value}
                        type="button"
                        aria-pressed={category === value}
                        onClick={() => setCategory(value)}
                      >
                        {value}
                      </button>
                    ))}
                  </div>
                ) : null}
                <div className="store-toolbar-end">
                  <label className="store-toggle">
                    <input type="checkbox" checked={inStockOnly} onChange={(event) => setInStockOnly(event.target.checked)} />
                    <span>En stock</span>
                  </label>
                  <label className="store-sort">
                    <span className="visually-hidden">Trier les produits</span>
                    <select value={sort} onChange={(event) => setSort(event.target.value as SortKey)}>
                      {(Object.keys(sortLabels) as SortKey[]).map((key) => (
                        <option key={key} value={key}>{sortLabels[key]}</option>
                      ))}
                    </select>
                  </label>
                </div>
              </div>
              <p className="store-results-count" role="status">
                {visibleProducts.length} produit{visibleProducts.length > 1 ? "s" : ""}
              </p>
              {visibleProducts.length ? (
                <div className="store-product-grid">
                  {visibleProducts.map((product) => (
                    <StoreProductCard
                      key={product.id}
                      product={product}
                      quantity={cart[product.id] ?? 0}
                      onAdd={addProduct}
                      onRemove={removeProduct}
                    />
                  ))}
                </div>
              ) : (
                <div className="public-products-empty">
                  <Search size={22} />
                  <p>Aucun produit ne correspond à votre recherche.</p>
                  <button className="store-reset" type="button" onClick={resetFilters}>
                    Réinitialiser les filtres
                  </button>
                </div>
              )}
            </section>
          </div>
        ) : (
          <div className="public-products-empty">
            <ShoppingBag size={22} />
            <p>La boutique prépare ses premiers produits. Revenez nous voir bientôt.</p>
          </div>
        )}
      </main>
      {cartCount ? (
        <Link className="store-cartbar" href="/panier">
          <span className="store-cartbar-icon">
            <ShoppingBag size={18} />
            <span>{cartCount}</span>
          </span>
          <span className="store-cartbar-copy">
            <strong>Voir mon panier</strong>
            <small>{formatFcfa(cartTotal)}</small>
          </span>
          <ArrowRight size={16} />
        </Link>
      ) : null}
      <PublicFooter />
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  CART PAGE                                                          */
/* ------------------------------------------------------------------ */
const checkoutSteps = ["Panier", "Coordonnées", "Confirmation"] as const;

export function CartPage() {
  const queryClient = useQueryClient();
  const { cart, setCart } = useShopCart();
  const [step, setStep] = useState(0);
  const [completedOrder, setCompletedOrder] = useState<StoreOrder | null>(null);
  const [deliveryAddressOverride, setDeliveryAddressOverride] = useState<string | null>(null);
  const products = useQuery({
    queryKey: storeProductsQueryKey,
    queryFn: () => apiRequest<StoreProductPage>("/store/products"),
    retry: false,
  });
  const profile = useQuery({
    queryKey: ["auth", "me"],
    queryFn: () => apiRequest<UserProfile>("/auth/me"),
    retry: false,
  });
  const customerProfile = useQuery({
    queryKey: ["store", "my-profile"],
    queryFn: () => apiRequest<StoreCustomerProfile>("/store/my-profile"),
    enabled: profile.data?.customer_account === true,
    retry: false,
  });
  const deliveryAddress = deliveryAddressOverride ?? customerProfile.data?.address ?? "";
  const checkout = useMutation({
    mutationFn: (data: {
      delivery_address?: string;
      items: { product_id: string; quantity: number }[];
    }) => apiRequest<StoreOrder>("/store/orders", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    }),
    onSuccess: async (order) => {
      setCart({});
      setCompletedOrder(order);
      setStep(2);
      await queryClient.invalidateQueries({ queryKey: storeProductsQueryKey });
    },
  });

  const availableProducts = products.data?.items ?? [];
  const cartItems = availableProducts
    .filter((product) => cart[product.id])
    .map((product) => ({
      product,
      quantity: cart[product.id],
    }));
  const itemCount = cartItems.reduce((sum, item) => sum + item.quantity, 0);
  const hasUnavailableItems = cartItems.some(
    ({ product, quantity }) => quantity > product.stock_quantity,
  );
  const total = cartItems.reduce(
    (sum, item) => sum + item.product.price_fcfa * item.quantity,
    0,
  );

  function changeQuantity(product: StoreProduct, adjustment: number) {
    setCart((current) => {
      const next = (current[product.id] ?? 0) + adjustment;
      if (next < 1) {
        const remaining = { ...current };
        delete remaining[product.id];
        return remaining;
      }
      return { ...current, [product.id]: Math.min(next, product.stock_quantity) };
    });
  }

  function removeLine(product: StoreProduct) {
    setCart((current) => {
      const remaining = { ...current };
      delete remaining[product.id];
      return remaining;
    });
  }

  function submitOrder(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formData = new FormData(event.currentTarget);
    checkout.mutate({
      delivery_address: String(formData.get("delivery_address") ?? "") || undefined,
      items: cartItems.map(({ product, quantity }) => ({
        product_id: product.id,
        quantity,
      })),
    });
  }

  return (
    <div className="public-site">
      <PublicHeader />
      <main className="public-section store-page cart-page">
        <div className="store-page-heading">
          <div>
            <p className="public-eyebrow">Votre sélection Mamari</p>
            <h1>{step === 2 ? "Merci pour votre commande." : "Votre panier."}</h1>
            <p>Votre commande en quelques étapes, sans paiement en ligne.</p>
          </div>
          {step < 2 ? (
            <Link className="store-back-link" href="/produits">
              <ArrowLeft size={15} /> Continuer mes achats
            </Link>
          ) : null}
        </div>

        <nav className="checkout-progress" aria-label="Étapes de commande">
          {checkoutSteps.map((label, index) => {
            const isCurrent = step === index;
            const isComplete = step > index;
            const canNavigateBack = index < step && index < 2;
            return (
              <button
                key={label}
                className={`checkout-progress-step${isCurrent ? " is-current" : ""}${isComplete ? " is-complete" : ""}`}
                type="button"
                aria-current={isCurrent ? "step" : undefined}
                disabled={!canNavigateBack}
                onClick={() => setStep(index)}
              >
                <span>{isComplete ? <Check size={15} /> : index + 1}</span>
                <strong>{label}</strong>
              </button>
            );
          })}
        </nav>

        {products.isPending && step < 2 ? (
          <p className="store-loading" role="status">Chargement de votre panier…</p>
        ) : products.isError && step < 2 ? (
          <div className="store-feedback store-feedback-error" role="alert">
            {getApiErrorMessage(products.error)}
          </div>
        ) : step === 2 && completedOrder ? (
          <section className="checkout-complete">
            <span className="checkout-complete-icon"><Check size={27} /></span>
            <p className="public-eyebrow">Commande transmise</p>
            <h2>Merci, {completedOrder.customer_name} !</h2>
            <p>
              Votre demande <strong>{completedOrder.reference}</strong> est bien reçue.
              Notre équipe vous contactera au {completedOrder.customer_phone} pour confirmer
              la disponibilité et les modalités de règlement.
            </p>
            <div className="checkout-complete-summary">
              <span>{completedOrder.items.reduce((sum, item) => sum + item.quantity, 0)} article(s)</span>
              <strong>{formatFcfa(completedOrder.amount_fcfa)}</strong>
            </div>
            <Link className="button-primary checkout-home-link" href="/produits">
              Retour à la boutique <ArrowRight size={16} />
            </Link>
            <Link className="checkout-account-link" href="/mon-compte">
              Suivre ma commande <ArrowRight size={15} />
            </Link>
          </section>
        ) : !cartItems.length ? (
          <section className="checkout-empty">
            <span><ShoppingBag size={24} /></span>
            <h2>Votre panier est vide.</h2>
            <p>Choisissez quelques produits dans notre boutique pour commencer votre commande.</p>
            <Link className="button-primary checkout-home-link" href="/produits">
              Découvrir les produits <ArrowRight size={16} />
            </Link>
          </section>
        ) : step === 0 ? (
          <section className="checkout-step-panel" aria-labelledby="checkout-cart-title">
            <div className="checkout-step-heading">
              <div>
                <p className="public-eyebrow">Étape 1 sur 3</p>
                <h2 id="checkout-cart-title">Vérifiez votre panier</h2>
                <p>{itemCount} article(s) sélectionné(s)</p>
              </div>
              <ShoppingBag size={22} />
            </div>
            <div className="checkout-cart-layout">
              <div className="checkout-cart-main">
                <ul className="checkout-cart-list">
                  {cartItems.map(({ product, quantity }) => (
                    <li className="checkout-cart-item" key={product.id}>
                      <ProductImage product={product} className="checkout-product-image" />
                      <div className="checkout-cart-product-copy">
                        {product.category ? <span className="store-product-category">{product.category}</span> : null}
                        <h3>{product.name}</h3>
                        <p>{formatFcfa(product.price_fcfa)} / {product.unit}</p>
                      </div>
                      <div className="store-quantity">
                        <button type="button" aria-label={`Retirer une unité de ${product.name}`} onClick={() => changeQuantity(product, -1)}>
                          <Minus size={13} />
                        </button>
                        <span>{quantity}</span>
                        <button
                          type="button"
                          aria-label={`Ajouter une unité de ${product.name}`}
                          disabled={quantity >= product.stock_quantity}
                          onClick={() => changeQuantity(product, 1)}
                        >
                          <Plus size={13} />
                        </button>
                      </div>
                      <strong className="checkout-line-total">
                        {formatFcfa(product.price_fcfa * quantity)}
                      </strong>
                      <button
                        className="checkout-remove"
                        type="button"
                        aria-label={`Retirer ${product.name} du panier`}
                        onClick={() => removeLine(product)}
                      >
                        <Trash2 size={16} />
                      </button>
                    </li>
                  ))}
                </ul>
                <button className="checkout-clear" type="button" onClick={() => setCart({})}>
                  Vider le panier
                </button>
              </div>
              <aside className="checkout-summary">
                <h3>Résumé</h3>
                {hasUnavailableItems ? (
                  <p className="checkout-stock-warning" role="alert">
                    Un stock a changé. Ajustez les quantités avant de continuer.
                  </p>
                ) : null}
                <div><span>Sous-total ({itemCount} article(s))</span><strong>{formatFcfa(total)}</strong></div>
                <div><span>Livraison</span><span>À confirmer</span></div>
                <div className="checkout-summary-total"><span>Total estimé</span><strong>{formatFcfa(total)}</strong></div>
                <button className="button-primary checkout-next-button" type="button" disabled={hasUnavailableItems} onClick={() => setStep(1)}>
                  Passer aux coordonnées <ArrowRight size={16} />
                </button>
                <p><ShieldCheck size={14} /> Aucun paiement demandé à cette étape.</p>
              </aside>
            </div>
          </section>
        ) : (
          <section className="checkout-step-panel checkout-details-panel" aria-labelledby="checkout-details-title">
            <div className="checkout-step-heading">
              <div>
                <p className="public-eyebrow">Étape 2 sur 3</p>
                <h2 id="checkout-details-title">Où pouvons-nous vous joindre ?</h2>
                <p>Nous vous recontacterons pour confirmer votre commande.</p>
              </div>
              <span className="checkout-details-count">{itemCount} article(s) · {formatFcfa(total)}</span>
            </div>
            <div className="checkout-details-layout">
              {profile.isPending ? (
                <p className="store-loading" role="status">Vérification de votre compte…</p>
              ) : profile.isError &&
                !(profile.error instanceof ApiError && profile.error.status === 401) ? (
                <div className="store-feedback store-feedback-error" role="alert">
                  <p>{getApiErrorMessage(profile.error)}</p>
                  <button className="button-secondary" type="button" onClick={() => void profile.refetch()}>
                    Réessayer
                  </button>
                </div>
              ) : profile.data?.customer_account ? (
                <form className="checkout-customer-form" onSubmit={submitOrder}>
                  <p className="customer-checkout-greeting">
                    Connecté en tant que <strong>{customerProfile.data?.full_name ?? profile.data.full_name}</strong>
                    {customerProfile.data?.phone ? <> · Téléphone : <strong>{customerProfile.data.phone}</strong></> : null}
                  </p>
                  {customerProfile.isError ? (
                    <p className="auth-error" role="alert">
                      Impossible de charger votre adresse enregistrée. {getApiErrorMessage(customerProfile.error)}
                    </p>
                  ) : null}
                  <label className="auth-field">
                    <span>Adresse ou indications <small>(facultatif)</small></span>
                    <textarea
                      maxLength={500}
                      name="delivery_address"
                      onChange={(event) => setDeliveryAddressOverride(event.target.value)}
                      rows={3}
                      value={deliveryAddress}
                    />
                  </label>
                  {checkout.isError ? (
                    <p className="auth-error checkout-form-error" role="alert">
                      {getApiErrorMessage(checkout.error)}
                    </p>
                  ) : null}
                  <div className="checkout-form-actions">
                    <button className="button-secondary" type="button" onClick={() => setStep(0)}>
                      <ArrowLeft size={15} /> Retour au panier
                    </button>
                    <button className="button-primary" disabled={checkout.isPending} type="submit">
                      {checkout.isPending ? <LoaderCircle className="auth-spinner" size={16} /> : null}
                      {checkout.isPending ? "Envoi en cours…" : "Confirmer la commande"}
                      {!checkout.isPending ? <ArrowRight size={16} /> : null}
                    </button>
                  </div>
                  <p className="store-payment-note">
                    Aucun paiement en ligne. Le règlement sera organisé avec notre équipe.
                  </p>
                </form>
              ) : (
                <div className="customer-checkout-auth">
                  <ShoppingBag size={24} />
                  <h3>Connectez-vous pour commander</h3>
                  <p>Votre compte vous permettra aussi de retrouver vos achats et de suivre chaque commande.</p>
                  <div className="checkout-form-actions">
                    <Link className="button-secondary" href="/produits">Retour au panier</Link>
                    <Link className="button-primary" href="/register?next=%2Fpanier">
                      Créer un compte <ArrowRight size={15} />
                    </Link>
                  </div>
                  <p className="auth-switch">
                    Vous avez déjà un compte ? <Link href="/login?next=%2Fpanier">Se connecter</Link>
                  </p>
                </div>
              )}
              <aside className="checkout-summary checkout-details-summary">
                <h3>Votre sélection</h3>
                {cartItems.map(({ product, quantity }) => (
                  <div className="checkout-summary-product" key={product.id}>
                    <span>{quantity} × {product.name}</span>
                    <strong>{formatFcfa(product.price_fcfa * quantity)}</strong>
                  </div>
                ))}
                <div className="checkout-summary-total"><span>Total estimé</span><strong>{formatFcfa(total)}</strong></div>
                <p><ShieldCheck size={14} /> Vous pourrez confirmer les détails avec notre équipe.</p>
              </aside>
            </div>
          </section>
        )}
      </main>
      <PublicFooter />
    </div>
  );
}