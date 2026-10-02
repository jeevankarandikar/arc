# Arc design

The rules for every change to `index.html`. Apple's Human Interface Guidelines are the canon. Never use Apple's Design Resources downloads (the SF Pro, New York and SF Mono font files, SF Symbols exports, UI kits and their tokens, device bezels) or anything traced from them. The system font through `-apple-system` is fine because the page asks the device for it and ships no Apple files.

## Principles

- **A number gets a shape.** Put a ring, bar, dot row, sparkline or range slider next to any number that has a target, a range or a trend. Tables are for lists a person scans, such as the day's lifts, and never for progress.
- **The first screen says what to do today.** The day's checklist, then today's dials, then the last 7 days, then the six-month bars. Detail sits one tap away in folds, the explorer or the day switcher.
- **Glass is for navigation only.** The tab bar, the Log button, the top bar's scroll edge and the log sheet use glass. Content cards stay solid white.
- **Light mode only.** The page sets `color-scheme: light`.
- **Copy is short.** A card says one thing. Sub-lines run a few words. Explanations go in a fold.

## Color

Tokens live on `:root`. Use the token, never the hex, in new rules.

| Token | Value | Use |
|---|---|---|
| `--bg` | `#F6F6F8` | Page background |
| `--card` | `#FFFFFF` | Cards, tiles, folds |
| `--fill` | `#EDEDF1` | Tracks behind bars and rings, chips, segmented control |
| `--text` | `#111214` | Primary text, target ticks, slider dots in range |
| `--text-2` | `#4A4D56` | Secondary text |
| `--text-3` | `#6B6E78` | Labels, dates, units. 5.1:1 on white, 4.7:1 on `--bg` |
| `--line` | `#E7E8EC` | Row dividers |
| `--accent` | `#E8452C` | The one accent: data fills, rings, dots, large numbers, the Log button. 4.0:1 on white, so never for small text |
| `--accent-ink` | `#B8321D` | Accent for small text and warnings. 6.0:1 on white |
| `--accent-soft` | `rgba(232,69,44,.1)` | Warning chip backgrounds |

Today's dials are separate single rings in accent on a `--fill` track. Concentric three-ring stacks are left to Apple's Activity rings, as the HIG asks. There is no second accent color, no gradient text and no colored side rails on cards.

## Type

Three families. Archivo 900 and JetBrains Mono load from Google Fonts. Everything else uses the system font.

| Role | Font | Size and weight |
|---|---|---|
| Large tab title | Archivo | 900, 34px, tracking -0.035em |
| Program day title | Archivo | 900, 22px |
| Section header (`.h`) | System | 600, 20px |
| Card or fold title | System | 600, 16 to 17px |
| Body | System | 400, 15px, line height 1.45 |
| Sub-line, note | System | 400, 12 to 13px, `--text-3` |
| Label (`.k`, chips) | System | 600, 12 to 13px, sentence case |
| Hero number | JetBrains Mono | 600, 30 to 38px, tracking -0.045em |
| Tile number | JetBrains Mono | 600, 21px |
| Table and row numbers | JetBrains Mono | 500, 13 to 15px, tabular figures |
| Tab bar label | System | 600, 10px |

Labels are sentence case, never uppercase. Units follow the number in the system font at 12px in `--text-3`, for example **152.0** lb.

## Space, shape, depth

| Thing | Value |
|---|---|
| Page gutter | 16px each side, content max width 680px |
| Gap between cards | 12px, 10px inside tile grids |
| Card padding | 16px |
| Card radius | 22px (`--r`), tiles 18px, chips and pills fully round |
| Card shadow | `--shadow`, a faint two-layer shadow, no borders |
| Tap targets | 44px minimum, 48px for fold headers |
| Bottom padding | 116px plus the safe area, so the dock never covers content |

## Motion

- `--spring` for the tab lens and segmented thumbs, `--ease` for the sheet, folds and presses.
- Presses scale to 0.92 to 0.97.
- `prefers-reduced-motion` turns every transition and animation off.
- `prefers-reduced-transparency` swaps glass for solid fills.

## Components

