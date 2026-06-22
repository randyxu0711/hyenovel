#!/usr/bin/env python3
"""hyenovel viz — 讀 stories/<slug>/analysis.json,出 viz.html。

職責:
  1. 逐字引用硬閘門:每個 evidence.quote 必須在 source.md 找得到,否則報錯。
  2. 算文本軸座標:命中位置 / 全文長度 → 0..1,給文本軸與點擊跳原文。
  3. 出自包含 viz.html:① 意圖鏈(cytoscape) ② 文本軸解剖(SVG)連動。

用法:
  python viz.py <slug>            # 驗證 + 出 viz.html
  python viz.py <slug> --check    # 只驗證引用,不出圖(給 critique 編排當閘門)
"""
import json
import re
import sys
import html
from pathlib import Path

ROOT = Path(__file__).resolve().parent
NODE_COLORS = {
    "theme": "#c0392b",      # 紅
    "motif": "#8e44ad",      # 紫
    "technique": "#2980b9",  # 藍
    "effect": "#e67e22",     # 橘
    "character": "#27ae60",  # 綠
    "beat": "#7f8c8d",       # 灰
}
NODE_CN = {"theme": "主題", "motif": "意象", "technique": "技法",
           "effect": "效果", "character": "角色", "beat": "節拍"}


def load(slug):
    base = ROOT / "stories" / slug
    aj = base / "analysis.json"
    src = base / "source.md"
    if not aj.exists():
        sys.exit(f"找不到 {aj}(先跑 /story-critique)")
    if not src.exists():
        sys.exit(f"找不到 {src}")
    analysis = json.loads(aj.read_text(encoding="utf-8"))
    source = src.read_text(encoding="utf-8")
    return base, analysis, source


def locate(quote, source):
    """回傳 (start, end) 或 None。先精確找,再容許空白差異。"""
    idx = source.find(quote)
    if idx != -1:
        return idx, idx + len(quote)
    # 容許換行/空白差異
    pat = re.compile(r"\s*".join(re.escape(ch) for ch in quote if not ch.isspace()))
    m = pat.search(source)
    if m:
        return m.start(), m.end()
    return None


def validate_and_locate(analysis, source):
    """就地把命中座標寫進 evidence(_start/_end/_pos),回傳錯誤清單。"""
    total = len(source) or 1
    errors = []
    for node in analysis.get("nodes", []):
        for ev in node.get("evidence", []) or []:
            q = ev.get("quote", "")
            span = locate(q, source) if q else None
            if span is None:
                errors.append((node.get("id", "?"), q))
                ev["_start"] = ev["_end"] = -1
                ev["_pos"] = None
            else:
                ev["_start"], ev["_end"] = span
                ev["_pos"] = span[0] / total
    return errors


def diagnostics(analysis):
    """意圖鏈診斷:孤兒技法 / 過載主題 / 空心主題。回傳 {node_id: set(classes)}。"""
    nodes = {n["id"]: n for n in analysis.get("nodes", [])}
    edges = analysis.get("edges", [])
    out_produces = {}   # technique -> [effect]
    serves_to = {}      # theme -> [effect] (incoming serves)
    for e in edges:
        if e["type"] == "produces":
            out_produces.setdefault(e["from"], []).append(e["to"])
        if e["type"] == "serves":
            serves_to.setdefault(e["to"], []).append(e["from"])
    # motif manifests theme 也算餵養主題
    manifests_to = {}
    for e in edges:
        if e["type"] == "manifests":
            manifests_to.setdefault(e["to"], []).append(e["from"])

    classes = {}
    for nid, n in nodes.items():
        t = n["type"]
        if t == "technique" and not out_produces.get(nid):
            classes.setdefault(nid, set()).add("orphan")        # 孤兒技法
        if t == "theme":
            feeders = len(serves_to.get(nid, [])) + len(manifests_to.get(nid, []))
            if feeders == 0:
                classes.setdefault(nid, set()).add("hollow")    # 空心主題
            elif feeders >= 4:
                classes.setdefault(nid, set()).add("overloaded")  # 過載主題
    return classes


