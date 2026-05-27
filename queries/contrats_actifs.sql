-- Nombre de contrats actifs par stagiaire — appelée par l'assistant
-- pour répondre à « avec qui avons-nous des contrats actifs ? ».

SELECT
    s.prenom,
    s.nom,
    COUNT(c.id) AS nb_contrats_actifs
FROM contrats c
JOIN stagiaires s ON c.stagiaire_id = s.id
WHERE c.statut = 'actif'
GROUP BY s.prenom, s.nom
ORDER BY nb_contrats_actifs DESC;
