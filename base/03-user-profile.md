# User profile (base personalization)

> Base prompt. Runs **once per user**, before installing any squad.
> Produces `{{ROOT}}/user/profile.md`, which every bot reads. Each squad has its own questionnaire, which **does not repeat** these questions.

## How to run the interview (instructions for the AI)

1. **Start with what you know.** Your memory of the user, `{{ROOT}}/user/profile.md` if it exists, and any document they gave you (CV, notes). Build a draft from that.
2. **Confirm, don't re-ask.** Show the draft in a short block: "This is what I know about you. Is it correct?". Mark unconfirmed inferences with `(?)`.
3. **Ask only what is missing**, at most 5 questions per batch, required ones first. Offer options when there are any.
4. **No invented defaults.** If the user does not want to answer, write `not_specified` and move on.
5. Write the file, show it in full, and ask for an "ok" before continuing.
6. Save in persistent memory a 3-5 line summary (name, country, language, communication preference) and the file path.

## Questions

### Required

| Field | Question | Example answer |
| --- | --- | --- |
| `name` | What do you want the bots to call you? | "Lucía" |
| `country` | Which country and city do you live in? | "Argentina, Buenos Aires" |
| `timezone` | Your time zone? (I can work it out from your city) | `America/Argentina/Buenos_Aires` |
| `preferred_language` | Which language do you want the bots to talk to you in? | "Spanish" |
| `languages` | Which languages do you speak, and at what level? If you don't know your CEFR level, describe it and I'll translate it | `es: native, en: B1` |
| `channel` | Which app do you want the orchestrator and the builder to message you on? Explain the options with the table in `02-architecture.md` §4 (Telegram is the easiest; WhatsApp risks a ban of the number, so a dedicated number is advisable) | "Telegram" |

### Recommended

| Field | Question |
| --- | --- |
| `schedule` | At what times can the bots message you? Any times when you don't want notifications? |
| `tone` | How do you prefer answers: direct and short, or explained? Informal address (for example, Spanish "tú")? |
| `autonomy` | How much do you want the bots to do on their own? `automatic` (default: they only ask you about irreversible things, like applying) · `ask_important` · `ask_everything` |
| `monthly_budget` | Roughly how much do you want to spend per month on AI models? |
| `privacy` | Is there any data they must never use or store? (for example, health, family, ID document) |

### Technical (whoever installs can answer these)

| Field | Question |
| --- | --- |
| `machine` | Where does Hermes run? `laptop` · `desktop` · `vps` · and operating system |
| `always_on` | Does the computer stay on all day? (determines whether scheduled tasks can be used) |
| `llm_provider` | Which model provider do you use? If one is already set up in Hermes (for example OpenCode Go), that one is used |
| `main_model` | The default model suggested for every bot. Recommendation: the most powerful model of a fast, affordable provider **at that moment** (example, September 2026, on OpenCode Go: MiMo V2.6 Pro, DeepSeek Flash 4.1 or Muse Spark 1.3). If Hermes already has a default model, suggest it. The builder then asks, per bot, which model and reasoning effort to use (`07-builder.md` §5) |
| `fallback_model` | (Optional) Another model of the same tier, for when the main one fails or is overloaded |
| `vision_model` | Only if the main model cannot see images and a squad needs it (forms, piece review). Set as `auxiliary.vision` in the bots that need it, without changing their model. The installer checks whether the main model sees images |

## Resulting file: `{{ROOT}}/user/profile.md`

```markdown
# Profile of {{name}}
Updated: {{date}}

## Details
- Country and city: {{country}}
- Time zone: {{timezone}}
- Language for talking with the bots: {{preferred_language}}
- Languages: {{languages}}   # CEFR where applicable

## Preferences
- Channel: {{channel}}
- Notification hours: {{schedule}}
- Tone: {{tone}}
- Autonomy: {{autonomy}}
- Monthly AI budget: {{monthly_budget}}
- Never use or store: {{privacy}}

## Technical environment
- Machine: {{machine}} · Always on: {{always_on}}
- LLM provider: {{llm_provider}}
- Default model: {{main_model}} · fallback: {{fallback_model}} · vision: {{vision_model | the main one}}
- Per-bot models: in each squad's `projects/<key>/squad.yaml`

## Active squads
- (the builder adds one line per installed squad, with its level)
```

## Contact details: `{{ROOT}}/user/contact.yaml`

Separate from the profile because it is sensitive. Read only by the bots a squad authorizes (for example, the writer for the CV header, the applier for forms). In `.gitignore`. Ask only for the fields the user wants to give; each squad may ask for more.

```yaml
full_name: "{{...}}"
email: "{{...}}"
phone: "{{+country code ...}}"
city: "{{...}}"
links:                       # public profiles they want to show
  linkedin: "{{url | not_specified}}"
  others: []
```

## Maintenance rules

- Only the orchestrator modifies this file, showing the change and asking for confirmation. Exception: the builder maintains "Active squads".
- If the user contradicts the profile ("I don't live in Chile anymore"), the orchestrator proposes the update right then.
- Specialists read it; they never write it.