def build_html(slug, analysis, source, diag):
    title = analysis.get("title") or slug
    nodes = analysis.get("nodes", [])
    edges = analysis.get("edges", [])

    # cytoscape elements
    cy_nodes = []
    for n in nodes:
        cls = sorted(diag.get(n["id"], set()))
        cy_nodes.append({"data": {
            "id": n["id"], "label": n.get("label", n["id"]),
            "ntype": n["type"], "note": n.get("note", ""),
        }, "classes": " ".join(cls)})
    cy_edges = []
    for i, e in enumerate(edges):
        cy_edges.append({"data": {
            "id": f"e{i}", "source": e["from"], "target": e["to"],
            "label": e["type"], "note": e.get("note", ""),
        }})

    # node 附帶 evidence(座標)給文本軸 + 點擊
    node_payload = []
    for n in nodes:
        evs = []
        for ev in n.get("evidence", []) or []:
            evs.append({"quote": ev.get("quote", ""), "start": ev.get("_start", -1),
                        "end": ev.get("_end", -1), "pos": ev.get("_pos")})
        node_payload.append({"id": n["id"], "type": n["type"],
                             "label": n.get("label", n["id"]),
                             "note": n.get("note", ""),
                             "intensity": n.get("intensity"),
                             "evidence": evs})

    data = {
        "slug": slug, "title": title,
        "cyElements": cy_nodes + cy_edges,
        "nodes": node_payload, "edges": edges,
        "colors": NODE_COLORS, "cn": NODE_CN,
        "diag": {k: sorted(v) for k, v in diag.items()},
    }
    data_json = json.dumps(data, ensure_ascii=False)
    source_json = json.dumps(source, ensure_ascii=False)

    return _TEMPLATE.replace("/*__DATA__*/", data_json).replace(
        "/*__SOURCE__*/", source_json).replace("__TITLE__", html.escape(title))


_TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-Hant"><head><meta charset="utf-8">
<title>hyenovel — __TITLE__</title>
<script src="https://unpkg.com/cytoscape@3.30.2/dist/cytoscape.min.js"
  integrity="sha384-IWROdLKRsN1UuJywMlWl7/blXQ8GEooN2n7dzTxfEPd7ybYIKCUJ2Ol/1Gpf3YV4"
  crossorigin="anonymous"></script>
