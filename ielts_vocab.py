import json
import re
from pathlib import Path


IELTS_WORDS = [
    {
        "word": "alleviate",
        "phonetic": "/əˈliːvieɪt/",
        "meaning": "减轻，缓解",
        "phrases": ["alleviate poverty", "alleviate pressure", "alleviate traffic congestion"],
        "essay_use": "Governments should invest in public transport to alleviate traffic congestion in major cities.",
        "topic": "社会 / 城市",
    },
    {
        "word": "detrimental",
        "phonetic": "/ˌdetrɪˈmentl/",
        "meaning": "有害的，不利的",
        "phrases": ["detrimental effects", "be detrimental to health", "detrimental consequences"],
        "essay_use": "Excessive screen time can be detrimental to children's physical and mental health.",
        "topic": "健康 / 科技",
    },
    {
        "word": "sustainable",
        "phonetic": "/səˈsteɪnəbl/",
        "meaning": "可持续的",
        "phrases": ["sustainable development", "sustainable lifestyle", "sustainable energy"],
        "essay_use": "A sustainable lifestyle requires individuals to reduce waste and use resources responsibly.",
        "topic": "环境",
    },
    {
        "word": "profound",
        "phonetic": "/prəˈfaʊnd/",
        "meaning": "深远的，巨大的",
        "phrases": ["a profound impact", "profound changes", "profound influence"],
        "essay_use": "Technology has had a profound impact on the way people communicate and work.",
        "topic": "科技",
    },
    {
        "word": "inequality",
        "phonetic": "/ˌɪnɪˈkwɒləti/",
        "meaning": "不平等",
        "phrases": ["income inequality", "social inequality", "reduce inequality"],
        "essay_use": "Improving access to education is one of the most effective ways to reduce social inequality.",
        "topic": "社会 / 教育",
    },
    {
        "word": "innovation",
        "phonetic": "/ˌɪnəˈveɪʃn/",
        "meaning": "创新",
        "phrases": ["technological innovation", "encourage innovation", "drive innovation"],
        "essay_use": "Investment in research can drive innovation and strengthen a country's economy.",
        "topic": "科技 / 经济",
    },
    {
        "word": "compulsory",
        "phonetic": "/kəmˈpʌlsəri/",
        "meaning": "强制的，义务的",
        "phrases": ["compulsory education", "make it compulsory", "compulsory subjects"],
        "essay_use": "Some people believe that environmental education should be made compulsory in schools.",
        "topic": "教育",
    },
    {
        "word": "controversial",
        "phonetic": "/ˌkɒntrəˈvɜːʃl/",
        "meaning": "有争议的",
        "phrases": ["a controversial issue", "remain controversial", "controversial policy"],
        "essay_use": "Whether governments should fund the arts remains a controversial issue.",
        "topic": "政府 / 文化",
    },
    {
        "word": "urbanization",
        "phonetic": "/ˌɜːbənaɪˈzeɪʃn/",
        "meaning": "城市化",
        "phrases": ["rapid urbanization", "urbanization process", "problems caused by urbanization"],
        "essay_use": "Rapid urbanization has created pressure on housing, transport and public services.",
        "topic": "城市",
    },
    {
        "word": "prioritize",
        "phonetic": "/praɪˈɒrətaɪz/",
        "meaning": "优先考虑",
        "phrases": ["prioritize education", "prioritize public health", "prioritize long-term benefits"],
        "essay_use": "Policy makers should prioritize public health when allocating limited resources.",
        "topic": "政府 / 健康",
    },
    {
        "word": "adaptability",
        "phonetic": "/əˌdæptəˈbɪləti/",
        "meaning": "适应能力",
        "phrases": ["workplace adaptability", "develop adaptability", "adaptability skills"],
        "essay_use": "In a rapidly changing job market, adaptability is as important as technical knowledge.",
        "topic": "工作",
    },
    {
        "word": "mitigate",
        "phonetic": "/ˈmɪtɪɡeɪt/",
        "meaning": "缓和，减轻",
        "phrases": ["mitigate climate change", "mitigate risks", "mitigate negative effects"],
        "essay_use": "International cooperation is essential to mitigate the effects of climate change.",
        "topic": "环境",
    },
]

