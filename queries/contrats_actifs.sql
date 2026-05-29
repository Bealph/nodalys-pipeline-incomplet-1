-- Nombre de contrats actifs par client (organisme) — appelée par l'assistant
-- pour répondre à « avec qui avons-nous des contrats actifs ? ».
--
-- Note : un contrat lie un client (organisme) à Nodalys pour une session
-- donnée. Il n'est pas rattaché à un stagiaire individuel.

SELECT
    cl.raison_sociale,
    COUNT(c.id) AS nb_contrats_actifs
FROM contrats c
JOIN clients cl ON cl.id = c.client_id
WHERE c.statut = 'actif'
GROUP BY cl.raison_sociale
ORDER BY nb_contrats_actifs DESC;
