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
# 1. 嚴格過濾規則設定（防誤抓、防靜態名冊）
# ==============================================================================
MUST_HAVE_ACTION = [
    "招募", "甄選", "甄試", "徵聘", "遴選", "誠徵", "徵才", "徵求", 
    "簡章", "申請辦法", "招募公告", "錄取名單", "初審名單", "複試名單"
]

PSY_KEYWORDS = [
    "諮商", "心輔", "心理", "駐地", "輔導", "臨床", "全職實習", "兼職實習", "實習"
]

GENERAL_EXCLUDE = [
    "護理", "藥劑", "藥學", "醫檢", "物理治療", "職能治療", "放射", 
    "營養", "資訊", "工讀生", "工讀", "資工", "社工實習", "社工師",
    "暑期企業實習", "海外實習", "幼兒園", "幼教", "保母", "兼任助理",
    "行政助理", "研究助理", "駕駛", "清潔", "工友"
]

STATIC_MEMBER_EXCLUDE = [
    "團隊介紹", "成員介紹", "中心成員", "師資介紹", "專業團隊", "現任", 
    "名冊", "人員職掌", "業務職掌", "心輔人員", "個別諮商預約", "諮商預約", 
    "預約服務", "服務收費", "收費標準", "實習心得", "成果展", "成果發表", 
    "實習點滴", "生活札記", "工作職掌", "歷屆", "組織架構"
]

ALL_EXCLUDE = GENERAL_EXCLUDE + STATIC_MEMBER_EXCLUDE

# ==============================================================================
# 2. 監聽的 Facebook 公開粉專（六都重點諮商所社群擴充）
# ==============================================================================
FB_TARGETS = [
    # 雙北
    {"area": "雙北", "name": "看見心理諮商所", "fb_id": "seemind.tw"},
    {"area": "雙北", "name": "點晴心理諮商所", "fb_id": "dianqingcounseling"},
    {"area": "雙北", "name": "暖心全人心理諮商所", "fb_id": "warmheartcounseling"},
    {"area": "雙北", "name": "旭立心理諮商中心", "fb_id": "shiuhlidental"},
    {"area": "雙北", "name": "啟宗心理諮商所", "fb_id": "openmindcounseling"},
    {"area": "雙北", "name": "愛心理諮商所", "fb_id": "iiispace"},
    {"area": "雙北", "name": "心曦心理諮商所", "fb_id": "SunshinePsychologyCenter"},
    {"area": "雙北", "name": "擁抱心理諮商所", "fb_id": "hugcounseling"},
    
    # 桃園
    {"area": "桃竹苗", "name": "日光心理諮商所(桃園)", "fb_id": "nikkocounseling"},
    {"area": "桃竹苗", "name": "晴朗心理諮商所(桃園)", "fb_id": "sunshinepsytaoyuan"},
    
    # 台中
    {"area": "中部", "name": "蛹之生心理諮商所", "fb_id": "morphocounseling"},
    {"area": "中部", "name": "若水心理諮商所", "fb_id": "waterspsy"},
    {"area": "中部", "name": "初色心理諮商所", "fb_id": "trueselfpsy"},
    {"area": "中部", "name": "展現心理諮商所", "fb_id": "unfoldpsy"},

    # 台南
    {"area": "南部", "name": "寬欣心理諮商所(台南)", "fb_id": "kuanhsinpsy"},
    {"area": "南部", "name": "禾心心理諮商所", "fb_id": "hexinpsy"},
    {"area": "南部", "name": "心物語心理諮商所", "fb_id": "heartstorypsy"},

    # 高雄
    {"area": "南部", "name": "大心心理諮商所(高雄)", "fb_id": "greatmindclinic"},
    {"area": "南部", "name": "芯耕圓心理諮商所(高雄)", "fb_id": "careu.counseling"},
    {"area": "南部", "name": "童伴心理諮商所(高雄)", "fb_id": "partnercounseling"},

    # 全台機構
    {"area": "全台", "name": "張老師基金會", "fb_id": "1980youth"}
]