IELTS_WORDS.extend([
    {"word": "analysis", "phonetic": "/əˈnæləsɪs/", "meaning": "分析", "phrases": ["detailed analysis", "data analysis", "critical analysis"], "essay_use": "A detailed analysis of the data shows a clear shift in public attitudes.", "topic": "学术 / 写作"},
    {"word": "approach", "phonetic": "/əˈprəʊtʃ/", "meaning": "方法，途径", "phrases": ["a practical approach", "alternative approach", "approach a problem"], "essay_use": "A practical approach to education should combine theory with real-world experience.", "topic": "教育"},
    {"word": "benefit", "phonetic": "/ˈbenɪfɪt/", "meaning": "好处，使受益", "phrases": ["long-term benefits", "economic benefits", "benefit society"], "essay_use": "Public libraries bring long-term benefits to both students and local communities.", "topic": "社会 / 教育"},
    {"word": "consequence", "phonetic": "/ˈkɒnsɪkwəns/", "meaning": "后果，结果", "phrases": ["serious consequences", "unintended consequences", "environmental consequences"], "essay_use": "Ignoring climate change may lead to serious environmental consequences.", "topic": "环境"},
    {"word": "context", "phonetic": "/ˈkɒntekst/", "meaning": "背景，语境", "phrases": ["social context", "historical context", "in this context"], "essay_use": "In this context, online learning can be seen as a useful supplement to classroom teaching.", "topic": "教育 / 社会"},
    {"word": "criteria", "phonetic": "/kraɪˈtɪəriə/", "meaning": "标准，准则", "phrases": ["assessment criteria", "clear criteria", "meet the criteria"], "essay_use": "Schools should use clear criteria when assessing students' performance.", "topic": "教育"},
    {"word": "derive", "phonetic": "/dɪˈraɪv/", "meaning": "获得，源于", "phrases": ["derive benefits from", "derive from", "derive meaning"], "essay_use": "Young people can derive valuable skills from volunteer work.", "topic": "社会 / 工作"},
    {"word": "distribute", "phonetic": "/dɪˈstrɪbjuːt/", "meaning": "分配，分发", "phrases": ["distribute resources", "fairly distributed", "income distribution"], "essay_use": "Public resources should be distributed more fairly between urban and rural areas.", "topic": "政府 / 社会"},
    {"word": "economy", "phonetic": "/ɪˈkɒnəmi/", "meaning": "经济", "phrases": ["local economy", "global economy", "boost the economy"], "essay_use": "Tourism can boost the local economy, but it may also damage the environment.", "topic": "经济"},
    {"word": "environment", "phonetic": "/ɪnˈvaɪrənmənt/", "meaning": "环境", "phrases": ["protect the environment", "natural environment", "environmental damage"], "essay_use": "Protecting the environment requires action from both governments and individuals.", "topic": "环境"},
    {"word": "evidence", "phonetic": "/ˈevɪdəns/", "meaning": "证据", "phrases": ["strong evidence", "scientific evidence", "provide evidence"], "essay_use": "There is strong evidence that regular exercise improves mental health.", "topic": "健康"},
    {"word": "factor", "phonetic": "/ˈfæktə/", "meaning": "因素", "phrases": ["key factor", "major factor", "contributing factor"], "essay_use": "Family background is a key factor in children's educational development.", "topic": "教育 / 社会"},
    {"word": "function", "phonetic": "/ˈfʌŋkʃn/", "meaning": "功能，作用", "phrases": ["main function", "social function", "function effectively"], "essay_use": "The main function of public transport is to provide affordable mobility.", "topic": "城市"},
    {"word": "identify", "phonetic": "/aɪˈdentɪfaɪ/", "meaning": "识别，确认", "phrases": ["identify problems", "identify causes", "identify solutions"], "essay_use": "Governments must first identify the causes of unemployment before creating solutions.", "topic": "政府 / 工作"},
    {"word": "impact", "phonetic": "/ˈɪmpækt/", "meaning": "影响", "phrases": ["positive impact", "negative impact", "impact on society"], "essay_use": "Social media has had a significant impact on how people form opinions.", "topic": "科技 / 社会"},
    {"word": "income", "phonetic": "/ˈɪnkʌm/", "meaning": "收入", "phrases": ["household income", "income gap", "low-income families"], "essay_use": "Low-income families may struggle to access quality healthcare and education.", "topic": "社会 / 经济"},
    {"word": "indicate", "phonetic": "/ˈɪndɪkeɪt/", "meaning": "表明，显示", "phrases": ["statistics indicate", "results indicate", "indicate a trend"], "essay_use": "The figures indicate a steady increase in online shopping.", "topic": "小作文"},
    {"word": "individual", "phonetic": "/ˌɪndɪˈvɪdʒuəl/", "meaning": "个人", "phrases": ["individual responsibility", "individual choice", "individual freedom"], "essay_use": "Environmental protection depends not only on government policy but also on individual responsibility.", "topic": "社会"},
    {"word": "infrastructure", "phonetic": "/ˈɪnfrəstrʌktʃə/", "meaning": "基础设施", "phrases": ["transport infrastructure", "urban infrastructure", "invest in infrastructure"], "essay_use": "Investment in transport infrastructure can reduce congestion and improve productivity.", "topic": "城市 / 政府"},
    {"word": "interpret", "phonetic": "/ɪnˈtɜːprɪt/", "meaning": "解释，理解", "phrases": ["interpret data", "interpret information", "interpret results"], "essay_use": "Students need to learn how to interpret data rather than simply memorize facts.", "topic": "教育 / 小作文"},
    {"word": "investment", "phonetic": "/ɪnˈvestmənt/", "meaning": "投资", "phrases": ["public investment", "foreign investment", "investment in education"], "essay_use": "Investment in education is one of the most effective ways to promote social mobility.", "topic": "经济 / 教育"},
    {"word": "legislation", "phonetic": "/ˌledʒɪsˈleɪʃn/", "meaning": "法律，立法", "phrases": ["strict legislation", "environmental legislation", "introduce legislation"], "essay_use": "Strict legislation is needed to prevent companies from polluting rivers.", "topic": "政府 / 环境"},
    {"word": "maintain", "phonetic": "/meɪnˈteɪn/", "meaning": "维持，维护", "phrases": ["maintain standards", "maintain balance", "maintain public order"], "essay_use": "Schools should maintain high academic standards while supporting students' mental health.", "topic": "教育"},
    {"word": "method", "phonetic": "/ˈmeθəd/", "meaning": "方法", "phrases": ["teaching method", "research method", "effective method"], "essay_use": "Traditional teaching methods are still useful when combined with digital tools.", "topic": "教育"},
    {"word": "obtain", "phonetic": "/əbˈteɪn/", "meaning": "获得", "phrases": ["obtain information", "obtain a qualification", "obtain evidence"], "essay_use": "The internet allows students to obtain information quickly from different sources.", "topic": "科技 / 教育"},
    {"word": "participation", "phonetic": "/pɑːˌtɪsɪˈpeɪʃn/", "meaning": "参与", "phrases": ["public participation", "active participation", "participation in sports"], "essay_use": "Active participation in sports can improve children's confidence and teamwork skills.", "topic": "健康 / 教育"},
    {"word": "policy", "phonetic": "/ˈpɒləsi/", "meaning": "政策", "phrases": ["government policy", "public policy", "environmental policy"], "essay_use": "Government policy should encourage companies to reduce carbon emissions.", "topic": "政府"},
    {"word": "potential", "phonetic": "/pəˈtenʃl/", "meaning": "潜力，潜在的", "phrases": ["potential benefits", "potential risks", "reach one's potential"], "essay_use": "Online education has the potential to make learning more accessible.", "topic": "教育 / 科技"},
    {"word": "primary", "phonetic": "/ˈpraɪməri/", "meaning": "主要的，初级的", "phrases": ["primary reason", "primary education", "primary concern"], "essay_use": "The primary reason for urban migration is the search for better job opportunities.", "topic": "城市 / 工作"},
    {"word": "purchase", "phonetic": "/ˈpɜːtʃəs/", "meaning": "购买", "phrases": ["make a purchase", "purchase goods", "online purchases"], "essay_use": "Consumers are increasingly making online purchases because of convenience and lower prices.", "topic": "消费 / 科技"},
    {"word": "regulation", "phonetic": "/ˌreɡjuˈleɪʃn/", "meaning": "规定，监管", "phrases": ["strict regulation", "government regulation", "safety regulations"], "essay_use": "Stricter regulation of advertising may protect children from unhealthy food marketing.", "topic": "政府 / 健康"},
    {"word": "relevant", "phonetic": "/ˈreləvənt/", "meaning": "相关的", "phrases": ["relevant skills", "relevant information", "highly relevant"], "essay_use": "Schools should teach relevant skills that prepare students for the modern workplace.", "topic": "教育 / 工作"},
    {"word": "research", "phonetic": "/rɪˈsɜːtʃ/", "meaning": "研究", "phrases": ["scientific research", "conduct research", "research findings"], "essay_use": "Scientific research plays a vital role in solving public health problems.", "topic": "科技 / 健康"},
    {"word": "resource", "phonetic": "/rɪˈsɔːs/", "meaning": "资源", "phrases": ["natural resources", "educational resources", "limited resources"], "essay_use": "Developing countries often need better access to educational resources.", "topic": "教育 / 环境"},
    {"word": "restrict", "phonetic": "/rɪˈstrɪkt/", "meaning": "限制", "phrases": ["restrict access", "restrict advertising", "restrict freedom"], "essay_use": "Some people argue that governments should restrict junk food advertising aimed at children.", "topic": "政府 / 健康"},
    {"word": "sector", "phonetic": "/ˈsektə/", "meaning": "部门，行业", "phrases": ["public sector", "private sector", "technology sector"], "essay_use": "The private sector can create jobs, while the public sector provides essential services.", "topic": "经济 / 政府"},
    {"word": "significant", "phonetic": "/sɪɡˈnɪfɪkənt/", "meaning": "显著的，重要的", "phrases": ["significant increase", "significant role", "significant difference"], "essay_use": "There was a significant increase in the number of people using renewable energy.", "topic": "小作文 / 环境"},
    {"word": "source", "phonetic": "/sɔːs/", "meaning": "来源", "phrases": ["reliable source", "source of income", "energy source"], "essay_use": "Students should learn to distinguish reliable sources from misleading information.", "topic": "教育 / 科技"},
    {"word": "strategy", "phonetic": "/ˈstrætədʒi/", "meaning": "策略", "phrases": ["effective strategy", "long-term strategy", "learning strategy"], "essay_use": "A long-term strategy is required to address housing shortages in large cities.", "topic": "城市 / 政府"},
    {"word": "structure", "phonetic": "/ˈstrʌktʃə/", "meaning": "结构", "phrases": ["essay structure", "social structure", "clear structure"], "essay_use": "A clear essay structure helps readers follow the argument more easily.", "topic": "写作"},
    {"word": "technology", "phonetic": "/tekˈnɒlədʒi/", "meaning": "技术", "phrases": ["digital technology", "advanced technology", "technology use"], "essay_use": "Digital technology can improve access to education, especially in remote areas.", "topic": "科技 / 教育"},
    {"word": "trend", "phonetic": "/trend/", "meaning": "趋势", "phrases": ["upward trend", "recent trend", "global trend"], "essay_use": "The graph shows an upward trend in the use of public transport.", "topic": "小作文"},
    {"word": "welfare", "phonetic": "/ˈwelfeə/", "meaning": "福利，福祉", "phrases": ["public welfare", "animal welfare", "social welfare"], "essay_use": "Governments have a responsibility to protect public welfare through healthcare and education.", "topic": "政府 / 社会"},
])


