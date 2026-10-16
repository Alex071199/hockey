from app.scraper.livetv import _is_jastar, _parse_matches


def test_jastar_by_label():
    assert _is_jastar("MHL", "Jastar Hokei Ligasy", "Арлан", "Жас Батыр")
    assert _is_jastar("MHL", "Kazakhstan", "Локо", "Чайка")
    assert _is_jastar("MHL", "МХЛ", "Локо", "Чайка") is False


def test_jastar_by_mol_suffix():
    assert _is_jastar("MHL", "МХЛ", "Арлан (мол)", "Жас Батыр (мол)")
    assert _is_jastar("MHL", "МХЛ", "Кармет (мол)", "Туран Тайгерс (мол)")
    assert _is_jastar("MHL", "МХЛ", "Тайфун", "Локо") is False


def test_jastar_by_team_token_mhl_only():
    assert _is_jastar("MHL", "МХЛ", "Барыс", "Кулагер")
    assert _is_jastar("MHL", "МХЛ", "Астана", "Сункар")
    assert _is_jastar("KHL", "КХЛ", "Барыс", "Ак Барыс Татарстан") is False


def test_snezhnye_barsy_is_mhl_not_jastar():
    assert _is_jastar("MHL", "МХЛ", "Снежные Барсы", "Спутник Альметьевск") is False
    assert _is_jastar("MHL", "МХЛ", "Снежные Барсы", "МХК Молот") is False


def test_regular_mhl_not_filtered():
    assert _is_jastar("MHL", "МХЛ", "Тайфун", "Красная Армия") is False
    assert _is_jastar("MHL", "МХЛ", "Кузнецкие Медведи", "Красноярские Рыси") is False


def _icon_html(eid, slug, teams, time_and_label, league_icon="МХЛ"):
    return (
        f'<div><img src="i.gif" alt="Хоккей. {league_icon}"></div>'
        f'<a href="/eventinfo/{eid}_{slug}/">{teams}</a>'
        f' {time_and_label} '
    )


def test_parse_matches_drops_jastar_keeps_mhl():
    pad = " " * 400  # chunk ищет event в [-300; +1200] от иконки — не склеиваем строки
    html = (
        _icon_html(495781592, "arlan_zhas_batyr",
                   "Арлан (мол) – Жас Батыр (мол)", "19:00 (Jastar Hokei Ligasy)")
        + pad
        + _icon_html(450059654, "spartak_mah_almaz",
                     "Спартак МАХ – Алмаз", "19:00 (МХЛ)")
        + pad
        + _icon_html(8235832, "dinamo_m_km_atlant",
                     "МХК Динамо М – Красная Машина Атлант", "19:00 (МХЛ)")
    )
    items = _parse_matches(html)
    eids = {m["event_id"] for m in items}
    assert "495781592" not in eids
    assert "450059654" in eids
    assert "8235832" in eids
