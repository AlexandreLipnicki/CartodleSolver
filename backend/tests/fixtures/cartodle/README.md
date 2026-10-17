# Référence Lucario

`lucario.expected.json` transcrit manuellement les valeurs, couleurs et flèches visibles dans la capture affichée par l’utilisateur. Toutes les cases sont violettes (incorrectes, `gray`), sauf les PV jaunes (`yellow`). Flèches : Pokédex ↓, PV ↓, rareté ↓, extension ↑.

`lucario.recreated.html` et `lucario.recreated.png` sont une **reconstitution synthétique** de cette ligne, sans l’illustration Pokémon. Ce ne sont pas les pixels du fichier original de l’utilisateur, qui n’était pas monté dans l’espace de travail. Ils permettent une régression reproductible, mais ne prouvent pas la lecture de la vraie capture.

Génération : `node scripts/render-vision-fixture.mjs`.
Test avec un vrai Ollama : `.venv/bin/python scripts/check-vision.py backend/tests/fixtures/cartodle/lucario.recreated.png --expected backend/tests/fixtures/cartodle/lucario.expected.json`.

# Partie Ronflex

`ronflex-game.json` est la transcription manuelle de la capture utilisateur, dans l’ordre chronologique Lucario → Pyroli → Mew → Ronflex Pokémon GO → Ronflex Origine Perdue → Ronflex Galerie. Les identifiants TCGdex de référence servent aux assertions ; chaque ligne OCR laisse `card_id` à null et utilise les noms affichés sans suffixe V. Les tests rejouent aussi les lignes précédentes et vérifient le filtrage cumulatif sur le catalogue complet. Aucune lecture réelle de cette image par Ollama n’est revendiquée.

# Partie Corvaillus

`corvaillus-game.json` transcrit les deux lignes visibles sur la capture utilisateur : Lucario (rareté verte, PV gris ↑) puis Corvaillus (stade et rareté verts, PV jaunes ↓, extension grise ↓). Le test de filtrage et le test HTTP ne font pas appel à un vrai Ollama : ils isolent le défaut de catalogue qui rejetait ces résultats pourtant cohérents. Les 12 candidats attendus gardent tous les critères et les bornes cumulées.

# Partie Pikachu et règles de rareté

`pikachu-game.json` transcrit les cinq lignes de la capture utilisateur. Le dernier Pikachu conserve un illustrateur incorrect : la partie n'est pas résolue. Les tests rejouent les valeurs OCR et vérifient les exclusions cumulées sur le catalogue complet.

L'aide de https://holopocket.fr/ fournie par l'utilisateur indique : « Presque : même série d'extensions, un type en commun, PV à 20 près, même niveau de rareté. » Le jaune signifie donc même niveau, et non une distance numérique de un. Les groupes partiels de `config/rules.json` viennent uniquement des captures Pikachu et Ronflex. Les relations non documentées restent inconnues. Les cibles excluent Pokémon Pocket et les communes/peu communes, conformément au texte « une rare ou mieux » visible sur la capture CartoDle. Ces cartes restent lisibles comme essais historiques. Aucun test ne prétend interroger réellement Ollama ni vérifier directement le site, inaccessible depuis le cloud.