TOPIC_KEYWORDS = {
    "教育": [
        "academic", "school", "student", "teacher", "education", "curriculum", "subject",
        "university", "college", "learn", "literacy", "classroom", "qualification",
        "教育", "学校", "学生", "老师", "学术", "课程", "大学", "学习",
    ],
    "科技": [
        "technology", "digital", "internet", "online", "computer", "software", "data",
        "innovation", "automation", "device", "media", "network",
        "科技", "技术", "数字", "网络", "电脑", "数据", "创新", "自动",
    ],
    "环境": [
        "environment", "climate", "pollution", "energy", "sustainable", "waste",
        "carbon", "ecological", "wildlife", "conservation", "resource",
        "环境", "气候", "污染", "能源", "可持续", "废物", "碳", "生态", "资源",
    ],
    "健康": [
        "health", "medical", "disease", "exercise", "diet", "mental", "stress",
        "hospital", "patient", "nutrition", "wellbeing",
        "健康", "医疗", "疾病", "运动", "饮食", "心理", "压力", "医院", "营养",
    ],
    "工作 / 经济": [
        "work", "job", "career", "income", "economy", "economic", "industry",
        "business", "employment", "salary", "market", "trade", "investment",
        "工作", "职业", "收入", "经济", "产业", "商业", "就业", "工资", "市场", "贸易", "投资",
    ],
    "城市 / 交通": [
        "urban", "city", "transport", "traffic", "housing", "vehicle", "road",
        "infrastructure", "commute", "public transport",
        "城市", "交通", "住房", "车辆", "道路", "基础设施", "通勤",
    ],
    "政府 / 社会": [
        "government", "policy", "law", "social", "public", "crime", "welfare",
        "poverty", "inequality", "community", "rights", "regulation",
        "政府", "政策", "法律", "社会", "公共", "犯罪", "福利", "贫困", "不平等", "社区", "权利", "监管",
    ],
    "文化 / 媒体": [
        "culture", "cultural", "media", "advertising", "art", "museum", "language",
        "tradition", "entertainment", "tourism",
        "文化", "媒体", "广告", "艺术", "博物馆", "语言", "传统", "娱乐", "旅游",
    ],
    "家庭 / 个人": [
        "family", "parent", "child", "children", "individual", "personal",
        "friend", "lifestyle", "habit",
        "家庭", "父母", "孩子", "儿童", "个人", "朋友", "生活方式", "习惯",
    ],
    "小作文": [
        "increase", "decrease", "trend", "proportion", "figure", "percentage",
        "graph", "chart", "table", "rate", "compare",
        "增加", "减少", "趋势", "比例", "图表", "表格", "比较",
    ],
    "写作": [
        "essay", "argument", "viewpoint", "evidence", "paragraph", "coherence",
        "grammar", "vocabulary", "structure",
        "作文", "论点", "观点", "证据", "段落", "语法", "词汇", "结构",
    ],
}


