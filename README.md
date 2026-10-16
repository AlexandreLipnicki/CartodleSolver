# CartoSolver

Application web de résolution CartoDle : **Nouvelle partie → Lucario → capture → Ctrl+V → prochaine carte**.
React/TypeScript, FastAPI, SQLite et lecture d’images par Ollama. La déduction n’utilise aucun modèle IA.

## Démarrage sur Windows

Prérequis : **Python 3.11+**, **Node.js 22 ou 24 LTS** (npm inclus) et Ollama avec un modèle vision. Le catalogue français SQLite est désormais inclus dans le dépôt. Python et Ollama seuls ne suffisent pas : Node est nécessaire pour construire l’interface ; le parsing TypeScript sert seulement à reconstruire les données sources.

1. Téléchargez la dernière version du dépôt et conservez les fichiers `data/catalog.fr.sqlite3`, `data/catalog.fr.manifest.json` et `data/catalog.fr.quality.json` ensemble. **Aucun téléchargement ni ajout manuel de TCGdex n’est nécessaire.** Le catalogue contient 22 242 cartes avec un nom français, dont 18 838 Pokémon.
2. Copiez `.env.example` en `.env` ; renseignez `CARTO_OLLAMA_MODEL` avec le nom exact d’un de vos modèles vision (`ollama list`). Le modèle par défaut peut être installé avec `ollama pull qwen2.5vl:7b`.
3. Lancez Ollama, puis double-cliquez sur **`LANCER_CARTOSOLVER.bat`**.
4. Attendez la compilation et l’import initial. La fenêtre du navigateur s’ouvre **uniquement lorsque le serveur répond**. L’application s’affiche directement, sans compte ni code d’accès. Le navigateur reçoit automatiquement une session distincte.

Le lanceur prépare `.venv`, installe les dépendances verrouillées, construit l’interface si nécessaire, vérifie la base et démarre un seul serveur qui sert l’interface et l’API. Il garde la véritable erreur visible si une étape échoue. Les lancements suivants conservent la base et les parties. Arrêt : Ctrl+C dans le terminal.

Le catalogue SQLite est commité dans ce dépôt ; les captures et la base de parties ne le sont jamais. Pour auditer la couverture, les données manquantes, les optimisations et la reconstruction du catalogue, consultez [Données et performances](docs/DONNEES_ET_PERFORMANCES.md).

### Linux / macOS

```bash
python3 scripts/run.py
```

Le lanceur Windows est fourni mais **n’a pas été exécuté sur Windows dans cette livraison**. Son programme Python commun a été testé sous Linux.

### Installation explicite et développement

Depuis la racine du dépôt :

