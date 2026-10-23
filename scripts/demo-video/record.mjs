// Records the silent CLEARWAY demo in headless Chrome: no browser chrome, a drawn pointer, 1920x1200.
// Serve the built app with live agents on (local .env keys), then record:
//   cd web && npm run build
//   cd ../backend && CLEARWAY_ALLOW_LIVE=1 uv run uvicorn clearway.api:app --port 8000
//   node scripts/demo-video/record.mjs        (writes scripts/demo-video/out/; prints the ffmpeg line)
// One take spends ~$0.003 of Nemotron (Super + one Ultra paragraph) and 3 Tavily credits.
import { launch, sleep } from "./cdp.mjs";
import { mkdirSync, rmSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const URL_ = process.env.DEMO_URL ?? "http://127.0.0.1:8000/";
const DIR = fileURLToPath(new URL("./out/", import.meta.url));
rmSync(DIR + "frames", { recursive: true, force: true });   // only the frames: finished videos stay
mkdirSync(DIR + "frames", { recursive: true });

const W = 1440, H = 900;
const b = await launch({ width: W, height: H, scale: 4 / 3, port: 9361 });
const cues = [];
const cue = (text) => { cues.push({ at: b.mark(), text }); console.log(b.mark().toFixed(1), text); };
const hover = (x, y) => b.moveTo({ x, y });

const top = (sel, text = "") => b.evaluate(`(() => {
  const e = [...document.querySelectorAll(${JSON.stringify(sel)})].find((e) => e.textContent.includes(${JSON.stringify(text)}));
  return e ? e.getBoundingClientRect().top + scrollY : null; })()`);
const scrollTo = (y) => b.evaluate(`window.scrollTo({ top: ${Math.max(0, Math.round(y))}, behavior: "smooth" })`);
const scrollToEl = async (sel, text = "", offset = 120, wait = 1300) => {
  const y = await top(sel, text);
  if (y == null) throw new Error(`missing ${sel} ${text}`);
  await scrollTo(y - offset); await sleep(wait);
};
// click a control, first scrolling it into view if the camera can't see it. The pointer moves
// there, then the element itself is clicked: after the long brief renders, CDP mouse presses
// landed ~36 px above the pointer (picked the wrong preset).
const press = async (text, opts = {}) => {
  let p = await b.find(text, opts);
  if (!p) throw new Error("not found: " + text);
  if (p.y < 40 || p.y > H - 40) {
    await b.evaluate(`document.querySelector('[data-rec-target]').scrollIntoView({ behavior: "smooth", block: "center" })`);
    await sleep(900);
    p = await b.find(text, opts);
  }
  await b.moveTo(p);
  await b.evaluate(`document.querySelector('[data-rec-target]').click()`);
  await sleep(150);
};
const waitFor = async (expr, maxMs = 90_000) => {
  const t0 = Date.now();
  while (Date.now() - t0 < maxMs) { if (await b.evaluate(expr)) return; await sleep(200); }
  throw new Error("timed out waiting for: " + expr);
};
const idle = `![...document.querySelectorAll('button.primary')].some(e => e.textContent.includes('Driving'))`;
const animated = `!/Driving|Parking/.test(document.querySelector('figcaption.status')?.textContent || 'Driving')`;
// press "Test-drive", wait for the answer (cutting the wait when it is a live model call), then the drive
async function testDrive({ live = false } = {}) {
  await press("Test-drive this home");
  await scrollTo(0);   // the button can sit below the fold; the drive happens at the top
  if (live) { b.pause(); await waitFor(idle); await b.resume(); } else await waitFor(idle);
  await sleep(300); await waitFor(animated);
}
async function afterFix() { await press("After fix"); await sleep(300); await waitFor(animated); }

try {
await b.goto(URL_, 3500);
await b.startRec();

// FROM=hallways records only sections 4-6 (offline, free) to splice onto an earlier take
if (process.env.FROM !== "hallways") {
// 1. What it is
cue("CLEARWAY: test-drive a home in a wheelchair before you change it");
await sleep(2500); await hover(170, 170); await sleep(2000);
cue("Pick a home and a chair; six agents do the rest");
await hover(170, 430); await sleep(3000);

// 2. A doorway, offline (the deterministic stub stands in for the model)
cue("A 1970s apartment: a 65 cm bathroom door and a 70 cm power chair");
await testDrive();
cue("The chair drives its real route and jams at the door");
await hover(700, 330); await sleep(3500);
cue("The Builder proposes the cheapest fix; the Auditor re-drives it and checks the code");
await scrollToEl(".ev.refuse", "", 220, 1500); await hover(1200, 330); await sleep(4000);
cue("Offset hinges squeeze the chair through, but 700 mm is under ADA's 815 mm: refused");
await sleep(3500);
await scrollTo(0); await sleep(1200);
cue("Widening the frame passes both checks: refused 1 of 2 before you saw one");
await hover(1250, 170); await sleep(3000);
cue("After the fix, the chair rolls through");
await afterFix(); await sleep(2000);

// 3. The same door with live agents: Nemotron 3 Super proposes, Tavily cites, Ultra writes the brief
cue("Now with live agents on Nebius Token Factory");
await press("Live agents"); await sleep(1200);
await testDrive({ live: true });
cue("Every step shows what ran: Nemotron 3 Super, Tavily, or deterministic code");
await scrollToEl(".ev.propose", "", 200, 1500); await hover(1250, 260); await sleep(4500);
cue("The Auditor refuses what fails; Super reads the reason and tries again");
await scrollToEl(".ev.refuse", "", 220, 1500); await hover(1250, 330); await sleep(4500);
cue("Tavily evidence: the code clause and a cited contractor price");
await scrollToEl(".card", "", 260, 1500); await hover(1250, 300); await sleep(4000);
await scrollTo(0); await sleep(1200);
cue("You approve; the brief's figures come from code, Nemotron 3 Ultra writes the plain words");
await sleep(800); await press("Approve this fix", { gone: true });   // a click lost to a still-moving scroll is retried
b.pause(); await waitFor(`!!document.querySelector('.brief')`); await b.resume();
await scrollToEl(".brief", "", 120, 1500); await hover(1250, 400); await sleep(6000);
await scrollTo(0); await sleep(1000);
await press("Live agents"); await sleep(800);   // hallways below run offline
}

// 4. An S-shaped hallway: wheelchair kinematics, a real chair from its spec
cue("Hallways need real wheelchair physics: the chair turns about its drive axle and drives arcs");
await press("S-shaped hallway"); await sleep(1500);
await hover(170, 590); await sleep(2500);
cue("A real chair from its published spec: the Quantum Q6 Edge 3 Stretto");
await sleep(2000);
await testDrive();
cue("It jams at the first bend of a 70 cm hallway");
await hover(700, 280); await sleep(3000);
cue("The cheapest width it can manage, 80 cm, is under ADA's 915 mm: refused");
await scrollToEl(".ev.refuse", "", 220, 1500); await hover(1200, 330); await sleep(4000);
await scrollTo(0); await sleep(1200);
cue("At 95 cm it gets round both bends");
await afterFix(); await sleep(2000);

// 5. A dead end: the chair has to turn around
cue("A dead-end hallway: the chair has to turn around and come back");
await press("Dead-end hallway"); await sleep(1500);
await testDrive();
await hover(700, 300); await sleep(2500);
cue("A 100 cm turning space would do for this chair, but ADA asks for 1525 mm: refused");
await hover(1250, 170); await sleep(7000);
cue("With a code-size T it turns around and drives back out");
await afterFix(); await sleep(1500);

// 5b. Car mode: a side-entry ramp van at home (the same engine drives a car)
cue("Car mode: a side-entry ramp van parks at home, with real car steering");
await press("Home driveway"); await sleep(1200);
await testDrive();
cue("In a 350 cm bay its ramp hits the wall; 445 cm would fit, but ADA asks for 4875 mm: refused");
await hover(700, 250); await sleep(7600);
cue("At 490 cm the aisle is marked, the ramp deploys and the chair rolls off");
await afterFix(); await sleep(1500);

// 6. Close
cue("The model proposes. Code decides. An independent auditor can say no. You approve.");
await hover(700, 160); await sleep(4500);

var { frames, end } = await b.stopRec();
} finally {
  b.close();   // always: a crashed take must not leave headless Chrome on the port
}

// frames -> constant 30 fps: each output slot shows the newest frame captured by then
const FPS = 30, start = frames[0].t, slots = Math.ceil((end - start) * FPS);
const list = []; let j = 0; const written = new Map();
for (let s = 0; s < slots; s++) {
  const t = start + s / FPS;
  while (j + 1 < frames.length && frames[j + 1].t <= t) j++;
  if (!written.has(j)) {
    const name = `frames/${String(j).padStart(5, "0")}.jpg`;
    writeFileSync(DIR + name, Buffer.from(frames[j].data, "base64")); written.set(j, name);
  }
  list.push(`file '${written.get(j)}'`, `duration ${(1 / FPS).toFixed(6)}`);
}
list.push(list[list.length - 2]);
writeFileSync(DIR + "list.txt", list.join("\n") + "\n");
writeFileSync(DIR + "cues.json", JSON.stringify(cues.map((c) => ({ at: Math.max(0, c.at - start), text: c.text })), null, 1));
console.log(`frames ${frames.length}, length ${(end - start).toFixed(1)} s`);
console.log(`cd ${DIR} && ffmpeg -f concat -safe 0 -i list.txt -vf "scale=1920:1200,format=yuv420p" -r 30 -c:v libx264 -crf 18 clearway-silent.mp4`);
