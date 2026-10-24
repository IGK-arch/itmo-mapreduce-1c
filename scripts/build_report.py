"""Build the Russian report from the actual S3 runs and analysis tables."""
from pathlib import Path
import hashlib
import html
import json
import statistics

import bootstrap
from bootstrap import ROOT
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle, Preformatted, Flowable, KeepTogether
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_RIGHT
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.utils import ImageReader

OUT = ROOT / 'output' / 'pdf' / 'Карташов_Игорь_J3312_MapReduce.pdf'
for font, filename in [('Times', 'times.ttf'), ('Times-Bold', 'timesbd.ttf'), ('Times-Italic', 'timesi.ttf'), ('Mono', 'consola.ttf')]:
    pdfmetrics.registerFont(TTFont(font, 'C:/Windows/Fonts/' + filename))
pdfmetrics.registerFontFamily('Times', normal='Times', bold='Times-Bold', italic='Times-Italic', boldItalic='Times-Bold')
W = A4[0] - 40 * mm
styles = {
    'body': ParagraphStyle('body', fontName='Times', fontSize=11.7, leading=15.2, alignment=TA_JUSTIFY, spaceAfter=8),
    'h1': ParagraphStyle('h1', fontName='Times-Bold', fontSize=16, leading=20, spaceAfter=12),
    'h2': ParagraphStyle('h2', fontName='Times-Bold', fontSize=12.7, leading=16, spaceBefore=8, spaceAfter=7),
    'cell': ParagraphStyle('cell', fontName='Times', fontSize=10, leading=12.5),
    'head': ParagraphStyle('head', fontName='Times-Bold', fontSize=9.9, leading=12.4),
    'caption': ParagraphStyle('caption', fontName='Times-Italic', fontSize=10, leading=12.7, alignment=TA_CENTER, spaceBefore=5, spaceAfter=9),
    'code': ParagraphStyle('code', fontName='Mono', fontSize=8.4, leading=11.3, spaceBefore=3, spaceAfter=9, backColor=colors.HexColor('#f2f2f2'), borderPadding=5),
}
story = []
views = []


def read(path):
    return json.loads((ROOT / path).read_text(encoding='utf-8'))


def n(value):
    if value is None:
        return '-'
    return f'{value:,.0f}'.replace(',', ' ')


def dec(value, digits=2):
    return f'{value:.{digits}f}'.replace('.', ',')


def p(text, style='body'):
    story.append(Paragraph(text, styles[style]))


def h(text):
    p(text, 'h1')


def sub(text):
    p(text, 'h2')


def code(text):
    story.append(Preformatted(text, styles['code']))


def page():
    story.append(PageBreak())


def table(headers, rows, widths):
    def cell(value, style):
        return Paragraph(html.escape(str(value)).replace('\n', '<br/>'), styles[style])
    data = [[cell(v, 'head') for v in headers]] + [[cell(v, 'cell') for v in row] for row in rows]
    result = Table(data, colWidths=widths, repeatRows=1, hAlign='LEFT')
    result.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#eaeaea')),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LINEBELOW', (0, 0), (-1, 0), 0.7, colors.HexColor('#aaaaaa')),
        ('LINEBELOW', (0, 1), (-1, -1), 0.35, colors.HexColor('#d5d5d5')),
        ('LEFTPADDING', (0, 0), (-1, -1), 6), ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 6), ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.extend([result, Spacer(1, 8)])


class ScreenRegion(Flowable):
    def __init__(self, filename, box, width=W):
        super().__init__()
        self.path = ROOT / 'evidence' / 'screenshots' / filename
        self.box, self.width = box, width
        self.height = width * box[3] / box[2]
        self.hAlign = 'CENTER'

    def draw(self):
        im = ImageReader(str(self.path))
        iw, ih = im.getSize()
        x, y, w, height = self.box
        assert 0 <= x and 0 <= y and x+w <= iw and y+height <= ih
        scale = self.width / w
        c = self.canv
        c.saveState()
        clip = c.beginPath()
        clip.rect(0, 0, self.width, self.height)
        c.clipPath(clip, stroke=0)
        c.drawImage(im, -x*scale, self.height-(ih-y)*scale, iw*scale, ih*scale)
        c.restoreState()
        px, py = c.absolutePosition(0, 0)
        views.append({'source': self.path.name, 'source_box': self.box, 'source_size': [iw, ih],
                      'page': c.getPageNumber(), 'page_box': [px, py, px+self.width, py+self.height],
                      'scale': scale, 'sha256': hashlib.sha256(self.path.read_bytes()).hexdigest()})