```bash
python -m venv .venv
# Windows : .venv\Scripts\activate
# Linux/macOS : source .venv/bin/activate
python -m pip install -r requirements.txt
npm ci
npm --prefix frontend ci
python -m backend.app.importer
npm --prefix frontend run build
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

Pour le rechargement à chaud : backend avec `--reload`, puis `npm --prefix frontend run dev` dans un autre terminal. Le proxy Vite garde l’API sur la même origine. En développement HTTP uniquement, conservez `CARTO_SECURE_COOKIES=false`.

## Utiliser le solveur : accès direct, deux actions

À la première visite, la partie est créée automatiquement.

1. Cliquez sur **Nouvelle partie** pour recommencer. Lucario `xy10-63` apparaît immédiatement dans **Le fil de votre enquête**, avec ses sept résultats en attente. Aucun indice n’est inventé et le filtrage n’est pas modifié à ce stade.
2. Jouez la carte proposée dans CartoDle, copiez sa capture de résultat puis faites **Ctrl+V** sur CartoSolver. La page récupère l’image, le serveur lit les résultats, identifie la carte réellement jouée et utilise ses valeurs visibles comme référence pour la partie, enregistre l’essai et affiche automatiquement la suivante dans le fil. Recommencez avec la nouvelle carte.

Il n’y a aucun formulaire de confirmation, sélection d’impression, saisie manuelle, bouton d’import ou correction à effectuer. Le navigateur n’envoie pas d’essai manuel après la lecture : le serveur enregistre lui-même le résultat et calcule la prochaine carte dans une transaction.

- Le premier essai est **Lucario `xy10-63`, Impact des Destins, 2016**, Métal, 110 PV, Niveau 1, Hitoshi Ariga. La rareté est **Rare Holo**, selon la correction CartoDle fournie par l’utilisateur dans `config/card-overrides.json` (la source TCGdex brute indique Rare).
- L’impression attendue vient de la recommandation persistante, capturée au moment de l’upload. Ollama lit les couleurs, flèches et valeurs affichées ; il ne recherche pas une nouvelle carte dans le catalogue. Le nom et les valeurs lisibles sont contrôlés contre cette impression. L’identité repose sur ce contexte et les éléments visibles : une information absente de l’image ne peut pas être vérifiée visuellement.
- Une capture peut contenir les anciennes lignes : les lignes déjà enregistrées sont ignorées. La proposition sert de contexte par défaut ; une autre carte lisible est également acceptée. Une répétition déjà enregistrée ne consomme pas la nouvelle carte. Deux lectures incompatibles pour la même carte conduisent à demander une capture recadrée, sans formulaire.
- Si la capture est illisible, le nom introuvable ou les indices contradictoires, **rien n’est ajouté**. Un message demande une capture recadrée du dernier résultat. L’essai reste en attente.
- Une seule carte compatible signifie « solution probable » : elle reste à jouer et son résultat peut encore être collé. La partie affiche « carte trouvée » après lecture des sept cases vertes, puis ne propose que Nouvelle partie.
- Les valeurs visibles remplacent les attributs du catalogue pour cet essai et cette partie, y compris dans le filtrage et le fil des essais. Les valeurs absentes utilisent les données connues ; les métadonnées d’une impression ambiguë restent inconnues plutôt que d’être inventées. Les observations sont persistées dans la base de parties, sans modifier le catalogue commun.
- Formats PNG/JPG/WEBP, 8 Mo et 20 mégapixels maximum. Ollama et un modèle vision opérationnels sont nécessaires pour lire les captures.
- L’accès est ouvert à toute personne qui peut joindre l’URL ou l’IP du serveur. Aucun code ni compte n’est demandé, même si une ancienne variable `CARTO_INVITE_CODE` reste dans votre `.env` : elle est ignorée. Chaque navigateur reçoit un cookie de session HttpOnly/SameSite strict de 30 jours. Nouvelle partie ne réinitialise pas les autres visiteurs ; l’essai en attente et le fil reviennent au rechargement.

## Catalogue fourni, import et persistance

Le catalogue français fourni est chargé automatiquement après vérification SHA-256 et de l’intégrité SQLite. Il utilise des tables et index SQL, puis des index en mémoire par ensembles de bits pour la résolution. Les lancements suivants évitent le réimport si son empreinte est inchangée. Une mise à jour du fichier est détectée au démarrage. La base de parties dans `storage/` est conservée séparément.

L’importeur de sources brutes reste disponible si vous passez explicitement un autre dossier avec `--source`. L’importeur parcourt les vrais fichiers TypeScript avec l’AST TypeScript : objets, tableaux, littéraux, concaténation de chaînes et imports relatifs. **Il n’exécute jamais le code du dépôt de données.** Les relations importées déterminent l’extension et la série, y compris les promos ; les noms de dossiers ne servent pas à inventer ces relations.

Les informations françaises sont conservées telles quelles. Un nom français absent reste absent ; un nom anglais peut être affiché explicitement dans les outils de recherche. Les cartes incomplètes sont mises à vérifier. Les cartes multi-Pokémon, dont l’ordre Pokédex serait ambigu, ne sont pas recommandées.

Les fragments linguistiques qui partagent un identifiant sont fusionnés seulement si leurs caractéristiques de résolution sont identiques. Une collision contradictoire annule l’import et préserve la base existante. Les fichiers invalides figurent dans `storage/import-report.json`. Les cartes absentes d’une réindexation sont retirées du catalogue actif mais conservées pour lire les anciens historiques.

Réindexation réservée au propriétaire du serveur, sans route HTTP d’administration :

```bash
python -m backend.app.importer --force
# Ou : python -m backend.app.importer --source "C:/chemin/cards-database" --force
```

Redémarrez ensuite le serveur pour rafraîchir le cache des métadonnées. N’exécutez pas de réindexation pendant des parties actives si vous souhaitez garder les mêmes données de référence.

`storage/cartosolver.sqlite3` conserve cartes, sessions, parties, essais et recommandations. Les contraintes sont recalculées à partir des essais persistants. SQLite utilise WAL et des transactions avec contrôle de version : une analyse issue d’une ancienne version ne peut pas écraser une correction plus récente. Sauvegardez `storage/` **serveur arrêté**, ainsi que `.env` séparément dans un emplacement sécurisé.

Les captures ne sont pas stockées côté serveur. Elles sont redimensionnées au maximum à 2400 pixels et transmises temporairement au modèle. Les analyses en cours sont perdues lors d’un redémarrage ; recollez la capture si nécessaire. Les illustrations TCGdex sont mises en cache dans `storage/images/` ; la résolution utilise uniquement SQLite, sans appel à une API Pokémon externe.

## Règles et limites explicites

- PV : jaune à distance **1 à 20 inclus**, gris **au-delà de 20**, puis intersection avec la direction. Les valeurs réelles de la base sont utilisées, même hors multiples de 10.
- Pokédex : vert exact ; sinon bornes strictes selon les flèches. Aucun seuil jaune inventé.
- Types JCC : ensembles exacts / intersection non exacte / aucune intersection.
- Stade et illustrateur : exact ou différent, sans proximité présumée. Les noms d’artistes sont normalisés sans modifier leur affichage.
- Extension : identifiant exact, même série TCGdex pour jaune, autre série pour gris, puis date de sortie pour la direction. Deux extensions du même jour ne sont pas ordonnées arbitrairement.
- **La correspondance entre séries TCGdex et CartoDle suit votre cahier des charges ; elle n’a pas été vérifiée sur un site CartoDle fourni.** Vous pouvez définir `set_series_overrides` dans `config/rules.json`, ou désactiver `series_proximity_verified` pour ne garder que les contraintes certaines.
- **Aucune hiérarchie de rareté n’a été inventée.** Sans groupes vérifiés, vert impose la rareté exacte et jaune/gris excluent l’exacte ; leur proximité et leur direction restent en attente avec un avertissement visible. Pour activer ces filtres, le propriétaire renseigne `rarity_groups` (rareté TCGdex → groupe) et `rarity_order` (rareté → rang numérique) dans `config/rules.json`, puis redémarre. Ces noms et rangs doivent venir du jeu, pas d’une hiérarchie supposée.
- Les cartes qui satisfont les contraintes certaines restent recommandables même quand une règle de rareté est en attente, avec l’avertissement affiché. Les **métadonnées manquantes**, elles, interdisent la recommandation validée.
- Le choix de l’essai maximise l’entropie de partitions déterministes. Il est exact jusqu’à 160 essais candidats et 512 cibles ; au-delà, un échantillonnage stable borne le temps de calcul. Il n’est pas garanti globalement optimal.

## Ollama : configuration du propriétaire

Tout est côté serveur, dans `.env` : URL, modèle vision, timeout et concurrence. L’appel utilise `/api/chat`, un schéma JSON et une température nulle, puis une validation Pydantic stricte. La sortie du modèle ne décide jamais du filtrage. Un timeout, une réponse invalide, une capture illisible ou un modèle absent laissent l’essai en attente et demandent une nouvelle capture après résolution du problème. Aucune confirmation manuelle n’est proposée.

File limitée à 8 analyses, une analyse active par session, concurrence Ollama par défaut 1. Les requêtes HTTP restent disponibles pendant les lectures. Utilisez **un seul worker Uvicorn**, car la file et les limites sont en mémoire. Il ne s’agit pas d’un service distribué.

## Accès par IP ou URL

Le lanceur écoute par défaut sur `0.0.0.0:8000`. Sur le même réseau local, ouvrez `http://IP_DU_PC:8000` depuis un autre appareil, après avoir autorisé l’application dans le pare-feu Windows si nécessaire. L’IP du PC est visible avec `ipconfig`. Pour HTTP, conservez `CARTO_SECURE_COOKIES=false`. Pour limiter volontairement le service à votre PC, utilisez `python scripts/run.py --host 127.0.0.1`.

