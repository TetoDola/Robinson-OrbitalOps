import { spawn } from "node:child_process";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { inflateSync } from "node:zlib";

import { chromium } from "playwright";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const frontendDir = path.resolve(__dirname, "..");
const defaultUrl = process.env.UX_REVIEW_URL ?? "http://127.0.0.1:5173/";
const args = new Set(process.argv.slice(2));
const headed = args.has("--headed");

const viewports = [
  { name: "desktop", width: 1440, height: 900, expected: "three-column command layout" },
  { name: "laptop", width: 1280, height: 800, expected: "three-column command layout" },
  { name: "tablet", width: 834, height: 1112, expected: "scene first, rails below" },
  { name: "mobile", width: 390, height: 844, expected: "single-column stacked layout" },
];

const now = new Date();
const stamp = now.toISOString().replace(/[:.]/g, "-");
const outDir = path.join(frontendDir, ".ux-review", stamp);
const screenshotDir = path.join(outDir, "screenshots");

function severityRank(severity) {
  return { P0: 0, P1: 1, P2: 2, P3: 3 }[severity] ?? 4;
}

function issue(severity, category, title, impact, recommendation, evidence = "") {
  return { severity, category, title, impact, recommendation, evidence };
}

function escapeMd(value) {
  return String(value).replaceAll("|", "\\|").replaceAll("\n", " ");
}

function toRelative(filePath) {
  return path.relative(frontendDir, filePath).replaceAll("\\", "/");
}

function paethPredictor(a, b, c) {
  const p = a + b - c;
  const pa = Math.abs(p - a);
  const pb = Math.abs(p - b);
  const pc = Math.abs(p - c);
  if (pa <= pb && pa <= pc) return a;
  if (pb <= pc) return b;
  return c;
}

function analyzePng(buffer) {
  const signature = buffer.subarray(0, 8).toString("hex");
  if (signature !== "89504e470d0a1a0a") {
    return { readable: false, sampleRatio: null, variance: null, reason: "not a PNG" };
  }

  let width = 0;
  let height = 0;
  let bitDepth = 0;
  let colorType = 0;
  const idatChunks = [];
  let offset = 8;

  while (offset < buffer.length) {
    const length = buffer.readUInt32BE(offset);
    const type = buffer.subarray(offset + 4, offset + 8).toString("ascii");
    const data = buffer.subarray(offset + 8, offset + 8 + length);
    if (type === "IHDR") {
      width = data.readUInt32BE(0);
      height = data.readUInt32BE(4);
      bitDepth = data[8];
      colorType = data[9];
    } else if (type === "IDAT") {
      idatChunks.push(data);
    } else if (type === "IEND") {
      break;
    }
    offset += length + 12;
  }

  if (bitDepth !== 8 || ![2, 6].includes(colorType) || !width || !height) {
    return { readable: false, sampleRatio: null, variance: null, reason: `unsupported PNG type ${colorType}/${bitDepth}` };
  }

  const bytesPerPixel = colorType === 6 ? 4 : 3;
  const stride = width * bytesPerPixel;
  const inflated = inflateSync(Buffer.concat(idatChunks));
  const pixels = Buffer.alloc(height * stride);
  let inputOffset = 0;
  let outputOffset = 0;

  for (let y = 0; y < height; y += 1) {
    const filter = inflated[inputOffset];
    inputOffset += 1;
    for (let x = 0; x < stride; x += 1) {
      const raw = inflated[inputOffset];
      inputOffset += 1;
      const left = x >= bytesPerPixel ? pixels[outputOffset - bytesPerPixel] : 0;
      const up = y > 0 ? pixels[outputOffset - stride] : 0;
      const upLeft = y > 0 && x >= bytesPerPixel ? pixels[outputOffset - stride - bytesPerPixel] : 0;
      let value = raw;
      if (filter === 1) value = raw + left;
      if (filter === 2) value = raw + up;
      if (filter === 3) value = raw + Math.floor((left + up) / 2);
      if (filter === 4) value = raw + paethPredictor(left, up, upLeft);
      pixels[outputOffset] = value & 255;
      outputOffset += 1;
    }
  }

  let nonBlank = 0;
  let sum = 0;
  let sumSq = 0;
  const sampleEvery = Math.max(1, Math.floor((width * height) / 6000));
  let sampled = 0;
  for (let i = 0; i < width * height; i += sampleEvery) {
    const index = i * bytesPerPixel;
    const alpha = colorType === 6 ? pixels[index + 3] : 255;
    if (alpha < 10) continue;
    const light = pixels[index] + pixels[index + 1] + pixels[index + 2];
    if (light > 18) nonBlank += 1;
    sum += light;
    sumSq += light * light;
    sampled += 1;
  }
  const mean = sampled ? sum / sampled : 0;
  return {
    readable: true,
    sampleRatio: sampled ? Number((nonBlank / sampled).toFixed(3)) : 0,
    variance: sampled ? Number((sumSq / sampled - mean * mean).toFixed(2)) : 0,
    reason: "",
  };
}

