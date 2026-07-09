// Capture live-demo screenshots, waiting for client-side data to load.
import puppeteer from "puppeteer-core";
import { mkdirSync } from "fs";

const CHROME = "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
const F = "http://localhost:3000";
const TID = "054a5738-8033-4e8b-b8da-c8b15cad4217";
const DIR = "C:\\Users\\dheer\\CX agent\\docs\\images";
mkdirSync(DIR, { recursive: true });

const shots = [
  { f: "01-chat.png", u: `${F}/`, ready: () => document.body.innerText.includes("support assistant"), h: 900 },
  { f: "02-dashboard.png", u: `${F}/ops`, ready: () => document.querySelectorAll("tbody tr").length > 0, h: 1000 },
  { f: "03-trace.png", u: `${F}/ops?conversation=${TID}`, ready: () => !document.body.innerText.includes("Select a conversation"), h: 1050 },
  { f: "04-impact.png", u: `${F}/ops/impact`, ready: () => !!document.querySelector("svg.recharts-surface"), full: true },
  { f: "05-insights.png", u: `${F}/ops/insights`, ready: () => /workflow|escalation|Most-used|volume/.test(document.body.innerText), full: true },
  { f: "06-report.png", u: `${F}/report`, ready: () => document.querySelectorAll("table tbody tr").length > 3, full: true },
  { f: "07-voice.png", u: `${F}/voice`, ready: () => document.body.innerText.includes("Tap to start"), h: 900 },
];

const browser = await puppeteer.launch({
  executablePath: CHROME,
  headless: "new",
  args: ["--no-sandbox", "--hide-scrollbars"],
  defaultViewport: { width: 1440, height: 900 },
});

for (const s of shots) {
  const page = await browser.newPage();
  try {
    await page.goto(s.u, { waitUntil: "domcontentloaded", timeout: 60000 });
    await page.addStyleTag({
      content: "#__next-build-watcher,nextjs-portal,[data-nextjs-toast],[data-next-badge-root]{display:none!important}",
    });
    let loaded = true;
    try {
      await page.waitForFunction(s.ready, { timeout: 30000, polling: 500 });
    } catch {
      loaded = false;
    }
    if (!s.full) await page.setViewport({ width: 1440, height: s.h || 900 });
    await new Promise((r) => setTimeout(r, 1800)); // settle charts / count-up animations
    await page.screenshot({ path: `${DIR}\\${s.f}`, fullPage: !!s.full });
    console.log(`${s.f} ${loaded ? "ok (data loaded)" : "ok (wait timed out)"}`);
  } catch (e) {
    console.log(`${s.f} FAILED: ${e.message}`);
  } finally {
    await page.close();
  }
}
await browser.close();
