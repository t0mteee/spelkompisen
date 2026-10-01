// BETRODD kopia av agentens tools/skarmbild.mjs (~/spel-ai-kompisen @ a2fbc12),
// granskad rad för rad 2026-10-01 och skärpt. Facitsidan kör den UTANFÖR
// agentens sandbox mot en sida vars JavaScript agenten skriver, så den får
// inte ge sidan något agenten själv saknar (designens avsnitt 11):
//
//  * Bara URL:er med exakt ursprunget SKARMBILD_ORIGIN (http://127.0.0.1:5176,
//    satt av app/spelai/skarmbilder.py). Allt annat avvisas före Chrome startar.
//  * Chrome får en DÖD proxy (127.0.0.1:9) och går förbi den ENDAST för
//    ursprungets värd:port. `<-loopback>` tar bort Chromes inbyggda undantag
//    för localhost, så sidans JavaScript når varken 8002/5175, nätet eller
//    andra lokala portar — inte ens med fetch(no-cors), bilder, sendBeacon
//    eller WebSocket. ORDNINGEN spelar roll: senare regler går före tidigare,
//    så `<-loopback>` står FÖRST och ursprunget sist (uppmätt 2026-10-01: med
//    omvänd ordning nekades även ursprunget; utan `<-loopback>` nådde sidans
//    POST, bild, beacon och WebSocket en annan lokal port direkt).
//  * DevTools över pipe (--remote-debugging-pipe): ingen TCP-port alls, så
//    sidan kan inte ta över webbläsaren (agentens original öppnade en port
//    9300–9899 som sidan själv kunde ansluta till).
//  * Chromes egen bakgrundstrafik är avstängd (komponentuppdatering, synk,
//    tillägg, DNS-förhämtning, WebRTC utanför proxyn).
//  * Skriver BARA <ut.png>. Chromes profil är en temporär katalog som tas
//    bort efteråt. Skriptet självt gör inga nätanrop.
//  * Sidans svar (scrollmått) är agentens data: valideras, höjden kapas.
//
//   node skarmbild.mjs <url> <ut.png> [bredd=390] [höjd=844] [hel=0|1]
// Skriver {out, innerWidth, scrollWidth, scrollHeight} på stdout.
import { spawn } from 'node:child_process'
import { mkdtemp, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import process from 'node:process'

const MAX_HOJD = 16000
const TIDSGRANS_MS = 60000
const ORIGIN = new URL(process.env.SKARMBILD_ORIGIN || 'http://127.0.0.1:5176')
const CHROME = process.env.CHROME || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
const [url, out, w = '390', h = '844', full = '0'] = process.argv.slice(2)

const fail = (msg) => { console.error(msg); process.exit(2) }
if (ORIGIN.protocol !== 'http:' || !['127.0.0.1', 'localhost'].includes(ORIGIN.hostname) || !ORIGIN.port) {
  fail(`ogiltigt ursprung: ${ORIGIN.href}`)
}
if (!url || !out) fail('användning: node skarmbild.mjs <url> <ut.png> [bredd] [höjd] [hel]')
let target
try { target = new URL(url) } catch { fail(`ogiltig URL: ${url}`) }
if (target.origin !== ORIGIN.origin) fail(`URL utanför ${ORIGIN.origin}: ${url}`)
const width = Number(w)
const height = Number(h)
if (![width, height].every((n) => Number.isInteger(n) && n >= 200 && n <= 4000)) fail('ogiltigt mått')

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))
const profile = await mkdtemp(join(tmpdir(), 'skarmbild-'))
const chrome = spawn(CHROME, [
  '--headless=new', '--disable-gpu', '--hide-scrollbars', '--no-first-run',
  '--no-default-browser-check', '--disable-background-networking',
  '--disable-component-update', '--disable-sync', '--disable-extensions',
  '--disable-default-apps', '--dns-prefetch-disable', '--no-pings',
  '--force-webrtc-ip-handling-policy=disable_non_proxied_udp',
  '--proxy-server=http://127.0.0.1:9',
  `--proxy-bypass-list=<-loopback>;${ORIGIN.host}`,
  '--remote-debugging-pipe', `--user-data-dir=${profile}`, 'about:blank',
], { stdio: ['ignore', 'ignore', 'ignore', 'pipe', 'pipe'] })
const watchdog = setTimeout(() => { console.error('tidsgräns'); chrome.kill('SIGKILL'); process.exit(1) }, TIDSGRANS_MS)

// CDP över pipe: JSON-meddelanden avslutade med NUL, fd 3 till Chrome, fd 4 från.
let seq = 0
const pending = new Map()
let buffered = Buffer.alloc(0)
chrome.stdio[4].on('data', (chunk) => {
  buffered = Buffer.concat([buffered, chunk])
  let end
  while ((end = buffered.indexOf(0)) >= 0) {
    const msg = JSON.parse(buffered.subarray(0, end).toString('utf8'))
    buffered = buffered.subarray(end + 1)
    if (msg.id && pending.has(msg.id)) { pending.get(msg.id)(msg); pending.delete(msg.id) }
  }
})
const send = (method, params = {}, sessionId = undefined) => new Promise((resolve, reject) => {
  seq += 1
  pending.set(seq, (msg) => (msg.error ? reject(new Error(`${method}: ${msg.error.message}`)) : resolve(msg.result)))
  chrome.stdio[3].write(JSON.stringify({ id: seq, method, params, ...(sessionId ? { sessionId } : {}) }) + '\0')
})

let code = 0
try {
  const { targetId } = await send('Target.createTarget', { url: 'about:blank' })
  const { sessionId } = await send('Target.attachToTarget', { targetId, flatten: true })
  const page = (method, params = {}) => send(method, params, sessionId)
  const metrics = (hh) => page('Emulation.setDeviceMetricsOverride',
    { width, height: hh, deviceScaleFactor: 1, mobile: true })
  await metrics(height)
  await page('Page.enable')
  await page('Page.navigate', { url: target.href })
  await sleep(4000)
  const probe = await page('Runtime.evaluate', {
    expression: '[document.documentElement.scrollWidth, document.documentElement.scrollHeight, innerWidth]',
    returnByValue: true,
  })
  const raw = Array.isArray(probe?.result?.value) ? probe.result.value : []
  const [scrollWidth, scrollHeight, innerWidth] = [0, 1, 2].map((i) => (Number.isFinite(raw[i]) ? Math.round(raw[i]) : null))
  if (full === '1' && scrollHeight) {
    await metrics(Math.min(Math.max(scrollHeight, height), MAX_HOJD))
    await sleep(600)
  }
  const shot = await page('Page.captureScreenshot', { format: 'png' })
  await writeFile(out, Buffer.from(shot.data, 'base64'))
  console.log(JSON.stringify({ out, innerWidth, scrollWidth, scrollHeight }))
} catch (err) {
  console.error(String(err?.message || err))
  code = 1
} finally {
  clearTimeout(watchdog)
  chrome.kill()
  await sleep(300)
  await rm(profile, { recursive: true, force: true })
}
process.exit(code)