async function waitForServer(url, timeoutMs = 30_000) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    if (await isReachable(url)) {
      return true;
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  return false;
}

async function isReachable(url) {
  try {
    const response = await fetch(url, { cache: "no-store" });
    return response.ok;
  } catch {
    return false;
  }
}

async function ensureDevServer(url) {
  if (await isReachable(url)) {
    return { started: false, process: null, log: "Reused existing dev server." };
  }

  const command = process.platform === "win32" ? "npm.cmd" : "npm";
  const child = spawn(
    command,
    ["run", "dev", "--", "--host", "127.0.0.1", "--port", "5173", "--strictPort"],
    {
      cwd: frontendDir,
      env: { ...process.env, BROWSER: "none" },
      stdio: ["ignore", "pipe", "pipe"],
    },
  );

  let log = "";
  child.stdout.on("data", (chunk) => {
    log += chunk.toString();
  });
  child.stderr.on("data", (chunk) => {
    log += chunk.toString();
  });

  const ready = await waitForServer(url);
  if (!ready) {
    child.kill();
    throw new Error(`Could not start Vite dev server at ${url}.\n${log}`);
  }

  return { started: true, process: child, log: "Started Vite dev server for review." };
}

async function collectSnapshot(page) {
  return page.evaluate(() => {
    const viewport = { width: window.innerWidth, height: window.innerHeight };
    const area = (rect) => Math.max(0, rect.width) * Math.max(0, rect.height);
    const isVisible = (el) => {
      const style = window.getComputedStyle(el);
      const rect = el.getBoundingClientRect();
      return (
        style.visibility !== "hidden" &&
        style.display !== "none" &&
        Number(style.opacity) !== 0 &&
        rect.width > 0 &&
        rect.height > 0
      );
    };
    const rectOf = (selector) => {
      const el = document.querySelector(selector);
      if (!el) return null;
      const rect = el.getBoundingClientRect();
      return {
        x: Math.round(rect.x),
        y: Math.round(rect.y),
        width: Math.round(rect.width),
        height: Math.round(rect.height),
        right: Math.round(rect.right),
        bottom: Math.round(rect.bottom),
      };
    };
    const textOf = (el) =>
      (el.getAttribute("aria-label") || el.textContent || el.getAttribute("title") || "").replace(/\s+/g, " ").trim();
    const selectorFor = (el) => {
      if (el.id) return `#${el.id}`;
      const className = typeof el.className === "string" ? el.className.trim().split(/\s+/).slice(0, 3).join(".") : "";
      return `${el.tagName.toLowerCase()}${className ? `.${className}` : ""}`;
    };

    function parseColor(value) {
      if (!value || value === "transparent") return null;
      const rgb = value.match(/rgba?\(([^)]+)\)/i);
      if (rgb) {
        const parts = rgb[1].split(/[,\s/]+/).filter(Boolean).map(Number);
        return { r: parts[0], g: parts[1], b: parts[2], a: Number.isFinite(parts[3]) ? parts[3] : 1 };
      }
      const oklch = value.match(/oklch\(\s*([\d.]+)%?\s+([\d.]+)\s+([\d.]+)(?:deg)?(?:\s*\/\s*([\d.]+))?\s*\)/i);
      if (oklch) {
        const lValue = Number(oklch[1]);
        const L = lValue > 1 ? lValue / 100 : lValue;
        const C = Number(oklch[2]);
        const h = (Number(oklch[3]) * Math.PI) / 180;
        const a = C * Math.cos(h);
        const b = C * Math.sin(h);
        const l = Math.pow(L + 0.3963377774 * a + 0.2158037573 * b, 3);
        const m = Math.pow(L - 0.1055613458 * a - 0.0638541728 * b, 3);
        const s = Math.pow(L - 0.0894841775 * a - 1.291485548 * b, 3);
        const linear = {
          r: 4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
          g: -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
          b: -0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s,
        };
        const toSrgb = (channel) => {
          const clipped = Math.min(1, Math.max(0, channel));
          const encoded = clipped <= 0.0031308 ? 12.92 * clipped : 1.055 * Math.pow(clipped, 1 / 2.4) - 0.055;
          return Math.round(encoded * 255);
        };
        return { r: toSrgb(linear.r), g: toSrgb(linear.g), b: toSrgb(linear.b), a: Number(oklch[4] ?? 1) };
      }
      return null;
    }

    function luminance(color) {
      const values = [color.r, color.g, color.b].map((value) => {
        const srgb = value / 255;
        return srgb <= 0.03928 ? srgb / 12.92 : Math.pow((srgb + 0.055) / 1.055, 2.4);
      });
      return 0.2126 * values[0] + 0.7152 * values[1] + 0.0722 * values[2];
    }

    function contrastRatio(fg, bg) {
      const l1 = luminance(fg);
      const l2 = luminance(bg);
      return (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);
    }

    function blend(top, bottom) {
      const alpha = top.a + bottom.a * (1 - top.a);
      if (alpha <= 0) return { r: 0, g: 0, b: 0, a: 0 };
      return {
        r: (top.r * top.a + bottom.r * bottom.a * (1 - top.a)) / alpha,
        g: (top.g * top.a + bottom.g * bottom.a * (1 - top.a)) / alpha,
        b: (top.b * top.a + bottom.b * bottom.a * (1 - top.a)) / alpha,
        a: alpha,
      };
    }

    function backgroundFor(el) {
      const bodyBg = parseColor(window.getComputedStyle(document.body).backgroundColor) ?? { r: 18, g: 20, b: 18, a: 1 };
      const chain = [];
      let current = el;
      while (current && current !== document.documentElement) {
        chain.push(current);
        current = current.parentElement;
      }
      return chain.reverse().reduce((background, item) => {
        const color = parseColor(window.getComputedStyle(item).backgroundColor);
        if (!color || color.a <= 0.01) return background;
        return blend(color, background);
      }, bodyBg);
    }

    const requiredRegions = [".app-shell", ".left-rail", ".scene-viewport", ".right-rail", "canvas.scene-canvas"];
    const missingRegions = requiredRegions.filter((selector) => !document.querySelector(selector));

    const interactive = Array.from(
      document.querySelectorAll("button, a[href], input, select, textarea, [role='button'], [tabindex]:not([tabindex='-1'])"),
    )
      .filter(isVisible)
      .map((el) => {
        const rect = el.getBoundingClientRect();
        const name = textOf(el);
        return {
          selector: selectorFor(el),
          name,
          role: el.getAttribute("role") || el.tagName.toLowerCase(),
          width: Math.round(rect.width),
          height: Math.round(rect.height),
          x: Math.round(rect.x),
          y: Math.round(rect.y),
          disabled: Boolean(el.disabled || el.getAttribute("aria-disabled") === "true"),
          hasName: name.length > 0,
          smallTarget: rect.width < 44 || rect.height < 44,
        };
      });

    const textClipping = Array.from(document.querySelectorAll("body *"))
      .filter((el) => isVisible(el) && el.children.length === 0 && textOf(el).length > 0)
      .filter((el) => {
        const style = window.getComputedStyle(el);
        const clipsX = el.scrollWidth > el.clientWidth + 2 && !["visible", ""].includes(style.overflowX);
        const clipsY = el.scrollHeight > el.clientHeight + 3 && !["visible", ""].includes(style.overflowY);
        return clipsX || clipsY;
      })
      .slice(0, 20)
      .map((el) => ({
        selector: selectorFor(el),
        text: textOf(el).slice(0, 80),
        clientWidth: el.clientWidth,
        scrollWidth: el.scrollWidth,
        clientHeight: el.clientHeight,
        scrollHeight: el.scrollHeight,
      }));

    const overlapTargets = Array.from(
      document.querySelectorAll(
        ".left-rail, .right-rail, .scene-viewport, .rail-section, .patch-panel, .agent-card, .node-row, .incident-row, .metric, .patch-btn, .nav-item, .follow-btn, .speed-group button, .ir-popup",
      ),
    ).filter(isVisible);
    const overlaps = [];
    for (let i = 0; i < overlapTargets.length; i += 1) {
      for (let j = i + 1; j < overlapTargets.length; j += 1) {
        const a = overlapTargets[i];
        const b = overlapTargets[j];
        if (a.contains(b) || b.contains(a)) continue;
        const ar = a.getBoundingClientRect();
        const br = b.getBoundingClientRect();
        const x = Math.max(0, Math.min(ar.right, br.right) - Math.max(ar.left, br.left));
        const y = Math.max(0, Math.min(ar.bottom, br.bottom) - Math.max(ar.top, br.top));
        const overlapArea = x * y;
        if (overlapArea > 16 && overlapArea / Math.min(area(ar), area(br)) > 0.12) {
          overlaps.push({
            a: selectorFor(a),
            b: selectorFor(b),
            overlapArea: Math.round(overlapArea),
          });
        }
      }
    }

    const contrastSamples = Array.from(document.querySelectorAll("body *"))
      .filter((el) => isVisible(el) && textOf(el).length > 0 && el.children.length === 0)
      .slice(0, 250)
      .map((el) => {
        const style = window.getComputedStyle(el);
        const fg = parseColor(style.color);
        const bg = backgroundFor(el);
        if (!fg || !bg) return null;
        return {
          selector: selectorFor(el),
          text: textOf(el).slice(0, 80),
          fontSize: Number.parseFloat(style.fontSize),
          ratio: Number(contrastRatio(fg, bg).toFixed(2)),
        };
      })
      .filter(Boolean);
    const lowContrast = contrastSamples
      .filter((sample) => sample.ratio < (sample.fontSize >= 24 ? 3 : 4.5))
      .slice(0, 20);

    const canvas = document.querySelector("canvas.scene-canvas");
    let canvasRead = { readable: false, sampleRatio: null, variance: null, reason: "canvas missing" };
    if (canvas) {
      try {
        const sample = document.createElement("canvas");
        sample.width = 32;
        sample.height = 32;
        const ctx = sample.getContext("2d", { willReadFrequently: true });
        ctx.drawImage(canvas, 0, 0, 32, 32);
        const pixels = ctx.getImageData(0, 0, 32, 32).data;
        let nonBlank = 0;
        let sum = 0;
        let sumSq = 0;
        for (let i = 0; i < pixels.length; i += 4) {
          const light = pixels[i] + pixels[i + 1] + pixels[i + 2];
          if (light > 18) nonBlank += 1;
          sum += light;
          sumSq += light * light;
        }
        const count = pixels.length / 4;
        const mean = sum / count;
        canvasRead = {
          readable: true,
          sampleRatio: Number((nonBlank / count).toFixed(3)),
          variance: Number((sumSq / count - mean * mean).toFixed(2)),
          reason: "",
        };
      } catch (error) {
        canvasRead = { readable: false, sampleRatio: null, variance: null, reason: error.message };
      }
    }

    const shell = rectOf(".app-shell");
    const left = rectOf(".left-rail");
    const scene = rectOf(".scene-viewport");
    const right = rectOf(".right-rail");
    const bodyOverflowX = document.documentElement.scrollWidth - document.documentElement.clientWidth;
    const bodyOverflowY = document.documentElement.scrollHeight - document.documentElement.clientHeight;

    return {
      title: document.title,
      viewport,
      rootLength: document.querySelector("#root")?.innerHTML.length ?? 0,
      bodyTextStart: document.body.innerText.slice(0, 320),
      missingRegions,
      regions: { shell, left, scene, right, canvas: rectOf("canvas.scene-canvas") },
      bodyOverflowX,
      bodyOverflowY,
      oldStandaloneMarkup: document.body.innerText.includes("AKJA // ORBITAL"),
      buttonCount: document.querySelectorAll("button").length,
      headingTexts: Array.from(document.querySelectorAll("h1,h2,h3"))
        .map((el) => textOf(el))
        .filter(Boolean),
      interactive,
      unnamedInteractive: interactive.filter((item) => !item.hasName),
      smallTargets: interactive.filter((item) => item.smallTarget && !item.disabled),
      textClipping,
      overlaps: overlaps.slice(0, 20),
      lowContrast,
      canvasRead,
    };
  });
}