| Component | Class or function | Rules |
|---|---|---|
| Tile | `tile()`, `.tile` | Label, number with unit, 2 to 4 word sub-line, then one visual. A tile that opens a chart gets a chevron. |
| Checklist | `todo()`, `.todo-h`, `.tdr` | The day's plan as timed rows with a check circle and kcal on the right. Rows check themselves when the log has the meal, weigh-in or session; taps are saved per day in localStorage. The header names the lifting day, and `pickDay()` swaps it when the planned day would hit a muscle trained yesterday. |
| Dials | `todayCard()`, `.dials` | Calories, protein, and workouts this week. One ring per dial with the number inside and "of target" below. |
| Bar with target | `meter(frac, tick)` | Fill in accent, target as a dark tick, deeper red past the target. `mini` is the 84px bar inside week rows. |
| Dots | `dots(n, of)` | Counts out of a small total, such as workouts of 4 or drink nights of 7. |
| Sparkline | `spark(values)` | Trend inside a tile, no axes, accent line. |
| Range slider | `rangeBar(v, lo, hi, min, max)` | Labs and body fat. Gray band is the normal or goal range. The dot is dark in range and accent outside it. |
| Physique compare | `physique()`, `.px` | Pose chips (front, biceps, side, back, back biceps), then Slider, Side by side or Timelapse. The slider wipes the before frame over the after one with a white line and a round handle that also takes arrow keys. Month tags sit on the photos in solid white pills. Weight and body fat for both months sit under the photo with the change between them. Before and After buttons pick which slot a thumbnail fills. Timelapse never autoplays with reduced motion. The frames exist only on the Mac and the phone, so the artifact shows a one-line note instead. |
| Warm-up ramp | `ramp()` in `program()`, `.wu` | One row of steps per lift, growing toward the work weight. Warm-up steps in `--fill`, the work weight in accent, weight in mono and reps below. Bodyweight moves get a line of text. |
| Stacked bar | `plan()` | A day's calories or protein by meal, with the target tick. |
| Explorer | `explorer()` | Metric chips, W, M, 6M, Y, All, previous and next, scrubbing. Bars for daily totals, lines for levels, dashed line for the target. No list of values under the chart: the summary line and scrubbing carry the numbers, and the list exists only for VoiceOver. The metric's explanation sits behind an info button beside the summary label. |
| Paired bars | `alcohol()`, `.vs` | Two measures compared, such as the morning after drinking against other mornings: one accent bar and one dark bar per measure, from zero, value on the right, and a note saying which way is better. |
| Pair chart | explorer type `pair` | Energy: eaten as accent bars, burned as a dark tick on each bar, with a legend. The balance only counts days that have both. |
| Segmented control | `.seg`, `.seg.four`, `.seg.three` | White thumb on `--fill`, spring animation. |
| Fold | `details.fold` | Rules, warm-ups, supplements, shopping list, full histories. Title in 16px semibold, a short count on the right, chevron. |
| Compact table | `.tbl2` | Lists only: the program, every lift, supplements. Label left, numbers right in mono. |
| Chips and pills | `.chip`, `.pill` | Chips switch metrics. Pills tag items, with `.pill.warn` for gaps. |
| Tab bar | `.tabbar.glass` | Floating capsule, six tabs, sliding lens, accent for the selected tab. |
| Log button | `.logbtn` | Tinted glass circle beside the tab bar. |
| Sheet | `.sheet` | Glass, 34px radius, inset from the edges, grab handle. |

## Showing data

- A summary line sits above every chart: the number for the period, then its dates.
- Bars start at zero, and y labels sit on the trailing side.
- Color is never the only cue. Two series differ in shape too, such as bars for eaten and ticks for burned.
- The target is always visible: a tick on a bar, a dashed line on a chart, "of 2,500" after a number.
- Out of range or behind target shows in accent. Everything else stays neutral, so red means something.
- Monthly estimates draw lighter than daily data. Partial days say "partial".
- Never repeat a chart as a table. If a plot shows the numbers, the plot is enough.
- Averages come with their window, such as "avg a day" or "28-day avg".
- Numbers use thousands separators and one decimal at most.

## Writing on the page

The global writing rules apply, and the hook in JeevsHarness checks them.

- No em dashes. An en dash only inside a number or date range.
- No middle-dot separators between items.
- No paired "not this, that" sentences and no rhetorical groups of three.
- None of the banned words.
- Sub-lines are fragments of a few words. A note is one or two plain sentences.

## Before publishing

1. Run the writing check on `index.html`.
2. Load the page at 402 by 874 in the Browser pane and check every tab, with no console errors.
3. Open every fold and switch every segmented control once.
4. Rebuild the artifact fragment and republish.
