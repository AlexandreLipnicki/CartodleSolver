# Catalogue français et performances

## Source retenue et portée

Source : [TCGdex / cards-database](https://github.com/tcgdex/cards-database), commit `4199850a6af49665db0080fa2bb9ef751750a406`, licence MIT conservée dans `TCGDEX-LICENSE.txt`. Le dépôt officiel est multilingue, couvre des séries anciennes et modernes, des promotions et Pokémon TCG Pocket. La compilation utilise uniquement les impressions avec un champ `name.fr` réellement présent ; aucune traduction n’est inventée.

Comparaison des sources effectivement vérifiées :

| Source | Constat | Choix |
|---|---|---|
| [TCGdex](https://github.com/tcgdex/cards-database/blob/master/README.md) | Données multilingues, objets cartes/extensions/séries, Pokédex, types JCC, stade, PV, rareté, illustrateur, dates ; export local possible et licence MIT. | Source du catalogue embarqué. |
| [Pokémon TCG Data](https://github.com/PokemonTCG/pokemon-tcg-data/blob/master/README.md) | Le README indique désormais un projet legacy/déprécié et recommande une migration vers Scrydex. Il ne fournit pas dans ce README de garantie de catalogue français exhaustif directement substituable. | Pas de fusion automatique ni de dépendance ajoutée. |
| API publique TCGdex `/v2/fr/cards` | Accès refusé par le proxy réseau de cette machine. | Couverture calculée sur le dépôt officiel cloné, pas sur une réponse API non vérifiée. |

**Il ne s’agit pas d’une garantie de 100 % des cartes françaises jamais publiées.** TCGdex reste une base communautaire. Une absence de nom français peut correspondre à une carte non éditée en français ou à une donnée manquante : ces deux cas ne sont pas confondus avec une traduction fabriquée. Les dates sont celles fournies par TCGdex ; elles ne sont pas certifiées comme dates de commercialisation françaises lorsque la source ne distingue pas les pays.

## Couverture vérifiée

| Mesure | Nombre |
|---|---:|
| Impressions distinctes dans la source internationale | 23 864 |
| Impressions avec un nom français, livrées | **22 242** |
| Extensions représentées dans ce catalogue français | **201** |
| Cartes Pokémon françaises utilisables par le solveur | **18 838** |
| Pokémon avec tous les champs nécessaires à une recommandation validée | **17 724** |
| Pokémon à vérifier, jamais recommandés comme entièrement validés | **1 114** |
| Cartes sans nom français exclues du catalogue français | 1 622 |
| Cartes Pocket incluses, toutes catégories confondues | 2 116 |
| Fragments linguistiques compatibles fusionnés | 9 |
| Fichiers TypeScript invalides | 0 |

Le catalogue contient aussi les Dresseurs et Énergies français, mais le solveur ne les propose pas : ses critères comportent le Pokédex et le stade Pokémon. Les différentes impressions restent distinctes par leur identifiant TCGdex et numéro de collection.

Lacunes parmi les Pokémon français : 806 stades, 237 illustrateurs, 41 noms français d’extension, 4 ensembles de types. Les cartes multi-Pokémon dont le Pokédex n’a pas d’ordre de comparaison vérifié sont aussi à vérifier. Ces groupes peuvent se chevaucher ; leur somme ne donne donc pas le nombre de cartes incomplètes. Aucun Pokédex, PV ou identifiant de rareté Pokémon ne manque dans ce snapshot. Cela ne certifie pas leur exactitude dans le jeu CartoDle.

Le détail par carte est dans `data/catalog.fr.quality.json`. La hiérarchie et les groupes de rareté **propres à CartoDle** restent à confirmer dans `config/rules.json` : une base de cartes ne prouve pas les règles de proximité du jeu.

## Format livré

- `data/catalog.fr.sqlite3` : **24 526 848 octets, soit environ 23,4 Mio**, catalogue sans comptes, sessions, parties ni secrets.
- `data/catalog.fr.manifest.json` : source, commit, langue, couverture, version de schéma et SHA-256 du fichier SQLite.
- `data/catalog.fr.quality.json` : liste explicite des données Pokémon à vérifier.

Le fichier SQLite est portable sous Windows, Linux et macOS. Les tables `series`, `sets`, `cards`, `card_dex` et `card_types` permettent des requêtes SQL locales ; les index couvrent le nom, l’extension, la catégorie/PV, le stade, la rareté, l’illustrateur, la date et la série. Les relations et l’intégrité SQLite sont vérifiées lors de la génération. Les tables de relation ont des clés composées sans ROWID. `ANALYZE` et `VACUUM` préparent le fichier final.

Un payload JSON compact par carte conserve l’objet utilisé par l’interface, en plus des colonnes SQL pour les recherches. Cette duplication limitée évite de multiplier les jointures et transformations à chaque affichage. Les textes d’attaques et traductions inutiles à la résolution ne sont pas embarqués ; les noms français et anglais servent à reconnaître les captures.

Au premier lancement, l’empreinte et l’intégrité sont vérifiées puis les cartes sont copiées en transaction, par lots, dans la base utilisateur `storage/cartosolver.sqlite3`. Le catalogue distribué reste en lecture seule. Au prochain lancement, une empreinte inchangée évite le réimport. Une nouvelle version est appliquée sans supprimer les parties ; les impressions retirées restent disponibles pour lire les historiques, mais quittent les candidats actifs. Après une mise à jour importante, démarrez une nouvelle partie si le jeu a aussi changé de référentiel.

Ne remplacez pas la base `storage/cartosolver.sqlite3` par le catalogue fourni : elle contient les sessions et une structure applicative différente. Pour restaurer l’ensemble, gardez bien les fichiers SQLite **et** manifeste de la même version.

## Optimisations en cours de partie

1. Chargement des payloads sans créer une entité ORM par carte ; cache du catalogue en mémoire.
2. Vue Pokémon active construite une seule fois, en conservant l’archive des anciennes impressions.
3. Index inversés avec **ensembles de bits** : chaque impression occupe un bit. Les indices produisent des masques, puis leurs intersections filtrent les candidats. Les valeurs manquantes restent explicitement compatibles à vérifier ; elles ne sont pas perdues dans un filtre SQL `NULL`.
4. Cache borné à 512 masques, partagé entre parties. Sa clé inclut les règles ; aucun historique ni identité d’utilisateur n’est partagé. Les accès concurrents sont protégés.
5. Textes de recherche normalisés une seule fois, y compris les accents. Recherche limitée aux 40 résultats affichés.
6. Préparation des caractéristiques de chaque carte une seule fois avant les simulations d’entropie, plutôt qu’à chaque paire essai/cible.
7. Construction des index au démarrage, avant la disponibilité du serveur. Le premier joueur ne paie pas leur coût de préparation.
8. Reconstruction du frontend uniquement si ses fichiers sources ont changé ou si la sortie manque.

Aucune dépendance NumPy, pandas, service de recherche, serveur SQL externe ou API Pokémon n’est nécessaire pendant une partie. La base ne contient pas les octets des illustrations : elles utilisent toujours le cache d’images séparé. La lecture des captures reste soumise au temps du modèle Ollama ; ces optimisations ne prétendent pas accélérer son inférence.

## Mesures reproductibles

Depuis la racine, après installation/import :

```bash
python scripts/benchmark.py
```

Le script utilise le même catalogue français, les mêmes indices Lucario, le même échantillonnage de recommandation et sept répétitions par mesure. Il vérifie l’égalité des candidats, de la carte recommandée et de la recherche avant d’afficher les temps. Les références sont les parcours sans index de filtrage, sans caractéristiques précalculées pour l’entropie et sans clés de recherche précalculées, sur les **mêmes cartes**.

Mesure dans cette machine (médianes, charge et matériel variables) :

| Opération | Référence | Optimisé | Gain |
|---|---:|---:|---:|
| Filtrage après un essai | 70,365 ms | 3,274 ms | 21,49 × |
| Choix par entropie | 182,171 ms | 74,857 ms | 2,43 × |
| Recherche « Lucario » | 107,764 ms | 1,968 ms | 54,76 × |

La lecture initiale du catalogue et la préparation des index ne sont pas incluses dans les temps chauds : elles ont pris respectivement environ 537 ms et 255 ms dans cette exécution. Le filtrage mesuré laisse 1 746 candidats validés et 55 cartes à vérifier. Ce cas n’est pas une garantie de temps maximal pour toutes les parties. La recommandation conserve l’échantillonnage déterministe de 160 essais et 512 cibles et ne devient pas une recherche exhaustive globale.

Le premier import dans une base utilisateur vide a pris 2,87 secondes, puis un second lancement a réutilisé le même catalogue sans reconstruction du frontend. Une partie HTTP complète sur le catalogue français a retrouvé Pikachu `base1-58` en quatre essais, avec vérification de l’isolation d’une deuxième session. Il s’agit d’indices structurés générés depuis une cible connue, pas d’une lecture Ollama de capture.

Les tests comparent aussi le moteur indexé au moteur de référence pour les couleurs, flèches, données manquantes, intersections, changements de règles et accès de plusieurs utilisateurs.

## Reconstruire ou actualiser le catalogue

La base livrée suffit pour jouer ; cette procédure est réservée à une mise à jour des données.

1. Récupérez le dépôt TCGdex officiel complet (ou mettez votre copie à jour) et relevez son commit.
2. Dans CartoSolver, installez les outils d’import avec `npm ci` si nécessaire.
3. Exécutez :

```bash
python scripts/build-catalog.py --source "C:/chemin/cards-database"
python -m pytest backend/tests -q
```

Le constructeur utilise une base temporaire et n’accède pas aux sessions existantes. Il parse les littéraux et imports TypeScript sans exécuter les fichiers de données, puis génère SQLite, son manifeste et son rapport qualité. Une collision contradictoire d’identifiants bloque la compilation au lieu d’inventer une carte fusionnée.

Distribuez les trois fichiers `data/catalog.fr.*` ensemble. Arrêtez l’application, sauvegardez `storage/`, mettez à jour les fichiers et relancez. Pour appliquer manuellement : `python -m backend.app.importer --source data/catalog.fr.sqlite3 --force`, puis redémarrez le serveur. Pour importer une autre source brute malgré la présence du catalogue embarqué, passez explicitement son dossier à `--source`.