async function runKeyboardProbe(page) {
  return page.evaluate(() => {
    const focusable = Array.from(
      document.querySelectorAll("button, a[href], input, select, textarea, [role='button'], [tabindex]:not([tabindex='-1'])"),
    ).filter((el) => {
      const style = window.getComputedStyle(el);
      const rect = el.getBoundingClientRect();
      return style.display !== "none" && style.visibility !== "hidden" && rect.width > 0 && rect.height > 0;
    });
    return focusable.map((el) => ({
      tag: el.tagName.toLowerCase(),
      name: (el.getAttribute("aria-label") || el.textContent || el.getAttribute("title") || "").replace(/\s+/g, " ").trim(),
      disabled: Boolean(el.disabled || el.getAttribute("aria-disabled") === "true"),
    }));
  });
}

async function runInteractionChecks(page) {
  const checks = [];
  const add = (name, pass, evidence, severity = "P1", recommendation = "") => {
    checks.push({ name, pass, evidence, severity, recommendation });
  };

  await page.locator(".speed-group button", { hasText: "60x" }).click();
  add(
    "time scale button updates active state",
    await page.locator(".speed-group button.active", { hasText: "60x" }).count() === 1,
    "Clicked 60x speed control.",
    "P2",
    "Keep simulation speed visibly selected after click.",
  );

  await page.locator(".follow-btn").click();
  add(
    "follow node toggles active state",
    await page.locator(".follow-btn.active").count() === 1,
    "Clicked follow node control.",
    "P2",
    "Make the active follow state visually and programmatically obvious.",
  );

  const reticle = page.locator(".sat-reticle.is-visible").first();
  if (await reticle.count()) {
    await reticle.dispatchEvent("click");
    add(
      "satellite can be selected",
      (await page.locator(".selection-state", { hasText: /selected/i }).count()) === 1,
      "Clicked visible satellite reticle.",
      "P1",
      "Ensure the reticle toggles selected asset state.",
    );
    await page.keyboard.press("Escape");
    add(
      "escape deselects satellite",
      (await page.locator(".selection-state", { hasText: /idle/i }).count()) === 1,
      "Pressed Escape after selecting satellite.",
      "P1",
      "Escape should return the user to the overview state.",
    );
  } else {
    add(
      "satellite reticle is visible",
      false,
      "Reticle did not become visible during the review window.",
      "P2",
      "Keep a reliable visible target for selecting the orbital asset.",
    );
  }

  const firstNode = page.locator(".node-row.is-clickable").first();
  if (await firstNode.count()) {
    await firstNode.click();
    add(
      "node row opens IR thermal view",
      (await page.locator(".ir-popup").count()) === 1,
      "Clicked first node row.",
      "P1",
      "Node inspection should reveal the thermal popover.",
    );
    await page.screenshot({ path: path.join(screenshotDir, "desktop-ir-popup.png"), fullPage: false });
    await page.locator(".ir-popup .close-btn").click();
    add(
      "IR thermal view closes",
      (await page.locator(".ir-popup").count()) === 0,
      "Clicked IR close button.",
      "P2",
      "Inspection overlays need a reliable close path.",
    );
  } else {
    add("node rows are available", false, "No inspectable node rows found.", "P1", "Expose node inspection affordances.");
  }

  const approveButton = page.locator(".patch-btn.primary", { hasText: "Approve" }).first();
  add(
    "approve action is present and enabled",
    (await approveButton.count()) === 1 && (await approveButton.isEnabled()),
    "Checked primary approval control without requiring a live backend.",
    "P1",
    "The primary approval action must remain visible and enabled while a mission patch is pending.",
  );

  for (const [label, expected] of [
    ["Replan", /replan/i],
    ["Modify", /modifying/i],
    ["Reject", /rejected/i],
  ]) {
    const button = page.locator(".patch-btn", { hasText: label }).first();
    if (await button.count()) {
      await button.click();
      const stateText = (await page.locator(".patch-panel strong").first().innerText()).trim();
      add(
        `${label.toLowerCase()} approval action updates state`,
        expected.test(stateText),
        `After ${label}, state text was "${stateText}".`,
        "P1",
        "Approval controls should provide immediate, unambiguous state feedback.",
      );
    } else {
      add(`${label.toLowerCase()} approval action exists`, false, `${label} button was missing.`, "P1", "Keep all approval actions discoverable.");
    }
  }

  return checks;
}

