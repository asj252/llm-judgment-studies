"""Curate and normalize the 100 Experiment 2 Chinese clusters (closing all c Round 1 items).

Applies:
1. Drops the 20 flawed candidates from the 120-cluster pool (18 seed + 102 flash).
2. Fixes all specific clusters identified by c Round 1 (Blocker 2, 3, 4 & Suggestion 2, 3):
   - Motion to Goal (T_10, T_66, T_67, T_68, T_70, T_71): uses bounded path/climb objects
     and completion complement '完' so h_comp unambiguously encodes full traversal to the
     endpoint rather than surface entry ('上'), while preserving exact character-for-character
     minimal-pair insertion (h_comp minus '完' == h_bare).
   - Pure Unbounded Activity (A_pure_01..20): all 20 uniformly use satiation complements
     ('够' or '足'); fixes onset timing on A_pure_06, 08, 11, 13, 14, 15, 17, 18, 20.
   - Goal-Prone / Planned Activity (A_plan_01..20): all 20 uniformly use task-completion
     complement '完'; unifies verb/syntax on A_plan_02, 04, 05, 10, 12, 18, 21.
   - Fixes partial-onset and removes restart/resume wording on T_21, T_22, T_37, T_38, T_39,
     T_41, T_47, T_48, T_49, T_55, T_58, T_64, A_plan_15, A_plan_18, A_plan_22.
3. Appends explicit observation-window closure `，且直到{temporal_anchor}结束都没再继续。`
   to every `p_int` so interruption strictly excludes later completion within `temporal_anchor`.
4. Constructs `p_diag_pos` and `p_diag_neg` strictly within `temporal_anchor` directly from
   `p_no_int` and `h_comp`.
5. Extracts and binds `verb_root` and `comp_marker` on all 100 clusters and validates with
   `validate_materials.py`.
"""
import json
from pathlib import Path
from validate_materials import validate_clusters

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"

DROP_IDS = {
    "T_16", "T_19", "T_20", "T_26",
    "T_45", "T_51", "T_52", "T_54",
    "T_63", "T_65",
    "T_69", "T_72",
    "A_pure_09", "A_pure_10", "A_pure_21", "A_pure_22",
    "A_plan_11", "A_plan_13", "A_plan_16", "A_plan_24",
}