### Option A : PC Windows + Cloudflare Tunnel

Le PC conserve l’application, SQLite et Ollama. Vos amis n’installent rien. Le PC doit rester allumé et connecté ; la latence dépend de votre modèle et de la connexion montante.

1. Créez un tunnel nommé dans Cloudflare et associez un domaine que vous contrôlez à votre application. Configurez sa destination comme le service HTTP local sur le port 8000. Installez le connecteur `cloudflared` selon les instructions officielles Cloudflare.
2. Définissez `CARTO_SECURE_COOKIES=true`, `CARTO_ALLOWED_ORIGINS=https://cartosolver.votre-domaine.fr` dans `.env`. Redémarrez l’application. Avec les cookies Secure, utilisez l’URL HTTPS pour accéder à votre session.
3. Conservez HTTPS sur le domaine public. Aucune règle Cloudflare Access n’est nécessaire pour ce mode ouvert ; une éventuelle protection configurée auparavant dans Cloudflare doit être retirée dans Cloudflare si vous voulez aussi supprimer son écran d’accès.
4. Partagez l’URL : les visiteurs arrivent directement sur l’application, chacun avec sa propre partie.

Aucune redirection de port sur la box. **Ne créez jamais de tunnel vers le port 11434.** Ollama doit rester lié à localhost. L’application ne demande aucune authentification. Ollama reste un service interne, sans port public.