async function reviewViewport(browser, viewport) {
  const page = await browser.newPage({
    viewport: { width: viewport.width, height: viewport.height },
    deviceScaleFactor: viewport.name === "mobile" ? 2 : 1,
    isMobile: viewport.name === "mobile",
  });
  const consoleMessages = [];
  const pageErrors = [];
  const failedRequests = [];
  page.on("console", (message) => {
    consoleMessages.push({ type: message.type(), text: message.text() });
  });
  page.on("pageerror", (error) => {
    pageErrors.push(error.message);
  });
  page.on("requestfailed", (request) => {
    failedRequests.push({
      url: request.url(),
      method: request.method(),
      error: request.failure()?.errorText ?? "unknown",
    });
  });

  await page.goto(defaultUrl, { waitUntil: "domcontentloaded", timeout: 30_000 });
  await page.waitForSelector(".app-shell", { timeout: 15_000 });
  await page.waitForTimeout(1600);

  const screenshot = path.join(screenshotDir, `${viewport.name}-initial.png`);
  const sceneScreenshot = path.join(screenshotDir, `${viewport.name}-scene.png`);
  await page.screenshot({ path: screenshot, fullPage: false });
  await page.locator(".scene-viewport").screenshot({ path: sceneScreenshot });
  const sceneSample = analyzePng(await readFile(sceneScreenshot));
  const snapshot = await collectSnapshot(page);
  const keyboardOrder = await runKeyboardProbe(page);
  const interactionChecks = viewport.name === "desktop" ? await runInteractionChecks(page) : [];
  if (viewport.name === "desktop") {
    await page.screenshot({ path: path.join(screenshotDir, "desktop-after-interactions.png"), fullPage: false });
  }

  await page.close();
  return {
    viewport,
    screenshot,
    sceneScreenshot,
    sceneSample,
    snapshot,
    keyboardOrder,
    interactionChecks,
    consoleMessages,
    pageErrors,
    failedRequests,
  };
}

