export async function onRequestPost(context) {
    const { request, env } = context;
    const db = env.DB;

    const corsHeaders = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Headers": "Content-Type",
    };

    try {
        const { ids } = await request.json(); // ids: ['hash1', 'hash2']
        if (!ids || !Array.isArray(ids) || ids.length === 0) {
            return Response.json({}, { headers: corsHeaders });
        }

        // Build SQL IN clause
        const placeholders = ids.map(() => '?').join(',');
        const query = `SELECT question_id, correct_count, total_count, fav_count FROM question_stats WHERE question_id IN (${placeholders})`;

        const { results } = await db.prepare(query).bind(...ids).all();

        // Transform to Map: { "hash1": { rate: 50, total: 10, fav: 1 } }
        const map = {};
        results.forEach(r => {
            let rate = 0;
            if (r.total_count > 0) {
                rate = Math.round((r.correct_count / r.total_count) * 100);
            }
            map[r.question_id] = {
                rate: rate,
                total: r.total_count,
                fav: r.fav_count || 0
            };
        });

        return Response.json(map, { headers: corsHeaders });

    } catch (e) {
        return Response.json({ error: e.message, stack: e.stack }, { status: 500, headers: corsHeaders });
    }
}

export async function onRequestOptions() {
    return new Response(null, {
        headers: {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type",
        }
    });
}
