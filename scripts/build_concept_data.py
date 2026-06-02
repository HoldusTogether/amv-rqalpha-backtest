"""
Updated build_concept_data.py
- Uses expanded concept->ETF mapping (267 concepts, 46 ETFs)
- Generates concept flow data correlated with AMV market trends rather than pure random
"""
import csv
import os
import re
import random
from collections import defaultdict
from datetime import datetime

import pandas as pd

# Paths
TDX_HQ_CACHE = r"D:\new_tdx\T0002\hq_cache"
OUTPUT_DIR = r"D:\workSpace\amv-rqalpha-backtest\data"


def extract_concepts():
    """Extract concept names from infoharbor_block.dat."""
    path = os.path.join(TDX_HQ_CACHE, "infoharbor_block.dat")
    data = open(path, "rb").read()
    concepts = []
    lines = data.split(b'\n')
    for line in lines:
        if not line:
            continue
        text = line.decode('gbk', errors='replace').strip()
        if text.startswith('#GN_'):
            parts = text.split(',')
            if len(parts) >= 2:
                name = parts[0][4:]
                concepts.append(name)
    return concepts


def load_bundle_etfs():
    """Load all available ETFs from rqalpha bundle."""
    import pickle
    bundle_path = os.path.join(OUTPUT_DIR, '..', 'bundle', 'bundle', 'instruments.pk')
    with open(bundle_path, 'rb') as f:
        instruments = pickle.load(f)
    etfs = {}
    for inst in instruments:
        tp = inst.get('type', '')
        sym = inst.get('symbol', '')
        oid = inst.get('order_book_id', '')
        if tp != 'ETF':
            continue
        if any(kw in sym for kw in ['货币', '国债', '可转债', '公司债', '地方债',
                                      '城投债', '短融', '信用债', '利率债', '政金债']):
            continue
        etfs[oid] = sym
    return etfs


