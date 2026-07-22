"""Known real attraction names per city — ensures the activity agent never generates
placeholder names like "Shanghai Attraction 3" when scraping fails."""

_K = "type, name, ticket_price, rating, opening_hours".split(", ")
_c = "culture"; _n = "nature"; _e = "entertainment"; _s = "shopping"

# Each entry: [type, name, ticket_price, rating, opening_hours]
# fmt: off
_RAW = {
    "shanghai": [
        [_n, "The Bund (外滩)", 0, 4.7, "24h"],
        [_c, "Yu Garden (豫园)", 40, 4.5, "08:30-17:00"],
        [_c, "Shanghai Museum (上海博物馆)", 0, 4.6, "09:00-17:00"],
        [_e, "Oriental Pearl Tower (东方明珠)", 190, 4.4, "08:00-21:30"],
        [_s, "Nanjing Road (南京路步行街)", 0, 4.5, "10:00-22:00"],
        [_e, "Shanghai Disneyland (上海迪士尼)", 475, 4.6, "08:30-20:30"],
        [_s, "Tianzifang (田子坊)", 0, 4.3, "10:00-22:00"],
        [_c, "Jade Buddha Temple (玉佛寺)", 20, 4.4, "08:00-16:30"],
        [_n, "Shanghai Ocean Aquarium (上海海洋水族馆)", 160, 4.4, "09:00-18:00"],
        [_c, "Zhujiajiao Water Town (朱家角古镇)", 0, 4.4, "08:30-16:30"],
        [_e, "Shanghai World Financial Center (上海环球金融中心)", 180, 4.5, "08:00-23:00"],
        [_n, "French Concession (法租界)", 0, 4.6, "24h"],
        [_c, "Shanghai Natural History Museum", 30, 4.7, "09:00-17:15"],
    ],
    "beijing": [
        [_c, "Forbidden City (故宫)", 60, 4.8, "08:30-17:00"],
        [_n, "Great Wall at Mutianyu (慕田峪长城)", 45, 4.7, "07:30-17:30"],
        [_c, "Temple of Heaven (天坛)", 34, 4.6, "06:00-21:00"],
        [_n, "Summer Palace (颐和园)", 30, 4.7, "06:30-18:00"],
        [_c, "Tiananmen Square (天安门广场)", 0, 4.7, "05:00-22:00"],
        [_c, "798 Art District (798艺术区)", 0, 4.4, "10:00-18:00"],
        [_e, "Beijing National Stadium (鸟巢)", 50, 4.3, "09:00-19:00"],
        [_c, "Lama Temple (雍和宫)", 25, 4.5, "09:00-16:30"],
        [_n, "Beihai Park (北海公园)", 10, 4.5, "06:30-21:00"],
        [_s, "Nanluoguxiang (南锣鼓巷)", 0, 4.3, "24h"],
        [_c, "National Museum of China (国家博物馆)", 0, 4.7, "09:00-17:00"],
        [_n, "Jingshan Park (景山公园)", 2, 4.6, "06:30-21:00"],
        [_c, "Hutong Rickshaw Tour (胡同游)", 80, 4.3, "09:00-18:00"],
    ],
    "guangzhou": [
        [_e, "Canton Tower (广州塔)", 150, 4.5, "09:00-23:00"],
        [_c, "Chen Clan Ancestral Hall (陈家祠)", 10, 4.6, "08:30-17:30"],
        [_n, "Shamian Island (沙面)", 0, 4.5, "24h"],
        [_n, "Chimelong Safari Park (长隆野生动物世界)", 300, 4.7, "09:30-18:00"],
        [_c, "Sacred Heart Cathedral (石室圣心大教堂)", 0, 4.4, "08:00-17:30"],
        [_n, "Yuexiu Park (越秀公园)", 0, 4.4, "06:00-22:00"],
        [_n, "Baiyun Mountain (白云山)", 5, 4.5, "06:00-17:00"],
        [_c, "Guangdong Museum (广东省博物馆)", 0, 4.5, "09:00-17:00"],
        [_s, "Beijing Road (北京路步行街)", 0, 4.3, "10:00-22:00"],
        [_c, "Sun Yat-sen Memorial Hall (中山纪念堂)", 10, 4.4, "08:00-18:00"],
        [_e, "Pearl River Night Cruise (珠江夜游)", 55, 4.4, "18:00-22:00"],
        [_c, "Redtory Art District (红专厂)", 0, 4.2, "10:00-18:00"],
    ],
    "shenzhen": [
        [_e, "Window of the World (世界之窗)", 220, 4.3, "09:00-22:30"],
        [_c, "OCT-LOFT Creative Culture Park (华侨城创意园)", 0, 4.4, "10:00-22:00"],
        [_n, "Lianhuashan Park (莲花山公园)", 0, 4.5, "06:00-23:00"],
        [_n, "Shenzhen Bay Park (深圳湾公园)", 0, 4.6, "24h"],
        [_c, "Shenzhen Museum (深圳博物馆)", 0, 4.4, "10:00-18:00"],
        [_n, "Dameisha Beach (大梅沙)", 0, 4.2, "24h"],
        [_e, "Ping An Finance Center (平安金融中心)", 200, 4.4, "09:00-22:00"],
        [_c, "Dafen Oil Painting Village (大芬油画村)", 0, 4.2, "09:00-18:00"],
        [_n, "Wutong Mountain (梧桐山)", 0, 4.5, "24h"],
        [_n, "Xianhu Botanical Garden (仙湖植物园)", 15, 4.4, "06:00-19:00"],
        [_s, "Dongmen Pedestrian Street (东门步行街)", 0, 4.2, "10:00-22:00"],
        [_e, "Sea World (海上世界)", 0, 4.3, "10:00-22:00"],
    ],
    "hangzhou": [
        [_n, "West Lake (西湖)", 0, 4.8, "24h"],
        [_c, "Lingyin Temple (灵隐寺)", 75, 4.7, "07:00-18:00"],
        [_c, "Leifeng Pagoda (雷峰塔)", 40, 4.5, "08:00-20:30"],
        [_n, "Longjing Tea Plantation (龙井茶园)", 0, 4.5, "08:00-17:00"],
        [_c, "Wuzhen Water Town (乌镇)", 150, 4.6, "07:00-18:00"],
        [_n, "Xixi Wetland Park (西溪湿地)", 80, 4.4, "07:30-18:30"],
        [_c, "China National Silk Museum (中国丝绸博物馆)", 0, 4.5, "09:00-17:00"],
        [_s, "Qinghefang Ancient Street (清河坊街)", 0, 4.3, "10:00-22:00"],
        [_n, "Feilai Peak (飞来峰)", 45, 4.4, "07:00-18:00"],
        [_c, "Six Harmonies Pagoda (六和塔)", 20, 4.4, "06:30-18:30"],
        [_e, "Impression West Lake Show (印象西湖)", 260, 4.5, "19:30-20:30"],
    ],
    "chengdu": [
        [_n, "Giant Panda Base (大熊猫基地)", 55, 4.7, "07:30-18:00"],
        [_s, "Jinli Ancient Street (锦里)", 0, 4.4, "24h"],
        [_c, "Wuhou Shrine (武侯祠)", 50, 4.5, "08:00-18:00"],
        [_c, "Kuanzhai Alley (宽窄巷子)", 0, 4.4, "24h"],
        [_c, "Dujiangyan (都江堰)", 90, 4.6, "08:00-17:30"],
        [_n, "Mount Qingcheng (青城山)", 90, 4.5, "08:00-17:00"],
        [_n, "People's Park (人民公园)", 0, 4.4, "06:00-22:30"],
        [_e, "Sichuan Opera Face-Changing (变脸表演)", 80, 4.4, "19:00-21:00"],
        [_c, "Wenshu Monastery (文殊院)", 0, 4.5, "08:00-17:00"],
        [_c, "Jinsha Site Museum (金沙遗址博物馆)", 70, 4.5, "08:00-18:00"],
        [_s, "Taikoo Li (太古里)", 0, 4.3, "10:00-22:00"],
    ],
    "xian": [
        [_c, "Terracotta Warriors (兵马俑)", 120, 4.8, "08:30-18:00"],
        [_c, "City Wall (西安城墙)", 54, 4.7, "08:00-22:00"],
        [_s, "Muslim Quarter (回民街)", 0, 4.4, "24h"],
        [_c, "Big Wild Goose Pagoda (大雁塔)", 50, 4.5, "08:00-17:30"],
        [_c, "Shaanxi History Museum (陕西历史博物馆)", 0, 4.7, "08:30-18:00"],
        [_c, "Bell Tower & Drum Tower (钟鼓楼)", 50, 4.5, "08:30-21:30"],
        [_e, "Tang Paradise (大唐芙蓉园)", 120, 4.3, "09:00-22:00"],
        [_c, "Huaqing Hot Springs (华清池)", 120, 4.4, "07:00-19:00"],
        [_n, "Mount Hua (华山)", 180, 4.7, "07:00-19:00"],
        [_c, "Great Mosque (大清真寺)", 25, 4.4, "08:00-19:00"],
        [_e, "Wild Goose Pagoda Fountain Show", 0, 4.3, "12:00,20:30"],
    ],
    "nanjing": [
        [_c, "Sun Yat-sen Mausoleum (中山陵)", 0, 4.6, "06:30-18:00"],
        [_c, "Memorial Hall of Nanjing Massacre (南京大屠杀纪念馆)", 0, 4.7, "08:30-16:30"],
        [_c, "Confucius Temple (夫子庙)", 0, 4.4, "08:00-22:00"],
        [_c, "Ming Xiaoling Mausoleum (明孝陵)", 70, 4.5, "06:30-18:00"],
        [_n, "Xuanwu Lake (玄武湖)", 0, 4.5, "06:00-22:00"],
        [_c, "Nanjing City Wall (南京城墙)", 30, 4.4, "08:00-18:00"],
        [_c, "Presidential Palace (总统府)", 40, 4.5, "08:00-18:00"],
        [_e, "Qinhuai River Night Cruise (秦淮河夜游)", 80, 4.4, "18:00-22:00"],
        [_c, "Niushoushan (牛首山)", 98, 4.5, "08:30-17:00"],
        [_c, "Zhonghua Gate (中华门)", 50, 4.3, "08:00-17:30"],
    ],
    "wuhan": [
        [_c, "Yellow Crane Tower (黄鹤楼)", 70, 4.5, "08:00-18:00"],
        [_n, "East Lake (东湖)", 0, 4.6, "24h"],
        [_c, "Hubei Provincial Museum (湖北省博物馆)", 0, 4.6, "09:00-17:00"],
        [_c, "Guiyuan Temple (归元寺)", 20, 4.3, "08:00-17:00"],
        [_n, "Wuhan Yangtze River Bridge (武汉长江大桥)", 0, 4.4, "24h"],
        [_s, "Hubu Alley (户部巷)", 0, 4.2, "24h"],
        [_c, "Tan Hualin (昙华林)", 0, 4.3, "24h"],
        [_s, "Chu River Han Street (楚河汉街)", 0, 4.2, "10:00-22:00"],
        [_n, "Wuhan Polar Ocean Park (武汉极地海洋公园)", 210, 4.4, "09:00-17:00"],
        [_e, "Happy Valley Wuhan (武汉欢乐谷)", 200, 4.2, "09:30-18:00"],
    ],
    "xiamen": [
        [_n, "Gulangyu Island (鼓浪屿)", 50, 4.6, "24h"],
        [_c, "Nanputuo Temple (南普陀寺)", 0, 4.5, "04:00-18:30"],
        [_s, "Zengcuoan Village (曾厝垵)", 0, 4.3, "10:00-22:00"],
        [_n, "Xiamen University (厦门大学)", 0, 4.5, "12:00-14:00"],
        [_c, "Hulishan Fortress (胡里山炮台)", 25, 4.3, "07:30-18:00"],
        [_n, "Island Ring Road (环岛路)", 0, 4.5, "24h"],
        [_c, "Yongding Tulou (永定土楼)", 90, 4.5, "08:00-17:30"],
        [_n, "Shuzhuang Garden (菽庄花园)", 30, 4.4, "07:00-18:00"],
        [_n, "Xiamen Botanical Garden (厦门植物园)", 40, 4.4, "06:30-18:00"],
        [_s, "Zhongshan Road (中山路步行街)", 0, 4.2, "10:00-22:00"],
    ],
    "kunming": [
        [_n, "Stone Forest (石林)", 175, 4.5, "08:00-18:00"],
        [_n, "Dian Lake (滇池)", 0, 4.4, "24h"],
        [_n, "Green Lake Park (翠湖公园)", 0, 4.5, "06:00-22:00"],
        [_n, "Western Hills (西山)", 40, 4.4, "08:00-18:00"],
        [_c, "Yunnan Nationalities Village (云南民族村)", 90, 4.3, "08:30-17:30"],
        [_c, "Golden Temple (金殿)", 30, 4.3, "08:00-17:30"],
        [_s, "Kunming Flower Market (昆明花市)", 0, 4.3, "08:00-18:00"],
        [_c, "Yuantong Temple (圆通寺)", 6, 4.3, "08:00-17:30"],
        [_n, "Jiuxiang Scenic Area (九乡风景区)", 120, 4.3, "08:30-17:00"],
    ],
    "qingdao": [
        [_n, "Zhanqiao Pier (栈桥)", 0, 4.4, "24h"],
        [_n, "Laoshan Mountain (崂山)", 80, 4.5, "06:00-19:00"],
        [_n, "Badaguan Scenic Area (八大关)", 0, 4.5, "24h"],
        [_c, "Qingdao Beer Museum (青岛啤酒博物馆)", 60, 4.5, "08:00-17:30"],
        [_n, "May Fourth Square (五四广场)", 0, 4.3, "24h"],
        [_n, "Golden Sand Beach (金沙滩)", 0, 4.3, "24h"],
        [_c, "St. Michael's Cathedral (圣弥厄尔教堂)", 10, 4.4, "08:00-17:00"],
        [_n, "Qingdao Underwater World (青岛海底世界)", 130, 4.2, "08:30-17:00"],
        [_s, "Pichaiyuan (劈柴院)", 0, 4.1, "10:00-22:00"],
    ],
    "suzhou": [
        [_n, "Humble Administrator's Garden (拙政园)", 80, 4.6, "07:30-17:30"],
        [_c, "Tiger Hill (虎丘)", 70, 4.5, "07:30-17:30"],
        [_n, "Lingering Garden (留园)", 55, 4.5, "07:30-17:30"],
        [_c, "Hanshan Temple (寒山寺)", 20, 4.4, "07:30-17:00"],
        [_s, "Pingjiang Road (平江路)", 0, 4.5, "24h"],
        [_s, "Shantang Street (山塘街)", 0, 4.4, "24h"],
        [_c, "Suzhou Museum (苏州博物馆)", 0, 4.6, "09:00-17:00"],
        [_c, "Panmen Gate (盘门)", 40, 4.3, "08:00-17:00"],
        [_n, "Jinji Lake (金鸡湖)", 0, 4.4, "24h"],
        [_c, "Master of the Nets Garden (网师园)", 40, 4.5, "07:30-17:30"],
    ],
    "sanya": [
        [_n, "Yalong Bay (亚龙湾)", 0, 4.5, "24h"],
        [_n, "Nanshan Temple (南山寺)", 150, 4.5, "08:00-17:30"],
        [_n, "Wuzhizhou Island (蜈支洲岛)", 144, 4.5, "08:00-17:30"],
        [_n, "Dadonghai Beach (大东海)", 0, 4.3, "24h"],
        [_n, "Tianya Haijiao (天涯海角)", 81, 4.3, "07:30-18:00"],
        [_n, "Sanya Bay (三亚湾)", 0, 4.4, "24h"],
        [_n, "Luhuitou Park (鹿回头公园)", 42, 4.3, "08:00-22:00"],
        [_c, "Binglanggu (槟榔谷)", 80, 4.2, "08:00-17:30"],
        [_e, "Sanya Romance Park (三亚千古情)", 280, 4.4, "12:00-21:30"],
    ],
    "ningbo": [
        [_c, "Tianyi Pavilion (天一阁)", 30, 4.5, "08:30-17:00"],
        [_c, "Baoguo Temple (保国寺)", 20, 4.3, "08:00-17:00"],
        [_n, "Dongqian Lake (东钱湖)", 0, 4.5, "24h"],
        [_n, "Putuo Mountain (普陀山)", 160, 4.6, "06:00-17:30"],
        [_c, "Ningbo Museum (宁波博物馆)", 0, 4.5, "09:00-17:00"],
        [_s, "Old Bund (老外滩)", 0, 4.3, "24h"],
        [_c, "Ashoka Temple (阿育王寺)", 0, 4.3, "06:00-17:00"],
        [_c, "Tiantong Temple (天童寺)", 0, 4.4, "06:00-17:00"],
        [_n, "Moon Lake Park (月湖公园)", 0, 4.3, "24h"],
        [_c, "Xikou-Tengtou (溪口腾头)", 120, 4.3, "08:00-17:00"],
    ],
    "changsha": [
        [_n, "Yuelu Mountain (岳麓山)", 0, 4.5, "06:00-23:00"],
        [_c, "Yuelu Academy (岳麓书院)", 40, 4.5, "07:30-18:00"],
        [_n, "Orange Island (橘子洲)", 0, 4.6, "24h"],
        [_c, "Hunan Provincial Museum (湖南省博物馆)", 0, 4.6, "09:00-17:00"],
        [_e, "Window of the World Changsha (长沙世界之窗)", 200, 4.2, "08:30-22:00"],
        [_s, "Taiping Street (太平街)", 0, 4.3, "24h"],
        [_s, "Huangxing Road (黄兴路步行街)", 0, 4.2, "10:00-22:00"],
        [_c, "Tianxin Pavilion (天心阁)", 32, 4.3, "07:30-17:30"],
        [_c, "Mawangdui Han Tombs (马王堆汉墓)", 0, 4.5, "09:00-17:00"],
    ],
    "tianjin": [
        [_n, "Haihe River (海河)", 0, 4.4, "24h"],
        [_c, "Tianjin Eye (天津之眼)", 70, 4.4, "09:30-21:30"],
        [_s, "Ancient Culture Street (古文化街)", 0, 4.3, "09:00-17:00"],
        [_e, "Tianjin Happy Valley (天津欢乐谷)", 200, 4.3, "09:30-18:00"],
        [_c, "Porcelain House (瓷房子)", 50, 4.2, "09:00-18:00"],
        [_c, "Tianjin Radio & TV Tower (天塔)", 50, 4.3, "08:30-21:00"],
        [_n, "Five Great Avenues (五大道)", 0, 4.5, "24h"],
        [_c, "Italian Style Town (意大利风情区)", 0, 4.3, "24h"],
        [_s, "Binjiang Avenue (滨江道)", 0, 4.2, "10:00-22:00"],
    ],
}
# fmt: on


