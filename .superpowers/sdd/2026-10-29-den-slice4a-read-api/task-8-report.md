# Task 8 report
Changed: .claude/skills/story-critique/SKILL.md (rewritten: start_critique/critique_status/cancel/resume, imperative rules + examples, bans old subagent flow); .claude/skills/story-discuss/SKILL.md (open_discussion first, editor attitude kept, tells user conclusions are not saved, cross-story label-map section removed since open_discussion is single-story); CLAUDE.md (core principles, diagram, usage, export, web, viz.py/render.py as library, server/ retired slice 5); web/README.md (den-only reading, export, cutover section).
Suites: pytest 916 passed, coverage 100%; vitest 200 passed / 8 skipped; tsc clean.
Concerns: label-map cross-story guidance dropped from story-discuss (no MCP source for it). Cutover/smoke not done (R4). Root README.md still mentions old flow (not in brief scope).

## Fix round 1
dev.sh now ensures den via DenClient.ensure() (same path as MCP shim; reuses healthy den, else detached spawn) then starts vite; Ctrl-C stops only vite (den is detached/shared, idle-exits). README.md/README.en.md updated (web=dev.sh, CLI=/story-critique,/story-discuss,export, 4b note, DB not stories/). CLAUDE.md den bullet and web/README.md cutover (no uvicorn server.app) fixed. pytest 916/100%, vitest 200 pass. dev.sh not run live (would spawn real den).
