export async function onRequest(context) {
    const { request, env } = context;
    const db = env.DB;

    // 统一 CORS 头
    const corsHeaders = {
        "Access-Control-Allow-Origin": "https://PediatricsQBank.heihaheihaha.com", // 请替换为实际域名
        "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, Authorization",
    };

    if (request.method === "OPTIONS") {
        return new Response(null, { headers: corsHeaders });
    }

    const url = new URL(request.url);
    const action = url.searchParams.get("action"); // register, login, upload, download

    try {
        // -------------------------------------------------------------
        // 1. 注册 (POST)
        // -------------------------------------------------------------
        if (action === "register" && request.method === "POST") {
            const { username, password } = await request.json();
            if (!username || !password || username.length < 3 || password.length < 6) {
                return Response.json({ error: "用户名至少3位，密码至少6位" }, { status: 400, headers: corsHeaders });
            }

            // 检查用户是否存在
            const exist = await db.prepare("SELECT id FROM users WHERE username = ?").bind(username).first();
            if (exist) return Response.json({ error: "用户名已存在" }, { status: 409, headers: corsHeaders });

            // 密码哈希 (Web Crypto API)
            const salt = crypto.randomUUID();
            const hash = await hashPassword(password, salt);

            await db.prepare("INSERT INTO users (username, password_hash, salt) VALUES (?, ?, ?)")
                .bind(username, hash, salt).run();

            return Response.json({ success: true, msg: "注册成功，请登录" }, { headers: corsHeaders });
        }

        // -------------------------------------------------------------
        // 2. 登录 (POST)
        // -------------------------------------------------------------
        if (action === "login" && request.method === "POST") {
            const { username, password } = await request.json();

            const user = await db.prepare("SELECT id, password_hash, salt FROM users WHERE username = ?").bind(username).first();
            if (!user) return Response.json({ error: "用户不存在或密码错误" }, { status: 401, headers: corsHeaders });

            const hash = await hashPassword(password, user.salt);
            if (hash !== user.password_hash) {
                return Response.json({ error: "用户不存在或密码错误" }, { status: 401, headers: corsHeaders });
            }

            // 生成 Token (有效期 30 天)
            const token = crypto.randomUUID();
            const expiresAt = Date.now() + 1000 * 60 * 60 * 24 * 30;

            await db.prepare("INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)")
                .bind(token, user.id, expiresAt).run();

            return Response.json({ success: true, token, username }, { headers: corsHeaders });
        }

        // ================= 鉴权中间件逻辑 =================
        // 下面的操作需要 Token
        const authHeader = request.headers.get("Authorization");
        const token = authHeader ? authHeader.replace("Bearer ", "") : null;
        if (!token) return Response.json({ error: "未登录" }, { status: 401, headers: corsHeaders });

        const session = await db.prepare("SELECT user_id FROM sessions WHERE token = ? AND expires_at > ?")
            .bind(token, Date.now()).first();

        if (!session) return Response.json({ error: "会话失效，请重新登录" }, { status: 401, headers: corsHeaders });
        const userId = session.user_id;

        // -------------------------------------------------------------
        // 3. 上传/备份进度 (POST)
        // -------------------------------------------------------------
        if (action === "upload" && request.method === "POST") {
            const { records, favs } = await request.json();

            // Upsert: 存在则更新，不存在则插入
            await db.prepare(`
        INSERT INTO user_data (user_id, records_json, favs_json, updated_at) 
        VALUES (?1, ?2, ?3, ?4)
        ON CONFLICT(user_id) DO UPDATE SET 
        records_json = ?2, favs_json = ?3, updated_at = ?4
      `).bind(userId, JSON.stringify(records), JSON.stringify(favs), Date.now()).run();

            return Response.json({ success: true, time: Date.now() }, { headers: corsHeaders });
        }

        // -------------------------------------------------------------
        // 4. 下载/恢复进度 (GET)
        // -------------------------------------------------------------
        if (action === "download" && request.method === "GET") {
            const data = await db.prepare("SELECT records_json, favs_json, updated_at FROM user_data WHERE user_id = ?").bind(userId).first();

            if (!data) return Response.json({ empty: true }, { headers: corsHeaders });

            return Response.json({
                success: true,
                records: JSON.parse(data.records_json),
                favs: JSON.parse(data.favs_json),
                updated_at: data.updated_at
            }, { headers: corsHeaders });
        }

    } catch (e) {
        return Response.json({ error: e.message }, { status: 500, headers: corsHeaders });
    }

    return Response.json({ error: "Invalid Action" }, { status: 400, headers: corsHeaders });
}

// 简单的 SHA-256 哈希辅助函数
async function hashPassword(password, salt) {
    const enc = new TextEncoder();
    const keyMaterial = await crypto.subtle.importKey(
        "raw", enc.encode(password + salt), { name: "PBKDF2" }, false, ["deriveBits", "deriveKey"]
    );
    // 这里为了简单，其实直接做 SHA-256 也可以，但 PBKDF2 更标准。
    // 为了不引入复杂性，我们用最简单的：SHA-256(password + salt)
    const msgBuffer = enc.encode(password + salt);
    const hashBuffer = await crypto.subtle.digest('SHA-256', msgBuffer);
    const hashArray = Array.from(new Uint8Array(hashBuffer));
    return hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
}