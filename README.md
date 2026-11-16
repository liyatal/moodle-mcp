# 🎓 moodle-mcp

**Talk to your Moodle.** A tiny [MCP](https://modelcontextprotocol.io) server that lets Claude read your courses, deadlines, grades and files — so you can ask instead of click.

> "What's due this week?"
> "Download the new homework from Analog Circuits."
> "Any announcements in Electromagnetic Fields?"

Built for Tel Aviv University's Moodle, works with any Moodle that has the mobile web service enabled.

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
git clone https://github.com/<you>/moodle-mcp.git
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

## ⚙️ Options

| Variable | Default | Meaning |
| --- | --- | --- |
| `MOODLE_URL` | `https://moodle.tau.ac.il` | Your Moodle site |
| `MOODLE_TOKEN` | – | Token (overrides the `.token` file) |
| `MOODLE_TOKEN_FILE` | `.token` next to the script | Where to read the token from |
| `MOODLE_DOWNLOAD_DIR` | `~/Downloads/moodle` | Where downloads go |

## 🔒 Security

- Your token is as good as your password for reading Moodle. Keep it out of git and chats.
- The token is only ever sent to the configured Moodle host — downloads from any other host are refused.
- Downloads can't escape the download directory.

---

Not affiliated with Tel Aviv University or Moodle.