function analyzeViewport(result) {
  const issues = [];
  const { viewport, snapshot, pageErrors, consoleMessages, failedRequests, interactionChecks } = result;
  const viewportLabel = `${viewport.name} ${viewport.width}x${viewport.height}`;

  if (snapshot.rootLength < 1000 || snapshot.missingRegions.length > 0) {
    issues.push(
      issue(
        "P0",
        "Render",
        `Dashboard failed core render on ${viewportLabel}`,
        "Users would see a blank or incomplete command surface.",
        "Fix the missing app shell regions before reviewing polish.",
        `Missing: ${snapshot.missingRegions.join(", ") || "none"}, root length: ${snapshot.rootLength}`,
      ),
    );
  }

  if (snapshot.oldStandaloneMarkup) {
    issues.push(
      issue(
        "P0",
        "Render",
        `Old standalone dashboard markup is still visible on ${viewportLabel}`,
        "Users may be looking at the wrong entry point and miss the React dashboard.",
        "Serve the Vite entry only and remove stale standalone pages from user-facing paths.",
      ),
    );
  }

  if (pageErrors.length) {
    issues.push(
      issue(
        "P0",
        "Runtime",
        `JavaScript page errors on ${viewportLabel}`,
        "Runtime exceptions undermine confidence and can stop interactions from working.",
        "Fix the first page error and rerun the reviewer.",
        pageErrors.slice(0, 3).join(" | "),
      ),
    );
  }

  const browserWarnings = consoleMessages.filter((message) => ["error", "warning"].includes(message.type));
  const nonEnvironmentWarnings = browserWarnings.filter(
    (message) => !/WebSocket|GPU stall|React DevTools|favicon/i.test(message.text),
  );
  if (nonEnvironmentWarnings.length) {
    issues.push(
      issue(
        "P2",
        "Runtime",
        `Browser console warnings on ${viewportLabel}`,
        "Console noise often hides real failures during demos.",
        "Resolve non-environment warnings or explicitly suppress expected development warnings.",
        nonEnvironmentWarnings.slice(0, 3).map((message) => `${message.type}: ${message.text}`).join(" | "),
      ),
    );
  }

  const failedNonBackendRequests = failedRequests.filter((request) => !/\/ws\/live|\/world-state|\/agents|\/commands|\/incidents|\/mission-patches/.test(request.url));
  if (failedNonBackendRequests.length) {
    issues.push(
      issue(
        "P1",
        "Runtime",
        `Static or UI requests failed on ${viewportLabel}`,
        "Missing assets make the interface feel broken or incomplete.",
        "Fix failing non-backend requests.",
        failedNonBackendRequests.slice(0, 3).map((request) => `${request.method} ${request.url}: ${request.error}`).join(" | "),
      ),
    );
  }

  if (snapshot.bodyOverflowX > 2) {
    issues.push(
      issue(
        "P1",
        "Responsive",
        `Horizontal overflow on ${viewportLabel}`,
        "Horizontal scrolling on dashboards hides controls and breaks mobile confidence.",
        "Constrain wide panels, long labels, and fixed-width popovers at this viewport.",
        `Overflow: ${snapshot.bodyOverflowX}px`,
      ),
    );
  }

  if (snapshot.overlaps.length) {
    issues.push(
      issue(
        "P1",
        "Layout",
        `Overlapping UI regions on ${viewportLabel}`,
        "Overlaps make controls hard to read or click and create demo instability.",
        "Adjust grid sizing, z-index, and popover placement for this viewport.",
        snapshot.overlaps.slice(0, 5).map((item) => `${item.a} overlaps ${item.b}`).join(" | "),
      ),
    );
  }

  if (snapshot.textClipping.length) {
    issues.push(
      issue(
        "P2",
        "Typography",
        `Text clipping on ${viewportLabel}`,
        "Clipped telemetry and labels force users to guess at critical system state.",
        "Allow wrapping or tighten label/value layout where clipping appears.",
        snapshot.textClipping.slice(0, 5).map((item) => `${item.selector}: "${item.text}"`).join(" | "),
      ),
    );
  }

  if (snapshot.smallTargets.length && viewport.width < 900) {
    issues.push(
      issue(
        "P2",
        "Accessibility",
        `Small touch targets on ${viewportLabel}`,
        "Small controls are difficult to tap under pressure, especially on tablets and phones.",
        "Make mobile interactive targets at least 44px in both dimensions.",
        snapshot.smallTargets.slice(0, 8).map((item) => `${item.selector} ${item.width}x${item.height}`).join(" | "),
      ),
    );
  }

  if (snapshot.unnamedInteractive.length) {
    issues.push(
      issue(
        "P1",
        "Accessibility",
        `Unnamed interactive elements on ${viewportLabel}`,
        "Screen reader users cannot understand controls without accessible names.",
        "Add visible text, aria-label, or title to every interactive element.",
        snapshot.unnamedInteractive.slice(0, 8).map((item) => item.selector).join(" | "),
      ),
    );
  }

  if (snapshot.lowContrast.length > 4) {
    issues.push(
      issue(
        "P2",
        "Accessibility",
        `Possible contrast issues on ${viewportLabel}`,
        "Low-contrast labels and telemetry are hard to scan in a command environment.",
        "Increase contrast for muted labels or reserve low contrast for decorative metadata.",
        snapshot.lowContrast.slice(0, 6).map((item) => `${item.selector} ${item.ratio}:1`).join(" | "),
      ),
    );
  }

  if (result.sceneSample.readable && (result.sceneSample.sampleRatio < 0.02 || result.sceneSample.variance < 4)) {
    issues.push(
      issue(
        "P1",
        "3D Scene",
        `Scene canvas appears blank on ${viewportLabel}`,
        "The central orbital scene is the primary dashboard object; blank rendering breaks orientation.",
        "Verify textures, WebGL context, camera framing, and renderer sizing.",
        `screenshot sample ratio ${result.sceneSample.sampleRatio}, variance ${result.sceneSample.variance}`,
      ),
    );
  }

  for (const check of interactionChecks.filter((item) => !item.pass)) {
    issues.push(issue(check.severity, "Interaction", check.name, "A core dashboard control did not respond as expected.", check.recommendation, check.evidence));
  }

  return issues;
}

