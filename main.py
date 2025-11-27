# File: main.py
# -------------
# AstrBot 插件主文件；将其放在插件目录下的 main.py

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.api.message_components import Image, Plain

import aiohttp
import asyncio
from bs4 import BeautifulSoup
import urllib.parse
import re
import os

try:
    import imgkit
    IMGKIT_AVAILABLE = True
except Exception:
    IMGKIT_AVAILABLE = False

KARDS_DECK_BUILDER = "https://www.kards.com/decks/deck-builder"

@register("astrbot_plugin_kards", "你的名字", "KARDS 卡组码识别并快速打开官网 Deck Builder 的插件", "0.1.0")
class KardsPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        # data dir example: persist if needed
        self.data_dir = os.path.join(context.data_dir, "kards")
        os.makedirs(self.data_dir, exist_ok=True)

    @filter.command("kards", alias={"kards码","卡组"})
    async def kards(self, event: AstrMessageEvent, deck_code: str = ""):
        '''识别消息中的 KARDS 卡组码并快速在官网打开，尝试截图返回。用法: /kards <deck code> 或直接把卡组码作为参数发送。'''
        message_str = event.message_str.strip()
        # if user passes deck_code param, use it; otherwise try to extract from message
        code = deck_code.strip() or self._extract_code(message_str)
        if not code:
            yield event.plain_result("未检测到 KARDS 卡组码。请将卡组码粘贴到命令后或在消息中包含以 '%%' 开头的卡组码。")
            return

        # normalize code: remove surrounding whitespace
        code = code.strip()
        logger.info(f"Detected kards code: {code}")

        # Build deck-builder URL
        # The KARDS site expects the hash query param to be URL-encoded; the deck code often starts with '%%'
        encoded = urllib.parse.quote(code, safe='')
        builder_url = f"{KARDS_DECK_BUILDER}?hash={encoded}"

        # Try to fetch the deck page and parse basic info
        try:
            async with aiohttp.ClientSession() as sess:
                async with sess.get(builder_url, timeout=15) as resp:
                    text = await resp.text()
        except Exception as e:
            logger.exception("fetch deck builder failed")
            yield event.plain_result(f"构造了 Deck Builder 链接: {builder_url}\n但尝试访问官网时出现错误: {e}\n你可以手动打开链接在浏览器中确认并导入。")
            return

        # Try to parse the deck name and a short card list from the returned HTML
        deck_info = self._parse_deck_html(text)

        # Attempt to screenshot the page using imgkit (if available and wkhtmltoimage installed)
        screenshot_path = None
        if IMGKIT_AVAILABLE:
            try:
                outpath = os.path.join(self.data_dir, f"kards_{int(asyncio.get_event_loop().time())}.png")
                # imgkit.from_string may require wkhtmltoimage in system PATH
                imgkit.from_string(text, outpath)
                screenshot_path = outpath
            except Exception as e:
                logger.warning("imgkit screenshot failed: %s", e)
                screenshot_path = None

        # Compose reply
        lines = []
        if deck_info.get('title'):
            lines.append(f"解析到的卡组名: {deck_info['title']}")
        if deck_info.get('meta'):
            lines.append(deck_info['meta'])
        if deck_info.get('cards'):
            # show first 12 cards as preview
            preview = deck_info['cards'][:12]
            lines.append("卡牌预览 (最多显示前12张):")
            for c in preview:
                lines.append(f"  - {c}")
        lines.append("")
        lines.append(f"官网 Deck Builder 链接: {builder_url}")
        lines.append("小提示: 在 KARDS 客户端点击 New Deck 并确保剪贴板中包含卡组码，客户端会自动识别并提示导入。")

        # Send text result first
        yield event.plain_result("\n".join(lines))

        # If screenshot available, send as image (注意: 部分平台可能只接受网络图片 URL，某些适配器可以直接发送本地文件)
        if screenshot_path and os.path.exists(screenshot_path):
            # If adapter supports local file path in Image(file=), it will work; otherwise请将图片上传至图床并使用 URL。
            try:
                yield event.plain_result("尝试发送生成的截图：")
                yield event.result([Image(file=screenshot_path)])
            except Exception:
                # fallback: tell user where the file is stored on the host
                yield event.plain_result(f"已在机器人主机生成截图，但当前适配器无法直接发送本地文件。截图路径: {screenshot_path}")

    def _extract_code(self, text: str) -> str:
        # Look for sequences that look like KARDS deck codes. Many examples start with '%%' followed by characters and sometimes '|' or ';'
        m = re.search(r"(%%[^\s]+)", text)
        if m:
            return m.group(1)
        # fallback: look for shorter patterns (alphanumeric + punctuation typical for kards)
        m = re.search(r"([A-Za-z0-9%\|;,_\-]{10,200})", text)
        if m:
            return m.group(1)
        return ""

    def _parse_deck_html(self, html: str) -> dict:
        # Basic HTML parse to extract deck title and card names if present on the page
        soup = BeautifulSoup(html, "html.parser")
        result = {"title": "", "meta": "", "cards": []}
        # try to find deck title (common: h1 or .deck-title)
        h1 = soup.find('h1')
        if h1 and h1.text.strip():
            result['title'] = h1.text.strip()
        # meta info
        meta = soup.select_one('.deck-meta') or soup.select_one('.deck-info')
        if meta:
            result['meta'] = meta.get_text(separator=' ', strip=True)
        # Try to find card list elements
        card_elems = soup.select('.deck-card, .card-name, .card')
        if card_elems:
            for ce in card_elems:
                name = ce.get_text(strip=True)
                if name:
                    result['cards'].append(name)
        # If no structured card elements, try to parse plain text lines that resemble cards
        if not result['cards']:
            # heuristic: lines with capitalized words and numbers maybe card entries
            lines = [ln.strip() for ln in soup.get_text().splitlines() if ln.strip()]
            for ln in lines:
                if len(result['cards']) >= 40:
                    break
                # crude heuristic: lines that contain letters and optional 'x' or numbers
                if re.match(r"^[A-Z][A-Za-z0-9'""().,: -]{2,50}$", ln):
                    result['cards'].append(ln)
        return result

    async def terminate(self):
        logger.info("KardsPlugin terminate called")

# End of main.py

