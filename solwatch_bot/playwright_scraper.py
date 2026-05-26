"""
playwright_scraper.py — Scrapa callouts za SOLWATCH coin s pump.fun prek pravega browserja.
Standalone test: py -3.12 playwright_scraper.py
"""
import asyncio
import logging
from dotenv import load_dotenv
load_dotenv()

from playwright.async_api import async_playwright
from config import settings
from db import upsert_callout
import time

logger = logging.getLogger(__name__)

MINT = settings.SOLWATCH_MINT_ADDRESS
COIN_URL = f"https://pump.fun/coin/{MINT}"


async def scrape_callouts_playwright() -> int:
    """
    Odpre pump.fun stran za naš coin, počaka da se callouts naložijo,
    in prebere wallet naslove + tekste. Vrne število novih calloutov.
    """
    added = 0

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        try:
            logger.info("Playwright: nalagam %s", COIN_URL)
            await page.goto(COIN_URL, wait_until="domcontentloaded", timeout=30000)

            # Počakaj da se callouts naložijo
            await page.wait_for_timeout(5000)

            # Poišči callout elemente — prilagodi selector glede na dejanski HTML
            callout_items = await page.query_selector_all("[class*='callout'], [class*='call-item'], [class*='top-call']")

            if not callout_items:
                # Fallback: poiščemo po tekstu "called at"
                callout_items = await page.query_selector_all("div:has-text('called at')")

            logger.info("Playwright: našel %d callout elementov", len(callout_items))

            for item in callout_items:
                text_content = await item.inner_text()
                lines = [l.strip() for l in text_content.split("\n") if l.strip()]
                logger.debug("Callout raw text: %s", lines)

                # Poiščemo wallet — pump.fun prikazuje skrajšano obliko (npr. 3jQgpYda)
                # Za pravi wallet naslov preverimo href linka
                wallet = ""
                link = await item.query_selector("a[href*='/profile/']")
                if link:
                    href = await link.get_attribute("href")
                    if href:
                        wallet = href.split("/profile/")[-1].split("?")[0]

                callout_text = text_content
                has_magic = settings.MAGIC_PHRASE in text_content.lower()

                if wallet:
                    upsert_callout(wallet, callout_text, int(time.time()), has_magic)
                    added += 1
                    logger.info("Callout: wallet=%s magic=%s", wallet[:8], has_magic)

        except Exception as e:
            logger.error("Playwright scrape napaka: %s", e)
        finally:
            await browser.close()

    return added


async def main():
    """Standalone test."""
    logging.basicConfig(level=logging.DEBUG, format="%(asctime)s %(levelname)s %(message)s")

    from db import init_db
    init_db()

    print(f"Scrapam: {COIN_URL}\n")
    count = await scrape_callouts_playwright()
    print(f"\nSkupaj dodanih: {count}")

    # Prikaži kaj je v bazi
    from db import get_conn
    conn = get_conn()
    rows = conn.execute("SELECT * FROM callouts ORDER BY callout_timestamp DESC LIMIT 10").fetchall()
    print("\nCallouts v bazi:")
    for r in rows:
        print(f"  wallet={r['wallet'][:12]}... magic={r['has_magic_phrase']} text={r['callout_text'][:60]}")
    conn.close()


if __name__ == "__main__":
    asyncio.run(main())
