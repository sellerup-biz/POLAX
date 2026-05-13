// ─────────────────────────────────────────────────────────────────
// POLAX · Shared Theme + i18n System
// ─────────────────────────────────────────────────────────────────
(function(){

// ── Translations ──────────────────────────────────────────────────
var TR = {
  ru: {
    // Nav
    nav_analytics:'Аналитика →', nav_unit:'Юнит-экономика →',
    nav_categories:'Продажи по категориям →', nav_main:'← Главная',
    nav_back:'← Главный дашборд', nav_settings:'Настройки',
    // Theme
    theme_light:'Светлая', theme_dark:'Тёмная',
    // Index
    hdr_sub:'Правила ценообразования · Allegro + eMAG · 4 магазина',
    daily_title:'Продажи по дням · последние 30 дней',
    update_auto:'Allegro + eMAG · обновляется каждую ночь автоматически',
    monthly_title:'Продажи по месяцам · 2026',
    monthly_totals:'Сумма по месяцам',
    pricing_section:'Правила ценообразования · Allegro',
    legend_cheaper:'Дешевле рынка (−zł / −%)',
    legend_pricier:'Дороже мин. цены (+20%)',
    legend_ref:'Ориентир: самая дешёвая цена на рынке',
    goal_title:'Цель: 200 000 zł в месяц',
    goal_sub:'суммарно по всем 4 магазинам (Allegro + eMAG)',
    goal_best:'Лучший месяц',
    goal_current:'Текущий месяц',
    goal_best_cur:'Лучший и текущий месяц',
    goal_to_best:'До цели (лучший):',
    goal_to_cur:'До цели (текущий):',
    all_shops:'ВСЕ МАГАЗИНЫ', total_period:'всего за период',
    total_sum:'общая сумма', partial:'(неполный день)',
    rule_cheaper:'чем самая дешёвая цена на рынке',
    rule_above:'от самой дешёвой цены на рынке',
    rule_all_other:'Все остальные товары', rule_all:'Все товары',
    ads_title:'ADS · Рекламные кампании',
    shop_rules_2:'2 правила цены', shop_rules_5:'5 правил цены + ADS',
    shop_rules_6:'6 правил цены',
    rule_cheaper_ads:'чем самая дешёвая цена на рынке · отдельный ADS',
    camp_company:'Компания', camp_group:'группа', camp_all_except:'все товары кроме:',
    goog_prod:'товары', range_from:'от', range_to:'до', range_above_all:'все товары >',
    // Analytics
    an_title:'POLAX · Аналитика',
    an_sub:'Продажи и расходы по месяцам · все магазины · в PLN',
    sales_for:'Продажи за', sales_pln_sfx:'· в PLN',
    shops_bd:'Продажи по магазинам', countries_bd:'Продажи по странам',
    costs_bd:'Расходы по категориям', summary:'Сводка месяца',
    shop_details:'Детализация по магазинам',
    dyn_title:'Динамика продаж · все магазины суммарно',
    dyn_tag:'PLN · по месяцам',
    nbp_loading:'НБП курс...', nbp_na:'НБП недоступен',
    c_pl:'🇵🇱 Польша (Allegro)', c_cz:'🇨🇿 Чехия (Allegro)',
    c_hu:'🇭🇺 Венгрия (Allegro)', c_sk:'🇸🇰 Словакия (Allegro)',
    c_ro:'🇷🇴 Румыния (eMAG)', c_bg:'🇧🇬 Болгария (eMAG)',
    c_hu_e:'🇭🇺 Венгрия (eMAG)',
    total_all_pln:'Итого (все → PLN)', total:'Итого',
    total_costs:'Итого расходы', sales_pln:'Продажи (PLN)',
    costs_pln:'Расходы (PLN, все рынки)', profit:'Прибыль (оценка)',
    cost_comm:'Obowiązkowe (комиссия)', cost_del:'Dostawa (доставка)',
    cost_ads:'Reklama i promowanie', cost_sub:'Abonament',
    cost_disc:'Rabaty od Allegro',
    sales_month:'продажи PLN за месяц',
    cat_col:'Категория', sum_col:'Сумма', pct_col:'% продаж',
    chart_sales:'Все магазины · продажи',
    chart_costs:'Расходы суммарно · % над столбиком',
    chart_all_s:'Продажи (все магазины)', chart_all_c:'Расходы суммарно (PLN)',
    // Unit economy
    ue_title:'POLAX · Юнит-экономика',
    ue_loading:'Загрузка каталога и данных…',
    ue_name:'Юнит-экономика', ue_updated:'обновлено', ue_err_title:'Ошибка загрузки данных',
    b_hit:'★ Хит', b_win:'↑ Выигрывает', b_lose:'✕ Проигрышный', b_sleep:'◎ Спящий', b_nocog:'? Нет COG',
    tab_all:'Все', f_all:'Все', f_hit:'★ Хиты', f_win:'↑ Выигрывает',
    f_lose:'✕ Проигрышные', f_sleep:'◎ Спящие', f_nocog:'? Без COG',
    p_all:'Все время', p_30:'Последние 30 дней', p_custom:'Свой',
    sort_lbl:'Сортировка:', s_rev:'Выручка', s_sales:'Продажи',
    s_profit:'Прибыль', s_margin:'Маржа', s_cog:'Себестоимость',
    s_name:'Название', col_prod:'Товар', col_cog:'Себест.',
    col_rev:'Выручка', col_profit:'Прибыль', col_margin:'Маржа',
    no_prods:'Нет товаров по выбранным фильтрам',
    period_lbl:'📅 ПЕРИОД:', from_lbl:'С', to_lbl:'По',
    loading_pill:'⟳ загрузка…',
    units_abbr:'шт.', days_abbr:'дн.',
    items_lbl:'товаров', page_lbl:'стр.', of_lbl:'из',
    col_fees:'Сборы', col_qty_hdr:'Кол-во', col_sku_hdr:'SKU',
    sb_net_margin:'Чистая маржа', sb_pct_rev:'% от выручки',
    sb_allegro_fees:'Сборы Allegro', sb_roas:'ROAS',
    sb_ads_cpc:'Реклама CPC', sb_ads_promo:'реклама+промо',
    sb_promo:'Промование', sb_dist:'Распределение выручки',
    sb_no_sales:'нет продаж', sb_transactions:'транзакций',
    sb_no_data:'Нет данных за выбранный период',
    sb_price_lbl:'🏷 Цена', total_cats:'категорий',
    no_data_period:'Нет данных за выбранный период',
    // Categories
    cat_title:'POLAX · Продажи по категориям',
    cat_loading:'Загрузка каталога и данных…',
    cat_chart_t:'Выручка по категориям',
    cat_chart_s:'Топ категорий по выручке за период',
    cat_tbl_t:'Все категории',
    col_cat:'Категория', col_units:'Шт.', col_margin:'Маржа %',
    col_avg:'Ср. цена', top_show:'Показывать топ:',
    cat_top_pfx:'Топ', cat_top_sfx:'категорий по выручке',
    cat_others:'Остальные объединены в группу «Другие»',
    cat_sort_rev:'По выручке', cat_sort_qty:'По кол-ву',
    cat_sort_pct:'По % продаж', cat_sort_skus:'По кол-ву SKU', cat_sort_mg:'По марже',
    // Footers
    f_main:'POLAX · ALLEGRO PRICING RULES · 2026',
    f_an:'POLAX · АНАЛИТИКА · 2026',
    f_ue:'POLAX · Юнит-экономика',
    f_cat:'POLAX · Продажи по категориям',
    // Month names (display only — keys in data.json are always Russian)
    months:['Янв','Фев','Мар','Апр','Май','Июн','Июл','Авг','Сен','Окт','Ноя','Дек'],
  },

  uk: {
    nav_analytics:'Аналітика →', nav_unit:'Юніт-економіка →',
    nav_categories:'Продажі за категоріями →', nav_main:'← Головна',
    nav_back:'← Головний дашборд', nav_settings:'Налаштування',
    theme_light:'Світла', theme_dark:'Темна',
    hdr_sub:'Правила ціноутворення · Allegro + eMAG · 4 магазини',
    daily_title:'Продажі по днях · останні 30 днів',
    update_auto:'Allegro + eMAG · оновлюється щоночі автоматично',
    monthly_title:'Продажі по місяцях · 2026',
    monthly_totals:'Сума по місяцях',
    pricing_section:'Правила ціноутворення · Allegro',
    legend_cheaper:'Дешевше ринку (−zł / −%)',
    legend_pricier:'Дорожче мін. ціни (+20%)',
    legend_ref:'Орієнтир: найдешевша ціна на ринку',
    goal_title:'Ціль: 200 000 zł на місяць',
    goal_sub:'разом по всіх 4 магазинах (Allegro + eMAG)',
    goal_best:'Найкращий місяць', goal_current:'Поточний місяць',
    goal_best_cur:'Найкращий і поточний місяць',
    goal_to_best:'До цілі (найкращий):', goal_to_cur:'До цілі (поточний):',
    all_shops:'ВСІ МАГАЗИНИ', total_period:'всього за період',
    total_sum:'загальна сума', partial:'(неповний день)',
    rule_cheaper:'ніж найдешевша ціна на ринку',
    rule_above:'від найдешевшої ціни на ринку',
    rule_all_other:'Всі інші товари', rule_all:'Всі товари',
    ads_title:'ADS · Рекламні кампанії',
    shop_rules_2:'2 правила ціни', shop_rules_5:'5 правил ціни + ADS',
    shop_rules_6:'6 правил ціни',
    rule_cheaper_ads:'ніж найдешевша ціна на ринку · окрема ADS',
    camp_company:'Кампанія', camp_group:'група', camp_all_except:'всі товари крім:',
    goog_prod:'товари', range_from:'від', range_to:'до', range_above_all:'всі товари >',
    an_title:'POLAX · Аналітика',
    an_sub:'Продажі та витрати по місяцях · всі магазини · в PLN',
    sales_for:'Продажі за', sales_pln_sfx:'· в PLN',
    shops_bd:'Продажі по магазинах', countries_bd:'Продажі по країнах',
    costs_bd:'Витрати по категоріях', summary:'Зведення місяця',
    shop_details:'Деталізація по магазинах',
    dyn_title:'Динаміка продажів · всі магазини',
    dyn_tag:'PLN · по місяцях',
    nbp_loading:'Курс НБП...', nbp_na:'НБП недоступний',
    c_pl:'🇵🇱 Польща (Allegro)', c_cz:'🇨🇿 Чехія (Allegro)',
    c_hu:'🇭🇺 Угорщина (Allegro)', c_sk:'🇸🇰 Словаччина (Allegro)',
    c_ro:'🇷🇴 Румунія (eMAG)', c_bg:'🇧🇬 Болгарія (eMAG)',
    c_hu_e:'🇭🇺 Угорщина (eMAG)',
    total_all_pln:'Разом (всі → PLN)', total:'Разом',
    total_costs:'Разом витрати', sales_pln:'Продажі (PLN)',
    costs_pln:'Витрати (PLN, всі ринки)', profit:'Прибуток (оцінка)',
    cost_comm:'Obowiązkowe (комісія)', cost_del:'Dostawa (доставка)',
    cost_ads:'Reklama i promowanie', cost_sub:'Abonament',
    cost_disc:'Rabaty od Allegro',
    sales_month:'продажі PLN за місяць',
    cat_col:'Категорія', sum_col:'Сума', pct_col:'% продажів',
    chart_sales:'Всі магазини · продажі',
    chart_costs:'Витрати · % над стовпчиком',
    chart_all_s:'Продажі (всі магазини)', chart_all_c:'Витрати (PLN)',
    ue_title:'POLAX · Юніт-економіка',
    ue_loading:'Завантаження каталогу та даних…',
    ue_name:'Юніт-економіка', ue_updated:'оновлено', ue_err_title:'Помилка завантаження даних',
    b_hit:'★ Хіт', b_win:'↑ Перемагає', b_lose:'✕ Програшний', b_sleep:'◎ Сплячий', b_nocog:'? Без COG',
    tab_all:'Всі', f_all:'Всі', f_hit:'★ Хіти', f_win:'↑ Перемагає',
    f_lose:'✕ Програшні', f_sleep:'◎ Сплячі', f_nocog:'? Без COG',
    p_all:'Весь час', p_30:'Останні 30 днів', p_custom:'Свій',
    sort_lbl:'Сортування:', s_rev:'Виручка', s_sales:'Продажі',
    s_profit:'Прибуток', s_margin:'Маржа', s_cog:'Собівартість',
    s_name:'Назва', col_prod:'Товар', col_cog:'Собів.',
    col_rev:'Виручка', col_profit:'Прибуток', col_margin:'Маржа',
    no_prods:'Немає товарів із такими фільтрами',
    period_lbl:'📅 ПЕРІОД:', from_lbl:'З', to_lbl:'По',
    loading_pill:'⟳ завантаження…',
    units_abbr:'шт.', days_abbr:'дн.',
    items_lbl:'товарів', page_lbl:'стор.', of_lbl:'з',
    col_fees:'Збори', col_qty_hdr:'Кількість', col_sku_hdr:'SKU',
    sb_net_margin:'Чистий прибуток', sb_pct_rev:'% від виручки',
    sb_allegro_fees:'Збори Allegro', sb_roas:'ROAS',
    sb_ads_cpc:'Реклама CPC', sb_ads_promo:'реклама+просування',
    sb_promo:'Просування', sb_dist:'Розподіл виручки',
    sb_no_sales:'немає продажів', sb_transactions:'транзакцій',
    sb_no_data:'Немає даних за обраний період',
    sb_price_lbl:'🏷 Ціна', total_cats:'категорій',
    no_data_period:'Немає даних за обраний період',
    cat_title:'POLAX · Продажі за категоріями',
    cat_loading:'Завантаження каталогу та даних…',
    cat_chart_t:'Виручка за категоріями',
    cat_chart_s:'Топ категорій за виручкою за період',
    cat_tbl_t:'Всі категорії',
    col_cat:'Категорія', col_units:'Шт.', col_margin:'Маржа %',
    col_avg:'Сер. ціна', top_show:'Показувати топ:',
    cat_top_pfx:'Топ', cat_top_sfx:'категорій за виручкою',
    cat_others:'Інші об\'єднані у групу «Інші»',
    cat_sort_rev:'За виручкою', cat_sort_qty:'За кількістю',
    cat_sort_pct:'За % продажів', cat_sort_skus:'За SKU', cat_sort_mg:'За маржею',
    f_main:'POLAX · ПРАВИЛА ЦІНОУТВОРЕННЯ · 2026',
    f_an:'POLAX · АНАЛІТИКА · 2026',
    f_ue:'POLAX · Юніт-економіка',
    f_cat:'POLAX · Продажі за категоріями',
    months:['Січ','Лют','Бер','Кві','Тра','Чер','Лип','Сер','Вер','Жов','Лис','Гру'],
  },

  en: {
    nav_analytics:'Analytics →', nav_unit:'Unit Economy →',
    nav_categories:'Sales by Category →', nav_main:'← Home',
    nav_back:'← Main Dashboard', nav_settings:'Settings',
    theme_light:'Light', theme_dark:'Dark',
    hdr_sub:'Pricing Rules · Allegro + eMAG · 4 stores',
    daily_title:'Daily Sales · Last 30 Days',
    update_auto:'Allegro + eMAG · updates automatically every night',
    monthly_title:'Monthly Sales · 2026',
    monthly_totals:'Monthly Totals',
    pricing_section:'Pricing Rules · Allegro',
    legend_cheaper:'Below market (−zł / −%)',
    legend_pricier:'Above min. price (+20%)',
    legend_ref:'Reference: cheapest market price',
    goal_title:'Goal: 200,000 zł / month',
    goal_sub:'total across all 4 stores (Allegro + eMAG)',
    goal_best:'Best Month', goal_current:'Current Month',
    goal_best_cur:'Best & Current Month',
    goal_to_best:'To goal (best):', goal_to_cur:'To goal (current):',
    all_shops:'ALL STORES', total_period:'total for period',
    total_sum:'grand total', partial:'(partial day)',
    rule_cheaper:'than cheapest market price',
    rule_above:'above cheapest market price',
    rule_all_other:'All other products', rule_all:'All products',
    ads_title:'ADS · Ad Campaigns',
    shop_rules_2:'2 pricing rules', shop_rules_5:'5 pricing rules + ADS',
    shop_rules_6:'6 pricing rules',
    rule_cheaper_ads:'than cheapest market price · separate ADS',
    camp_company:'Campaign', camp_group:'group', camp_all_except:'all products except:',
    goog_prod:'products', range_from:'from', range_to:'to', range_above_all:'all products >',
    an_title:'POLAX · Analytics',
    an_sub:'Sales & costs by month · all stores · in PLN',
    sales_for:'Sales for', sales_pln_sfx:'· in PLN',
    shops_bd:'Sales by Store', countries_bd:'Sales by Country',
    costs_bd:'Costs by Category', summary:'Month Summary',
    shop_details:'Store Breakdown',
    dyn_title:'Sales Trend · all stores combined',
    dyn_tag:'PLN · by month',
    nbp_loading:'NBP rate...', nbp_na:'NBP unavailable',
    c_pl:'🇵🇱 Poland (Allegro)', c_cz:'🇨🇿 Czech Republic (Allegro)',
    c_hu:'🇭🇺 Hungary (Allegro)', c_sk:'🇸🇰 Slovakia (Allegro)',
    c_ro:'🇷🇴 Romania (eMAG)', c_bg:'🇧🇬 Bulgaria (eMAG)',
    c_hu_e:'🇭🇺 Hungary (eMAG)',
    total_all_pln:'Total (all → PLN)', total:'Total',
    total_costs:'Total Costs', sales_pln:'Sales (PLN)',
    costs_pln:'Costs (PLN, all markets)', profit:'Profit (estimate)',
    cost_comm:'Commission', cost_del:'Delivery',
    cost_ads:'Advertising', cost_sub:'Subscription',
    cost_disc:'Discounts from Allegro',
    sales_month:'PLN sales for month',
    cat_col:'Category', sum_col:'Amount', pct_col:'% of sales',
    chart_sales:'All stores · sales',
    chart_costs:'Total costs · % above bar',
    chart_all_s:'Sales (all stores)', chart_all_c:'Total costs (PLN)',
    ue_title:'POLAX · Unit Economy',
    ue_loading:'Loading catalog and data…',
    ue_name:'Unit Economy', ue_updated:'updated', ue_err_title:'Data loading error',
    b_hit:'★ Hit', b_win:'↑ Winning', b_lose:'✕ Losing', b_sleep:'◎ Sleeping', b_nocog:'? No COG',
    tab_all:'All', f_all:'All', f_hit:'★ Hits', f_win:'↑ Winning',
    f_lose:'✕ Losing', f_sleep:'◎ Sleeping', f_nocog:'? No COG',
    p_all:'All time', p_30:'Last 30 days', p_custom:'Custom',
    sort_lbl:'Sort by:', s_rev:'Revenue', s_sales:'Sales',
    s_profit:'Profit', s_margin:'Margin', s_cog:'Cost',
    s_name:'Name', col_prod:'Product', col_cog:'COG',
    col_rev:'Revenue', col_profit:'Profit', col_margin:'Margin',
    no_prods:'No products match selected filters',
    period_lbl:'📅 PERIOD:', from_lbl:'From', to_lbl:'To',
    loading_pill:'⟳ loading…',
    units_abbr:'pcs', days_abbr:'days',
    items_lbl:'items', page_lbl:'p.', of_lbl:'of',
    col_fees:'Fees', col_qty_hdr:'Qty', col_sku_hdr:'SKUs',
    sb_net_margin:'Net margin', sb_pct_rev:'% of revenue',
    sb_allegro_fees:'Allegro fees', sb_roas:'ROAS',
    sb_ads_cpc:'Ads CPC', sb_ads_promo:'ads+promo',
    sb_promo:'Promotion', sb_dist:'Revenue distribution',
    sb_no_sales:'no sales', sb_transactions:'transactions',
    sb_no_data:'No data for selected period',
    sb_price_lbl:'🏷 Price', total_cats:'categories',
    no_data_period:'No data for selected period',
    cat_title:'POLAX · Sales by Category',
    cat_loading:'Loading catalog and data…',
    cat_chart_t:'Revenue by Category',
    cat_chart_s:'Top categories by revenue for period',
    cat_tbl_t:'All Categories',
    col_cat:'Category', col_units:'Units', col_margin:'Margin %',
    col_avg:'Avg. price', top_show:'Show top:',
    cat_top_pfx:'Top', cat_top_sfx:'categories by revenue',
    cat_others:'Others grouped as «Others»',
    cat_sort_rev:'By revenue', cat_sort_qty:'By quantity',
    cat_sort_pct:'By % of sales', cat_sort_skus:'By SKU count', cat_sort_mg:'By margin',
    f_main:'POLAX · ALLEGRO PRICING RULES · 2026',
    f_an:'POLAX · ANALYTICS · 2026',
    f_ue:'POLAX · Unit Economy',
    f_cat:'POLAX · Sales by Category',
    months:['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'],
  },

  pl: {
    nav_analytics:'Analityka →', nav_unit:'Ekonomia jednostkowa →',
    nav_categories:'Sprzedaż wg kategorii →', nav_main:'← Strona główna',
    nav_back:'← Główny dashboard', nav_settings:'Ustawienia',
    theme_light:'Jasny', theme_dark:'Ciemny',
    hdr_sub:'Zasady cenowe · Allegro + eMAG · 4 sklepy',
    daily_title:'Sprzedaż dzienna · ostatnie 30 dni',
    update_auto:'Allegro + eMAG · aktualizuje się co noc automatycznie',
    monthly_title:'Sprzedaż miesięczna · 2026',
    monthly_totals:'Sumy miesięczne',
    pricing_section:'Zasady cenowe · Allegro',
    legend_cheaper:'Taniej niż rynek (−zł / −%)',
    legend_pricier:'Powyżej min. ceny (+20%)',
    legend_ref:'Odniesienie: najtańsza cena na rynku',
    goal_title:'Cel: 200 000 zł miesięcznie',
    goal_sub:'łącznie dla wszystkich 4 sklepów (Allegro + eMAG)',
    goal_best:'Najlepszy miesiąc', goal_current:'Bieżący miesiąc',
    goal_best_cur:'Najlepszy i bieżący miesiąc',
    goal_to_best:'Do celu (najlepszy):', goal_to_cur:'Do celu (bieżący):',
    all_shops:'WSZYSTKIE SKLEPY', total_period:'łącznie za okres',
    total_sum:'suma łączna', partial:'(niepełny dzień)',
    rule_cheaper:'niż najtańsza cena na rynku',
    rule_above:'od najtańszej ceny na rynku',
    rule_all_other:'Wszystkie inne produkty', rule_all:'Wszystkie produkty',
    ads_title:'ADS · Kampanie reklamowe',
    shop_rules_2:'2 zasady ceny', shop_rules_5:'5 zasad ceny + ADS',
    shop_rules_6:'6 zasad ceny',
    rule_cheaper_ads:'niż najtańsza cena na rynku · osobna ADS',
    camp_company:'Kampania', camp_group:'grupa', camp_all_except:'wszystkie produkty oprócz:',
    goog_prod:'produkty', range_from:'od', range_to:'do', range_above_all:'wszystkie produkty >',
    an_title:'POLAX · Analityka',
    an_sub:'Sprzedaż i koszty miesięczne · wszystkie sklepy · w PLN',
    sales_for:'Sprzedaż za', sales_pln_sfx:'· w PLN',
    shops_bd:'Sprzedaż wg sklepów', countries_bd:'Sprzedaż wg krajów',
    costs_bd:'Koszty wg kategorii', summary:'Podsumowanie miesiąca',
    shop_details:'Szczegóły sklepów',
    dyn_title:'Dynamika sprzedaży · wszystkie sklepy',
    dyn_tag:'PLN · miesięcznie',
    nbp_loading:'Kurs NBP...', nbp_na:'NBP niedostępny',
    c_pl:'🇵🇱 Polska (Allegro)', c_cz:'🇨🇿 Czechy (Allegro)',
    c_hu:'🇭🇺 Węgry (Allegro)', c_sk:'🇸🇰 Słowacja (Allegro)',
    c_ro:'🇷🇴 Rumunia (eMAG)', c_bg:'🇧🇬 Bułgaria (eMAG)',
    c_hu_e:'🇭🇺 Węgry (eMAG)',
    total_all_pln:'Łącznie (wszystko → PLN)', total:'Łącznie',
    total_costs:'Koszty łącznie', sales_pln:'Sprzedaż (PLN)',
    costs_pln:'Koszty (PLN, wszystkie rynki)', profit:'Zysk (szacunek)',
    cost_comm:'Prowizja', cost_del:'Dostawa',
    cost_ads:'Reklama i promocja', cost_sub:'Abonament',
    cost_disc:'Rabaty od Allegro',
    sales_month:'sprzedaż PLN za miesiąc',
    cat_col:'Kategoria', sum_col:'Kwota', pct_col:'% sprzedaży',
    chart_sales:'Wszystkie sklepy · sprzedaż',
    chart_costs:'Koszty łącznie · % nad słupkiem',
    chart_all_s:'Sprzedaż (wszystkie sklepy)', chart_all_c:'Koszty łącznie (PLN)',
    ue_title:'POLAX · Ekonomia jednostkowa',
    ue_loading:'Ładowanie katalogu i danych…',
    ue_name:'Ekonomia jednostkowa', ue_updated:'zaktualizowano', ue_err_title:'Błąd ładowania danych',
    b_hit:'★ Hit', b_win:'↑ Wygrywa', b_lose:'✕ Przegrywa', b_sleep:'◎ Śpiący', b_nocog:'? Brak COG',
    tab_all:'Wszystkie', f_all:'Wszystkie', f_hit:'★ Hity', f_win:'↑ Wygrywa',
    f_lose:'✕ Przegrywa', f_sleep:'◎ Śpiące', f_nocog:'? Brak COG',
    p_all:'Cały czas', p_30:'Ostatnie 30 dni', p_custom:'Własny',
    sort_lbl:'Sortowanie:', s_rev:'Przychód', s_sales:'Sprzedaż',
    s_profit:'Zysk', s_margin:'Marża', s_cog:'Koszt',
    s_name:'Nazwa', col_prod:'Produkt', col_cog:'Koszt',
    col_rev:'Przychód', col_profit:'Zysk', col_margin:'Marża',
    no_prods:'Brak produktów spełniających filtry',
    period_lbl:'📅 OKRES:', from_lbl:'Od', to_lbl:'Do',
    loading_pill:'⟳ ładowanie…',
    units_abbr:'szt.', days_abbr:'dni',
    items_lbl:'pozycji', page_lbl:'str.', of_lbl:'z',
    col_fees:'Opłaty', col_qty_hdr:'Ilość', col_sku_hdr:'SKU',
    sb_net_margin:'Marża netto', sb_pct_rev:'% przychodu',
    sb_allegro_fees:'Opłaty Allegro', sb_roas:'ROAS',
    sb_ads_cpc:'Reklama CPC', sb_ads_promo:'reklama+promo',
    sb_promo:'Promowanie', sb_dist:'Podział przychodu',
    sb_no_sales:'brak sprzedaży', sb_transactions:'transakcji',
    sb_no_data:'Brak danych dla wybranego okresu',
    sb_price_lbl:'🏷 Cena', total_cats:'kategorii',
    no_data_period:'Brak danych dla wybranego okresu',
    cat_title:'POLAX · Sprzedaż wg kategorii',
    cat_loading:'Ładowanie katalogu i danych…',
    cat_chart_t:'Przychód wg kategorii',
    cat_chart_s:'Top kategorii wg przychodu za okres',
    cat_tbl_t:'Wszystkie kategorie',
    col_cat:'Kategoria', col_units:'Szt.', col_margin:'Marża %',
    col_avg:'Śr. cena', top_show:'Pokaż top:',
    cat_top_pfx:'Top', cat_top_sfx:'kategorii wg przychodu',
    cat_others:'Pozostałe zgrupowane jako «Inne»',
    cat_sort_rev:'Wg przychodu', cat_sort_qty:'Wg ilości',
    cat_sort_pct:'Wg % sprzedaży', cat_sort_skus:'Wg SKU', cat_sort_mg:'Wg marży',
    f_main:'POLAX · ZASADY CENOWE ALLEGRO · 2026',
    f_an:'POLAX · ANALITYKA · 2026',
    f_ue:'POLAX · Ekonomia jednostkowa',
    f_cat:'POLAX · Sprzedaż wg kategorii',
    months:['Sty','Lut','Mar','Kwi','Maj','Cze','Lip','Sie','Wrz','Paź','Lis','Gru'],
  }
};

// Mapping of Russian month short names (as used in data.json) to month index
var RU_MONTH_IDX = {
  'Янв':0,'Фев':1,'Мар':2,'Апр':3,'Май':4,'Июн':5,
  'Июл':6,'Авг':7,'Сен':8,'Окт':9,'Ноя':10,'Дек':11
};

// ── State ─────────────────────────────────────────────────────────
var lang  = localStorage.getItem('polax-lang')  || 'ru';
var theme = localStorage.getItem('polax-theme') || 'light';
var _callbacks = [];

// ── Translate ──────────────────────────────────────────────────────
function T(key) {
  return (TR[lang] || TR.ru)[key] || (TR.ru[key] || key);
}
window.T = T;

// Convert a Russian-format month string "Янв 2026" to current language display
window.displayMonth = function(ruMonth) {
  if (!ruMonth) return ruMonth;
  var parts = ruMonth.split(' ');
  if (parts.length !== 2) return ruMonth;
  var idx = RU_MONTH_IDX[parts[0]];
  if (idx === undefined) return ruMonth;
  var months = (TR[lang] || TR.ru).months;
  return months[idx] + ' ' + parts[1];
};

// ── Theme ──────────────────────────────────────────────────────────
function applyTheme(t) {
  theme = t;
  document.documentElement.setAttribute('data-theme', t);
  localStorage.setItem('polax-theme', t);
  var btn = document.getElementById('polax-theme-btn');
  if (btn) btn.textContent = (t === 'dark' ? '☀ ' : '🌙 ') + T(t === 'dark' ? 'theme_light' : 'theme_dark');
  _callbacks.forEach(function(fn){ fn('theme'); });
}
window.polaxToggleTheme = function() {
  applyTheme(theme === 'dark' ? 'light' : 'dark');
};

// ── Language ───────────────────────────────────────────────────────
function applyLang(l) {
  lang = l;
  localStorage.setItem('polax-lang', l);
  // Update static data-i18n elements
  document.querySelectorAll('[data-i18n]').forEach(function(el) {
    var key = el.getAttribute('data-i18n');
    var val = T(key);
    if (el.getAttribute('data-i18n-html')) el.innerHTML = val;
    else el.textContent = val;
  });
  // Update lang button highlights
  document.querySelectorAll('.polax-lang-btn').forEach(function(b) {
    b.classList.toggle('active', b.getAttribute('data-lang') === l);
  });
  // Update theme button text
  var btn = document.getElementById('polax-theme-btn');
  if (btn) btn.textContent = (theme === 'dark' ? '☀ ' : '🌙 ') + T(theme === 'dark' ? 'theme_light' : 'theme_dark');
  // Fire re-render callbacks
  _callbacks.forEach(function(fn){ fn('lang'); });
}
window.polaxSwitchLang = function(l) { applyLang(l); };

// Register a callback to be called on theme or lang change
window.onPolaxChange = function(fn) { _callbacks.push(fn); };

// ── CSS injection ─────────────────────────────────────────────────
var css = `
  :root {
    --bg-page:#090909; --bg-card:#111111; --bg-subtle:#0f0f0f;
    --bg-deep:#0d0d0d; --bg-alt:#0e0e0e; --bg-input:#0d0d0d;
    --text-primary:#e8e8e8; --text-secondary:#aaa; --text-muted:#888;
    --text-faint:#666; --border:#252525; --border-mid:#222;
    --border-subtle:#1e1e1e; --border-faint:#181818; --sep:#333;
    --tag-am-bg:#1a0d00; --tag-am-t:#D4891E;
    --tag-tl-bg:#001a12; --tag-tl-t:#1A9E7A;
    --tag-bl-bg:#001226; --tag-bl-t:#3B8FD4;
    --tag-gn-bg:#0d1a00; --tag-gn-t:#6db84d;
    --tag-rd-bg:#1a0606; --tag-rd-t:#E04545;
    --progress-bg:#1a1a1a; --chart-grid:rgba(255,255,255,0.07);
    --chart-tick:#666; --chart-legend:#aaa; --chart-line:#e8e8e8;
    --shadow:rgba(0,0,0,0.6); --active-neutral:#2a2a2a; --active-neutral-t:#fff;
  }
  [data-theme="light"] {
    --bg-page:#F4F2EE; --bg-card:#ffffff; --bg-subtle:#fdfaf4;
    --bg-deep:#f9f7f4; --bg-alt:#fdfaf4; --bg-input:#ffffff;
    --text-primary:#1a1a1a; --text-secondary:#555; --text-muted:#777;
    --text-faint:#888; --border:#e0dcd4; --border-mid:#ddd;
    --border-subtle:#f0ece4; --border-faint:#f5f2ec; --sep:#e5e1d8;
    --tag-am-bg:#FAEEDA; --tag-am-t:#BA7517;
    --tag-tl-bg:#E1F5EE; --tag-tl-t:#0F6E56;
    --tag-bl-bg:#E6F1FB; --tag-bl-t:#185FA5;
    --tag-gn-bg:#EAF3DE; --tag-gn-t:#3B6D11;
    --tag-rd-bg:#FCEBEB; --tag-rd-t:#A32D2D;
    --progress-bg:#f0ece4; --chart-grid:rgba(0,0,0,0.04);
    --chart-tick:#999; --chart-legend:#555; --chart-line:#1a1a1a;
    --shadow:rgba(0,0,0,0.15); --active-neutral:#BA7517; --active-neutral-t:#fff;
  }
  /* Controls bar */
  #polax-controls {
    display:flex; align-items:center; gap:6px;
    flex-shrink:0; flex-wrap:wrap;
    min-width:258px;
  }
  #polax-theme-btn {
    font-size:12px; padding:5px 13px; border-radius:20px;
    border:1px solid var(--border-mid); background:var(--bg-deep);
    color:var(--text-secondary); cursor:pointer; font-family:inherit;
    white-space:nowrap; transition:all .15s; font-weight:500;
  }
  #polax-theme-btn:hover { border-color:#BA7517; color:#BA7517; }
  .polax-lang-sep { width:1px; height:20px; background:var(--border-mid); flex-shrink:0; }
  .polax-lang-group { display:flex; gap:3px; }
  .polax-lang-btn {
    font-size:11px; padding:4px 9px; border-radius:6px;
    border:1px solid var(--border-mid); background:transparent;
    color:var(--text-muted); cursor:pointer; font-family:inherit;
    font-weight:700; letter-spacing:.3px; transition:all .15s;
  }
  .polax-lang-btn.active { background:#BA7517; color:#fff; border-color:#BA7517; }
  .polax-lang-btn:hover:not(.active) { border-color:#BA7517; color:#BA7517; }
`;
var styleEl = document.createElement('style');
styleEl.textContent = css;
document.head.appendChild(styleEl);

// ── UI injection ───────────────────────────────────────────────────
function buildControls() {
  var el = document.getElementById('polax-controls');
  if (!el) return;
  el.innerHTML =
    '<button id="polax-theme-btn" onclick="polaxToggleTheme()"></button>' +
    '<div class="polax-lang-sep"></div>' +
    '<div class="polax-lang-group">' +
    ['ru','uk','en','pl'].map(function(l){
      return '<button class="polax-lang-btn' + (l===lang?' active':'') +
             '" data-lang="'+l+'" onclick="polaxSwitchLang(\''+l+'\')">'+l.toUpperCase()+'</button>';
    }).join('') +
    '</div>';
  // Set theme button text
  document.getElementById('polax-theme-btn').textContent =
    (theme === 'dark' ? '☀ ' : '🌙 ') + T(theme === 'dark' ? 'theme_light' : 'theme_dark');
}

// ── Init ───────────────────────────────────────────────────────────
// Apply theme immediately (before DOM ready) to avoid flash
document.documentElement.setAttribute('data-theme', theme);

function _polaxInit() {
  buildControls();
  document.documentElement.setAttribute('data-theme', theme);
  applyLang(lang);
}
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', _polaxInit);
} else {
  _polaxInit();
}

})();