def _infer_topic(word, meaning="", phrases=None):
    text = " ".join([word or "", meaning or "", " ".join(phrases or [])]).lower()
    scores = {}
    for topic, keywords in TOPIC_KEYWORDS.items():
        score = 0
        for keyword in keywords:
            if re.search(rf"\b{re.escape(keyword)}\b", text):
                score += 2
            elif keyword in text:
                score += 1
        if score:
            scores[topic] = score
    if scores:
        return max(scores.items(), key=lambda item: item[1])[0]
    return "通用学术词"


def _load_extra_words():
    extra_path = Path(__file__).resolve().parent / "data" / "ielts_extra_vocab.json"
    if not extra_path.exists():
        return []
    try:
        data = json.loads(extra_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(data, list):
        return []
    existing = {item.get("word", "").lower() for item in IELTS_WORDS}
    cleaned = []
    for item in data:
        if not isinstance(item, dict):
            continue
        word = str(item.get("word", "")).strip()
        if not word or word.lower() in existing:
            continue
        phrases = item.get("phrases", []) if isinstance(item.get("phrases"), list) else []
        raw_topic = str(item.get("topic", "") or "").strip()
        generic_topics = {"", "雅思核心词", "雅思中文词表", "IELTS", "ielts"}
        topic = raw_topic if raw_topic not in generic_topics else _infer_topic(word, item.get("meaning", ""), phrases)
        if topic == "经济 / 工作":
            topic = "工作 / 经济"
        cleaned.append({
            "word": word,
            "phonetic": item.get("phonetic", ""),
            "meaning": item.get("meaning", ""),
            "phrases": phrases,
            "essay_use": item.get("essay_use", ""),
            "topic": topic,
        })
        existing.add(word.lower())
    return cleaned


IELTS_WORDS.extend(_load_extra_words())


def _apply_ai_overrides():
    override_path = Path(__file__).resolve().parent / "data" / "vocab_ai_overrides.json"
    if not override_path.exists():
        return
    try:
        data = json.loads(override_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    if not isinstance(data, dict):
        return
    by_word = {item.get("word", "").lower(): item for item in IELTS_WORDS}
    for word, override in data.items():
        if not isinstance(override, dict):
            continue
        item = by_word.get(str(word).lower())
        if not item:
            continue
        if override.get("meaning"):
            item["meaning"] = override["meaning"]
        if override.get("phonetic"):
            item["phonetic"] = override["phonetic"]
        if override.get("topic"):
            item["topic"] = override["topic"]
        if isinstance(override.get("phrases"), list) and override["phrases"]:
            item["phrases"] = override["phrases"]
        if override.get("essay_use"):
            item["essay_use"] = override["essay_use"]
        item["ai_enriched"] = True


_apply_ai_overrides()
