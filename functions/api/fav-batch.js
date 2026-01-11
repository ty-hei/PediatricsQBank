export async function onRequestPost(context) {
    const { request, env } = context;
    const db = env.DB;

    const corsHeaders = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Headers": "Content-Type",
    };

    try {
        const { ids } = await request.json(); // ids 是一个数组 ['hash1', 'hash2']
        if (!ids || !Array.isArray(ids) || ids.length === 0) {
            return Response.json({}, { headers: corsHeaders });
        }

        // 构建 SQL IN 查询 (注意：D1 参数绑定限制，如果数组过大需分片，这里假设每页题目<100)
        const placeholders = ids.map(() => '?').join(',');
        const query = `SELECT question_id, fav_count FROM question_stats WHERE question_id IN (${placeholders})`;

        const { results } = await db.prepare(query).bind(...ids).all();

        // 转换为 Map 格式 { "hash1": 10, "hash2": 5 }
        const map = {};
        results.forEach(r => {
            map[r.question_id] = r.fav_count;
        });

        return Response.json(map, { headers: corsHeaders });

    } catch (e) {
        return Response.json({ error: e.message }, { status: 500, headers: corsHeaders });
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