# ==============================================================================
# 3. 目標官網機構名冊（大專心輔 + 醫療身心科 + 六都社區諮商所大擴充）
# ==============================================================================
TARGETS = [
    # ------------------ 雙北：大專院校 ------------------
    {"area": "雙北", "name": "臺灣大學 心理輔導中心", "url": "https://counseling.ntu.edu.tw/category/news/", "base_url": "https://counseling.ntu.edu.tw"},
    {"area": "雙北", "name": "臺灣師範大學 學生輔導中心", "url": "https://counseling.sa.ntnu.edu.tw/category/news/", "base_url": "https://counseling.sa.ntnu.edu.tw"},
    {"area": "雙北", "name": "政治大學 身心健康中心", "url": "https://osa.nccu.edu.tw/tw/physical-and-mental-health-center/news", "base_url": "https://osa.nccu.edu.tw"},
    {"area": "雙北", "name": "國立臺北教育大學 心理諮商中心", "url": "https://psyc.ntue.edu.tw/category/news/", "base_url": "https://psyc.ntue.edu.tw"},
    {"area": "雙北", "name": "臺北市立大學 學生輔導中心", "url": "https://studentcounsel.utaipei.edu.tw/p/412-1049-348.php", "base_url": "https://studentcounsel.utaipei.edu.tw"},
    {"area": "雙北", "name": "陽明交通大學 諮商中心(陽明校區)", "url": "https://counseling.nycu.edu.tw/", "base_url": "https://counseling.nycu.edu.tw"},
    {"area": "雙北", "name": "臺北科技大學 學生諮商中心", "url": "https://counseling.ntut.edu.tw/p/412-1041-370.php", "base_url": "https://counseling.ntut.edu.tw"},
    {"area": "雙北", "name": "臺灣科技大學 學生諮商中心", "url": "https://counseling.ntust.edu.tw/p/412-1051-229.php", "base_url": "https://counseling.ntust.edu.tw"},
    {"area": "雙北", "name": "東吳大學 生涯發展暨心理諮商中心", "url": "https://web-ch.scu.edu.tw/counsel/web_page/562", "base_url": "https://web-ch.scu.edu.tw"},
    {"area": "雙北", "name": "世新大學 諮商中心", "url": "https://counseling.shu.edu.tw/news", "base_url": "https://counseling.shu.edu.tw"},
    {"area": "雙北", "name": "輔仁大學 學生輔導中心", "url": "http://scc.fju.edu.tw/news", "base_url": "http://scc.fju.edu.tw"},
    {"area": "雙北", "name": "淡江大學 諮商職涯暨學習發展中心", "url": "https://fl.acad.tku.edu.tw/", "base_url": "https://fl.acad.tku.edu.tw"},
    {"area": "雙北", "name": "國立臺北大學 學生諮商中心", "url": "https://sea.ntpu.edu.tw/counseling/", "base_url": "https://sea.ntpu.edu.tw"},

    # ------------------ 雙北：醫療院所 ------------------
    {"area": "雙北", "name": "市立聯醫 松德院區", "url": "https://tpech.gov.taipei/mp109191/", "base_url": "https://tpech.gov.taipei"},
    {"area": "雙北", "name": "臺北榮民總醫院 精神醫學部", "url": "https://org.vghtpe.gov.tw/psy/", "base_url": "https://org.vghtpe.gov.tw"},
    {"area": "雙北", "name": "馬偕紀念醫院 精神醫學部", "url": "https://www.mmh.org.tw/division.php?depid=38", "base_url": "https://www.mmh.org.tw"},
    {"area": "雙北", "name": "亞東紀念醫院 精神醫學部", "url": "https://www.femh.org.tw/recruit/recruit_list", "base_url": "https://www.femh.org.tw"},

    # ------------------ 雙北：社福與社區諮商所（擴充） ------------------
    {"area": "雙北", "name": "懷仁全人發展中心", "url": "http://www.huaren.org.tw/news/", "base_url": "http://www.huaren.org.tw"},
    {"area": "雙北", "name": "張老師基金會(台北分事務所)", "url": "https://www.1980.org.tw/category/news/", "base_url": "https://www.1980.org.tw"},
    {"area": "雙北", "name": "看見心理諮商所", "url": "https://www.seemind.com.tw/news", "base_url": "https://www.seemind.com.tw"},
    {"area": "雙北", "name": "點晴心理諮商所", "url": "https://www.dianqing.com.tw/news", "base_url": "https://www.dianqing.com.tw"},
    {"area": "雙北", "name": "點亮心燈心理諮商所", "url": "https://www.lightup.org.tw/news", "base_url": "https://www.lightup.org.tw"},
    {"area": "雙北", "name": "旭立心理諮商中心", "url": "https://www.shiuhli.org.tw/", "base_url": "https://www.shiuhli.org.tw"},
    {"area": "雙北", "name": "吾心基金會", "url": "http://www.weprecat.org.tw/", "base_url": "http://www.weprecat.org.tw"},
    {"area": "雙北", "name": "格瑞思心理諮商所", "url": "https://www.grace.org.tw/", "base_url": "https://www.grace.org.tw"},
    {"area": "雙北", "name": "啟宗心理諮商所", "url": "https://open-mind.tw/", "base_url": "https://open-mind.tw"},
    {"area": "雙北", "name": "同心心理諮商所", "url": "https://www.tongxin.com.tw/", "base_url": "https://www.tongxin.com.tw"},
    {"area": "雙北", "name": "好時光心理諮商所", "url": "https://goodtimecounseling.com/", "base_url": "https://goodtimecounseling.com"},
    {"area": "雙北", "name": "心曦心理諮商所", "url": "https://sunshinepsychology.com/", "base_url": "https://sunshinepsychology.com"},
    {"area": "雙北", "name": "擁抱心理諮商所", "url": "https://www.hugcounseling.com/", "base_url": "https://www.hugcounseling.com"},
    {"area": "雙北", "name": "微煦心靈診所暨諮商所", "url": "https://www.warmclinic.com.tw/", "base_url": "https://www.warmclinic.com.tw"},
    {"area": "雙北", "name": "華人伴侶與家族治療基金會", "url": "http://www.c-cft.org/", "base_url": "http://www.c-cft.org"},
    {"area": "雙北", "name": "暖心全人心理諮商所", "url": "https://warmheartcounseling.com/", "base_url": "https://warmheartcounseling.com"},
    {"area": "雙北", "name": "愛心理心理諮商所", "url": "https://www.iiispace.com/", "base_url": "https://www.iiispace.com"},

    # ------------------ 桃竹苗：大專與醫療 ------------------
    {"area": "桃竹苗", "name": "國立中央大學 諮商輔導中心", "url": "https://counseling.ncu.edu.tw/announcement", "base_url": "https://counseling.ncu.edu.tw"},
    {"area": "桃竹苗", "name": "中原大學 諮商中心", "url": "https://counseling.cycu.edu.tw/announcement", "base_url": "https://counseling.cycu.edu.tw"},
    {"area": "桃竹苗", "name": "國立清華大學 諮商中心", "url": "https://counsel.site.nthu.edu.tw/p/412-1250-3255.php", "base_url": "https://counsel.site.nthu.edu.tw"},
    {"area": "桃竹苗", "name": "國立陽明交通大學 諮商中心(交大校區)", "url": "https://counseling-osa.nycu.edu.tw/", "base_url": "https://counseling-osa.nycu.edu.tw"},
    {"area": "桃竹苗", "name": "林口長庚紀念醫院 精神醫學部", "url": "https://www.cgmh.org.tw/branch/lnk/division/38000", "base_url": "https://www.cgmh.org.tw"},
    {"area": "桃竹苗", "name": "衛生福利部桃園療養院", "url": "https://www.typc.mohw.gov.tw/", "base_url": "https://www.typc.mohw.gov.tw"},

    # ------------------ 桃竹苗：社區諮商所（桃園大擴充） ------------------
    {"area": "桃竹苗", "name": "晴朗心理諮商所(桃園館)", "url": "https://sunshine-psy.com.tw/", "base_url": "https://sunshine-psy.com.tw"},
    {"area": "桃竹苗", "name": "日光心理諮商所", "url": "https://nikko-counseling.com/", "base_url": "https://nikko-counseling.com"},
    {"area": "桃竹苗", "name": "晴天心理諮商所(新竹)", "url": "https://sunny-psy.com.tw/", "base_url": "https://sunny-psy.com.tw"},
    {"area": "桃竹苗", "name": "心景心理諮商所", "url": "https://mindscape-counseling.tw/", "base_url": "https://mindscape-counseling.tw"},

    # ------------------ 中部：大專與醫療 ------------------
    {"area": "中部", "name": "國立中興大學 學生諮商中心", "url": "https://osa.nchu.edu.tw/counseling/news", "base_url": "https://osa.nchu.edu.tw"},
    {"area": "中部", "name": "國立臺中教育大學 諮商中心", "url": "https://counseling.ntcu.edu.tw/p/412-1033-1200.php", "base_url": "https://counseling.ntcu.edu.tw"},
    {"area": "中部", "name": "東海大學 學生諮商中心", "url": "https://counseling.thu.edu.tw/web/news/news.php", "base_url": "https://counseling.thu.edu.tw"},
    {"area": "中部", "name": "逢甲大學 諮商輔導中心", "url": "https://sa.fcu.edu.tw/counseling/announcement/", "base_url": "https://sa.fcu.edu.tw"},
    {"area": "中部", "name": "國立彰化師範大學 學生心理諮商中心", "url": "https://counseling.ncue.edu.tw/p/412-1023-1100.php", "base_url": "https://counseling.ncue.edu.tw"},
    {"area": "中部", "name": "臺中榮民總醫院 精神部", "url": "https://www.vghtc.gov.tw/UnitPage/UnitIndex?UnitId=38", "base_url": "https://www.vghtc.gov.tw"},
    {"area": "中部", "name": "中國醫藥大學附設醫院 精神醫學部", "url": "https://www.cmuh.cmu.edu.tw/Department/Detail?depid=38", "base_url": "https://www.cmuh.cmu.edu.tw"},

    # ------------------ 中部：社區諮商所（台中大擴充） ------------------
    {"area": "中部", "name": "蛹之生心理諮商所", "url": "https://www.morphocounseling.com/", "base_url": "https://www.morphocounseling.com"},
    {"area": "中部", "name": "若水心理諮商所", "url": "https://www.waterspsy.com/", "base_url": "https://www.waterspsy.com"},
    {"area": "中部", "name": "抱抱心身診所暨心理諮商所", "url": "https://www.hugsmental.com/", "base_url": "https://www.hugsmental.com"},
    {"area": "中部", "name": "日域心理諮商所", "url": "https://www.dailyzone.tw/", "base_url": "https://www.dailyzone.tw"},
    {"area": "中部", "name": "展現心理諮商所", "url": "https://www.unfoldpsy.com/", "base_url": "https://www.unfoldpsy.com"},
    {"area": "中部", "name": "初色心理諮商所", "url": "https://www.trueselfpsy.com/", "base_url": "https://www.trueselfpsy.com"},
    {"area": "中部", "name": "好晴天身心診所暨諮商所", "url": "https://sincereclinic.com/", "base_url": "https://sincereclinic.com"},
    {"area": "中部", "name": "綠野仙蹤心理諮商所(台中館)", "url": "https://dorothy-psychology.com/", "base_url": "https://dorothy-psychology.com"},

    # ------------------ 南部：大專與醫療 ------------------
    {"area": "南部", "name": "國立成功大學 心理健康與諮商輔導組", "url": "https://counseling.sa.ncku.edu.tw/", "base_url": "https://counseling.sa.ncku.edu.tw"},
    {"area": "南部", "name": "國立中山大學 諮商與職涯發展組", "url": "https://counsel.nsysu.edu.tw/", "base_url": "https://counsel.nsysu.edu.tw"},
    {"area": "南部", "name": "國立高雄師範大學 學生輔導中心", "url": "https://counseling.nknu.edu.tw/", "base_url": "https://counseling.nknu.edu.tw"},
    {"area": "南部", "name": "國立臺南大學 諮商輔導中心", "url": "https://counseling.nutn.edu.tw/", "base_url": "https://counseling.nutn.edu.tw"},
    {"area": "南部", "name": "成大醫院 精神部", "url": "https://www.hosp.ncku.edu.tw/", "base_url": "https://www.hosp.ncku.edu.tw"},
    {"area": "南部", "name": "高雄市立凱旋醫院", "url": "https://ksp.kcg.gov.tw/", "base_url": "https://ksp.kcg.gov.tw"},
    {"area": "南部", "name": "高雄長庚紀念醫院 精神部", "url": "https://www.cgmh.org.tw/branch/kh/", "base_url": "https://www.cgmh.org.tw"},
    {"area": "南部", "name": "高雄醫學大學附設醫院 精神醫學部", "url": "https://www.kmuh.org.tw/", "base_url": "https://www.kmuh.org.tw"},
    {"area": "南部", "name": "衛生福利部嘉南療養院", "url": "https://www.cnpc.mohw.gov.tw/", "base_url": "https://www.cnpc.mohw.gov.tw"},

    # ------------------ 南部：社區諮商所（台南、高雄大擴充） ------------------
    {"area": "南部", "name": "寬欣心理諮商所(台南)", "url": "https://www.kuan-hsin.tw/", "base_url": "https://www.kuan-hsin.tw"},
    {"area": "南部", "name": "心物語心理諮商所(台南)", "url": "https://www.heartstory.tw/", "base_url": "https://www.heartstory.tw"},
    {"area": "南部", "name": "大心心理諮商所(高雄)", "url": "https://www.greatmind.com.tw/", "base_url": "https://www.greatmind.com.tw"},
    {"area": "南部", "name": "芯耕圓心理諮商所(高雄)", "url": "https://www.care-u.com.tw/", "base_url": "https://www.care-u.com.tw"},
    {"area": "南部", "name": "童伴心理諮商所(高雄)", "url": "https://www.partner-counseling.com/", "base_url": "https://www.partner-counseling.com"},
    {"area": "南部", "name": "晴朗心理諮商所(高雄館)", "url": "https://sunshine-psy.com.tw/", "base_url": "https://sunshine-psy.com.tw"},
    {"area": "南部", "name": "力人心理諮商所(台南館)", "url": "https://www.powerperson.com.tw/", "base_url": "https://www.powerperson.com.tw"},
    {"area": "南部", "name": "好晴天身心診所暨諮商所(高雄館)", "url": "https://sincereclinic.com/", "base_url": "https://sincereclinic.com"},
    {"area": "南部", "name": "禾心心理諮商所", "url": "https://hexin-psy.com/", "base_url": "https://hexin-psy.com"},
    {"area": "南部", "name": "伴旅心理諮商所", "url": "https://journey-counseling.com/", "base_url": "https://journey-counseling.com"},

    # ------------------ 東部與離島 ------------------
    {"area": "東部", "name": "國立東華大學 諮商心理中心", "url": "https://counseling.ndhu.edu.tw/", "base_url": "https://counseling.ndhu.edu.tw"},
    {"area": "東部", "name": "花蓮慈濟醫院 精神醫學部", "url": "https://hlm.tzuchi.com.tw/psy/", "base_url": "https://hlm.tzuchi.com.tw"}
]