CLUSTER_OVERRIDES = {
    # Motion to Goal (6 clusters: unified to '完' on bounded path/climb NPs, interruption explicitly at start of that path)
    "T_10": {
        "vp_label": "爬登山石道",
        "p_no_int": "那天上午，登山客阿杰正在顺着山脊爬一段登山石道。",
        "p_int": "那天上午，登山客阿杰正在顺着山脊爬一段登山石道，刚爬了那段石道的开头一小截就突遇大雾封山只好原路下撤。",
        "h_comp": "那天上午，登山客阿杰爬完了那段登山石道。",
        "h_bare": "那天上午，登山客阿杰爬了那段登山石道。",
    },
    "T_66": {
        "vp_label": "登古塔石阶",
        "p_no_int": "那天下午，摄影师柯飞正在沿着塔内通道登一段古塔石阶。",
        "p_int": "那天下午，摄影师柯飞正在沿着塔内通道登一段古塔石阶，刚登了那段石阶的头几级就突发脚踝扭伤只好下塔休息。",
        "h_comp": "那天下午，摄影师柯飞登完了那段古塔石阶。",
        "h_bare": "那天下午，摄影师柯飞登了那段古塔石阶。",
    },
    "T_67": {
        "vp_label": "攀陡峭岩壁",
        "p_no_int": "那天上午，攀岩手董亮正在岩场里攀爬一面陡峭岩壁。",
        "p_int": "那天上午，攀岩手董亮正在岩场里攀爬一面陡峭岩壁，刚攀上那面岩壁底部两米高安全锁扣就发出异响只好绳降回地面。",
        "h_comp": "那天上午，攀岩手董亮攀完了那面陡峭岩壁。",
        "h_bare": "那天上午，攀岩手董亮攀了那面陡峭岩壁。",
    },
    "T_68": {
        "vp_label": "跑陡坡石道",
        "p_no_int": "那天清晨，田径队员魏征正在后山跑一段陡坡石道。",
        "p_int": "那天清晨，田径队员魏征正在后山跑一段陡坡石道，刚跑了那段石道的开头二十米就踩到湿青苔滑倒磕破膝盖只好折返。",
        "h_comp": "那天清晨，田径队员魏征跑完了那段陡坡石道。",
        "h_bare": "那天清晨，田径队员魏征跑了那段陡坡石道。",
    },
    "T_70": {
        "vp_label": "登烽火台石阶",
        "p_no_int": "那天下午，徒步者齐峰正在长城上登一段烽火台石阶。",
        "p_int": "那天下午，徒步者齐峰正在长城上登一段烽火台石阶，刚登了那段石阶的头几级管理人员就吹哨封道防雷雨只好退下。",
        "h_comp": "那天下午，徒步者齐峰登完了那段烽火台石阶。",
        "h_bare": "那天下午，徒步者齐峰登了那段烽火台石阶。",
    },
    "T_71": {
        "vp_label": "爬百级长石阶",
        "p_no_int": "那天清晨，晨练老人田大爷正在纪念公园里爬一段百级长石阶。",
        "p_int": "那天清晨，晨练老人田大爷正在纪念公园里爬一段百级长石阶，刚爬了那段长石阶的头十级就突然胸闷气短只好扶栏下撤。",
        "h_comp": "那天清晨，晨练老人田大爷爬完了那段百级长石阶。",
        "h_bare": "那天清晨，晨练老人田大爷爬了那段百级长石阶。",
    },
    # Telic onset / restart fixes
    "T_21": {
        "vp_label": "捏彩泥面人",
        "p_no_int": "那天下午，捏面师傅老鲁正在摊位前捏一个彩泥面人。",
        "p_int": "那天下午，捏面师傅老鲁正在摊位前捏一个彩泥面人，刚捏出半截身躯彩泥就被打翻的颜料盒泼脏只好收摊作罢。",
        "h_comp": "那天下午，捏面师傅老鲁捏好了那个彩泥面人。",
        "h_bare": "那天下午，捏面师傅老鲁捏了那个彩泥面人。",
    },
    "T_22": {
        "p_int": "那天上午，陶艺师傅陆明正在拉胚机前做一把陶瓷茶壶，壶身刚拉到一半陶泥就塌陷裂开只好停机作罢。",
    },
    "T_37": {
        "p_int": "那天下午，电工老徐正在工作台前修理一台老式收音机，刚焊好一处虚焊节点电烙铁就烧坏发热芯只好停手收工。",
    },
    "T_38": {
        "p_int": "那天上午，家政员徐姐正在客户厨房里清洗一台抽油烟机，刚刷洗掉外壳一角油污厨房就突然停水只好停手。",
    },
    "T_39": {
        "vp_label": "通卫生间下水道",
    },
    "T_41": {
        "p_int": "那天下午，修车匠老冯正在路边摊位前修补一条自行车内胎，刚贴上半片补胎胶片胶水就彻底干涸失效只好停手。",
    },
    "T_47": {
        "p_int": "那天上午，油漆工老陶正在走廊里粉刷一扇旧木门，刚刷了半幅门板白漆就彻底用光只好停工收起刷子。",
    },
    "T_48": {
        "p_int": "那天晚上，宿管阿姨吴妈正在值班室里缝补一条破洞牛仔裤，刚缝了两针就被叫去处理整晚的紧急查寝事务只好收起针线。",
    },
    "T_49": {
        "p_int": "那天下午，钳工老谢正在仓库门口剪一根生锈铁链，刚把链环剪开一道浅口液压剪刀刃就崩裂缺口只好作罢。",
    },
    "T_55": {
        "p_int": "那天下午，图书管理员柳芳正在修复室里贴补一本破损古籍，刚贴补好前两页破损书叶浆糊罐就被碰翻只好停手。",
    },
    "T_58": {
        "p_int": "那天下午，老茶客潘伯正在凉亭里喝一壶龙井茶，刚抿了一小口茶汤就有一只马蜂落入壶中只好倒掉茶水。",
    },
    "T_64": {
        "p_int": "那天中午，实习生高翔正在休息室里喝一杯冰镇西瓜汁，刚吸了两小口杯子就被手肘碰翻洒了一地只好作罢。",
    },
    # Atelic Pure (unified to '够'/'足' and clear ongoing duration before interruption)
    "A_pure_01": {
        "h_comp": "那天傍晚，沈括在湖边步道上散够了步。",
        "h_bare": "那天傍晚，沈括在湖边步道上散了步。",
    },
    "A_pure_06": {
        "p_int": "那天傍晚，中学女生陶桃正在楼顶天台上看天边的晚霞，刚静静看了两分钟天台门禁就鸣响清场铃只好下楼。",
    },
    "A_pure_08": {
        "p_int": "那天夜里，货车司机韩刚正在宿舍床前用木桶热水泡脚，刚泡了两分钟车队调度就来电通知紧急发车只好擦脚穿鞋。",
    },
    "A_pure_11": {
        "p_int": "那天午后，青年作家温言正在书房窗台前托腮发呆，刚托腮发呆了两分钟快递员就重重敲门派件只好起身。",
    },
    "A_pure_13": {
        "p_int": "那天夜里，白领何洁正在高层露台上看城市夜景，刚凭栏看了两分钟狂风就刮灭了露台灯光只好退回室内。",
    },
    "A_pure_14": {
        "p_int": "那天下午，老中医卢老正在庭院藤椅上闭目养神，刚闭目养神了两分钟邻家小孩就在院外放鞭炮轰鸣只好起身。",
    },
    "A_pure_15": {
        "p_int": "那天上午，游客薛涵正在公园水榭里看水中的锦鲤，刚低头看了两分钟游动的锦鲤遮阳帽就被大风刮走只好离开。",
    },
    "A_pure_17": {
        "p_int": "那天夜里，游客舒岚正在度假村露天汤池里泡温泉，刚在池中泡了两分钟就突降冰雹只好裹起浴袍跑回客房。",
    },
    "A_pure_18": {
        "vp_label": "浅滩玩溪水",
        "p_no_int": "那天下午，顽童皮皮正在小溪浅滩边玩溪水。",
        "p_int": "那天下午，顽童皮皮正在小溪浅滩边玩溪水，刚捧水玩了两分钟脚底就踩到碎瓦片大哭只好被大人抱离。",
        "h_comp": "那天下午，顽童皮皮在小溪浅滩边玩够了溪水。",
        "h_bare": "那天下午，顽童皮皮在小溪浅滩边玩了溪水。",
    },
    "A_pure_20": {
        "vp_label": "火塘烤火",
        "p_no_int": "那天夜里，守林老人骆老汉正在木屋火塘前烤火。",
        "p_int": "那天夜里，守林老人骆老汉正在木屋火塘前烤火，刚烤了两分钟火塘风道就倒灌浓烟只好灭掉火堆出屋。",
        "h_comp": "那天夜里，守林老人骆老汉在木屋火塘前烤够了火。",
        "h_bare": "那天夜里，守林老人骆老汉在木屋火塘前烤了火。",
    },
    # Atelic Planned (unified to '完' and natural training/task VP objects)
    "A_plan_02": {
        "vp_label": "马路推抛锚轿车",
        "agent": "车主老刘",
        "p_no_int": "那天上午，车主老刘正在马路上推那辆抛锚的轿车。",
        "p_int": "那天上午，车主老刘正在马路上推那辆抛锚的轿车，刚往前推了两米就腰部拉伤只好停手等拖车。",
        "h_comp": "那天上午，车主老刘在马路上推完了那辆抛锚的轿车。",
        "h_bare": "那天上午，车主老刘在马路上推了那辆抛锚的轿车。",
    },
    "A_plan_04": {
        "h_comp": "那天上午，韩雪在琴房里弹完了钢琴练习曲。",
        "h_bare": "那天上午，韩雪在琴房里弹了钢琴练习曲。",
    },
    "A_plan_05": {
        "vp_label": "绿道骑公路自行车",
        "p_no_int": "那天清晨，骑行客白宇正在环湖绿道上骑公路自行车。",
        "p_int": "那天清晨，骑行客白宇正在环湖绿道上骑公路自行车，刚骑出去一公里车胎就扎破漏气只好推车折返。",
        "h_comp": "那天清晨，骑行客白宇在环湖绿道上骑完了公路自行车。",
        "h_bare": "那天清晨，骑行客白宇在环湖绿道上骑了公路自行车。",
    },
    "A_plan_10": {
        "vp_label": "湖面划皮划艇",
        "p_no_int": "那天下午，划船游客傅强正在水上基地里划皮划艇。",
        "p_int": "那天下午，划船游客傅强正在水上基地里划皮划艇，刚划出去二十米桨叶就断裂只好被巡逻艇拖回码头。",
        "h_comp": "那天下午，划船游客傅强在水上基地里划完了皮划艇。",
        "h_bare": "那天下午，划船游客傅强在水上基地里划了皮划艇。",
    },
    "A_plan_12": {
        "vp_label": "健身房骑动感单车",
        "p_no_int": "那天晚上，健身青年陆毅正在健身房里骑动感单车。",
        "p_int": "那天晚上，健身青年陆毅正在健身房里骑动感单车，刚踩了两分钟单车传动皮带就脱落卡死只好下车。",
        "h_comp": "那天晚上，健身青年陆毅在健身房里骑完了动感单车。",
        "h_bare": "那天晚上，健身青年陆毅在健身房里骑了动感单车。",
    },
    "A_plan_15": {
        "p_int": "那天下午，篮球队员庞博正在操场篮球架下练习三步上篮，刚练了两个回合就踩到碎石扭伤膝盖只好扶墙停下。",
    },
    "A_plan_18": {
        "p_int": "那天傍晚，羽球学员岑菲正在羽毛球馆里练习发球，刚挥拍发了五个球球拍中杆就意外折断只好停下。",
    },
    "A_plan_21": {
        "vp_label": "擂台打悬挂沙袋",
        "p_no_int": "那天晚上，拳击手邹凯正在拳馆擂台边打悬挂沙袋。",
        "p_int": "那天晚上，拳击手邹凯正在拳馆擂台边打悬挂沙袋，刚连续击打了一分钟沙袋挂钩就断裂砸落只好作罢。",
        "h_comp": "那天晚上，拳击手邹凯在拳馆擂台边打完了悬挂沙袋。",
        "h_bare": "那天晚上，拳击手邹凯在拳馆擂台边打了悬挂沙袋。",
    },
    "A_plan_22": {
        "p_int": "那天下午，高中生蔚来正在操场单杠上做引体向上，刚拉起两个引体向上手掌就磨破老茧出血只好跳下单杠。",
    },
}


