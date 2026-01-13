-- 1. 题目统计表 (原有功能)
CREATE TABLE IF NOT EXISTS question_stats (
    question_id TEXT PRIMARY KEY,
    fav_count INTEGER DEFAULT 0,
    correct_count INTEGER DEFAULT 0,
    total_count INTEGER DEFAULT 0,
    last_updated INTEGER
);

-- 2. 评论表 (原有功能)
CREATE TABLE IF NOT EXISTS comments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    question_id TEXT NOT NULL,
    nickname TEXT NOT NULL,
    content TEXT NOT NULL,
    ip_hash TEXT,
    created_at INTEGER DEFAULT (strftime('%s', 'now')),
    user_id INTEGER,
    updated_at INTEGER,
    FOREIGN KEY(user_id) REFERENCES users(id)
);
CREATE INDEX IF NOT EXISTS idx_comments_qid ON comments(question_id);

-- 3. 用户表 (新功能)
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL, -- 用户名唯一
    password_hash TEXT NOT NULL,   -- 存储哈希后的密码
    salt TEXT NOT NULL,            -- 随机盐值
    created_at INTEGER DEFAULT (strftime('%s', 'now'))
);

-- 4. 用户数据存档表 (新功能 - 用于多端同步)
CREATE TABLE IF NOT EXISTS user_data (
    user_id INTEGER PRIMARY KEY,
    records_json TEXT, -- 答题记录 JSON 字符串
    favs_json TEXT,    -- 收藏记录 JSON 字符串
    updated_at INTEGER,
    FOREIGN KEY(user_id) REFERENCES users(id)
);

-- 5. 会话表 (新功能 - 简单的 Token 管理)
CREATE TABLE IF NOT EXISTS sessions (
    token TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    expires_at INTEGER NOT NULL,
    FOREIGN KEY(user_id) REFERENCES users(id)
);