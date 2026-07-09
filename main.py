import asyncio
import httpx
import feedparser
from pydantic import BaseModel, Field
from twikit import Client
from astrbot.api.all import *

class Config(BaseModel):
    x_auth_token: str = Field("", description="X(Twitter)网页版 F12 抓取的 auth_token Cookie")
    x_target_users: list[str] = Field(["sama", "karpathy", "paulg", "ycombinator"], description="需要关注的 X 博主 handle (不要带@)")
    reddit_subs: list[str] = Field(["selfhosted", "InternetIsBeautiful", "SaaS", "startups"], description="关注的 Reddit 节点")

@register("entp_hacker", "AstrBot", "1.0.0", "ENTP独立开发者专用资讯源整合 (包含 X, HN, Github等)")
class ENTPHackerPlugin(Star):
    def __init__(self, context: Context, config: Config):
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
            # 1. GitHub Trending (Using unofficial simple API)
            try:
                res = await client.get("https://api.gitterapp.com/repositories?language=&since=daily")
                if res.status_code == 200:
                    repos = res.json()[:5]
                    gh_text = "【GitHub Trending Top 5】\n" + "\n".join([f"- {r['author']}/{r['name']}: {r.get('description', '')}" for r in repos])
                    results.append(gh_text)
            except Exception as e:
                results.append(f"【GitHub Trending】获取失败: {e}")

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
                            hn_text += f"- {item.get('title', '')} (Score: {item.get('score', 0)})\n"
                    results.append(hn_text)
            except Exception as e:
                results.append(f"【Hacker News】获取失败: {e}")

            # 3. V2EX Hot
            try:
                res = await client.get("https://www.v2ex.com/api/topics/hot.json")
                if res.status_code == 200:
                    topics = res.json()[:5]
                    v2_text = "【V2EX 今日热议】\n" + "\n".join([f"- {t['title']} ({t['replies']} replies)" for t in topics])
                    results.append(v2_text)
            except Exception as e:
                pass

            # 4. Reddit
            try:
                reddit_text = "【Reddit 热门】\n"
                # 随机抓取两个板块防止内容太多
                subs = self.config.reddit_subs[:2]
                for sub in subs:
                    res = await client.get(f"https://www.reddit.com/r/{sub}/top.json?limit=3&t=day", headers={"User-Agent": "AstrBot/1.0"})
                    if res.status_code == 200:
                        posts = res.json().get('data', {}).get('children', [])
                        reddit_text += f"r/{sub}:\n" + "\n".join([f"  - {p['data']['title']}" for p in posts]) + "\n"
                results.append(reddit_text)
            except Exception:
                pass
                
            # 5. Product Hunt (via RSSHub proxy or official RSS if available)
            try:
                # 使用 RSS 解析
                # 为了简单不暴露 API Key，可以通过第三方免费接口或官方 RSS
                feed = feedparser.parse("https://www.producthunt.com/feed")
                ph_text = "【Product Hunt 最新产品】\n"
                for entry in feed.entries[:5]:
                    ph_text += f"- {entry.title}: {entry.description}\n"
                results.append(ph_text)
            except Exception:
                pass

        # 6. X (Twitter) via twikit
        x_text = "【X (Twitter) 关注圈子最新动态】\n"
        if self.config.x_auth_token:
            try:
                self.twikit_client.set_cookies({'auth_token': self.config.x_auth_token})
                for user_handle in self.config.x_target_users[:3]: # 限制数量
                    user = await self.twikit_client.get_user_by_screen_name(user_handle)
                    if user:
                        tweets = await user.get_tweets('Tweets', count=3)
                        x_text += f"@{user_handle}:\n"
                        for t in tweets:
                            x_text += f"  - {t.text}\n"
                results.append(x_text)
            except Exception as e:
                results.append(f"【X (Twitter)】获取失败（可能是 auth_token 错误或过期）: {e}")
        else:
            results.append("【X (Twitter)】未配置 auth_token，跳过。")

        # 最终汇总
        final_context = "\n\n".join(results)
        
        # 限制长度以避免超出上下文限制
        max_length = 8000
        if len(final_context) > max_length:
            final_context = final_context[:max_length] + "\n...[已截断，内容过多]"
            
        return final_context