def screenshot(filename, regions, caption, width=W):
    panels = []
    for i, box in enumerate(regions):
        if i:
            panels.append(Spacer(1, 5))
        panels.append(ScreenRegion(filename, box, width))
    panels.append(Paragraph(caption, styles['caption']))
    story.append(KeepTogether(panels))


audit = read('evidence/source-audit.json')
analysis = read('results/analysis.json')
verification = read('evidence/verification.json')
bench = read('evidence/benchmark-summary.json')
runs = read('evidence/benchmark-runs.json')
mr = read('results/optimized-1/metadata.json')
fault = read('results/mapper-failure/metadata.json')
env = read('evidence/environment.json')
selected_n = mr['selected_vacancies']
growth = {r['stack_size']: r for r in verification['growth']}
region_overview = {r['area']: r for r in analysis['regions_overview']}

# Title.
p('МИНИСТЕРСТВО НАУКИ И ВЫСШЕГО ОБРАЗОВАНИЯ<br/>РОССИЙСКОЙ ФЕДЕРАЦИИ', 'caption')
story.append(Spacer(1, 7*mm))
p('УНИВЕРСИТЕТ ИТМО', 'caption')
story.append(Spacer(1, 35*mm))
p('ОТЧЁТ ПО ЛАБОРАТОРНОЙ РАБОТЕ 3', 'caption')
story.append(Paragraph('Технология MapReduce', ParagraphStyle('title', fontName='Times-Bold', fontSize=21, leading=27, alignment=TA_CENTER, spaceAfter=15)))
story.append(Paragraph('Сравнение MapReduce и DuckDB<br/>при анализе ИТ-вакансий', ParagraphStyle('subtitle', fontName='Times', fontSize=15, leading=21, alignment=TA_CENTER)))
story.append(Spacer(1, 10*mm))
p('Вариант 1: программист, разработчик на 1С', 'caption')
story.append(Spacer(1, 27*mm))
story.append(Paragraph('Выполнил:<br/>Карташов Игорь Олегович<br/>Группа J3312', ParagraphStyle('author', fontName='Times', fontSize=14, leading=20, alignment=TA_RIGHT)))
story.append(Spacer(1, 35*mm))
p('Санкт-Петербург<br/>2026', 'caption')
page()

h('1. Стенд и исходные данные')
p('Я сравнил собственный MapReduce и DuckDB на вакансиях разработчиков 1С: посчитал навыки, пары и тройки, проверил совпадение результатов, измерил время и память. Затем сравнил зарплаты и три региона.')
table(['Параметр', 'Значение'], [
    ['Компьютер', 'Windows 11, Ryzen 7 7840H, 8 ядер / 16 потоков, 32 ГБ ОЗУ'],
    ['Программы', 'RustFS 1.0.3; Python 3.12.14; DuckDB 2.0.0; boto3 1.43.118'],
    ['Хранилище', 'Стенд работы 2: четыре папки, EC 2+2; S3 127.0.0.1:9000; бакет hh-lake'],
], [90, W-90])
p('Основной источник — <link href="https://drive.google.com/file/d/1rLEu3N2isIBhAkK1EcSJ2482ouOPAots/view" color="#224d73">it_vacancies_2024.csv преподавателя</link>: <b>229 388 вакансий, 847 619 384 байта</b>. В нём есть должность, роль, регион, навыки и зарплата. Все папки RustFS находятся на одном физическом диске E:.')
p('Из архива на 10 000 JSON я случайно выбрал 1 000 файлов с seed=42 и загрузил их как JSONL. В этой выборке только 74 вакансии варианта, поэтому основной расчёт выполнен по полному CSV.')
code('.\\Run-Lab.ps1 init-storage\n.\\Run-Lab.ps1 audit\n.\\Run-Lab.ps1 upload\n\nСводка загрузки:\nhh-lake: HTTP 200\nraw/it_vacancies_2024.csv: 847619384 bytes; HTTP 200\nraw/hh-sample-1000.jsonl: 5402691 bytes; HTTP 200')
screenshot('raw-objects.jpg', [(0,0,850,65),(280,260,650,145)], 'Рисунок 1. Бакет hh-lake: исходный CSV и случайная выборка JSON.')
p('У каждого объекта проверены размер и контрольная сумма. При полном чтении CSV через MapReduce SHA-256 совпал с исходным файлом.')
page()

