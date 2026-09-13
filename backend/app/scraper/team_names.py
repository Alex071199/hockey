TEAM_NAME_MAP: dict[str, str] = {
    # === KHL ===
    "CSKA Moscow": "ЦСКА",
    "Dynamo Moscow": "Динамо М",
    "Dinamo Moscow": "Динамо М",
    "Dynamo M": "Динамо М",
    "Dinamo M": "Динамо М",
    "Dynamo Minsk": "Динамо Мн",
    "Dinamo Minsk": "Динамо Мн",
    "Spartak Moscow": "Спартак",
    "Spartak": "Спартак",
    "Lokomotiv Yaroslavl": "Локомотив",
    "Lokomotiv": "Локомотив",
    "Ak Bars Kazan": "Ак Барс",
    "Ak Bars": "Ак Барс",
    "Metallurg Magnitogorsk": "Металлург Мг",
    "Metallurg": "Металлург Мг",
    "Traktor Chelyabinsk": "Трактор",
    "Tractor Chelyabinsk": "Трактор",
    "Traktor": "Трактор",
    "Tractor": "Трактор",
    "Avtomobilist Yekaterinburg": "Автомобилист",
    "Avtomobilist": "Автомобилист",
    "Salavat Yulaev Ufa": "Салават Юлаев",
    "Salavat Yulaev": "Салават Юлаев",
    "Barys Nur-Sultan": "Барыс",
    "Barys Astana": "Барыс",
    "Barys": "Барыс",
    "Torpedo Nizhny Novgorod": "Торпедо",
    "Torpedo": "Торпедо",
    "Severstal Cherepovets": "Северсталь",
    "Severstal": "Северсталь",
    "Sibir Novosibirsk": "Сибирь",
    "Sibir": "Сибирь",
    "Admiral Vladivostok": "Адмирал",
    "Admiral": "Адмирал",
    "Amur Khabarovsk": "Амур",
    "Amur": "Амур",
    "Neftekhimik Nizhnekamsk": "Нефтехимик",
    "Neftekhimik": "Нефтехимик",
    "HC Sochi": "ХК Сочи",
    "Sochi": "ХК Сочи",
    "Avangard Omsk": "Авангард",
    "Avangard": "Авангард",
    "Lada Togliatti": "Лада",
    "Lada": "Лада",
    "Shanghai Dragons": "Шанхайские Драконы",
    "SKA St. Petersburg": "СКА",
    "SKA": "СКА",

    # === VHL ===
    "Yuzhny Ural": "Южный Урал",
    "Gornyak": "Горняк",
    "Ugra": "Угра",
    "Ryazan-VDV": "Рязань-ВДВ",
    "Zauralye": "Зауралье",
    "Dinamo St. Petersburg": "Динамо СПб",
    "Toros Neftekamsk": "Торос",
    "Bars Kazan": "Барс",
    "Molot Permice": "Молот",
    "Rubin Tyumen": "Рубин",
    "Sokol Krasnoyarsk": "Сокол",
    "Tambov": "Тамбов",
    "Vityaz Podolsk": "Витязь",
    "Kristall Saratov": "Кристалл",
    "HC Ryazan": "Рязань",
    "Ermak Angarsk": "Ермак",
    "Buran Voronezh": "Буран",
    "HC Rostov": "Ростов",
    "Izhstal Izhevsk": "Ижсталь",
    "Khimik Voskresensk": "Химик",
    "Neftyanik Almetievsk": "Нефтяник",
    "HC Beibarys": "Бейбарыс",
    "HC Arlan": "Арлан",
    "Nomad Astana": "Номад",
    "HC Almaty": "Алматы",
    "Almaty": "Алматы",
    "HC Saryarka": "Сарыарка",
    "Slavutich": "Славутич",
    "Shakhter": "Шахтёр",
    "Toros": "Торос",
    "Izhstal": "Ижсталь",
    "Dynamo SPb": "Динамо СПб",
    "SKA-VMF": "СКА-ВМФ",
    "Olimpiya": "Олимпия",
    "Zvezda Moscow": "Звезда",
    "Zvezda": "Звезда",
    "HK Tambov": "Тамбов",
    "Neftyanik": "Нефтяник",
    "Buran Voronezh": "Буран",
    "Bars": "Барс",
    "Dizel": "Дизель",
    "Dizel Penza": "Дизель",
    "CSK VVS": "ЦСК ВВС",
    "Ertis Pavlodar": "Иртыш",
    "Arlan": "Арлан",
    "Arlan Kókshetaý": "Арлан",

    # === MHL ===
    "MHK Spartak": "Спартак М",
    "Krasnaya Armiya": "Красная Армия",
    "CSKA-Junior": "ЦСКА М",
    "CSKA- Junior": "ЦСКА М",
    "Loko Yaroslavl": "Локо",
    "Avto Yekaterinburg": "Авто",
    "Tolpar Ufa": "Толпар",
    "Belye Medvedi": "Белые Медведи",
    "Sibirskie Snaipery": "Сибирские Снайперы",
    "Mikhailov Academy": "Академия Михайлова",
    "Stalnye Lisy": "Стальные Лисы",
    "SKA-Junior": "СКА М",
    "SKA- Junior": "СКА М",
    "Dynamo Saint Petersburg-Junior": "Динамо СПб М",
    "Dynamo Saint Petersburg- Junior": "Динамо СПб М",
    "JHC Dynamo Moscow": "Динамо Москва М",
    "Amurskie Tigry": "Амурские Тигры",
    "Taifun": "Тайфун",
    "Dinamo-Shinnik": "Динамо-Шинник",
    "Shinnik": "Шинник",
    "Chaika Nizhny": "Чайка",
    "Irbis": "Ирбис",
    "Almaz": "Алмаз",
    "SKA Academy": "СКА-Академия",
}

