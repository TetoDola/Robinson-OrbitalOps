// Downloads all remote assets from terminal-industries.com into public/.
// Run: node scripts/download-assets.mjs
import { mkdir, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const PUBLIC = join(ROOT, "public");

/** [remoteUrl, localRelativePath] */
const ASSETS = [
  // ---- Hero video carousel clips (vid_3-*) ----
  ["https://a.storyblok.com/f/337048/x/f0f51ea10f/vid_3-1_prerender_1.mp4", "videos/hero-1.mp4"],
  ["https://a.storyblok.com/f/337048/x/5d1992bef6/vid_3-2_prerender_1.mp4", "videos/hero-2.mp4"],
  ["https://a.storyblok.com/f/337048/x/5c039660e1/vid_3-3_prerender_1.mp4", "videos/hero-3.mp4"],
  ["https://a.storyblok.com/f/337048/x/daeedd63c8/vid_3-5_prerender_1.mp4", "videos/hero-4.mp4"],
  // ---- Fullscreen-features benefit clips (vid_4-*, vid_5-*) ----
  ["https://a.storyblok.com/f/337048/x/85fd9d83d7/vid_4-1_wide_prerender_1.mp4", "videos/benefit-1-wide.mp4"],
  ["https://a.storyblok.com/f/337048/x/cd4b14d97d/vid_4-2_vert_prerender_1.mp4", "videos/benefit-2-vert.mp4"],
  ["https://a.storyblok.com/f/337048/x/0f153ebd58/vid_4-3_wide_v02_1.mp4", "videos/benefit-3-wide.mp4"],
  ["https://a.storyblok.com/f/337048/x/408e8d26ba/vid_5-4_prerender_1.mp4", "videos/benefit-4.mp4"],
  ["https://a.storyblok.com/f/337048/x/cbcaf12722/hp-where-4.mp4", "videos/hp-where.mp4"],
  // ---- Logo wall (top: "brands you know") ----
  ["https://a.storyblok.com/f/337048/1280x395/5d869ff961/dsv-b-w.svg", "images/brands/dsv.svg"],
  ["https://a.storyblok.com/f/337048/170x44/9386c9fae8/lineage.svg", "images/brands/lineage.svg"],
  ["https://a.storyblok.com/f/337048/160x120/90aa0c203e/goodyear2.svg", "images/brands/goodyear.svg"],
  ["https://a.storyblok.com/f/337048/160x80/22de92909e/ocean-spray-2.svg", "images/brands/ocean-spray.svg"],
  ["https://a.storyblok.com/f/337048/2500x702/f030eafaea/culligan-water.svg", "images/brands/culligan.svg"],
  ["https://a.storyblok.com/f/337048/161x62/44ea74f049/nfi.svg", "images/brands/nfi.svg"],
  ["https://a.storyblok.com/f/337048/176x49/27affef2ea/ryder-green.svg", "images/brands/ryder.svg"],
  ["https://a.storyblok.com/f/337048/2500x2500/6c9f6434ea/hp.svg", "images/brands/hp.svg"],
  ["https://a.storyblok.com/f/337048/1280x319/621d5efa86/tjx-b-w.svg", "images/brands/tjx.svg"],
  ["https://a.storyblok.com/f/337048/249x47/15a7349d4e/prologis.svg", "images/brands/prologis.svg"],
  ["https://a.storyblok.com/f/337048/900x500/fe6a1384ae/vince-logo-vector.png", "images/brands/vince.png"],
  // ---- Logo grid (investors: "Built by the Industry") ----
  ["https://a.storyblok.com/f/337048/1366x768/f672774b7b/untitled-design-2.svg", "images/investors/inv-1.svg"],
  ["https://a.storyblok.com/f/337048/1366x768/3b2ae6c538/rac-b-w-website.svg", "images/investors/rac.svg"],
  ["https://a.storyblok.com/f/337048/1366x768/802a86b588/marc-jacobs2.svg", "images/investors/marc-jacobs.svg"],
  ["https://a.storyblok.com/f/337048/1280x302/92b80c4809/pods-b-w-1.svg", "images/investors/pods.svg"],
  ["https://a.storyblok.com/f/337048/1280x142/4da4eb329e/foxconn-b-w.svg", "images/investors/foxconn.svg"],
  ["https://a.storyblok.com/f/337048/200x100/3cd9d313bd/nine-west-b-w-200-x-100-px-1.svg", "images/investors/nine-west.svg"],
  ["https://a.storyblok.com/f/337048/3840x1181/df7256d5e0/kirkland-b-w.svg", "images/investors/kirkland.svg"],
  ["https://a.storyblok.com/f/337048/869x147/26858fd378/db-schenker-2.svg", "images/investors/db-schenker.svg"],
  ["https://a.storyblok.com/f/337048/225x225/fc77667383/kasper-logo.png", "images/investors/kasper.png"],
  ["https://a.storyblok.com/f/337048/114x45/04e08dca33/8vc.svg", "images/investors/8vc.svg"],
  ["https://a.storyblok.com/f/337048/1130x140/8e14227e2e/logo-stripe.png", "images/investors/logo-stripe.png"],
  // ---- Quote image ----
  ["https://a.storyblok.com/f/337048/5112x3410/74c4e40128/quote-image.jpg/m/1680x0/filters:format(webp):quality(85)", "images/sections/quote-image.webp"],
  // ---- Misc / footer ----
  ["https://terminal-industries.com/static/images/gartner.svg", "images/gartner.svg"],
  ["https://terminal-industries.com/static/images/linkedin.svg", "images/social/linkedin.svg"],
  ["https://terminal-industries.com/static/images/x.svg", "images/social/x.svg"],
  ["https://terminal-industries.com/static/images/youtube.svg", "images/social/youtube.svg"],
  // ---- Favicons / SEO ----
  ["https://terminal-industries.com/static/apple-touch-icon.png", "seo/apple-touch-icon.png"],
  ["https://terminal-industries.com/static/favicon-96x96.png", "seo/favicon-96x96.png"],
  ["https://terminal-industries.com/static/favicon-192x192.png", "seo/favicon-192x192.png"],
  ["https://terminal-industries.com/static/favicon-512x512.png", "seo/favicon-512x512.png"],
  ["https://terminal-industries.com/static/favicon.svg", "seo/favicon.svg"],
  ["https://terminal-industries.com/static/favicon.ico", "seo/favicon.ico"],
  ["https://terminal-industries.com/static/site.webmanifest", "seo/site.webmanifest"],
  ["https://a.storyblok.com/f/337048/1600x960/af6630c057/social-image.webp", "seo/social-image.webp"],
];

async function download([url, rel]) {
  const dest = join(PUBLIC, rel);
  await mkdir(dirname(dest), { recursive: true });
  try {
    const res = await fetch(url, { headers: { "User-Agent": "Mozilla/5.0" } });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const buf = Buffer.from(await res.arrayBuffer());
    await writeFile(dest, buf);
    console.log(`OK  ${rel} (${(buf.length / 1024).toFixed(1)} KB)`);
    return true;
  } catch (err) {
    console.error(`ERR ${rel}: ${err.message}`);
    return false;
  }
}

async function run() {
  let ok = 0;
  for (let i = 0; i < ASSETS.length; i += 4) {
    const batch = ASSETS.slice(i, i + 4);
    const results = await Promise.all(batch.map(download));
    ok += results.filter(Boolean).length;
  }
  console.log(`\nDone: ${ok}/${ASSETS.length} downloaded.`);
}

run();