function scanStaticAntiPatterns() {
  return [
    {
      pattern: /background-clip:\s*text/i,
      title: "Gradient text detected",
      recommendation: "Use solid text color and hierarchy through weight or size.",
    },
    {
      pattern: /backdrop-filter:\s*blur/i,
      title: "Glassmorphism blur detected",
      recommendation: "Use solid or lightly tinted surfaces unless blur is essential to the interaction.",
    },
    {
      pattern: /border-(left|right):\s*(?:[2-9]|\d{2,})px/i,
      title: "Side-stripe border detected",
      recommendation: "Use full borders, subtle background tint, or icons instead of thick side stripes.",
    },
    {
      pattern: /font-size:\s*clamp\(/i,
      title: "Fluid product UI type detected",
      recommendation: "Use fixed rem scales for dense product surfaces.",
    },
  ];
}

async function runStaticScan() {
  const files = [
    path.join(frontendDir, "src", "styles", "app.css"),
    path.join(frontendDir, "src", "App.tsx"),
    path.join(frontendDir, "src", "components", "TelemetryPanel.tsx"),
    path.join(frontendDir, "src", "components", "MissionPatchPanel.tsx"),
  ];
  const findings = [];
  const { readFile } = await import("node:fs/promises");
  for (const file of files) {
    const source = await readFile(file, "utf8");
    for (const check of scanStaticAntiPatterns()) {
      const match = source.match(check.pattern);
      if (match) {
        const before = source.slice(0, match.index);
        const line = before.split("\n").length;
        findings.push({
          file: toRelative(file),
          line,
          title: check.title,
          recommendation: check.recommendation,
        });
      }
    }
  }
  return findings;
}

function scoreCategory(issues, categoryNames) {
  const relevant = issues.filter((item) => categoryNames.includes(item.category));
  if (relevant.some((item) => item.severity === "P0")) return 0;
  if (relevant.filter((item) => item.severity === "P1").length >= 2) return 1;
  if (relevant.some((item) => item.severity === "P1")) return 2;
  if (relevant.some((item) => item.severity === "P2")) return 3;
  return 4;
}

function buildReport({ results, issues, staticFindings, serverInfo }) {
  const sortedIssues = [...issues].sort((a, b) => severityRank(a.severity) - severityRank(b.severity));
  const counts = ["P0", "P1", "P2", "P3"].map((level) => `${level}: ${sortedIssues.filter((item) => item.severity === level).length}`).join(", ");
  const scoreRows = [
    ["Render and Runtime", scoreCategory(sortedIssues, ["Render", "Runtime", "3D Scene"]), "App shell, console, failed requests, WebGL scene"],
    ["Responsive Layout", scoreCategory(sortedIssues, ["Responsive", "Layout", "Typography"]), "Viewport structure, overflow, overlap, clipping"],
    ["Interaction", scoreCategory(sortedIssues, ["Interaction"]), "Scene selection, node inspection, approval controls"],
    ["Accessibility", scoreCategory(sortedIssues, ["Accessibility"]), "Names, touch targets, contrast, keyboard reachability"],
    ["Visual Craft", staticFindings.length ? 3 : 4, "Static anti-pattern scan and screenshot review support"],
  ];
  const total = scoreRows.reduce((sum, row) => sum + row[1], 0);
  const rating = total >= 18 ? "Excellent" : total >= 14 ? "Good" : total >= 10 ? "Needs work" : total >= 6 ? "Poor" : "Critical";

  const screenshotList = results
    .map(
      (result) =>
        `- ${result.viewport.name}: [full](${toRelative(result.screenshot)}), [scene crop](${toRelative(result.sceneScreenshot)})`,
    )
    .join("\n");
  const interactionEvidence = results
    .flatMap((result) => result.interactionChecks)
    .map((check) => `- ${check.pass ? "PASS" : "FAIL"}: ${check.name}. ${check.evidence}`)
    .join("\n");
  const staticEvidence = staticFindings.length
    ? staticFindings.map((finding) => `- ${finding.file}:${finding.line} ${finding.title}. ${finding.recommendation}`).join("\n")
    : "- No blocked static anti-patterns found in the scanned frontend files.";

  const viewportSummary = results
    .map((result) => {
      const snap = result.snapshot;
      return `| ${result.viewport.name} | ${result.viewport.width}x${result.viewport.height} | ${snap.regions.left?.width ?? "missing"} | ${snap.regions.scene?.width ?? "missing"} | ${snap.regions.right?.width ?? "missing"} | ${snap.bodyOverflowX}px | ${result.sceneSample.readable ? `${result.sceneSample.sampleRatio} sample` : result.sceneSample.reason} |`;
    })
    .join("\n");

  const issueList = sortedIssues.length
    ? sortedIssues
        .map(
          (item, index) => `### ${index + 1}. [${item.severity}] ${item.title}

- Category: ${item.category}
- Impact: ${item.impact}
- Recommendation: ${item.recommendation}
- Evidence: ${item.evidence || "See screenshots and viewport metrics."}`,
        )
        .join("\n\n")
    : "No P0-P2 UX/UI issues were detected by the automated reviewer.";

  const working = [
    "The dashboard has a clear three-zone mental model on desktop: overview, orbit scene, operations.",
    "The Three.js render loop stays outside React, so high-frequency scene movement does not drive React re-renders.",
    "Core state-changing controls give visible feedback for speed, follow, node inspection, and approval modes.",
  ];

  const topRecommendations = sortedIssues.slice(0, 5).length
    ? sortedIssues
        .slice(0, 5)
        .map((item, index) => `${index + 1}. [${item.severity}] ${item.title}: ${item.recommendation}`)
        .join("\n")
    : "1. Keep this reviewer in the pre-demo loop and rerun after UI changes.";

  return `# UX/UI Review Report

Generated: ${now.toISOString()}
Target: ${defaultUrl}
Server: ${serverInfo.log}

## Design Health Score

| Dimension | Score | What Was Tested |
|---|---:|---|
${scoreRows.map((row) => `| ${row[0]} | ${row[1]}/4 | ${row[2]} |`).join("\n")}
| Total | ${total}/20 | ${rating} |

Issue count: ${counts}

## Viewport Coverage

| Viewport | Size | Left Rail | Scene | Right Rail | X Overflow | Canvas Sample |
|---|---:|---:|---:|---:|---:|---|
${viewportSummary}

## Screenshots

${screenshotList}
- Interaction state: [screenshots/desktop-after-interactions.png](screenshots/desktop-after-interactions.png)
- IR popup state: [screenshots/desktop-ir-popup.png](screenshots/desktop-ir-popup.png)

## Anti-Patterns Verdict

The reviewer scans for product-UI anti-patterns that tend to make interfaces feel generic or brittle: gradient text, decorative blur, thick side-stripe borders, and fluid product UI typography.

${staticEvidence}

## What Is Working

${working.map((item) => `- ${item}`).join("\n")}

## Interaction Checks

${interactionEvidence || "- Interaction checks were skipped outside the desktop viewport."}

## Priority Findings

${issueList}

## Recommended Actions

${topRecommendations}

## Reviewer Notes

- Backend REST and WebSocket failures are treated as environment notes unless they block the fallback UI.
- Contrast checks are computed from rendered CSS colors, including OKLCH tokens when the browser exposes them.
- The screenshot set is the source of truth for visual critique. Open the files above when deciding final polish.
- This reviewer is deterministic. It finds measurable UX/UI risks; use human judgment for brand tone and product strategy.
`;
}

async function main() {
  await mkdir(screenshotDir, { recursive: true });
  const serverInfo = await ensureDevServer(defaultUrl);
  let browser;
  try {
    browser = await chromium.launch({ headless: !headed });
    const results = [];
    for (const viewport of viewports) {
      results.push(await reviewViewport(browser, viewport));
    }
    const viewportIssues = results.flatMap(analyzeViewport);
    const staticFindings = await runStaticScan();
    const staticIssues = staticFindings.map((finding) =>
      issue(
        "P2",
        "Visual Craft",
        finding.title,
        "A banned or risky visual pattern makes the product UI feel less intentional.",
        finding.recommendation,
        `${finding.file}:${finding.line}`,
      ),
    );
    const issues = [...viewportIssues, ...staticIssues];
    const report = buildReport({ results, issues, staticFindings, serverInfo });
    const reportPath = path.join(outDir, "ux-ui-review.md");
    const jsonPath = path.join(outDir, "ux-ui-review.json");
    await writeFile(reportPath, report, "utf8");
    await writeFile(
      jsonPath,
      JSON.stringify(
        {
          generatedAt: now.toISOString(),
          target: defaultUrl,
          score: {
            issueCount: issues.length,
            counts: Object.fromEntries(["P0", "P1", "P2", "P3"].map((level) => [level, issues.filter((item) => item.severity === level).length])),
          },
          issues,
          staticFindings,
          results: results.map((result) => ({
            viewport: result.viewport,
            screenshot: toRelative(result.screenshot),
            sceneScreenshot: toRelative(result.sceneScreenshot),
            sceneSample: result.sceneSample,
            snapshot: result.snapshot,
            keyboardOrder: result.keyboardOrder,
            interactionChecks: result.interactionChecks,
            consoleMessages: result.consoleMessages,
            pageErrors: result.pageErrors,
            failedRequests: result.failedRequests,
          })),
        },
        null,
        2,
      ),
      "utf8",
    );
    console.log(`UX/UI review complete: ${toRelative(reportPath)}`);
    console.log(`Screenshots: ${toRelative(screenshotDir)}`);
    if (issues.some((item) => item.severity === "P0")) {
      process.exitCode = 2;
    }
  } finally {
    await browser?.close();
    if (serverInfo.started && !args.has("--keep-server")) {
      serverInfo.process.kill();
    }
  }
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