Alternative : Tailscale Serve fournit une URL HTTPS privée aux membres de votre tailnet, avec ACL limitées. C’est simple, mais les amis doivent installer Tailscale et rejoindre le réseau : cela ne correspond donc pas au besoin « navigateur seulement » aussi bien qu’un tunnel public vers l’application.

### Option B : VPS + Ollama sur le PC

Le VPS peut servir l’interface en permanence mais les analyses restent dépendantes du PC. Cette architecture ajoute des mises à jour système, un reverse proxy HTTPS, les sauvegardes et un lien privé à maintenir.

Utilisez Tailscale entre le VPS et le PC. Autorisez uniquement l’identité du VPS vers un **proxy privé authentifié par les identités/ACL Tailscale**, qui relaie vers Ollama localhost. Tailscale Serve peut fournir ce relais HTTPS dans le tailnet ; configurez `CARTO_OLLAMA_URL` sur cette adresse privée. N’utilisez ni Funnel public ni une règle autorisant tout le tailnet. Vérifiez depuis le VPS que seul ce service privé est joignable. N’exposez pas 11434 sur une interface publique, et n’ouvrez pas ce port dans le pare-feu du VPS ou de la box.

Le reverse proxy public expose seulement l’application, impose HTTPS et limite le corps des requêtes à 9 Mo (marge multipart comprise). Configurez l’origine publique exacte et les cookies Secure. Le port Uvicorn reste en boucle locale. Cette option est documentée mais pas provisionnée par ce projet.

### Docker Compose (facultatif)

```bash
docker compose up --build -d
docker compose exec ollama ollama pull qwen2.5vl:7b
```

