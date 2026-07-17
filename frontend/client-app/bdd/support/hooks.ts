import { Before, After } from "@cucumber/cucumber";
import { OtterWorld } from "./world";

Before(async function (this: OtterWorld) {
  await this.openBrowser();
});

After(async function (this: OtterWorld) {
  await this.closeBrowser();
});
