-- Effectif réel de chaque session avec le nom du client commanditaire.
-- Tournée par l'assistant pour répondre aux questions de remplissage.

SELECT
    s.titre,
    cl.raison_sociale AS client,
    COUNT(st.id) AS nb_stagiaires
FROM sessions s
JOIN clients cl ON cl.id = s.client_id
LEFT JOIN stagiaires st ON st.session_id = s.id
GROUP BY s.titre, cl.raison_sociale
ORDER BY nb_stagiaires DESC;
