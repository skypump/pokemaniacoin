"""
test_playwright_html.py — Shrani HTML pump.fun strani da vidimo selektorje za callouts.
Uporaba: py -3.12 test_playwright_html.py
"""
import asyncio
from dotenv import load_dotenv
load_dotenv()

from playwright.async_api import async_playwright
from config import settings

MINT = settings.SOLWATCH_MINT_ADDRESS
COIN_URL = f"https://pump.fun/coin/C3YqoCUDUdzPoTf7YUhXDnxzrfHyHnRbxYnLWvpFpump"  # test coin z callouts


async def main():
    print(f"Nalagam: {COIN_URL}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        await page.goto(COIN_URL, wait_until="domcontentloaded", timeout=40000)

        # Počakaj da skeleton loader izgine iz callouts sekcije
        try:
            await page.wait_for_function(
                """() => {
                    const heading = [...document.querySelectorAll('p')].find(p => p.textContent.includes('Top callouts'));
                    if (!heading) return false;
                    const section = heading.closest('div');
                    if (!section) return false;
                    // Skeleton ima animate-pulse — čakamo da izgine
                    return !section.querySelector('.animate-pulse');
                }""",
                timeout=20000
            )
            print("Callouts naloženi!")
        except Exception:
            print("Timeout čakanja na callouts — nadaljujem vseeno")
            await page.wait_for_timeout(5000)

        # Shrani cel HTML
        html = await page.content()
        with open("page_dump.html", "w", encoding="utf-8") as f:
            f.write(html)
        print(f"HTML shranjen v page_dump.html ({len(html)} znakov)")

        # Poišči del ki vsebuje "callout" ali "called at"
        snippet = ""
        idx = html.lower().find("callout")
        if idx == -1:
            idx = html.lower().find("called at")
        if idx == -1:
            idx = html.lower().find("i need a watch")

        if idx != -1:
            snippet = html[max(0, idx-200):idx+500]
            print(f"\nNajden relevanten del HTML (okoli pozicije {idx}):\n")
            print(snippet)
        else:
            print("\nNI najden 'callout', 'called at' ali 'i need a watch' v HTML-ju!")
            print("Morda stran zahteva login ali se callouts naložijo drugače.")

        await browser.close()


asyncio.run(main())
