// gladys.js — Gladys, the AI MC.
//
// A brassy, big-haired, leopard-print cougar from Flushing by way of a Princess
// cruise ship: she honks when she laughs ("Hah!"), sprinkles Yiddish, drops
// names, flirts with the whole room, and calls everyone "sweetie." Think Fran
// Fine (The Nanny) crossed with every campy SNL cougar sketch — playful, warm,
// and openly thirsty: R-rated innuendo is her brand (suggestive, never
// explicit, never mean). It's a friends' game night; she's rooting for
// everybody and hitting on most of them. Inside jokes from the sum-beach-26
// group chat are a feature — never shy away from one.
//
// Pure client-side personality, served straight off /gladys.js (no build step,
// no external anything). A line bank + a STABLE picker (same seed -> same line,
// so a caption doesn't flicker across the display's 2.5s poll and matches
// whatever got spoken) + a Web Speech voice that runs on the display laptop.
//
// The voice uses the operating system's voices — it can't literally BE Fran
// Drescher; we shape a female voice nasal-and-brassy with pitch/rate, and the
// personality lands through the words. See docs/plans/2026-07-06-gladys-*.
window.Gladys = (function () {
  'use strict';

  // Line banks keyed by game context. Deliberately repeatable — a catchphrase
  // is FUNNIER the third time; that's the running bit. No `round_open` bank:
  // while a question is live it's quiet writing/thinking time, Gladys hushes.
  const LINES = {
    lobby: [
      "Well hello, hello, HELLO! Sit your gorgeous tuchus down, sweetie — Gladys is your hostess tonight, and oh, do we have fun.",
      "Scan the little square with your phone, doll, it doesn't bite. Unlike me. Hah!",
      "Look at all these punims! Grab a team, grab a cocktail, and let's make some magic, bubbeleh.",
      "I haven't seen a crowd this good-lookin' since I hosted bingo on the Lido deck. Get in here!",
      "The more the merrier, darlings — just like my ex-husbands. Sign on up!",
      "Don't be shy, honey — nobody good ever got anywhere bein' shy. Tap a team and let's go.",
      "Welcome, welcome! I'm Gladys: your MC, your muse, and possibly your future stepmother.",
      "Ohhh I love a full house. Reminds me of cousin Marsha's wedding, minus the fistfight. Join up, sweeties!",
      "Well, well, WELL. I hear rule number one of this trip was 'No Gladys.' And yet here I am on the big screen, sweeties — you can't keep a good woman out. Hah!",
      "The teams tonight are completely random, sweeties. Completely. Random. Wink.",
      "Bar's open, darlings — and before anybody asks: yes, the Dr Pepper is here.",
      "Nice jerseys, boys. Very World Cup. The ladies made iron-on COUTURE, sweetie — that's commitment.",
      "I heard about the dissolving swim trunks, sweetie. Don't you worry — Gladys is a strong swimmer and a PATIENT woman. Hah!",
      "Ten-passenger van to AJ's later, and Mama calls a lap. I don't care whose.",
    ],
    round_closed: [
      "Pens DOWN, sweethearts! Fingers off the paper — I've caught men doin' less and regretted it more. Hah!",
      "That's it, cap those pens! Hand 'em over, chop chop, Mama hasn't got all night.",
      "Time, doll! Put it down. If you didn't know it, chewin' that pen isn't gonna help ya now.",
      "Pens down, sheets UP! Pass 'em to the front like it's the last brisket at the buffet.",
      "And... freeze! Hands where I can see 'em, darlings. Sheets to the front.",
      "Pens DOWN, doll! This ain't one of Travis's riddles — it means exactly what it says.",
      "Pens down, hands UP, sweeties — unless you're on MY team, in which case they're free to wander. Hah!",
    ],
    marking: [
      "Hold your horses while I put my readin' glasses on. Gladys has a system, and the system is fabulous.",
      "Gimme a minute, darlings — I grade like my mother judged my boyfriends: fair, but thorough.",
      "Markin' now, sweeties. No peeking, no bribing... well, maybe a little bribing. Hah!",
      "One moment while I squint at your penmanship. Oy, some of you write like Grandma Yetta after her second sherry.",
      "Crunchin' the numbers, honey. Math was never my strong suit, but neither was patience — sit tight.",
      "Grading now, sweeties — and unlike certain swim trunks, my standards do NOT dissolve in salt water. Hah!",
      "Patience, darlings. This is an enterprise-wide AI initiative, don'tcha know.",
      "Hush while Mama grades. I'm very good with my hands, sweetie — ask any of my ex-husbands. Well, the two that still take my calls.",
    ],
    // framing quip; the real answer is read right after (see answerLeadIn)
    answers: [
      "Ooh, this one — a classic, sweetie. Listen close.",
      "Now THIS one, darling, I know by heart. And I know a lot by heart.",
      "Alright, drumroll for Mama...",
      "Here we go, bubbeleh, don't blink.",
      "Oh, I love this one. Reminds me of a fella I dated. Anyway —",
      "Pay attention, doll, this is the good part.",
      "Don't be upset if you missed it — we can't all be geniuses AND this glamorous.",
      "Ohhh, tricky little thing, wasn't it? Here's the truth of it.",
      "Sit tight, sweetheart, Gladys is about to drop some knowledge.",
      "You didn't need Euler's formula for this one, sweetie... but wouldn't THAT have been somethin'.",
      "Missed it? Slap the bag and let it go, bubbeleh. Nobody's got an excuse tonight.",
      "Easy one, doll. Not as easy as me after two mai tais on the Lido deck — but easy.",
    ],
    // connective spoken between the quip and the actual answer text
    answerLeadIn: [
      "The answer is",
      "It was, of course,",
      "And the answer, darling, is",
      "You were lookin' for",
      "Correct answer, sweetie:",
    ],
    reveal: [
      "Let's see who's been naughty and who's been NICE. Scores are up, sweeties!",
      "Moment of truth, darlings — and remember, it's not the winning, it's the gloating. Hah!",
      "Fresh scores, hot off the press! Somebody's buyin' Gladys a cocktail.",
      "Here come the numbers, honey. Chin up if you're losin' — you're still gorgeous.",
      "Standings, everyone! No pushing — there's plenty of Gladys to go around.",
      "Scores are UP! And if you're mad about your team, take it up with Bailey — nobody ever yells at Bailey. Hah!",
      "Fresh numbers, darlings! Somebody's winning, somebody's learning, and somebody STILL hasn't texted Anthony Franks back.",
      "Scores are up, sweeties! And remember — it's not the size of the score, it's what you do with it. Hah!",
    ],
    final_wager: [
      "Final round, my loves — bet it ALL. Fortune favors the brassy, take it from me.",
      "Time to wager, sweethearts. Go big or go home — and honestly, home's overrated.",
      "Place your bets, darlings! I've gambled on worse and married two of 'em. Hah!",
      "How much you got, bubbeleh? Wager like nobody's watchin' — 'cause it's just me, and I approve.",
      "Wagers up, honey. Faint heart never won a fair anything, so don't be stingy.",
      "Bet BIG, sweetie! 'If I don't get anywhere, I won't push it' — that's what Travis told Tessa on their weddin' night. Hah!",
      "Wager like there's no tomorrow, doll. Worst case, you sleep it off in the hangover room. Best case, you don't sleep at all. Hah!",
      "Go ALL in, bubbeleh. Gladys always does — that's why there's a rule about me.",
    ],
    final_open: [
      "Here it is, sweeties — the big one. Deep breath, good posture, DAZZLE me.",
      "The final question, darlings. Make Gladys proud, or at least make her laugh.",
      "Everything rides on this one, doll. No pressure — that's a lie, it's all pressure.",
      "Last chance to shine, honey. Give it everything, like it's a first date with somebody rich.",
      "The big one, sweeties! More pressure than timin' a pregnancy around a friend trip — and yes, that IS the rule now.",
      "Last one, darlings. Finish STRONG — Mama always does, and she expects the same from you. Hah!",
    ],
    tiebreak: [
      "A TIE?! Be still my heart — I LIVE for the drama, darlings.",
      "Would you believe it, a tiebreak! Somebody's a hero, somebody's buyin' the next round.",
      "Neck and neck, sweeties! More suspense than my wedding day — and THAT had a runaway groom.",
      "A tie, a TIE! Closest guess takes it, so think hard, doll, and think fast.",
      "A TIE?! Somebody grab the spare engine belt, darlings — we are in for a bumpy finish!",
      "Overtime, sweeties! Ooh, I just LOVE it when the night goes longer than expected. Hah!",
    ],
    done: [
      "And the winner is... oh, come to Gladys, you magnificent creature! Get up here!",
      "We have a champion, darlings! Somebody get this genius a crown and my number.",
      "That's a wrap, sweethearts! Winners, you're fabulous — everyone else, ALSO fabulous, just... less.",
      "Ohhh what a night! Give it up for our winners — and for your hostess, obviously. Hah!",
      "Victory, doll! I'd say the best team won, but really the best team is whoever's drivin' me home.",
      "That's the game, sweethearts! Now load me into that ten-passenger van — Gladys calls shotgun to AJ's.",
      "What a night, darlings! And no, Travis did NOT quit his day job for this. ...Right, sweetie? Hah!",
      "We're done, my loves! Winner gets braggin' rights and first crack at the master suite — six more nights to lock it down!",
      "Somebody get Travis his dress and his crop top — we're goin' to AJ's, and Mama's buyin' the first round.",
      "Game over, sweeties! Winners take the master suite. Everyone else — mine's the room with the leopard robe on the door. Hah!",
    ],
  };

  // FNV-1a — cheap, stable string hash so a (context, seed) pair always maps to
  // the same line. Stability is the whole point: the display re-picks on every
  // 2.5s poll and must land on the same line each time (cf. the ticker de-dupe).
  function hash(str) {
    let h = 2166136261;
    const s = String(str);
    for (let i = 0; i < s.length; i++) {
      h ^= s.charCodeAt(i);
      h = Math.imul(h, 16777619);
    }
    return h >>> 0;
  }

  function pickLine(context, seed) {
    const bank = LINES[context];
    if (!bank || !bank.length) return '';
    return bank[hash(context + '|' + (seed == null ? '' : seed)) % bank.length];
  }

  // Flatten a question's answer to speakable text (list-aware).
  function answerText(q) {
    if (!q) return '';
    if (Array.isArray(q.answer_items) && q.answer_items.length) {
      return q.answer_items.join(', ');
    }
    return q.answer || '';
  }

  // ── Web Speech voice ──────────────────────────────────────────────────────
  const Voice = (function () {
    const supported =
      typeof window !== 'undefined' &&
      'speechSynthesis' in window &&
      typeof window.SpeechSynthesisUtterance !== 'undefined';
    const KEY = 'gladys_voice';
    let voices = [];
    let chosen = null;
    let enabled = false;

    // Prefer a female-sounding en-US voice; degrade gracefully to any en, then
    // anything at all. We can't get Fran — we get the room's least-robotic gal.
    function pickVoice(list) {
      if (!list || !list.length) return null;
      const en = list.filter((v) => /^en(-|_|$)/i.test(v.lang || ''));
      const pool = en.length ? en : list;
      const prefer = [
        'samantha', 'victoria', 'karen', 'moira', 'tessa', 'fiona',
        'zira', 'susan', 'allison', 'ava', 'female',
      ];
      for (const name of prefer) {
        const hit = pool.find((v) => (v.name || '').toLowerCase().includes(name));
        if (hit) return hit;
      }
      const us = pool.find((v) => /en[-_]us/i.test(v.lang || ''));
      return us || pool[0];
    }

    function loadVoices() {
      if (!supported) return;
      voices = window.speechSynthesis.getVoices() || [];
      chosen = pickVoice(voices);
    }

    if (supported) {
      loadVoices();
      // voice list often loads async — repick when it arrives
      window.speechSynthesis.onvoiceschanged = loadVoices;
      try { enabled = localStorage.getItem(KEY) === 'on'; } catch (_) { enabled = false; }
    }

    function speak(text) {
      if (!supported || !enabled || !text) return;
      try {
        window.speechSynthesis.cancel(); // never queue behind a stale line
        const u = new SpeechSynthesisUtterance(String(text));
        if (chosen) u.voice = chosen;
        u.pitch = 1.5;  // nasal + brassy
        u.rate = 1.05;  // brisk NY patter
        u.volume = 1;
        window.speechSynthesis.speak(u);
      } catch (_) {}
    }

    return {
      get supported() { return supported; },
      get enabled() { return enabled; },
      get voiceName() { return chosen ? chosen.name : null; },
      enable() {
        enabled = true;
        try { localStorage.setItem(KEY, 'on'); } catch (_) {}
        loadVoices();
      },
      disable() {
        enabled = false;
        try { localStorage.setItem(KEY, 'off'); } catch (_) {}
        if (supported) window.speechSynthesis.cancel();
      },
      toggle() { if (enabled) this.disable(); else this.enable(); return enabled; },
      speak,
      _pickVoice: pickVoice, // exposed for manual browser testing
    };
  })();

  return { LINES, hash, pickLine, answerText, Voice };
})();
