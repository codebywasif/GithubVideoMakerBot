from playwright.sync_api import sync_playwright
import os

os.makedirs("assets/screenshots", exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch()
    # Dark mode color scheme to match our UI nicely
    context = browser.new_context(color_scheme='dark', viewport={"width": 1280, "height": 800})
    page = context.new_page()
    
    print("Capturing Dashboard...")
    page.goto("http://localhost:4000/")
    page.wait_for_timeout(1000)
    page.screenshot(path="assets/screenshots/dashboard.png")
    
    print("Capturing Create Page...")
    page.goto("http://localhost:4000/#/create")
    page.wait_for_timeout(1000)
    page.screenshot(path="assets/screenshots/create.png")
    
    print("Capturing Backgrounds Page...")
    page.goto("http://localhost:4000/#/backgrounds")
    page.wait_for_timeout(1000)
    page.screenshot(path="assets/screenshots/backgrounds.png")
    
    print("Capturing Settings Page...")
    page.goto("http://localhost:4000/#/settings")
    page.wait_for_timeout(1000)
    page.screenshot(path="assets/screenshots/settings.png")
    
    browser.close()
    print("Screenshots captured successfully.")
