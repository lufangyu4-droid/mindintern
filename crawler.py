import os
import re
import csv
import json
import urllib.parse
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
import requests
from bs4 import BeautifulSoup
import feedparser
import pandas as pd

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    )
}

# ==============================================================================
# 1. 精準過濾條件設定（徹底過濾現任團隊與非招募資訊）
# ==============================================================================

# 專業領域核心詞
PSY_KEYWORDS = [
    "諮商", "心輔", "心理", "駐地", "輔導", "臨床", "全職實習", "兼職實習"
]

# 招募行為動詞/關鍵字（必須有找人的意圖）
ACTION_RECRUIT_KEYWORDS = [
    "招募", "甄選", "甄試", "徵聘", "遴選", "誠徵", "徵才", "徵求", 
    "簡章", "申請辦法", "招募公告", "錄取名單", "初審名單", "複試名單"
]

# 排除黑名單 A：非相關專業與非正職實習
GENERAL_EXCLUDE = [
    "護理", "藥劑", "藥學", "醫檢", "物理治療", "職能治療", "放射", 
    "營養", "資訊", "工讀生", "工讀", "資工", "社工實習", "社工師",
    "暑期企業實習", "海外實習", "幼兒園", "幼教", "保母", "兼任助理",
    "行政助理", "研究助理", "駕駛", "清潔", "工友"
]

# 排除黑名單 B：已在實習的靜態成員介紹、心得、服務預約說明（核心優化）
STATIC_MEMBER_EXCLUDE = [
    "團隊介紹", "成員介紹", "中心成員", "師資介紹", "專業團隊", "現任", 
    "名冊", "人員職掌", "業務職掌", "心輔人員", "個別諮商預約", "諮商預約", 
    "預約服務", "服務收費", "收費標準", "實習心得", "成果展", "成果發表", 
    "實習點滴", "生活札記", "工作職掌", "歷屆", "組織架構"
]

# 合併所有排除詞
ALL_EXCLUDE = GENERAL_EXCLUDE + STATIC_MEMBER_EXCLUDE

# ==============================================================================
# 2. 監聽的 Facebook 公開粉專
# ==============================================================================
FB_TARGETS = [
    {"area": "雙北", "name": "看見心理諮商所", "fb_id": "seemind.tw"},
    {"area": "雙北", "name": "點晴心理諮商所", "fb_id": "dianqingcounseling"},
    {"area": "雙北", "name": "暖心全人心理諮商所", "fb_id": "warmheartcounseling"},
    {"area": "中部", "name": "蛹之生心理諮商所", "fb_id": "morphocounseling"},
    {"area": "全台", "name": "張老師基金會", "fb_id": "1980youth"}
]

