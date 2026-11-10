# Mamari

Plateforme métier modulaire pour piloter une entreprise agricole et ses activités.

## Architecture

```text
apps/
  api/       API REST FastAPI (Python, SQLAlchemy, Alembic)
  web/       Interface Next.js App Router (TypeScript)
```

Le produit démarre comme un monolithe modulaire : les domaines partagent une
API et une base PostgreSQL, mais gardent leurs propres routes, schémas et règles
métier. Toute donnée appartenant à un client devra être rattachée à une
organisation. Les frontières multi-tenant et les permissions doivent être
appliquées côté API, jamais uniquement dans l’interface.

### Frontend

- `apps/web/src/app/` : routes et layouts App Router.
- `apps/web/src/features/` : fonctionnalités par domaine métier.
- `apps/web/src/components/` : shell applicatif et composants partagés.
- TanStack Query est réservé au cache serveur et aux mutations API.
- Zustand est réservé à l’état d’interface partagé.
- Les composants interactifs sont explicitement client ; le rendu serveur
  reste le comportement par défaut.

### Backend

- `apps/api/src/mamari_api/core/` : configuration, base et infrastructure.
- `apps/api/src/mamari_api/api/` : composition/versionnement HTTP.
- `apps/api/src/mamari_api/modules/` : domaines métier isolés.
- Chaque domaine évoluera vers `router`, `schemas`, `service` et `repository`.
- `apps/api/migrations/` : migrations Alembic versionnées.
- `apps/api/tests/` : tests unitaires et d’API.

## Démarrage local

1. Copier `.env.example` vers `.env`, puis renseigner les identifiants réels
   de PostgreSQL dans `DATABASE_URL`. Ce fichier est lu depuis la racine du
   dépôt, même lorsque les commandes sont lancées depuis `apps/api`.
2. Démarrer PostgreSQL : `docker compose up -d db`.
3. Installer l’interface : `npm install`.
4. Lancer Next.js : `npm run dev`.
5. Dans un autre terminal, installer l’API et ses dépendances :

   ```powershell
   py -3.13 -m venv apps\api\.venv
   apps\api\.venv\Scripts\python -m pip install -e "apps\api[dev]"
   ```

6. Depuis la racine du dépôt, appliquer les migrations avant le premier
   démarrage de l’API et après chaque mise à jour qui modifie le schéma :

   ```powershell
   Set-Location apps\api
   .\.venv\Scripts\python.exe -m alembic upgrade head
   ```

   Utiliser le Python du venv est indispensable : la commande globale
   `alembic` peut lancer Conda ou un autre environnement sans les dépendances
   du projet.

7. Démarrer l’API avec ce même environnement :

   ```powershell
   .\.venv\Scripts\python.exe -m uvicorn mamari_api.main:app --app-dir src --reload
   ```

L’interface est disponible sur `http://localhost:3000`, l’API sur
`http://localhost:8000` et sa documentation OpenAPI sur
`http://localhost:8000/docs`. Le tableau de bord agrège les commandes et les récoltes réellement saisies.
Les graphiques Revenus et Production sont indépendants et proposent les modes
courbe, aire et colonnes ; ils restent vides tant qu’aucune donnée correspondante
n’a été enregistrée.

### Accès privé et comptes

- L’espace de travail de l’équipe reste privé. Les clients de la boutique
  peuvent créer leur compte depuis `/register` ou au moment de la commande ;
  le compte est lié à une fiche client de l’organisation de la boutique.
- Une commande boutique exige une session client. La route
  `POST /api/v1/store/orders` utilise la fiche liée au compte connecté et ne
  fait pas confiance à un identifiant client fourni par le navigateur. Les
  commandes restent en attente jusqu’à leur validation par l’équipe. Le client
  ne peut consulter que ses commandes via `GET /api/v1/store/my-orders`.
  L’équipe retrouve les commandes depuis la fiche client et met leur statut à
  jour dans Ventes.
