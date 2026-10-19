# Raretés Holopocket

Source : six captures du filtre de rareté fournies par l'utilisateur. La transcription des noms et badges est conservée dans `config/holopocket-rarities.json`. Les équivalences TCGdex sont appliquées dans la normalisation commune au catalogue et aux observations OCR ; les niveaux sont dans `config/rules.json`.

43 libellés sont renseignés dans neuf groupes de badges. Les deux noms initialement tronqués ont été confirmés explicitement par l'utilisateur : « Ultra Rare Chromatique » (`Shiny Ultra Rare`, deux étoiles dorées) et « Rare Chromatique VMAX » (`Shiny rare VMAX`, trois étoiles multicolores). « Illustration Spéciale… » est reconnu sous son préfixe non ambigu et sous « Illustration Spéciale Rare ».

Le jaune exige un même groupe et une rareté différente ; le gris exclut tout le groupe ; le vert exige la rareté exacte. Les paires dont le niveau n'est pas documenté restent possibles avec un avertissement. L'ordre des flèches n'est pas déduit de la position des noms dans le menu : les relations attestées par les captures de parties restent appliquées séparément.

Les cases cochées du filtre ne remplacent pas les critères du solveur et ne provoquent aucune suppression de cartes. Les catégories Pocket restent exclues des propositions. La rareté simple `Rare`, absente des captures, n'est pas assimilée à `Rare Holo`.

Attention aux traductions : `Amazing Rare` = « Rare Magnifique », tandis que `Secret Rare` = « Rare Secrète ». L'ancienne traduction TCGdex « Magnifique rare » reste un alias technique de `Secret Rare`, mais le libellé affiché est désormais celui de Holopocket.

Vérifications : test croisé vert/jaune/gris pour toutes les paires des 43 libellés ; alias TCGdex/français ; absence d'ordre inventé ; régressions complètes des parties Ronflex, Pikachu, Corvaillus et Coléodôme. Ces tests utilisent des transcriptions des captures et un résultat vision simulé ; ils ne constituent pas une nouvelle inférence réelle d'Ollama.
