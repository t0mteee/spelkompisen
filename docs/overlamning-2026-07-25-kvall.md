# Överlämning inför reset — 2026-07-25 (Claude Fable 5)

**Läs denna först, sedan `CLAUDE.md` och STATUS-blocket i `docs/plan.md`.**
Tidigare pass: `docs/overlamning-2026-07-25.md` (natten 24→25 + Codex-uppföljning).

Allt är committat, rent träd, **219 backendtester gröna**, frontendbygge grönt.

---

## Läget just nu

Verktyget är i drift: två launchd-jobb (Oddset :00/:30, poolspel var 5:e minut),
tio ligor, fyra prissättare (Svenska Spel via Kambi, Ninja Casino via Altenar,
Pinnacle som sharp, Smarkets som andra sharp-ankare) plus en shadow-live-radar.

**Den enda siffra som säger något om huruvida detta tjänar pengar:**
sharp-tierns close-EV är **+2,65 % [1,19..4,11]** över 147 stängda flaggor,
hela historiken, winsoriserat estimand. Amber-modellen ligger på −4,23 %
[−6,08..−2,26] och är därför bortkopplad från värdekorten.

## Vad detta pass gjorde

Granskade Codex arbete kritiskt och lagade fem fel. Codex metodval höll:
`pit-v3` startades som NYTT experiment i stället för att smyga in ändrad
datasemantik i det gamla, gamla manifestet är verifierat orört, och Betsson
håller gränsen (ingen cookie-/WAF-replay, medvetet inte i `BOOKS`).

1. **Ankarkontaminering — allvarligast.** Smarkets kopplades in som ankare och
   lades utanför `BOOKS`, men `attach_value` byggde sin boklista som "allt utom
   pinnacle". Börsen blev därför en bok att hitta värde hos: 192 av 902
   value_log-rader var Smarkets-flaggor (133 i tunna träningsmatcher,
   snitt-edge 13,2 % mot SvS 6,0 %) som mätte ankaroenighet och bid-ask-spread.
   Rensade med backup; `ANCHOR_SOURCES`-spärr införd.
2. **CDN-Age överkorrigerade.** Age drogs från varvets STARTTID; en ligaloop kan
   pågå 25 min, så sena ligor bakåtdaterades med Age plus hela insamlingstiden.
   Nu mot det egna anropets tid — även för Kambi, sidoböcker och Smarkets.
3. **Ingen monotonispärr.** Olika CDN-noder kunde flytta färskhetsklockan bakåt
   och skapa falska rörelsepunkter. `MAX(last_seen_at, ?)`, och cacheobjekt
   äldre än senaste bekräftelse hoppas över helt.
4. **Radarn delade HTTP-klient med den spelbara xG-pipelinen.** Egen klient,
   matchtak (14), tidsbudget (90 s), tidsstämpel per event, och proxyn heter
   `proxy_index` och sorteras skild från xG:s `chance_gap`.
5. **Dubbeltrafik mot Pinnacle** från de två jobben — 10-minutersspärr.

Ett agentfynd verifierades BORT: ett radarfel kan inte släcka Oddset-vyn
(fetchen har `.catch`, renderingen är skyddad). Verifiera alltid själv.

## Två regler som nu står i CLAUDE.md

**🕐 Observationstidsregeln.** Samma bugg uppstod tre gånger på tre dygn:
förändringstid ≠ observationstid (pit-v1), hämtningstid ≠ pristid (CDN-Age),
loopstart ≠ per-post-tid (radarn). Läs regeln innan du skriver en ny insamlare.

**🎯 ANKARE ≠ BOK.** `BOOKS` styr insamlingen, `ANCHOR_SOURCES` styr
värderingen. En ny sharp-referens MÅSTE in i den senare.

## Öppet — väntar på Saman

- **Betsson-headern.** Codex löste fältnamnet (`brandId`) men matchtabellen
  ligger bakom CloudFront. Klienten finns i `app/betsson.py`, medvetet inte i
  `BOOKS`. Med en header från Samans egen DevTools (Network → `api/sb`) blir
  Betsson-koncernen vår första genuint oberoende prismotor.
- **bwin** ger 403 från Cloudflare här; svarar den 200 från Samans nät är
  klienten trivial.
- **m20-horisonten för sharp** kan strukturellt inte nå 10-minuterstoleransen:
  uppmätt ger Pinnacle en distinkt capture var 30:e minut i median (CDN-cache
  905 s), medan SvS får sina var 5:e. Poolens femminutersjobb löste rätt problem
  för fel källa. Toleransen är förregistrerad och får INTE ändras — men frågan
  om sharp överhuvudtaget kan bära m20 bör avgöras medvetet.

## Nästa session bör

1. **Auditera första PH3-settlementen.** SvS hade fortfarande inte publicerat
   facit för topptipset 4226/4227 (`drawState=Closed`, ingen `result`). 12
   system ligger korrekt osettlade. Granska då egen vinstutspädning,
   `payout_complete` och `n_evaluable` innan någon ROI läses.
2. **Låt Smarkets-serien växa**, koppla sedan in tvåankarkravet: en edge ska
   överleva mot BÅDE Pinnacle och Smarkets. Det angriper projektets djupaste
   metodproblem — devigmetodens val rör ~3 pp medan flaggtröskeln är 2 pp, så
   vi vet inte om edgen är marknadens eller devigens. Mätt oenighet: median
   1,12 pp, och 11 % av selektionerna skiljer mer än hela tröskeln.
3. **Rör inte manifest eller toleranser** för det frysta forwardexperimentet
   (`docs/pool-ph4-forward-manifest-v2.json`, `pit-v3`).
4. **Live-radarn samlar data i shadow.** Mitt 220-matcherstest visade att en ren
   skottsignal inte förutsäger mål (0,94–1,06× basraten över alla kvintiler;
   topp 10 % låg UNDER basraten). Radarn får inte bli rekommendationer utan en
   förregistrerad gate. Sofascore saknar dessutom xG helt för Allsvenskan.

## Gränsen som gäller

Publika JSON-API:er, statiska publika tokens i sidans kod, läsa publik
JavaScript och artig rate limiting är fritt fram. Att lösa eller förfalska
anti-bot-utmaningar — Cloudflare-challenges, Impervas `reese84`, CAPTCHA —
görs inte. bet365, Coolbet och Betano ligger bakom det senare.