<style>
 :root{ --bg:#1a1a1e; --panel:#24242b; --ink:#e8e6e0; --dim:#9a978f; --line:#3a3a44; }
 *{box-sizing:border-box} body{margin:0;font-family:-apple-system,"Noto Sans CJK TC","PingFang TC",sans-serif;
   background:var(--bg);color:var(--ink);}
 header{padding:14px 20px;border-bottom:1px solid var(--line);display:flex;gap:18px;align-items:baseline}
 header h1{font-size:17px;margin:0;font-weight:600} header .sub{color:var(--dim);font-size:13px}
 .tabs{display:flex;gap:6px;padding:10px 20px 0}
 .tab{padding:7px 14px;border:1px solid var(--line);border-bottom:none;border-radius:8px 8px 0 0;
   background:var(--panel);color:var(--dim);cursor:pointer;font-size:13px}
 .tab.active{color:var(--ink);background:#2e2e37}
 .view{display:none;padding:0 20px 20px} .view.active{display:block}
 .row{display:flex;gap:16px;height:calc(100vh - 150px)}
 #cy{flex:2;background:#202027;border:1px solid var(--line);border-radius:10px}
 .side{flex:1;min-width:280px;background:var(--panel);border:1px solid var(--line);border-radius:10px;
   padding:14px;overflow:auto}
 .side h3{margin:.2em 0 .5em;font-size:13px;color:var(--dim);text-transform:uppercase;letter-spacing:.05em}
 .legend span{display:inline-flex;align-items:center;gap:5px;margin:0 10px 6px 0;font-size:12px}
 .dot{width:11px;height:11px;border-radius:50%;display:inline-block}
 .diagbox{font-size:13px;line-height:1.7}
 .diag-tag{display:inline-block;padding:1px 7px;border-radius:4px;font-size:11px;margin-right:6px}
 .orphan{background:#5a3a1a;color:#ffce93} .overloaded{background:#5a1a1a;color:#ff9b9b}
 .hollow{background:#1a3a5a;color:#9bccff}
 #info{font-size:13px;line-height:1.7} #info .q{color:#ffd479;cursor:pointer;border-bottom:1px dashed #555}
 .axiswrap{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:10px}
 svg{display:block;width:100%}
 #src{margin-top:14px;background:var(--panel);border:1px solid var(--line);border-radius:10px;
   padding:18px;line-height:2;font-size:15px;max-height:42vh;overflow:auto;white-space:pre-wrap}
 #src mark{background:#ffd479;color:#1a1a1e;border-radius:3px;padding:0 2px}
 .hint{color:var(--dim);font-size:12px;margin:6px 0}
</style></head>
<body>
<header><h1>hyenovel</h1><span class="sub" id="ttl"></span></header>
<div class="tabs">
  <div class="tab active" data-v="chain">① 意圖鏈</div>
  <div class="tab" data-v="axis">② 文本軸解剖</div>
</div>

<div class="view active" id="v-chain"><div class="row">
  <div id="cy"></div>
  <div class="side">
    <h3>圖例</h3><div class="legend" id="legend"></div>
    <h3>診斷</h3><div class="diagbox" id="diag"></div>
    <h3>節點</h3><div id="info" class="hint">點任一節點看 note 與原文證據;點主題會在「文本軸」高亮餵養它的段落。</div>
  </div>
</div></div>

<div class="view" id="v-axis">
  <div class="axiswrap"><svg id="axis" height="320"></svg></div>
  <p class="hint">曲線=節拍張力(intensity)。下方圓點=意象、三角=技法、方塊=效果,位置=在全文的相對位置。點任一標記跳原文。</p>
  <div id="src"></div>
</div>

<script>
const D = /*__DATA__*/;
const SRC = /*__SOURCE__*/;
document.getElementById('ttl').textContent = D.title + ' · ' + D.slug;
const byId = {}; D.nodes.forEach(n=>byId[n.id]=n);

/* ---- tabs ---- */
document.querySelectorAll('.tab').forEach(t=>t.onclick=()=>{
  document.querySelectorAll('.tab').forEach(x=>x.classList.remove('active'));
  document.querySelectorAll('.view').forEach(x=>x.classList.remove('active'));
  t.classList.add('active');
  document.getElementById('v-'+t.dataset.v).classList.add('active');
  if(t.dataset.v==='axis') drawAxis();
  if(t.dataset.v==='chain') cy.resize();
});

/* ---- legend + diagnostics ---- */
const leg = document.getElementById('legend');
for(const [k,c] of Object.entries(D.colors)){
  const s=document.createElement('span');
  s.innerHTML=`<i class="dot" style="background:${c}"></i>${D.cn[k]}`; leg.appendChild(s);
}
const diagNames={orphan:['孤兒技法','不服務任何效果/主題=可能是裝飾'],
  overloaded:['過載主題','被太多東西餵=可能用力過猛'],
  hollow:['空心主題','沒有技法餵它=意圖可能落空']};
const diagEl=document.getElementById('diag'); let any=false;
for(const [nid,cls] of Object.entries(D.diag)){
  cls.forEach(c=>{any=true;
    const d=document.createElement('div');
    d.innerHTML=`<span class="diag-tag ${c}">${diagNames[c][0]}</span>`+
      `<b>${byId[nid]?byId[nid].label:nid}</b> — <span style="color:var(--dim)">${diagNames[c][1]}</span>`;
    diagEl.appendChild(d);});
}
if(!any) diagEl.innerHTML='<span style="color:var(--dim)">意圖鏈無明顯孤兒/過載/空心。</span>';

/* ---- cytoscape:意圖鏈 ---- */
const cy = cytoscape({
  container:document.getElementById('cy'),
  elements:D.cyElements,
  style:[
    {selector:'node',style:{'background-color':ele=>D.colors[ele.data('ntype')]||'#888',
      'label':'data(label)','color':'#e8e6e0','font-size':'11px','text-wrap':'wrap',
      'text-max-width':'90px','text-valign':'bottom','text-margin-y':4,'width':26,'height':26}},
    {selector:'node.orphan',style:{'border-width':3,'border-color':'#ffce93'}},
    {selector:'node.overloaded',style:{'border-width':3,'border-color':'#ff9b9b'}},
    {selector:'node.hollow',style:{'border-width':3,'border-color':'#9bccff','border-style':'dashed'}},
    {selector:'edge',style:{'width':1.4,'line-color':'#4a4a55','target-arrow-color':'#4a4a55',
      'target-arrow-shape':'triangle','curve-style':'bezier','label':'data(label)',
      'font-size':'9px','color':'#8a8a95','text-rotation':'autorotate'}},
    {selector:'edge[label="produces"]',style:{'line-color':'#2980b9','target-arrow-color':'#2980b9'}},
    {selector:'edge[label="serves"]',style:{'line-color':'#c0392b','target-arrow-color':'#c0392b'}},
    {selector:'.faded',style:{'opacity':0.2}},
  ],
  layout:{name:'breadthfirst',directed:true,spacingFactor:1.1,padding:20}
});
cy.on('tap','node',ev=>{
  const n=byId[ev.target.id()]; showInfo(n);
  cy.elements().removeClass('faded');
  if(n.type==='theme'){ // 連動:餵養此主題的上游 → 文本軸高亮
    const up=feeders(n.id); axisHi=new Set(); up.forEach(id=>axisHi.add(id));
    const keep=new Set([n.id,...up]);
    cy.nodes().forEach(x=>{if(!keep.has(x.id()))x.addClass('faded')});
  }else{ axisHi=new Set([n.id]); }
});
cy.on('tap',ev=>{if(ev.target===cy){cy.elements().removeClass('faded');}});

function feeders(themeId){ // effects serving theme + their producing techniques + motifs manifesting
  const res=new Set();
  D.edges.forEach(e=>{
    if((e.type==='serves'||e.type==='manifests')&&e.to===themeId){res.add(e.from);
      D.edges.forEach(e2=>{if(e2.type==='produces'&&e2.to===e.from)res.add(e2.from);});}
  });
  return [...res];
}
function showInfo(n){
  const el=document.getElementById('info'); el.classList.remove('hint');
  let h=`<b style="color:${D.colors[n.type]}">${D.cn[n.type]}</b> ${n.label}`;
  if(n.intensity!=null) h+=` <span style="color:var(--dim)">強度 ${n.intensity}</span>`;
  if(n.note) h+=`<p>${esc(n.note)}</p>`;
  if(n.evidence&&n.evidence.length){h+='<h3>原文證據</h3>';
    n.evidence.forEach(ev=>{h+=`<div>「<span class="q" data-s="${ev.start}" data-e="${ev.end}">${esc(ev.quote)}</span>」`+
      (ev.note?` <span style="color:var(--dim)">— ${esc(ev.note)}</span>`:'')+'</div>';});}
  el.innerHTML=h;
  el.querySelectorAll('.q').forEach(q=>q.onclick=()=>{
    document.querySelector('.tab[data-v=axis]').click();
    setTimeout(()=>highlightRange(+q.dataset.s,+q.dataset.e),60);});
}

/* ---- 文本軸 SVG ---- */
let axisHi=new Set();
function drawAxis(){
  const svg=document.getElementById('axis'); const W=svg.clientWidth||900,H=320;
  svg.setAttribute('viewBox',`0 0 ${W} ${H}`); svg.innerHTML='';
  const ml=40,mr=20,mt=20,mb=40, w=W-ml-mr;
  const NS='http://www.w3.org/2000/svg';
  const mk=(t,a)=>{const e=document.createElementNS(NS,t);for(const k in a)e.setAttribute(k,a[k]);return e;};
  const X=p=>ml+w*p;
  // 軸線
  const baseY=H-mb;
  svg.appendChild(mk('line',{x1:ml,y1:baseY,x2:W-mr,y2:baseY,stroke:'#4a4a55'}));
  ['開頭','中段','結尾'].forEach((t,i)=>{const tx=mk('text',{x:X(i/2),y:H-14,fill:'#9a978f','font-size':11,'text-anchor':'middle'});tx.textContent=t;svg.appendChild(tx);});
  // 張力曲線:beats by pos+intensity
  const beats=D.nodes.filter(n=>n.type==='beat'&&n.intensity!=null&&n.evidence.some(e=>e.pos!=null))
    .map(n=>({x:X(n.evidence.find(e=>e.pos!=null).pos),inten:n.intensity,n}))
    .sort((a,b)=>a.x-b.x);
  const topY=mt, curveH=baseY-topY-60;
  const Y=v=>baseY-60-curveH*v;
  if(beats.length){
    let d='M '+beats[0].x+' '+Y(beats[0].inten);
    beats.slice(1).forEach(b=>d+=' L '+b.x+' '+Y(b.inten));
    svg.appendChild(mk('path',{d:d,fill:'none',stroke:'#7f8c8d','stroke-width':2}));
    beats.forEach(b=>{const c=mk('circle',{cx:b.x,cy:Y(b.inten),r:4,fill:'#7f8c8d'});
      c.style.cursor='pointer';c.onclick=()=>jump(b.n);
      const tt=mk('title');tt.textContent=b.n.label+' ('+b.inten+')';c.appendChild(tt);svg.appendChild(c);});
  }
  const tlab=mk('text',{x:ml,y:topY+4,fill:'#9a978f','font-size':10});tlab.textContent='張力';svg.appendChild(tlab);
  // 三條 lane:意象(圓) 技法(三角) 效果(方)
  const lanes={motif:{y:baseY-40,sh:'circle'},technique:{y:baseY-22,sh:'tri'},effect:{y:baseY-6,sh:'rect'}};
  for(const [type,L] of Object.entries(lanes)){
    const lab=mk('text',{x:ml-6,y:L.y+3,fill:'#9a978f','font-size':10,'text-anchor':'end'});
    lab.textContent=D.cn[type];svg.appendChild(lab);
    D.nodes.filter(n=>n.type===type).forEach(n=>{
      n.evidence.filter(e=>e.pos!=null).forEach(e=>{
        const x=X(e.pos),col=D.colors[type];const hot=axisHi.has(n.id);
        let s; if(L.sh==='circle')s=mk('circle',{cx:x,cy:L.y,r:hot?6:4,fill:col});
        else if(L.sh==='tri')s=mk('polygon',{points:`${x},${L.y-5} ${x-4},${L.y+4} ${x+4},${L.y+4}`,fill:col});
        else s=mk('rect',{x:x-4,y:L.y-4,width:8,height:8,fill:col});
        if(hot)s.setAttribute('stroke','#fff'),s.setAttribute('stroke-width',1.5);
        s.style.cursor='pointer';s.onclick=()=>jump(n,e);
        const tt=mk('title');tt.textContent=n.label+'「'+e.quote+'」';s.appendChild(tt);svg.appendChild(s);});
    });
  }
}
function jump(n,e){ const ev=e||(n.evidence&&n.evidence.find(x=>x.start>=0));
  if(ev&&ev.start>=0) highlightRange(ev.start,ev.end); }

/* ---- 原文高亮 ---- */
function highlightRange(s,e){
  const box=document.getElementById('src');
  box.innerHTML = esc(SRC.slice(0,s))+'<mark>'+esc(SRC.slice(s,e))+'</mark>'+esc(SRC.slice(e));
  const m=box.querySelector('mark'); if(m)m.scrollIntoView({block:'center',behavior:'smooth'});
}
function esc(s){return (s||'').replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));}
document.getElementById('src').textContent = SRC;
</script>
</body></html>
"""


def main():
    args = [a for a in sys.argv[1:]]
    if not args:
        sys.exit("用法:python viz.py <slug> [--check]")
    check = "--check" in args
    raw = next((a for a in args if not a.startswith("--")), None)
    if not raw:
        sys.exit("缺 slug")
    # 容許傳 <slug>、stories/<slug> 或 stories/<slug>/source.md
    p = Path(raw.rstrip("/"))
    if p.name == "source.md":
        slug = p.parent.name
    elif "stories" in p.parts:
        slug = p.parts[p.parts.index("stories") + 1]
    else:
        slug = p.name

    base, analysis, source = load(slug)
    errors = validate_and_locate(analysis, source)

    if errors:
        print(f"⚠ 引用硬閘門:{len(errors)} 條 quote 在 source.md 找不到:")
        for nid, q in errors:
            print(f"  [{nid}] {q[:50]}")
    else:
        print(f"✓ 引用硬閘門通過:所有 quote 皆對得上原文。")

    if check:
        sys.exit(1 if errors else 0)

    diag = diagnostics(analysis)
    out = base / "viz.html"
    out.write_text(build_html(slug, analysis, source, diag), encoding="utf-8")
    n_nodes, n_edges = len(analysis.get("nodes", [])), len(analysis.get("edges", []))
    print(f"✓ 出圖:{out}  ({n_nodes} 節點 / {n_edges} 邊)")
    if diag:
        print(f"  診斷:{sum(len(v) for v in diag.values())} 項(孤兒/過載/空心)")


if __name__ == "__main__":
    main()
