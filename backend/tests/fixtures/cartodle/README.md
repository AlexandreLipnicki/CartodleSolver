# Référence Lucario

`lucario.expected.json` transcrit manuellement les valeurs, couleurs et flèches visibles dans la capture affichée par l’utilisateur. Toutes les cases sont violettes (incorrectes, `gray`), sauf les PV jaunes (`yellow`). Flèches : Pokédex ↓, PV ↓, rareté ↓, extension ↑.

`lucario.recreated.html` et `lucario.recreated.png` sont une **reconstitution synthétique** de cette ligne, sans l’illustration Pokémon. Ce ne sont pas les pixels du fichier original de l’utilisateur, qui n’était pas monté dans l’espace de travail. Ils permettent une régression reproductible, mais ne prouvent pas la lecture de la vraie capture.

Génération : `node scripts/render-vision-fixture.mjs`.
Test avec un vrai Ollama : `.venv/bin/python scripts/check-vision.py backend/tests/fixtures/cartodle/lucario.recreated.png --expected backend/tests/fixtures/cartodle/lucario.expected.json`.
