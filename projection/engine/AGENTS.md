# AGENTS.md — moteur de projection

Le moteur prend un **texte de base** et un **amendement**, applique les instructions du dispositif
et rend le **texte résultant**. Un outil de plaidoyer ne peut pas afficher un texte faux : un
résultat est **exact ou absent**.

Ce fichier explique les identifiants (A1, B2, C3…, R1–R5) cités dans le code, les tests et les
grammaires, pour que l'utilisateur et les agents s'y retrouvent. Les suivre à la lettre : en
ajouter ou en changer un, c'est changer le périmètre du moteur, à valider avec l'utilisateur.

Vocabulaire : la base est le `Text` de l'adaptateur Tricoteuses (article → alinéas, un alinéa par
ligne). Un amendement modifie le texte du projet, pas le code qu'il cite.

## Périmètre : les besoins

✅ déterministe · ⚠️ sous condition · ❌ refusé (`hors_perimetre` sauf mention).

| Id | Besoin | | Condition ou raison |
|----|--------|---|---------------------|
| A1 | Base structurée | ⚠️ | Refus si l'article est `inchange` sans source ou issu d'une plage. Le n° d'alinéa est la position. |
| A2, A4, A5 | Modificatif = amendement ; HTML → lignes ; normalisation (nbsp, U+202F, U+2011, apostrophes, guillemets) | ✅ | Fonctions fixes, normalisation appliquée aux deux côtés. |
| A3 | Modificatif = loi modifiant un code | ❌ | Exige l'état du code. |
| B1 | Découpage en instructions (« I. – », « II. – ») | ⚠️ | Découpage unique, jamais redécoupé, sinon refus. |
| B2, B3 | Instruction → opération typée ; citations « … » | ✅ | Une seule analyse (R1). |
| B4 | Texte libre | ❌ | |
| C1 | Article visé (`ART. 2`, `ART. UNIQUE`) | ⚠️ | Refus si absent, plusieurs, ou autre article cité. |
| C2, C3 | Alinéa par numéro, ordinal, dernier ; listes et plages | ✅ | Position dans la liste. |
| C4 | « même alinéa », « cet alinéa » | ⚠️ | Antécédent = instruction immédiatement précédente, résolue. |
| C5–C8 | Phrases, subdivisions (4°), tableaux/titres, champ `alinea` | ❌ | Ambigu ou absent de `Text`. Le dispositif prime sur `alinea`. |
| D1–D4 | Substituer, supprimer/insérer des mots, insérer/compléter en bord | ⚠️ | R3 + règles d'écriture. |
| D5, D6 | Supprimer alinéa / article | ✅ | Article supprimé : `supprime=True`, `lignes=[]` ; absent = supprimé. |
| D7 | Rédiger ainsi | ✅ | Remplacement intégral. |
| D8 | Réécrire / supprimer la fin après des mots | ⚠️ | R3 pour l'ancre. |
| D9 | Insérer / compléter par des alinéas | ⚠️ | Nombre annoncé vérifié ; « les alinéas suivants » seulement en dernière instruction. |
| D10 | Article additionnel | ❌ | Numéro attribué après coup. |
| D11 | « Procéder à la même substitution… » | ⚠️ | Rejoue l'opération précédente du même genre. |
| D12, D13 | Coordination des renvois ; occurrences multiples sans ordinal | ❌ | Exige le sens. |
| E1 | Retenir `sort == "Adopté"` | ✅ | Filtre fait par l'appelant. |
| E2 | Plusieurs amendements sur un article | ⚠️ | Cibles disjointes ; sinon `conflit` pour tous. Identiques dédoublonnés. |
| E3 | Sous-amendements | ❌ | L'amendement parent et le sous-amendement sont refusés. |
| E4, E5 | Amendement rectifié ; commission → séance | ✅ | Base de la séance = texte officiel de la commission, jamais notre résultat. |
| E6 | Amendement multi-instructions | ⚠️ | Tout ou rien. |
| E7 | Retouches de coordination des services | ❌ | Absentes des amendements. |
| F1–F3 | Texte résultant ; trace par instruction ; pureté (aucun I/O) | ✅ | |

## Critère de retenue : R1–R5

Une instruction est appliquée si et seulement si :

- **R1** une seule analyse grammaticale ;
- **R2** la cible désigne exactement un nœud existant ;
- **R3** l'ancre apparaît exactement une fois (ou occurrence ordinale explicite), par mots entiers,
  sensible à la casse, après normalisation ;
- **R4** le texte écrit figure intégralement dans l'instruction ;
- **R5** aucune dépendance à un autre amendement, un vote ou un ordre (sauf E2 disjoint).

Sinon : **refus explicite** avec raison, jamais de meilleure hypothèse.

## Règles d'écriture

- **Insertion** (D3) : si la citation commence par `,` `.` `)` `;` elle se colle ; sinon une espace
  sépare, sauf si elle en porte déjà une. D4 : insertion avant la ponctuation finale.
- **Recollement** (D2, D8) : espaces multiples réduites à une ; espace avant `,` ou `.` retirée.
- **Article vidé** : supprimer tous les alinéas sans supprimer l'article est refusé.
