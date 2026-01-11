export async function onRequest(context) {
    const { request, env } = context;
    const db = env.DB;

    // Handle CORS
    const corsHeaders = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Headers": "Content-Type",
        "Access-Control-Allow-Methods": "POST, OPTIONS",
    };

    if (request.method === "OPTIONS") {
        return new Response(null, { headers: corsHeaders });
    }

    if (request.method !== "POST") {
        return new Response("Method Not Allowed", { status: 405, headers: corsHeaders });
    }

    try {
        const body = await request.json();
        const { questionId, type, value } = body;
        // type: 'answer' (value=1 correct, 0 wrong), 'fav' (value=1 add, -1 remove)

        if (!questionId) {
            return Response.json({ error: "Missing questionId" }, { status: 400, headers: corsHeaders });
        }

        if (type === 'answer') {
            const isCorrect = value === 1 ? 1 : 0;
            // Upsert Answer Stats
            const query = `
                INSERT INTO question_stats (question_id, correct_count, total_count, fav_count)
                VALUES (?, ?, 1, 0)
                ON CONFLICT(question_id) DO UPDATE SET
                correct_count = correct_count + ?,
                total_count = total_count + 1
            `;
            await db.prepare(query).bind(questionId, isCorrect, isCorrect).run();
            return Response.json({ success: true }, { headers: corsHeaders });
        }

        if (type === 'fav') {
            const delta = value === 1 ? 1 : -1;
            // Upsert Fav Stats
            // Initial insert: fav_count = 1 if adding, 0 if removing (edge case)
            const initVal = delta > 0 ? 1 : 0;

            const query = `
                INSERT INTO question_stats (question_id, correct_count, total_count, fav_count)
                VALUES (?, 0, 0, ?)
                ON CONFLICT(question_id) DO UPDATE SET
                fav_count = fav_count + ?
            `;
            await db.prepare(query).bind(questionId, initVal, delta).run();
            return Response.json({ success: true }, { headers: corsHeaders });
        }

        return Response.json({ error: "Unknown type" }, { status: 400, headers: corsHeaders });

    } catch (e) {
        return Response.json({ error: e.message }, { status: 500, headers: corsHeaders });
    }
}
