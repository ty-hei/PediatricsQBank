export async function onRequest(context) {
    const { request, env } = context;
    const db = env.DB; // 确保在 CF 后台绑定 D1 变量名为 DB

    // CORS 头
    const corsHeaders = {
        "Access-Control-Allow-Origin": "*", // 生产环境请改为你的具体域名
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
    };

    if (request.method === "OPTIONS") {
        return new Response(null, { headers: corsHeaders });
    }

    const url = new URL(request.url);
    const questionId = url.searchParams.get("qid");

    if (!questionId) {
        return new Response("Missing question ID", { status: 400, headers: corsHeaders });
    }

    // GET: 获取评论
    if (request.method === "GET") {
        try {
            const { results } = await db.prepare(
                "SELECT nickname, content, created_at FROM comments WHERE question_id = ? ORDER BY created_at DESC LIMIT 50"
            ).bind(questionId).all();
            return Response.json(results, { headers: corsHeaders });
        } catch (e) {
            return Response.json({ error: e.message }, { status: 500, headers: corsHeaders });
        }
    }

    // POST: 发表评论
    if (request.method === "POST") {
        try {
            const data = await request.json();
            const { nickname, content } = data;

            // 1. 安全检查 & 简单清洗 (HTML 转义)
            if (!content || content.length > 5000) return new Response("Content too long (max 5000) or empty", { status: 400, headers: corsHeaders });
            if (!nickname || nickname.length > 20) return new Response("Nickname too long", { status: 400, headers: corsHeaders });

            const safeContent = content.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
            const safeNick = nickname.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
            const clientIp = request.headers.get("CF-Connecting-IP") || "unknown";

            // 2. 简单的频率限制 (实际生产建议用 KV 或 Durable Objects)
            // 这里仅演示：插入数据
            await db.prepare(
                "INSERT INTO comments (question_id, nickname, content, ip_hash) VALUES (?, ?, ?, ?)"
            ).bind(questionId, safeNick, safeContent, clientIp).run();

            return Response.json({ success: true }, { headers: corsHeaders });
        } catch (e) {
            return Response.json({ error: e.message }, { status: 500, headers: corsHeaders });
        }
    }

    return new Response("Method not allowed", { status: 405, headers: corsHeaders });
}