# ==============================================================================
# 3. 目標官網機構名冊
# ==============================================================================
TARGETS = [
    # 雙北地區
    {"area": "雙北", "name": "臺灣大學 心理輔導中心", "url": "https://counseling.ntu.edu.tw/category/news/", "base_url": "https://counseling.ntu.edu.tw"},
    {"area": "雙北", "name": "臺灣師範大學 學生輔導中心", "url": "https://counseling.sa.ntnu.edu.tw/category/news/", "base_url": "https://counseling.sa.ntnu.edu.tw"},
    {"area": "雙北", "name": "政治大學 身心健康中心", "url": "https://osa.nccu.edu.tw/tw/physical-and-mental-health-center/news", "base_url": "https://osa.nccu.edu.tw"},
    {"area": "雙北", "name": "國立臺北教育大學 心理諮商中心", "url": "https://psyc.ntue.edu.tw/category/news/", "base_url": "https://psyc.ntue.edu.tw"},
    {"area": "雙北", "name": "臺北市立大學 學生輔導中心", "url": "https://studentcounsel.utaipei.edu.tw/p/412-1049-348.php", "base_url": "https://studentcounsel.utaipei.edu.tw"},
    {"area": "雙北", "name": "陽明交通大學 諮商中心(陽明校區)", "url": "https://counseling.nycu.edu.tw/", "base_url": "https://counseling.nycu.edu.tw"},
    {"area": "雙北", "name": "臺北科技大學 學生諮商中心", "url": "https://counseling.ntut.edu.tw/p/412-1041-370.php", "base_url": "https://counseling.ntut.edu.tw"},
    {"area": "雙北", "name": "臺灣科技大學 學生諮商中心", "url": "https://counseling.ntust.edu.tw/p/412-1051-229.php", "base_url": "https://counseling.ntust.edu.tw"},
    {"area": "雙北", "name": "東吳大學 生涯發展暨心理諮商中心", "url": "https://web-ch.scu.edu.tw/counsel/web_page/562", "base_url": "https://web-ch.scu.edu.tw"},
    {"area": "雙北", "name": "輔仁大學 學生輔導中心", "url": "http://scc.fju.edu.tw/news", "base_url": "http://scc.fju.edu.tw"},
    {"area": "雙北", "name": "淡江大學 諮商職涯暨學習發展中心", "url": "https://fl.acad.tku.edu.tw/", "base_url": "https://fl.acad.tku.edu.tw"},
    {"area": "雙北", "name": "市立聯醫 松德院區", "url": "https://tpech.gov.taipei/mp109191/", "base_url": "https://tpech.gov.taipei"},
    {"area": "雙北", "name": "臺北榮民總醫院 精神醫學部", "url": "https://org.vghtpe.gov.tw/psy/", "base_url": "https://org.vghtpe.gov.tw"},
    {"area": "雙北", "name": "懷仁全人發展中心", "url": "http://www.huaren.org.tw/news/", "base_url": "http://www.huaren.org.tw"},
    {"area": "雙北", "name": "看見心理諮商所", "url": "https://www.seemind.com.tw/news", "base_url": "https://www.seemind.com.tw"},
    {"area": "雙北", "name": "點晴心理諮商所", "url": "https://www.dianqing.com.tw/news", "base_url": "https://www.dianqing.com.tw"},
    {"area": "雙北", "name": "旭立心理諮商中心", "url": "https://www.shiuhli.org.tw/", "base_url": "https://www.shiuhli.org.tw"},
    {"area": "雙北", "name": "啟宗心理諮商所", "url": "https://open-mind.tw/", "base_url": "https://open-mind.tw"},
    {"area": "雙北", "name": "愛心理心理諮商所", "url": "https://www.iiispace.com/", "base_url": "https://www.iiispace.com"},

    # 桃竹苗地區
    {"area": "桃竹苗", "name": "國立中央大學 諮商輔導中心", "url": "https://counseling.ncu.edu.tw/announcement", "base_url": "https://counseling.ncu.edu.tw"},
    {"area": "桃竹苗", "name": "中原大學 諮商中心", "url": "https://counseling.cycu.edu.tw/announcement", "base_url": "https://counseling.cycu.edu.tw"},
    {"area": "桃竹苗", "name": "國立清華大學 諮商中心", "url": "https://counsel.site.nthu.edu.tw/p/412-1250-3255.php", "base_url": "https://counsel.site.nthu.edu.tw"},
    {"area": "桃竹苗", "name": "國立陽明交通大學 諮商中心(交大校區)", "url": "https://counseling-osa.nycu.edu.tw/", "base_url": "https://counseling-osa.nycu.edu.tw"},
    {"area": "桃竹苗", "name": "林口長庚紀念醫院 精神醫學部", "url": "https://www.cgmh.org.tw/branch/lnk/division/38000", "base_url": "https://www.cgmh.org.tw"},
    {"area": "桃竹苗", "name": "衛生福利部桃園療養院", "url": "https://www.typc.mohw.gov.tw/", "base_url": "https://www.typc.mohw.gov.tw"},

    # 中部地區
    {"area": "中部", "name": "國立中興大學 學生諮商中心", "url": "https://osa.nchu.edu.tw/counseling/news", "base_url": "https://osa.nchu.edu.tw"},
    {"area": "中部", "name": "國立臺中教育大學 諮商中心", "url": "https://counseling.ntcu.edu.tw/p/412-1033-1200.php", "base_url": "https://counseling.ntcu.edu.tw"},
    {"area": "中部", "name": "東海大學 學生諮商中心", "url": "https://counseling.thu.edu.tw/web/news/news.php", "base_url": "https://counseling.thu.edu.tw"},
    {"area": "中部", "name": "逢甲大學 諮商輔導中心", "url": "https://sa.fcu.edu.tw/counseling/announcement/", "base_url": "https://sa.fcu.edu.tw"},
    {"area": "中部", "name": "國立彰化師範大學 學生心理諮商中心", "url": "https://counseling.ncue.edu.tw/p/412-1023-1100.php", "base_url": "https://counseling.ncue.edu.tw"},
    {"area": "中部", "name": "臺中榮民總醫院 精神部", "url": "https://www.vghtc.gov.tw/UnitPage/UnitIndex?UnitId=38", "base_url": "https://www.vghtc.gov.tw"},
    {"area": "中部", "name": "蛹之生心理諮商所", "url": "https://www.morphocounseling.com/", "base_url": "https://www.morphocounseling.com"},

    # 南部地區
    {"area": "南部", "name": "國立成功大學 心理健康與諮商輔導組", "url": "https://counseling.sa.ncku.edu.tw/", "base_url": "https://counseling.sa.ncku.edu.tw"},
    {"area": "南部", "name": "國立中山大學 諮商與職涯發展組", "url": "https://counsel.nsysu.edu.tw/", "base_url": "https://counsel.nsysu.edu.tw"},
    {"area": "南部", "name": "國立高雄師範大學 學生輔導中心", "url": "https://counseling.nknu.edu.tw/", "base_url": "https://counseling.nknu.edu.tw"},
    {"area": "南部", "name": "高雄市立凱旋醫院", "url": "https://ksp.kcg.gov.tw/", "base_url": "https://ksp.kcg.gov.tw"},
    {"area": "南部", "name": "衛生福利部嘉南療養院", "url": "https://www.cnpc.mohw.gov.tw/", "base_url": "https://www.cnpc.mohw.gov.tw"},
    {"area": "南部", "name": "寬欣心理諮商所(台南)", "url": "https://www.kuan-hsin.tw/", "base_url": "https://www.kuan-hsin.tw"},

    # 東部地區
    {"area": "東部", "name": "國立東華大學 諮商心理中心", "url": "https://counseling.ndhu.edu.tw/", "base_url": "https://counseling.ndhu.edu.tw"},
    {"area": "東部", "name": "花蓮慈濟醫院 精神醫學部", "url": "https://hlm.tzuchi.com.tw/psy/", "base_url": "https://hlm.tzuchi.com.tw"}
]

