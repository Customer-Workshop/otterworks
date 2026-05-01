import { setWorldConstructor, World, IWorldOptions } from "@cucumber/cucumber";
import { chromium, type Browser, type BrowserContext, type Page } from "@playwright/test";

export class OtterWorld extends World {
  browser!: Browser;
  context!: BrowserContext;
  page!: Page;

  constructor(options: IWorldOptions) {
    super(options);
  }

  async openBrowser() {
    this.browser = await chromium.launch({ headless: true });
    this.context = await this.browser.newContext();
    this.page = await this.context.newPage();
  }

  async closeBrowser() {
    await this.page?.close().catch(() => {});
    await this.context?.close().catch(() => {});
    await this.browser?.close().catch(() => {});
  }
}

setWorldConstructor(OtterWorld);
