# 🎓 moodle-mcp

<div dir="rtl">

**מדברים עם ה-Moodle.** שרת [MCP](https://modelcontextprotocol.io) קטן שנותן ל-Claude לקרוא את הקורסים, המטלות, הציונים והקבצים שלכם — שואלים במקום ללחוץ.

[English below ↓](#english)

</div>

![moodle-mcp demo](demo/demo.gif)

<div dir="rtl">

<sub>הדמו משתמש בנתוני דוגמה. [הסרטון המלא](demo/demo.mp4)</sub>

> "מה יש לי להגיש השבוע?"<br>
> "תוריד לי את שיעורי הבית החדשים במעגלים אנלוגיים"<br>
> "יש הודעות חדשות מהמרצים?"<br>
> "תסביר לי את הפרויקט החדש במבנה המחשב"

נבנה באוניברסיטת תל אביב, עם הגדרות מוכנות ל-37 אוניברסיטאות ומכללות בארץ. לקריאה בלבד: לא מגיש, לא מפרסם ולא משנה שום דבר.

## ⚡ הדרך הקלה: תנו ל-Claude להתקין

פותחים את [Claude Code](https://claude.com/claude-code) וכותבים לו:

</div>

```text
אני לומד בטכניון, תתקין לי את https://github.com/raztassa2000-eng/moodle-mcp
```

<div dir="rtl">

משם Claude יוריד את הפרויקט, יתקין אותו, יבחר את המוסד שלכם ויחבר את השרת. בסוף הוא יבקש מכם דבר אחד: לשמור את ה-token בעצמכם (שלב 2 למטה). את ה-token לא מדביקים בצ'אט.

## 🧰 מה הוא יודע לעשות

| כלי | מה הוא עושה |
| --- | --- |
| `list_courses` | הקורסים שאתם רשומים אליהם |
| `course_contents` | יחידות, פעילויות וקבצים של קורס |
| `upcoming_deadlines` | מטלות ובחנים בימים הקרובים |
| `assignments` | תאריכי הגשה, סטטוס ההגשה שלכם וקבצים מצורפים |
| `grades` | הציונים שלכם בקורס |
| `forum_discussions` | הודעות אחרונות בפורומים ובלוח ההודעות |
| `download_file` | שמירת קובץ מהקורס ל-`~/Downloads/moodle` |

## 🚀 התקנה ידנית

### 1. מורידים ומתקינים

</div>

```bash
git clone https://github.com/raztassa2000-eng/moodle-mcp.git
cd moodle-mcp
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

<div dir="rtl">

### 2. משיגים token

ב-Moodle: תמונת הפרופיל ← **העדפות** ← **מפתחות אבטחה** ← מעתיקים את המפתח של *Moodle mobile web service*.

כשהמפתח בלוח, מריצים בתיקיית הפרויקט:

</div>

```bash
pbpaste > .token && chmod 600 .token
```

<div dir="rtl">

הקובץ `.token` לא נכנס ל-git. אפשר גם להשתמש במשתנה הסביבה `MOODLE_TOKEN`.

### 3. מחברים ל-Claude

ב-**Claude Code** (מחליפים את `tau` במפתח של המוסד שלכם):

</div>

```bash
claude mcp add moodle -s user -e MOODLE_SITE=tau -- "$PWD/.venv/bin/python" "$PWD/moodle_mcp.py"
```

<div dir="rtl">

ב-**Claude Desktop** מוסיפים ל-`claude_desktop_config.json` ומפעילים מחדש את האפליקציה:

</div>

```json
{
  "mcpServers": {
    "moodle": {
      "command": "/full/path/to/moodle-mcp/.venv/bin/python",
      "args": ["/full/path/to/moodle-mcp/moodle_mcp.py"],
      "env": { "MOODLE_SITE": "tau" }
    }
  }
}
```

<div dir="rtl">

## 🏫 בוחרים מוסד

מגדירים את `MOODLE_SITE` לאחד מהמפתחות הבאים (ברירת המחדל: `tau`).

**אוניברסיטאות**

`tau` תל אביב · `technion` הטכניון · `bgu` בן-גוריון · `ariel` אריאל · `openu` האוניברסיטה הפתוחה

**מכללות להנדסה, עיצוב וכלליות**

`hit` HIT חולון · `sce` סמי שמעון · `braude` בראודה · `azrieli` עזריאלי ירושלים · `jct` המרכז האקדמי לב · `shenkar` שנקר · `bezalel` בצלאל · `jamd` האקדמיה למוסיקה ולמחול · `mta` האקדמית תל אביב-יפו · `colman` המכללה למינהל · `ruppin` רופין · `kinneret` כנרת · `wgalil` גליל מערבי · `achva` אחוה · `zefat` צפת · `schechter` מכון שכטר

**מכללות לחינוך**

`smkb` סמינר הקיבוצים · `levinsky` לוינסקי · `wingate` וינגייט · `beitberl` בית ברל · `oranim` אורנים · `dyellin` דוד ילין · `kaye` קיי · `washington` גבעת ושינגטון · `talpiot` תלפיות · `shaanan` שאנן · `orot` אורות ישראל · `efrata` אפרתה · `hemdat` חמדת · `sakhnin` סכנין · `qsm` אלקאסמי · `arabcol` המכללה האקדמית הערבית לחינוך, חיפה

**המוסד שלכם לא ברשימה?** אצל העברית, בר-אילן, חיפה, רייכמן, אפקה, ספיר, תל-חי ואחרים ה-Moodle יושב מאחורי מסך התחברות או הגנת בוטים, ולכן לא ניתן היה לבדוק את הכתובת אוטומטית. מגדירים במקום זה את `MOODLE_URL` לכתובת ה-Moodle שלכם — ומוזמנים לפתוח PR שמוסיף אותה.

כדאי לדעת:

- כל 37 האתרים נבדקו כאתרי Moodle פעילים (נובמבר 2026), אבל רק תל אביב נבדקה מקצה לקצה עם token אמיתי. האם אפשר להוציא token תלוי בהגדרות של כל מוסד.
- חלק מהמוסדות פותחים Moodle חדש כל שנה (`moodle26…`, `moodle27…`), ולכן הכתובות האלה דורשות עדכון שנתי.

## ⚙️ הגדרות

| משתנה | ברירת מחדל | משמעות |
| --- | --- | --- |
| `MOODLE_SITE` | `tau` | מפתח המוסד מהרשימה למעלה |
| `MOODLE_URL` | – | כתובת של כל Moodle אחר (גובר על `MOODLE_SITE`) |
| `MOODLE_TOKEN` | – | ה-token (גובר על הקובץ `.token`) |
| `MOODLE_TOKEN_FILE` | `.token` ליד הסקריפט | מאיפה לקרוא את ה-token |
| `MOODLE_DOWNLOAD_DIR` | `~/Downloads/moodle` | לאן נשמרות ההורדות |

## 🔒 אבטחה

- ה-token שווה ערך לסיסמה לקריאת ה-Moodle שלכם. לא מעלים אותו ל-git ולא מדביקים אותו בצ'אט.
- ה-token נשלח רק לשרת ה-Moodle שהוגדר. הורדה מכל כתובת אחרת נחסמת.
- הורדות לא יכולות לצאת מתיקיית ההורדות.

</div>

---

<a name="english"></a>

## 🇬🇧 English

**Talk to your Moodle.** A tiny [MCP](https://modelcontextprotocol.io) server that lets Claude read your courses, deadlines, grades and files — so you can ask instead of click. Read-only by design: it never submits, posts or changes anything.

Built at Tel Aviv University, with presets for 37 Israeli universities and colleges — and it works with any other Moodle that hands out a web service token.

### ⚡ The easy way: let Claude install it

Open [Claude Code](https://claude.com/claude-code) and say:

```text
Install https://github.com/raztassa2000-eng/moodle-mcp for me — I study at the Technion
```

Claude clones, installs, picks your institution and connects the server. You only save the token yourself (step 2 below) — never paste it into the chat.

### 🚀 Manual setup

```bash
git clone https://github.com/raztassa2000-eng/moodle-mcp.git
cd moodle-mcp
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

**Token:** in Moodle, profile picture → **Preferences** → **Security keys** → copy the key for *Moodle mobile web service*, then:

```bash
pbpaste > .token && chmod 600 .token
```

**Connect** (replace `tau` with your institution's key from the list above):

```bash
claude mcp add moodle -s user -e MOODLE_SITE=tau -- "$PWD/.venv/bin/python" "$PWD/moodle_mcp.py"
```

For Claude Desktop, use the JSON block shown above. Run `.venv/bin/python moodle_mcp.py --sites` for the full list of institutions with names and URLs; for anything not listed, set `MOODLE_URL`.

All 37 sites were checked to be live Moodle sites (November 2026), but only TAU has been tested end to end with a real token.

---

## 🤖 Instructions for Claude (automatic install)

If a user gave you this repository and asked you to install it, do this:

1. Clone the repo to a sensible permanent location (ask if unsure), create `.venv`, and `pip install -r requirements.txt`. Python 3.10+ is required.
2. Map the institution the user named to a key: run `.venv/bin/python moodle_mcp.py --sites`. If it isn't listed, ask the user for their Moodle address and use `MOODLE_URL` instead of `MOODLE_SITE`.
3. Register the server with absolute paths:
   `claude mcp add moodle -s user -e MOODLE_SITE=<key> -- <repo>/.venv/bin/python <repo>/moodle_mcp.py`
4. **Do not ask for the token in chat and do not read `.token`.** Tell the user to copy their key from Moodle (Preferences → Security keys) and run `pbpaste > <repo>/.token && chmod 600 <repo>/.token` themselves. On Windows/Linux, have them save it to that file with their own editor.
5. After they confirm, verify with `MOODLE_SITE=<key> .venv/bin/python -c "import moodle_mcp as m; print(len(m.list_courses()), 'courses')"`, then tell them to start a new session so the tools load.
6. If verification fails with `invalidtoken` or a web-service error, say so plainly: their institution may not issue tokens to students. Do not try to obtain a token another way.

---

Not affiliated with any university, college or Moodle.
