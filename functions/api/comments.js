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

    // 统一 Auth 逻辑
    const authHeader = request.headers.get("Authorization");
    const token = authHeader ? authHeader.replace("Bearer ", "") : null;
    let userId = null;
    let username = null;

    // Validate QID for GET/POST (PUT uses body)
    if (!questionId && (request.method === "GET" || request.method === "POST")) {
        return new Response("Missing question ID", { status: 400, headers: corsHeaders });
    }

    if (token) {
        const session = await db.prepare(
            "SELECT u.id, u.username FROM sessions s JOIN users u ON s.user_id = u.id WHERE s.token = ? AND s.expires_at > ?"
        ).bind(token, Date.now()).first();
        if (session) {
            userId = session.id;
            username = session.username;
        }
    }

    // GET: 获取评论 (关联用户)
    if (request.method === "GET") {
        try {
            const { results } = await db.prepare(`
                SELECT c.id, c.content, c.created_at, c.updated_at, c.user_id,
                       COALESCE(u.username, c.nickname) as nickname 
                FROM comments c
                LEFT JOIN users u ON c.user_id = u.id
                WHERE c.question_id = ? 
                ORDER BY c.created_at DESC LIMIT 50
            `).bind(questionId).all();

            // Allow frontend to identify own comments
            return Response.json(results, { headers: corsHeaders });
        } catch (e) {
            return Response.json({ error: e.message }, { status: 500, headers: corsHeaders });
        }
    }

    // POST: 发表评论
    if (request.method === "POST") {
        try {
            const data = await request.json();
            const { content } = data;
            // 如果未登录，使用传入的 nickname，否则使用账户名
            let { nickname } = data;
            if (username) nickname = username;

            // 1. 安全检查 & 简单清洗 (HTML 转义)
            if (!content || content.length > 5000) return new Response("Content too long (max 5000) or empty", { status: 400, headers: corsHeaders });
            if (!nickname || nickname.length > 20) return new Response("Nickname too long", { status: 400, headers: corsHeaders });

            const safeContent = content.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
            const safeNick = nickname.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
            const clientIp = request.headers.get("CF-Connecting-IP") || "unknown";

            await db.prepare(
                "INSERT INTO comments (question_id, nickname, content, ip_hash, user_id) VALUES (?, ?, ?, ?, ?)"
            ).bind(questionId, safeNick, safeContent, clientIp, userId).run();

            return Response.json({ success: true }, { headers: corsHeaders });
        } catch (e) {
            return Response.json({ error: e.message }, { status: 500, headers: corsHeaders });
        }
    }

    // PUT: 修改评论
    if (request.method === "PUT") {
        try {
            if (!userId) return new Response("Unauthorized", { status: 401, headers: corsHeaders });

            const data = await request.json();
            const { commentId, content } = data;

            if (!content || content.length > 5000) return new Response("Content invalid", { status: 400, headers: corsHeaders });

            // Verify ownership
            const comment = await db.prepare("SELECT user_id FROM comments WHERE id = ?").bind(commentId).first();
            if (!comment) return new Response("Comment not found", { status: 404, headers: corsHeaders });
            if (comment.user_id !== userId) return new Response("Forbidden", { status: 403, headers: corsHeaders });

            const safeContent = content.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

            await db.prepare(
                "UPDATE comments SET content = ?, updated_at = ? WHERE id = ?"
            ).bind(safeContent, Math.floor(Date.now() / 1000), commentId).run();

            return Response.json({ success: true }, { headers: corsHeaders });

        } catch (e) {
            return Response.json({ error: e.message }, { status: 500, headers: corsHeaders });
        }
    }

    return new Response("Method not allowed", { status: 405, headers: corsHeaders });
}