# Russian names of KHL clubs — used to detect league by team names
KHL_TEAMS_RU: set[str] = {
    "ЦСКА", "Динамо М", "Динамо Мн", "Спартак", "Локомотив",
    "Ак Барс", "Металлург Мг", "Трактор", "Автомобилист",
    "Салават Юлаев", "Барыс", "Торпедо", "Северсталь", "Сибирь",
    "Адмирал", "Амур", "Нефтехимик", "ХК Сочи", "Авангард",
    "Лада", "Шанхайские Драконы", "СКА",
}

# Source name variants (usually with a city suffix) -> base calendar name.
# Explicit map only (no generic suffix stripping) so that
# "Динамо М" (Moscow) and "Динамо Мн" (Minsk) stay distinct.
CANONICAL_TEAM_NAMES: dict[str, str] = {
    "Лада Тл": "Лада",
    "Лада Тольятти": "Лада",
    "Спартак М": "Спартак",
    "Спартак Москва": "Спартак",
    "Торпедо НН": "Торпедо",
    "Торпедо Нижний Новгород": "Торпедо",
    "Динамо Москва": "Динамо М",
    "Динамо Мск": "Динамо М",
    "Динамо Минск": "Динамо Мн",
    "ЦСКА Москва": "ЦСКА",
    "СКА СПб": "СКА",
    "СКА Санкт-Петербург": "СКА",
    "Сибирь Новосибирск": "Сибирь",
    "Авангард Омск": "Авангард",
    "Адмирал Владивосток": "Адмирал",
    "Ак Барс Казань": "Ак Барс",
    "Амур Хабаровск": "Амур",
    "Автомобилист Екатеринбург": "Автомобилист",
    "Барыс Астана": "Барыс",
    "Локомотив Ярославль": "Локомотив",
    "Металлург Магнитогорск": "Металлург Мг",
    "Нефтехимик Нижнекамск": "Нефтехимик",
    "Салават Юлаев Уфа": "Салават Юлаев",
    "Северсталь Череповец": "Северсталь",
    "Трактор Челябинск": "Трактор",
    "Сочи": "ХК Сочи",
}


def canonical_team_name(name: str) -> str:
    """Reduce a source team name to the base calendar name."""
    stripped = name.strip()
    if stripped in CANONICAL_TEAM_NAMES:
        return CANONICAL_TEAM_NAMES[stripped]
    lowered = stripped.lower()
    for key, value in CANONICAL_TEAM_NAMES.items():
        if key.lower() == lowered:
            return value
    return stripped


# Additional partial/keyword matching for names not in the exact map
PARTIAL_KEYWORD_MAP: dict[str, str] = {
    "авангард": "Авангард",
    "dinamo minsk": "Динамо Мн",
    "динамо минск": "Динамо Мн",
    "динамо м": "Динамо М",
    "hc sochi": "ХК Сочи",
    "хк сочи": "ХК Сочи",
    "shanghai": "Шанхайские Драконы",
    "дракон": "Шанхайские Драконы",
    "dragon": "Шанхайские Драконы",
}


def translate_team_name(name: str) -> str:
    """Translate team name from Latin to Russian."""
    # 1. Exact match
    if name in TEAM_NAME_MAP:
        return TEAM_NAME_MAP[name]

    # 2. Case-insensitive exact match
    name_lower = name.lower()
    for key, value in TEAM_NAME_MAP.items():
        if key.lower() == name_lower:
            return value

    # 3. Partial/keyword match
    for keyword, value in PARTIAL_KEYWORD_MAP.items():
        if keyword in name_lower:
            return value

    return name
