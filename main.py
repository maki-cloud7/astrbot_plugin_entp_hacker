import asyncio
import httpx
import feedparser
from twikit import Client
from astrbot.api.all import *

@register("entp_hacker", "AstrBot", "1.0.0", "ENTP独立开发者专用资讯源整合 (包含 X, HN, Github等)")
class ENTPHackerPlugin(Star):
    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        self.config = config
        self.twikit_client = Client('en-US')
        
    @llm_tool("get_geek_news")
    async def get_geek_news(self, event: AstrMessageEvent) -> str:
        """
        获取全网极客、创业相关的最新硬核资讯（包含 Github Trending, Hacker News, V2EX, Product Hunt, X, Reddit最新动态等）。
        请仔细阅览这篇长文本返回的数据，挑选出 1-2 条最有趣的，加入你作为 ENTP 独立开发者的独特见解和吐槽，像个好朋友一样分享出来。
        """
        
        results = []
        timeout = 10.0
        
        async with httpx.AsyncClient(timeout=timeout) as client:
            # 1. GitHub Trending (Using OSSInsight API)
            try:
                res = await client.get("https://api.ossinsight.io/v1/trends/repos", headers={"User-Agent": "Mozilla/5.0"})
                if res.status_code == 200:
                    repos = res.json().get('data', {}).get('rows', [])[:5]
                    gh_text = "【GitHub Trending Top 5】\n"
                    for r in repos:
                        repo_url = f"https://github.com/{r.get('repo_name', '')}"
                        gh_text += f"- {r.get('repo_name', '')}: {r.get('description', '')} URL: {repo_url}\n"
                    results.append(gh_text)
                else:
                    results.append(f"【GitHub Trending】获取失败 HTTP: {res.status_code}")
            except Exception as e:
                results.append(f"【GitHub Trending】获取异常: {e}")

            # 2. Hacker News
            try:
                res = await client.get("https://hacker-news.firebaseio.com/v0/topstories.json")
                if res.status_code == 200:
                    top_ids = res.json()[:5]
                    hn_text = "【Hacker News Top 5】\n"
                    for item_id in top_ids:
                        item_res = await client.get(f"https://hacker-news.firebaseio.com/v0/item/{item_id}.json")
                        if item_res.status_code == 200:
                            item = item_res.json()
                            url = item.get('url', f"https://news.ycombinator.com/item?id={item_id}")
                            hn_text += f"- {item.get('title', '')} (Score: {item.get('score', 0)}) URL: {url}\n"
                    results.append(hn_text)
            except Exception as e:
                results.append(f"【Hacker News】获取失败: {e}")

            # 3. V2EX Hot
            try:
                res = await client.get("https://www.v2ex.com/api/topics/hot.json", headers={"User-Agent": "Mozilla/5.0"})
                if res.status_code == 200:
                    topics = res.json()[:5]
                    v2_text = "【V2EX 今日热议】\n" + "\n".join([f"- {t['title']} ({t['replies']} replies) URL: {t.get('url', '')}" for t in topics])
                    results.append(v2_text)
                else:
                    results.append(f"【V2EX】获取失败 HTTP: {res.status_code}")
            except Exception as e:
                results.append(f"【V2EX】获取异常: {e}")

            # 4. Reddit
            try:
                reddit_text = "【Reddit 热门】\n"
                # 随机抓取两个板块防止内容太多
                subs = self.config.get("reddit_subs", ["selfhosted", "InternetIsBeautiful", "SaaS", "startups"])[:2]
                for sub in subs:
                    res = await client.get(f"https://www.reddit.com/r/{sub}/top.json?limit=3&t=day", headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"})
                    if res.status_code == 200:
                        posts = res.json().get('data', {}).get('children', [])
                        reddit_text += f"r/{sub}:\n" + "\n".join([f"  - {p['data']['title']} URL: https://www.reddit.com{p['data'].get('permalink', '')}" for p in posts]) + "\n"
                    else:
                        reddit_text += f"r/{sub} 获取失败 HTTP {res.status_code}\n"
                results.append(reddit_text)
            except Exception as e:
                results.append(f"【Reddit】获取异常: {e}")
                
            # 5. Product Hunt (via RSSHub proxy or official RSS if available)
            try:
                # 使用 RSS 解析
                # 为了简单不暴露 API Key，可以通过第三方免费接口或官方 RSS
                feed = feedparser.parse("https://www.producthunt.com/feed")
                ph_text = "【Product Hunt 最新产品】\n"
                for entry in feed.entries[:5]:
                    ph_text += f"- {entry.title}: {entry.description} URL: {entry.link}\n"
                results.append(ph_text)
            except Exception:
                pass

        # 6. X (Twitter) via twikit
        x_text = "【X (Twitter) 关注圈子最新动态】\n"
        x_auth_token = self.config.get("x_auth_token", "")
        x_ct0 = self.config.get("x_ct0", "")
        x_target_users = self.config.get("x_target_users", ["sama", "karpathy", "paulg", "ycombinator"])
        
        if x_auth_token and x_ct0:
            try:
                self.twikit_client.set_cookies({'auth_token': x_auth_token, 'ct0': x_ct0})
                for user_handle in x_target_users[:3]: # 限制数量
                    user = await self.twikit_client.get_user_by_screen_name(user_handle)
                    if user:
                        tweets = await user.get_tweets('Tweets', count=3)
                        x_text += f"@{user_handle}:\n"
                        for t in tweets:
                            x_text += f"  - {t.text} URL: https://x.com/{user_handle}/status/{t.id}\n"
                results.append(x_text)
            except Exception as e:
                results.append(f"【X (Twitter)】获取失败（可能是 auth_token 或 ct0 错误/过期）: {e}")
        else:
            results.append("【X (Twitter)】未配置 auth_token 或 ct0，跳过。")

        # 最终汇总
        final_context = "\n\n".join(results)
        
        # 限制长度以避免超出上下文限制
        max_length = 8000
        if len(final_context) > max_length:
            final_context = final_context[:max_length] + "\n...[已截断，内容过多]"
            
        # 强制大模型输出格式的指令（直接附加在返回给大模型的文本末尾，确保它能看到）
        system_instruction = (
            "\n\n====================\n"
            "【SYSTEM INSTRUCTION FOR LLM - 极其重要的强制要求】\n"
            "请阅读上述抓取到的资讯，挑选 1-2 条最有趣的进行分析和吐槽。\n"
            "1. 用户的聊天客户端是纯文本环境，**完全不支持任何 Markdown 语法**！\n"
            "2. 绝对禁止使用任何 Markdown 符号进行排版（禁止使用 `#`标题、`**`加粗、`>`引用、`-`列表等）。请用普通的换行、空格或者基础标点符号（如 1. 2. 3.）来组织你的发言。\n"
            "3. 绝对禁止使用 `[文字](链接)` 的格式。在介绍完一条资讯后，**必须**单开一行，以纯文本形式直接原样粘贴对应的原始 URL！例如：\n"
            "链接：https://github.com/xxx\n"
            "如果你不输出原始 URL，用户将无法阅读原文！"
        )
        
        return final_context + system_instruction