h('2. Отбор варианта и собственный MapReduce')
p('Я отбирал программистов и разработчиков на 1С по роли и названию вакансии. Исключил Битрикс и Java Developer: упоминание продукта 1С в названии ещё не означает работу на языке 1С.')
code("role = 'Программист, разработчик'\nAND regexp_matches(lower(name), '1[сc]')\nAND regexp_matches(lower(name),\n    'программист|разработчик|developer|programmer')\nAND NOT regexp_matches(lower(name), 'битрикс|bitrix')\nAND NOT regexp_matches(lower(name), 'java[[:space:]-]+developer')")
table(['Пример названия', 'Результат'], [
    ['Программист 1С; Разработчик 1C:CRM', 'Включены при нужной роли'],
    ['Консультант 1C; Системный аналитик 1С', 'Исключены'],
    ['PHP / Программист 1С-Битрикс в веб-студию', 'Исключена'],
    ['Java Developer (разработка технологии 1С:Предприятие.Элемент)', 'Исключена'],
], [W-140,140])
table(['Показатель', 'Вакансий'], [
    ['Все строки CSV; повторных source:vacancy_id нет', n(audit['counts']['input_rows'])],
    ['Упоминание 1С/1C в названии', n(audit['counts']['name_mentions_1c'])],
    ['После полного условия варианта', n(mr['selected_vacancies'])],
    ['Из них с непустым списком навыков', n(audit['counts']['selected_with_skills'])],
], [W-100,100])
sub('Как устроен расчёт')
p('Сначала get_object открывает поток S3. Я читаю его порциями по 1 МиБ и передаю CSV-парсеру, который сохраняет многострочные поля и символы UTF-8 на границе порций. За полный проход прочитаны 847 619 384 байта за 809 чтений тела ответа.')
p('Строки собираются в батчи по 1 000 записей; четыре процесса-маппера независимо применяют условие варианта. Навыки разделяются по «;», очищаются от пробелов и приводятся к нижнему регистру. Повторы навыка внутри одной вакансии удаляются.')
p('Маппер выдаёт неупорядоченные сочетания размеров 1, 2 и 3. Затем reducer суммирует одинаковые ключи. У вакансии с n навыками получается C(n,k)=n!/[k!(n-k)!] сочетаний. Например, шесть навыков дают 6 одиночных записей, 15 пар и 20 троек.')
page()

h('3. Независимый SQL и проверка частот')
p('DuckDB читает тот же s3://hh-lake/raw/it_vacancies_2024.csv через httpfs. Условие варианта написано отдельно на SQL. После очистки списка навыков я присвоил им позиции и построил сочетания соединением строк одной вакансии:')
code('SELECT a.vacancy_key, a.skill, b.skill\nFROM skill_positions a JOIN skill_positions b\n  ON a.vacancy_key=b.vacancy_key AND a.position<b.position;\n\nSELECT a.vacancy_key, a.skill, b.skill, c.skill\nFROM skill_positions a\nJOIN skill_positions b ON a.vacancy_key=b.vacancy_key\n                     AND a.position<b.position\nJOIN skill_positions c ON a.vacancy_key=c.vacancy_key\n                     AND b.position<c.position;')
table(['Размер стека', 'Выдано сочетаний', 'Разных ключей', 'Расхождений'], [
    [str(r['stack_size']), n(r['emitted_combinations']), n(r['unique_combinations']), '0'] for r in verification['growth']
], [90,140,135,W-365])
p('Проверены все ключи и частоты, а также состав выбранных вакансий по SHA-256 отсортированного списка идентификаторов. Оба способа выбрали '+n(selected_n)+' вакансии. Суммы частот совпали с суммой C(n,k) по всем вакансиям.')
code('.\\Run-Lab.ps1 verify\n\nСводка проверки:\nall_equal: true\nselected_vacancies: '+str(selected_n)+'\ndifferent_keys: 0 (k=1, k=2, k=3)')
sub('Наиболее частые навыки')
table(['Навык', 'Вакансий', 'Доля от '+n(selected_n)], [
    [r['skill_1'], n(r['vacancies']), dec(100*r['vacancies']/selected_n,1)+'%'] for r in analysis['top_skills'][:5]
], [W-170,85,85])
p('От одиночных навыков к парам число выдач выросло в '+dec(growth[2]['emitted_combinations']/growth[1]['emitted_combinations'],2)+' раза, от пар к тройкам — ещё в '+dec(growth[3]['emitted_combinations']/growth[2]['emitted_combinations'],2)+' раза. Это результат перебора сочетаний внутри каждой вакансии.')
page()

