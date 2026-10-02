# Arc

A personal health dashboard you run from chat. You tell Claude what you ate, lifted and weighed, and it keeps one HTML page current: calories and protein, lifts and estimated 1RMs, weight and body fat, sleep, goals, labs. There is no app to type into and no server. The page is a single file you open in your browser.

## Start

You need [Claude Code](https://claude.com/claude-code) and a Mac or Linux terminal.

```bash
git clone https://github.com/jeevankarandikar/arc.git arc
cd arc
claude
```

Then say: **Set me up.**

Claude reads `CLAUDE.md`, sees there is no `PROFILE.md` yet, and walks you through a ten minute interview: your goal, your gym, your food, what devices you wear. It sets your targets, builds a training program that fits your week, fills in the dashboard and shows it to you. After that you just chat:

- "had two eggs and toast"
- a photo of your plate or a nutrition label
- "bench 155x8, 155x7, 145x8"
- "weighed 171.4 fasted"
- "how is my protein this week?"

Open `index.html` any time to see the page. Add `series.js` history from Apple Health, Whoop, a smart scale or Strong if you have them, and Claude will tell you how.

## Keep your data private

Your logs, weight, labs and photos end up in this folder. Do not push them to the public repo you cloned from.

- Claude will offer to remove the public remote or point it at a private repo of yours during setup.
- `data/`, `physique/` and `PROFILE.md` are gitignored. `series.js` and `index.html` become personal once filled, so keep them in a private place too.
- Nothing is sent anywhere. The page reads local files.

## What is in here

| file | what it is |
|---|---|
| `CLAUDE.md` | the instructions Claude follows: onboarding, logging rules, how to edit the page |
| `index.html` | the dashboard, with your data blocks at the top |
| `series.js` | daily history built from exports |
| `tools/` | scripts that build `series.js`, import old lift logs and align physique photos |
| `DESIGN.md` | the visual rules, if you want to change how it looks |
| `PROFILE.md` | created during setup, holds everything about you |

## Not medical advice

Arc estimates calories and tracks numbers. It does not diagnose or prescribe. Take medication and lab questions to your doctor.
