"""
test_intercept_callouts.py — Ujame API klic ki ga pump.fun naredi za callout podatke.
Uporaba: py -3.12 test_intercept_callouts.py
"""
import asyncio
import json
from dotenv import load_dotenv
load_dotenv()

from playwright.async_api import async_playwright

COIN_URL = "https://pump.fun/coin/C3YqoCUDUdzPoTf7YUhXDnxzrfHyHnRbxYnLWvpFpump"

caught = []

async def main():
    print(f"Nalagam: {COIN_URL}")
    print("Lovim API klice...\n")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        # Ujemi VSE response-e in išči callout podatke
        async def on_response(response):
            url = response.url
            # Preskoči slike, fonti, statične fajle
            if any(x in url for x in ['.png', '.jpg', '.svg', '.woff', '.css', 'analytics', 'intercom', 'mixpanel', 'datadog']):
                return
            try:
                ct = response.headers.get("content-type", "")
                if "json" in ct or "x-component" in ct:
                    body = await response.body()
                    text = body.decode("utf-8", errors="replace")
                    # Išči callout-related podatke
                    if any(kw in text.lower() for kw in ["callout", "called at", "caller", "callcount"]):
                        print(f"\n✅ CALLOUT DATA NAJDEN!")
                        print(f"URL: {url}")
                        print(f"Content-Type: {ct}")
                        print(f"Preview: {text[:500]}")
                        caught.append({"url": url, "body": text[:2000]})
                    elif "json" in ct and len(text) > 50:
                        # Prikaži vse JSON response-e (za debug)
                        print(f"  JSON [{response.status}]: {url[:100]}")
            except Exception:
                pass

        page.on("response", on_response)

        await page.goto(COIN_URL, wait_until="domcontentloaded", timeout=40000)
        print("Stran naložena, čakam 15s na API klice...\n")
        await page.wait_for_timeout(15000)

        if not caught:
            print("\n❌ Callout API klic NI bil ujet.")
            print("Pump.fun verjetno pošilja callouts prek RSC streama, ne JSON API-ja.")
        else:
            print(f"\n✅ Ujeto {len(caught)} callout odgovorov!")
            for c in caught:
                with open("callout_api_response.json", "w", encoding="utf-8") as f:
                    json.dump(c, f, indent=2)
                print(f"Shranjeno v callout_api_response.json")

        await browser.close()


asyncio.run(main())
