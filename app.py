"""
構造材積算ツール - Streamlit Webアプリ
B: 土台・大引き集計
C: 床束・アンカーボルト集計
"""
import streamlit as st
import ezdxf
import warnings
import io
import os
import tempfile
from collections import defaultdict

warnings.filterwarnings("ignore")

# ============================================================
# 設定
# ============================================================
DODAI_W = 105; OHIKI_W = 60
DODAI_SECTION = (105, 105); OHIKI_SECTION = (90, 90)
MAT_LEN = 4000
X_NAMES = ['い','ろ','は','に','ほ','へ','と','ち','り','ぬ']
Y_NAMES = ['1','2','3','4','5','6','7','8','9','10','11','12']
SOLID_TOL = 50

# ============================================================
# DXF読み込み（JW_CAD CP932対応）
# ============================================================
def read_dxf(uploaded_file):
    """
    StreamlitのUploadedFileからezdxfのModelspaceを返す。
    ezdxf.read()(StringIO経由)はJW_CAD出力DXFで内部的に
    エンティティを取得できないケースがあるため、
    一時ファイルに書き出してezdxf.readfile()で読み込む
    （最も確実な方法）。
    """
    data = uploaded_file.read()
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".dxf", delete=False) as tmp:
            tmp.write(data)
            tmp_path = tmp.name
        doc = ezdxf.readfile(tmp_path)
        return doc.modelspace()
    except Exception as e:
        raise RuntimeError("DXFの読み込みに失敗しました: " + str(e))
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)

# ============================================================
# 共通関数
# ============================================================
def get_grid(msp):
    gh = set(); gv = set()
    for e in msp:
        if e.dxf.layer == "Grid" and e.dxftype() == "LINE":
            s = e.dxf.start; en = e.dxf.end
            if abs(s.y-en.y) < 1: gh.add(round(s.y))
            elif abs(s.x-en.x) < 1: gv.add(round(s.x))
    return sorted(gh), sorted(gv)

def build_ext(vals, names):
    base = list(zip(vals, names[:len(vals)]))
    ext = []
    for i,(g,n) in enumerate(base):
        ext.append((g,n))
        if i < len(base)-1:
            ext.append((round((base[i][0]+base[i+1][0])/2), n+"'"+base[i+1][1]))
    return ext

def snap(val, ext):
    return min(ext, key=lambda t: abs(t[0]-val))

def ffd(spans):
    pieces = []
    for s in spans:
        r = s
        while r > MAT_LEN: pieces.append(MAT_LEN); r -= MAT_LEN
        if r > 0: pieces.append(r)
    items = sorted(pieces, reverse=True); bins = []
    for item in items:
        placed = False
        for b in bins:
            if sum(b)+item <= MAT_LEN: b.append(item); placed=True; break
        if not placed: bins.append([item])
    return bins

# ============================================================
# B: 土台・大引き
# ============================================================
def get_members(msp):
    dodai=[]; ohiki=[]
    for e in msp:
        if e.dxf.layer=="Hari" and e.dxftype()=="POLYLINE":
            pts=[(v.dxf.location.x,v.dxf.location.y) for v in e.vertices]
            if len(pts)==4:
                xmin=min(p[0] for p in pts); xmax=max(p[0] for p in pts)
                ymin=min(p[1] for p in pts); ymax=max(p[1] for p in pts)
                w=xmax-xmin; h=ymax-ymin; width=round(min(w,h))
                if w>h: d="水平"; cx=(xmin+xmax)/2; cy=(ymin+ymax)/2
                else:   d="垂直"; cx=(xmin+xmax)/2; cy=(ymin+ymax)/2
                rec=(d,xmin,ymin,xmax,ymax,cx,cy)
                if width==DODAI_W: dodai.append(rec)
                elif width==OHIKI_W: ohiki.append(rec)
    return dodai, ohiki

def process_members(segs, gx_ext, gy_ext):
    results=[]
    horiz=[s for s in segs if s[0]=="水平"]
    vert=[s for s in segs if s[0]=="垂直"]
    hg=defaultdict(list)
    for s in horiz:
        _,xmin,ymin,xmax,ymax,cx,cy=s
        gv,_=snap(cy,gy_ext); hg[gv].append(s)
    for gv,grp in sorted(hg.items()):
        _,yn=snap(gv,gy_ext); grp_s=sorted(grp,key=lambda s:s[1]); sp=len(grp_s)>1
        for s in grp_s:
            _,xmin,ymin,xmax,ymax,cx,cy=s
            gx1,xn1=snap(xmin,gx_ext); gx2,xn2=snap(xmax,gx_ext)
            span=abs(gx2-gx1)
            if span==0: continue
            results.append((yn+"通り", xn1+"〜"+xn2, span, sp))
    vg=defaultdict(list)
    for s in vert:
        _,xmin,ymin,xmax,ymax,cx,cy=s
        gv,_=snap(cx,gx_ext); vg[gv].append(s)
    for gv,grp in sorted(vg.items()):
        _,xn=snap(gv,gx_ext); grp_s=sorted(grp,key=lambda s:s[3]); sp=len(grp_s)>1
        for s in grp_s:
            _,xmin,ymin,xmax,ymax,cx,cy=s
            gy1,yn1=snap(ymin,gy_ext); gy2,yn2=snap(ymax,gy_ext)
            span=abs(gy2-gy1)
            if span==0: continue
            results.append((xn+"通り", yn1+"〜"+yn2, span, sp))
    return results