- Au premier accès à une base vide, se connecter avec `mamari` / `passer123m`
  crée l’organisation Mamari et son compte propriétaire. La création ne se
  produit qu’une fois ; les connexions suivantes vérifient le compte existant.
- L’administrateur peut créer des utilisateurs dans Administration. L’API
  `POST /api/v1/organizations/users` exige un compte propriétaire ou
  administrateur, une organisation autorisée et un mot de passe d’au moins
  6 caractères. La page Administration permet aussi de gérer les rôles,
  suspendre/réactiver un accès, enregistrer le téléphone WhatsApp et la photo
  de profil des membres. Les mots de passe sont hachés avec Argon2id.
- `POST /api/v1/auth/login`, `POST /api/v1/auth/logout` et `GET /api/v1/auth/me`
  gèrent les sessions avec un cookie `HttpOnly`. La connexion accepte
  l’identifiant d’équipe ou l’adresse e-mail du compte client.
- Dans Clients, sélectionner le nom d’une fiche affiche ses achats. Les cartes
  d’indicateurs du tableau de bord ouvrent leur définition et leur détail
  mensuel. Les formulaires d’unités utilisent un catalogue commun plutôt qu’une
  saisie libre.
- Les routes de domaine protégées doivent utiliser la dépendance
  `get_current_membership` et exiger l’en-tête `X-Organization-ID`. Les rôles
  disponibles sont `owner`, `admin`, `manager`, `operator` et `reader`.
  Seuls les propriétaires, administrateurs et responsables peuvent gérer les
  données métier des modules ; un employé (`operator`) consulte uniquement les
  opérations qui lui sont attribuées et transmet leur avancement. Le rôle
  `reader` reste en lecture seule.
- Le module Ventes fournit les routes paginées et filtrables
  `GET /api/v1/sales/orders`, l’enregistrement d’une commande par
  `POST /api/v1/sales/orders` et le changement de statut par
  `PATCH /api/v1/sales/orders/{id}/status`. Le tableau de bord agrège les ventes
  non annulées par mois via `GET /api/v1/dashboard/overview?year=2026`.
- Le module Agriculture organise plusieurs fermes, leurs parcelles et leur
  catalogue de cultures. Les campagnes suivent le parcours planification,
  simulation sur la base des hypothèses saisies, lancement, récoltes,
  clôture, commercialisation et archivage. Les dépenses et recettes sont
  rattachées à une ferme et facultativement à une campagne ; les rapports
  agrègent les mouvements réels. Les routes principales sont
  `/api/v1/agriculture/farms`, `/crops`, `/parcels`, `/campaigns`,
  `/harvests` et `/finance/transactions`. Les photos JPEG, PNG et WebP sont
  limitées à 5 Mo et stockées hors de la base ; en production, configurer
  `UPLOAD_DIRECTORY` vers un stockage persistant partagé avec l’API.
- Le module Opérations suit les tâches de l’équipe, avec échéance, priorité,
  responsable, recherche, filtres et états à faire/en cours/terminé/archivé.
  Les employés ne voient que les tâches qui leur sont attribuées et peuvent
  transmettre leur avancement ; une tâche en retard demande une justification.
  Les responsables et administrateurs suivent l’activité, consultent son
  historique et peuvent contacter un collaborateur via WhatsApp. Le tableau se
  rafraîchit automatiquement toutes les 15 secondes (sans connexion WebSocket).
  Les tâches et leurs statistiques sont isolées par organisation via
  `/api/v1/operations`.
- Le module Élevage suit les animaux individuels et les lots, leurs bâtiments,
  photos, soins et échéances, événements de reproduction, productions et
  alimentation. Les bâtiments rattachés à une ferme ajoutent automatiquement
  les coûts aux Finances et les recettes de production aux revenus. Les médias
  privés sont stockés sous `UPLOAD_DIRECTORY` et limités à 5 Mo.
