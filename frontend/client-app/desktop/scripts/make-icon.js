/* Generates the app icons from the web app's otter (../public/favicon.svg).
 *
 * Runs under Electron so it works on macOS, Windows, and Linux with no native
 * SVG tooling: the SVG is drawn onto a <canvas> in a hidden window and read
 * back as PNG (alpha preserved). Run with: npm run icons
 *
 * Outputs (1024x1024, transparent):
 *   assets/icon.png     - full-bleed rounded square; Windows/Linux icons are
 *                         edge-to-edge, so this is used for .ico/Linux pngs
 *                         and the dev-mode window/taskbar icon
 *   assets/icon-mac.png - Apple icon grid: 824x824 artwork centered with
 *                         transparent margins and ~22.4% corner radius,
 *                         used for the Dock icon and .icns
 */
const fs = require("node:fs");
const path = require("node:path");
const { app, BrowserWindow } = require("electron");

const SRC = path.resolve(__dirname, "..", "..", "public", "favicon.svg");
const OUT_DIR = path.resolve(__dirname, "..", "assets");

const svgSource = fs.readFileSync(SRC, "utf8");
// Widen the favicon's baked-in 18% corner radius (180/1000) to Apple's ~22.4%
const svgMac = svgSource.replace('rx="180" ry="180"', 'rx="224" ry="224"');

const toDataUrl = (svg) => `data:image/svg+xml;base64,${Buffer.from(svg).toString("base64")}`;

async function render(win, svg, rect) {
  const dataUrl = await win.webContents.executeJavaScript(`(async () => {
    const img = new Image();
    img.src = ${JSON.stringify(toDataUrl(svg))};
    await img.decode();
    const canvas = document.createElement("canvas");
    canvas.width = 1024;
    canvas.height = 1024;
    canvas.getContext("2d").drawImage(img, ${rect.x}, ${rect.y}, ${rect.w}, ${rect.h});
    return canvas.toDataURL("image/png");
  })()`);
  return Buffer.from(dataUrl.split(",")[1], "base64");
}

app
  .whenReady()
  .then(async () => {
    if (process.platform === "darwin") app.dock?.hide();
    const win = new BrowserWindow({ show: false });
    await win.loadURL("about:blank");
    fs.mkdirSync(OUT_DIR, { recursive: true });
    const jobs = [
      ["icon.png", svgSource, { x: 0, y: 0, w: 1024, h: 1024 }],
      ["icon-mac.png", svgMac, { x: 100, y: 100, w: 824, h: 824 }],
    ];
    for (const [name, svg, rect] of jobs) {
      fs.writeFileSync(path.join(OUT_DIR, name), await render(win, svg, rect));
      console.log(`wrote assets/${name}`);
    }
    app.exit(0);
  })
  .catch((err) => {
    console.error(err);
    app.exit(1);
  });