h('4. Время, память и оптимизация')
p('Каждый подход я запускал трижды отдельным процессом. MapReduce использовал четыре процесса, DuckDB — четыре потока с лимитом памяти 2 ГБ. Порядок менялся между сериями. Время включает запуск, чтение S3, вычисление и запись таблиц; httpfs был установлен заранее.')
p('Память измерял внешним монитором как максимум суммарного RSS клиента и его дочерних процессов. Между опросами задана пауза 5 мс; сам опрос тоже занимает время. Сервер RustFS в эти значения не входит. Кеш ОС между запусками не очищался.')
labels = {'baseline':'MapReduce', 'optimized':'MapReduce с оптимизацией', 'duckdb':'DuckDB'}
table(['Способ', 'Попытка', 'Время, с', 'Пик RSS, МиБ'], [
    [labels[method], str(r['trial']), dec(r['wall_seconds']), dec(r['peak_process_tree_rss_bytes']/1048576,1)]
    for method in ['baseline','optimized','duckdb'] for r in runs if r['method']==method
], [205,60,95,W-360])
table(['Способ', 'Медиана времени, с', 'Медиана пиков RSS, МиБ'], [
    [labels[method],dec(bench[method]['median_wall_seconds']),dec(bench[method]['median_peak_rss_mib'],1)]
    for method in ['baseline','optimized','duckdb']
], [205,125,W-330])
time_saved = 100*(1-bench['optimized']['median_wall_seconds']/bench['baseline']['median_wall_seconds'])
mem_saved = 100*(1-bench['optimized']['median_peak_rss_mib']/bench['baseline']['median_peak_rss_mib'])
p('В базовой версии мапперам передавались полные строки, включая описание вакансии, а промежуточные записи накапливались перед reduce. В оптимизированной версии я оставил для передачи пять нужных полей и добавил локальный combiner. Время сократилось на <b>'+dec(time_saved,1)+'%</b>, память — на <b>'+dec(mem_saved,1)+'%</b>; результаты не изменились.')
p('DuckDB оказался в '+dec(bench['optimized']['median_wall_seconds']/bench['duckdb']['median_wall_seconds'],2)+' раза быстрее оптимизированного MapReduce, но использовал в '+dec(bench['duckdb']['median_peak_rss_mib']/bench['optimized']['median_peak_rss_mib'],2)+' раза больше памяти. SQL выполняет разбор и агрегацию в движке; у Python добавляются создание объектов и обмен батчами между процессами.')
page()

h('5. Отказ маппера и результаты в S3')
p('Для проверки отказа я завершил процесс, обрабатывающий второй батч, с кодом 73. Родитель получил BrokenProcessPool, создал новый пул и повторил незафиксированный батч. Уже учтённые батчи повторно в reducer не попадали.')
code('.\\Run-Lab.ps1 fault\n.\\Run-Lab.ps1 verify\n\nСводка проверки отказа:\nmapper_process_exit: 73\nuncommitted_batches_replayed: 1\ncommitted_batches: 230 / 230\nselected_vacancies: '+str(fault['selected_vacancies'])+'\ndifferent_keys_after_recovery: 0')
p('После восстановления частоты и выбранные идентификаторы полностью совпали с обычным запуском. Отдельные проверки подтвердили чтение UTF-8 и многострочного CSV при границе порции в три байта, удаление повторных навыков и исключение чужих профессий.')
table(['Файл результата', 'Размер, байт', 'Проверка обратным чтением'], [
    [Path(r['key']).name, n(r['bytes']), 'Совпал']
    for r in verification['results_in_s3'] if '/mapreduce/' in r['key']
], [155,110,W-265])
p('Все три файла записаны отдельно для MapReduce и DuckDB в hh-lake/results/variant-01/. Итого сохранено шесть объектов. Соответствующие файлы двух способов совпадают побайтно.')
screenshot('mapreduce-results.jpg', [(265,0,755,126),(280,260,650,195)], 'Рисунок 2. Результаты MapReduce для одиночных навыков, пар и троек в S3.')
page()

