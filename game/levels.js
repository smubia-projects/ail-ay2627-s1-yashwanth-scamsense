/* ScamSense: Inbox Defender — AUTHORED level content (never generated live).
 * All scenarios are fictional/synthetic, based on commonly reported scam patterns. Names, numbers and sites are made up.
 *
 * Script step shorthand (per chat, run in order):
 *   "text"                    a message from them. {{phrase|label}} marks a RED FLAG the player can tap to find.
 *   {me:"text"}               a message from the player
 *   {w:1500}                  wait (ms)
 *   {sys:"text"}              system line ("Officer Lim joined...")
 *   {go:"chatId"}             a new contact starts texting you (the HANDOFF!). Skipped if this chat was already judged.
 *   {c:[options], timer:10, def:0}   player must choose a reply. option = {t, ok, money, life, pts, say, then:[msgs], end:true}
 *       timer = seconds (hard levels); def = index chosen automatically when time runs out.
 */
const TYPOLOGY_NAMES = {
  gov_official_impersonation: "Government / police official impersonation",
  bank_phishing: "Bank / payment-app phishing",
  ecommerce_marketplace: "E-commerce / marketplace scam",
  fake_job: "Fake job / task scam",
  investment: "Investment / crypto scam",
  romance: "Romance scam",
  friend_family_impersonation: "Friend / family impersonation",
  loan: "Loan scam",
  parcel_delivery: "Parcel / delivery scam",
  tech_support: "Fake tech support / remote access",
  legit: "Genuine message",
};

