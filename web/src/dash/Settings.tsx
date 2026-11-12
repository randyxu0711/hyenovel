import { useEffect, useRef, useState, type PointerEvent, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { api, DashError, type ArchivedSession, type CardDraft, type Character, type RecentSession, type SessionDetail } from "./api";
import Figure from "./Figure";
import CardEditor, { SAVED_LIMITS } from "./CardEditor";
import Icon, { type IconName } from "./Icon";
import { errorMessage, localized, setLang, useLang, useT, type Lang, type MsgKey } from "./i18n";
import MemoryPage from "./MemoryPage";
import NewCharacter, { NewSlot } from "./NewCharacter";
import { setPaperFlow, usePaperFlow } from "./paperFlow";
import { loadPaperSize, PAPER_SIZE_KEY, type PaperSize } from "./Paper";
import { speakerChanges } from "./Talk";
import { selectTheme, setMode, useThemeState, type ModePref } from "./theme";
import { useCharacters } from "./useCharacters";
import { companionId, setCompanion } from "./useTalk";
import { whenLabel } from "./when";

const MODES: { pref: ModePref; key: MsgKey; icon: IconName }[] = [
  { pref: "system", key: "set.mode.system", icon: "auto" }, { pref: "light", key: "set.mode.light", icon: "sun" },
  { pref: "dark", key: "set.mode.dark", icon: "moon" },
];
const SIZES: { size: PaperSize; key: "set.size.s" | "set.size.m" | "set.size.l" }[] = [
  { size: "s", key: "set.size.s" }, { size: "m", key: "set.size.m" }, { size: "l", key: "set.size.l" },
];
const LANGS: { lang: Lang; label: string }[] = [{ lang: "zh-Hant", label: "繁體中文" }, { lang: "en", label: "English" }];

function byWork(rows: RecentSession[]) {
  const groups = new Map<string, { slug: string; title: string; rows: RecentSession[] }>();
  for (const r of rows) {
    const slug = r.slug ?? "";
    if (!groups.has(slug)) groups.set(slug, { slug, title: r.title ?? "", rows: [] });
    groups.get(slug)!.rows.push(r);
  }
  return [...groups.values()];
}

export const plain = (s: string) => s.replace(/\*\*|__|`/g, "").replace(/^#+\s*/, "");

/** 舊討論封存:唯讀。直接列出,點一局看逐字;沒有輸入框。 */
function Archive() {
  const t = useT();
  const lang = useLang();
  const chars = useCharacters();
  const { mode } = useThemeState();
  const [rows, setRows] = useState<RecentSession[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [detail, setDetail] = useState<SessionDetail | null>(null);
  useEffect(() => {
    let live = true;
    api.recentSessions(100, { legacy: true }).then(
      r => { if (live) setRows(r.filter(s => s.legacy)); },
      e => { if (live) setErr(e instanceof DashError ? e.code : "unknown"); });
    return () => { live = false; };
  }, []);
  const [archived, setArchived] = useState<ArchivedSession[]>([]);
  const [sure, setSure] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    api.archivedSessions().then(r => { if (live) setArchived(r); }, () => {});
    return () => { live = false; };
  }, []);
  const fail = (e: unknown) => setErr(e instanceof DashError ? e.code : "unknown");
  const drop = (id: string) => { setArchived(rs => rs.filter(r => r.session !== id)); setSure(null); };
  const restore = (id: string) => api.unarchiveSession(id).then(() => drop(id), fail);
  const remove = (id: string) => api.deleteSession(id).then(() => drop(id), fail);
  const show = (id: string) => api.session(id).then(setDetail, fail);
  const who = speakerChanges(detail?.turns ?? [], chars.byId);
  const now = Date.now() / 1000;
  return (
    <>
      {err && <p role="alert">{t(errorMessage(err))}</p>}
      {archived.length > 0 && !detail && (
        <section className="dash-set-archived" aria-label={t("set.archived")}>
          <h2 className="set-group-h">{t("set.archived")}<span className="dash-dm">{archived.length}</span></h2>
          <ul>
            {archived.map(s => (
              <li key={s.session}>
                {sure === s.session ? (
                  <p className="arch-sure" role="group" aria-label={t("session.delete")}>
                    <span>{t("session.deleteSure")}</span>
                    <button type="button" className="ib arch-kill" aria-label={t("session.delete")} title={t("session.delete")}
                      onClick={() => void remove(s.session)}><Icon name="trash" /></button>
                    <button type="button" className="ib" aria-label={t("memory.cancel")} title={t("memory.cancel")}
                      onClick={() => setSure(null)}><Icon name="close" /></button>
                  </p>
                ) : (
                  <>
                    <button type="button" className="arch-open" onClick={() => void show(s.session)}>
                      {s.title && <b>{s.title}</b>}<span>{plain(s.preview)}</span>
                      <time className="dash-dm">{whenLabel(s.archived_at, now, lang)}</time>
                    </button>
                    <button type="button" className="ib" aria-label={t("session.restore")} title={t("session.restore")}
                      onClick={() => void restore(s.session)}><Icon name="back" /></button>
                    <button type="button" className="ib" aria-label={t("session.delete")} title={t("session.delete")}
                      onClick={() => setSure(s.session)}><Icon name="trash" /></button>
                  </>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}
      {rows && !detail && (
        <div className="dash-set-archive">
          {archived.length > 0 && <h2 className="set-group-h">{t("set.legacyHead")}</h2>}
          <p className="dash-set-count">{t("set.legacy", { n: rows.length })}</p>
          {byWork(rows).map(g => (
            <section key={g.slug} aria-label={g.title}>
              <h2>{g.title}<span className="dash-dm">{g.rows.length}</span></h2>
              <ul>
                {g.rows.map(s => (
                  <li key={s.session}>
                    <button type="button" onClick={() => void show(s.session)}>
                      <span>{plain(s.preview)}</span><time className="dash-dm">{whenLabel(s.last_at, now, lang)}</time>
                    </button>
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>
      )}
      {detail && (
        <div className="dash-set-log">
          <button type="button" className="ib" aria-label={t("set.back")} title={t("set.back")} onClick={() => setDetail(null)}><Icon name="back" /></button>
          <h3>{detail.title}</h3>
          {detail.turns.map((turn, i) => {
            if (turn.role !== "assistant") return <div key={i} className="chat-me"><p>{turn.text}</p></div>;
            const c = chars.byId(turn.character);
            return (
              <div key={i} className="chat-turn">
                {who.has(i) && <p className="chat-who"><Figure character={c} size={22} /><b style={{ color: c.colors[mode].text }}>{localized(c.name, lang)}</b></p>}
                <p className="chat-text">{turn.text}</p>
              </div>
            );
          })}
        </div>
      )}
    </>
  );
}

export type SettingsSection = "look" | "companions" | "memory" | "archive";
const SECTIONS: { id: SettingsSection; key: MsgKey; icon: IconName }[] = [
  { id: "look", key: "set.look", icon: "look" }, { id: "companions", key: "set.companions", icon: "pal" },
  { id: "memory", key: "set.memory", icon: "memory" }, { id: "archive", key: "set.archive", icon: "talk" },
];
const NAV_GROUPS: { key: MsgKey; ids: SettingsSection[] }[] = [
  { key: "set.nav.pref", ids: ["look", "companions"] }, { key: "set.nav.data", ids: ["memory", "archive"] },
];

/** 設定分區:回去鍵 + 各分區。書架在設定頁時畫它;窄螢幕由 Settings 畫在內容上方(橫排)。 */
export function SettingsNav({ section, onPick, back }: {
  section: SettingsSection; onPick: (s: SettingsSection) => void; back: { label: string; to: string };
}) {
  const t = useT();
  const nav = useNavigate();
  return (
    <div className="set-nav" role="group" aria-label={t("set.sections")}>
      <button type="button" className="set-back" aria-label={back.label} title={back.label} onClick={() => nav(back.to)}>
        <Icon name="back" /><span>{back.label}</span>
      </button>
      {NAV_GROUPS.map(g => (
        <div key={g.key} className="set-nav-g">
          <p className="set-nav-h" aria-hidden="true">{t(g.key)}</p>
          {SECTIONS.filter(x => g.ids.includes(x.id)).map(x => (
            <button key={x.id} type="button" aria-label={t(x.key)} title={t(x.key)} aria-current={section === x.id ? "true" : undefined}
              onClick={() => onPick(x.id)}>
              <Icon name={x.icon} /><span>{t(x.key)}</span>
            </button>
          ))}
        </div>
      ))}
    </div>
  );
}

/** 一列:左標籤、右控制。 */
function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="set-row">
      <span className="set-lab">{label}</span>
      <div className="set-ctl">{children}</div>
    </div>
  );
}

const FLOWS = [
  { flow: "v", key: "flow.v", icon: "vert" },
  { flow: "h", key: "flow.h", icon: "hori" },
] as const;

function Look() {
  const t = useT();
  const lang = useLang();
  const { themes, theme, pref } = useThemeState();
  const [size, setSize] = useState<PaperSize>(loadPaperSize);
  const flow = usePaperFlow();
  const pickSize = (s: PaperSize) => {
    try { localStorage.setItem(PAPER_SIZE_KEY, s); } catch { /* 存不了就只這次有效 */ }
    setSize(s);
  };
  return (
    <div className="set-look">
      <section className="set-group" aria-label={t("set.group.ui")}>
        <h2 className="set-group-h">{t("set.group.ui")}</h2>
        <Row label={t("set.mode")}>
          <div className="set-seg" role="group" aria-label={t("set.mode")}>
            {MODES.map(m => (
              <button key={m.pref} type="button" aria-pressed={pref === m.pref} aria-label={t(m.key)} title={t(m.key)}
                onClick={() => setMode(m.pref)}><Icon name={m.icon} /></button>
            ))}
          </div>
        </Row>
        <Row label={t("set.palette")}>
          <div className="set-seg" role="group" aria-label={t("set.palette")}>
            {themes.map(th => (
              <button key={th.id} type="button" className="set-swatch" aria-pressed={theme?.id === th.id}
                aria-label={localized(th.name, lang)} title={localized(th.name, lang)} onClick={() => selectTheme(th.id)}>
                <span className="set-scene" aria-hidden="true">
                  {(["light", "dark"] as const).map(m => (
                    <span key={m} style={{ background: th[m].desk }}>
                      <i style={{ background: th[m].paper }}><b style={{ background: th[m].ink }} /><b style={{ background: th[m].accent }} /></i>
                    </span>
                  ))}
                </span>
              </button>
            ))}
          </div>
        </Row>
        <Row label={t("set.lang")}>
          <div className="set-seg" role="group" aria-label={t("set.lang")}>
            {LANGS.map(l => (
              <button key={l.lang} type="button" aria-pressed={lang === l.lang} onClick={() => setLang(l.lang)}>{l.label}</button>
            ))}
          </div>
        </Row>
      </section>
      <section className="set-group" aria-label={t("set.group.paper")}>
        <h2 className="set-group-h">{t("set.group.paper")}</h2>
        <Row label={t("set.flow")}>
          <div className="set-seg" role="group" aria-label={t("set.flow")}>
            {FLOWS.map(f => (
              <button key={f.flow} type="button" aria-pressed={flow === f.flow} aria-label={t(f.key)} title={t(f.key)}
                onClick={() => setPaperFlow(f.flow)}><Icon name={f.icon} /></button>
            ))}
          </div>
        </Row>
        <Row label={t("set.paper")}>
          <div className="set-seg" role="group" aria-label={t("set.paper")}>
            {SIZES.map(s => (
              <button key={s.size} type="button" aria-pressed={size === s.size} aria-label={t(s.key)} title={t(s.key)}
                onClick={() => pickSize(s.size)}><span className="set-glyph" data-size={s.size} aria-hidden="true">字</span></button>
            ))}
          </div>
        </Row>
      </section>
    </div>
  );
}

function Companions() {
  const t = useT();
  const chars = useCharacters();
  const [who, setWho] = useState(() => companionId(chars));
  const [err, setErr] = useState<string | null>(null);
  const [problems, setProblems] = useState<string[]>([]);
  const [held, setHeld] = useState<{ card: unknown; warnings: string[] } | null>(null);
  const [creating, setCreating] = useState(false);
  const [fresh, setFresh] = useState<string | null>(null);
  const [editing, setEditing] = useState<string | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  useEffect(() => setWho(companionId(chars)), [chars]);
  const code = (e: unknown) => (e instanceof DashError ? e.code : "unknown");
  const pick = (id: string) => {
    const before = who;
    setWho(id); setErr(null);
    setCompanion(id).catch(e => { setWho(before); setErr(code(e)); });
  };
  const send = async (card: unknown, confirm: boolean) => {
    setErr(null); setProblems([]);
    try {
      const r = await api.importCharacter(card, confirm);
      if (!r.imported) { setHeld({ card, warnings: r.warnings }); return; }
      setHeld(null);
      await chars.reload();
    } catch (e) {
      setHeld(null);
      if (e instanceof DashError && Array.isArray(e.params.errors)) setProblems(e.params.errors as string[]);
      else setErr(code(e));
    }
  };
  const fromFile = async (file: File) => {
    setErr(null); setHeld(null);
    let card: unknown;
    try { card = JSON.parse(await file.text()); } catch { setProblems(["not-json"]); return; }
    await send(card, false);
  };
  const archive = (id: string) => {
    setErr(null);
    api.archiveCharacter(id).then(() => chars.reload()).catch(e => setErr(code(e)));
  };
  const reloadSaved = () => chars.reload().catch(() => {});
  const copy = (id: string) => {
    setErr(null);
    api.copyCharacter(id).then(reloadSaved).catch(e => setErr(code(e)));
  };
  const saveEdit = async (c: Character, draft: CardDraft, confirm: boolean) => {
    const out = await api.editCharacter(c.id, draft, confirm);
    if (!out.edited) return out.warnings ?? [];
    await reloadSaved();
    setEditing(null);
    return [];
  };
  if (creating) {
    return <NewCharacter onClose={() => setCreating(false)} onSaved={async id => { await reloadSaved(); setFresh(id ?? null); setCreating(false); }} />;
  }
  const opened = open ? chars.active.find(c => c.id === open) ?? null : null;
  return (
    <div className="set-rows">
      {err && <p role="alert">{t(errorMessage(err))}</p>}
      <div className="char-cards char-lineup">
      {chars.active.map(c => {
        if (editing === c.id) {
          return <CardEditor key={c.id} draft={c} limits={SAVED_LIMITS}
            onSave={(draft, confirm) => saveEdit(c, draft, confirm)} onCancel={() => setEditing(null)} />;
        }
        return <PopCard key={c.id} character={c} on={who === c.id} fresh={fresh === c.id} onOpen={() => setOpen(c.id)} />;
      })}
      <div className="char-new">
        <NewSlot onOpen={() => setCreating(true)} />
        <button type="button" className="char-new-imp" aria-label={t("set.card.import")} title={t("set.card.import")} onClick={() => fileInput.current?.click()}><Icon name="up" /><span aria-hidden="true">{t("set.card.import")}</span></button>
        <input ref={fileInput} type="file" accept=".json,application/json" hidden aria-label={t("set.card.import")}
          onChange={e => { const f = e.target.files?.[0]; e.target.value = ""; if (f) void fromFile(f); }} />
      </div>
      </div>
      {opened && (
        <CharSheet character={opened} on={who === opened.id} onClose={() => setOpen(null)} onPick={() => pick(opened.id)}
          onEdit={() => { setOpen(null); setEditing(opened.id); }} onCopy={() => copy(opened.id)}
          onArchive={() => { setOpen(null); archive(opened.id); }} />
      )}
      {problems.length > 0 && (
        <ul role="alert">{problems.map(p => <li key={p}>{t(`card.err.${p}` as MsgKey)}</li>)}</ul>
      )}
      {held && (
        <div role="group" aria-label={t("set.card.import")}>
          <ul>{held.warnings.map(w => <li key={w}>{t(`card.warn.${w}` as MsgKey)}</li>)}</ul>
          <button type="button" onClick={() => void send(held.card, true)}>{t("set.card.confirm")}</button>
          <button type="button" onClick={() => setHeld(null)}>{t("set.card.cancel")}</button>
        </div>
      )}
    </div>
  );
}

/** 讀伴卡:立體書的紙卡,角色立在摺線上;整張可點,打開資訊面板。 */
function PopCard({ character: c, on, fresh, onOpen }: { character: Character; on: boolean; fresh: boolean; onOpen: () => void }) {
  const t = useT();
  const lang = useLang();
  const ref = useRef<HTMLButtonElement>(null);
  useEffect(() => { if (fresh) ref.current?.focus(); }, [fresh]);
  const name = localized(c.name, lang);
  const tilt = (e: PointerEvent<HTMLButtonElement>) => {
    if (e.pointerType !== "mouse") return;
    const r = e.currentTarget.getBoundingClientRect();
    e.currentTarget.style.setProperty("--rx", `${(0.5 - (e.clientY - r.top) / r.height) * 10}deg`);
    e.currentTarget.style.setProperty("--ry", `${((e.clientX - r.left) / r.width - 0.5) * 12}deg`);
  };
  const flat = (e: PointerEvent<HTMLButtonElement>) => {
    e.currentTarget.style.removeProperty("--rx");
    e.currentTarget.style.removeProperty("--ry");
  };
  return (
    <button type="button" ref={ref} className="char-pop" data-on={on} data-fresh={fresh || undefined} aria-haspopup="dialog" aria-label={t("set.card.open", { name })}
      onClick={onOpen} onPointerMove={tilt} onPointerLeave={flat}>
      <span className="char-stage" aria-hidden="true"><Figure character={c} size={96} /></span>
      <b className="char-name">{name}</b>
      <span className="char-line">{localized(c.line, lang)}</span>
      {on && <span className="char-tag">{t("set.default")}</span>}
    </button>
  );
}

/** 資訊面板:角色站起來、名字、讀法、來源;預設與卡片動作都在這裡。Esc 或點外面關。 */
function CharSheet({ character: c, on, onClose, onPick, onEdit, onCopy, onArchive }: {
  character: Character; on: boolean; onClose: () => void; onPick: () => void; onEdit: () => void; onCopy: () => void; onArchive: () => void;
}) {
  const t = useT();
  const lang = useLang();
  const name = localized(c.name, lang);
  const closeRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    const before = document.activeElement as HTMLElement | null;
    closeRef.current?.focus();
    return () => before?.focus?.();
  }, []);
  return (
    <div className="char-veil" onClick={onClose}>
      <div role="dialog" aria-modal="true" aria-label={name} className="char-sheet" onClick={e => e.stopPropagation()}
        onKeyDown={e => { if (e.key === "Escape") { e.stopPropagation(); onClose(); } }}>
        <button ref={closeRef} type="button" className="ib char-sheet-x" aria-label={t("set.card.close")} title={t("set.card.close")} onClick={onClose}><Icon name="close" /></button>
        <div className="char-sheet-stage" aria-hidden="true"><Figure character={c} size={168} /></div>
        <h2>{name}</h2>
        <p className="char-line">{localized(c.line, lang)}</p>
        <p className="char-meta">{t(`set.card.origin.${c.origin}` as MsgKey)}<span>{t("set.card.ver", { n: c.version })}</span></p>
        {c.reading && (
          <section className="char-reading" aria-label={t("card.reading")}>
            <h3>{t("card.reading")}</h3>
            <p>{c.reading}</p>
          </section>
        )}
        <div className="char-sheet-foot">
          <button type="button" className="dash-key" aria-pressed={on} disabled={on} onClick={onPick}>{t(on ? "set.default" : "set.makeDefault")}</button>
          <span className="char-acts">
            <a className="ib" href={api.characterCardUrl(c.id)} download={`${c.id}.json`}
              aria-label={t("set.card.export", { name })} title={t("set.card.export", { name })}><Icon name="down" /></a>
            <button type="button" className="ib" aria-label={t("set.card.copy", { name })} title={t("set.card.copy", { name })}
              onClick={onCopy}><Icon name="copy" /></button>
            {c.origin !== "builtin" && (
              <>
                <button type="button" className="ib" aria-label={t("set.card.edit", { name })} title={t("set.card.edit", { name })}
                  onClick={onEdit}><Icon name="edit" /></button>
                <button type="button" className="ib" aria-label={t("set.card.archive", { name })} title={t("set.card.archive", { name })}
                  onClick={onArchive}><Icon name="box" /></button>
              </>
            )}
          </span>
        </div>
      </div>
    </div>
  );
}

/** 設定內容:只畫目前分區。分區導覽在書架(窄螢幕時 nav 由外面給,畫在內容上方)。 */
export default function Settings({ section, nav }: { section: SettingsSection; nav: ReactNode | null }) {
  const t = useT();
  const title = t(SECTIONS.find(x => x.id === section)!.key);
  return (
    <section className="dash-settings" aria-label={t("rail.settings")} data-section={section}>
      {nav}
      <h1 className="dash-h">{title}</h1>
      {section === "look" && <Look />}
      {section === "companions" && <Companions />}
      {section === "memory" && <MemoryPage />}
      {section === "archive" && <Archive />}
    </section>
  );
}