h('6. Зарплаты: пары навыков')
p('В зарплатное сравнение вошли <b>7 594 вакансии</b> с рублёвой суммой на руки (gross=false). При двух границах я брал их среднее, при одной — указанную границу. Медиана сегмента составила <b>150 000 руб.</b> Вакансии без такой зарплаты остаются в общих частотах навыков.')
p('Для пары база — более частый отдельный навык по всему сегменту. Сравниваю медиану вакансий с базой M0 и медиану вакансий со всей парой M: Δ=M-M0. В рейтинг включены сочетания хотя бы с 20 зарплатами; n0/n — число зарплатных наблюдений базы и сочетания.')


def effects_table(k):
    groups = analysis['salary_rankings'][str(k)]
    rows = []
    for direction in ['higher','lower']:
        for r in groups[direction][:3]:
            change = ('+' if r['difference_rub'] > 0 else '') + n(r['difference_rub'])
            percent = ('+' if r['difference_percent'] > 0 else '') + dec(r['difference_percent'],1)+'%'
            rows.append([r['base_skills']+'\nN0='+n(r['base_vacancies']),
                         r['added_skill']+'\nN='+n(r['vacancies']),
                         n(r['base_salary_vacancies'])+' / '+n(r['salary_vacancies']),
                         n(r['base_median_salary']),n(r['median_salary']),change+'\n'+percent])
    table(['Базовый навык' if k==2 else 'Базовая пара','Добавлен навык','n0 / n','M0, руб.','M, руб.','Разница'],
          rows,[135,103,55,60,60,W-413])


effects_table(2)
p('N0 и N — частоты базы и полного сочетания среди всех вакансий варианта. Из 680 пар с нужным числом зарплат выше показаны три наибольшие положительные и три наибольшие отрицательные разницы.')
p('У пары «1С программирование + Java» медиана выше базы на 120 000 руб., но 18 из 27 зарплатных объявлений размещены одним работодателем. Если исключить его из обеих групп, у оставшихся девяти объявлений пары медиана равна 30 000 руб., у базы — 150 000 руб. Высокий результат здесь связан с составом объявлений; считать его обычной надбавкой за Java нельзя.')
p('У «ERP-системы на базе 1С + работа с базами данных» медиана ниже на 80 000 руб. В этой группе 28 зарплат от 18 работодателей. Без крупнейшего работодателя остаются 22 наблюдения с медианой 137 500 руб.; разрыв с базой сокращается до 42 500 руб. Состав работодателей заметно влияет и на отрицательные результаты.')
page()

h('7. Зарплаты: тройки навыков')
p('Для тройки базой служит самая частая из трёх входящих пар. Частота определяется по всем вакансиям варианта; при равенстве выбирается первая пара по алфавиту. Порог в 20 зарплатных наблюдений и формула разницы те же, что для пар.')
effects_table(3)
p('Из 1 472 троек с достаточным числом зарплат наибольшая положительная разница — <b>109 500 руб. (+73%)</b>: к паре «1c: бухгалтерия + 1с: зарплата и управление персоналом» добавляется «1с: торговля». Медианы базы и тройки — 150 000 и 259 500 руб.')
p('У этой тройки 20 зарплатных наблюдений от шести работодателей, причём 14 объявлений приходятся на одного. После его исключения остаются шесть наблюдений с медианой 250 000 руб. Для общей оценки зарплат такой группы мало.')
p('Наибольшая отрицательная разница — <b>80 000 руб. (-44,4%)</b> у добавления «работа с базами данных» к паре «1С программирование + ERP-системы на базе 1С»: 100 000 против 180 000 руб. После исключения крупнейшего работодателя медиана тройки повышается до 125 000 руб., а база остаётся на 180 000 руб.')
p('Разницу медиан нельзя считать прибавкой конкретному работнику: сравниваются разные вакансии, работодатели и требования к опыту.')
page()

