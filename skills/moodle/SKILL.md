---
name: moodle
description: Use the student's Moodle (courses, deadlines, assignments, grades, forum announcements, course files) through the moodle MCP server. Use when the user asks what is due, about homework, assignments, exams, quizzes, grades, lecturer announcements, course materials or a course project, or wants a study plan built around their real deadlines.
---

# Moodle for students

The `moodle` MCP server reads the user's own Moodle account. It is read-only: it cannot submit, post or change anything, and you should never try to work around that.

## Which tool for which question

| The user asks | Call |
| --- | --- |
| "Anything new?", "what did I miss?", catching up after a few days | `whats_new` (default 7 days) — one call covers every course |
| "What's due?", "what do I have this week?", planning their week | `upcoming_deadlines` (default 14 days; pass `days` for a different window) |
| Exam dates, "what's on my calendar?" | `calendar_events` (default 30 days) |
| Anything about one course | `list_courses` first to get the course id, then the course tool |
| Homework, assignment details, "did I submit?", "what did I get?", grader comments | `assignments(course_id)` |
| Quizzes: when they open, time limit, my attempts | `quizzes(course_id)` |
| Lecture slides, PDFs, "the new project", course materials | `course_contents(course_id)`, then `download_file` for the file that matches |
| "Download everything for X", preparing for an exam | `download_course(course_id)`; pass `section` for one unit |
| Grades in one course | `grades(course_id)` |
| "How am I doing overall?" | `grades_overview` |
| "Any announcements?", "what did the lecturer say?" | `forum_discussions(course_id)`, then `forum_thread(discussion_id)` to read the replies |
| "Was my work graded?", "any notifications?" | `notifications` |

## How to work

- Match course names loosely. Course names often contain both the Hebrew and English name, and users refer to courses by nickname ("analog", "מבנה"). If more than one course could match, ask which one.
- For "anything new?" questions across all courses, call `whats_new` instead of querying each course. Report newest first, with the course name.
- `download_course` stops after about 45 seconds. If `remaining` is above 0, call it again with the same arguments until it reaches 0; files already saved are skipped.
- When the user wants to understand an assignment or project, download the file and read it before explaining. Summarise the goal, what to hand in, the due date, and a sensible first step.
- Before suggesting a study plan or schedule, check `upcoming_deadlines` so the plan respects real due dates.
- Give dates in the user's local format and say how far away they are ("Wednesday 23:59, in 2 days").
- Files are saved under `~/Downloads/moodle`. Tell the user the exact path you saved to. Pass a short `subfolder` per course to keep things organised.

## Never

- Never submit, upload or post anything to Moodle, or suggest that you did. Submitting stays the user's job.
- Never ask the user to paste their Moodle token or password into the chat, and never read or print the `.token` file.
- If a tool fails with `invalidtoken`, tell the user their key was reset or expired and that they need to save a new one (see the project README). Do not try to get a token another way.
