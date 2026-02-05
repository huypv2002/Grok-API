"""Test multiple tabs with zendriver"""
import asyncio
import zendriver


async def main():
    print("🚀 Starting browser...")
    
    # Create browser config
    config = zendriver.Config(headless=True)  # Headless mode
    
    # Start browser
    browser = zendriver.Browser(config)
    await browser.start()
    
    try:
        # Tab 1: Google (main_tab is created automatically)
        print("📑 Tab 1: Going to Google...")
        await browser.main_tab.get("https://www.google.com")
        await asyncio.sleep(1)
        
        # Get title of tab 1
        title1 = await browser.main_tab.evaluate("document.title")
        print(f"   Tab 1 title: {title1}")
        
        # Tab 2: Facebook - create new tab
        print("📑 Tab 2: Going to Facebook...")
        tab2 = await browser.get("https://www.facebook.com", new_tab=True)
        await asyncio.sleep(1)
        
        title2 = await tab2.evaluate("document.title")
        print(f"   Tab 2 title: {title2}")
        
        # Tab 3: YouTube - create another new tab
        print("📑 Tab 3: Going to YouTube...")
        tab3 = await browser.get("https://www.youtube.com", new_tab=True)
        await asyncio.sleep(1)
        
        title3 = await tab3.evaluate("document.title")
        print(f"   Tab 3 title: {title3}")
        
        # List all tabs
        print("\n📋 All tabs:")
        print(f"   - Tab 1 (main_tab): {browser.main_tab}")
        print(f"   - Tab 2: {tab2}")
        print(f"   - Tab 3: {tab3}")
        
        # Switch between tabs and do something
        print("\n🔄 Switching between tabs...")
        
        # Do something on tab 1
        await browser.main_tab.evaluate("console.log('Hello from Tab 1')")
        print("   Tab 1: Executed JS")
        
        # Do something on tab 2
        await tab2.evaluate("console.log('Hello from Tab 2')")
        print("   Tab 2: Executed JS")
        
        # Do something on tab 3
        await tab3.evaluate("console.log('Hello from Tab 3')")
        print("   Tab 3: Executed JS")
        
        # Navigate tab 1 to another URL
        print("\n🔄 Navigating Tab 1 to Bing...")
        await browser.main_tab.get("https://www.bing.com")
        await asyncio.sleep(1)
        title1_new = await browser.main_tab.evaluate("document.title")
        print(f"   Tab 1 new title: {title1_new}")
        
        # Get current URLs of all tabs
        print("\n🔗 Current URLs:")
        url1 = await browser.main_tab.evaluate("window.location.href")
        url2 = await tab2.evaluate("window.location.href")
        url3 = await tab3.evaluate("window.location.href")
        print(f"   Tab 1: {url1}")
        print(f"   Tab 2: {url2}")
        print(f"   Tab 3: {url3}")
        
        print("\n✅ Multi-tab test completed!")
        
    except KeyboardInterrupt:
        print("\n👋 Closing browser...")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await browser.stop()
        print("🛑 Browser closed")


if __name__ == "__main__":
    asyncio.run(main())
