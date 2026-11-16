# 🎓 moodle-mcp

**Talk to your Moodle.** A tiny [MCP](https://modelcontextprotocol.io) server that lets Claude read your courses, deadlines, grades and files — so you can ask instead of click.

[🇮🇱 הוראות בעברית](#hebrew)

![moodle-mcp demo](demo/demo.gif)

<sub>Demo uses sample data. [Full-quality video](demo/demo.mp4)</sub>

> "What's due this week?"
> "Download the new homework from Analog Circuits."
> "Any announcements in Electromagnetic Fields?"

Built at Tel Aviv University, with presets for 37 Israeli universities and colleges — and it works with any other Moodle that hands out a web service token.

## 🧰 Tools

| Tool | What it does |
| --- | --- |
| `list_courses` | Courses you're enrolled in |
| `course_contents` | Sections, activities and files of a course |
| `upcoming_deadlines` | Assignments and quizzes due in the next N days |
| `assignments` | Due dates, your submission status, attached files |
| `grades` | Your grade items in a course |
| `forum_discussions` | Latest forum posts and announcements |
| `download_file` | Save a course file to `~/Downloads/moodle` |

Read-only by design: it never submits, posts or changes anything.

## 🚀 Setup

```bash
git clone https://github.com/raztassa2000-eng/moodle-mcp.git
cd moodle-mcp
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

### 1. Get your token

In Moodle: profile picture → **Preferences** → **Security keys** → copy the key for *Moodle mobile web service*.

Copy it to the clipboard, then:

```bash
pbpaste > .token && chmod 600 .token
```

(`.token` is git-ignored. You can use the `MOODLE_TOKEN` environment variable instead.)

### 2. Connect it to Claude

**Claude Code**

```bash
claude mcp add moodle -s user -- "$PWD/.venv/bin/python" "$PWD/moodle_mcp.py"
```

**Claude Desktop** — add to `claude_desktop_config.json`, then restart the app:

```json
{
  "mcpServers": {
    "moodle": {
      "command": "/full/path/to/moodle-mcp/.venv/bin/python",
      "args": ["/full/path/to/moodle-mcp/moodle_mcp.py"]
    }
  }
}
```

## 🏫 Pick your institution

TAU is the default. For anywhere else, set `MOODLE_SITE` to one of these keys:

| | Keys |
| --- | --- |
| **Universities** | `tau` · `technion` · `bgu` · `ariel` · `openu` |
| **Engineering, design & general colleges** | `hit` · `sce` · `braude` · `azrieli` · `jct` · `shenkar` · `bezalel` · `jamd` · `mta` · `colman` · `ruppin` · `kinneret` · `wgalil` · `achva` · `zefat` · `schechter` |
| **Colleges of education** | `smkb` · `levinsky` · `wingate` · `beitberl` · `oranim` · `dyellin` · `kaye` · `washington` · `talpiot` · `shaanan` · `orot` · `efrata` · `hemdat` · `sakhnin` · `qsm` · `arabcol` |

```bash
claude mcp add moodle -s user -e MOODLE_SITE=technion -- "$PWD/.venv/bin/python" "$PWD/moodle_mcp.py"
```

In Claude Desktop, add `"env": { "MOODLE_SITE": "technion" }` to the server block. Run `.venv/bin/python moodle_mcp.py --sites` for full names and URLs.

**Not on the list?** Hebrew University, Bar-Ilan, Haifa, Reichman, Afeka, Sapir, Tel-Hai and others sit behind a login wall or bot protection, so their address couldn't be checked automatically. Set `MOODLE_URL` to your Moodle's address instead — and open a PR to add it.

Good to know:
- All 37 sites were checked to be live Moodle sites (November 2026), but only TAU has been tested end to end with a real token. Whether you can get a token depends on your institution's settings.
- Some institutions open a new Moodle every academic year (`moodle26…`, `moodle27…`), so those addresses will need a yearly update.

## ⚙️ Options

| Variable | Default | Meaning |
| --- | --- | --- |
| `MOODLE_SITE` | `tau` | Institution key from the list above |
| `MOODLE_URL` | – | Any Moodle address (overrides `MOODLE_SITE`) |
| `MOODLE_TOKEN` | – | Token (overrides the `.token` file) |
| `MOODLE_TOKEN_FILE` | `.token` next to the script | Where to read the token from |
| `MOODLE_DOWNLOAD_DIR` | `~/Downloads/moodle` | Where downloads go |

## 🔒 Security

- Your token is as good as your password for reading Moodle. Keep it out of git and chats.
- The token is only ever sent to the configured Moodle host — downloads from any other host are refused.
- Downloads can't escape the download directory.

<a name="hebrew"></a>

## 🇮🇱 הוראות בעברית

<div dir="rtl">

**מדברים עם ה-Moodle.** שרת MCP קטן שנותן ל-Claude לקרוא את הקורסים, המטלות, הציונים והקבצים שלכם — שואלים במקום ללחוץ. הוא לקריאה בלבד: לא מגיש, לא מפרסם ולא משנה שום דבר.

### 1. התקנה

</div>

```bash
git clone https://github.com/raztassa2000-eng/moodle-mcp.git
cd moodle-mcp
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

<div dir="rtl">

### 2. השגת token

ב-Moodle: תמונת הפרופיל ← **העדפות** ← **מפתחות אבטחה** ← מעתיקים את המפתח של *Moodle mobile web service*.

כשהמפתח בלוח, מריצים בתיקיית הפרויקט:

</div>

```bash
pbpaste > .token && chmod 600 .token
```

<div dir="rtl">

הקובץ `.token` לא נכנס ל-git. ה-token שווה ערך לסיסמה לקריאת ה-Moodle שלכם — לא משתפים אותו.

### 3. חיבור ל-Claude

**Claude Code:**

</div>

```bash
claude mcp add moodle -s user -- "$PWD/.venv/bin/python" "$PWD/moodle_mcp.py"
```

<div dir="rtl">

**Claude Desktop:** מוסיפים את הבלוק `mcpServers` שמופיע למעלה לקובץ `claude_desktop_config.json` (עם הנתיב המלא לתיקייה), ומפעילים מחדש את האפליקציה.

### 4. שואלים

- "מה יש לי להגיש השבוע?"
- "תוריד לי את שיעורי הבית החדשים במעגלים אנלוגיים"
- "יש הודעות חדשות מהמרצים?"
- "תסביר לי את הפרויקט החדש במבנה המחשב"

### לא לומדים בתל אביב?

ברירת המחדל היא אוניברסיטת תל אביב. לכל מוסד אחר מגדירים את `MOODLE_SITE` לאחד מ-37 המפתחות שבטבלה "Pick your institution" למעלה (למשל `technion`, `bgu`, `hit`, `braude`, `smkb`):

</div>

```bash
claude mcp add moodle -s user -e MOODLE_SITE=technion -- "$PWD/.venv/bin/python" "$PWD/moodle_mcp.py"
```

<div dir="rtl">

המוסד שלכם לא ברשימה (למשל העברית, בר-אילן, חיפה, רייכמן, אפקה, ספיר)? מגדירים את `MOODLE_URL` לכתובת ה-Moodle שלכם. שימו לב: רק תל אביב נבדקה מקצה לקצה עם token אמיתי; בשאר המוסדות נבדק רק שאתר ה-Moodle פעיל.

</div>

---

Not affiliated with Tel Aviv University or Moodle.