Conservez le catalogue fourni dans `data/` avant le démarrage. Cette variante utilise **son propre Ollama dans Docker**, sans port publié, et ne remplace pas celui déjà installé sur Windows. Le modèle tourne sur CPU par défaut ; l’accélération GPU dépend de votre hôte et n’est pas configurée automatiquement. Les volumes nommés conservent SQLite et les modèles. Le port applicatif 8000 est publié pour l’accès par IP ; aucun port Ollama n’est publié. Ne lancez pas `docker compose down -v` si vous voulez garder ces données. La configuration Compose a été validée (`docker compose config`). La construction a été tentée mais reste bloquée dans le moteur Docker de cette machine : échec DNS vers `deb.debian.org`. Son exécution complète n’a donc pas été validée ici.

## Tests et vérifications

```bash
python -m pytest backend/tests -q
npm --prefix frontend run build
# Serveur déjà lancé, dépendances npm de la racine installées :
# Linux si Chromium est installé à cet emplacement :
node scripts/browser-check.mjs
# Parcours complet isolé, serveur HTTP Ollama simulé et vraie base française :
python scripts/test-automatic-ui.py
# Autre emplacement : définir CHROMIUM_PATH ; le test ouvre Chromium en headless.
```

`TESTER_CARTOSOLVER.bat` lance les tests Python et la compilation. Le test navigateur utilise une base locale de développement et **crée une partie de test** ; ne le lancez pas contre une base partagée en production. Le contrôle navigateur simple simule une réponse serveur. `scripts/test-automatic-ui.py` démarre une application et une base temporaires, puis fait jouer une partie complète par collage natif avec un serveur HTTP Ollama simulé. Ce test ne modifie pas vos parties et ne valide pas la vision réelle du modèle.

**Les tests automatisés couvrent aussi les corrections lues dans les captures, leur persistance et leur isolation entre parties.** Une simulation sur le catalogue complet a également retrouvé Pikachu `base1-58` en quatre essais via les routes HTTP du catalogue français, sans éliminer la cible à aucune étape. Ce cas ne garantit pas un nombre d’essais universel.

Vérifications exécutées dans cette machine : import complet de TCGdex, import d’une fixture officielle Lucario vers SQLite, règles et intersections, déduplication, contradictions atomiques, corrections, versions concurrentes, accès anonyme sans code, réutilisation de session, isolation de deux navigateurs à la même IP, routes HTTP, attente immédiate de Lucario, enregistrement automatique côté serveur, refus des mauvaises cartes et valeurs, anciennes lignes et doublons, distinction solution probable/carte trouvée, validation stricte Ollama avec transport simulé, refus d’uploads invalides, build TypeScript/Vite, démarrage réel et contrôle du parcours dans Chromium desktop/mobile.

**Non validés ici : lecture d’une vraie capture par votre modèle Ollama, lancement Windows natif et déploiement distant.** Aucun exemple de capture CartoDle n’a été fourni. Les illustrations sont bloquées par la politique réseau de cette machine tant que `assets.tcgdex.net` n’est pas autorisé ; le remplacement visuel a été vérifié. Le code de téléchargement et de cache est couvert avec un transport simulé.

## Provenance

Données auditées : [`tcgdex/cards-database`](https://github.com/tcgdex/cards-database), commit `4199850a6af49665db0080fa2bb9ef751750a406`. Source internationale : 23 864 cartes. Catalogue livré : **22 242 cartes avec un nom français, 18 838 Pokémon, 201 extensions**, 9 fragments linguistiques fusionnés, aucun fichier invalide. Les 1 622 cartes sans nom français ne sont pas incluses dans le catalogue français. Sur les Pokémon français, 17 724 sont entièrement renseignés et 1 114 restent à vérifier. Détails et mesures : [Données et performances](docs/DONNEES_ET_PERFORMANCES.md).

Les fichiers officiels utilisés dans les tests et les traductions conservent la licence TCGdex dans `docs/TCGDEX-LICENSE.txt`. CartoSolver n’est affilié ni à TCGdex ni à Pokémon. Les illustrations restent la propriété de leurs ayants droit.