def build_concept_etf_map(concepts, all_etfs):
    """
    Build expanded concept->ETF mapping using hand-crafted base + keyword matching.
    """
    # Hand-crafted base mapping
    hand_map = {
        "通达信88": "510050.XSHG",
        "海峡西岸": "510050.XSHG",
        "海南自贸": "159790.XSHE",
        "一带一路": "516950.XSHG",
        "上海自贸": "510050.XSHG",
        "雄安新区": "516950.XSHG",
        "粤港澳": "159920.XSHE",
        "含H股": "510900.XSHG",
        "含B股": "510050.XSHG",
        "含GDR": "510050.XSHG",
        "国防军工": "512660.XSHG",
        "军民融合": "512660.XSHG",
        "大飞机": "512660.XSHG",
        "稀缺资源": "512400.XSHG",
        "5G概念": "515050.XSHG",
        "碳中和": "159790.XSHE",
        "黄金概念": "518880.XSHG",
        "物联网": "515050.XSHG",
        "创投概念": "510050.XSHG",
        "航运概念": "516530.XSHG",
        "高铁": "516950.XSHG",
        "高端装备": "516020.XSHG",
        "核电核能": "159611.XSHE",
        "光伏": "515790.XSHG",
        "风电": "516160.XSHG",
        "锂电池": "159840.XSHE",
        "燃料电池": "159840.XSHE",
        "HJT电池": "515790.XSHG",
        "固态电池": "516160.XSHG",
        "钠电池": "516160.XSHG",
        "钒电池": "516160.XSHG",
        "TOPCon": "515790.XSHG",
        "钙钛矿": "515790.XSHG",
        "BC电池": "515790.XSHG",
        "氢能源": "159785.XSHE",
        "稀土永磁": "516780.XSHG",
        "盐湖提锂": "159840.XSHE",
        "锂矿": "159840.XSHE",
        "水利建设": "516950.XSHG",
        "卫星导航": "512660.XSHG",
        "可燃冰": "516160.XSHG",
        "页岩气": "516160.XSHG",
        "生物疫苗": "512010.XSHG",
        "基因概念": "512010.XSHG",
        "仿制药": "512170.XSHG",
        "创新药": "159992.XSHE",
        "免疫治疗": "512010.XSHG",
        "CXO概念": "159992.XSHE",
        "节能环保": "159790.XSHE",
        "白酒概念": "512690.XSHG",
        "猪肉": "159825.XSHE",
        "鸡肉": "159825.XSHE",
        "水产品": "159825.XSHE",
        "碳纤维": "516020.XSHG",
        "石墨烯": "516020.XSHG",
        "3D打印": "562500.XSHG",
        "苹果概念": "515070.XSHG",
        "阿里概念": "517200.XSHG",
        "腾讯概念": "517200.XSHG",
        "小米概念": "515070.XSHG",
        "百度概念": "515070.XSHG",
        "华为鸿蒙": "562030.XSHG",
        "华为海思": "512480.XSHG",
        "华为汽车": "515700.XSHG",
        "华为算力": "516510.XSHG",
        "特斯拉": "515700.XSHG",
        "消费电子": "159781.XSHE",
        "汽车电子": "515700.XSHG",
        "生物质能": "159790.XSHE",
        "充电桩": "159755.XSHE",
        "新能源车": "515700.XSHG",
        "换电概念": "159755.XSHE",
        "高压快充": "159755.XSHE",
        "安防服务": "515880.XSHG",
        "垃圾分类": "159790.XSHE",
        "乡村振兴": "159825.XSHE",
        "体育概念": "159805.XSHE",
        "云计算": "516510.XSHG",
        "边缘计算": "516510.XSHG",
        "网络游戏": "159869.XSHE",
        "信息安全": "515400.XSHG",
        "国产软件": "562030.XSHG",
        "大数据": "515400.XSHG",
        "数据中心": "516510.XSHG",
        "芯片": "512480.XSHG",
        "MCU芯片": "512480.XSHG",
        "汽车芯片": "159995.XSHE",
        "存储芯片": "159995.XSHE",
        "互联金融": "512880.XSHG",
        "婴童概念": "159928.XSHE",
        "养老概念": "512010.XSHG",
        "网红经济": "159805.XSHE",
        "民营医院": "512170.XSHG",
        "特高压": "159755.XSHE",
        "智能电网": "159755.XSHE",
        "智能穿戴": "159781.XSHE",
        "智能交通": "516530.XSHG",
        "智能医疗": "512170.XSHG",
        "智慧城市": "516510.XSHG",
        "智慧政务": "562030.XSHG",
        "智能机器": "562500.XSHG",
        "机器视觉": "562500.XSHG",
        "超导概念": "516020.XSHG",
        "职业教育": "159805.XSHE",
        "物业管理": "512200.XSHG",
        "虚拟现实": "159781.XSHE",
        "数字孪生": "562030.XSHG",
        "钛金属": "512400.XSHG",
        "钴金属": "512400.XSHG",
        "镍金属": "512400.XSHG",
        "氟概念": "512400.XSHG",
        "磷概念": "512400.XSHG",
        "无人机": "512660.XSHG",
        "PPP概念": "516950.XSHG",
        "新零售": "159928.XSHE",
        "跨境电商": "516530.XSHG",
        "量子科技": "515880.XSHG",
        "无人驾驶": "562030.XSHG",
        "ETC概念": "515880.XSHG",
        "胎压监测": "515700.XSHG",
        "OLED概念": "159781.XSHE",
        "MiniLED": "159781.XSHE",
        "超清视频": "159805.XSHE",
        "区块链": "515400.XSHG",
        "数字货币": "562030.XSHG",
        "人工智能": "515070.XSHG",
        "租购同权": "512200.XSHG",
        "工业互联": "516510.XSHG",
        "知识产权": "562030.XSHG",
        "工业气体": "516020.XSHG",
        "预制菜": "159928.XSHE",
        "种业": "159825.XSHE",
        "操作系统": "562030.XSHG",
        "光刻机": "512480.XSHG",
        "三代半导": "512480.XSHG",
        "远程办公": "562030.XSHG",
        "口罩防护": "512170.XSHG",
        "虫害防治": "159825.XSHE",
        "超级电容": "516160.XSHG",
        "地摊经济": "159928.XSHE",
        "冷链物流": "516530.XSHG",
        "抖音概念": "159805.XSHE",
        "降解塑料": "159790.XSHE",
        "医美概念": "512170.XSHG",
        "人脑工程": "515070.XSHG",
        "有机硅": "516020.XSHG",
        "BIPV概念": "515790.XSHG",
        "地下管网": "516950.XSHG",
        "储能": "159755.XSHE",
        "新材料": "516020.XSHG",
        "工业母机": "159667.XSHE",
        "一体压铸": "515700.XSHG",
        "热管理": "516020.XSHG",
        "汽车拆解": "159825.XSHE",
        "国资云": "516510.XSHG",
        "元宇宙": "159781.XSHE",
        "云游戏": "159869.XSHE",
        "天然气": "515220.XSHG",
        "绿色电力": "159611.XSHE",
        "培育钻石": "512400.XSHG",
        "信创": "562030.XSHG",
        "电子纸": "159781.XSHE",
        "免税概念": "159928.XSHE",
        "装配建筑": "512200.XSHG",
        "绿色建筑": "512200.XSHG",
        "东数西算": "516510.XSHG",
        "跨境支付": "562030.XSHG",
        "中俄贸易": "516530.XSHG",
        "电子身份": "562030.XSHG",
        "家庭医生": "512170.XSHG",
        "辅助生殖": "512170.XSHG",
        "肝炎概念": "512010.XSHG",
        "新型城镇": "516950.XSHG",
        "粮食概念": "159825.XSHE",
        "临界发电": "159611.XSHE",
        "虚拟电厂": "159611.XSHE",
        "电池回收": "159840.XSHE",
        "PCB概念": "512480.XSHG",
        "先进封装": "159995.XSHE",
        "热泵概念": "515790.XSHG",
        "EDA概念": "562030.XSHG",
        "光热发电": "159611.XSHE",
        "供销社": "159825.XSHE",
        "DRG-DIP": "512170.XSHG",
        "AIGC概念": "515070.XSHG",
        "复合铜箔": "516020.XSHG",
        "数据确权": "515400.XSHG",
        "数据要素": "515400.XSHG",
        "POE胶膜": "515790.XSHG",
        "血氧仪": "512170.XSHG",
        "旅游概念": "159805.XSHE",
        "中特估": "512950.XSHG",
        "ChatGPT": "515070.XSHG",
        "CPO概念": "515880.XSHG",
        "数字水印": "562030.XSHG",
        "毫米雷达": "512660.XSHG",
        "工业软件": "562030.XSHG",
        "6G概念": "515880.XSHG",
        "时空数据": "515400.XSHG",
        "可控核变": "159611.XSHE",
        "知识付费": "159869.XSHE",
        "算力租赁": "516510.XSHG",
        "光通信": "515880.XSHG",
        "混合现实": "159781.XSHE",
        "英伟达": "515070.XSHG",
        "减速器": "562500.XSHG",
        "减肥药": "512170.XSHG",
        "合成生物": "512010.XSHG",
        "星闪概念": "515070.XSHG",
        "液冷服务": "516510.XSHG",
        "新型工业": "562500.XSHG",
        "短剧游戏": "159869.XSHE",
        "多模态AI": "515070.XSHG",
        "PEEK材料": "516020.XSHG",
        "小米汽车": "515700.XSHG",
        "飞行汽车": "159688.XSHE",
        "人形机器": "562500.XSHG",
        "AI手机PC": "515070.XSHG",
        "低空经济": "159688.XSHE",
        "铜缆连接": "515880.XSHG",
        "军工信息": "512660.XSHG",
        "玻璃基板": "159781.XSHE",
        "商业航天": "512660.XSHG",
        "车联网": "515700.XSHG",
        "财税数字": "562030.XSHG",
        "折叠屏": "159781.XSHE",
        "AI眼镜": "159781.XSHE",
        "智谱AI": "515070.XSHG",
        "IP经济": "159805.XSHE",
        "宠物经济": "159928.XSHE",
        "小红书": "159805.XSHE",
        "AI智能体": "515070.XSHG",
        "DeepSeek": "515070.XSHG",
        "AI医疗": "512170.XSHG",
        "海洋经济": "510050.XSHG",
        "外骨骼": "562500.XSHG",
        "军贸概念": "512660.XSHG",
        "雅江水电": "159611.XSHE",
        "AI营销": "515070.XSHG",
    }

    # Build ETF keyword index for auto-matching
    def clean_etf_name(name):
        name = name.replace('ETF', '').replace('中证', '').replace('全指', '')
        name = name.replace('国证', '').replace('上证', '').replace('深证', '')
        name = name.replace('产业', '').replace('主题', '').replace('指数', '')
        prefixes = ['华泰柏瑞', '华夏', '易方达', '南方', '广发', '富国', '嘉实', '博时',
                    '华安', '招商', '汇添富', '工银', '鹏华', '天弘', '景顺长城', '万家',
                    '国联', '华宝', '国泰', '大成', '银华', '建信', '中欧',
                    '平安', '海富通', '民生加银', '长城', '银河', '国投',
                    '新华', '泰康', '方正富邦', '前海开源', '摩根', '安信', '创金合信']
        for p in prefixes:
            name = name.replace(p, '')
        return name.strip()

    etf_keywords = defaultdict(list)
    for oid, sym in all_etfs.items():
        cleaned = clean_etf_name(sym)
        words = re.findall(r'[\u4e00-\u9fff]{2,}', cleaned)
        if cleaned:
            etf_keywords[cleaned].append(oid)
        for w in words:
            if w:
                etf_keywords[w].append(oid)

    # Build final mapping
    result = {}
    for concept in concepts:
        if concept in hand_map:
            result[concept] = hand_map[concept]
        elif concept in etf_keywords:
            candidates = etf_keywords[concept]
            result[concept] = candidates[0]
        else:
            # Last resort: broad market ETF
            result[concept] = "510050.XSHG"

    return result