def extract_verb_and_comp(hc: str, hb: str) -> tuple[str, str]:
    """Extract verb_root and comp_marker from strict minimal pair (hc, hb)."""
    i = 0
    while i < min(len(hc), len(hb)) and hc[i] == hb[i]:
        i += 1
    j = 0
    while j < (min(len(hc), len(hb)) - i) and hc[len(hc) - 1 - j] == hb[len(hb) - 1 - j]:
        j += 1
    comp_marker = hc[i : len(hc) - j]
    assert hb[i : len(hb) - j] == "", f"Non-insertion diff between {hc} and {hb}"
    assert hc[len(hc) - j] == "了", f"Expected '了' immediately after comp_marker in {hc}"
    verb_root = hb[i - 1]
    return verb_root, comp_marker


def build_diagnostics(item: dict) -> tuple[str, str]:
    anchor = item["temporal_anchor"]
    agent = item["agent"]
    p0_stem = item["p_no_int"][:-1]
    hc_pred = item["h_comp"][len(anchor) + 1 + len(agent) :]  # ends with '。'
    v_root = item["verb_root"]
    c_mark = item["comp_marker"]
    # For negative diagnostic, replace '{v_root}{c_mark}了' with '{v_root}{c_mark}'
    hc_pred_neg = hc_pred.replace(f"{v_root}{c_mark}了", f"{v_root}{c_mark}", 1)
    p_diag_pos = f"{p0_stem}，并且在{anchor}结束前就{hc_pred}"
    p_diag_neg = f"{p0_stem}，但直到{anchor}结束都还没有{hc_pred_neg}"
    return p_diag_pos, p_diag_neg