def _known_attractions(destination: str, num_days: int, activity_styles: list[str]) -> list[dict]:
    """Return a curated list of real attraction names for known cities.
    Falls back to empty list if the city is not in our database."""
    key = destination.lower().strip().split(",")[0].strip()
    if key not in _RAW:
        return []

    raw_list = _RAW[key]

    # Match preferences: if user wants cultural, prioritize culture; etc.
    pref_set = {s.lower() for s in activity_styles}
    scored = []
    for entry in raw_list:
        atype, name, price, rating, hours = entry
        score = rating  # base score
        if atype == "culture" and any(w in pref_set for w in ("cultural", "culture", "museum", "history")):
            score += 1.0
        if atype == "nature" and any(w in pref_set for w in ("nature", "outdoor", "adventure", "hiking", "relaxed")):
            score += 1.0
        if atype == "entertainment" and any(w in pref_set for w in ("entertainment", "fun", "night")):
            score += 0.8
        if atype == "shopping" and any(w in pref_set for w in ("shopping", "food")):
            score += 0.5
        scored.append((score, entry))

    scored.sort(key=lambda x: -x[0])

    activities = []
    for i, (_, entry) in enumerate(scored[:num_days]):
        atype, name, price, rating, hours = entry
        activities.append({
            "id": f"known_{key}_{i}",
            "name": name,
            "location": destination,
            "description": f"Popular {atype} destination in {destination}",
            "type": atype,
            "start_time": "09:00",
            "end_time": "12:00",
            "ticket_price": price,
            "total_price": price,
            "opening_hours": hours,
            "best_visit_time": "09:00-11:00",
            "population_level": "medium",
            "rating": rating,
            "meal_slot": "lunch",
            "source": "known_database",
        })
    return activities