h('8. Регионы: число вакансий и зарплаты')
p('Я выбрал Москву, Санкт-Петербург и Екатеринбург — три региона с наибольшим числом вакансий моего варианта. Сравнение включает весь сегмент, а не только объявления с заполненными навыками.')
code('SELECT s.area, count(*) AS vacancies,\n       count_if(len(s.skills)>0) AS with_skills,\n       count(p.salary) AS salary_vacancies, median(p.salary)\nFROM selected s JOIN paid p USING(vacancy_key)\nGROUP BY s.area ORDER BY vacancies DESC LIMIT 3;')
table(['Регион','Всего','С навыками','С зарплатой','Медиана, руб.'], [
    [r['area'],n(r['vacancies']),n(r['vacancies_with_skills']),n(r['salary_vacancies']),n(r['median_salary'])]
    for r in analysis['regions_overview']
], [112,70,90,90,W-362])
p('Москва содержит '+dec(100*region_overview['Москва']['vacancies']/selected_n,1)+'% всех вакансий варианта. Её медиана выше Екатеринбурга на 50 000 руб. (+33,3%) и Санкт-Петербурга на 25 000 руб. (+14,3%).')
p('Доля объявлений с сопоставимой зарплатой различается: '+dec(100*region_overview['Москва']['salary_vacancies']/region_overview['Москва']['vacancies'],1)+'% в Москве, '+dec(100*region_overview['Санкт-Петербург']['salary_vacancies']/region_overview['Санкт-Петербург']['vacancies'],1)+'% в Санкт-Петербурге и '+dec(100*region_overview['Екатеринбург']['salary_vacancies']/region_overview['Екатеринбург']['vacancies'],1)+'% в Екатеринбурге. Медианы рассчитаны только по этим объявлениям.')
sub('Наиболее частый отдельный навык')
best = [r for r in analysis['regional_combinations'] if r['place']==1 and r['stack_size']==1]
best.sort(key=lambda r: analysis['regions'].index(r['area']))
table(['Регион','Навык','Вакансий','Доля региона'], [
    [r['area'],r['skill_1'],n(r['vacancies']),dec(r['share_percent'],1)+'%'] for r in best
], [112,W-272,75,85])
p('Во всех трёх регионах лидирует «1С программирование». Его доля выше в Екатеринбурге (58,7%), затем идут Санкт-Петербург (56,5%) и Москва (49,1%). Для долей использовал все вакансии региона, включая объявления без навыков.')
page()

