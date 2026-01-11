# Serverless Markdown Question Bank (SMQB)

![Python](https://img.shields.io/badge/Python-3.9+-blue.svg)
![Cloudflare](https://img.shields.io/badge/Cloudflare-Pages%20%2F%20D1-orange.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)

**SMQB** 是一个全栈自动化工具，用于将 Markdown 格式的题库文件转换为高性能、单文件、具备社区功能的 Web 题库应用。

基于 **Python** 生成静态前端，利用 **Cloudflare Pages + D1 + Functions** 实现无服务器后端，支持从简单的静态刷题到复杂的用户同步、评论互动和大数据统计。

## ✨ 核心特性

* **⚡️ 极速体验**: 核心逻辑预编译为单一 HTML 文件，秒级加载，无白屏。
* **📄 Markdown 驱动**: 维护简单，只需编辑 Markdown 文件即可更新题库。
* **💾 状态记忆**: 自动保存答题进度（localStorage），刷新不丢失。
* **☁️ 云端同步**: 支持用户注册/登录，多端同步答题进度和收藏夹。
* **💬 社区互动**: 支持 Markdown 格式评论，自动展开热门讨论。
* **📊 数据统计**: 实时追踪全网题目热度（收藏数）与答题正确率。
* **🛡 安全可靠**: 密码加盐哈希存储，Token 鉴权，IP 频率限制。
* **💸 零成本部署**: 完全基于 Cloudflare 免费层（Pages + D1），无需购买服务器。

## 📂 项目结构

```text
.
├── convert.py              # 核心构建脚本 (Markdown -> HTML)
├── schema.sql              # D1 数据库初始化语句
├── Q1.md, Q2.md            # 题库源文件 (支持多文件合并)
├── dist/                   # 构建产物目录
│   ├── index.html          # 生成的单页应用
│   └── _headers            # Cloudflare 缓存配置
└── functions/              # 后端 Serverless 函数
    └── api/
        ├── comments.js     # 评论获取/发布
        ├── stats.js        # 收藏/答题数据上报
        ├── batch-info.js   # 批量数据查询
        └── user.js         # 用户注册/登录/同步

## 📚 数据统计原理

### 1. 核心表结构 (`question_stats`)
所有统计数据存储在 Cloudflare D1 数据库中：
```sql
CREATE TABLE question_stats (
    question_id TEXT PRIMARY KEY, -- 题目唯一哈希ID
    fav_count INTEGER DEFAULT 0,  -- 收藏总数
    correct_count INTEGER DEFAULT 0, -- 答对总次数
    total_count INTEGER DEFAULT 0,   -- 总答题次数
    last_updated INTEGER
);
```

### 2. 交互逻辑

#### 📝 数据上报 (Write)
当用户答题或点击收藏时，前端调用 `POST /api/stats`：
- **答题**: `{ type: 'answer', value: 1/0 }` -> 数据库原子更新 `correct_count` 和 `total_count`。
- **收藏**: `{ type: 'fav', value: 1/-1 }` -> 数据库原子更新 `fav_count`。
- **注意**: 目前数据上报API**不校验登录状态**，所有访客均可贡献数据（大数据众包模式）。

#### 📉 数据读取 (Read)
当用户进入某个章节时，前端调用 `POST /api/batch-info`：
- **入参**: 当前章节所有题目的 ID 列表。
- **返回**: 批量查询结果 `{ question_id: { rate: 50, total: 10, fav: 5 } }`。
- **计算公式**:
  - **正确率**: `(correct_count / total_count) * 100` (四舍五入)
  - **热度**: 直接显示 `fav_count`

此设计确保了在高并发下数据的准确性，并利用 D1 的边缘读取能力实现极快的加载速度。