def is_valid_recruitment(title, site_name):
    # 1. 命中黑名單（非相關科系 或 靜態名冊/心得）直接排除
    if any(bad in title for bad in ALL_EXCLUDE):
        return False

    # 2. 必須含有主動招募意圖（招募/甄選/簡章/徵求等）
    has_recruit_intent = any(act in title for act in ACTION_RECRUIT_KEYWORDS)
    if not has_recruit_intent:
        return False

    # 3. 領域確認：標題含有心理專業詞彙，或是該機構本身就是諮商/心輔單位
    has_psy_keyword = any(p in title for p in PSY_KEYWORDS)
    is_psy_unit = ("諮商" in site_name or "心輔" in site_name or "心理" in site_name)

    return has_psy_keyword or is_psy_unit

def parse_target(target):
    area = target["area"]
    site_name = target["name"]
    url = target["url"]
    base_url = target["base_url"]
    items = []

    try:
        resp = requests.get(url, headers=HEADERS, timeout=3.5)
        resp.encoding = resp.apparent_encoding or "utf-8"
        
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            for a in soup.find_all("a"):
                title = a.get_text(strip=True)
                raw_href = a.get("href", "")

                if len(title) < 5 or not raw_href or "javascript" in raw_href or raw_href.startswith("#"):
                    continue

                full_url = urllib.parse.urljoin(base_url, raw_href)

                if is_valid_recruitment(title, site_name):
                    if "全職" in title or "駐地" in title:
                        role = "全職實習"
                    elif "兼職" in title:
                        role = "兼職實習"
                    elif "心理師" in title:
                        role = "心理師甄選"
                    else:
                        role = "實習招募"

                    items.append({
                        "地區": area,
                        "來源機構": site_name,
                        "招募類別": role,
                        "公告標題": title,
                        "公告連結": full_url,
                        "抓取時間": datetime.now().strftime("%Y-%m-%d %H:%M")
                    })
    except Exception:
        pass
    return items