h('9. Регионы: пары и тройки навыков')
p('Для каждого региона я сгруппировал сочетания отдельно. Ниже — самая частая пара и тройка; медиана рассчитана по вакансиям этой комбинации с сопоставимой рублёвой зарплатой.')
code('SELECT p.area,c.stack_size,c.skill_1,c.skill_2,c.skill_3,\n       count(*) AS vacancies, count(p.salary) AS salary_n,\n       median(p.salary) AS median_salary\nFROM combinations c JOIN paid p USING(vacancy_key)\nGROUP BY p.area,c.stack_size,c.skill_1,c.skill_2,c.skill_3;')
regional = [r for r in analysis['regional_combinations'] if r['place']==1 and r['stack_size']>=2]
regional.sort(key=lambda r:(analysis['regions'].index(r['area']),r['stack_size']))
table(['Регион / k','Наиболее частое сочетание','Частота / доля','Медиана, руб. / n'], [
    [r['area']+'\nk='+str(r['stack_size']),
     ' + '.join([r['skill_1'],r['skill_2'],r['skill_3']][:r['stack_size']]),
     n(r['vacancies'])+' / '+dec(r['share_percent'],1)+'%',
     n(r['median_salary'])+'\nn='+n(r['salary_vacancies'])]
    for r in regional
], [100,220,80,W-400])
p('Лидирующая пара одинакова: «1С программирование + 1С: Предприятие 8». Она встречается в 20,5% московских, 23,1% петербургских и 24,2% екатеринбургских вакансий. При этом её медианы различаются: 200 000, 177 500 и 150 000 руб. соответственно.')
p('В Москве и Екатеринбурге к лидирующей паре в самой частой тройке добавляется «1С: Бухгалтерия», в Санкт-Петербурге — «1С: Управление торговлей». У петербургской тройки медиана 165 000 руб., что ниже общей медианы города 175 000 руб. Самое частое сочетание не обязательно самое высокооплачиваемое.')
sub('Вывод')
p('MapReduce и DuckDB дали одинаковые частоты всех '+n(sum(r['unique_combinations'] for r in growth.values()))+' разных навыков и сочетаний. Для этой задачи я выбрал бы DuckDB: он быстрее, а его расход памяти укладывается в 32 ГБ стенда. Потоковый MapReduce полезен при более жёстком ограничении памяти. Отказ маппера не изменил результат. При сравнении зарплат нужно учитывать регион и работодателя: у одной из лидирующих пар 18 из 27 зарплатных объявлений размещены одной компанией.')
repository_path = ROOT / 'evidence' / 'repository.json'
if repository_path.is_file():
    repository = json.loads(repository_path.read_text(encoding='utf-8'))['url']
    p('Код и отчёт: <link href="'+repository+'" color="#224d73">'+html.escape(repository.removeprefix('https://'))+'</link>.')

page()
h('Приложение. Ход работы')
screenshot('csv-properties.jpg', [(1035,0,675,60),(1055,178,635,181)],
           'Рисунок 3. Свойства исходного CSV: размер, тип и время загрузки.')
screenshot('sql-filter.jpg', [(325,6,660,45),(375,470,610,126)],
           'Рисунок 4. SQL-фильтр варианта 1С в опубликованном коде.')
screenshot('skills-preview.jpg', [(405,95,600,239)],
           'Рисунок 5. Начало CSV с частотами навыков в RustFS.')
page()
h('Приложение. Замеры и проверка')
screenshot('benchmark-runs.jpg', [(325,6,605,45),(345,216,385,349)],
           'Рисунок 6. Время и пик RSS в девяти запусках.', width=350)
screenshot('result-checks.jpg', [(325,6,555,45),(374,174,485,287)],
           'Рисунок 7. Полная сверка результатов и отказ маппера.', width=395)
page()
h('Приложение. Запуск расчёта')
screenshot('terminal-compute.jpg', [(395,10,920,610)],
           'Рисунок 8. Локальная консоль: повторный запуск MapReduce и DuckDB.')
screenshot('terminal-verify.jpg', [(395,10,920,510)],
           'Рисунок 9. Локальная консоль: полная сверка и обратное чтение из S3.')


def footer(canvas, document):
    if document.page == 1:
        return
    canvas.saveState()
    canvas.setFont('Times',9)
    canvas.setFillColor(colors.HexColor('#555555'))
    canvas.drawString(20*mm,14*mm,'Карташов И. О. | J3312 | MapReduce и DuckDB | Вариант 1')
    canvas.drawRightString(A4[0]-20*mm,14*mm,str(document.page))
    canvas.restoreState()


doc = SimpleDocTemplate(str(OUT), pagesize=A4, leftMargin=20*mm, rightMargin=20*mm,
                        topMargin=18*mm, bottomMargin=20*mm, title='MapReduce и DuckDB: разработчики 1С',
                        author='Карташов Игорь Олегович', subject='Лабораторная работа 3, J3312, ИТМО')
doc.build(story,onFirstPage=footer,onLaterPages=footer)
(ROOT/'evidence'/'pdf-image-views.json').write_text(json.dumps(views,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
import pymupdf
pdf = pymupdf.open(OUT)
for i,pg in enumerate(pdf):
    pg.get_pixmap(matrix=pymupdf.Matrix(1.4,1.4),alpha=False).save(ROOT/'tmp'/'pdfs'/f'page-{i+1:02}.png')
print(OUT)
print('Pages:',len(pdf))
for i,pg in enumerate(pdf):
    lines=pg.get_text().splitlines()
    print(i+1,len(pg.get_text()),lines[1:3])