- La boutique estime les frais de livraison à vol d’oiseau depuis les coordonnées
  de référence définies dans `.env` : gratuit jusqu’à 5 km, 1 000 FCFA jusqu’à
  15 km, 2 000 FCFA jusqu’à 30 km, puis tarif à confirmer. Ces seuils sont
  temporaires et doivent être remplacés par l’adresse et les tarifs validés par
  Mamari avant la mise en production. La recherche d’adresse utilise le service
  Nominatim d’OpenStreetMap à la demande (sans autocomplétion).
- La migration `0010_operations_collaborators` ajoute les profils des membres,
  les comptes rendus des tâches et leur historique.
- Avant d’exposer le serveur sur Internet, remplacer `BOOTSTRAP_ADMIN_PASSWORD`
  par un secret propre à l’instance dans `.env`, et définir une clé
  `JWT_SECRET_KEY` unique d’au moins 32 caractères ainsi que les origines de
  confiance dans `CORS_ORIGINS`. Ne pas partager les identifiants par défaut.

### Mise à jour du VPS

Après publication d’une nouvelle version, installer les dépendances, configurer
la clé JWT de production et appliquer les migrations avant de redémarrer l’API :

```bash
cd /opt/mamari
sudo -u mamari git pull --ff-only origin main
sudo -u mamari -H bash -lc 'cd /opt/mamari && npm ci && npm run build'
sudo -u mamari -H bash -lc \
  'cd /opt/mamari && apps/api/.venv/bin/pip install -e apps/api'
```

Si `JWT_SECRET_KEY` n’existe pas encore dans `/opt/mamari/.env`, générer une
clé aléatoire sur le serveur et l’ajouter sans l’afficher :

```bash
if ! sudo grep -qE '^JWT_SECRET_KEY=[^[:space:]]{32,}$' /opt/mamari/.env ||
   sudo grep -qE '^JWT_SECRET_KEY=(development-only-change-before-production|replace-with-a-random-secret-at-least-32-characters)$' /opt/mamari/.env; then
  JWT_SECRET="$(openssl rand -hex 32)"
  printf '\nJWT_SECRET_KEY=%s\n' "$JWT_SECRET" |
    sudo tee -a /opt/mamari/.env >/dev/null
  unset JWT_SECRET
  sudo chmod 640 /opt/mamari/.env
fi
```

Appliquer ensuite les migrations avec la configuration du service, puis
redémarrer :

```bash
sudo -u mamari -H bash -lc \
  'set -a; . /opt/mamari/.env; set +a; cd /opt/mamari/apps/api && .venv/bin/alembic upgrade head'
sudo systemctl restart mamari-api mamari-web
curl -fsS https://mamari.fisafigroupe.com/api/v1/health
```

## Qualité

- `npm run lint` : ESLint frontend.
- `npm run typecheck` : vérification TypeScript.
- `npm run build` : build de production frontend.
- Depuis `apps/api` : `python -m pytest`.
- Les changements de schéma passent par Alembic ; ne pas créer les tables à
  partir des modèles automatiquement au démarrage. La migration
  `0004_agriculture` crée les tables historiques des parcelles et récoltes ;
  `0005_farm_campaign_finance` les rattache aux fermes et cultures, puis ajoute
  les campagnes et mouvements financiers en conservant les données existantes ;
  `0006_parcel_photos` ajoute la métadonnée photo des parcelles ;
  `0007_operations_tasks` ajoute le planning des tâches ;
  `0008_seed_crop_catalog` initialise le catalogue des cultures des organisations
  qui n’en possèdent pas encore ;
  `0009_livestock` ajoute les bâtiments, lots, animaux et événements d’élevage.

## Principes de conception

1. Les agrégats et règles métier appartiennent à leur domaine.
2. Les intégrations inter-domaines passent par des services explicites ; éviter
   les dépendances circulaires.
3. Les listes API sont paginées et leurs filtres explicitement validés.
4. Les dates sont enregistrées en UTC ; les montants utilisent des types
   décimaux et une devise explicite.
5. Les permissions, l’audit et l’isolation des organisations sont vérifiés sur
   chaque opération sensible côté serveur.
6. Les fichiers sont stockés hors base ; PostgreSQL conserve leurs métadonnées.
