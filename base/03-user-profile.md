# User profile (base personalization)

> Base prompt. It runs **only once per user**, before installing any squad.
> It produces `{{ROOT}}/user/profile.md`, which the orchestrator and all the bots read.
> Each squad then has its own, more specific questionnaire, which **does not repeat** these questions.

## How to run the interview (instructions for the AI)

1. **Start with what you already know.** Review your memory of the user, `{{ROOT}}/user/profile.md` if it exists, and any document they have given you (CV, notes). Put together a draft of the profile from that.
2. **Confirm, don't re-ask.** Show the draft in a short block: "This is what I know about you. Is it correct?". Mark with `(?)` anything you inferred that is not confirmed.
3. **Ask only what is missing**, in batches of at most 5 questions, starting with the required ones. Offer options when there are any.
4. **Don't invent default values.** If the user doesn't want to answer something, write down `not_specified` and move on.
5. When you finish, write the file, show it in full and ask for an "ok" before continuing.
6. Save in your persistent memory a 3-5 line summary (name, country, language, communication preference) and the file path, so you don't ask again.

## Questions

### Required

| Field | Question | Example answer |
| --- | --- | --- |
| `name` | What do you want the bots to call you? | "Lucía" |
| `country` | Which country and city do you live in? | "Argentina, Buenos Aires" |
| `timezone` | Your time zone? (I can work it out from your city if you like) | `America/Argentina/Buenos_Aires` |
| `preferred_language` | Which language do you want the bots to talk to you in? | "Spanish" |
| `languages` | Which languages do you speak, and at what level? If you don't know your CEFR level, describe it in your own words and I'll translate it | `es: native, en: B1` |
| `channel` | Which app do you want the orchestrator to message you on? Explain the options with the table in `02-architecture.md` §4 (Telegram is the easiest; WhatsApp carries a risk of the number being banned, so a dedicated number is advisable) | "Telegram" |

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
| `llm_provider` | Which model provider do you use? If you already have one set up in Hermes (for example OpenCode Go), that one is used |
| `main_model` | Which model will all the bots use? Recommendation: the most powerful one in the catalog of a fast and affordable provider **at that moment**. Example in September 2026, on OpenCode Go: MiMo V2.6 Pro (Xiaomi), DeepSeek Flash 4.1 or Muse Spark 1.3. If Hermes already has a default model, suggest that one |
| `fallback_model` | (Optional) Another model of the same tier, in case the main one fails or is overloaded |
| `vision_model` | Only if the main model can't see images and some squad needs it (for example, to look at forms or review pieces). It is set up as the auxiliary vision model (`auxiliary.vision`) in the bots that need it, without changing their model. The installer AI checks whether the main model can see images |

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
- Main model: {{main_model}} · fallback: {{fallback_model}} · vision: {{vision_model | the main one}}

## Active squads
- (the orchestrator adds one line per installed squad, with its level)
```

## Contact details: `{{ROOT}}/user/contact.yaml`

Kept separate from the profile because it is sensitive. It is read only by the bots a squad authorizes (for example, the writer for the CV header and the applier for forms). It is in `.gitignore`. Ask only for the fields the user wants to give; each squad may ask for more.

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

- Only the orchestrator modifies this file, always showing the change and asking for confirmation.
- If the user says something that contradicts the profile ("I don't live in Chile anymore"), the orchestrator proposes the update right then.
- Specialist bots read it; they never write it.