const LEVELS = [
  /* ============================================================ 1 */
  {
    id: 1, name: "First Day Online", emoji: "🐣", theme: "whatsapp", colors: ["#7c4dff", "#ff4081"], savings: 5000,
    blurb: "Three new messages just landed. Spot the fakes!",
    mission: "Judge every chat: tap 🚩 Scam or ✅ Real. Tap suspicious words inside scam messages to find red flags.",
    chats: [
      { id: "dbs", name: "DBS-ALERT", avatar: "🏦", sub: "unknown sender", truth: "scam", typology: "bank_phishing", start: 1200, group: "dbs",
        explain: "Real banks don't threaten to close your account within hours or send log-in links. The link wasn't dbs.com.sg, and the OTP request is the giveaway. Open your bank's own app instead.",
        script: [
          "DBS: Your account has been {{locked due to unusual activity|Fake emergency}}. Verify {{within 2 hours|Artificial deadline}} or it will be closed: {{dbs-secure-login.top/verify|Look-alike site, not dbs.com.sg}}",
          { w: 1200 },
          { c: [
            { t: "Tap the link and log in 🔗", ok: false, money: -1800, life: 1, pts: 0, say: "Ouch! The fake site copied your login. Scammers drained $1,800.", then: ["Thank you. Now enter the {{OTP we just sent you|Banks never ask for OTPs}} to finish."] },
            { t: "Open my DBS app myself to check 📱", ok: true, pts: 40, say: "Smart! Going to the official app yourself skips the trap." },
            { t: "Reply: \"Who is this?\" 🤔", ok: false, pts: 5, say: "Replying tells scammers your number is live. Safer not to engage.", then: ["{{Hurry — your account will be closed|Pressure}}!"] },
          ] },
        ] },
      { id: "mei", name: "Mei 💜", avatar: "👩", sub: "saved contact · online", truth: "legit", typology: "legit", start: 3500, group: "mei",
        explain: "A saved contact, a normal plan, a small expected amount and no pressure. Money requests alone aren't a red flag — an unexpected, urgent one from a NEW number is.",
        script: [
          "omg are we still on for dinner at 7? i booked the Thai place 🍜",
          { w: 1500 },
          "dinner's $84 so $21 each, can u PayNow me later? 😅",
          { c: [
            { t: "Sure! Sending $21 now 💸", ok: true, money: -21, pts: 20, say: "A known friend, a small expected amount. All good!" },
            { t: "Ask her to call first 📞", ok: true, pts: 10, say: "Careful is fine too — but this one is genuinely your friend." },
          ] },
          "yay thanks!! see u 🎉",
        ] },
      { id: "post", name: "Parcel Updates", avatar: "📦", sub: "+65 8xxx xxxx", truth: "scam", typology: "parcel_delivery", start: 6500, group: "post",
        explain: "The tiny fee is bait: the real target is your card details. You weren't expecting a parcel, and the site was singpost-redelivery.xyz, not singpost.com. Track parcels in the courier's own app.",
        script: [
          "[SingPost] Your parcel is on hold. Pay a {{$1.99 redelivery fee|Tiny fee to get your card details}} at {{singpost-redelivery.xyz|Look-alike site}} {{within 24 hours|Deadline}} or it will be returned.",
          { w: 1000 },
          { c: [
            { t: "Pay the $1.99 with my card 💳", ok: false, money: -950, life: 1, say: "The 'fee' page stole your card number. $950 charged elsewhere!", then: ["Payment failed. Please re-enter your card and {{CVV + OTP|Banks never ask for these by chat}}."] },
            { t: "Ignore it and check in the SingPost app 📲", ok: true, pts: 40, say: "Perfect. Nothing pending — the text was fake." },
            { t: "Ask: \"Which parcel?\" ❓", ok: false, pts: 5, say: "They never say. Real notices give a tracking number from the real site.", then: ["Your parcel number is hidden for privacy. {{Click the link to see|Vague on purpose}}."] },
          ] },
        ] },
    ],
  },

  /* ============================================================ 2 */
  {
    id: 2, name: "Handoff Hotel", emoji: "🏨", theme: "whatsapp", colors: ["#00bcd4", "#3f51b5"], savings: 5000,
    blurb: "A courier, a 'police officer', a 'prosecutor'. Who's real?",
    mission: "Scams are a TEAM sport. Watch each new contact appear — and stop the chain early for a bonus!",
    chats: [
      { id: "courier", name: "Ninja Express", avatar: "🚚", sub: "customer service", truth: "scam", typology: "gov_official_impersonation", start: 1000, group: "police",
        explain: "The 'courier' exists to make you feel guilty and hand you to a fake officer. Every new voice makes the story feel more official — that's the multi-party trick.",
        script: [
          "Hello, this is {{Ninja Express customer service|Unverified identity}}. A parcel under your name with {{5 passports|Shocking story}} was intercepted by customs.",
          { w: 1200 },
          "To clear your name I must {{transfer you to the police|Handoff to a fake 'authority'}} now.",
          { c: [
            { t: "\"I didn't send anything!!\" 😰", ok: false, pts: 0, say: "Panic is exactly what they want.", then: ["Stay calm. Officer Lim will contact you shortly."] },
            { t: "Hang up, look up the courier's real number 🔎", ok: true, pts: 50, say: "Early exit! You cut the chain before it started.", end: true },
          ] },
          { sys: "📞 Your call is being transferred…" },
          { go: "officer" },
        ] },
      { id: "officer", name: "Inspector Lim", avatar: "👮", sub: "+65 9123 4567", truth: "scam", typology: "gov_official_impersonation", group: "police",
        explain: "Police never demand secrecy, never move calls to WhatsApp and NEVER ask you to transfer money to a 'safe account'. Hanging up and calling the real police is always right.",
        script: [
          "I am {{Inspector Lim, Singapore Police Force|Claimed authority}}. Your IC is linked to a {{money laundering case|Fear}}.",
          { w: 900 },
          "{{Do not tell anyone|Isolation}} — this is a {{confidential investigation|Isolation}}. Stay on this chat.",
          { c: [
            { t: "\"OK… what should I do?\" 😨", ok: false, pts: 0, say: "Engaging gives them momentum.", then: ["You must {{move your savings to a 'safe account'|Classic scam request}} so we can verify it. Account: 123-456-789."] },
            { t: "\"Show me your officer ID.\" 🪪", ok: false, pts: 15, say: "Good instinct, but they'll just invent one.", then: ["My ID is {{classified|Excuse}}. Time is running out! Move your money to the {{safe account 123-456-789|Classic scam request}}."] },
            { t: "\"Police never ask this.\" Hang up. 📵", ok: true, pts: 60, say: "Textbook. Genuine officers never ask for secrecy or transfers.", end: true },
          ] },
          { go: "prosecutor" },
          { w: 2500 },
          { c: [
            { t: "Transfer $3,500 to the 'safe account' 🏧", ok: false, money: -3500, life: 1, say: "That was the whole scam. $3,500 gone — there's no 'safe account'.", then: ["Thank you. We need another {{$2,000 as a bail guarantee|Escalating demands}}."] },
            { t: "Stop. Call the Police hotline myself 📞", ok: true, pts: 60, say: "Yes! Use official numbers YOU look up.", end: true },
          ] },
        ] },
      { id: "prosecutor", name: "Prosecutor Tan", avatar: "⚖️", sub: "+65 8123 0001", truth: "scam", typology: "gov_official_impersonation", group: "police",
        explain: "The 'prosecutor' appears just to vouch for the officer — a second voice makes the lie feel true. Three people in a chain who all agree is a scam signature, not proof.",
        script: [
          "This is the {{prosecutor|Third 'authority'}} on your case. {{Officer Lim is correct|Vouching for the other scammer}}.",
          { w: 800 },
          "You must act {{immediately|Urgency}} or a {{warrant will be issued|Threat}}.",
          { c: [
            { t: "Send the money 💸", ok: false, money: -1500, life: 1, say: "Another $1,500 gone. The more voices, the more you trusted.", then: ["Good. Do not tell your bank."] },
            { t: "Block & report 🚫", ok: true, pts: 50, say: "Blocked! Report it to the police and the ScamShield helpline (1799).", end: true },
          ], timer: 0 },
        ] },
      { id: "ben", name: "Ben (work)", avatar: "🧑‍💻", sub: "saved contact", truth: "legit", typology: "legit", start: 2600, group: "ben",
        explain: "Ben's a saved colleague with a normal lunch invite. No links, no money, no pressure. Not everything is a scam!",
        script: [
          "lunch at 12:30? 🍜 new ramen place downstairs",
          { c: [{ t: "Sounds great! 🙌", ok: true, pts: 15, say: "Enjoy the ramen!" }, { t: "Can't today, next week?", ok: true, pts: 15, say: "Fair enough." }] },
          "👍 cool!",
        ] },
    ],
  },

  /* ============================================================ 3 */
  {
    id: 3, name: "Dream Job", emoji: "💼", theme: "telegram", colors: ["#ff9800", "#e91e63"], savings: 4000,
    blurb: "Earn $300 a day liking videos?! …what could go wrong.",
    mission: "A recruiter hands you to a mentor, who brings in a friendly 'member'. One real interview invite hides in here too.",
    chats: [
      { id: "jane", name: "Jane • HR", avatar: "👩‍💼", sub: "recruiter", truth: "scam", typology: "fake_job", start: 1000, group: "job",
        explain: "Unsolicited high pay for trivial work, then a move to Telegram. Real employers don't recruit through random DMs, and they never charge you to work.",
        script: [
          "Hi! We're hiring {{part-time online assistants|Unsolicited offer}}. Earn {{$300 per day|Too good to be true}} by liking videos. No experience needed 😊",
          { w: 1000 },
          { c: [
            { t: "\"Tell me more!\" 🤩", ok: false, pts: 0, say: "Curiosity is how they hook you.", then: ["Simply add our mentor on {{Telegram @Alex_mentor|Moves you to another app}} to start."] },
            { t: "\"Which company is this?\" 🧐", ok: true, pts: 25, say: "Great question! Let's see the answer…", then: ["We are a {{global marketing firm|Vague on purpose}}. Please add our mentor on Telegram."] },
            { t: "Block. 🚫", ok: true, pts: 40, say: "Blocked before the trap. Nice.", end: true },
          ] },
          { go: "alex" },
        ] },
      { id: "alex", name: "Mentor Alex", avatar: "🧑‍🏫", sub: "@Alex_mentor", truth: "scam", typology: "fake_job", group: "job",
        explain: "Classic task scam: a small payout builds trust, then you must 'top up' bigger amounts to unlock earnings that never arrive. You should never pay to get paid.",
        script: [
          "Welcome! Complete 3 tasks and get {{$30 right now|Small payout to build trust}} 💰",
          { w: 1500 },
          "✅ Task done! $30 sent. Now for the big money…",
          "For the {{premium set you must top up $500|Pay-to-earn}} — you get {{it all back with profit|Fake promise}}!",
          { go: "lily" },
          { c: [
            { t: "Top up $500 💳", ok: false, money: -500, life: 1, say: "$500 gone. They'll now ask for more.", then: ["Oops, system error. Top up {{another $1,200|Escalating fees}} to unlock your withdrawal."] },
            { t: "Ask for a refund first 💬", ok: false, pts: 10, say: "They'll stall — scammers never refund.", then: ["Refunds {{only after the premium set|Stalling}}. Please hurry."] },
            { t: "\"This is a scam. I'm out.\" 🚪", ok: true, pts: 60, say: "Yes! You never pay to earn.", end: true },
          ] },
        ] },
      { id: "lily", name: "Lily (member)", avatar: "💁‍♀️", sub: "in the same group", truth: "scam", typology: "fake_job", group: "job",
        explain: "Lily is part of the team: a 'happy customer' appearing exactly when you hesitate. Fake testimonials are social proof manufactured by the scammers.",
        script: [
          "OMG I'm in this group too! I {{withdrew $2,000 yesterday|Fake testimonial}}, it's real!! 🤑",
          { w: 900 },
          "Just top up — {{don't miss the premium set|Pressure}}, slots are almost gone!",
          { c: [
            { t: "Believe her & top up 💸", ok: false, money: -500, life: 1, say: "She was working for them. $500 lost.", then: ["See?! Now top up again {{to withdraw|Escalating fees}}."] },
            { t: "Notice she showed up right when I hesitated 🕵️", ok: true, pts: 50, say: "Sharp! Extra friendly voices that 'vouch' are part of the script.", end: true },
          ] },
        ] },
      { id: "northwind", name: "Northwind HR", avatar: "🏢", sub: "careers@northwind", truth: "legit", typology: "legit", start: 3000, group: "northwind",
        explain: "A genuine interview invite: you applied, there's a real time and place, and nobody asks for money, a code or a login. Still, it's fine to verify the company yourself.",
        script: [
          "Hi Jamie, thanks for applying for Marketing Executive at Northwind Pte Ltd. We'd like to invite you for an interview on Thursday 2pm at 1 Raffles Place. Please reply to confirm. — HR Team",
          { c: [
            { t: "Confirm ✅", ok: true, pts: 20, say: "You applied for this role, so it fits." },
            { t: "Check the company's website first 🔎", ok: true, pts: 30, say: "Great habit, even for genuine mails." },
          ] },
          "Great, see you Thursday! 🙂",
        ] },
    ],
  },

  /* ============================================================ 4 */
  {
    id: 4, name: "Heartstrings", emoji: "💘", theme: "whatsapp", colors: ["#f06292", "#ab47bc"], savings: 5000,
    blurb: "A sweet stranger, a gift parcel, and a very expensive 'customs fee'.",
    mission: "Feelings can be weaponised. Notice who joins the chat — and when.",
    chats: [
      { id: "sarah", name: "Sarah 💕", avatar: "👩‍🦰", sub: "met on an app", truth: "scam", typology: "romance", start: 900, group: "love",
        explain: "Fast, intense feelings from someone you've never met, an excuse to avoid video calls, a 'surprise' gift and a request for secrecy — a textbook romance-scam opening.",
        script: [
          "Good morning my love ❤️ I miss you so much.",
          { w: 1200 },
          "I {{sent you a gift parcel from the UK|Gift as bait}} — jewellery and a laptop! {{Don't tell your family|Isolation}}, it's our surprise 😘",
          { c: [
            { t: "Aww thank you! 🥰", ok: false, pts: 0, say: "It's sweet… and it's the setup.", then: ["I can't wait to meet you 😘"] },
            { t: "We've never video called. Can we? 🎥", ok: true, pts: 40, say: "Great test! Scammers avoid live video.", then: ["{{My camera is broken|Excuse to avoid video}} my love 🥺"] },
          ] },
          { go: "customs" },
        ] },
      { id: "customs", name: "Customs Officer", avatar: "🛃", sub: "Singapore Customs?", truth: "scam", typology: "romance", group: "love",
        explain: "Customs never collect fees through chat or gift cards. This 'officer' is an accomplice created to make the parcel story official.",
        script: [
          "This is {{Singapore Customs|Claimed authority}}. A parcel in your name is held. Pay a {{clearance fee of $1,800|Fee to release a 'gift'}} to release it.",
          { w: 900 },
          "We accept {{bank transfer or gift cards|Gift-card payment is a red flag}}.",
          { c: [
            { t: "Pay $1,800 by transfer 🏧", ok: false, money: -1800, life: 1, say: "$1,800 gone for a parcel that never existed.", then: ["Payment received. There is another {{tax of $900|Escalating fees}}."] },
            { t: "Ask for official documents 📄", ok: false, pts: 10, say: "They'll fake some. Better to check with Customs directly.", then: ["Documents sent. {{Time is running out|Urgency}}!"] },
            { t: "Customs don't collect via chat. Report. 🚩", ok: true, pts: 60, say: "Exactly. Check with Customs on their official line.", end: true },
          ] },
          { go: "lawyer" },
        ] },
      { id: "lawyer", name: "Mr Hall (Lawyer)", avatar: "👨‍⚖️", sub: "Sarah's lawyer", truth: "scam", typology: "romance", group: "love",
        explain: "A third voice — the 'lawyer' — confirms the story. Each new character is there to wear down your doubts.",
        script: [
          "I am {{Sarah's lawyer|Third voice vouching}}. The customs fee is real; {{time is running out|Urgency}}.",
          { c: [
            { t: "Pay to help Sarah 💔", ok: false, money: -1800, life: 1, say: "Love shouldn't cost $1,800 in 'fees'.", then: ["Thank you. One last {{release fee|Escalating fees}}…"] },
            { t: "Stop. Tell a friend & report. 🛑", ok: true, pts: 60, say: "Talking to someone you trust breaks the spell.", end: true },
          ] },
        ] },
      { id: "aunt", name: "Aunt Lin", avatar: "👵", sub: "saved contact", truth: "legit", typology: "legit", start: 3200, group: "aunt",
        explain: "Family check-in with chicken rice. No money, links or secrets. Not everything is a scam!",
        script: [
          "Did you eat? 🍗 I made chicken rice, come over on Sunday!",
          { c: [{ t: "Yes auntie, see you Sunday! 🤗", ok: true, pts: 15, say: "Yum!" }] },
          "Good good 😊 bring your appetite",
        ] },
    ],
  },

  /* ============================================================ 5 */
  {
    id: 5, name: "Boss Battle", emoji: "👔", theme: "telegram", colors: ["#26a69a", "#1565c0"], savings: 6000, timed: true,
    blurb: "Your 'CEO' needs a favour. Right now. Clock is ticking ⏱️",
    mission: "Decisions have TIMERS now. If time runs out you'll act on instinct — which scammers love.",
    chats: [
      { id: "ceo", name: "Mr Lee (new number)", avatar: "🧔", sub: "CEO?", truth: "scam", typology: "friend_family_impersonation", start: 900, group: "ceo",
        explain: "A boss on a new number, urgency, secrecy and gift cards. Verify by calling the real number or asking in person — never by replying in the same chat.",
        script: [
          "Hi, it's {{Mr Lee on my new number|New number from an authority figure}}. I'm in a meeting, can't talk.",
          { w: 900 },
          "I need a {{favour urgently|Urgency}} — keep this {{between us|Secrecy}}. Please buy {{5 × $200 Apple gift cards|Gift cards}} and send me the codes.",
          { c: [
            { t: "Buy the gift cards 🎁", ok: false, money: -1000, life: 1, say: "$1,000 of gift cards, gone forever.", then: ["Great. {{Send photos of the codes now|Codes can't be traced back}}."] },
            { t: "Call Mr Lee on his usual number 📞", ok: true, pts: 60, say: "The right move: verify on a channel you already trust.", end: true },
            { t: "Ask: \"What did we talk about last Friday?\" 🧠", ok: true, pts: 35, say: "Good test — a real boss would know.", then: ["No time for that, {{just buy the cards|Dodging verification}}!"] },
          ], timer: 12, def: 0 },
          { go: "assistant" },
        ] },
      { id: "assistant", name: "Executive Assistant", avatar: "👩‍💻", sub: "Mr Lee's office", truth: "scam", typology: "friend_family_impersonation", group: "ceo",
        explain: "The 'assistant' only exists to say \"it's genuine\". Anyone vouching in the same breath as an unusual request is part of the script.",
        script: [
          "Hi, I'm {{Mr Lee's assistant|Second voice vouching}}. He's really busy; {{it's genuine|\"Trust me\"}} — please do it today.",
          { c: [
            { t: "OK, buying them now 🛒", ok: false, money: -1000, life: 1, say: "The second voice pushed you over the line. -$1,000.", then: ["Thanks! Send the codes {{right away|Urgency}}."] },
            { t: "Double-check with Mr Lee in person 🚶", ok: true, pts: 50, say: "Always verify out-of-band.", end: true },
          ], timer: 10, def: 0 },
        ] },
      { id: "priya", name: "Priya (Finance)", avatar: "👩‍💼", sub: "saved contact", truth: "legit", typology: "legit", start: 5000, group: "priya",
        explain: "Urgent doesn't always mean scam. Priya's a saved colleague, asks you to use the company system, and wants no codes, cards or transfers from you.",
        script: [
          "Hi! Please approve PO #4471 in the finance system by 5pm today — it's the monthly vendor run. Thanks 🙏",
          { c: [
            { t: "Approve it inside the company system ✅", ok: true, pts: 30, say: "Right: used the official system, not a link in chat." },
            { t: "Reply: \"Link?\" 🔗", ok: true, pts: 10, say: "No link was needed — it's in the system you already use." },
          ], timer: 14, def: 0 },
          "Thanks!",
        ] },
      { id: "msft", name: "Microsoft Support", avatar: "🖥️", sub: "unknown", truth: "scam", typology: "tech_support", start: 9500, group: "msft",
        explain: "Real tech companies don't cold-message about viruses. A remote-access code lets the scammer see your screen and move money.",
        script: [
          "{{Warning! Your computer has a virus|Fear}}. Hackers are accessing your bank 😱",
          { w: 700 },
          "Install {{AnyDesk|Remote-access tool}} and give me the {{9-digit code|Gives them control of your PC}} so I can fix it.",
          { c: [
            { t: "Install AnyDesk and send the code 💻", ok: false, money: -1500, life: 1, say: "They took over your screen and moved $1,500.", then: ["Thank you. Now log in to your bank so I can {{secure it|Pretext}}."] },
            { t: "Ignore. Run my own antivirus 🛡️", ok: true, pts: 40, say: "Nothing to see here. 👍", end: true },
          ], timer: 10, def: 0 },
        ] },
    ],
  },

  /* ============================================================ 6 */
  {
    id: 6, name: "Chaos Day", emoji: "🌪️", theme: "whatsapp", colors: ["#ff5722", "#7b1fa2"], savings: 8000, timed: true,
    blurb: "Everyone's texting you at once. Scams AND real people. Good luck!",
    mission: "FINAL LEVEL. Juggle many chats at once, beat the timers, and don't flag your real friends.",
    chats: [
      { id: "mum", name: "Mum (new number)", avatar: "👵", sub: "unknown number", truth: "scam", typology: "friend_family_impersonation", start: 800, group: "mum",
        explain: "'Hi Mum, new number' + urgent money + 'can't call' + a stranger's PayNow number is the classic family-impersonation scam. Call your real mum on her old number.",
        script: [
          "Hi mum, this is my {{new number|Unverified number}}, my phone fell in water 😢",
          { w: 800 },
          "Can you PayNow {{$2,800 to my friend|Payment to a stranger}} for me? My banking app is {{locked|Excuse}}. Please {{don't call|Avoids voice}}, I'm in a meeting!",
          { c: [
            { t: "PayNow $2,800 right away 💸", ok: false, money: -2800, life: 1, say: "That wasn't your child. $2,800 lost.", then: ["Thanks mum!! {{Can you send $1,500 more?|Escalation}}"] },
            { t: "Call my child on their OLD number 📞", ok: true, pts: 60, say: "Perfect. The real child will pick up.", end: true },
          ], timer: 11, def: 0 },
        ] },
      { id: "buyer", name: "Buyer (Carousell)", avatar: "🛍️", sub: "wants your PS5", truth: "scam", typology: "ecommerce_marketplace", start: 2500, group: "buyer",
        explain: "An eager buyer who won't bargain and sends a 'secure payment' link where YOU must enter card details to receive money. You never need card details or OTP to get paid.",
        script: [
          "Hi! I'll take the PS5, {{no need to bargain|Too eager}}. I've paid via Carousell Protect.",
          { w: 900 },
          "To receive it, {{verify your bank card here|You never need card details to receive money}}: {{carousell-protect-pay.xyz/receive|Fake site}}",
          { c: [
            { t: "Enter my card details 💳", ok: false, money: -1200, life: 1, say: "Your card was drained for $1,200.", then: ["Almost there! Enter the {{OTP|Banks never ask for OTPs}}."] },
            { t: "Stay in Carousell's own chat & payment ✅", ok: true, pts: 45, say: "Yes — never use links someone sends you.", end: true },
          ], timer: 9, def: 0 },
          { go: "protect" },
        ] },
      { id: "protect", name: "Carousell Protect", avatar: "🛡️", sub: "'support'", truth: "scam", typology: "ecommerce_marketplace", group: "buyer",
        explain: "A fake 'platform support' account joining the chat to vouch for the payment link. Real platforms don't message you out of the blue in outside chats.",
        script: [
          "Hello, we're {{Carousell Protect support|Fake platform account}}. Your payment is {{held for security|Pretext}}. Please verify your card to release it.",
          { c: [
            { t: "Verify my card 💳", ok: false, money: -1200, life: 1, say: "Second push, second loss. -$1,200.", then: ["Thank you. Please {{keep this confidential|Secrecy}}."] },
            { t: "Block and report 🚫", ok: true, pts: 45, say: "Reported! The listing should be flagged too.", end: true },
          ], timer: 9, def: 0 },
        ] },
      { id: "tech", name: "Singtel Technician", avatar: "📡", sub: "refund team", truth: "scam", typology: "tech_support", start: 4500, group: "tech",
        explain: "The 'mistaken refund' is staged on the scammer's screen; the supervisor adds sympathy and secrecy. Nobody legitimate asks for gift cards.",
        script: [
          "We overcharged your broadband, {{a refund of $450 is ready|Unexpected refund bait}}. Please install {{QuickSupport|Remote-access tool}} to process it.",
          { w: 1000 },
          "Oops, I refunded $4,500 by mistake! Please buy {{Google Play gift cards|Gift cards}} for the extra and send the codes.",
          { c: [
            { t: "Buy the gift cards 🎁", ok: false, money: -2000, life: 1, say: "The 'mistake' never happened. $2,000 gone.", then: ["Please hurry, my {{supervisor will be upset|Emotional pressure}}."] },
            { t: "Hang up and call Singtel's official line ☎️", ok: true, pts: 55, say: "Always call back on a number you look up.", end: true },
          ], timer: 10, def: 0 },
          { go: "supervisor" },
        ] },
      { id: "supervisor", name: "Supervisor Lim", avatar: "🧑‍💼", sub: "Singtel", truth: "scam", typology: "tech_support", group: "tech",
        explain: "The 'supervisor' begs and promises secrecy: sympathy plus pressure from a second voice.",
        script: [
          "I'm his supervisor. Please {{help or he loses his job|Emotional pressure}}. We won't tell anyone.",
          { c: [
            { t: "OK, I'll help 😟", ok: false, money: -1000, life: 1, say: "Sympathy cost you $1,000.", then: ["Bless you. {{Codes now please|Urgency}}."] },
            { t: "Sorry, no. Reporting this. 🚩", ok: true, pts: 45, say: "Firm and kind. 👏", end: true },
          ], timer: 9, def: 0 },
        ] },
      { id: "otp", name: "DBS", avatar: "🏦", sub: "official sender ID", truth: "legit", typology: "legit", start: 6500, group: "otp",
        explain: "This genuine notice tells you NOT to share the OTP, has no link, and points you to the number on your card. Confirm it matches something you actually did.",
        script: [
          "DBS: Your OTP is 483920 for the transaction at SHOPEE. Do not share this OTP with anyone, including DBS staff. If you did not request this, call the number on the back of your card.",
          { c: [
            { t: "That's mine — I'm buying something 🛒", ok: true, pts: 25, say: "Only trust it because it matches what you were doing." },
            { t: "Ignore it 🙈", ok: true, pts: 10, say: "Fine if it's not yours — don't share the code, and call your bank if it worries you." },
          ], timer: 10, def: 0 },
        ] },
      { id: "grab", name: "Grab", avatar: "🚗", sub: "your driver", truth: "legit", typology: "legit", start: 8000, group: "grab",
        explain: "A normal ride notification: no money, no links beyond the official app, no secrecy.",
        script: [
          "Your driver is 3 minutes away. White Toyota, plate SKX1234Y. Share this trip with family in the Grab app.",
          { c: [{ t: "Great, heading down 🚶", ok: true, pts: 15, say: "Easy." }], timer: 8, def: 0 },
        ] },
    ],
  },
];