def generate_concept_flow(concept_etf_map, all_etfs):
    """
    Generate concept capital flow data with AMV-correlated patterns.
    Uses AMV daily data to drive market-wide sentiment, then
    assigns concept flows with realistic sector rotation.
    """
    amv = pd.read_csv(os.path.join(OUTPUT_DIR, "amv_daily.csv"))
    amv['date'] = pd.to_datetime(amv['date'])
    amv = amv[amv['date'] >= '2020-01-01'].copy()
    amv.reset_index(drop=True, inplace=True)

    if amv.empty:
        print("No AMV data available after 2020-01-01")
        return []

    # Concept categories for sector rotation
    concept_list = sorted(concept_etf_map.keys())

    # Market regime definitions based on AMV
    # When AMV is in a bullish trend: growth/tech concepts lead
    # When AMV is bearish: defensive/value concepts lead
    growth_concepts = [c for c in concept_list if any(kw in c for kw in [
        '芯片', 'AI', '智能', '科技', '算力', '数据', '信创', '5G', '6G',
        '半导体', '软件', '机器', '数字', '元宇宙', '人工', '低空', '飞行',
        '机器人', '无人', '消费电子', '华为', '小米', '苹果', '特斯拉',
        '创新药', '新能源', '光伏', '储能', '氢能', '锂电', '充电桩',
        '东风', '卫星', '量子', '量子',
    ])]
    defensive_concepts = [c for c in concept_list if any(kw in c for kw in [
        '黄金', '银行', '保险', '红利', '公用', '电力', '煤炭', '有色',
        '军工', '国防', '医药', '医疗', '消费', '白酒', '食品', '农业',
        '红利', '央企', '国企', '基建',
    ])]

    rest_concepts = [c for c in concept_list if c not in growth_concepts and c not in defensive_concepts]

    random.seed(42)
    flow_rows = []

    for _, row in amv.iterrows():
        date = row['date']
        date_str = date.isoformat() if hasattr(date, 'isoformat') else str(date)[:10]
        pct = float(row.get('pct_change', 0))

        # AMV trend determines market regime (-1 to 1 scale)
        # Positive AMV change = bullish, negative = bearish
        market_trend = max(-1.0, min(1.0, pct * 10))  # scale pct_change to [-1, 1]

        # Generate flows for all concepts
        date_flows = []

        for c in concept_list:
            # Base flow magnitude depends on concept category
            if c in growth_concepts:
                # Growth concepts: flow up when market is bullish
                base = 5e8 * max(0, market_trend) + random.gauss(0, 2e8)
            elif c in defensive_concepts:
                # Defensive concepts: flow up when market is bearish (flight to safety)
                base = 5e8 * max(0, -market_trend) + random.gauss(0, 1.5e8)
            else:
                # Other concepts: modest correlation with market
                base = 3e8 * market_trend + random.gauss(0, 1.5e8)

            noise = random.gauss(0, 1e8)
            net_flow = base + noise
            date_flows.append((c, net_flow))

        # Sort by flow descending, keep top 20
        date_flows.sort(key=lambda x: -x[1])
        top_n = min(20, len(date_flows))
        for c, flow in date_flows[:top_n]:
            flow_rows.append([date_str, c, round(flow, 2)])

    return flow_rows


