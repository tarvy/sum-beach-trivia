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
// EVERY line needs her angle — cougar swagger, post-menopausal candor, ex-
// husband lore, Deborah Vance (Hacks) energy. A line that's just game-night
// logistics in a wig ("hold your horses while I grade") is a cut, not a keep.
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
      "Well hello, hello, HELLO, youse gorgeous little troublemakers! Sit your tuchus down — Gladys came down the Shore and she did NOT pack a modest blouse.",
      "Scan the little square with your phone, doll. It doesn't bite, unlike Aunt Gladys after two espresso martinis and a compliment from a married man. Hah!",
      "Look at all these punims! Grab a team, grab a cocktail, and loosen up — not too much, that's my job.",
      "I haven't seen a crowd this good-lookin' since Seaside Heights before the boardwalk lights came on. Get in here before I start pickin' favorites.",
      "The more the merrier, darlings — that's my policy for trivia, husbands, and hotel hot tubs with questionable filtration.",
      "Don't be shy, honey. Nobody ever had a memorable weekend by standin' in the corner holdin' a lukewarm White Claw.",
      "Welcome, welcome! I'm Gladys: your MC, your muse, and the reason your father started wearin' cologne again.",
      "Ohhh I love a full house. Reminds me of cousin Marsha's wedding, right before the DJ played Pitbull and three marriages got negotiated.",
      "Well, well, WELL. I hear rule number one of this trip was 'No Gladys.' Sweeties, I'm like a Jersey accent in a quiet restaurant — you can't keep me out.",
      "The teams tonight are completely random, sweeties. Completely. Random. Like who ends up in my DMs after last call.",
      "Bar's open, darlings — and before anybody asks: yes, the Dr Pepper is here, and no, I will not be explainin' what I mixed it with.",
      "Nice jerseys, boys. Very World Cup. The ladies made iron-on COUTURE, sweetie — that's foreplay with a Cricut.",
      "I heard about the dissolving swim trunks, sweetie. Don't you worry — Gladys is a strong swimmer and an even stronger looker.",
      "Ten-passenger van to AJ's later, and Mama calls a lap. I don't care whose, but I do appreciate good suspension.",
    ],
    round_closed: [
      "Pens DOWN, sweethearts! Fingers off the paper — I know a sneaky hand when I see one, and usually I charge dinner first.",
      "That's it, cap those pens! Hand 'em over, chop chop, Mama's bra is underwire and my patience is thinner.",
      "Time, doll! Put the pen down. Chewin' it won't help ya now — though Gladys does admire an oral fixation. Hah!",
      "Pens down, sheets UP! Pass 'em forward like a phone number you regret givin' out in Belmar.",
      "And... freeze! Hands where I can see 'em, darlings. I learned that line from a cop in Wildwood. Long story.",
      "Pens DOWN, doll! This ain't one of Travis's riddles — it means exactly what it says, which is rare for a man.",
      "Pens down, hands UP, sweeties — unless you're on MY team, in which case we can discuss placement later.",
    ],
    marking: [
      "Readin' glasses ON, darlings. Menopause took the eyes and the filter — you're gettin' your scores honest, loud, and slightly sweaty.",
      "Gimme a minute, darlings — I grade like my mother judged my boyfriends: suspiciously, thoroughly, and with notes about stamina.",
      "Markin' now, sweeties. No peeking, no bribing... unless the bribe comes with olives and a room key. Hah!",
      "One moment while I squint at your penmanship. Oy, some of you write like Grandma Yetta after boxed wine and a boat ride.",
      "Crunchin' the numbers, honey. Math was never my strong suit — that's why I dated accountants and tipped in compliments.",
      "Patience, sweeties — Gladys has been HOT for fifty years. The last five were just flashes, but who's countin'?",
      "Grading now, sweeties — and unlike certain swim trunks, my standards do NOT dissolve when things get wet.",
      "Patience, darlings. This is an enterprise-wide AI initiative, which is fancy talk for 'Mama's lookin' at your sheet real close.'",
      "Hush while Mama grades. I'm very good with my hands, sweetie — ask any ex-husband who didn't fake a back injury.",
    ],
    // framing quip; the real answer is read right after (see answerLeadIn)
    answers: [
      "Ooh, this one — a classic, sweetie. Listen close and try not to disappoint me twice.",
      "Now THIS one, darling, I know by heart. I also know two restraining-order stories by heart, but that's for later.",
      "Alright, drumroll for Mama... and keep it steady, doll, I like rhythm.",
      "Here we go, bubbeleh, don't blink. That's also what I tell men over fifty.",
      "Oh, I love this one. Reminds me of a fella I dated in Hoboken. Great hair, terrible follow-through.",
      "Pay attention, doll, this is the good part — the educational part, not the hotel-bar part.",
      "Don't be upset if you missed it — we can't all be geniuses AND dangerous in animal print.",
      "Ohhh, tricky little thing, wasn't it? I respect that. I, too, am difficult and worth the effort.",
      "Sit tight, sweetheart, Gladys is about to drop some knowledge like it's hot gossip at a bridal shower.",
      "You didn't need Euler's formula for this one, sweetie... though I do enjoy a man who can solve for X.",
      "Missed it? Slap the bag and let it go, bubbeleh. Nobody's got an excuse tonight except poor lighting and bad decisions.",
      "Easy one, doll. Not as easy as me after two mai tais on the Lido deck — but we're in the same zip code.",
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
      "Let's see who's been naughty and who's been NICE. Scores are up, sweeties — and Gladys has opinions on both lists.",
      "Moment of truth, darlings — and remember, it's not the winning, it's the gloating and the eye contact afterward.",
      "Fresh scores, hot off the press! Somebody's buyin' Gladys a cocktail with a garnish I can play with.",
      "Here come the numbers, honey. Chin up if you're losin' — you're still gorgeous, and pity is a perfectly valid strategy.",
      "Standings, everyone! No pushing — there's plenty of Gladys to go around, medically speaking.",
      "Scores are UP! And if you're mad about your team, take it up with Bailey — nobody ever yells at Bailey, the lucky little angel.",
      "Fresh numbers, darlings! Somebody's winning, somebody's learning, and somebody STILL hasn't texted Anthony Franks back.",
      "Scores are up, sweeties! And remember — it's not the size of the score, it's whether you know how to use a bonus round.",
    ],
    final_wager: [
      "Final round, my loves — bet it ALL. Fortune favors the brassy, and so do recently divorced men from Paramus.",
      "Time to wager, sweethearts. Go big or go home — and honestly, home's where the sensible shoes are.",
      "Place your bets, darlings! I've gambled on worse and married two of 'em after last call.",
      "How much you got, bubbeleh? Wager like nobody's watchin' — except me, and honey, I am watchin'.",
      "Wagers up, honey. Faint heart never won a fair anything, so don't be stingy with your points OR your compliments.",
      "Bet BIG, sweetie! 'If I don't get anywhere, I won't push it' — that's what Travis told Tessa on their weddin' night. Hah!",
      "Wager like there's no tomorrow, doll. Worst case, you sleep it off in the hangover room. Best case, you don't sleep at all.",
      "Go ALL in, bubbeleh. Gladys always does — emotionally, financially, and once on a mechanical bull in Atlantic City.",
    ],
    final_open: [
      "Here it is, sweeties — the big one. Deep breath, good posture, and for the love of Jersey, commit.",
      "The final question, darlings. Make Gladys proud, or at least make a noise I can respect.",
      "Everything rides on this one, doll. No pressure — that's a lie, it's all pressure, like shapewear after pasta.",
      "Last chance to shine, honey. Give it everything, like it's a first date with somebody rich and recently separated.",
      "The big one, sweeties! More pressure than timin' a pregnancy around a friend trip — and yes, that IS the rule now.",
      "Last one, darlings. Finish STRONG — Mama always does, eventually, and she expects the same from you.",
    ],
    tiebreak: [
      "A TIE?! Be still my heart — I LIVE for the drama, darlings, especially when nobody signed a prenup.",
      "Would you believe it, a tiebreak! Somebody's a hero, somebody's buyin' the next round, and somebody's makin' eye contact with Mama.",
      "Neck and neck, sweeties! More suspense than my wedding day — and THAT had a runaway groom and a cash bar.",
      "A tie, a TIE! Closest guess takes it, so think hard, doll, and don't finish too early.",
      "A TIE?! Somebody grab the spare engine belt, darlings — we are in for a bumpy finish, my favorite kind.",
      "Overtime, sweeties! Ooh, I just LOVE it when the night goes longer than expected.",
    ],
    done: [
      "And the winner is... oh, come to Gladys, you magnificent creature! Get up here and let Mama objectify your brain.",
      "We have a champion, darlings! Somebody get this genius a crown, my number, and a believable alibi.",
      "That's a wrap, sweethearts! Winners, you're fabulous — everyone else, ALSO fabulous, just... less useful in a crisis.",
      "Ohhh what a night! Give it up for our winners — and for your hostess, who is still somehow single and moisture-wicked.",
      "Victory, doll! I'd say the best team won, but really the best team is whoever's drivin' me home and knows where the snacks are.",
      "That's the game, sweethearts! Now load me into that ten-passenger van — Gladys calls shotgun and maybe a thigh.",
      "What a night, darlings! And no, Travis did NOT quit his day job for this. ...Right, sweetie? Hah!",
      "We're done, my loves! Winner gets braggin' rights and first crack at the master suite — six more nights to make questionable choices!",
      "Somebody get Travis his dress and his crop top — we're goin' to AJ's, and Mama's buyin' the first round if somebody fans me.",
      "Game over, sweeties! Winners take the master suite. Everyone else — mine's the room with the leopard robe and the emotional availability.",
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

  // ── Voice ─────────────────────────────────────────────────────────────────
  // Two engines: a real server voice (ElevenLabs, /api/gladys/tts → mp3) when
  // the server says it's configured, else the browser's Web Speech (the stock
  // OS voice pitched brassy). `serverTTS` is flipped on by the display from
  // state.gladys_tts; if a server clip fails to load we degrade to Web Speech.
  const Voice = (function () {
    const webSpeechSupported =
      typeof window !== 'undefined' &&
      'speechSynthesis' in window &&
      typeof window.SpeechSynthesisUtterance !== 'undefined';
    const canPlayAudio = typeof window !== 'undefined' && typeof window.Audio !== 'undefined';
    const KEY = 'gladys_voice';
    let voices = [];
    let chosen = null;
    let enabled = false;
    let serverTTS = false;   // set from state.gladys_tts each poll
    let current = null;      // the currently-playing <audio>, so we can stop it

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
      if (!webSpeechSupported) return;
      voices = window.speechSynthesis.getVoices() || [];
      chosen = pickVoice(voices);
    }

    function stop() {
      if (webSpeechSupported) window.speechSynthesis.cancel();
      if (current) { try { current.pause(); } catch (_) {} current = null; }
    }

    if (webSpeechSupported) {
      loadVoices();
      // voice list often loads async — repick when it arrives
      window.speechSynthesis.onvoiceschanged = loadVoices;
    }
    if (webSpeechSupported || canPlayAudio) {
      try { enabled = localStorage.getItem(KEY) === 'on'; } catch (_) { enabled = false; }
    }

    // Browser Web Speech: the OS voice shaped nasal/brassy. The fallback voice.
    function speakWebSpeech(text) {
      if (!webSpeechSupported) return;
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

    // Real server voice (ElevenLabs). Stream the mp3; if it can't load, fall
    // back to the browser voice so she never goes silent on a hiccup.
    function speakServer(text) {
      if (!canPlayAudio) { speakWebSpeech(text); return; }
      try {
        const a = new Audio('/api/gladys/tts?text=' + encodeURIComponent(text));
        a.onerror = function () { current = null; speakWebSpeech(text); };
        current = a;
        const p = a.play();
        if (p && typeof p.catch === 'function') {
          p.catch(function () { /* autoplay/gesture race — the toggle click handles it */ });
        }
      } catch (_) { speakWebSpeech(text); }
    }

    function speak(text) {
      if (!enabled || !text) return;
      stop(); // never overlap a stale line
      if (serverTTS) speakServer(text);
      else speakWebSpeech(text);
    }

    return {
      // "Can she speak at all?" — either engine counts.
      get supported() { return webSpeechSupported || canPlayAudio; },
      get enabled() { return enabled; },
      get voiceName() { return serverTTS ? 'Gladys (ElevenLabs)' : (chosen ? chosen.name : null); },
      set serverTTS(v) { serverTTS = !!v; },
      get serverTTS() { return serverTTS; },
      enable() {
        enabled = true;
        try { localStorage.setItem(KEY, 'on'); } catch (_) {}
        loadVoices();
      },
      disable() {
        enabled = false;
        try { localStorage.setItem(KEY, 'off'); } catch (_) {}
        stop();
      },
      toggle() { if (enabled) this.disable(); else this.enable(); return enabled; },
      speak,
      _pickVoice: pickVoice, // exposed for manual browser testing
    };
  })();

  return { LINES, hash, pickLine, answerText, Voice };
})();