def main() -> int:
    # Load original 18 seeds (strip any previous dynamic fields if re-running)
    seeds_raw = json.loads((DATA / "seed_clusters_18.json").read_text(encoding="utf-8"))
    flash_raw = json.loads((DATA / "candidates_flash_raw.json").read_text(encoding="utf-8"))
    pool = seeds_raw + flash_raw
    assert len(pool) == 120, f"Expected 120, got {len(pool)}"

    curated: list[dict] = []
    updated_seeds: list[dict] = []

    for orig in pool:
        cid = orig["cluster_id"]
        if cid in DROP_IDS:
            continue
        item = dict(orig)
        if cid in CLUSTER_OVERRIDES:
            item.update(CLUSTER_OVERRIDES[cid])

        anchor = item["temporal_anchor"]
        closure = f"，且直到{anchor}结束都没再继续。"
        if not item["p_int"].endswith(closure):
            item["p_int"] = item["p_int"][:-1] + closure

        v_root, c_mark = extract_verb_and_comp(item["h_comp"], item["h_bare"])
        item["verb_root"] = v_root
        item["comp_marker"] = c_mark
        item["p_diag_pos"], item["p_diag_neg"] = build_diagnostics(item)

        # Order keys canonically
        ordered = {
            "cluster_id": item["cluster_id"],
            "macro_class": item["macro_class"],
            "subclass": item["subclass"],
            "vp_label": item["vp_label"],
            "verb_root": item["verb_root"],
            "comp_marker": item["comp_marker"],
            "temporal_anchor": item["temporal_anchor"],
            "agent": item["agent"],
            "p_no_int": item["p_no_int"],
            "p_int": item["p_int"],
            "h_comp": item["h_comp"],
            "h_bare": item["h_bare"],
            "p_diag_pos": item["p_diag_pos"],
            "p_diag_neg": item["p_diag_neg"],
        }
        curated.append(ordered)
        if len(updated_seeds) < 18:
            updated_seeds.append(ordered)

    assert len(curated) == 100
    errs = validate_clusters(curated)
    if errs:
        for e in errs:
            print("ERROR:", e)
        return 1

    (DATA / "seed_clusters_18.json").write_bytes(
        (json.dumps(updated_seeds, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    )
    out_path = DATA / "clusters_100_curated.json"
    out_path.write_bytes((json.dumps(curated, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))

    lines = [
        "# 实验 2（中文版）精选 100 组事件簇完整一览表（v0.2）",
        "",
        "- 构成：**60 组终结类（`telic`）**（建造/创制 26、状态改变 18、消耗/阅读 10、趋向位移 6）+ **40 组非终结活动类（`atelic`）**（纯无界活动 `A_pure` 20、带主观计划活动 `A_plan` 20）。",
        "- 铁律：全部 100 组满足严格单成分插入最小对（`h_comp` 去掉 `comp_marker` 即逐字等于 `h_bare`），全部 `p_int` 显式封闭观察期（`且直到{temporal_anchor}结束都没再继续`），全部诊断语境严格落在同一观察期内。",
        "",
        "| 序号 | 簇 ID | 大类 / 子类 | 动词短语 (`verb_root`+`comp_marker`) | 无中断前提 (`p_no_int`) | 中断前提 (`p_int`) | 结果/完结补语假设 (`h_comp`) | 光杆 `V了` 假设 (`h_bare`) |",
        "| :---: | :--- | :--- | :--- | :--- | :--- | :--- | :--- |",
    ]
    for i, c in enumerate(curated, 1):
        lines.append(
            f"| {i} | `{c['cluster_id']}` | `{c['macro_class']}` / {c['subclass']} | "
            f"{c['vp_label']} (`{c['verb_root']}`+`{c['comp_marker']}`) | "
            f"{c['p_no_int']} | {c['p_int']} | {c['h_comp']} | {c['h_bare']} |"
        )
    md_path = HERE / "materials-100-preview.md"
    md_path.write_bytes(("\n".join(lines) + "\n").encode("utf-8"))
    print(f"OK: wrote {len(curated)} curated clusters to {out_path.name} and {md_path.name} (0 errors, pure LF).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
