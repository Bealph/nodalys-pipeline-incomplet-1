-- Feedbacks saisis dans la dernière semaine.

SELECT
    f.session_id,
    f.stagiaire_email,
    f.note_globale,
    f.commentaire,
    f.created_at
FROM feedbacks f
WHERE f.created_at > NOW() - INTERVAL '7 days'
ORDER BY f.created_at DESC
LIMIT 50;