def parse_fb(target):
    area = target["area"]
    site_name = target["name"]
    fb_id = target["fb_id"]
    items = []
    
    rss_url = f"https://rsshub.app/facebook/page/{fb_id}"
    try:
        feed = feedparser.parse(rss_url)
        for entry in feed.entries:
            title = entry.get("title", "")
            description = entry.get("description", "")
            link = entry.get("link", "")
            clean_text = re.sub(r"<[^>]+>", "", description)
            full_text = f"{title} {clean_text}"

            if is_valid_recruitment(full_text, site_name):
                role = "FB全職實習" if ("全職" in full_text or "駐地" in full_text) else ("FB兼職實習" if "兼職" in full_text else "FB實習招募")
                summary = clean_text[:60] + "..." if len(clean_text) > 60 else (clean_text or title)

                items.append({
                    "地區": area,
                    "來源機構": f"[FB] {site_name}",
                    "招募類別": role,
                    "公告標題": summary.strip(),
                    "公告連結": link,
                    "抓取時間": datetime.now().strftime("%Y-%m-%d %H:%M")
                })
    except Exception:
        pass
    return items

def main():
    print("=" * 80)
    print("🚀 心實境 (MindIntern) 諮商實習公告【嚴格招募過濾版】")
    print("🛡️ 已啟用「現任成員介紹 / 預約選單 / 實習心得」全自動過濾機制")
    print("=" * 80)

    all_data = []

    with ThreadPoolExecutor(max_workers=20) as executor:
        web_results = executor.map(parse_target, TARGETS)
        for res in web_results:
            all_data.extend(res)

    print("📱 正在檢查諮商所 FB 公開粉專招募動態...")
    with ThreadPoolExecutor(max_workers=5) as executor:
        fb_results = executor.map(parse_fb, FB_TARGETS)
        for res in fb_results:
            all_data.extend(res)

    if not all_data:
        print("\n💡 目前各機構暫無新發布之實習招募簡章。")
        return

    df = pd.DataFrame(all_data)
    df.drop_duplicates(subset=["公告標題"], keep="first", inplace=True)

    sort_order = {"雙北": 1, "桃竹苗": 2, "中部": 3, "南部": 4, "東部": 5, "全台": 6}
    df["順序"] = df["地區"].map(sort_order).fillna(99)
    df.sort_values(by=["順序", "地區"], inplace=True)
    df.drop(columns=["順序"], inplace=True)

    # 輸出 CSV
    filename = "最新實習招募清單.csv"
    df.to_csv(filename, index=False, encoding="utf-8-sig")

    # 輸出 data.js
    json_data = df.to_json(orient="records", force_ascii=False)
    with open("data.js", "w", encoding="utf-8") as f:
        f.write(f"const internData = {json_data};")

    print("\n" + "=" * 80)
    print(f"🎉 篩選完成！共尋獲 {len(df)} 筆真正的【實習招募 / 甄選公告】")
    print(f"📁 檔案已更新至：【{filename}】與【data.js】")
    print("=" * 80)

if __name__ == "__main__":
    main()