def make_csv_B(dodai_r, ohiki_r):
    import math
    lines=[]
    def calc_kasadaka(results, sw, sh):
        bins=ffd([r[2] for r in results])
        n=len(bins)
        k=round((sw/1000)*(sh/1000)*4.0*n, 5)
        # 小数第三位切上・小数第二位表示
        k_ceil = math.ceil(k * 100) / 100
        return k_ceil

    kd = calc_kasadaka(dodai_r, *DODAI_SECTION)
    ko = calc_kasadaka(ohiki_r,  *OHIKI_SECTION)

    lines.append("#土台・大引き")
    lines.append("番号,明細1,明細2,数量,単位")
    lines.append("1,土台,4000×105×105 桧 KD,"+str(kd)+",m3")
    lines.append("2,大引き,4000×90×90 米松 KD,"+str(ko)+",m3")
    return "\n".join(lines)

# ============================================================
# C: 床束・アンカー
# ============================================================
def count_yukaduka(msp):
    solids=[]
    for e in msp:
        if e.dxf.layer=="Yukaduka" and e.dxftype()=="SOLID":
            pts=[e.dxf.vtx0,e.dxf.vtx1,e.dxf.vtx2,e.dxf.vtx3]
            xs=[p.x for p in pts]; ys=[p.y for p in pts]
            solids.append((round((max(xs)+min(xs))/2), round((max(ys)+min(ys))/2)))
    pg=defaultdict(list)
    for cx,cy in solids:
        key=(round(cx/SOLID_TOL)*SOLID_TOL, round(cy/SOLID_TOL)*SOLID_TOL)
        pg[key].append((cx,cy))
    locs=[]
    for key,pts in sorted(pg.items()):
        locs.append((round(sum(p[0] for p in pts)/len(pts)),
                     round(sum(p[1] for p in pts)/len(pts))))
    return locs

def count_m12(msp):
    anchors=[]
    for e in msp:
        if e.dxf.layer=="AnchorBolt_M12" and e.dxftype()=="CIRCLE":
            anchors.append((round(e.dxf.center.x), round(e.dxf.center.y)))
    return anchors

def count_m16(msp):
    """M16アンカーボルト: 三角形3本のLINEで1個を表す → LINE数÷3"""
    count=0
    for e in msp:
        if e.dxf.layer=="AnchorBolt_M16" and e.dxftype()=="LINE":
            count+=1
    return count // 3

def make_csv_C(yuka, m12, m16):
    lines=[]
    lines.append("#床束・アンカー")
    lines.append("番号,明細1,明細2,数量,単位")
    lines.append("1,床束,鋼製束,"+str(len(yuka))+",箇所")
    lines.append("2,M12アンカーボルト,M12×360ザボレス,"+str(len(m12))+",本")
    lines.append("3,M16アンカーボルト,M16×800,"+str(m16)+",本")
    return "\n".join(lines)

# ============================================================
# Streamlit UI
# ============================================================
st.set_page_config(page_title="構造材積算ツール", page_icon="🏠", layout="centered")
st.title("🏠 構造材積算ツール")
st.caption("工房信州の家 / フォレストコーポレーション")

tab_b, tab_c = st.tabs(["B：土台・大引き", "C：床束・M12アンカー"])

# ---- タブB ----
with tab_b:
    st.header("B：土台・大引きまとめ")
    st.info("1階床伏図のDXFファイルをアップロードしてください。")
    file_b = st.file_uploader("DXFファイルを選択", type=["dxf","DXF"], key="b")
    if file_b:
        with st.spinner("解析中..."):
            try:
                msp = read_dxf(file_b)
                gy_vals, gx_vals = get_grid(msp)
                gx_910 = gx_vals[1:8] if len(gx_vals)>=8 else gx_vals
                gy_910 = gy_vals[1:11] if len(gy_vals)>=11 else gy_vals
                gx_ext = build_ext(gx_910, X_NAMES)
                gy_ext = build_ext(gy_910, Y_NAMES)
                d_segs, o_segs = get_members(msp)
                dr = process_members(d_segs, gx_ext, gy_ext)
                or_ = process_members(o_segs, gx_ext, gy_ext)

                st.success("解析完了！")
                csv = make_csv_B(dr, or_)
                st.subheader("集計結果")
                st.code(csv, language="csv")
            except Exception as ex:
                st.error("エラーが発生しました: "+str(ex))

# ---- タブC ----
with tab_c:
    st.header("C：床束・アンカーボルト集計")
    st.info("基礎伏図のDXFファイルをアップロードしてください。")
    file_c = st.file_uploader("DXFファイルを選択", type=["dxf","DXF"], key="c")
    if file_c:
        with st.spinner("解析中..."):
            try:
                msp = read_dxf(file_c)
                yuka = count_yukaduka(msp)
                m12  = count_m12(msp)
                m16  = count_m16(msp)

                st.success("解析完了！")
                csv = make_csv_C(yuka, m12, m16)
                st.subheader("集計結果")
                st.code(csv, language="csv")
            except Exception as ex:
                st.error("エラーが発生しました: "+str(ex))

st.divider()
st.caption("© フォレストコーポレーション 積算ツール v1.0")