def main():
    print("=== Building concept data ===")

    # 1. Extract concepts from TDX
    concepts = extract_concepts()
    print(f"TDX concepts: {len(concepts)}")

    # 2. Load ETFs from bundle
    all_etfs = load_bundle_etfs()
    print(f"Bundle ETFs: {len(all_etfs)}")

    # 3. Build expanded concept->ETF mapping
    concept_map = build_concept_etf_map(concepts, all_etfs)
    unique_etfs = set(concept_map.values())
    print(f"Mapped concepts: {len(concept_map)}, unique ETFs: {len(unique_etfs)}")

    # 4. Save concept_etf_map.csv
    etf_name_map = {}
    for oid, sym in all_etfs.items():
        etf_name_map[oid] = sym

    etf_rows = []
    for concept in sorted(concept_map.keys()):
        oid = concept_map[concept]
        ename = etf_name_map.get(oid, '')
        etf_rows.append([concept, oid, ename, 1])

    out_path = os.path.join(OUTPUT_DIR, "concept_etf_map.csv")
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["concept", "order_book_id", "etf_name", "priority"])
        writer.writerows(etf_rows)
    print(f"Saved {len(etf_rows)} mappings")

    # 5. Generate concept flow data
    flow_rows = generate_concept_flow(concept_map, all_etfs)
    out_path = os.path.join(OUTPUT_DIR, "concept_flow.csv")
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["date", "concept", "net_inflow"])
        writer.writerows(flow_rows)
    print(f"Saved {len(flow_rows)} flow rows")

    print("Done!")


if __name__ == "__main__":
    main()
