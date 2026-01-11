export async function onRequestPost(context) {
    const { request, env } = context;
    const db = env.DB;

    const corsHeaders = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Headers": "Content-Type",
    };

    try {
        const { questionId, action } = await request.json(); // action: 'add' or 'remove'
        if (!questionId) return new Response("Missing ID", { status: 400 });

        const delta = action === 'add' ? 1 : -1;

        // Upsert 逻辑 (SQLite 风格)
        await db.prepare(`
      INSERT INTO question_stats (question_id, fav_count, last_updated)
      VALUES (?1, MAX(0, ?2), ?3)
      ON CONFLICT(question_id) DO UPDATE SET
      fav_count = MAX(0, fav_count + ?2),
      last_updated = ?3
    `).bind(questionId, delta, Date.now()).run();

        // 返回最新计数
        const result = await db.prepare("SELECT fav_count FROM question_stats WHERE question_id = ?").bind(questionId).first();

        return Response.json({ count: result ? result.fav_count : 0 }, { headers: corsHeaders });

    } catch (e) {
        return Response.json({ error: e.message }, { status: 500, headers: corsHeaders });
    }
}

// 处理 OPTIONS 预检
export async function onRequestOptions() {
    return new Response(null, {
        headers: {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type",
        }
    });
}