def is_valid_recruitment(title, site_name):
    if any(bad in title for bad in ALL_EXCLUDE):
        return False

    has_action = any(act in title for act in MUST_HAVE_ACTION)
    if not has_action:
        return False

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
                    elif "實習" in title:
                        role = "實習招募"
                    elif "心理師" in title:
                        role = "心理師招募"
                    else:
                        role = "招募公告"

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
    print("🚀 台灣諮商實習公告【六都名冊擴充＋社群粉專雙軌版】")
    print("⚡ 正在啟用 20 條平行通道高速掃描全台機構與粉專...")
    print("=" * 80)

    all_data = []

    # 1. 掃描官網
    with ThreadPoolExecutor(max_workers=20) as executor:
        web_results = executor.map(parse_target, TARGETS)
        for res in web_results:
            all_data.extend(res)

    # 2. 掃描 FB 粉專
    print("📱 正在同步檢查六都諮商所 FB 公開粉專貼文...")
    with ThreadPoolExecutor(max_workers=5) as executor:
        fb_results = executor.map(parse_fb, FB_TARGETS)
        for res in fb_results:
            all_data.extend(res)

    if not all_data:
        print("\n💡 目前各機構暫無新發布之實習招募公告。")
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
    print(f"🎉 六都諮商所掃描完成！共尋獲 {len(df)} 筆精準公告")
    print(f"📁 檔案已覆蓋至：【{filename}】與【data.js】")
    print("=" * 80)

if __name__ == "__main__":
    main()